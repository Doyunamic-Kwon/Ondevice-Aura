import pyaudio
import queue
import config

audio_queue = queue.Queue()

def callback(in_data, frame_count, time_info, status):
    audio_queue.put(in_data)
    return (None, pyaudio.paContinue)

def start_stream():
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=config.SAMPLE_RATE,
        input=True,
        frames_per_buffer=config.FRAME_SIZE,
        stream_callback=callback
    )
    stream.start_stream()