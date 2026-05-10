import json
import requests
import sys
import os

# 경로 추가 (src 폴더를 참조하기 위함)
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from node_c_server import serve  # gRPC 서버 함수 불러오기

# [설정]
MODEL_NAME = "aura-gemma:latest"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PW = "password123"

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🌟 아우라(Aura) Node C 시스템 가동")
    print("="*50)
    
    # [성능 최적화] 분석 엔진 미리 로드 (백그라운드 예열)
    # 서버 가동과 동시에 모델을 로드하여 첫 텍스트 수신 시 딜레이를 없앱니다.
    import threading
    from bridge_sender_integrated import get_node_c
    threading.Thread(target=get_node_c, daemon=True).start()

    # gRPC 서버 실행 (이 함수가 실행되면 서버가 종료될 때까지 대기합니다)
    try:
        serve()
    except Exception as e:
        print(f"❌ 서버 실행 중 오류 발생: {e}")
