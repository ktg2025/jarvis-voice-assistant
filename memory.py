"""
Jarvis Memory System — lernt aus täglichen Interaktionen.
Speichert Präferenzen, Gewohnheiten und persönliche Fakten in memory.json.
"""
import json
import os
import asyncio
from datetime import datetime

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

def load_memory() -> dict:
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "user": {},
        "preferences": {},
        "facts": [],
        "daily_patterns": {},
        "interaction_count": 0,
        "last_updated": "",
    }

def save_memory(mem: dict):
    mem["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

def format_for_prompt(mem: dict) -> str:
    """Format memory as context for the system prompt."""
    parts = []
    if mem.get("user"):
        parts.append("=== Was Jarvis über Sie weiss ===")
        for k, v in mem["user"].items():
            parts.append(f"- {k}: {v}")
    if mem.get("preferences"):
        parts.append("=== Ihre Präferenzen ===")
        for k, v in mem["preferences"].items():
            parts.append(f"- {k}: {v}")
    if mem.get("facts"):
        parts.append("=== Gemerkte Fakten ===")
        for f in mem["facts"][-10:]:  # last 10 facts
            parts.append(f"- {f}")
    if mem.get("daily_patterns"):
        parts.append("=== Gewohnheiten ===")
        for k, v in mem["daily_patterns"].items():
            parts.append(f"- {k}: {v}")
    return "\n".join(parts) if parts else ""

EXTRACTION_PROMPT = """Analysiere diese Konversation zwischen einem Nutzer und Jarvis.
Extrahiere neue Fakten, Präferenzen oder Gewohnheiten die du über den Nutzer gelernt hast.
Antworte NUR mit einem JSON-Objekt (oder leeres JSON {} wenn nichts Neues):
{
  "user": {"schlüssel": "wert"},
  "preferences": {"schlüssel": "wert"},
  "facts": ["fakt1", "fakt2"],
  "daily_patterns": {"schlüssel": "wert"}
}
Nur wirklich neue, relevante Informationen. Keine Wetteranfragen oder triviale Aussagen."""

async def extract_and_update(conversation: list, call_llm_fn) -> dict:
    """Extract learnings from a conversation and update memory."""
    if len(conversation) < 2:
        return load_memory()

    mem = load_memory()
    mem["interaction_count"] = mem.get("interaction_count", 0) + 1

    # Only extract every 3 interactions to save API calls
    if mem["interaction_count"] % 3 != 0:
        save_memory(mem)
        return mem

    try:
        conv_text = "\n".join(
            f"{'Nutzer' if m['role']=='user' else 'Jarvis'}: {m['content'][:200]}"
            for m in conversation[-6:]
        )
        result = await call_llm_fn(
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": conv_text}],
            max_tokens=300,
        )

        # Parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            learned = json.loads(json_match.group())
            for key in ("user", "preferences", "daily_patterns"):
                if learned.get(key):
                    mem.setdefault(key, {}).update(learned[key])
            if learned.get("facts"):
                existing = set(mem.get("facts", []))
                for fact in learned["facts"]:
                    if fact not in existing:
                        mem.setdefault("facts", []).append(fact)
    except Exception:
        pass

    save_memory(mem)
    return mem
