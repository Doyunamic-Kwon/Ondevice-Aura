"""
Aura-Sync: Node B (Brain) — Jetson Orin Nano 로컬 테스트
=========================================================
Node C 팀원 없이 혼자 테스트할 수 있는 Mock 입력 포함

역할:
  - Node C에서 프롬프트(gRPC)를 수신
  - 컨텍스트 윈도우로 대화 히스토리 관리
  - Ollama(Gemma)로 공감 발화 생성
  - Fail-safe: 위기 키워드 감지 시 LLM 차단

실행 방법:
  1. 의존성 설치: pip3 install requests --break-system-packages
  2. 실행 (Mock): python3 test_node_b.py
  3. 특정 케이스: python3 test_node_b.py --case 1
  4. 실제 Ollama: python3 test_node_b.py --real-llm
"""

import time
import argparse
from dataclasses import dataclass, field
from typing import List
from collections import deque


# ──────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────

@dataclass
class NodeCPacket:
    prompt     : str
    valence    : float
    arousal    : float
    stt_text   : str
    kg_context : List[str] = field(default_factory=list)
    alignment  : dict      = field(default_factory=dict)
    session_id : str       = "test_user"
    timestamp  : int       = 0


# ──────────────────────────────────────────
# Mock 입력 데이터
# ──────────────────────────────────────────

TEST_CASES = [
    {
        "name"  : "이별 — 슬픔/무기력",
        "packet": NodeCPacket(
            stt_text   = "이별했어요, 너무 힘들어요",
            valence    = -0.9,
            arousal    = -0.4,
            kg_context = ["외로움", "그리움", "무기력", "일상 무너짐"],
            alignment  = {"score": -0.5, "is_consistent": True, "detected_anomaly": ""},
            prompt     = """[System Role]
You are Aura, an empathetic AI companion.
Always speak in Korean. 반드시 한국어로만 응답. 영어 사용 금지.
[Fused Emotion State]
- Valence: -0.90, Arousal: -0.40 / 감지된 감정: 우울/무기력
[Knowledge Graph Context]
- 외로움, 그리움, 무기력, 일상 무너짐
[Behavior Rules]
- 반드시 한국어로만 응답. 영어 사용 절대 금지.
- 이모지 사용 금지.
- 상대방에게 할 말만 출력. 설명, 분석, 태그 출력 금지.
- 공감 우선, 2문장 이내, 조언 금지.
[User]
이별했어요, 너무 힘들어요
[Aura]""",
        ),
    },
    {
        "name"  : "직장 스트레스 — 분노/좌절",
        "packet": NodeCPacket(
            stt_text   = "오늘 프로젝트 에러 때문에 미치겠어요",
            valence    = -0.7,
            arousal    =  0.6,
            kg_context = ["야근", "수면 부족", "스트레스", "짜증"],
            alignment  = {"score": -0.3, "is_consistent": True, "detected_anomaly": ""},
            prompt     = """[System Role]
You are Aura, an empathetic AI companion.
Always speak in Korean. 반드시 한국어로만 응답. 영어 사용 금지.
[Fused Emotion State]
- Valence: -0.70, Arousal: 0.60 / 감지된 감정: 분노/좌절
[Knowledge Graph Context]
- 야근, 수면 부족, 스트레스, 짜증
[Behavior Rules]
- 반드시 한국어로만 응답. 영어 사용 절대 금지.
- 이모지 사용 금지.
- 상대방에게 할 말만 출력. 설명, 분석, 태그 출력 금지.
- 공감 우선, 2문장 이내, 조언 금지.
[User]
오늘 프로젝트 에러 때문에 미치겠어요
[Aura]""",
        ),
    },
    {
        "name"  : "실직 — 매우 부정/무기력",
        "packet": NodeCPacket(
            stt_text   = "오늘 회사에서 잘렸어요, 가족한테 말하기도 무서워요",
            valence    = -0.95,
            arousal    = -0.6,
            kg_context = ["불안", "자존감 하락", "경제적 압박", "고립감"],
            alignment  = {"score": -0.6, "is_consistent": True, "detected_anomaly": ""},
            prompt     = """[System Role]
You are Aura, an empathetic AI companion.
Always speak in Korean. 반드시 한국어로만 응답. 영어 사용 금지.
[Fused Emotion State]
- Valence: -0.95, Arousal: -0.60 / 감지된 감정: 우울/무기력
[Knowledge Graph Context]
- 불안, 자존감 하락, 경제적 압박, 고립감
[Behavior Rules]
- 반드시 한국어로만 응답. 영어 사용 절대 금지.
- 이모지 사용 금지.
- 상대방에게 할 말만 출력. 설명, 분석, 태그 출력 금지.
- 공감 우선, 2문장 이내, 조언 금지.
[User]
오늘 회사에서 잘렸어요, 가족한테 말하기도 무서워요
[Aura]""",
        ),
    },
    {
        "name"  : "위기 감지 — Fail-safe 테스트",
        "packet": NodeCPacket(
            stt_text   = "너무 힘들어서 다 포기하고 싶어요, 사라지고 싶어요",
            valence    = -0.99,
            arousal    = -0.8,
            prompt     = "[User]\n너무 힘들어서 사라지고 싶어요\n[Aura]",
        ),
    },
    {
        "name"  : "중립 — 일반 대화",
        "packet": NodeCPacket(
            stt_text   = "오늘 날씨가 좀 흐리네요",
            valence    =  0.1,
            arousal    = -0.1,
            prompt     = """[System Role]
You are Aura. Always speak in Korean. 반드시 한국어로만 응답.
[User]
오늘 날씨가 좀 흐리네요
[Aura]""",
        ),
    },
]


# ──────────────────────────────────────────
# Fail-safe: Priority 0
# ──────────────────────────────────────────

CRISIS_KEYWORDS = ["죽", "자살", "사라지고 싶", "없어지고 싶",
                   "포기하고 싶", "끝내고 싶", "못 살겠", "살기 싫"]

CRISIS_RESPONSE = """지금 많이 힘드시군요. 혼자 감당하기 너무 힘든 감정이에요.

지금 바로 전문가와 이야기하실 수 있어요:
  📞 자살예방상담전화: 1393 (24시간)
  📞 정신건강위기상담전화: 1577-0199 (24시간)

지금 안전하신가요?"""


def check_crisis(stt_text: str) -> bool:
    return any(kw in stt_text for kw in CRISIS_KEYWORDS)


# ──────────────────────────────────────────
# KG Context 정제
# ──────────────────────────────────────────

_REL_KO = {
    "HinderedBy": "방해 요소",
    "xNeed"     : "사전에 필요한 것",
    "xWant"     : "원하는 것",
    "xEffect"   : "결과",
    "xReact"    : "감정 반응",
    "Causes"    : "원인",
}

def clean_kg_context(kg_context: List[str]) -> List[str]:
    cleaned, seen = [], set()
    for raw in kg_context:
        if not raw:
            continue
        rel_type = next((r for r in _REL_KO if r in raw), "")
        try:
            tail = raw.split("(은)는 ", 1)[1].split("(와)과")[0].strip()
            tail = tail.replace("personx", "").replace("person x", "").strip(" '\"")
        except Exception:
            tail = ""
        if not tail or len(tail) > 80:
            continue
        result = f"{_REL_KO.get(rel_type, rel_type)}: {tail}"
        if result not in seen:
            seen.add(result)
            cleaned.append(result)
    return cleaned if cleaned else kg_context


# ──────────────────────────────────────────
# 히스토리 매니저
# ──────────────────────────────────────────

class HistoryManager:
    """세션별 대화 히스토리 관리 — 최근 MAX_TURNS 턴만 유지"""
    MAX_TURNS = 5

    def __init__(self):
        self.histories   : dict = {}
        self.last_emotion: dict = {}  # session_id → (valence, arousal)

    def get(self, session_id: str) -> list:
        if session_id not in self.histories:
            self.histories[session_id] = deque(maxlen=self.MAX_TURNS * 2)
        return list(self.histories[session_id])

    def add(self, session_id: str, role: str, content: str):
        if session_id not in self.histories:
            self.histories[session_id] = deque(maxlen=self.MAX_TURNS * 2)
        self.histories[session_id].append({"role": role, "content": content})

    def get_emotion_delta(self, session_id: str, valence: float, arousal: float) -> dict:
        """이전 V/A 대비 변화량 계산. 처음 호출 시 delta=0 반환"""
        if session_id not in self.last_emotion:
            self.last_emotion[session_id] = (valence, arousal)
            return {"delta_v": 0.0, "delta_a": 0.0, "delta": 0.0}
        prev_v, prev_a = self.last_emotion[session_id]
        delta_v = valence - prev_v
        delta_a = arousal - prev_a
        delta   = (abs(delta_v) + abs(delta_a)) / 2
        self.last_emotion[session_id] = (valence, arousal)
        return {"delta_v": delta_v, "delta_a": delta_a, "delta": delta}

    def clear(self, session_id: str):
        if session_id in self.histories:
            del self.histories[session_id]
        if session_id in self.last_emotion:
            del self.last_emotion[session_id]


# ──────────────────────────────────────────
# LLM 인터페이스
# ──────────────────────────────────────────

class MockLLM:
    MOCK_RESPONSES = {
        "우울"  : "많이 지치고 슬프셨겠어요. 충분히 아파도 괜찮아요.",
        "분노"  : "정말 답답하고 화가 나셨겠어요. 지금 많이 지쳐 계시겠네요.",
        "불안"  : "많이 걱정되고 불안하시겠어요. 지금 느끼는 감정이 자연스러운 거예요.",
        "중립"  : "오늘 날씨가 흐리군요. 그런 날엔 마음도 무거워지기도 하죠.",
        "default": "지금 많이 힘드시겠어요. 그 감정, 충분히 느껴도 괜찮아요.",
    }

    def generate(self, messages: list, valence: float) -> tuple:
        t = time.time()
        time.sleep(0.05)
        if valence < -0.8:
            r = self.MOCK_RESPONSES["우울"]
        elif valence < -0.5:
            r = self.MOCK_RESPONSES["분노"]
        elif valence < -0.2:
            r = self.MOCK_RESPONSES["불안"]
        elif abs(valence) <= 0.2:
            r = self.MOCK_RESPONSES["중립"]
        else:
            r = self.MOCK_RESPONSES["default"]
        return r, (time.time() - t) * 1000


class OllamaLLM:
    def __init__(self, model: str = "gemma3:1b", host: str = "http://localhost:11434"):
        self.model = model
        self.host  = host

    def generate(self, messages: list, valence: float) -> tuple:
        try:
            import requests
            t = time.time()
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model"   : self.model,
                    "messages": messages,
                    "stream"  : False,
                    "options" : {
                        "temperature"   : 0.7,
                        "num_predict"   : 100,
                        "repeat_penalty": 1.3,
                    }
                },
                timeout=120,
            )
            data    = response.json()
            text    = data.get("message", {}).get("content", "").strip()
            latency = (time.time() - t) * 1000
            return text, latency
        except Exception as e:
            return f"[LLM 오류: {e}]", 0.0


# ──────────────────────────────────────────
# Node B Core
# ──────────────────────────────────────────

class NodeBCore:
    def __init__(self, use_real_llm: bool = False):
        self.history = HistoryManager()
        self.llm     = OllamaLLM() if use_real_llm else MockLLM()
        print(f"  LLM 모드: {'Ollama (Gemma)' if use_real_llm else 'Mock'}")

    def process(self, packet: NodeCPacket) -> dict:
        t_start = time.time()

        # Step 1: Fail-safe
        if check_crisis(packet.stt_text):
            latency = (time.time() - t_start) * 1000
            return {"response": CRISIS_RESPONSE, "is_crisis": True,
                    "latency_ms": latency, "llm_ms": 0.0}

        # Step 2: KG 정제
        cleaned_kg = clean_kg_context(packet.kg_context)

        # Step 3: 히스토리 구성 + 표정 변화량 계산
        session_id    = packet.session_id
        history       = self.history.get(session_id)
        emotion_delta = self.history.get_emotion_delta(
            session_id, packet.valence, packet.arousal
        )

        # 표정 변화량 블록 생성
        delta = emotion_delta["delta"]
        if delta >= 0.4:
            direction   = "악화" if emotion_delta["delta_v"] < 0 else "호전"
            delta_block = f"\n[표정 변화] 급격한 감정 {direction} 감지 (변화량={delta:.2f}) — 더 깊은 공감 필요"
        elif delta >= 0.2:
            delta_block = f"\n[표정 변화] 감정 변화 감지 (변화량={delta:.2f})"
        else:
            delta_block = ""

        # Node B 규칙 주입 — Node C 프롬프트 뒤에 덧붙임
        RULES = (
            "\n[Node B Rules - 반드시 준수]\n"
            "- 반드시 한국어로만 응답. 영어 사용 절대 금지.\n"
            "- 이모지 사용 금지.\n"
            "- 상대방에게 할 말만 출력. 설명, 분석, 태그 출력 금지.\n"
            "- 2문장 이내로 간결하게. 조언 금지."
        )
        prompt_with_rules = packet.prompt + delta_block + RULES
        messages = [{"role": "user", "content": prompt_with_rules}]
        if history:
            messages = history + messages

        # Step 4: LLM 추론
        response, llm_ms = self.llm.generate(messages, packet.valence)

        # Step 5: 히스토리 저장
        self.history.add(session_id, "user",      packet.stt_text or packet.prompt)
        self.history.add(session_id, "assistant", response)

        latency = (time.time() - t_start) * 1000
        return {
            "response"    : response,
            "is_crisis"   : False,
            "history_len" : len(self.history.get(session_id)),
            "emotion_delta": emotion_delta,
            "cleaned_kg"  : cleaned_kg,
            "latency_ms"  : latency,
            "llm_ms"      : llm_ms,
        }


# ──────────────────────────────────────────
# 테스트 실행
# ──────────────────────────────────────────

def run_test(case_idx: int, node_b: NodeBCore):
    case   = TEST_CASES[case_idx]
    packet = case["packet"]

    print(f"\n{'='*60}")
    print(f"테스트 {case_idx + 1}: {case['name']}")
    print(f"{'='*60}")
    print(f"  STT    : {packet.stt_text}")
    print(f"  V      : {packet.valence}  A: {packet.arousal}")
    print(f"  KG     : {packet.kg_context}")

    result = node_b.process(packet)

    print(f"\n[결과]")
    if result["is_crisis"]:
        print(f"  ⚠️  위기 감지 — LLM 차단됨")
    else:
        print(f"  히스토리 : {result.get('history_len', 0)}턴 누적")
        delta = result.get('emotion_delta', {}).get('delta', 0.0)
        if delta > 0:
            print(f"  표정변화 : {delta:.3f}")
    print(f"  전체   : {result['latency_ms']:.1f} ms")
    print(f"  LLM    : {result['llm_ms']:.1f} ms")
    print(f"  목표   : {'✅ <500ms' if result['latency_ms'] < 500 else '❌ 초과'}")
    print(f"\n[공감 발화]")
    print(f"  {result['response']}")


def run_all_tests(node_b: NodeBCore):
    print("\n" + "="*60)
    print("전체 테스트 실행")
    print("="*60)
    latencies = []
    for i in range(len(TEST_CASES)):
        run_test(i, node_b)
        latencies.append(node_b.process(TEST_CASES[i]["packet"])["latency_ms"])
    print(f"\n{'='*60}")
    print(f"[성능 요약]")
    print(f"  평균 처리시간: {sum(latencies)/len(latencies):.1f} ms")
    print(f"  최대 처리시간: {max(latencies):.1f} ms")
    print(f"  최소 처리시간: {min(latencies):.1f} ms")
    print(f"  목표 (<500ms): {'✅ 달성' if max(latencies) < 500 else '❌ 미달'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Node B Core 테스트")
    parser.add_argument("--case", type=int, default=None,
                        help=f"테스트 케이스 번호 (1~{len(TEST_CASES)}, 생략시 전체 실행)")
    parser.add_argument("--real-llm", action="store_true",
                        help="Ollama(Gemma) 실제 연동 (기본: Mock LLM)")
    args = parser.parse_args()

    print("Node B Core 초기화 중...")
    node_b = NodeBCore(use_real_llm=args.real_llm)
    print("초기화 완료\n")

    print("사용 가능한 테스트 케이스:")
    for i, case in enumerate(TEST_CASES):
        print(f"  {i+1}. {case['name']}")

    if args.case:
        idx = args.case - 1
        if 0 <= idx < len(TEST_CASES):
            run_test(idx, node_b)
        else:
            print(f"❌ 잘못된 케이스 번호: {args.case}")
    else:
        run_all_tests(node_b)