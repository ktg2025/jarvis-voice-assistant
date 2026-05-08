#!/usr/bin/env python3
"""
Lokale Spracheingabe mit Whisper — Always-on mit Stummschaltung während Jarvis spricht.
"""
import whisper
import sounddevice as sd
import numpy as np
import websocket
import json
import threading
import base64
import time

MODEL = whisper.load_model("turbo")
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION  = 2.0
MIN_DURATION      = 0.5
MAX_DURATION      = 30

print("🎤 Whisper aktiv — Jarvis hört immer zu")
print("   CTRL+C zum Beenden\n")

ws            = None
pending_audio = 0          # audio chunks still playing in browser
mute_lock     = threading.Lock()

def is_muted():
    return pending_audio > 0

def drain_responses():
    """Drain server responses; track audio playback to mute mic."""
    global pending_audio
    while True:
        try:
            raw = ws.recv()
            msg = json.loads(raw)
            # PTT trigger from browser — ignore (not needed in always-on mode)
            if msg.get("type") == "ptt":
                continue
            audio_b64 = msg.get("audio", "")
            if audio_b64:
                audio_bytes = len(base64.b64decode(audio_b64))
                duration_s  = audio_bytes / 44100 + 2.0  # WAV 22050Hz 16-bit mono + 2s buffer
                with mute_lock:
                    pending_audio += 1
                threading.Timer(duration_s, _chunk_done).start()
        except Exception:
            time.sleep(0.1)

def _chunk_done():
    global pending_audio
    with mute_lock:
        pending_audio = max(0, pending_audio - 1)

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
    """Record until silence, muted while Jarvis is speaking."""
    chunks        = []
    silent_chunks = 0
    speaking      = False
    cps           = SAMPLE_RATE // 1024  # chunks per second

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=1024) as stream:
        print("🟢 Höre zu...", end='\r')
        start = time.time()
        while time.time() - start < MAX_DURATION + 60:
            chunk, _ = stream.read(1024)

            if is_muted():
                # Reset any in-progress recording while Jarvis speaks
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
