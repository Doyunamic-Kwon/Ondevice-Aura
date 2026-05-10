import grpc
from concurrent import futures
import sys
import os
import time
import math

sys.path.append(os.path.dirname(__file__))
import aura_pb2
import aura_pb2_grpc
from bridge_sender_integrated import process_and_build_request, send_with_safety, NODE_B_ADDRESS

class AuraPerceptionServicer(aura_pb2_grpc.AuraPerceptionServicer):
    def __init__(self):
        # 마지막으로 Node B에 전송한 상태 저장 (필터링용)
        self.last_valence = 0.0
        self.last_arousal = 0.0
        self.last_sent_time = 0.0
        self.is_first_data = True  # 최초 전송 여부 확인용
        self.threshold = 0.08      # 변화량 임계치 (민감도 상향)
        self.min_interval = 0.5    # 최소 전송 간격 (0.5초)
        self.max_interval = 5.0    # 강제 전송 간격 (5초 동안 변화 없어도 현재 상태 유지 위해 전송)
        
        # 백그라운드 처리를 위한 스레드 풀 생성
        self.executor = futures.ThreadPoolExecutor(max_workers=5)
        self.bg_active_count = 0
        import threading
        self.bg_lock = threading.Lock()

    def _bg_send_to_node_b(self, prompt_request):
        """백그라운드에서 Node B로 데이터를 전송하는 헬퍼 함수"""
        with self.bg_lock:
            self.bg_active_count += 1
            
        try:
            print(f"  [Async] Node B({NODE_B_ADDRESS})로 데이터 전송 중... (대기 중인 전송: {self.bg_active_count}개)")
            send_with_safety(prompt_request)
            print(f"  [Async] Node B 전송 완료!")
        except Exception as e:
            print(f"  [Async] 전송 중 오류 발생: {e}")
        finally:
            with self.bg_lock:
                self.bg_active_count -= 1

    def is_significant_change(self, v, a):
        now = time.time()
        
        # 1. 최초 데이터인 경우 무조건 전송
        if self.is_first_data:
            self.is_first_data = False
            return True
            
        # 2. 강제 전송 간격(Heartbeat) 확인: 5초 이상 지났으면 변화 없어도 전송
        if now - self.last_sent_time > self.max_interval:
            print("\n[Heartbeat] 상태 유지 전송", end=" ")
            return True

        # 3. 최소 전송 간격 확인 (너무 빈번한 전송 방지)
        if now - self.last_sent_time < self.min_interval:
            return False
            
        # 4. 수치 변화량 확인
        diff = math.sqrt((v - self.last_valence)**2 + (a - self.last_arousal)**2)
        if diff < self.threshold:
            return False
            
        return True

    def SendFacePerception(self, request, context):
        # 큐 보호 로직: Node B가 바쁘면(진행 중인 작업 2개 이상) 표정 업데이트 스킵하여 딜레이 누적 방지
        with self.bg_lock:
            if self.bg_active_count >= 2:
                print("~", end="", flush=True) # 바빠서 스킵함을 물결표로 표시
                return aura_pb2.EmpathyResponse(
                    session_id="session_live",
                    text="Node B 바쁨 (스킵)",
                    strategy="skip_busy"
                )

        # 변화량이 적으면 Node B 호출 없이 즉시 응답 (서버 부하 감소)
        if not self.is_significant_change(request.valence, request.arousal):
            print(".", end="", flush=True) # 변화가 적을 때는 점 하나만 찍어서 작동 중임을 표시
            return aura_pb2.EmpathyResponse(
                session_id="session_live",
                text="상태 유지 (변화량 적음)",
                strategy="skip"
            )

        print(f"\n[Node C Server] 수신된 표정 데이터: {request.emotion_label} (V:{request.valence:.2f}, A:{request.arousal:.2f})")
        
        # 상태 업데이트
        self.last_valence = request.valence
        self.last_arousal = request.arousal
        self.last_sent_time = time.time()
        
        user_text = "" 
        fused_emotion = aura_pb2.FusedEmotionState(
            primary_emotion=request.emotion_label,
            confidence=request.confidence,
            valence=request.valence,
            arousal=request.arousal,
            description=f"표정 기반 분석: {request.emotion_label}"
        )
        
        # 3. Node C 파이프라인 가동 (분석 후 조립)
        print("  -> Node C 분석 파이프라인 가동 (지식 검색 및 감정 분석)...")
        prompt_request = process_and_build_request(
            session_id="session_live",
            user_text=user_text,
            nonverbal_vector=[request.valence, request.arousal],
            candidates=[request],
            fused_emotion=fused_emotion
        )
        
        # Node B로 보내는 작업은 백그라운드에서 실행 (Node A를 기다리게 하지 않음)
        self.executor.submit(self._bg_send_to_node_b, prompt_request)
        
        return aura_pb2.EmpathyResponse(
            session_id="session_live",
            text="분석 및 전송 시작 (비동기)",
            strategy="async_queued"
        )

    def SendVoicePerception(self, request, context):
        print(f"\n[Node C Server] 수신된 음성 데이터: {request.text} (V:{request.valence:.2f}, A:{request.arousal:.2f})")
        
        # 1. 음성에서 인식된 텍스트 사용
        user_text = request.text
        
        # 2. Fused Emotion 상태 생성
        fused_emotion = aura_pb2.FusedEmotionState(
            primary_emotion="voice_emotion",
            confidence=request.confidence,
            valence=request.valence,
            arousal=request.arousal,
            description=f"음성 톤 분석: {request.emotion_label}"
        )
        
        # 3. Node C 파이프라인 가동 (수신된 텍스트를 바탕으로 지식 검색 및 분석 수행)
        print(f"  -> Node C 분석 파이프라인 가동 (텍스트: '{user_text}')...")
        prompt_request = process_and_build_request(
            session_id="session_voice",
            user_text=user_text,
            nonverbal_vector=[request.valence, request.arousal],
            candidates=[request],
            fused_emotion=fused_emotion
        )
        
        # 백그라운드 전송 실행
        self.executor.submit(self._bg_send_to_node_b, prompt_request)
        
        return aura_pb2.EmpathyResponse(
            session_id="session_voice",
            text="분석 및 전송 시작 (비동기)",
            strategy="async_queued"
        )

import socket

def get_my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def serve():
    # Node C 서버 포트 설정 (사용자 요청에 따라 5052 사용)
    port = 5052
    my_ip = get_my_ip()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    aura_pb2_grpc.add_AuraPerceptionServicer_to_server(AuraPerceptionServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    print("======================================================")
    print(f" [Node C] AuraPerception Server가 가동되었습니다!")
    print(f"   - 접속 주소: {my_ip}:{port}")
    print(f"   - Node A 담당자에게 위 주소를 전달해주세요.")
    print("======================================================")
    
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
