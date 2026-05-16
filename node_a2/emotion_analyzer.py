import wave
import numpy as np

def analyze_voice_emotion(wav_path):
    try:
        with wave.open(wav_path, 'rb') as wf:
            y = np.frombuffer(wf.readframes(wf.getparams().nframes), dtype=np.int16).astype(np.float32)
        if len(y) == 0: return 0.0, 0.0, 0.0

        rms = np.sqrt(np.mean(y**2))
        normalized_energy = rms / 32768.0
        zcr = np.mean(np.abs(np.diff(np.sign(y)))) / 2
        high_freq = np.mean(np.abs(np.diff(y))) / (rms + 1e-6)

        arousal = round(max(-1.0, min(1.0, (normalized_energy * 20) + (zcr * 2) - 0.5)), 2)
        valence = round(max(-1.0, min(1.0, (high_freq / 10) - 0.2)), 2)
        conf = round(max(0.0, min(1.0, normalized_energy * 40)), 2)

        return valence, arousal, conf
    except:
        return 0.0, 0.0, 0.0