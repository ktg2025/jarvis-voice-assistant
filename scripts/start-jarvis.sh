#!/bin/bash

echo "🤖 JARVIS wird gestartet..."

# Alles beenden was noch läuft
kill $(lsof -ti:8340) 2>/dev/null
pkill -f whisper_mic 2>/dev/null
pkill chromium 2>/dev/null
sleep 1

# PipeWire neu starten
systemctl --user restart pipewire pipewire-pulse
sleep 1

# JARVIS Server starten
cd ~/jarvis-voice-assistant
source venv/bin/activate
python server.py &
echo "⏳ Warte auf Server..."
sleep 4

# Whisper starten
python whisper_mic.py &
sleep 2

# Browser öffnen
chromium http://localhost:8340 &

echo "✅ JARVIS ist bereit!"
wait
