# Aura-Sync: Node B (Brain)

> 공감형 엣지 AI 에이전트 — Node B 담당 모듈  
> Jetson Orin Nano 8GB | Ollama (Gemma3:1b) | gRPC

---

## 역할

Node C에서 전달받은 프롬프트를 기반으로 공감 발화를 생성하고 Node A(TTS)로 전달합니다.

```
Node A (지각)
  표정/음성 데이터
        ↓
Node C (융합)
  KG 탐색, Alignment 분석, 프롬프트 생성
        ↓ gRPC (5051)
Node B (추론) ← 여기
  ① Fail-safe 위기 감지
  ② BRD 감정 변화량 계산
  ③ Ollama LLM 공감 발화 생성
  ④ TTS 전송
        ↓ gRPC
Node A (TTS 출력)
```

---

## 파일 구조

```
Node_B/
├── README.md
├── test_node_b.py          # 로컬 테스트 (Mock/Ollama)
├── grpc/
│   ├── aura.proto          # 팀 공용 Proto 정의
│   ├── node_b_server.py    # gRPC 서버
│   └── test_connection.py  # 서버 연결 테스트
```

---

## 의존성 설치

```bash
pip3 install torch numpy requests grpcio grpcio-tools --break-system-packages
```

---

## Proto 컴파일 (최초 1회)

```bash
cd grpc/
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. aura.proto
```

---

## 실행 방법

### 1. 로컬 테스트 (Ollama 없이)

```bash
python3 test_node_b.py
```

### 2. 실제 Ollama 연동 테스트

```bash
# Ollama 먼저 웜업
ollama run gemma3:1b "안녕"

# 테스트 실행
python3 test_node_b.py --real-llm

# 특정 케이스만
python3 test_node_b.py --real-llm --case 1
```

### 3. gRPC 서버 실행

```bash
cd grpc/
python3 node_b_server.py            # Ollama 연동
python3 node_b_server.py --mock     # Mock LLM
```

### 4. 서버 연결 테스트

```bash
cd grpc/

# 로컬 테스트
python3 test_connection.py

# 원격 Jetson 테스트
python3 test_connection.py --host 192.168.0.37

# 전체 테스트
python3 test_connection.py --host 192.168.0.37 --full
```

---

## 핵심 컴포넌트

### Fail-safe (Priority 0)
위기 키워드 감지 시 LLM 호출 없이 즉시 전문가 안내 출력

```
감지 키워드: 죽, 사라지, 없어지, 포기, 끝내, 못 살겠
응답 시간: <1ms (LLM 완전 차단)
```

### BRD (Baseline-Relative Delta)
절대적 감정값이 아닌 개인 기준선 대비 변화량으로 공감 모드 결정

```
초기 5회 대화 → 개인 기준선 학습
이후 delta > 0.3 → HIGH 공감 모드
기준선 SQLite 로컬 저장 (재실행 시 유지)
```

### KG Context 정제
Node C에서 받은 ATOMIC raw 문자열을 자연어로 변환

```
입력: "personx finishes project(은)는 X(와)과 HinderedBy 관계임"
출력: "방해 요소: X"
```

---

## 네트워크 설정

| 노드 | IP | 포트 |
|---|---|---|
| Node B (문기님) | 192.168.0.37 | 5051 |
| Node A (TTS) | 192.168.0.34 | 5050 |
| Node C | 192.168.0.x | 50052 |

> 유선 기가비트 이더넷 연결 필수 (Wi-Fi 사용 금지)

---

## Proto 메시지 구조

### 수신 (Node C → Node B)
```protobuf
message ContextualPrompt {
  string session_id   // 사용자 세션
  string request_id   // 요청 ID (응답에 그대로 반환)
  string final_prompt // Node C가 생성한 프롬프트
  float  valence      // 감정 수치 V
  float  arousal      // 감정 수치 A
  string user_text    // 원본 발화 (Fail-safe용)
  FusedEmotionState fused_emotion
}
```

### 송신 (Node B → Node C)
```protobuf
message EmpathyResponse {
  string session_id
  string request_id
  string text          // 공감 발화
  float  response_time // 처리 시간 (ms)
  string strategy      // 응답 전략
  ErrorCode error_code
}
```

---

## 성능 목표

| 항목 | 목표 | 현재 (gemma3:1b) |
|---|---|---|
| Fail-safe 응답 | < 1ms | ✅ ~0ms |
| LLM 추론 | < 500ms | ⚠️ ~3초 |
| 전체 파이프라인 | < 500ms | ⚠️ ~3초 |

> LLM 추론 속도는 Ollama 웜업 후 측정 기준

---

## 참고 논문

| 논문 | 기여 |
|---|---|
| MISER (AAAI 2024) | Cross-Attention 멀티모달 융합 |
| KEMP (EMNLP 2022) | KG 기반 공감 대화 생성 |
| CASE (AAAI 2023) | 감정-상식 정렬 검증 |
| Empathetic CoT (ACL 2024) | 메타인지 공감 사고 연쇄 |
