#!/usr/bin/env python3
"""
Lokale Spracheingabe mit Whisper — Push-to-Talk via Browser-Button.
Wartet auf {"type": "ptt"} vom Server, nimmt dann auf und schickt Text zurück.
"""
import whisper
import sounddevice as sd
import numpy as np
import websocket
import json
import threading
import time

MODEL = whisper.load_model("turbo")
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION = 2.0
MAX_DURATION = 30

print("🎤 Whisper PTT aktiv — warte auf Browser-Button...")
print("   CTRL+C zum Beenden\n")

ws = None
ptt_event = threading.Event()

def drain_responses():
    """Listen for PTT triggers and drain audio responses."""
    while True:
        try:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("type") == "ptt":
                ptt_event.set()
        except Exception:
            time.sleep(0.1)

def connect_ws():
    global ws
    while True:
        try:
            ws = websocket.create_connection("ws://localhost:8340/ws")
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
    chunks = []
    silent_chunks = 0
    speaking = False
    chunks_per_second = SAMPLE_RATE // 1024

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=1024) as stream:
        print("🔴 Aufnahme...", end='\r')
        start = time.time()
        while time.time() - start < MAX_DURATION:
            chunk, _ = stream.read(1024)
            volume = np.abs(chunk).mean()

            if volume > SILENCE_THRESHOLD:
                speaking = True
                silent_chunks = 0
                chunks.append(chunk.copy())
            elif speaking:
                chunks.append(chunk.copy())
                silent_chunks += 1
                if silent_chunks > int(SILENCE_DURATION * chunks_per_second):
                    break

    return np.concatenate(chunks, axis=0).flatten() if chunks else None

def transcribe(audio):
    result = MODEL.transcribe(audio, language="de", fp16=False)
    return result["text"].strip()

connect_ws()
print("⏳ Warte auf PTT-Button im Browser...\n")

while True:
    try:
        ptt_event.wait()
        ptt_event.clear()

        audio = record_until_silence()
        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            print("(nichts erkannt)")
            continue

        print("🧠 Erkenne Sprache...", end='\r')
        text = transcribe(audio)
        if text and len(text) > 2:
            send_text(text)
        else:
            print("(nichts erkannt)")

    except KeyboardInterrupt:
        print("\n👋 Whisper beendet")
        break
    except Exception as e:
        print(f"Fehler: {e}")
        time.sleep(1)
