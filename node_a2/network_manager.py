import grpc
import threading
from concurrent import futures  # 💡 추가됨
import aura_pb2
import aura_pb2_grpc
from config import Config

class NetworkManager(aura_pb2_grpc.AuraTTSServicer):
    def __init__(self, tts_callback):
        self.tts_callback = tts_callback
        self.channel = grpc.insecure_channel(Config.FACE_NODE_TARGET)
        self.perception_stub = aura_pb2_grpc.AuraPerceptionStub(self.channel)

    def SendDialogue(self, request, context):
        print(f"\n📩 [수신] Node B 답변: {request.text}")
        # 데몬 스레드로 실행하여 TTS 도중 메인 프로세스 종료 방해 방지
        t = threading.Thread(target=self.tts_callback, args=(request.text,))
        t.daemon = True
        t.start()
        
        # EmpathyResponse 필드에 맞춰 반환 (session_id 등 추가 필요시 작성)
        return aura_pb2.EmpathyResponse(
            error_code=aura_pb2.ErrorCode.NONE
        )

    def send_to_face(self, text, v, a, conf):
        candidate = aura_pb2.EmotionCandidate(
            source="voice", valence=v, arousal=a, confidence=conf, text=text
        )
        return self.perception_stub.SendVoicePerception(candidate)

def start_grpc_server(manager):
    try:
        # 💡 concurrent.futures.ThreadPoolExecutor 사용
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
        aura_pb2_grpc.add_AuraTTSServicer_to_server(manager, server)
        
        port = Config.MY_TTS_SERVER_PORT
        server.add_insecure_port(f"[::]:{port}")
        server.start()
        
        print(f"📡 TTS 리스너 가동 성공 (Port: {port})")
        server.wait_for_termination()
    except Exception as e:
        print(f"❌ gRPC 서버 시작 실패: {e}")