import grpc
from concurrent import futures
import sys
import os
import time
import math

sys.path.append(os.path.dirname(__file__))
import aura_pb2
import aura_pb2_grpc
from bridge_sender_integrated import process_and_build_request, send_with_safety

class AuraPerceptionServicer(aura_pb2_grpc.AuraPerceptionServicer):
    def SendFacePerception(self, request, context):
        print(f"\n[Node C Server] 수신된 표정 데이터: {request.emotion_label} (V:{request.valence:.2f}, A:{request.arousal:.2f})")
        
        # 1. 현재 Node A에서 텍스트 데이터가 안 넘어오므로 빈 문자열 처리
        # (빈 문자열이 들어가면 Node C 로직은 안전하게 지식 검색을 스킵합니다)
        user_text = "" 
        
        # 2. Fused Emotion 상태 생성
        fused_emotion = aura_pb2.FusedEmotionState(
            primary_emotion=request.emotion_label,
            confidence=request.confidence,
            valence=request.valence,
            arousal=request.arousal
        )
        
        # 3. Node C 파이프라인 가동 및 Node B로 프롬프트 전송
        print("  -> Node C 분석 시작 및 Node B로 프롬프트 전송...")
        prompt_request = process_and_build_request(
            session_id="session_live",
            user_text=user_text,
            nonverbal_vector=[request.valence, request.arousal],
            candidates=[request],
            fused_emotion=fused_emotion
        )
        
        response = send_with_safety(prompt_request)
        print(f"  -> Node B 응답 수신 완료!")
        return response

def serve():
    # Node C 서버는 50052 포트를 사용합니다. (Node B는 보통 50051)
    port = 50052
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    aura_pb2_grpc.add_AuraPerceptionServicer_to_server(AuraPerceptionServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    print("======================================================")
    print(f"🚀 [Node C] AuraPerception Server가 {port}번 포트에서 열렸습니다!")
    print("   Node A 코드에서 target_address를 'localhost:50052'로 변경해주세요.")
    print("   Node C 서버는 표정 변화량이 클 때만 Node B를 호출합니다.")
    print("======================================================")
    
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
