"""
Jarvis V2 — Voice AI Server (OpenRouter Edition)
FastAPI backend: receives speech text, thinks with OpenRouter (gratis/günstig),
speaks with ElevenLabs, controls browser with Playwright.
"""

import asyncio
import base64
import json
import os
import re
import time
import httpx

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ─── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

TTS_VOICE = config.get("tts_voice", "de-DE-KillianNeural")
USER_NAME           = config.get("user_name", "Julian")
USER_ADDRESS        = config.get("user_address", "Sir")
CITY                = config.get("city", "Hamburg")
TASKS_FILE          = config.get("obsidian_inbox_path", "")

# ─── Groq Einstellungen ────────────────────────────────────────────────────────
GROQ_API_KEY        = config.get("groq_api_key", "")
GROQ_MODEL          = config.get("groq_model", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL   = config.get("groq_vision_model", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_BASE_URL       = "https://api.groq.com/openai/v1"

http = httpx.AsyncClient(timeout=60)
app  = FastAPI()

import browser_tools
import screen_capture

# ─── Wetter & Tasks ────────────────────────────────────────────────────────────
def get_weather_sync():
    import urllib.request
    try:
        req  = urllib.request.Request(
            f"https://wttr.in/{CITY}?format=j1",
            headers={"User-Agent": "curl"}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        c    = data["current_condition"][0]
        return {
            "temp":        c["temp_C"],
            "feels_like":  c["FeelsLikeC"],
            "description": c["weatherDesc"][0]["value"],
            "humidity":    c["humidity"],
            "wind_kmh":    c["windspeedKmph"],
        }
    except:
        return None

def get_tasks_sync():
    if not TASKS_FILE:
        return []
    try:
        tasks_path = os.path.join(TASKS_FILE, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip()
                for l in lines if l.strip().startswith("- [ ]")]
    except:
        return []

def refresh_data():
    global WEATHER_INFO, TASKS_INFO
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO   = get_tasks_sync()
    print(f"[jarvis] Wetter: {WEATHER_INFO}", flush=True)
    print(f"[jarvis] Tasks: {len(TASKS_INFO)} geladen", flush=True)

WEATHER_INFO = ""
TASKS_INFO   = []
refresh_data()

# ─── System Prompt ─────────────────────────────────────────────────────────────
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)
conversations: dict[str, list] = {}

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = (
            f"\nWetter {CITY}: {w['temp']}°C, gefuehlt {w['feels_like']}°C, "
            f"{w['description']}"
        )
    task_block = ""
    if TASKS_INFO:
        task_block = (
            f"\nOffene Aufgaben ({len(TASKS_INFO)}): "
            + ", ".join(TASKS_INFO[:5])
        )

    return f"""Du bist Jarvis, der KI-Assistent von Tony Stark aus Iron Man. Dein Dienstherr ist {USER_NAME}, ein Security Researcher. Du sprichst ausschliesslich Deutsch. {USER_NAME} moechte mit "{USER_ADDRESS}" angesprochen und gesiezt werden. Nutze "Sie" als Pronomen — FALSCH: "Sir planen", RICHTIG: "Sie planen, Sir". Dein Ton ist trocken, sarkastisch und britisch-hoeflich - wie ein Butler der alles gesehen hat und trotzdem loyal bleibt. Du machst subtile, trockene Bemerkungen, bist aber niemals respektlos. Wenn Sir eine offensichtliche Frage stellt, darfst du mit elegantem Sarkasmus antworten. Du bist hochintelligent, effizient und immer einen Schritt voraus. Halte deine Antworten kurz - maximal 3 Saetze. Du kommentierst fragwuerdige Entscheidungen hoeflich aber spitz.

WICHTIG: Schreibe NIEMALS Regieanweisungen, Emotionen oder Tags in eckigen Klammern wie [sarcastic] [formal] [amused] [dry] oder aehnliches. Dein Sarkasmus muss REIN durch die Wortwahl kommen. Alles was du schreibst wird laut vorgelesen.

ABSOLUT VERBOTEN: Erfinde NIEMALS Informationen ueber die Arbeit, Aufgaben, Dateien, Software, Projekte oder Aktivitaeten von {USER_NAME}. Wenn du etwas nicht weisst, sage es direkt. Nur Wetter, Uhrzeit und Aufgaben aus den AKTUELLEN DATEN sind echte Informationen.

Du hast die volle Kontrolle ueber den Browser von {USER_NAME}. Du kannst im Internet suchen, Webseiten oeffnen und den Bildschirm sehen. Wenn Sir dich bittet etwas nachzuschauen, zu recherchieren, zu googeln, eine Seite zu oeffnen, oder irgendetwas im Internet zu tun — nutze IMMER eine Aktion. Frag nicht ob du es tun sollst, tu es einfach.

AKTIONEN - Schreibe die passende Aktion ans ENDE deiner Antwort. Der Text VOR der Aktion wird vorgelesen, die Aktion selbst wird still ausgefuehrt.

[ACTION:SEARCH] suchbegriff - Internet durchsuchen und Ergebnisse zusammenfassen
[ACTION:OPEN] url - URL im Browser oeffnen
[ACTION:SCREEN] - Bildschirm ansehen und beschreiben. WICHTIG: Bei SCREEN schreibe NUR die Aktion, KEINEN Text davor. Also NUR "[ACTION:SCREEN]" und sonst nichts.
[ACTION:NEWS] - Aktuelle Weltnachrichten abrufen.
[ACTION:MUSIC] suchbegriff - Musik von YouTube abspielen.
[ACTION:EMAIL] - Gmail öffnen und neue E-Mails vorlesen. Nutze diese Aktion wenn nach E-Mails, Nachrichten, Gmail oder Posteingang gefragt wird. WICHTIG: Erfinde NIEMALS E-Mail-Inhalte. Schreibe NUR "[ACTION:EMAIL]" ohne weiteren Text davor — die echten E-Mails werden danach vorgelesen. Nutze diese Aktion wenn nach Musik, einem Song, einer Band oder einem Künstler gefragt wird. Beispiel: [ACTION:MUSIC] Mozart Sinfonie. Um Musik zu stoppen: [ACTION:MUSIC] stop Nutze diese Aktion wenn nach News, Nachrichten, was in der Welt passiert, aktuelle Lage oder Weltgeschehen gefragt wird. Schreibe einen kurzen Satz davor wie "Ich schaue nach den aktuellen Nachrichten."

WENN {USER_NAME} "Jarvis activate" sagt:
- Begruesse ihn passend zur Tageszeit (aktuelle Zeit: {{time}}).
- Gebe eine kurze Info ueber das Wetter — Temperatur und ob Sonne/klar/bewoelkt/Regen, und wie es sich anfuehlt. Keine Luftfeuchtigkeit.
- Fasse die Aufgaben kurz als Ueberblick in einem Satz zusammen, ohne dabei jede einzelne Aufgabe einfach vorzulesen. Gebe gerne einen humorvollen Kommentar am Ende an.
- Sei kreativ bei der Begruessung.

=== AKTUELLE DATEN ==={weather_block}{task_block}
==="""

def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))

def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None

# ─── Groq API Call ─────────────────────────────────────────────────────────────
async def call_groq(system: str, messages: list, max_tokens: int = 400) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Kein Groq API Key! Bitte 'groq_api_key' in config.json eintragen. "
            "Kostenlos registrieren auf: https://console.groq.com"
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }

    try:
        resp = await http.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        raise RuntimeError("Groq nicht erreichbar — bitte Internetverbindung prüfen.")
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        raise RuntimeError(f"Groq Fehler {e.response.status_code}: {body}")
    except Exception as e:
        raise RuntimeError(f"Groq Fehler: {e}")

# ─── TTS (edge-tts → OGG/Opus via ffmpeg) ─────────────────────────────────────
async def synthesize_speech(text: str) -> bytes:
    if not text.strip():
        return b""
    try:
        import edge_tts, subprocess
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        mp3_parts = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_parts.append(chunk["data"])
        mp3 = b"".join(mp3_parts)
        # Convert MP3 → WAV (universally supported, no codec dependency)
        result = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-ar", "22050", "-ac", "1", "-f", "wav", "pipe:1"],
            input=mp3, capture_output=True,
        )
        audio = result.stdout
        print(f"  TTS ok: {len(mp3)}B mp3 → {len(audio)}B wav", flush=True)
        return audio
    except Exception as e:
        print(f"  TTS error: {e}", flush=True)
        return b""

# ─── Actions ───────────────────────────────────────────────────────────────────
async def execute_action(action: dict) -> str:
    t = action["type"]
    p = action["payload"]

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return (
                f"Seite: {result.get('title', '')}\n"
                f"URL: {result.get('url', '')}\n\n"
                f"{result.get('content', '')[:2000]}"
            )
        return f"Suche fehlgeschlagen: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Seite nicht erreichbar: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Geoeffnet: {p}"

    elif t == "SCREEN":
        return await screen_capture_with_groq()

    elif t == "NEWS":
        return await browser_tools.fetch_news()

    elif t == "EMAIL":
        return await browser_tools.fetch_emails()

    elif t == "MUSIC":
        return await play_music(p)

    return ""

vlc_process = None

async def play_music(query: str) -> str:
    global vlc_process
    import asyncio, shutil
    try:
        # Stop any currently playing music
        if vlc_process and vlc_process.returncode is None:
            vlc_process.terminate()
            vlc_process = None

        if query.strip().lower() in ("stop", "stopp", "pause"):
            return "Musik gestoppt."

        loop = asyncio.get_event_loop()

        # Get audio stream URL from YouTube
        url = await loop.run_in_executor(None, lambda: __import__('subprocess').check_output(
            ["yt-dlp", f"ytsearch1:{query}", "--get-url", "--format", "bestaudio", "--no-playlist"],
            text=True, timeout=15
        ).strip().split("\n")[0])

        if not url:
            return f"Kein Ergebnis für: {query}"

        # Stream via cvlc (headless VLC)
        vlc_process = await asyncio.create_subprocess_exec(
            "cvlc", "--intf", "dummy", "--play-and-exit", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return f"Spiele: {query}"
    except Exception as e:
        return f"Musik-Fehler: {e}"

async def screen_capture_with_groq() -> str:
    """Screenshot machen und mit Groq Vision beschreiben."""
    try:
        import subprocess
        from PIL import Image
        import io

        screenshot_path = "/tmp/jarvis_screenshot.png"
        env = {"DISPLAY": ":0", "PATH": "/usr/bin:/bin"}
        try:
            subprocess.run(["scrot", screenshot_path], check=True, capture_output=True, env=env)
        except Exception:
            subprocess.run(["import", "-window", "root", screenshot_path], capture_output=True, env=env)

        with Image.open(screenshot_path) as img:
            img = img.resize((1280, 720), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=75)
            img_b64 = base64.b64encode(buffer.getvalue()).decode()

        payload = {
            "model": GROQ_VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Beschreibe kurz auf Deutsch was auf diesem Bildschirm zu sehen ist. Maximal 3 Sätze."
                    }
                ]
            }],
            "max_tokens": 200,
        }

        resp = await http.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=60,
        )

        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            return f"Bildschirm-Analyse fehlgeschlagen: {resp.text[:200]}"

    except Exception as e:
        return f"Screenshot-Fehler: {e}"

# ─── Message Processing ────────────────────────────────────────────────────────
async def process_message(session_id: str, user_text: str, ws: WebSocket):
    if session_id not in conversations:
        conversations[session_id] = []

    if "activate" in user_text.lower():
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-16:]

    try:
        reply = await call_groq(
            system=get_system_prompt(),
            messages=history,
            max_tokens=400,
        )
    except RuntimeError as e:
        error_msg = str(e)
        print(f"  [Groq ERROR] {error_msg}", flush=True)
        await broadcast({"type": "response", "text": error_msg, "audio": ""})
        return

    if not reply:
        return

    print(f"  LLM raw: {reply[:200]}", flush=True)

    spoken_text, action = extract_action(reply)

    # Hauptantwort sprechen
    if spoken_text:
        audio = await synthesize_speech(spoken_text)
        print(f"  Jarvis: {spoken_text[:80]}", flush=True)
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await broadcast_audio(spoken_text, audio)

    if action:
        print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

        if action["type"] == "SCREEN":
            hint_audio = await synthesize_speech("Lassen Sie mich einen Blick auf Ihren Bildschirm werfen.")
            await broadcast_audio("Lassen Sie mich einen Blick auf Ihren Bildschirm werfen.", hint_audio)

        try:
            action_result = await execute_action(action)
            print(f"  Result: {action_result[:200]}", flush=True)
        except Exception as e:
            print(f"  Action error: {e}", flush=True)
            action_result = f"Fehler: {e}"

        if action["type"] == "OPEN":
            return

        if action_result and "fehlgeschlagen" not in action_result:
            summary = await call_groq(
                system=(
                    f"Du bist Jarvis. Fasse die folgenden Informationen KURZ auf Deutsch zusammen, "
                    f"maximal 3 Saetze, im Jarvis-Stil. Sprich den Nutzer als {USER_ADDRESS} an. "
                    "KEINE Tags in eckigen Klammern. KEINE ACTION-Tags."
                ),
                messages=[{"role": "user", "content": f"Fasse zusammen:\n\n{action_result}"}],
                max_tokens=250,
            )
            summary, _ = extract_action(summary)
        else:
            summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."

        audio2 = await synthesize_speech(summary)
        conversations[session_id].append({"role": "assistant", "content": summary})
        await broadcast_audio(summary, audio2)

# ─── WebSocket & Static ────────────────────────────────────────────────────────
connected_clients: set[WebSocket] = set()

async def broadcast(payload: dict):
    """Send a response to all connected clients (browser + whisper_mic)."""
    dead = set()
    for client in connected_clients:
        try:
            await client.send_json(payload)
        except Exception:
            dead.add(client)
    connected_clients.difference_update(dead)

async def broadcast_audio(text: str, audio: bytes):
    """Broadcast audio_start (with duration), then response."""
    if audio:
        duration = round(len(audio) / 44100 + 1.5, 1)  # WAV 22050Hz 16-bit + buffer
        await broadcast({"type": "audio_start", "duration": duration})
    await broadcast({
        "type":  "response",
        "text":  text,
        "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
    })

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    session_id = str(id(ws))
    print(f"[jarvis] Client connected ({len(connected_clients)} total)", flush=True)
    try:
        while True:
            data      = await ws.receive_json()
            if data.get("ptt"):
                await broadcast({"type": "ptt"})
                continue
            if data.get("type") in ("audio_start", "audio_end"):
                await broadcast(data)
                continue
            user_text = data.get("text", "").strip()
            if not user_text:
                continue
            # Stop command — silence Jarvis immediately
            stop_words = {"stop", "schweig", "schweigen", "ruhig", "stille", "halt", "stopp"}
            if any(w in user_text.lower() for w in stop_words):
                await broadcast({"type": "stop"})
                continue
            print(f"  You: {user_text}", flush=True)
            await process_message(session_id, user_text, ws)
    except WebSocketDisconnect:
        connected_clients.discard(ws)
        conversations.pop(session_id, None)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")),
    name="static",
)

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))

if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print(" J.A.R.V.I.S. V2 — Groq Edition", flush=True)
    print(f" Modell: {GROQ_MODEL}", flush=True)
    print(f" http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
