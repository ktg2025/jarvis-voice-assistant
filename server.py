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
USER_NAME           = config.get("user_name", "Daniel")
USER_ADDRESS        = config.get("user_address", "Sir")
USER_ROLE           = config.get("user_role", "CEO von Synaptix Labs")
USER_WEBSITE        = config.get("user_website", "222.synaptixlabs.ch")
CITY                = config.get("city", "Melchnau")
TASKS_FILE          = config.get("obsidian_inbox_path", "")

# ─── LLM Provider Config ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY = config.get("anthropic_api_key", "")
ANTHROPIC_MODEL   = config.get("anthropic_model", "claude-haiku-4-5")
GROQ_API_KEY      = config.get("groq_api_key", "")
GROQ_MODEL        = config.get("groq_model", "llama-3.3-70b-versatile")
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"
GROQ_VISION_MODEL = config.get("groq_vision_model", "meta-llama/llama-4-scout-17b-16e-instruct")
VENICE_API_KEY    = config.get("venice_api_key", "")
VENICE_MODEL      = config.get("venice_model", "llama-3.3-70b")
VENICE_BASE_URL   = "https://api.venice.ai/api/v1"
OLLAMA_URL        = config.get("ollama_url", "http://localhost:11434")
OLLAMA_MODEL      = config.get("ollama_model", "llama3.2:3b")
OPENAI_API_KEY    = config.get("openai_api_key", "")
OPENAI_MODEL      = config.get("openai_model", "gpt-4o-mini")
OPENAI_BASE_URL   = "https://api.openai.com/v1"
HF_API_KEY        = config.get("huggingface_api_key", "")
HF_MODEL          = config.get("huggingface_model", "mistralai/Mixtral-8x7B-Instruct-v0.1")
HF_BASE_URL       = "https://api-inference.huggingface.co/models"

import anthropic as _anthropic
_claude = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Active provider — can be switched at runtime
ACTIVE_PROVIDER = config.get("active_provider", "venice")  # "claude" | "venice" | "groq"

http = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10))
app  = FastAPI()

import browser_tools
import screen_capture
import memory as _memory

_mem = _memory.load_memory()
print(f"[jarvis] Erinnerungen geladen: {_mem.get('interaction_count', 0)} Interaktionen", flush=True)

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
ACTION_PATTERN = re.compile(r'\[\s*(?:ACTION|AKTION)\s*:\s*(\w+)\s*\]\s*(.*?)$', re.DOTALL | re.MULTILINE | re.IGNORECASE)
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

    mem_context = _memory.format_for_prompt(_mem)

    return f"""Du bist Aria, eine hochintelligente KI-Assistentin. Dein Dienstherr ist {USER_NAME}, {USER_ROLE} (Webseite: {USER_WEBSITE}). Du sprichst ausschliesslich Deutsch. {USER_NAME} moechte mit "{USER_ADDRESS}" angesprochen und gesiezt werden. Nutze "Sie" als Pronomen — FALSCH: "Sir planen", RICHTIG: "Sie planen, Sir". Dein Ton ist elegant, selbstbewusst und praezise — mit einem Hauch trockenen Humors. Du bist loyal, effizient und immer einen Schritt voraus. Halte deine Antworten kurz - maximal 3 Saetze.

WICHTIG: Schreibe NIEMALS Regieanweisungen, Emotionen oder Tags in eckigen Klammern wie [sarcastic] [formal] [amused] [dry] oder aehnliches. Dein Sarkasmus muss REIN durch die Wortwahl kommen. Alles was du schreibst wird laut vorgelesen.

ABSOLUT VERBOTEN: Erfinde NIEMALS Informationen. Reagiere AUSSCHLIESSLICH auf die LETZTE Nachricht des Nutzers — ignoriere vorherige Konversation für Aktionen vollständig. Führe NUR Aktionen aus die explizit in der letzten Nachricht angefragt wurden. Wenn der Nutzer nach X fragt, tu NUR X — nichts anderes, nichts zusätzliches.

Du hast die volle Kontrolle ueber den Browser von {USER_NAME}. Du kannst im Internet suchen, Webseiten oeffnen und den Bildschirm sehen. Wenn Sir dich bittet etwas nachzuschauen, zu recherchieren, zu googeln, eine Seite zu oeffnen, oder irgendetwas im Internet zu tun — nutze IMMER eine Aktion. Frag nicht ob du es tun sollst, tu es einfach.

AKTIONEN - Schreibe die passende Aktion ans ENDE deiner Antwort. Der Text VOR der Aktion wird vorgelesen, die Aktion selbst wird still ausgefuehrt.

KRITISCHE REGEL FUER ALLE AKTIONEN: Der Text nach dem Aktions-Tag muss EXAKT das sein was der Nutzer gesagt hat — WORT FUER WORT. NIEMALS eigene Woerter hinzufuegen, uebersetzen, erweitern oder veraendern. Wenn Sir "suche nach Python" sagt → [ACTION:SEARCH] Python. NICHT [ACTION:SEARCH] Python Programmierung Tutorial. NICHT [ACTION:SEARCH] Kali Linux Python.

[ACTION:SEARCH] exakter-suchbegriff - Internet durchsuchen mit EXAKT den Woertern des Nutzers. Fuer Wikipedia: [ACTION:SEARCH] site:wikipedia.org exakter-begriff
[ACTION:OPEN] exakte-url - URL im Browser oeffnen — EXAKT die URL die der Nutzer nannte
[ACTION:SCREEN] - Bildschirm ansehen und beschreiben. NUR verwenden wenn der Nutzer EXPLIZIT fragt was auf dem Bildschirm zu sehen ist. NIEMALS automatisch oder ungefragt ausführen.
[ACTION:NEWS]              - Aktuelle Weltnachrichten (Tagesschau). NUR verwenden wenn der Nutzer EXPLIZIT nach Nachrichten, News oder aktuellen Ereignissen fragt. NIEMALS automatisch.
[ACTION:EMAIL]             - Gmail Posteingang lesen. NIEMALS Inhalte erfinden.
[ACTION:MUSIC] exakt       - Musik auf YouTube abspielen. EXAKT was der Nutzer sagte: z.B. Sir sagt "spiel Rammstein Du Hast" → [ACTION:MUSIC] Rammstein Du Hast
[ACTION:VIDEO] exakt       - YouTube-Video in Firefox oeffnen. EXAKT was der Nutzer sagte.
[ACTION:MOVIE] suchbegriff - Filme auf NeueFlix auflisten
[ACTION:PLAY]  filmtitel   - Film auf NeueFlix abspielen. EXAKT der Titel.
[ACTION:TV]    sendername  - Deutsche IPTV-Sender in VLC. Ohne Name = Senderliste. [ACTION:TV] stop zum Beenden.
[ACTION:TOR]   url         - Tor Browser starten (URL optional)
[ACTION:SHELL] befehl      - Shell-Befehl ausfuehren. EXAKT was der Nutzer will, z.B. [ACTION:SHELL] sudo apt update
[ACTION:TASK]  aufgabe1, aufgabe2 - Aufgabenliste in LibreOffice erstellen

WENN {USER_NAME} "Aria activate" oder "Jarvis activate" sagt:
- Begruesse ihn passend zur Tageszeit (aktuelle Zeit: {{time}}).
- Gebe eine kurze Info ueber das Wetter — Temperatur und ob Sonne/klar/bewoelkt/Regen, und wie es sich anfuehlt. Keine Luftfeuchtigkeit.
- Fasse die Aufgaben kurz als Ueberblick in einem Satz zusammen, ohne dabei jede einzelne Aufgabe einfach vorzulesen. Gebe gerne einen humorvollen Kommentar am Ende an.
- Sei kreativ bei der Begruessung.

=== AKTUELLE DATEN ==={weather_block}{task_block}
===

{mem_context}"""

def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))

def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None

# ─── LLM Call (routes to active provider) ─────────────────────────────────────
async def call_groq(system: str, messages: list, max_tokens: int = 400) -> str:
    global ACTIVE_PROVIDER
    loop = asyncio.get_event_loop()

    if ACTIVE_PROVIDER == "claude":
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: _claude.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ))
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Claude Fehler: {e}")

    elif ACTIVE_PROVIDER == "openai":
        try:
            resp = await http.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": OPENAI_MODEL,
                      "messages": [{"role": "system", "content": system}] + messages,
                      "max_tokens": max_tokens, "temperature": 0.7},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenAI Fehler: {e}")

    elif ACTIVE_PROVIDER == "ollama":
        try:
            print(f"  [ollama] calling {OLLAMA_MODEL}...", flush=True)
            resp = await http.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL,
                      "messages": [{"role": "system", "content": system}] + messages,
                      "stream": False, "options": {"temperature": 0.7, "num_predict": max_tokens}},
            )
            resp.raise_for_status()
            text = resp.json()["message"]["content"]
            print(f"  [ollama] response: {text[:60]}", flush=True)
            return text
        except Exception as e:
            print(f"  [ollama] ERROR: {e}", flush=True)
            raise RuntimeError(f"Ollama Fehler: {e}")

    else:  # venice or groq
        base_url = VENICE_BASE_URL if ACTIVE_PROVIDER == "venice" else GROQ_BASE_URL
        api_key  = VENICE_API_KEY  if ACTIVE_PROVIDER == "venice" else GROQ_API_KEY
        model    = VENICE_MODEL    if ACTIVE_PROVIDER == "venice" else GROQ_MODEL
        try:
            resp = await http.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "system", "content": system}] + messages,
                      "max_tokens": max_tokens, "temperature": 0.7},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"{ACTIVE_PROVIDER.capitalize()} Fehler: {e}")

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

    elif t == "TASK":
        return await create_task_document(p)

    elif t == "VIDEO":
        return await browser_tools.fetch_youtube_video(p)

    elif t == "MOVIE":
        return await browser_tools.fetch_movies(p)

    elif t == "PLAY":
        return await browser_tools.play_movie(p)

    elif t == "TOR":
        return await open_tor_browser(p)

    elif t == "MUSIC":
        return await play_music(p)

    elif t == "SHELL":
        return await run_shell(p)

    elif t == "TV":
        return await play_tv(p)

    return ""

SUDO_PASSWORD    = config.get("sudo_password", "")
IPTV_GERMAN_URL  = config.get("iptv_german_url", "https://iptv-org.github.io/iptv/languages/deu.m3u")

async def run_shell(command: str) -> str:
    import shlex
    try:
        if command.strip().startswith("sudo") and SUDO_PASSWORD:
            cmd = f"echo {shlex.quote(SUDO_PASSWORD)} | sudo -S {command.lstrip('sudo').strip()}"
        else:
            cmd = command
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "DISPLAY": ":0"},
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace").strip()
        print(f"  [shell] rc={proc.returncode} {command[:60]}", flush=True)
        return f"Befehl: {command}\n{output[:1500]}" if output else f"Ausgeführt: {command}"
    except asyncio.TimeoutError:
        return f"Timeout: {command}"
    except Exception as e:
        return f"Shell-Fehler: {e}"

TOR_BROWSER_PATH = os.path.expanduser(
    "~/.local/share/torbrowser/tbb/x86_64/tor-browser/Browser/start-tor-browser"
)

_tv_process = None

async def play_tv(channel: str = "") -> str:
    global _tv_process
    import subprocess
    try:
        if _tv_process and _tv_process.returncode is None:
            _tv_process.terminate()
        if channel.strip().lower() in ("stop", "stopp", "aus"):
            _tv_process = None
            return "TV gestoppt."
        # Play IPTV M3U — VLC will show channel list or play matching channel
        if channel.strip():
            # Try to find channel in M3U and play directly
            cmd = ["cvlc", "--intf", "qt", f"--qt-start-maximized",
                   f"#EXTM3U\n{channel}", IPTV_GERMAN_URL]
            # Simpler: open VLC with M3U and let user pick, or search
            _tv_process = subprocess.Popen(
                ["vlc", "--playlist-autostart", IPTV_GERMAN_URL],
                env={"DISPLAY": ":0", "HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin"}
            )
        else:
            _tv_process = subprocess.Popen(
                ["vlc", "--playlist-autostart", IPTV_GERMAN_URL],
                env={"DISPLAY": ":0", "HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin"}
            )
        return f"TV gestartet mit deutschen Sendern{(' — suche nach: ' + channel) if channel.strip() else ''}."
    except Exception as e:
        return f"TV-Fehler: {e}"

async def open_tor_browser(url: str = "") -> str:
    import asyncio
    try:
        cmd = [TOR_BROWSER_PATH]
        if url.strip():
            cmd.append(url.strip())
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: __import__('subprocess').Popen(
            cmd, cwd=os.path.dirname(TOR_BROWSER_PATH)
        ))
        return f"Tor Browser gestartet{(' — öffne: ' + url) if url.strip() else ''}."
    except Exception as e:
        return f"Tor Browser Fehler: {e}"

vlc_process = None

async def create_task_document(content: str) -> str:
    """Create an ODT task list and open it in LibreOffice."""
    import subprocess as sp, asyncio, re
    from datetime import datetime
    try:
        from odf.opendocument import OpenDocumentText
        from odf.text import H, P, List, ListItem

        doc   = OpenDocumentText()
        title = H(outlinelevel=1)
        title.addText(f"Aufgabenliste — {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        doc.text.addElement(title)

        raw   = re.sub(r'^\d+[\.\)]\s*', '', content, flags=re.MULTILINE)
        tasks = [t.strip() for t in re.split(r'[,\n;]+', raw) if t.strip()]

        lst = List()
        for task in tasks:
            item = ListItem()
            p    = P()
            p.addText(f"☐  {task}")
            item.addElement(p)
            lst.addElement(item)
        doc.text.addElement(lst)

        path = os.path.expanduser(f"~/Dokumente/Aufgaben_{datetime.now().strftime('%Y%m%d_%H%M')}.odt")
        doc.save(path)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: sp.Popen(["libreoffice", "--writer", path]))
        return f"Aufgabenliste mit {len(tasks)} Aufgaben erstellt und in LibreOffice geöffnet."
    except Exception as e:
        return f"Fehler beim Erstellen der Aufgabenliste: {e}"

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
        # Minimize all browser windows so we see the real desktop
        subprocess.run(["xdotool", "search", "--name", "Firefox", "windowminimize", "--sync"],
                       capture_output=True, env=env, timeout=2)
        import time as _t; _t.sleep(0.5)
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

# ─── Extract real query from user speech (overrides LLM payload) ──────────────
def extract_user_query(action_type: str, user_text: str) -> str:
    """Extract what the user ACTUALLY asked for, ignoring LLM rewriting."""
    import re
    t = user_text.strip()

    patterns = {
        "MUSIC": [
            r"spiel(?:e|en)?\s+(?:mir\s+)?(?:etwas\s+)?(?:von\s+)?(.+)",
            r"musik\s+(?:von\s+)?(.+)",
            r"h[oö]re?\s+(?:mir\s+)?(?:etwas\s+)?(?:von\s+)?(.+)",
            r"song\s+(?:von\s+)?(.+)",
        ],
        "VIDEO": [
            r"(?:spiel|zeig|öffne|such)(?:e|en)?\s+(?:mir\s+)?(?:das\s+)?video\s+(.+)",
            r"youtube\s+(.+)",
        ],
        "SEARCH": [
            r"such(?:e|en)?\s+(?:nach\s+)?(?:auf\s+\w+\s+)?(?:nach\s+)?(.+)",
            r"recherchier(?:e|en)?\s+(?:über\s+)?(.+)",
            r"was\s+(?:ist|sind|weisst)\s+(?:du\s+über\s+)?(.+)",
            r"erkl[äa]r(?:e|en)?\s+(?:mir\s+)?(.+)",
        ],
        "OPEN": [
            r"[öo]ff?ne[nt]?\s+(.+)",
            r"geh(?:e|en)?\s+(?:auf|zu)\s+(.+)",
            r"zeig\s+(?:mir\s+)?(?:die\s+)?(?:seite\s+)?(.+)",
        ],
        "TV": [
            r"(?:starte|zeig|schalte|öffne)\s+(?:tv|fernsehen|kanal|sender)?\s*(.+)?",
            r"(?:tv|fernsehen)\s+(.+)?",
        ],
    }

    for pat in patterns.get(action_type, []):
        m = re.search(pat, t, re.IGNORECASE)
        if m and m.group(1) and len(m.group(1).strip()) > 1:
            q = m.group(1).strip().rstrip(".,!?")
            # Remove trailing noise words
            q = re.sub(r'\s+(bitte|mal|doch|mir|an)$', '', q, flags=re.IGNORECASE).strip()
            return q

    return ""  # could not extract — keep LLM payload

# ─── Message Processing ────────────────────────────────────────────────────────
async def process_message(session_id: str, user_text: str, ws: WebSocket):
    if session_id not in conversations:
        conversations[session_id] = []

    if any(w in user_text.lower() for w in ("activate", "aktivieren", "hallo aria", "aria activate")):
        refresh_data()

    global _mem
    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-6:]  # short history = less confusion

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

    # For action requests: only keep last 2 messages to avoid context bleed
    if action and action["type"] in ("MUSIC", "VIDEO", "SEARCH", "OPEN", "TV", "SHELL", "TOR", "NEWS", "EMAIL", "MOVIE", "PLAY", "TV", "TASK"):
        conversations[session_id] = conversations[session_id][-2:]

    # Override LLM payload with what the user ACTUALLY said
    if action and action["type"] in ("MUSIC", "VIDEO", "SEARCH", "OPEN", "TV"):
        real_query = extract_user_query(action["type"], user_text)
        if real_query:
            print(f"  Query override: '{action['payload'][:40]}' → '{real_query}'", flush=True)
            action["payload"] = real_query

    # Hauptantwort sprechen
    if spoken_text:
        audio = await synthesize_speech(spoken_text)
        print(f"  Jarvis: {spoken_text[:80]}", flush=True)
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await broadcast_audio(spoken_text, audio)

    if action:
        # Guard: only run SCREEN/NEWS if user explicitly requested them
        txt = user_text.lower()
        if action["type"] == "SCREEN":
            print(f"  Action SCREEN disabled", flush=True)
            action = None
        elif action["type"] == "NEWS" and not any(w in txt for w in
                ("news","nachrichten","aktuell","welt","tagesschau","was passiert")):
            print(f"  Action NEWS blocked", flush=True)
            action = None
        elif action["type"] == "TASK" and not any(w in txt for w in
                ("aufgabe","task","todo","liste","erstell","schreib","dokument")):
            print(f"  Action TASK blocked", flush=True)
            action = None

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
                    f"Du bist Aria. Fasse die folgenden Informationen KURZ auf Deutsch zusammen, "
                    f"maximal 3 Saetze. Sprich den Nutzer als {USER_ADDRESS} an. "
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

    # Learn from this conversation in background (fire-and-forget, safe)
    conv_snapshot = list(conversations.get(session_id, []))
    async def _learn():
        global _mem
        try:
            _mem = await _memory.extract_and_update(conv_snapshot, call_groq)
        except Exception:
            pass
    asyncio.create_task(_learn())

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
    try:
        await ws.accept()
    except Exception:
        return
    connected_clients.add(ws)
    session_id = str(id(ws))
    print(f"[aria] Client connected ({len(connected_clients)} total)", flush=True)
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
            # Stop command
            stop_words = {"stop", "schweig", "schweigen", "ruhig", "stille", "halt", "stopp"}
            if any(w in user_text.lower() for w in stop_words):
                await broadcast({"type": "stop"})
                continue

            # Model switch command
            global ACTIVE_PROVIDER
            txt_lower = user_text.lower()
            switched  = None
            if any(w in txt_lower for w in ("venice",)):
                ACTIVE_PROVIDER = "venice"; switched = f"Venice ({VENICE_MODEL})"
            elif any(w in txt_lower for w in ("claude", "anthropic")):
                ACTIVE_PROVIDER = "claude"; switched = f"Claude ({ANTHROPIC_MODEL})"
            elif any(w in txt_lower for w in ("groq",)):
                ACTIVE_PROVIDER = "groq";   switched = f"Groq ({GROQ_MODEL})"
            elif any(w in txt_lower for w in ("openai", "gpt", "chatgpt")):
                ACTIVE_PROVIDER = "openai"; switched = f"OpenAI ({OPENAI_MODEL})"
            elif any(w in txt_lower for w in ("ollama", "lokal", "local")):
                ACTIVE_PROVIDER = "ollama"; switched = f"Ollama lokal ({OLLAMA_MODEL})"
            if switched:
                conversations.clear()
                # Test if the new provider works
                if ACTIVE_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
                    msg = f"Claude API Key fehlt, Sir."
                else:
                    msg = f"Modell gewechselt zu {switched}, Sir."
                audio = await synthesize_speech(msg)
                await broadcast_audio(msg, audio)
                print(f"  [model] switched to {ACTIVE_PROVIDER}", flush=True)
                continue
            print(f"  You: {user_text}", flush=True)
            await process_message(session_id, user_text, ws)
    except (WebSocketDisconnect, RuntimeError, Exception):
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
    print(" A.R.I.A. — Multi-Model Voice Assistant", flush=True)
    _model_name = {"claude": ANTHROPIC_MODEL, "groq": GROQ_MODEL, "venice": VENICE_MODEL, "ollama": OLLAMA_MODEL}.get(ACTIVE_PROVIDER, ACTIVE_PROVIDER)
    print(f" Standard: {ACTIVE_PROVIDER.upper()} ({_model_name})", flush=True)
    print(f" Verfügbar: Ollama (lokal), Groq, Venice, Claude", flush=True)
    print(f" http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
