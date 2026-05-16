# Ondevice-Aura: Node A (Face Perception & Data Hub Module)

본 저장소는 **Ondevice-Aura** 프로젝트의 **Node A (영상 감정 인식 파이프라인 및 분산 데이터 허브)** 모듈입니다. NVIDIA Jetson Nano 에지 디바이스 환경에 최적화되어 있으며, 실시간 Face Mesh 분석을 통한 감정 벡터 추출 및 타 노드(Node B)의 음성 데이터를 중앙 서버(Node C)로 안전하게 중계하는 허브 역할을 수행합니다.

---

## 🛠️ 주요 기능 (Key Features)

### 1. 실시간 Face Mesh 기반 감정 추출 및 맞춤 튜닝
* **MediaPipe Face Mesh:** 얼굴 고유의 랜드마크 좌표 변화를 실시간 트래킹합니다.
* **Valence-Arousal 사분면 알고리즘:** 랜드마크 간 유클리드 거리를 연산하여 감정의 긍정/부정 수치($V$)와 각성도($A$)를 실시간 좌표계로 매핑하고 7가지 핵심 감정 상태(`happy`, `sad`, `angry`, `relaxed`, `surprised`, `tired`, `neutral`)를 분류합니다.
* **한국어/동양인 무표정 오인식 보정:** 기존 오픈소스 모델들이 평균 무표정을 'Sad'로 과도하게 판별하는 한계를 극복하기 위해, 기하학적 기준 파라미터(Valence Offset)를 `0.45`에서 `0.38`로 완화 보정하여 무표정에서의 안정적인 `Neutral` 상태를 확보했습니다.

### 2. 분산 컴퓨팅 기반 gRPC 데이터 허브 및 포워딩
* **로컬 통신 서버 가동 (Port 5051):** 오디오 파트(Node B)가 전송하는 실시간 STT 텍스트 및 오디오 감정 수치를 안정적으로 청취(Listen)합니다.
* **멀티홉 포워딩 메커니즘:** Node B로부터 수신한 음성 데이터와 자체 추출한 얼굴 표정 벡터를 실시간 통합하여 중앙 인퍼런스 서버(Node C: `192.168.0.51:5052`)로 고속 라우팅합니다.
* **네트워크 병목 및 블로킹 방지:** 분산 네트워크 지연에 따른 메인 루프 데드락을 차단하기 위해 모든 gRPC 전송 파이프라인에 15초 타임아웃 예외 처리(`timeout=15`)를 기본 적용했습니다.

### 3. 에지 환경 자원 최적화 설계 (Edge Optimization)
* **프레임 다운샘플링 (Frame Skip):** Jetson Nano의 한정된 자원을 보호하기 위해 영상 입력 스트림의 10프레임당 1번만 Face Mesh 추론 가동(`frame_count % 10 == 0`)을 수행하여 CPU 오버헤드를 약 90% 급감시켰습니다.
* **임계값 기반 트래픽 필터링 (Thresholding):** 미세한 노이즈로 인한 패킷 낭비를 방지하기 위해, 직전 전송 값 대비 $V, A$ 수치 변동량이 임계값 `0.25`를 초과하거나 감정 라벨이 변경될 때만 전송 트리거가 발생하도록 설계했습니다.

### 4. 실시간 모니터링 HUD 및 안정적 종료 (Graceful Shutdown)
* **OpenCV HUD 오버레이:** 시연 및 디버깅 가시성을 극대화하기 위해 카메라 팝업 윈도우 좌측 상단에 실시간 감정 라벨과 연산 수치($V, A$)를 실시간 텍스트로 드로잉합니다.
* **자원 반환 보장:** 예기치 못한 인터럽트나 키보드 종료(`q`키 입력) 시, 시스템 소켓 및 V4L2 카메라 장치 바인딩을 깨끗하게 해제하고 종료하는 `try-finally` 자원 반환 아키텍처를 도입했습니다.

---

## 📦 필수 요구 사항 및 의존성 (Prerequisites)

Jetson Nano (ARMv8 아키텍처 / Ubuntu 20.04 LTS / Python 3.10) 배포 버전 사양입니다. 라이브러리 간 버전 충돌을 차단하기 위해 아래 고정 스펙으로 구성해야 합니다.

```bash
# 시스템 멀티미디어 종속성 설치
sudo apt-get update
sudo apt-get install mpg123 portaudio19-dev

# 파이썬 핵심 라이브러리 설치 (버전 락 적용)
pip3 install grpcio grpcio-tools protobuf==4.21.12
pip3 install mediapipe opencv-python gTTS
pip3 install "numpy<2" --force-reinstall