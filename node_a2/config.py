import os

class Config:
    # 경로 설정
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WHISPER_MAIN_PATH = "/home/ys9072/voice_pipeline/whisper.cpp/build/bin/whisper-cli"
    WHISPER_MODEL_PATH = "/home/ys9072/voice_pipeline/whisper.cpp/models/ggml-tiny.bin"
    RECORD_FILE = "/dev/shm/temp_input.wav"

    # 오디오 설정
    SAMPLE_RATE = 16000
    VAD_THRESHOLD = 0.1
    SILENCE_DURATION = 1.5

    # 네트워크 설정
    FACE_NODE_TARGET = "192.168.0.34:5051"
    MY_TTS_SERVER_PORT = "5050"