import webrtcvad
import numpy as np
import config

vad = webrtcvad.Vad(config.VAD_MODE)

def process_stream(audio_queue):
    buffer = []
    silence_count = 0
    is_speaking = False

    min_samples = int(config.SAMPLE_RATE * config.MIN_CHUNK_SEC)
    max_samples = int(config.SAMPLE_RATE * config.MAX_CHUNK_SEC)

    while True:
        try:
            frame = audio_queue.get()
            if frame is None:
                break

            raw_frame = frame
            if not isinstance(raw_frame, bytes):
                raw_frame = raw_frame.tobytes()

            is_speech = vad.is_speech(raw_frame, config.SAMPLE_RATE)

            if is_speech:
                if not is_speaking:
                    is_speaking = True
                buffer.append(frame)
                silence_count = 0
            else:
                if is_speaking:
                    buffer.append(frame)
                    silence_count += 1

            current_size = len(buffer) * config.FRAME_SIZE

            if is_speaking:
                if silence_count > config.SILENCE_LIMIT and current_size >= min_samples:
                    # Convert frames to numpy array safely
                    yield np.concatenate([np.frombuffer(f, dtype=np.int16) for f in buffer])
                    buffer = []
                    silence_count = 0
                    is_speaking = False

                elif current_size >= max_samples:
                    yield np.concatenate([np.frombuffer(f, dtype=np.int16) for f in buffer])
                    buffer = []
                    silence_count = 0
                    is_speaking = False

        except Exception as e:
            print(f"VAD Error: {e}")