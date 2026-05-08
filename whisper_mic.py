#!/usr/bin/env python3
"""
Lokale Spracheingabe mit Whisper — Always-on.
Mikrofon wird stummgeschaltet solange Browser Audio abspielt (audio_start/audio_end Signale).
"""
import whisper
import sounddevice as sd
import numpy as np
import websocket
import json
import threading
import time

MODEL = whisper.load_model("turbo")
SAMPLE_RATE      = 16000
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION  = 2.0
MIN_DURATION      = 0.5
MAX_DURATION      = 30

print("🎤 Whisper aktiv — Jarvis hört immer zu")
print("   CTRL+C zum Beenden\n")

ws            = None
audio_playing = 0          # incremented on audio_start, decremented on audio_end
lock          = threading.Lock()

def is_muted():
    return audio_playing > 0

def drain_responses():
    global audio_playing
    while True:
        try:
            msg = json.loads(ws.recv())
            t   = msg.get("type")
            if t == "audio_start":
                with lock:
                    audio_playing += 1
                # Fallback: unmute after duration even if audio_end never arrives
                duration = float(msg.get("duration", 10))
                threading.Timer(duration, _force_unmute_one).start()
            elif t == "audio_end":
                with lock:
                    audio_playing = max(0, audio_playing - 1)
        except Exception:
            time.sleep(0.1)

def _force_unmute_one():
    global audio_playing
    with lock:
        audio_playing = max(0, audio_playing - 1)

def connect_ws():
    global ws, audio_playing
    while True:
        try:
            ws = websocket.create_connection("ws://localhost:8340/ws")
            with lock:
                audio_playing = 0   # reset on reconnect
            print("✅ Mit JARVIS verbunden")
            threading.Thread(target=drain_responses, daemon=True).start()
            break
        except Exception:
            print("⏳ Warte auf JARVIS Server...")
            time.sleep(2)

def send_text(text):
    global ws
    try:
        ws.send(json.dumps({"text": text}))
        print(f"  Du: {text}")
    except Exception:
        print("  Verbindung verloren, reconnecting...")
        connect_ws()

def record_until_silence():
    chunks        = []
    silent_chunks = 0
    speaking      = False
    cps           = SAMPLE_RATE // 1024

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=1024) as stream:
        print("🟢 Höre zu...", end='\r')
        start = time.time()
        while time.time() - start < MAX_DURATION + 120:
            chunk, _ = stream.read(1024)

            if is_muted():
                chunks        = []
                silent_chunks = 0
                speaking      = False
                continue

            volume = np.abs(chunk).mean()

            if volume > SILENCE_THRESHOLD:
                speaking      = True
                silent_chunks = 0
                chunks.append(chunk.copy())
            elif speaking:
                chunks.append(chunk.copy())
                silent_chunks += 1
                if silent_chunks > int(SILENCE_DURATION * cps):
                    break

            if len(chunks) > SAMPLE_RATE * MAX_DURATION:
                break

    return np.concatenate(chunks, axis=0).flatten() if chunks else None

def transcribe(audio):
    result = MODEL.transcribe(audio, language="de", fp16=False)
    return result["text"].strip()

connect_ws()

while True:
    try:
        audio = record_until_silence()
        if audio is None or len(audio) < SAMPLE_RATE * MIN_DURATION:
            continue

        print("🧠 Erkenne Sprache...", end='\r')
        text = transcribe(audio)

        if text and len(text) > 2:
            send_text(text)

    except KeyboardInterrupt:
        print("\n👋 Whisper beendet")
        break
    except Exception as e:
        print(f"Fehler: {e}")
        time.sleep(1)
