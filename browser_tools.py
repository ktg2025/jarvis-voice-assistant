"""
Jarvis V2 — Browser Tools (Kali Linux Edition)
"""
import re
import webbrowser
import subprocess
import asyncio
from urllib.parse import unquote, parse_qs, urlparse
import httpx
from playwright.async_api import async_playwright

_playwright     = None
_browser        = None
_context        = None
_gmail_playwright = None
_gmail_context  = None

BROWSER_PROFILE = "/home/guru/.config/jarvis-browser"

def _bring_to_front():
    try:
        subprocess.run(["xdotool", "search", "--name", "Firefox", "windowactivate"], capture_output=True, timeout=2)
    except Exception:
        try:
            subprocess.run(["wmctrl", "-a", "Firefox"], capture_output=True, timeout=2)
        except Exception:
            pass

async def _get_browser():
    global _playwright, _browser, _context
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.firefox.launch(
            headless=False,
        )
        _context = await _browser.new_context(no_viewport=True)
    return _context

async def _get_gmail_browser():
    """Persistent Firefox context — saves Gmail session across restarts."""
    global _gmail_playwright, _gmail_context
    if _gmail_context is None:
        import os
        os.makedirs(BROWSER_PROFILE, exist_ok=True)
        _gmail_playwright = await async_playwright().start()
        _gmail_context = await _gmail_playwright.firefox.launch_persistent_context(
            BROWSER_PROFILE,
            headless=False,
            no_viewport=True,
        )
    return _gmail_context

async def fetch_emails() -> str:
    """Open Gmail in persistent browser, return unread email summaries."""
    ctx = await _get_gmail_browser()
    page = await ctx.new_page()
    try:
        await page.goto("https://mail.google.com/mail/u/0/#inbox", timeout=30000)
        _bring_to_front()

        # Check if login needed
        await page.wait_for_timeout(3000)
        url = page.url
        if "accounts.google.com" in url or "signin" in url:
            return "Bitte loggen Sie sich einmalig in Gmail ein — das Fenster ist geöffnet."

        await page.wait_for_selector('[role="main"]', timeout=10000)

        # Extract unread emails (bold rows = unread)
        emails = await page.evaluate("""() => {
            const rows = document.querySelectorAll('tr.zA');
            const results = [];
            for (const row of Array.from(rows).slice(0, 10)) {
                const unread = row.classList.contains('zE');
                const sender = row.querySelector('.yX')?.innerText || '';
                const subject = row.querySelector('.y6')?.innerText || '';
                const snippet = row.querySelector('.y2')?.innerText || '';
                if (sender || subject) results.push({unread, sender, subject, snippet});
            }
            return results;
        }""")

        if not emails:
            return "Keine E-Mails gefunden oder Gmail ist nicht erreichbar."

        lines = []
        unread_count = sum(1 for e in emails if e.get("unread"))
        lines.append(f"{unread_count} ungelesene E-Mails:")
        for e in emails:
            marker = "● " if e.get("unread") else "○ "
            lines.append(f'{marker}{e["sender"]}: {e["subject"]} — {e["snippet"][:60]}')
        return "\n".join(lines)

    except Exception as e:
        return f"Gmail-Fehler: {e}"
    finally:
        await page.close()

async def search_and_read(query: str) -> dict:
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        search_url = f"https://duckduckgo.com/?q={query}&kl=de-de"
        await page.goto(search_url, timeout=20000)
        _bring_to_front()
        await page.wait_for_timeout(2000)
        first_link = page.locator('[data-testid="result-title-a"]').first
        if await first_link.count() > 0:
            await first_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await page.wait_for_timeout(2000)
            title = await page.title()
            url = page.url
            text = await page.evaluate("() => document.body.innerText")
            return {"title": title, "url": url, "content": text[:3000]}
        else:
            text = await page.evaluate("() => document.body.innerText")
            return {"title": "DuckDuckGo Suche", "url": search_url, "content": text[:2000]}
    except Exception as e:
        return {"error": str(e), "url": query}

async def visit(url: str, max_chars: int = 5000) -> dict:
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        _bring_to_front()
        text = await page.evaluate("() => document.body.innerText")
        title = await page.title()
        return {"title": title, "url": url, "content": text[:max_chars]}
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        await page.close()

async def fetch_news() -> str:
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto("https://www.tagesschau.de/", timeout=20000)
        _bring_to_front()
        await page.wait_for_timeout(3000)
        text = await page.evaluate("() => document.body.innerText")
        return f"Tagesschau Nachrichten:\n{text[:3000]}"
    except Exception as e:
        return f"Nachrichten konnten nicht geladen werden: {e}"

async def open_url(url: str):
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        _bring_to_front()
    except Exception:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, webbrowser.open, url)
    return {"success": True, "url": url}

async def close():
    global _playwright, _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
