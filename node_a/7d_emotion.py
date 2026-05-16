import cv2
import mediapipe as mp
import math
import time
import grpc
import os
from gtts import gTTS
from concurrent import futures

import aura_pb2
import aura_pb2_grpc

# 1. Target destination (Node C)
target_ip = '192.168.0.51:5052'
channel = grpc.insecure_channel(target_ip)
doyun_stub = aura_pb2_grpc.AuraPerceptionStub(channel)

# 2. TTS Output Function
def play_voice(text):
    if not text: 
        return
    print(f"\n[TTS] {text}")
    try:
        tts = gTTS(text=text, lang='ko')
        tts.save("response.mp3")
        os.system("mpg123 -q response.mp3")
    except Exception as e:
        print(f"TTS Error: {e}")

# 3. Voice Receiver Server Class (From Node B)
class VoiceReceiver(aura_pb2_grpc.AuraPerceptionServicer):
    def SendVoicePerception(self, request, context):
        print("!!! DATA HIT THE SERVER !!!")
        print(f"\n[Voice Received] Text: {request.text} | V:{request.valence} A:{request.arousal}")
        try:
            # Forward data to Node C
            response = doyun_stub.SendVoicePerception(request)
            
            # Play TTS if response exists
            if response.text:
                play_voice(response.text)
                
            return response
            
        except grpc.RpcError as e:
            print(f"Forwarding Failed: {e.details()}")
            return aura_pb2.EmpathyResponse()

# 4. MediaPipe Face Mesh Setup
face_mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=False)

def calculate_va(landmarks):
    f_left = landmarks[234]
    f_right = landmarks[454]
    f_width = math.hypot(f_left.x - f_right.x, f_left.y - f_right.y)
    
    m_left = landmarks[61]
    m_right = landmarks[291]
    m_top = landmarks[13]
    m_bottom = landmarks[14]
    
    e_top = landmarks[159]
    e_bottom = landmarks[145]

    w = math.hypot(m_left.x - m_right.x, m_left.y - m_right.y) / f_width
    o = math.hypot(m_top.x - m_bottom.x, m_top.y - m_bottom.y) / f_width
    e = math.hypot(e_top.x - e_bottom.x, e_top.y - e_bottom.y) / f_width

    v = round(max(-1.0, min(1.0, (w - 0.45) * 5.0)), 2)
    a = round(max(0.0, min(1.0, (e + o) * 2.5)), 2)
    
    if v > 0.3:
        label = "happy"
    elif v < -0.3:
        label = "sad"
    else:
        label = "neutral"
        
    return v, a, label

def main():
    # Open local server on port 50051
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    aura_pb2_grpc.add_AuraPerceptionServicer_to_server(VoiceReceiver(), server)
    server.add_insecure_port('[::]:5051')
    server.start()
    print("--- [Hub Started] Port 5051 opened successfully ---")

    # Camera Setup
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    last_label = ""
    last_v = 0.0
    last_a = 0.0
    threshold = 0.15 
    frame_count = 0

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: 
                break

            # Analyze 1 out of 10 frames
            if frame_count % 10 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = face_mesh.process(rgb)

                if res.multi_face_landmarks:
                    for landmarks in res.multi_face_landmarks:
                        v, a, label = calculate_va(landmarks.landmark)
                        
                        v_diff = abs(v - last_v)
                        a_diff = abs(a - last_a)

                        # Send only when threshold is exceeded
                        if label != last_label or v_diff > threshold or a_diff > threshold:
                            candidate = aura_pb2.EmotionCandidate(
                                source="face", 
                                emotion_label=label,
                                valence=v, 
                                arousal=a, 
                                confidence=0.9
                            )
                            try:
                                response = doyun_stub.SendFacePerception(candidate)
                                print(f"[Face Sent] {label} V:{v} A:{a}")
                                
                                if response.text:
                                    play_voice(response.text)
                                
                                last_label = label
                                last_v = v
                                last_a = a
                            except grpc.RpcError:
                                pass
                                
            frame_count += 1
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nShutting down program...")
    finally:
        cap.release()
        server.stop(0)

if __name__ == "__main__":
    main()