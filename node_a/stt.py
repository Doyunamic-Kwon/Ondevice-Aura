from vosk import Model, KaldiRecognizer
import json
import config
import numpy as np # Add this import if missing

# Load model globally
model = Model(config.VOSK_MODEL_PATH)
rec = KaldiRecognizer(model, config.SAMPLE_RATE)

def transcribe(audio_chunk):
    """
    Fixed logic to handle NumPy arrays safely.
    """
    # FIX: Use .size or 'is None' instead of 'if not audio_chunk'
    if audio_chunk is None or (isinstance(audio_chunk, np.ndarray) and audio_chunk.size == 0):
        return ""

    try:
        # If it's a NumPy array, convert to bytes directly
        if isinstance(audio_chunk, np.ndarray):
            payload = audio_chunk.tobytes()
        elif isinstance(audio_chunk, list):
            payload = b"".join([bytes(f) for f in audio_chunk])
        else:
            payload = bytes(audio_chunk)

        if rec.AcceptWaveform(payload):
            result = json.loads(rec.Result())
        else:
            result = json.loads(rec.PartialResult())
            
        return result.get("text", result.get("partial", ""))

    except Exception as e:
        print(f"[STT ERROR] {e}")
        return ""