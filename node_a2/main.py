import threading
from config import Config
from audio_processor import record_vad, run_stt, speak_text
from emotion_analyzer import analyze_voice_emotion
from network_manager import NetworkManager, start_grpc_server

def main():
    # 1. 네트워크 매니저 초기화 (TTS 콜백 연결)
    net_manager = NetworkManager(tts_callback=speak_text)
    
    # 2. gRPC 서버(답변 수신용) 백그라운드 실행
    server_thread = threading.Thread(target=start_grpc_server, args=(net_manager,), daemon=True)
    server_thread.start()

    print("✨ 모든 모듈 로드 완료. 시스템 시작.")

    while True:
        try:
            # 3. 음성 감지 및 녹음
            if record_vad():
                # 4. 텍스트 변환 (STT)
                text = run_stt()
                if not text or len(text.strip()) < 2: continue
                
                # 5. 감정 분석
                v, a, conf = analyze_voice_emotion(Config.RECORD_FILE)
                print(f"📝 인식: {text} | 📊 VA: {v}, {a}")

                # 6. 표정 노드로 데이터 전송
                net_manager.send_to_face(text, v, a, conf)
                print("✅ 전송 완료")

        except KeyboardInterrupt:
            print("\n👋 종료합니다.")
            break
        except Exception as e:
            print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()