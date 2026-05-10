import json
import requests
import numpy as np
import sys
import os

# Node C 프로토타입 불러오기
sys.path.append(os.path.dirname(__file__))
try:
    from node_c_prototype import NodeC
except ImportError:
    print("Error: node_c_prototype.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

# [설정]
MODEL_NAME = "aura-gemma:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"

class FullEmpathySystem:
    def __init__(self):
        print("\n[시스템] Node C (Knowledge Bridge) 초기화 중...")
        # 실제 Neo4j 연결 시도, 실패 시 Dummy 모드
        self.node_c = NodeC()
        print("[시스템] 모든 노드 준비 완료.\n")

    def run_inference(self, user_text, face_v, face_a):
        # 1. Node C 처리
        face_vector = np.array([face_v, face_a], dtype=np.float32)
        
        node_c_result = self.node_c.process_data(user_text, face_vector)
        
        kg_context = "\n".join(node_c_result["kg_context"])
        alignment = node_c_result["alignment"]
        
        # 2. Node B (Gemma)용 프롬프트 조립
        anomaly_note = ""
        if not alignment["is_consistent"]:
            # 불일치 발생 시(예: -0.9 등) 공감 포인트 주입
            anomaly_note = f"사용자가 현재 감정을 숨기고 있을 가능성이 큽니다 (감정 불일치 점수: {alignment['score']}). 겉으로는 괜찮아 보여도 실제로는 힘든 상태일 수 있습니다."

        prompt = f"""
        당신은 사용자의 언어와 비언어(표정) 데이터를 통합 분석하는 초공감 AI 상담사 '아우라'입니다.
        
        [시스템 분석 정보]:
        - 지식 기반 맥락: {kg_context if kg_context else "일반적인 상황"}
        - 정서 정렬도 분석: {anomaly_note if anomaly_note else "사용자의 언행과 표정이 일치합니다."}
        
        [지침]:
        - 반드시 한국어로 답변하세요.
        - 분석된 '정서 정렬도'와 '지식'을 바탕으로 사용자의 숨은 의도까지 파악하여 공감해주세요.
        - 답변은 짧고 따뜻한 상담사 말투로 작성하세요.
        
        [사용자 말]: {user_text}
        
        [아우라의 공감 답변]:"""

        # 3. Ollama 호출
        try:
            res = requests.post(OLLAMA_URL, json={
                "model": MODEL_NAME, "prompt": prompt, "stream": False,
                "options": {"num_gpu": 1}
            }, timeout=60)
            return res.json().get("response", "Gemma 응답 생성 실패")
        except Exception as e:
            return f"Ollama 연결 에러: {e}"

if __name__ == "__main__":
    system = FullEmpathySystem()
    
    print("="*60)
    print("🌟 아우라(Aura) 실시간 통합 테스트 (Node C + Gemma)")
    print(" - 종료하려면 'exit' 또는 'quit'를 입력하세요.")
    print(" - 수치는 -1.0에서 1.0 사이로 입력하세요.")
    print("="*60)
    
    while True:
        try:
            print("\n" + "-"*50)
            text = input("👤 사용자 입력: ")
            if not text: continue
            if text.lower() in ['exit', 'quit']: break
            
            print("🎭 가상 표정 데이터 입력 (-1.0 ~ 1.0)")
            v_in = input("   - Valence (긍정 > 0 / 부정 < 0): ")
            a_in = input("   - Arousal (흥분 > 0 / 차분 < 0): ")
            
            v = float(v_in) if v_in else 0.0
            a = float(a_in) if a_in else 0.0
            
            print("\n[분석 중...]")
            response = system.run_inference(text, v, a)
            
            print(f"\n✨ 아우라(Aura): {response}")
            
        except KeyboardInterrupt:
            break
        except ValueError:
            print("❌ 숫자를 입력해 주세요.")
        except Exception as e:
            print(f"❌ 오류 발생: {e}")

    print("\n테스트를 종료합니다.")
