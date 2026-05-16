# config.py

SAMPLE_RATE = 16000
FRAME_SIZE = 320  # 20ms frame
VAD_MODE = 1      # 0 to 3 (3 is most aggressive)

MIN_CHUNK_SEC = 1.0
MAX_CHUNK_SEC = 5.0
SILENCE_LIMIT = 15

# Path to your vosk model folder
VOSK_MODEL_PATH = "vosk-model-small-ko-0.22"