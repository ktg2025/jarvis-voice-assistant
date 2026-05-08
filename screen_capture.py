"""
Jarvis V2 — Screen Capture (Kali Linux Edition)
Nutzt scrot statt ImageGrab, OpenRouter statt Anthropic.
"""
import base64
import io
import subprocess
from PIL import Image

def capture_screen() -> bytes:
    """Capture screen using scrot, return JPEG bytes."""
    screenshot_path = "/tmp/jarvis_screenshot.png"
    try:
        subprocess.run(["scrot", screenshot_path], check=True, capture_output=True)
    except Exception:
        try:
            subprocess.run(["import", "-window", "root", screenshot_path], check=True, capture_output=True)
        except Exception:
            # Leeres Bild als Fallback
            img = Image.new('RGB', (1920, 1080), color='black')
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()

    with Image.open(screenshot_path) as img:
        img = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()

async def describe_screen(client=None) -> str:
    """Wird nicht mehr direkt genutzt — screen_capture_with_openrouter in server.py übernimmt das."""
    return "Bitte screen_capture_with_openrouter() in server.py nutzen."
