import subprocess
import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
from gtts import gTTS
from config import Config

def record_vad():
    """
    VAD(Voice Activity Detection) 기반으로 음성을 감지하여 녹음합니다.
    """
    print("\n👂 듣고 있습니다... (말씀을 시작하세요)")
    audio_frames = []
    is_recording = False
    last_voice_time = time.time()

    # 오디오 입력 스트림 시작
    with sd.InputStream(samplerate=Config.SAMPLE_RATE, channels=1, dtype='float32') as stream:
        while True:
            chunk, _ = stream.read(1024)
            # 음압(RMS) 계산
            rms = np.sqrt(np.mean(chunk**2))
            
            if rms > Config.VAD_THRESHOLD:
                if not is_recording:
                    print("🎤 음성 감지: 녹음 시작")
                    is_recording = True
                audio_frames.append(chunk)
                last_voice_time = time.time()
            else:
                if is_recording:
                    audio_frames.append(chunk)
                    # 설정된 시간(SILENCE_DURATION) 동안 소리가 없으면 종료
                    if time.time() - last_voice_time > Config.SILENCE_DURATION:
                        print("🛑 침묵 감지: 녹음 종료")
                        break
            
            if not is_recording:
                time.sleep(0.01)

    # 녹음 데이터 병합 및 저장 (WAV)
    recording = np.concatenate(audio_frames, axis=0)
    # whisper.cpp 및 분석을 위해 16-bit PCM으로 변환하여 저장
    sf.write(Config.RECORD_FILE, (recording * 32767).astype(np.int16), Config.SAMPLE_RATE)
    return True

def run_stt():
    """
    저장된 WAV 파일을 whisper.cpp를 통해 텍스트로 변환합니다.
    """
    cmd = [
        Config.WHISPER_MAIN_PATH, 
        "-m", Config.WHISPER_MODEL_PATH, 
        "-f", Config.RECORD_FILE, 
        "-nt",      # 텍스트만 출력
        "-l", "ko"  # 한국어 고정
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ STT 실행 에러: {e}")
        return ""

def speak_text(text):
    """
    gTTS를 사용하여 자연스러운 한국어 음성으로 출력합니다. (인터넷 연결 필요)
    """
    if not text:
        return

    print(f"🔊 gTTS 출력 중: {text}")
    temp_file = "response.mp3"
    
    try:
        # 1. gTTS로 텍스트를 음성 데이터로 변환 (한국어)
        tts = gTTS(text=text, lang='ko')
        
        # 2. MP3 파일로 임시 저장
        tts.save(temp_file)
        
        # 3. mpg123 재생기 실행 (-q: 불필요한 로그 출력 방지)
        # 젯슨 나노의 오디오 리소스를 고려해 subprocess로 가볍게 실행
        subprocess.run(["mpg123", "-q", temp_file], check=True)
        
    except Exception as e:
        print(f"❌ TTS 재생 실패: {e}")
        
    finally:
        # 4. 사용이 끝난 임시 파일 삭제
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass