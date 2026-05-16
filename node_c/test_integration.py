import grpc
import sys
import os
import time

# gRPC stub을 사용하기 위해 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
try:
    import aura_pb2
    import aura_pb2_grpc
except ImportError:
    # 만약 위에서 실패하면 현재 디렉토리도 확인
    sys.path.append(os.path.dirname(__file__))
    import aura_pb2
    import aura_pb2_grpc

def test_pipeline():
    # Node C 서버 주소 (현재 main.py가 실행 중인 5052 포트)
    NODE_C_ADDR = 'localhost:5052'
    
    print(f"\n{'='*60}")
    print(f"  Node C -> Node B 통합 연결 테스트")
    print(f"{'='*60}")
    
    channel = grpc.insecure_channel(NODE_C_ADDR)
    stub = aura_pb2_grpc.AuraPerceptionStub(channel)
    
    # 1. 표정 데이터 전송 테스트 (Face)
    print("\n[테스트 1] 표정 데이터 전송 (Face Only)")
    print(" -> Node C가 이 데이터를 받아서 분석 스킵 후 Node B로 바로 쏴야 합니다.")
    
    face_req = aura_pb2.EmotionCandidate(
        source="test_bot",
        emotion_label="neutral",
        valence=-0.1,
        arousal=0.2,
        confidence=0.88
    )
    
    try:
        start_t = time.time()
        response = stub.SendFacePerception(face_req, timeout=45)
        end_t = time.time()
        
        print(f"\n 결과: 성공 (소요시간: {end_t - start_t:.2f}초)")
        print(f"   - Node B 답변: {response.text}")
        print(f"   - 적용 전략: {response.strategy}")
        print(f"   - 세션 ID: {response.session_id}")
    except grpc.RpcError as e:
        print(f"\n 실패: {e.code()}")
        print(f"   - 상세 내용: {e.details()}")
        print("\n[체크리스트]")
        print("1. main.py (Node C)가 실행 중인가요?")
        print("2. bridge_sender_integrated.py의 NODE_B_ADDRESS가 실제 Node B IP인가요?")
        print("3. Node B 서버가 5051 포트에서 실행 중인가요?")

if __name__ == "__main__":
    test_pipeline()
