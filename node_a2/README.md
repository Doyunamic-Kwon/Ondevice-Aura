# 🎙️ Aura Node A : Voice input (Jetson Nano)

본 프로젝트는 통합 시스템의 시작점인 **Aura Node A : Voice input** 노드 역할을 담당하며, **NVIDIA Jetson Nano** 환경에 최적화되어 있습니다.

마이크를 통해 들어오는 사용자의 음성을 실시간으로 감지(VAD)하고 텍스트로 변환(STT)할 뿐만 아니라, `librosa` 없이 가벼운 수치 계산만으로 목소리의 감정 상태(VA Vector)를 추출하는 기능을 수행합니다. 정밀하게 분석된 음성 및 감정 데이터는 gRPC 통신을 통해 표정 제어 노드로 전송되며, 외부 대화 노드(Node B)로부터 전달받은 답변 데이터를 수신하여 실시간 고품질 TTS로 출력합니다. 또한, TTS 출력 중 새로운 데이터가 수신되면 중복 출력을 방지하기 위해 자동으로 무시하는 동시성 제어 로직이 반영되어 있습니다.

---

## ✨ 주요 기능 및 기술적 장점 (Key Features & Advantages)

### 1. 실시간 VAD (Voice Activity Detection)
* `sounddevice` 라이브러리를 이용해 무음 구간을 제외한 실제 음성 구간만 스마트하게 감지 및 녹음합니다.

### 2. 경량 감정 분석 (VA Vector)
* `NumPy` 기반의 신호 처리를 통해 Valence(정서가)와 Arousal(각성도)을 실시간으로 계산합니다. 무거운 외부 오디오 라이브러리 의존성을 제거하여 시스템 안정성이 극대화되었습니다.

### 3. 초경량 고성능 whisper.cpp 도입
* **온디바이스(On-device) 최적화:** 외부 API 호출이나 네트워크 의존 없이 젯슨 나노 로컬 환경에서 완전히 독립적으로 작동하므로 보안성과 상시 가동성이 보장됩니다.
* **가벼운 리소스 소모:** 고성능 C/C++ 기반 코드로 재작성되어, GPU 가속 없이 젯슨 나노의 ARM CPU 환경에서도 놀라울 정도로 빠른 텍스트 변환 속도(Low Latency)를 보여줍니다.
* **효율적인 메모리 사용:** 대형 Python 패키지(PyTorch 등)를 로드할 필요가 없어 젯슨 나노의 제한된 RAM 공간을 매우 효율적으로 절약합니다.

### 4. 고품질 TTS 및 동시성 제어
* `gTTS`를 통해 구글의 자연스러운 신경망 음성으로 답변을 출력합니다. 특히 TTS가 출력 중일 때 새로운 답변이 수신되면 이를 드롭(Drop)하여 음성이 겹치지 않도록 방어 로직이 구현되어 있습니다.

### 5. gRPC 기반 멀티 노드 통신
* 타 노드로 분석 데이터를 송신하는 클라이언트 기능과 Node B(LLM)의 답변을 수신하는 서버 기능을 동시에 수행합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
voice_pipeline/
├── main.py              # 전체 시스템 흐름 제어 (Entry Point)
├── config.py            # 모든 경로, 포트, 임계값 설정 관리
├── audio_processor.py   # VAD 녹음, STT 연동, gTTS 출력 로직
├── emotion_analyzer.py  # 순수 수학 연산을 통한 감정 분석 (No Librosa)
├── network_manager.py   # gRPC 서버(답변 수신 및 중복 방지) 및 클라이언트(결과 전송)
├── aura.proto           # gRPC 인터페이스 정의 파일
└── dummy_node_b.py      # 시스템 테스트를 위한 Node B(LLM) 더미 클라이언트
```

---

## 🚀 시작하기 (Getting Started)

### 1. 필수 소프트웨어 설치
터미널에서 아래 명령어를 순서대로 실행하여 시스템 의존성 및 파이썬 패키지를 설치합니다.

```bash
sudo apt update
sudo apt install mpg123 portaudio19-dev
pip3 install numpy sounddevice soundfile gTTS grpcio grpcio-tools
```

### 2. Whisper.cpp 준비
본 프로젝트는 순수 C/C++ 기반으로 빌드되어 뛰어난 속도를 자랑하는 `whisper.cpp`의 CLI 실행 파일을 연동합니다.
1. [whisper.cpp 공식 레포지토리](https://github.com/ggerganov/whisper.cpp)를 클론하고 안내에 따라 빌드합니다.
2. 젯슨 나노 환경에 권장되는 `ggml-tiny.bin` 또는 `ggml-base.bin` 모델을 다운로드합니다.
3. 본 프로젝트의 `config.py` 파일 내 `WHISPER_MAIN_PATH`와 `WHISPER_MODEL_PATH`를 컴파일된 실제 경로로 수정합니다.

### 3. gRPC 코드 생성
프로토콜 버퍼 파일을 파이썬 코드로 컴파일합니다. 터미널에서 다음 명령어를 실행하세요.

```bash
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. aura.proto
```

### 4. 실행

* **터미널 1** (Node A 메인 파이프라인 실행):
  ```bash
  python3 main.py
  ```
* **터미널 2** (테스트용 Node B 더미 클라이언트 실행):
  ```bash
  python3 dummy_node_b.py
  ```

---

## ⚙️ 설정 가이드 (Configuration)

`config.py`에서 다음 변수들을 환경에 맞게 조정할 수 있습니다.
* `VAD_THRESHOLD`: 음성 감지 민감도 (추천: `0.05` ~ `0.2`)
* `SILENCE_DURATION`: 문장 종료로 판단할 침묵 시간 (초)
* `MY_TTS_SERVER_PORT`: Node B로부터 답변을 받을 포트 번호 (기본값: `5050`)
