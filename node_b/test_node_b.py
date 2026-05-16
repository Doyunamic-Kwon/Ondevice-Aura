"""
Aura-Sync: Node B (Brain) — Jetson Orin Nano 로컬 테스트
=========================================================
Node C 팀원 없이 혼자 테스트할 수 있는 Mock 입력 포함

역할:
  - Node C에서 프롬프트(gRPC)를 수신
  - BRD(Baseline-Relative Delta)로 감정 변화량 계산
  - Ollama(Gemma)로 공감 발화 생성
  - Fail-safe: 위기 키워드 감지 시 LLM 차단 → 전문가 안내 출력

실행 방법:
  1. 의존성 설치
     pip3 install ollama requests --break-system-packages

  2. Ollama + Gemma 설치 (Jetson 환경)
     curl -fsSL https://ollama.com/install.sh | sh
     ollama pull gemma2:2b

  3. 실행 (Ollama 없이 Mock LLM으로도 테스트 가능)
     python3 test_node_b.py

  4. 특정 케이스만 실행
     python3 test_node_b.py --case 2

  5. 실제 Ollama 연동
     python3 test_node_b.py --real-llm
"""

import time
import argparse
import json
import sqlite3
import os
from dataclasses import dataclass, field
from typing import List, Optional
from collections import deque


# ──────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────

@dataclass
class NodeCPacket:
    """
    Node C에서 수신하는 데이터 묶음
    실제 환경: gRPC로 수신
    테스트: Mock 데이터로 대체
    """
    prompt     : str              # Node C가 생성한 최종 프롬프트
    valence    : float            # 감정 수치 V (-1 ~ 1)
    arousal    : float            # 감정 수치 A (-1 ~ 1)
    stt_text   : str              # 원본 발화 텍스트 (Fail-safe 키워드 검사용)
    kg_context : List[str] = field(default_factory=list)  # Node C KG 탐색 결과 (raw)
    alignment  : dict      = field(default_factory=dict)  # Node C alignment 결과
    timestamp  : int = 0


@dataclass
class BRDState:
    """
    BRD(Baseline-Relative Delta) 상태 관리
    개인 기준선 대비 감정 변화량을 추적
    """
    baseline_v    : float = 0.0   # 개인 Valence 기준선
    baseline_a    : float = 0.0   # 개인 Arousal 기준선
    history       : deque = field(default_factory=lambda: deque(maxlen=10))
    sample_count  : int = 0


# ──────────────────────────────────────────
# Mock 입력 — Node C 팀원이 실제로 보내줄 데이터
# ──────────────────────────────────────────

TEST_CASES = [
    {
        "name"   : "이별 — 슬픔/무기력",
        "packet" : NodeCPacket(
            stt_text  = "이별했어요, 너무 힘들어요",
            valence   = -0.9,
            arousal   = -0.4,
            prompt    = """[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.
따뜻하고 천천히, 판단 없이 응답하세요.

[감정 분석]
- 감지된 감정: 우울 또는 무기력 (V=-0.90, A=-0.40)
- 권장 전략: 판단 없이 곁에 있어주는 따뜻한 수용

[맥락]
사용자가 직접 말하지 않았지만 관련 가능성이 높은 맥락:
- 외로움, 그리움, 무기력, 일상 무너짐
이 맥락을 자연스럽게 녹여서 구체적으로 공감할 것.

[응답 규칙]
1. 첫 문장에서 감정에 이름을 붙여줄 것
2. 조언보다 수용(Validation)을 우선할 것
3. 2~3문장으로 간결하게
4. "~해보세요" 류의 즉각적 해결책 제시 금지

[USER]
이별했어요, 너무 힘들어요

[ASSISTANT]""",
            timestamp = 1000,
        ),
    },
    {
        "name"   : "직장 스트레스 — 분노/좌절",
        "packet" : NodeCPacket(
            stt_text  = "오늘 프로젝트 에러 때문에 미치겠어요",
            valence   = -0.7,
            arousal   =  0.6,
            prompt    = """[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.
따뜻하고 천천히, 판단 없이 응답하세요.

[감정 분석]
- 감지된 감정: 분노 또는 좌절 (V=-0.70, A=0.60)
- 권장 전략: 감정을 먼저 인정하고, 상황에 대한 공감을 표현

[맥락]
사용자가 직접 말하지 않았지만 관련 가능성이 높은 맥락:
- 야근, 수면 부족, 스트레스, 짜증
이 맥락을 자연스럽게 녹여서 구체적으로 공감할 것.

[응답 규칙]
1. 첫 문장에서 감정에 이름을 붙여줄 것
2. 조언보다 수용(Validation)을 우선할 것
3. 2~3문장으로 간결하게
4. "~해보세요" 류의 즉각적 해결책 제시 금지

[USER]
오늘 프로젝트 에러 때문에 미치겠어요

[ASSISTANT]""",
            timestamp = 2000,
        ),
    },
    {
        "name"   : "실직 — 매우 부정/무기력",
        "packet" : NodeCPacket(
            stt_text  = "오늘 회사에서 잘렸어요, 가족한테 말하기도 무서워요",
            valence   = -0.95,
            arousal   = -0.6,
            prompt    = """[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.
따뜻하고 천천히, 판단 없이 응답하세요.

[감정 분석]
- 감지된 감정: 우울 또는 무기력 (V=-0.95, A=-0.60)
- 권장 전략: 판단 없이 곁에 있어주는 따뜻한 수용

[맥락]
사용자가 직접 말하지 않았지만 관련 가능성이 높은 맥락:
- 불안, 자존감 하락, 경제적 압박, 고립감
이 맥락을 자연스럽게 녹여서 구체적으로 공감할 것.

[응답 규칙]
1. 첫 문장에서 감정에 이름을 붙여줄 것
2. 조언보다 수용(Validation)을 우선할 것
3. 2~3문장으로 간결하게
4. "~해보세요" 류의 즉각적 해결책 제시 금지

[USER]
오늘 회사에서 잘렸어요, 가족한테 말하기도 무서워요

[ASSISTANT]""",
            timestamp = 3000,
        ),
    },
    {
        "name"   : "위기 감지 — Fail-safe 테스트",
        "packet" : NodeCPacket(
            stt_text  = "너무 힘들어서 다 포기하고 싶어요, 사라지고 싶어요",
            valence   = -0.99,
            arousal   = -0.8,
            prompt    = """[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.

[감정 분석]
- 감지된 감정: 우울 또는 무기력 (V=-0.99, A=-0.80)
- 권장 전략: 판단 없이 곁에 있어주는 따뜻한 수용

[USER]
너무 힘들어서 다 포기하고 싶어요, 사라지고 싶어요

[ASSISTANT]""",
            timestamp = 4000,
        ),
    },
    {
        "name"   : "중립 — 일반 대화",
        "packet" : NodeCPacket(
            stt_text  = "오늘 날씨가 좀 흐리네요",
            valence   =  0.1,
            arousal   = -0.1,
            prompt    = """[SYSTEM]
당신은 공감 능력이 뛰어난 AI 상담사입니다.
따뜻하고 천천히, 판단 없이 응답하세요.

[감정 분석]
- 감지된 감정: 중립 (V=0.10, A=-0.10)
- 권장 전략: 자연스러운 대화 유지

[맥락]
추가 맥락 없음 — 발화 내용에만 집중할 것.

[응답 규칙]
1. 첫 문장에서 감정에 이름을 붙여줄 것
2. 조언보다 수용(Validation)을 우선할 것
3. 2~3문장으로 간결하게
4. "~해보세요" 류의 즉각적 해결책 제시 금지

[USER]
오늘 날씨가 좀 흐리네요

[ASSISTANT]""",
            timestamp = 5000,
        ),
    },
]


# ──────────────────────────────────────────
# BRD: Baseline-Relative Delta
# ──────────────────────────────────────────

class BRDCalculator:
    """
    감정 절대값이 아닌 '개인 기준선 대비 변화량'으로 공감 모드 결정

    원리:
      - 처음 N번 대화로 개인 기준선(baseline) 학습
      - 이후 매 발화마다 delta = |현재 - baseline| 계산
      - delta가 임계값 초과 시 HIGH 공감 모드 활성화

    장점:
      - 평소에 부정적인 사람도 정확히 감지 가능
      - 절대값 기준보다 개인화된 반응
    """

    BASELINE_WINDOW  = 5     # 기준선 학습에 사용할 초기 샘플 수
    DELTA_THRESHOLD  = 0.3   # HIGH 모드 진입 임계값
    DB_PATH          = "/tmp/aura_sync_brd.db"

    def __init__(self, user_id: str = "test_user"):
        self.user_id = user_id
        self.state   = BRDState()
        self._init_db()
        self._load_state()

    def _init_db(self):
        """SQLite로 기준선 영구 저장 (로컬, 프라이버시 보호)"""
        conn = sqlite3.connect(self.DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brd_state (
                user_id      TEXT PRIMARY KEY,
                baseline_v   REAL,
                baseline_a   REAL,
                sample_count INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def _load_state(self):
        """저장된 기준선 불러오기"""
        conn = sqlite3.connect(self.DB_PATH)
        row = conn.execute(
            "SELECT baseline_v, baseline_a, sample_count FROM brd_state WHERE user_id=?",
            (self.user_id,)
        ).fetchone()
        conn.close()

        if row:
            self.state.baseline_v    = row[0]
            self.state.baseline_a    = row[1]
            self.state.sample_count  = row[2]

    def _save_state(self):
        """기준선 저장"""
        conn = sqlite3.connect(self.DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO brd_state (user_id, baseline_v, baseline_a, sample_count)
            VALUES (?, ?, ?, ?)
        """, (self.user_id, self.state.baseline_v, self.state.baseline_a, self.state.sample_count))
        conn.commit()
        conn.close()

    def calculate(self, valence: float, arousal: float) -> dict:
        """
        BRD Delta 계산 및 기준선 업데이트

        Returns:
            {
              "delta"       : float,  # 변화량 (0 ~ 2.0)
              "empathy_mode": str,    # "HIGH" or "NORMAL"
              "is_baseline" : bool,   # 아직 기준선 학습 중인지
            }
        """
        self.state.sample_count += 1
        self.state.history.append((valence, arousal))

        # 기준선 학습 단계
        if self.state.sample_count <= self.BASELINE_WINDOW:
            all_v = [h[0] for h in self.state.history]
            all_a = [h[1] for h in self.state.history]
            self.state.baseline_v = sum(all_v) / len(all_v)
            self.state.baseline_a = sum(all_a) / len(all_a)
            self._save_state()
            return {
                "delta"       : 0.0,
                "empathy_mode": "NORMAL",
                "is_baseline" : True,
            }

        # Delta 계산
        delta_v = abs(valence - self.state.baseline_v)
        delta_a = abs(arousal - self.state.baseline_a)
        delta   = (delta_v + delta_a) / 2

        # 기준선 지수이동평균 업데이트 (α=0.1)
        alpha = 0.1
        self.state.baseline_v = (1 - alpha) * self.state.baseline_v + alpha * valence
        self.state.baseline_a = (1 - alpha) * self.state.baseline_a + alpha * arousal
        self._save_state()

        empathy_mode = "HIGH" if delta > self.DELTA_THRESHOLD else "NORMAL"

        return {
            "delta"       : delta,
            "empathy_mode": empathy_mode,
            "is_baseline" : False,
        }


# ──────────────────────────────────────────
# Fail-safe: Priority 0
# ──────────────────────────────────────────

CRISIS_KEYWORDS = [
    "죽", "자살", "사라지고 싶", "없어지고 싶",
    "포기하고 싶", "끝내고 싶", "못 살겠", "살기 싫"
]

CRISIS_RESPONSE = """지금 많이 힘드시군요. 혼자 감당하기 너무 힘든 감정이에요.

지금 바로 전문가와 이야기하실 수 있어요:
  📞 자살예방상담전화: 1393 (24시간)
  📞 정신건강위기상담전화: 1577-0199 (24시간)

지금 안전하신가요?"""


def check_crisis(stt_text: str) -> bool:
    """위기 키워드 감지 — LLM 호출 전 반드시 먼저 실행"""
    return any(kw in stt_text for kw in CRISIS_KEYWORDS)


# ──────────────────────────────────────────
# KG Context 정제
# ──────────────────────────────────────────

# ATOMIC 관계 타입 → 한국어 자연어 매핑
_REL_KO = {
    "HinderedBy" : "방해 요소",
    "xNeed"      : "사전에 필요한 것",
    "xIntent"    : "의도",
    "xWant"      : "원하는 것",
    "xEffect"    : "결과",
    "xReact"     : "감정 반응",
    "xAttr"      : "성격/특성",
    "oWant"      : "상대방이 원하는 것",
    "oEffect"    : "상대방에게 미치는 영향",
    "oReact"     : "상대방의 반응",
    "Causes"     : "원인",
    "isAfter"    : "이후 상황",
    "isBefore"   : "이전 상황",
}


def _extract_rel_type(raw: str) -> str:
    """raw KG 문자열에서 관계 타입 추출"""
    for rel in _REL_KO:
        if rel in raw:
            return rel
    return ""


def _extract_tail(raw: str) -> str:
    """
    raw KG 문자열에서 목적어(tail) 추출
    Node C 팀원 포맷: "{subject}(은)는 {tail}(와)과 {RelType} 관계임"
    """
    try:
        after_subj = raw.split("(은)는 ", 1)[1]
        tail = after_subj.split("(와)과")[0].strip()
        # "personx", "person x" 제거
        tail = tail.replace("personx", "").replace("person x", "").strip(" '\"")
        return tail
    except Exception:
        return ""


def clean_kg_context(kg_context: List[str]) -> List[str]:
    """
    Node C에서 받은 날것의 ATOMIC KG 문자열을 자연어로 정제

    입력 예:
      "personx finishes personx's project(은)는
       personx's children need some play time(와)과 HinderedBy 관계임"

    출력 예:
      "방해 요소: 's children need some play time"

    정제 실패 시 원본 반환 (안전장치)
    """
    cleaned = []
    seen    = set()

    for raw in kg_context:
        if not raw:
            continue

        rel_type = _extract_rel_type(raw)
        tail     = _extract_tail(raw)

        if not tail or len(tail) > 80:
            continue

        rel_ko = _REL_KO.get(rel_type, rel_type)
        result = f"{rel_ko}: {tail}"

        if result not in seen:
            seen.add(result)
            cleaned.append(result)

    return cleaned if cleaned else kg_context  # 정제 실패 시 원본 반환


# ──────────────────────────────────────────
# LLM 인터페이스
# ──────────────────────────────────────────

class MockLLM:
    """
    Ollama 없이 테스트할 수 있는 Mock LLM
    실제 환경에서는 OllamaLLM으로 교체
    """

    MOCK_RESPONSES = {
        "우울": "많이 지치고 슬프셨겠어요. 이별은 정말 마음이 무너지는 경험이에요. 지금 이 감정을 느끼는 게 당연해요, 충분히 아파도 괜찮아요.",
        "분노": "정말 답답하고 화가 나셨겠어요. 에러 때문에 온종일 고생하셨을 텐데, 그 피로감이 느껴져요. 지금 많이 지쳐 계시겠네요.",
        "불안": "많이 걱정되고 불안하시겠어요. 그 떨리는 마음, 충분히 이해해요. 지금 느끼는 감정이 자연스러운 거예요.",
        "중립": "오늘 날씨가 흐리군요. 그런 날엔 괜히 마음도 무거워지기도 하죠. 오늘 하루 어떻게 지내셨어요?",
        "default": "지금 많이 힘드시겠어요. 그 감정, 충분히 느껴도 괜찮아요.",
    }

    def generate(self, prompt: str, valence: float) -> tuple[str, float]:
        """
        Mock 응답 생성

        Returns:
            (응답 텍스트, 처리시간ms)
        """
        t = time.time()
        time.sleep(0.05)  # Mock 추론 시간

        if valence < -0.8:
            response = self.MOCK_RESPONSES["우울"]
        elif valence < -0.5:
            response = self.MOCK_RESPONSES["분노"] if valence > -0.7 else self.MOCK_RESPONSES["우울"]
        elif valence < -0.2:
            response = self.MOCK_RESPONSES["불안"]
        elif abs(valence) <= 0.2:
            response = self.MOCK_RESPONSES["중립"]
        else:
            response = self.MOCK_RESPONSES["default"]

        latency = (time.time() - t) * 1000
        return response, latency


class OllamaLLM:
    """
    실제 Ollama(Gemma) 연동
    Jetson에서 ollama pull gemma2:2b 후 사용

    실행: python3 test_node_b.py --real-llm
    """

    def __init__(self, model: str = "gemma3:1b", host: str = "http://localhost:11434"):
        self.model = model
        self.host  = host

    def generate(self, prompt: str, valence: float) -> tuple[str, float]:
        try:
            import requests
            t = time.time()

            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model" : self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature"   : 0.7,
                        "num_predict"   : 150,   # 2~3문장 분량
                        "repeat_penalty": 1.1,
                    }
                },
                timeout=120,  # 첫 로딩 시 모델 웜업 시간 고려
            )
            data     = response.json()
            text     = data.get("response", "").strip()
            latency  = (time.time() - t) * 1000
            return text, latency

        except Exception as e:
            return f"[LLM 오류: {e}]", 0.0


# ──────────────────────────────────────────
# Node B Core
# ──────────────────────────────────────────

class NodeBCore:
    """
    Node B (Brain) 핵심 처리 로직

    처리 순서:
      1. Fail-safe 키워드 검사 (Priority 0)
      2. BRD Delta 계산
      3. LLM 공감 발화 생성
    """

    def __init__(self, use_real_llm: bool = False):
        self.brd = BRDCalculator(user_id="test_user")
        self.llm = OllamaLLM() if use_real_llm else MockLLM()
        print(f"  LLM 모드: {'Ollama (Gemma)' if use_real_llm else 'Mock'}")

    def process(self, packet: NodeCPacket) -> dict:
        """
        패킷 처리 → 공감 발화 생성

        Returns:
            {
              "response"    : 최종 공감 발화,
              "is_crisis"   : 위기 감지 여부,
              "brd"         : BRD 결과,
              "latency_ms"  : 전체 처리 시간,
              "llm_ms"      : LLM 추론 시간,
            }
        """
        t_start = time.time()

        # ── Step 1: Fail-safe (Priority 0) ──────────────
        is_crisis = check_crisis(packet.stt_text)
        if is_crisis:
            latency = (time.time() - t_start) * 1000
            return {
                "response"  : CRISIS_RESPONSE,
                "is_crisis" : True,
                "brd"       : None,
                "latency_ms": latency,
                "llm_ms"    : 0.0,
            }

        # ── Step 2: KG Context 정제 ─────────────────────
        cleaned_kg = clean_kg_context(packet.kg_context)

        # ── Step 3: BRD Delta 계산 ───────────────────────
        brd_result = self.brd.calculate(packet.valence, packet.arousal)

        # ── Step 4: LLM 추론 ────────────────────────────
        response, llm_ms = self.llm.generate(packet.prompt, packet.valence)

        latency = (time.time() - t_start) * 1000

        return {
            "response"  : response,
            "is_crisis" : False,
            "brd"       : brd_result,
            "cleaned_kg": cleaned_kg,
            "latency_ms": latency,
            "llm_ms"    : llm_ms,
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

    result = node_b.process(packet)

    print(f"\n[결과]")

    if result["is_crisis"]:
        print(f"  ⚠️  위기 감지 — LLM 차단됨")
    else:
        brd = result["brd"]
        if brd["is_baseline"]:
            print(f"  BRD    : 기준선 학습 중...")
        else:
            print(f"  BRD    : delta={brd['delta']:.3f}  모드={brd['empathy_mode']}")

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
    parser.add_argument(
        "--case", type=int, default=None,
        help=f"테스트 케이스 번호 (1~{len(TEST_CASES)}, 생략시 전체 실행)"
    )
    parser.add_argument(
        "--real-llm", action="store_true",
        help="Ollama(Gemma) 실제 연동 (기본: Mock LLM)"
    )
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
