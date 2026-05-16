import numpy as np

def extract_features(audio_chunk):
    # Check if chunk is empty
    if audio_chunk is None or len(audio_chunk) == 0:
        return [0.0, 0.0]

    # Convert to float32 for math
    data = np.array(audio_chunk, dtype=np.float32)
    
    # Root Mean Square (RMS) for volume
    rms = np.sqrt(np.mean(data**2))
    
    # Zero Crossing Rate (ZCR) for frequency change
    zcr = ((data[:-1] * data[1:]) < 0).sum() / len(data)

    return [float(rms), float(zcr)]