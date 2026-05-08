# J.A.R.V.I.S. — Personal AI Voice Assistant

> Speak. Jarvis wakes up, greets you with the weather, answers your questions with dry British wit, controls your browser, and sees your screen.

Built entirely with [Claude Code](https://claude.ai/code) — no code written manually.

---

## Youtube Video

[Demo & Explanation](https://youtu.be/XsceN-hEit4)

---

## Features

- **Local Voice Input** — Whisper runs on your machine, no cloud speech API needed
- **Voice Conversation** — Speak freely with Jarvis. He listens, thinks, and responds with voice
- **Sarcastic British Butler** — Jarvis speaks German with the personality of Tony Stark's AI: dry, witty, and always one step ahead
- **Weather on Startup** — Jarvis greets you with the current weather and a humorous summary
- **Browser Automation** — "Search for X" → Jarvis opens a real browser, navigates, reads the content, and summarizes it
- **Screen Vision** — "Was siehst du?" → Jarvis takes a screenshot, analyzes it with a vision model, and describes what he sees
- **World News** — "Was passiert in der Welt?" → Jarvis fetches Tagesschau and summarizes current events
- **Autostart** — Drops into XDG autostart, launches on every login

---

## Architecture

```
You (speak) → Whisper (local STT) → WebSocket → FastAPI Server (local)
                                                        ↓
                                                  Groq LLM (thinks)
                                                        ↓
                                    ┌───────────────────┼───────────────────┐
                                    ↓                   ↓                   ↓
                              edge-tts (speaks)  Playwright Browser   Screen Capture
                                    ↓             (searches/opens)   (Groq Vision)
                              Audio → Browser → You (hear)
```

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Speech Input | Whisper (local) | Converts your voice to text, no API needed |
| Server | FastAPI (Python) | Local orchestration |
| Brain | Groq — llama-3.3-70b | Fast, free-tier LLM |
| Voice | edge-tts | Free Microsoft TTS, natural German voices |
| Browser Control | Playwright | Automates a real Chromium you can see |
| Screen Vision | Groq Vision | Screenshots and describes your screen |

---

## Prerequisites

- **Linux** (tested on Kali)
- **Python 3.10+**
- **Chromium**

### API Keys Needed

| Service | What For | Cost | Link |
|---------|----------|------|------|
| Groq | LLM brain + vision | Free tier | [console.groq.com](https://console.groq.com) |

No ElevenLabs, no Anthropic key required.

---

## Quick Start

1. **Clone and set up a virtualenv:**
   ```bash
   git clone https://github.com/ktg2025/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install edge-tts
   playwright install chromium
   ```

2. **Create `config.json`** from the template:
   ```bash
   cp config.example.json config.json
   ```

3. **Edit `config.json`** with your details:
   ```json
   {
     "groq_api_key": "gsk_...",
     "groq_model": "llama-3.3-70b-versatile",
     "tts_voice": "de-DE-KillianNeural",
     "user_name": "Your Name",
     "user_address": "Sir",
     "city": "Berlin"
   }
   ```

4. **Start Jarvis:**
   ```bash
   bash scripts/start-jarvis.sh
   ```

5. **Open Chromium** and go to `http://localhost:8340`, click the page, and speak.

---

## Usage

### Start manually
```bash
bash scripts/start-jarvis.sh
```
Starts the FastAPI server, Whisper mic, and opens Chromium.

### Autostart on login (Linux / XDG)
```bash
cp scripts/jarvis.desktop ~/.config/autostart/
```
Jarvis will launch automatically on every graphical login.

---

## What You Can Say

| Command | What Happens |
|---------|-------------|
| *"Jarvis activate"* | Greets you with weather |
| *"Such nach KI-News"* | Opens browser, searches, summarizes |
| *"Öffne github.com"* | Opens the URL in Chromium |
| *"Was siehst du auf meinem Bildschirm?"* | Screenshots and describes |
| *"Was passiert in der Welt?"* | Fetches Tagesschau, summarizes news |
| *Any question* | Jarvis answers in sarcastic butler style |

---

## Project Structure

```
jarvis-voice-assistant/
├── server.py              # FastAPI backend — Groq + edge-tts
├── browser_tools.py       # Playwright browser automation (Linux)
├── screen_capture.py      # Screenshot + Groq Vision
├── whisper_mic.py         # Local Whisper speech recognition
├── config.json            # Your personal config (gitignored)
├── config.example.json    # Template for new users
├── requirements.txt       # Python dependencies
├── frontend/
│   ├── index.html         # Jarvis web UI
│   ├── main.js            # WebSocket + audio playback
│   └── style.css          # Dark theme with animated orb
└── scripts/
    ├── start-jarvis.sh    # Full startup script
    ├── jarvis.desktop     # XDG autostart entry
    └── clap-trigger.py    # Double-clap detection (optional)
```

---

## Customization

### Change the voice
Pick any `edge-tts` voice and set it in `config.json`:
```json
{ "tts_voice": "de-DE-ConradNeural" }
```
List all available voices: `edge-tts --list-voices | grep de-`

### Change the AI model
```json
{ "groq_model": "llama-3.3-70b-versatile" }
```
All Groq models: [console.groq.com/docs/models](https://console.groq.com/docs/models)

### Change Jarvis's personality
Edit the system prompt in `server.py` → `build_system_prompt()`.

### Adjust mic sensitivity
In `whisper_mic.py`:
```python
SILENCE_THRESHOLD = 0.02  # Lower = more sensitive
```

### Change the weather city
```json
{ "city": "Berlin" }
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Jarvis doesn't speak | Check server is running: `curl http://localhost:8340` |
| No audio in browser | Click anywhere on the page first (autoplay policy) |
| Jarvis doesn't hear you | Run the mic level test: `python -c "import sounddevice as sd, numpy as np; d=sd.rec(16000,16000,1,'float32'); sd.wait(); print(np.abs(d).max())"` — if below 0.02, lower `SILENCE_THRESHOLD` |
| Whisper keeps disconnecting | Old server still running on port 8340 — `kill $(lsof -ti:8340)` and restart |
| Browser search fails | `playwright install chromium` |
| Screen capture fails | Install scrot: `sudo apt install scrot` |

---

## Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — Python web framework
- **[Groq](https://groq.com)** — Fast LLM inference (llama-3.3-70b)
- **[edge-tts](https://github.com/rany2/edge-tts)** — Free Microsoft TTS
- **[Whisper](https://github.com/openai/whisper)** — Local speech recognition
- **[Playwright](https://playwright.dev)** — Browser automation
- **[sounddevice](https://python-sounddevice.readthedocs.io/)** — Audio input

---

## Credits

Original template by [Julian](https://skool.com/ki-automatisierung) — [original repo](https://github.com/Julian-Ivanov/jarvis-voice-assistant).

Linux port built with [Claude Code](https://claude.ai/code).

Inspired by Iron Man's J.A.R.V.I.S. — *"At your service, Sir."*

---

## License

MIT — use it, modify it, build on it.
