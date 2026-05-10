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
    
    # gRPC 서버 실행 (이 함수가 실행되면 서버가 종료될 때까지 대기합니다)
    try:
        serve()
    except Exception as e:
        print(f"❌ 서버 실행 중 오류 발생: {e}")
