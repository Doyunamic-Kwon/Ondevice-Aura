import grpc
from concurrent import futures
import sys
import os
import time
import math
import numpy as np

sys.path.append(os.path.dirname(__file__))
import aura_pb2
import aura_pb2_grpc
from bridge_sender_integrated import process_and_build_request, send_with_safety, get_node_c


class AuraPerceptionServicer(aura_pb2_grpc.AuraPerceptionServicer):
    def __init__(self):
        # ================================================
        # 감정 변화 임계치 필터링 (Emotion Change Throttling)
        # ================================================
        self.last_valence = 0.0
        self.last_arousal = 0.0
        self.last_sent_time = 0.0
        self.threshold = 0.12    # 유클리드 거리 기준 최소 변화량
        self.min_interval = 1.0  # 최소 전송 간격 (초)

    def is_significant_change(self, v: float, a: float) -> bool:
        """이전 상태 대비 감정 변화가 충분히 크고 최소 간격이 지났는지 확인."""
        now = time.time()
        if now - self.last_sent_time < self.min_interval:
            return False
        diff = math.sqrt((v - self.last_valence) ** 2 + (a - self.last_arousal) ** 2)
        return diff >= self.threshold

    def SendFacePerception(self, request, context):
        """
        표정 데이터 수신.

        [트리거 정책]
        - 텍스트(STT)가 없는 경우: face V-A 상태만 NodeC에 누적 저장하고 즉시 반환.
          Node B(LLM)는 호출하지 않는다. 표정만으로 LLM을 계속 트리거하면
          사용자가 말하지 않아도 AI가 반응하게 되어 대화 흐름이 어색해진다.
          누적된 face_va는 이후 텍스트가 들어올 때 3-모달 융합에 자동으로 참여한다.

        - 텍스트(STT)가 있는 경우: 전체 파이프라인(KG 검색 → 감성 분석 → Node B 전송)을 가동.
        """
        v, a = request.valence, request.arousal
        user_text = request.text if request.text else ""

        print(f"\n[Node C Server] 표정 수신: {request.emotion_label} (V:{v:.2f}, A:{a:.2f})")

        if not user_text:
            # 텍스트 없음: 상태 누적만 수행, Node B 호출 없음
            if self.is_significant_change(v, a):
                self.last_valence = v
                self.last_arousal = a
                self.last_sent_time = time.time()
                # NodeC 인스턴스의 face 상태 업데이트 (이후 텍스트 턴에 융합 사용)
                node_c = get_node_c()
                node_c.last_face_va = np.array([v, a], dtype=np.float32)
                print(f"  -> face_va 누적 저장: V:{v:.2f}, A:{a:.2f} (다음 텍스트 턴에 반영)")
            else:
                print(f"  -> 변화량 미달, 상태 유지")
            return aura_pb2.EmpathyResponse(
                session_id="session_live",
                text="표정 상태 저장됨 (텍스트 대기 중)",
                strategy="face_accumulate"
            )

        # 텍스트가 있는 경우: 전체 파이프라인 가동
        print(f"  -> STT 텍스트 수신, 전체 파이프라인 가동: '{user_text}'")
        self.last_valence = v
        self.last_arousal = a
        self.last_sent_time = time.time()

        fused_emotion = aura_pb2.FusedEmotionState(
            primary_emotion=request.emotion_label,
            confidence=request.confidence,
            valence=v,
            arousal=a,
            description=f"표정 기반 분석: {request.emotion_label}"
        )

        prompt_request = process_and_build_request(
            session_id="session_live",
            user_text=user_text,
            candidates=[request],
            fused_emotion=fused_emotion,
            face_va=[v, a],
            voice_va=None
        )

        response = send_with_safety(prompt_request)
        if response.error_code == 0:
            print(f"  -> Node B 응답 수신 완료!")
        else:
            print(f"  -> Node B 전송 실패: {response.error_message}")
        return response

    def SendVoicePerception(self, request, context):
        """
        음성 인식 결과 수신.
        STT 텍스트를 기반으로 전체 파이프라인을 가동한다.
        음성 톤(V, A)은 voice_va로 전달되어 3-모달 융합에 참여한다.
        """
        v, a = request.valence, request.arousal
        user_text = request.text if request.text else ""

        print(f"\n[Node C Server] 음성 수신: '{user_text}' (V:{v:.2f}, A:{a:.2f})")

        if not user_text:
            print(f"  -> STT 텍스트 없음, 스킵")
            return aura_pb2.EmpathyResponse(
                session_id="session_voice",
                text="음성 상태 저장됨 (텍스트 대기 중)",
                strategy="voice_accumulate"
            )

        fused_emotion = aura_pb2.FusedEmotionState(
            primary_emotion="voice_emotion",
            confidence=request.confidence,
            valence=v,
            arousal=a,
            description=f"음성 톤 분석: {request.emotion_label}"
        )

        print(f"  -> Node C 분석 시작 및 Node B로 전송...")
        prompt_request = process_and_build_request(
            session_id="session_voice",
            user_text=user_text,
            candidates=[request],
            fused_emotion=fused_emotion,
            face_va=None,
            voice_va=[v, a]
        )

        response = send_with_safety(prompt_request)
        if response.error_code == 0:
            print(f"  -> Node B 응답 수신 완료!")
        else:
            print(f"  -> Node B 전송 실패: {response.error_message}")
        return response


def serve():
    port = 5052
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    aura_pb2_grpc.add_AuraPerceptionServicer_to_server(AuraPerceptionServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()

    print("======================================================")
    print(f"[Node C] AuraPerception Server가 {port}번 포트에서 열렸습니다!")
    print("   [트리거 정책] 텍스트(STT)가 있을 때만 Node B(LLM)에 요청합니다.")
    print("   표정/음성 데이터는 상태로 누적되어 텍스트 턴에 맥락으로 활용됩니다.")
    print("======================================================")

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    serve()