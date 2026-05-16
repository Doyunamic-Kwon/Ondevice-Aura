# Aura Node C: Knowledge Bridge

Aura 시스템의 Node C (Knowledge Bridge) 모듈이다. 사용자의 언어적/비언어적 데이터를 분석하고, ATOMIC 2020 기반 지식 그래프에서 공감 맥락을 추출하여 Node B(LLM)에 전달하는 역할을 한다.

---

## 시스템 구성

| 구성 요소 | 기술 스택 | 역할 |
|-----------|----------|------|
| 지식 그래프 | Neo4j + ATOMIC 2020 | 공감 추론을 위한 상식 지식 저장소 |
| 키워드 추출 | Mecab (mecab-ko-dic) | 한국어 형태소 분석 및 명사 추출 |
| 감성 분석 | korean_sentiment (HuggingFace) | 텍스트 감정 → Valence-Arousal 매핑 |
| 언어 변환 | Google Translator (deep_translator) | 한국어 키워드 → 영어 변환 (KG 검색용) |
| 통신 | gRPC (Protobuf) | Node A/B 간 실시간 데이터 교환 |

---

## 지식 그래프 구축

### 데이터 소스

ATOMIC 2020 데이터셋 (`train.tsv`)을 사용한다. 원본 데이터는 약 1,076,880개의 트리플로 구성되어 있으며, 23종의 관계 타입을 포함한다.

### 관계 필터링

ATOMIC의 23개 관계 타입 중 공감 추론에 직접적으로 기여하는 9개만 선별하여 임포트한다. 물리적 속성이나 도구 사용법 등 공감과 무관한 관계는 노이즈로 작용하기 때문에 제외했다.

**선별된 9개 관계 (Empathy Relations)**

| 관계 | 의미 | 공감 활용 | 가중치 |
|------|------|----------|--------|
| `xReact` | PersonX가 느끼는 감정 반응 | 사용자가 어떤 감정을 느낄지 예측 | 1.0 |
| `oReact` | 타인이 느끼는 감정 반응 | 공감적 시각 전환에 활용 | 0.9 |
| `xWant` | PersonX가 원하는 것 | 위로 방향 설정에 활용 | 0.7 |
| `xEffect` | PersonX에게 미치는 영향 | 상황의 결과를 이해 | 0.7 |
| `xIntent` | PersonX의 의도 | 행동 이유 파악 | 0.6 |
| `xNeed` | PersonX에게 필요한 것 | 도움이 필요한 부분 파악 | 0.6 |
| `xAttr` | PersonX의 성격/속성 | 사용자 성향 이해 | 0.5 |
| `oWant` | 타인이 원하는 것 | 타인 관점의 욕구 이해 | 0.5 |
| `oEffect` | 타인에게 미치는 영향 | 주변에 미치는 영향 파악 | 0.5 |

**제외된 14개 관계와 그 이유**

| 관계 | 원본 건수 | 제외 사유 |
|------|----------|----------|
| `ObjectUse` | 140,669 | 물건 사용법은 공감과 무관 |
| `HinderedBy` | 77,616 | 행동 방해 요소로, 대부분 물리적 제약 |
| `isFilledBy` | 24,174 | 빈칸 채우기 형태의 구문 완성 |
| `AtLocation` | 17,423 | 장소 정보 |
| `isBefore` / `isAfter` | 33,579 | 시간/순서 관계 |
| `HasSubEvent` | 10,894 | 하위 이벤트 분해 |
| `CapableOf` | 7,216 | 물리적 능력 |
| `HasProperty` | 4,971 | 물리적 속성 |
| `MadeUpOf` | 2,911 | 구성 요소 |
| `NotDesires` / `Desires` | 5,525 | 건수가 적고 공감 기여도 낮음 |
| `Causes` / `xReason` | 621 | 건수가 너무 적어 실용성 낮음 |

### 실제 임포트 결과

```
필터링 전: 1,076,880 트리플 (23종 관계)
필터링 후:   630,999 트리플 (9종 관계)
제거된 양:   325,599건 (비공감 관계) + 120,282건 (tail="none" 제거)
```

### Neo4j 관계 저장 방식 변경

기존에는 모든 관계를 `ATOMIC_REL`이라는 단일 관계 레이블에 `type` 속성으로 관계명을 저장했다. 이 방식은 검색 시 속성 값을 필터링해야 하므로 인덱스를 활용하지 못한다.

변경 후에는 `xReact`, `oReact` 등 관계 타입 자체를 Neo4j의 관계 레이블로 직접 사용한다. Neo4j는 관계 레이블에 대한 인덱스를 내부적으로 유지하기 때문에 `type(r) IN $relations` 형태의 쿼리가 빠르게 동작한다.

```
Before: MATCH (n)-[r:ATOMIC_REL {type: 'xReact'}]->(m)   -- 속성 필터링 필요
After:  MATCH (n)-[r:xReact]->(m)                        -- 레이블 직접 매칭
```

---

## 검색 파이프라인

### 한국어 입력 → 영어 KG 검색 (번역 방식 선택 근거)

ATOMIC 데이터셋은 영어로 작성되어 있다. 한국어 사용자 입력을 영어 KG에서 검색하기 위한 두 가지 접근 방식을 검토했다.

**방식 A: DB 노드를 한국어로 번역 (미채택)**
- 63만 개 이상의 노드를 미리 한국어로 번역해두고, 한국어 키워드로 직접 검색
- 문제점: Google Translate로 대량 번역 시 오역이 빈번하게 발생했다. 특히 ATOMIC의 이벤트 표현(`PersonX gives a presentation`)은 문맥 없이 번역하면 의미가 왜곡되는 경우가 많았다.
- 실제 테스트에서 검색 품질이 낮게 나왔다.

**방식 B: 사용자 키워드를 영어로 번역 (채택)**
- 사용자 입력에서 추출한 한국어 키워드(1~3개)를 실시간으로 영어로 번역한 뒤, 영어 원본 DB에서 검색
- 번역 대상이 짧은 단어 단위이므로 오역 가능성이 낮다.
- 번역 결과를 캐싱하여 동일 키워드에 대한 중복 API 호출을 방지한다.
- 배치 번역(`translate_batch`)을 사용하여 네트워크 호출을 1회로 줄인다.

### 검색 결과 우선순위 정렬

검색된 KG 트리플은 관계 타입별 가중치(위 표 참고)에 따라 정렬된다. 감정 반응(`xReact`, `oReact`)이 가장 높은 우선순위를 가지며, 상위 7건만 프롬프트에 포함한다.

### 구조화된 프롬프트 포맷

검색 결과를 단순 텍스트로 나열하는 대신, 관계 카테고리별로 그룹핑하여 LLM이 맥락을 구분할 수 있도록 구조화했다.

```
[예상 감정 반응]
  - embarrassed
  - stressed

[예상 욕구/바람]
  - try again
  - get comfort from someone

[예상 결과/영향]
  - lose confidence
```

카테고리 출력 순서는 고정이다: 감정 반응 → 욕구/바람 → 결과/영향 → 의도 → 필요 → 성격/속성. 이 순서는 공감 대화에서 가장 먼저 파악해야 할 정보 순서를 반영한다.

---

## 감정 융합 방식: Cross-Attention 대신 Weighted RAG Pipeline

### Cross-Attention을 채택하지 않은 이유

멀티모달 감정 융합에서 Cross-Attention 기반 접근(KG 임베딩과 텍스트 임베딩을 어텐션으로 결합)은 학술적으로 높은 성능을 보이지만, 이 프로젝트에서는 채택하지 않았다.

**1. 디바이스 제약**: 타겟 하드웨어가 Jetson(ARM aarch64)이다. Cross-Attention 레이어를 추가하면 별도의 학습 가능한 파라미터가 필요하고, 이를 Jetson에서 실시간으로 추론하는 것은 레이턴시 요구사항(목표: 500ms 이내)을 충족하기 어렵다.

**2. 파인튜닝 비용**: Cross-Attention 방식은 KG 임베딩과 텍스트 임베딩을 동시에 입력받는 모델을 파인튜닝해야 한다. ATOMIC 규모의 데이터에 대해 이 학습을 수행하려면 GPU 시간과 학습 데이터(공감 대화 + KG 정답쌍) 구축 비용이 크다.

**3. 팀 구조**: Node B(LLM 추론)는 별도 팀원이 관리한다. Cross-Attention은 Node B의 모델 아키텍처를 직접 수정해야 하지만, RAG 방식은 Node C가 프롬프트만 조립하면 되므로 모듈 간 독립성이 유지된다.

### 대안: Weighted RAG Pipeline

Cross-Attention 대신 **가중치 기반 RAG(Retrieval-Augmented Generation) 파이프라인**을 설계했다. 이 방식은 세 가지 단계로 구성된다.

**1단계: 관계 타입별 가중치 검색 (Weighted Retrieval)**

KG 검색 결과에 관계 타입별 가중치를 부여하여, Cross-Attention이 학습으로 수행하는 "어떤 지식이 더 중요한가"의 판단을 규칙 기반으로 대체한다. `xReact`(감정 반응)에 1.0, `oReact`에 0.9 등 공감 기여도 순으로 가중치를 할당하고, 검색 결과를 이 가중치 기준으로 정렬한 뒤 상위 7건만 선별한다.

이 방식의 이점: Cross-Attention은 학습 데이터가 부족하면 관련 없는 지식에도 높은 attention score를 줄 수 있지만, 규칙 기반 가중치는 ATOMIC의 관계 체계가 명확히 정의되어 있으므로 안정적으로 동작한다.

**2단계: 구조화된 프롬프트 주입 (Structured Augmentation)**

Cross-Attention이 임베딩 공간에서 지식을 융합하는 것과 달리, 검색된 지식을 관계 카테고리별로 그룹핑하여 자연어 형태로 프롬프트에 삽입한다. 카테고리 순서(감정 반응 → 욕구 → 영향 → 의도 → 필요 → 성격)는 공감 대화에서 우선 파악해야 할 정보 순서를 반영한다.

이 방식의 이점: LLM이 자연어로 된 맥락을 직접 읽으므로, 임베딩 융합 시 발생할 수 있는 정보 손실이 없다. 또한 프롬프트의 KG 섹션을 사람이 직접 읽고 디버깅할 수 있다.

**3단계: Alignment 기반 우선순위 조정 (Sentiment-Aware Priority)**

텍스트 감정과 비언어 감정의 불일치가 감지되면, 해당 요청의 priority를 상향 조정하고 프롬프트에 불일치 정보를 명시한다. Cross-Attention 모델에서는 이런 메타 정보를 별도의 컨디셔닝 벡터로 주입해야 하지만, RAG 방식에서는 프롬프트 텍스트에 자연어로 추가하면 된다.

### 비교 요약

| 항목 | Cross-Attention | Weighted RAG (채택) |
|------|----------------|--------------------|
| 지식 융합 방식 | 임베딩 공간에서 어텐션 연산 | 자연어 프롬프트에 구조화 삽입 |
| 추론 비용 | 어텐션 레이어 추가 연산 필요 | KG 검색 + 문자열 조합만 필요 |
| 재학습 필요성 | KG 변경 시 모델 재학습 필요 | KG 변경 시 재학습 불필요 |
| 디버깅 용이성 | 어텐션 가중치 해석 필요 | 프롬프트를 직접 읽고 확인 가능 |
| Jetson 적합성 | 메모리/연산 부담 큼 | 경량으로 동작 |
| 모듈 독립성 | Node B 모델 수정 필수 | Node C만으로 완결 |

---

## Sentiment Alignment Check

사용자의 텍스트(언어적 감정)와 표정/음성(비언어적 감정)의 일치 여부를 검사한다.

- 텍스트 감성 분석: Valence-Arousal 2차원 벡터로 변환
- 비언어 감정: Node A에서 수신한 Valence-Arousal 벡터
- 비교 방법: 코사인 유사도 (임계값: 0.5)

불일치가 감지되면 (`score < 0.5`) "감정 은폐 또는 반어법 사용 가능성"을 프롬프트에 명시하여, LLM이 표면적 발화만이 아니라 숨겨진 감정까지 고려한 응답을 생성하도록 유도한다.

---

## 성능 최적화

커밋 히스토리에 걸쳐 적용된 주요 성능 최적화 항목들이다.

### 싱글톤 패턴으로 분석 엔진 관리

NodeC 객체(KG 연결, Mecab 로드, Sentiment 모델 로드)를 매 gRPC 요청마다 생성하면 초기화에 수 초가 소요된다. 이를 방지하기 위해 `get_node_c()` 함수에서 싱글톤 패턴을 적용했다. `threading.Lock`으로 동시 접근을 보호하여 멀티스레드 환경에서도 단 한 번만 초기화된다.

### 백그라운드 예열 (Pre-warming)

`main.py`에서 gRPC 서버 시작과 동시에 `get_node_c()`를 백그라운드 스레드에서 호출한다. 이렇게 하면 서버가 클라이언트 요청을 받기 전에 모델 로딩이 완료되므로, 첫 번째 요청에서 발생하는 Cold Start 지연을 제거할 수 있다.

```python
threading.Thread(target=get_node_c, daemon=True).start()
```

### 텍스트 없는 요청의 분석 스킵

Node A에서 표정 데이터만 전송하는 경우(텍스트 필드가 비어 있는 경우), KG 검색, Mecab 분석, Sentiment 분석을 모두 건너뛰고 즉시 프롬프트를 조립한다. 이를 통해 비언어 데이터의 전달 지연을 최소화했다.

### 비동기 전송으로 Node A 대기 시간 제거

Node C가 Node B에 프롬프트를 전송하고 응답을 기다리는 동안, Node A는 다음 데이터를 보내지 못하고 블로킹되는 문제가 있었다. Node B 전송 로직을 비동기로 분리하여, Node A의 gRPC 응답은 즉시 반환하고 Node B 통신은 백그라운드에서 처리하도록 변경했다.

### Node B 과부하 방지 및 락 최적화

동시에 여러 요청이 Node B로 전송되는 것을 방지하기 위해 큐 보호 로직을 추가했다. Numpy 배열 타입 불일치로 인한 잠재적 연산 오류도 `np.array(..., dtype=np.float32)` 강제 변환으로 사전에 차단한다.

### 번역 결과 캐싱

한국어 → 영어 번역 결과를 딕셔너리에 캐싱하여, 동일한 키워드가 반복 입력될 때 네트워크 호출을 하지 않는다. 대화가 진행될수록 캐시 적중률이 올라가 검색 속도가 향상된다.

### 감정 변화 임계치 필터링 (Emotion Change Throttling)

Node A는 카메라 프레임 단위로 표정 데이터를 전송하면 초당 수십 번의 gRPC 호출이 발생할 수 있다. 매번 Node B(LLM)를 호출하면 시스템이 버티지 않으므로, 의미 있는 변화가 있을 때만 파이프라인을 가동한다.

- **변화량 측정**: Valence-Arousal 평면에서 유클리드 거리로 계산 `sqrt((dV)^2 + (dA)^2)`
- **임계치**: 0.12 미만이면 스킵 (미세한 표정 노이즈 제거)
- **최소 전송 간격**: 1초 (연속 요청 시에도 최대 1Hz로 제한)
- 위 두 조건 중 하나라도 미충족이면 Node B 호출 없이 즉시 응답 반환

---

## 3-모달 감정 융합 (Modal Fusion)

### 문제 상황

사용자의 감정을 이해하려면 세 가지 신호가 필요하다.

- **표정 (Face)**: Node A가 매 프레임 보내는 Valence-Arousal 값
- **음성 톤 (Voice)**: STT와 함께 Node A가 보내는 Valence-Arousal 값
- **텍스트 감성 (Text)**: Sentiment 모델이 입력 텍스트를 분석한 Valence-Arousal 값

기존 코드는 이 세 신호가 각각 구분 없이 프롬프트에 나열되었고, Alignment Check도 텍스트 vs 표정만 비교했다. 음성 톤은 분석 모듈에서 제외되었다.

### 설계 방식: ModalFusionLayer

**가중치 근거**

| 신호 | 가중치 | 이유 |
|------|------|------|
| 표정 (face) | 0.4 | 비언어 감정은 사회적 필터링이 적어 직접적 |
| 음성 톤 (voice) | 0.4 | 음성의 감정적 컨텐츠를 반영 |
| 텍스트 (text) | 0.2 | 사회적 필터링으로 인해 실제 감정과 다를 수 있음 |

**신호가 일부만 있는 경우**

표정과 음성은 별도 gRPC 호출로 들어온다. 음성이 아직 도착하지 않은 상태에서 표정만 있으면, 음성 가중치(0.4)를 표정으로 통합하여 재정규화한다. `NodeC`는 `last_face_va`, `last_voice_va`를 세션 상태로 유지하며, 새 신호가 들어올 때마다 상태를 업데이트한다.

**Alignment Check와의 연동**

기존에는 텍스트 감성 vs 표정 V-A만 비교하는 2-way Alignment였다. 변경 후는 텍스트 감성 vs **융합된 비언어 벡터**를 비교하는 3-way Alignment로 확장되었다. 감정 은폐 감지가 더 견고해진다.

```
[Before] Alignment: 텍스트(V,A) vs 표정(V,A)
[After]  Alignment: 텍스트(V,A) vs fused_nonverbal(V,A)
                              fused = face(0.4) + voice(0.4)  // 업데이트 시 0.8+0.2 또는 0.5+0.5 재정규화
```

---

## 트러블슈팅

### Neo4j 연결 실패 (`ServiceUnavailable`)

`docker start aura-neo4j` 직후에 스크립트를 실행하면 연결이 거부될 수 있다. Neo4j는 컨테이너 시작 후 JVM 초기화와 데이터 복구에 15~30초가 소요된다.

```
neo4j.exceptions.ServiceUnavailable: Couldn't connect to localhost:7687
```

해결: 컨테이너 시작 후 로그에서 `Started.` 메시지를 확인한 뒤 스크립트를 실행한다.

```bash
sudo docker logs aura-neo4j | tail -n 5
# "Started." 확인 후
python3 src/import_atomic.py
```

### ATOMIC_REL → 개별 레이블 마이그레이션

기존 DB에 `ATOMIC_REL` 관계로 저장된 데이터가 있는 경우, `import_atomic.py`를 실행하면 기존 데이터를 전부 삭제하고 새로운 관계 레이블 구조로 재임포트한다. 기존에 `update_neo4j_korean.py`로 추가한 `name_ko` 속성도 함께 삭제되지만, 현재는 번역 방식을 "사용자 키워드 실시간 번역"으로 전환했으므로 `name_ko` 속성이 더 이상 필요하지 않다.

### gRPC 포트 충돌

Node C 서버 기본 포트는 `5052`이다. 이미 해당 포트를 사용하는 프로세스가 있으면 서버가 시작되지 않는다.

```bash
# 포트 사용 중인 프로세스 확인
lsof -i :5052
```

---

## 폴더 구조

```
node_c/
  src/
    import_atomic.py           -- ATOMIC 데이터 필터링 및 Neo4j 임포트
    node_c_prototype.py        -- KG 검색, 감성 분석, Alignment 검사 로직
    bridge_sender_integrated.py -- 프롬프트 조립 및 Node B gRPC 전송
    node_c_server.py           -- gRPC 서버 (Node A 수신용)
    aura.proto                 -- Protobuf 정의
    aura_pb2.py / aura_pb2_grpc.py -- 생성된 gRPC 코드
    update_neo4j_korean.py     -- DB 노드 한국어 번역 (현재 미사용)
    test_node_c.py             -- Node C 단위 테스트
  main.py                     -- 서버 실행 엔트리 포인트
  test_integration.py          -- Node C-B 통합 테스트
  train.tsv                   -- ATOMIC 2020 원본 데이터
```

---

## 실행 방법

### 사전 조건
- Python 3.8 이상
- Neo4j (Docker 권장)
- KoNLPy + Mecab (mecab-ko-dic)

### 지식 그래프 초기 구축 (1회)
```bash
sudo docker start aura-neo4j
# 30초 대기 후
python3 src/import_atomic.py
```

### 서버 실행
```bash
python3 main.py
```
