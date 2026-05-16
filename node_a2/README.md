# 🎙️ Aura Node A : Voice input (Jetson Nano)

[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![Jetson Nano](https://img.shields.io/badge/Hardware-Jetson%20Nano-green.svg)](https://developer.nvidia.com/embedded/jetson-nano-developer-kit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

본 프로젝트는 통합 시스템의 시작점인 **Aura Node A : Voice input** 노드 역할을 담당하며, **NVIDIA Jetson Nano** 환경에 최적화되어 있습니다. 

마이크를 통해 들어오는 사용자의 음성을 실시간으로 감지(VAD)하고 텍스트로 변환(STT)할 뿐만 아니라, `librosa` 없이 가벼운 수치 계산만으로 목소리의 감정 상태(VA Vector)를 추출하는 기능을 수행합니다. 정밀하게 분석된 음성 및 감정 데이터는 gRPC 통신을 통해 표정 제어 노드로 전송되며, 외부 대화 노드(Node B)로부터 전달받은 답변 데이터를 수신하여 실시간 고품질 TTS로 출력합니다.

---

## ✨ 주요 기능 (Key Features)

* **실시간 VAD (Voice Activity Detection):** `sounddevice`를 이용해 무음 구간을 제외한 실제 음성 구간만 스마트하게 감지 및 녹음합니다.
* **경량 감정 분석 (VA Vector):** `NumPy` 기반의 신호 처리를 통해 Valence(정서가)와 Arousal(각성도)을 실시간으로 계산합니다.
* **고성능 STT (Speech-to-Text):** `whisper.cpp`를 C++ 빌드 환경에서 직접 호출하여 제슨 나노에서도 지연 없는 한국어 인식을 수행합니다.
* **고품질 TTS (Text-to-Speech):** `gTTS`를 통해 구글의 자연스러운 신경망 음성으로 답변을 출력합니다.
* **gRPC 기반 멀티 노드 통신:** 타 노드로 분석 데이터를 송신하는 클라이언트 기능과 Node B(LLM)의 답변을 수신하는 서버 기능을 동시에 수행합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
voice_pipeline/
├── main.py              # 전체 시스템 흐름 제어 (Entry Point)
├── config.py            # 모든 경로, 포트, 임계값 설정 관리
├── audio_processor.py   # VAD 녹음, STT 연동, gTTS 출력 로직
├── emotion_analyzer.py  # 순수 수학 연산을 통한 감정 분석 (No Librosa)
├── network_manager.py   # gRPC 서버(답변 수신) 및 클라이언트(결과 전송)
├── aura.proto           # gRPC 인터페이스 정의 파일
└── dummy_node_b.py      # 시스템 테스트를 위한 Node B(LLM) 더미 클라이언트
