def predict_va(features):
    if not features or len(features) < 2:
        return {"valence": 0.5, "arousal": 0.5}

    rms_energy = features[0]
    zcr_value = features[1]

    # Simple logic mapping
    arousal = min(1.0, rms_energy / 2000.0)
    valence = min(1.0, zcr_value * 10.0)

    return {
        "valence": round(valence, 2),
        "arousal": round(arousal, 2)
    }