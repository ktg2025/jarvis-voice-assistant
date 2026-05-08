#!/usr/bin/env python3
"""
Lokale Spracheingabe mit Whisper — kein Google, kein Internet nötig.
Lauscht auf Mikrofon, sendet Text an JARVIS WebSocket.
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
MIN_DURATION = 0.5

print("🎤 Whisper Mikrofon aktiv — spreche mit Jarvis!")
print("   Drücke CTRL+C zum Beenden\n")

ws = None
jarvis_speaking = False  # True while Jarvis plays audio — mutes mic to avoid feedback

def drain_responses():
    """Read and discard server responses to keep the WebSocket buffer clear."""
    global jarvis_speaking
    while True:
        try:
            raw = ws.recv()
            msg = json.loads(raw)
            # Use audio presence as signal that Jarvis is speaking
            if msg.get("audio"):
                jarvis_speaking = True
                import base64
                audio_bytes = len(base64.b64decode(msg["audio"]))
                duration_s = audio_bytes / 16000 + 1.0  # 128kbps MP3 + 1s buffer
                threading.Timer(duration_s, _done_speaking).start()
        except Exception:
            time.sleep(0.1)

def _done_speaking():
    global jarvis_speaking
    jarvis_speaking = False

def connect_ws():
    global ws
    while True:
        try:
            ws = websocket.create_connection("ws://localhost:8340/ws")
            print("✅ Mit JARVIS verbunden")
            # Start response-draining thread for this connection
            t = threading.Thread(target=drain_responses, daemon=True)
            t.start()
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
    """Record until silence detected, skipping while Jarvis is speaking."""
    chunks = []
    silent_chunks = 0
    speaking = False
    chunks_per_second = SAMPLE_RATE // 1024

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=1024) as stream:
        print("🔴 Höre zu...", end='\r')
        while True:
            chunk, _ = stream.read(1024)

            # Ignore mic input while Jarvis is speaking to prevent feedback
            if jarvis_speaking:
                speaking = False
                chunks = []
                silent_chunks = 0
                continue

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

            if len(chunks) > SAMPLE_RATE * 30:
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
