"""
Aura-Sync: Node B gRPC 서버
============================
aura.proto 기준으로 Node C의 ContextualPrompt를 수신하여
EmpathyResponse를 반환

실행 방법:
  1. Proto 컴파일 (최초 1회)
     pip3 install grpcio grpcio-tools --break-system-packages
     python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. aura.proto

  2. 서버 실행
     python3 node_b_server.py

  3. Mock 모드 (Ollama 없이)
     python3 node_b_server.py --mock

네트워크:
  Node C → Node B: 0.0.0.0:50052
"""

import grpc
import time
import argparse
import logging
from concurrent import futures

import aura_pb2
import aura_pb2_grpc

from test_node_b import (
    NodeBCore, NodeCPacket,
    clean_kg_context, check_crisis,
    CRISIS_RESPONSE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Node B] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

NODE_B_PORT  = 5051
NODE_A_PORT  = 5050        # Node A TTS 수신 포트 (팀원과 확인 필요)
NODE_A_HOST  = "192.168.0.46"  # Node A IP (팀원과 확인 필요)
MAX_WORKERS  = 4


# ──────────────────────────────────────────
# TTS 전송 클라이언트 (Node B → Node A)
# ──────────────────────────────────────────

class TTSClient:
    """
    공감 발화 생성 후 Node A로 TTSRequest 전송
    Node A의 AuraTTS.SendDialogue 호출
    """

    def __init__(self, host: str = NODE_A_HOST, port: int = NODE_A_PORT):
        self.addr    = f"{host}:{port}"
        self.channel = None
        self.stub    = None
        self._connect()

    def _connect(self):
        try:
            self.channel = grpc.insecure_channel(
                self.addr,
                options=[("grpc.connect_timeout_ms", 3000)],
            )
            self.stub = aura_pb2_grpc.AuraTTSStub(self.channel)
            log.info(f"TTS 클라이언트 초기화: {self.addr}")
        except Exception as e:
            log.error(f"TTS 클라이언트 초기화 실패: {e}")
            self.stub = None

    def send(self, session_id, text, valence, arousal, strategy) -> bool:
        """
        Node A로 TTSRequest 전송
        실패해도 Fail-safe — 로그만 남기고 계속 진행
        """
        if not self.stub:
            log.warning("TTS 클라이언트 없음 — 재연결 시도")
            self._connect()
            if not self.stub:
                return False
        try:
            req = aura_pb2.TTSRequest(
                session_id = session_id,
                text       = text,
                valence    = valence,
                arousal    = arousal,
                strategy   = strategy,
            )
            self.stub.SendDialogue(req, timeout=5)
            log.info(f"[TTS] 전송 완료 | session={session_id} | text='{text[:30]}...'")
            return True
        except grpc.RpcError as e:
            log.error(f"[TTS] 전송 실패: {e.code()} — {e.details()}")
            return False
        except Exception as e:
            log.error(f"[TTS] 전송 오류: {e}")
            return False

    def close(self):
        if self.channel:
            self.channel.close()


# ──────────────────────────────────────────
# AuraService 구현 (Node C → Node B)
# ──────────────────────────────────────────

class AuraServicer(aura_pb2_grpc.AuraServiceServicer):
    """
    Node C가 ContextualPrompt를 보내면
    EmpathyResponse를 반환하는 서비스
    """

    def __init__(self, use_real_llm: bool = False):
        self.node_b     = NodeBCore(use_real_llm=use_real_llm)
        self.tts_client = TTSClient()
        log.info(f"AuraServicer 초기화 완료 (LLM: {'Ollama' if use_real_llm else 'Mock'})")

    def GenerateEmpathy(
        self,
        request: aura_pb2.ContextualPrompt,
        context: grpc.ServicerContext,
    ) -> aura_pb2.EmpathyResponse:
        """
        ContextualPrompt 수신 → EmpathyResponse 반환

        proto 필드 매핑:
          request.final_prompt  → NodeCPacket.prompt
          request.user_text     → NodeCPacket.stt_text (Fail-safe용)
          request.valence       → NodeCPacket.valence
          request.arousal       → NodeCPacket.arousal
          request.session_id    → BRDCalculator user_id
          request.request_id    → 응답에 그대로 반환
        """
        has_text = bool(request.user_text.strip())
        text_log = f"'{request.user_text[:30]}...'" if has_text else "⚠️ 텍스트 없음 (표정만)"
        log.info(
            f"[{request.request_id}] 수신 | "
            f"session={request.session_id} | "
            f"V={request.valence:.2f} A={request.arousal:.2f} | "
            f"text={text_log}"
        )
        if not has_text:
            log.warning(f"[{request.request_id}] 텍스트 미수신 — 표정 데이터만으로 처리")

        t_start = time.time()

        try:
            # ── Step 1: Fail-safe (Priority 0) ──────────
            if check_crisis(request.user_text):
                latency = (time.time() - t_start) * 1000
                log.warning(f"[{request.request_id}] ⚠️ 위기 감지 — LLM 차단")
                return aura_pb2.EmpathyResponse(
                    session_id    = request.session_id,
                    request_id    = request.request_id,
                    text          = CRISIS_RESPONSE,
                    response_time = latency,
                    strategy      = "CRISIS",
                    error_code    = aura_pb2.ErrorCode.NONE,
                )

            # ── Step 2: NodeCPacket 변환 ─────────────────
            # kg_context는 ContextualPrompt에 없으므로
            # fused_emotion의 primary_emotion을 활용
            kg_context = []
            if request.fused_emotion.primary_emotion:
                kg_context = [request.fused_emotion.primary_emotion]

            packet = NodeCPacket(
                prompt     = request.final_prompt,
                valence    = request.valence,
                arousal    = request.arousal,
                stt_text   = request.user_text,
                kg_context = kg_context,
                timestamp  = request.timestamp,
            )

            # ── Step 3: NodeBCore 처리 ───────────────────
            # BRD는 session_id 기준으로 개인화
            self.node_b.brd.user_id = request.session_id or "default"
            result = self.node_b.process(packet)

            # ── Step 4: 전략 결정 ────────────────────────
            brd = result.get("brd")
            if brd:
                empathy_mode = brd.get("empathy_mode", "NORMAL")
            else:
                empathy_mode = "NORMAL"

            strategy = _select_strategy(
                request.valence,
                request.arousal,
                empathy_mode,
                request.fused_emotion,
            )

            latency = (time.time() - t_start) * 1000
            log.info(
                f"[{request.request_id}] 완료 | "
                f"strategy={strategy} | "
                f"latency={latency:.1f}ms"
            )

            # ── Step 5: TTS 전송 (Node A) ────────────────
            self.tts_client.send(
                session_id = request.session_id,
                text       = result["response"],
                valence    = request.valence,
                arousal    = request.arousal,
                strategy   = strategy,
            )

            return aura_pb2.EmpathyResponse(
                session_id    = request.session_id,
                request_id    = request.request_id,
                text          = result["response"],
                response_time = latency,
                strategy      = strategy,
                error_code    = aura_pb2.ErrorCode.NONE,
            )

        except Exception as e:
            latency = (time.time() - t_start) * 1000
            log.error(f"[{request.request_id}] 오류: {e}")
            return aura_pb2.EmpathyResponse(
                session_id    = request.session_id,
                request_id    = request.request_id,
                text          = "",
                response_time = latency,
                error_code    = aura_pb2.ErrorCode.UNKNOWN_ERROR,
                error_message = str(e),
            )


# ──────────────────────────────────────────
# AuraPerception 구현 (Node A → Node B, Fail-safe용)
# Node A가 직접 Node B에 하트비트 보내는 경우
# ──────────────────────────────────────────

class AuraPerceptionServicer(aura_pb2_grpc.AuraPerceptionServicer):
    """
    Node A의 감정 후보 수신 (Fail-safe 모니터링용)
    Node C 장애 시 Node B가 직접 Node A 데이터로 최소 응답 생성
    """

    def __init__(self, node_b: NodeBCore):
        self.node_b    = node_b
        self.last_seen = {}   # node_id → timestamp

    def SendFacePerception(
        self,
        request: aura_pb2.EmotionCandidate,
        context: grpc.ServicerContext,
    ) -> aura_pb2.EmpathyResponse:
        """
        Node A 하트비트 수신
        Node C 장애 시 최소한의 응답 생성
        """
        self.last_seen[request.source] = time.time()
        log.info(
            f"[Heartbeat] Node A 수신 | "
            f"source={request.source} | "
            f"emotion={request.emotion_label} | "
            f"V={request.valence:.2f}"
        )

        # Node C 없이 최소 응답 (Fail-safe 모드)
        packet = NodeCPacket(
            prompt   = _make_fallback_prompt(request),
            valence  = request.valence,
            arousal  = request.arousal,
            stt_text = "",
        )
        result = self.node_b.process(packet)

        return aura_pb2.EmpathyResponse(
            session_id = request.source,
            request_id = "failsafe",
            text       = result["response"],
            strategy   = "FAILSAFE",
            error_code = aura_pb2.ErrorCode.NONE,
        )


# ──────────────────────────────────────────
# 헬퍼 함수
# ──────────────────────────────────────────

def _select_strategy(
    valence       : float,
    arousal       : float,
    empathy_mode  : str,
    fused_emotion : aura_pb2.FusedEmotionState,
) -> str:
    """
    감정 상태 + BRD 모드 → 응답 전략 결정
    EmpathyResponse.strategy 필드에 기록
    """
    primary = fused_emotion.primary_emotion if fused_emotion else ""

    if empathy_mode == "HIGH":
        if valence < -0.5 and arousal < -0.3:
            return "DEEP_VALIDATION"     # 우울/무기력 → 깊은 수용
        elif valence < -0.5 and arousal > 0.3:
            return "ANGER_ACKNOWLEDGMENT"  # 분노/좌절 → 감정 인정
        else:
            return "HIGH_EMPATHY"
    else:
        if abs(valence) < 0.2:
            return "NEUTRAL_CHAT"        # 중립 → 일상 대화
        else:
            return "NORMAL_EMPATHY"


def _make_fallback_prompt(candidate: aura_pb2.EmotionCandidate) -> str:
    """Node C 장애 시 최소 프롬프트 생성"""
    return f"""[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.
따뜻하고 판단 없이 응답하세요.

[감정 분석]
- 감지된 감정: {candidate.emotion_label}
- V={candidate.valence:.2f}, A={candidate.arousal:.2f}
- ※ 센서 데이터만 사용 중 (Node C 장애)

[응답 규칙]
1. 짧고 따뜻하게 (1~2문장)
2. 조언 금지

[ASSISTANT]"""


# ──────────────────────────────────────────
# 서버 실행
# ──────────────────────────────────────────

def serve(use_real_llm: bool = False):
    node_b = NodeBCore(use_real_llm=use_real_llm)

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=MAX_WORKERS),
        options=[
            ("grpc.max_send_message_length",    10 * 1024 * 1024),  # 10MB
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
            ("grpc.keepalive_time_ms",          10000),  # 10초마다 keepalive
            ("grpc.keepalive_timeout_ms",        5000),
        ]
    )

    # 서비스 등록
    aura_pb2_grpc.add_AuraServiceServicer_to_server(
        AuraServicer(use_real_llm=use_real_llm), server
    )
    aura_pb2_grpc.add_AuraPerceptionServicer_to_server(
        AuraPerceptionServicer(node_b), server
    )

    addr = f"0.0.0.0:{NODE_B_PORT}"
    server.add_insecure_port(addr)
    server.start()

    log.info(f"Node B gRPC 서버 시작: {addr}")
    log.info(f"LLM 모드: {'Ollama (Gemma)' if use_real_llm else 'Mock'}")
    log.info("Node C 연결 대기 중...")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        log.info("서버 종료 중...")
        server.stop(grace=3)
        log.info("서버 종료 완료")
        # TTS 클라이언트 정리는 AuraServicer 내부에서 관리


# ──────────────────────────────────────────
# 클라이언트 테스트 (Node C 역할 Mock)
# ──────────────────────────────────────────

def test_client():
    """
    Node C 없이 서버 동작 확인용 Mock 클라이언트
    별도 터미널에서 실행: python3 node_b_server.py --test-client
    """
    import uuid

    channel = grpc.insecure_channel(f"localhost:{NODE_B_PORT}")
    stub    = aura_pb2_grpc.AuraServiceStub(channel)

    test_cases = [
        {
            "name": "이별 — 슬픔",
            "prompt": aura_pb2.ContextualPrompt(
                session_id   = "user_001",
                request_id   = str(uuid.uuid4())[:8],
                final_prompt = "[SYSTEM]\n당신은 AI 상담사입니다.\n[USER]\n이별했어요, 너무 힘들어요\n[ASSISTANT]",
                valence      = -0.9,
                arousal      = -0.4,
                user_text    = "이별했어요, 너무 힘들어요",
                timestamp    = int(time.time() * 1000),
                fused_emotion= aura_pb2.FusedEmotionState(
                    primary_emotion = "슬픔",
                    confidence      = 0.91,
                    valence         = -0.9,
                    arousal         = -0.4,
                ),
            ),
        },
        {
            "name": "위기 감지 — Fail-safe",
            "prompt": aura_pb2.ContextualPrompt(
                session_id   = "user_001",
                request_id   = str(uuid.uuid4())[:8],
                final_prompt = "[USER]\n사라지고 싶어요\n[ASSISTANT]",
                valence      = -0.99,
                arousal      = -0.8,
                user_text    = "너무 힘들어서 사라지고 싶어요",
                timestamp    = int(time.time() * 1000),
                fused_emotion= aura_pb2.FusedEmotionState(
                    primary_emotion = "절망",
                    confidence      = 0.97,
                    valence         = -0.99,
                    arousal         = -0.8,
                ),
            ),
        },
    ]

    for case in test_cases:
        print(f"\n{'='*50}")
        print(f"테스트: {case['name']}")
        print(f"{'='*50}")
        try:
            response = stub.GenerateEmpathy(
                case["prompt"],
                timeout=130,
            )
            print(f"  request_id : {response.request_id}")
            print(f"  strategy   : {response.strategy}")
            print(f"  latency    : {response.response_time:.1f}ms")
            print(f"  error_code : {response.error_code}")
            print(f"\n  [공감 발화]")
            print(f"  {response.text}")
        except grpc.RpcError as e:
            print(f"  gRPC 오류: {e.code()} — {e.details()}")


# ──────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Node B gRPC 서버")
    parser.add_argument(
        "--mock", action="store_true",
        help="Mock LLM 사용 (기본: Ollama)"
    )
    parser.add_argument(
        "--test-client", action="store_true",
        help="Mock 클라이언트로 서버 테스트 (서버 실행 후 별도 터미널에서)"
    )
    args = parser.parse_args()

    if args.test_client:
        test_client()
    else:
        serve(use_real_llm=not args.mock)
