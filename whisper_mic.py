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
SILENCE_THRESHOLD = 0.35
SILENCE_DURATION = 2.0  # Sekunden Stille = Satz fertig
MIN_DURATION = 0.5       # Mindestlänge einer Aufnahme

print("🎤 Whisper Mikrofon aktiv — spreche mit Jarvis!")
print("   Drücke CTRL+C zum Beenden\n")

ws = None

def connect_ws():
    global ws
    while True:
        try:
            ws = websocket.create_connection("ws://localhost:8340/ws")
            print("✅ Mit JARVIS verbunden")
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
    """Nimmt auf bis Stille erkannt wird."""
    chunks = []
    silent_chunks = 0
    speaking = False
    chunks_per_second = SAMPLE_RATE // 1024

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=1024) as stream:
        print("🔴 Höre zu...", end='\r')
        while True:
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
            
            if len(chunks) > SAMPLE_RATE * 30:  # Max 30 Sekunden
                break

    return np.concatenate(chunks, axis=0).flatten() if chunks else None

def transcribe(audio):
    """Whisper transkription."""
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
