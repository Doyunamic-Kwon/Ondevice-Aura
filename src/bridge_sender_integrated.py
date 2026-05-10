import time
import uuid
import grpc
import numpy as np
import sys
import os

# 현재 경로 추가 (node_c_prototype 참조용)
sys.path.append(os.path.dirname(__file__))
from node_c_prototype import NodeC

import aura_pb2
import aura_pb2_grpc

# =====================================================
# 설정
# =====================================================
NODE_B_ADDRESS = "192.168.0.37:5051"
GRPC_TIMEOUT = 35
MAX_RETRY = 2

def log_event(node, request_id, message):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{node}] [{request_id}] {message}")

# =====================================================
# 1. 프롬프트 생성 함수 (우리의 KG, Alignment 추가됨)
# =====================================================
def build_prompt(user_text, fused_emotion, candidates, kg_context, anomaly_note):
    candidate_lines = "\n".join(
        [
            f"- {c.source}: {c.emotion_label}, valence={c.valence:.2f}, arousal={c.arousal:.2f}, confidence={c.confidence:.2f}"
            for c in candidates
        ]
    )

    return f"""
[System Role]
You are Aura, an empathetic AI companion.

[Emotion Candidates]
{candidate_lines}

[Fused Emotion State]
- State: {fused_emotion.emotion_label}
- Description: {fused_emotion.description}
- Valence: {fused_emotion.valence:.2f}
- Arousal: {fused_emotion.arousal:.2f}

[Knowledge Graph Context]
{kg_context if kg_context else "관련 배경지식 없음."}

[Sentiment Alignment Analysis]
{anomaly_note if anomaly_note else "사용자의 언행과 표정이 일치합니다."}

[Behavior Rules]
- Always speak in Korean
- Start with empathy
- Never judge the user
- Comfort first if sad/tired
- 분석된 [Knowledge Graph Context]와 [Sentiment Alignment Analysis]의 숨겨진 의미를 자연스럽게 반영하여 위로를 건네세요.

[User]
{user_text}

[Aura]
"""

# =====================================================
# 2. 통합 분석 및 gRPC 요청 조립 (Node C -> Node B)
# =====================================================
# 성능 최적화: 모델과 DB 연결을 매번 하지 않도록 전역 객체로 관리합니다.
import threading
_node_c_instance = None
_init_lock = threading.Lock()

def get_node_c():
    global _node_c_instance
    with _init_lock:
        if _node_c_instance is None:
            log_event("Node C", "INIT", "NodeC 엔진 초기화 중 (모델 로드 포함)...")
            _node_c_instance = NodeC()
    return _node_c_instance

def process_and_build_request(session_id, user_text, nonverbal_vector, candidates, fused_emotion):
    request_id = f"turn_{uuid.uuid4().hex[:8]}"
    
    # [성능 최적화] 텍스트가 없는 경우 (표정 데이터 전송 등) 무거운 분석 엔진 초기화를 건너뜁니다.
    if not user_text or user_text.strip() == "":
        log_event("Node C", request_id, "텍스트 없음: 분석 스킵 및 즉시 조립")
        node_c_result = {
            "kg_context": [],
            "alignment": {"score": 1.0, "is_consistent": True},
        }
    else:
        node_c = get_node_c()
        log_event("Node C", request_id, f"분석 시작 (텍스트: {user_text[:15]}...)")
        node_c_result = node_c.process_data(user_text, nonverbal_vector)
    
    kg_context_str = "\n".join(node_c_result["kg_context"])
    alignment = node_c_result["alignment"]

    # 정렬도 검사(Alignment Check) 결과에 따른 알림 생성
    anomaly_note = ""
    if not alignment["is_consistent"]:
         anomaly_note = f"주의: 사용자가 감정을 숨기거나 반어법을 사용 중일 수 있습니다. (불일치도 점수: {alignment['score']})"
         # Protobuf 객체의 description에도 안전하게 추가 반영
         fused_emotion.description += f" ({anomaly_note})"

    # --- [최종 프롬프트 조립] ---
    final_prompt = build_prompt(
        user_text=user_text,
        fused_emotion=fused_emotion,
        candidates=candidates,
        kg_context=kg_context_str,
        anomaly_note=anomaly_note
    )

    # --- [ContextualPrompt Protobuf 객체 생성] ---
    request = aura_pb2.ContextualPrompt(
        session_id=session_id,
        request_id=request_id,
        final_prompt=final_prompt,
        valence=fused_emotion.valence,
        arousal=fused_emotion.arousal,
        timestamp=int(time.time()),
        candidates=candidates,
        fused_emotion=fused_emotion,
        user_text=user_text
    )

    return request

# =====================================================
# 3. 안전 전송 함수 (팀원 원본 코드 유지)
# =====================================================
def send_with_safety(request):
    request_id = request.request_id

    for attempt in range(1, MAX_RETRY + 2):
        try:
            log_event("Node C", request_id, f"Node B 요청 시도 {attempt}/{MAX_RETRY + 1}")
            with grpc.insecure_channel(NODE_B_ADDRESS) as channel:
                stub = aura_pb2_grpc.AuraServiceStub(channel)
                response = stub.GenerateEmpathy(request, timeout=GRPC_TIMEOUT)

            if response.request_id != request.request_id:
                log_event("Node C", request_id, "request_id mismatch 발생")
                return aura_pb2.EmpathyResponse(
                    session_id=request.session_id, request_id=request.request_id,
                    text="응답 매칭 오류 발생", response_time=0.0, strategy="error",
                    error_code=aura_pb2.REQUEST_ID_MISMATCH, error_message="request_id mismatch"
                )

            log_event("Node C", request_id, "request_id 매칭 성공")
            return response

        except grpc.RpcError as e:
            log_event("Node C", request_id, f"gRPC 오류={e}")
            if attempt <= MAX_RETRY:
                log_event("Node C", request_id, "재시도 진행")
                time.sleep(1)
                continue

            return aura_pb2.EmpathyResponse(
                session_id=request.session_id, request_id=request.request_id,
                text="Node B 연결 실패", response_time=0.0, strategy="error",
                error_code=aura_pb2.GRPC_TIMEOUT, error_message=str(e)
            )
