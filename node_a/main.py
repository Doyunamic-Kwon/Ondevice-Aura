import os
import time

# Set env variables first to prevent Jetson Nano core dump
os.environ['GRPC_POLL_STRATEGY'] = 'poll'
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
os.environ['OPENBLAS_CORETYPE'] = 'ARMV8'

import grpc
import aura_pb2
import aura_pb2_grpc

from audio_stream import start_stream, audio_queue
from va_stream import process_stream
from feature import extract_features
from va_model import predict_va
from stt import transcribe

NODE_C_ADDRESS = "192.168.0.51:5052"

def main():
    print("Voice pipeline started.")

    options = [('grpc.enable_http_proxy', 0)]
    channel = grpc.insecure_channel(NODE_C_ADDRESS, options=options)
    stub = aura_pb2_grpc.AuraPerceptionStub(channel)
    
    start_stream()
    print("Microphone is listening...")

    frame_id = 0

    try:
        for chunk in process_stream(audio_queue):
            print(f"\n--- Frame {frame_id} ---")

            # 1. Get Text
            text_out = transcribe(chunk)
            display_text = text_out if text_out else "No_Text"
            
            # 2. Get VA
            features = extract_features(chunk)
            va_data = predict_va(features)
            
            v_val = float(va_data.get('valence', 0.0))
            a_val = float(va_data.get('arousal', 0.0))
            
            print(f"Text: {display_text}")
            print(f"VA: {v_val:.2f}, {a_val:.2f}")

            # 3. Build Packet safely
            candidate = aura_pb2.EmotionCandidate()
            candidate.source = "voice"
            candidate.emotion_label = "voice_integrated"
            candidate.valence = v_val
            candidate.arousal = a_val
            candidate.confidence = 0.9
            
            if hasattr(candidate, 'text'):
                # Force ascii to avoid serialization crash
                candidate.text = str(display_text).encode('utf-8', 'ignore').decode('utf-8')
            
            # 4. Send with pauses to protect CPU
            try:
                time.sleep(0.1)
                stub.SendFacePerception(candidate, timeout=5)
                print("Send success")
                time.sleep(0.2)
            except Exception as e:
                print(f"Send fail: {e}")

            frame_id += 1

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print(f"System error: {e}")
    finally:
        channel.close()
        print("Closed.")

if __name__ == "__main__":
    main()