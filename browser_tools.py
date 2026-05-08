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

_playwright       = None
_browser          = None
_context          = None
_gmail_playwright = None
_gmail_context    = None
_movie_playwright = None
_movie_context    = None

BROWSER_PROFILE       = "/home/guru/.config/jarvis-browser"
MOVIE_PROFILE         = "/home/guru/.config/jarvis-movie-browser"
MOVIE_URL             = "https://moviez.naranja.li/web/index.html#!/videos?serverId=e0c819e7a4544ad3bfc83b699503669f&parentId=19"

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
    """Open URL in the user's system Firefox (not Playwright)."""
    import asyncio, os
    env = {"DISPLAY": ":0", "HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin"}
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: subprocess.Popen(["firefox", url], env=env))
    _bring_to_front()
    return {"success": True, "url": url}

async def fetch_youtube_video(query: str) -> str:
    """Search YouTube in the user's system Firefox."""
    import asyncio, os, urllib.parse
    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    env = {"DISPLAY": ":0", "HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin"}
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: subprocess.Popen(["firefox", search_url], env=env))
    _bring_to_front()
    return f"YouTube geöffnet — Suchergebnisse für: {query}"

async def _get_movie_browser():
    global _movie_playwright, _movie_context
    if _movie_context is None:
        import os
        os.makedirs(MOVIE_PROFILE, exist_ok=True)
        _movie_playwright = await async_playwright().start()
        _movie_context = await _movie_playwright.firefox.launch_persistent_context(
            MOVIE_PROFILE, headless=False, no_viewport=True,
        )
    return _movie_context

async def fetch_movies(query: str = "") -> str:
    """List or search movies on the NeueFlix server."""
    ctx  = await _get_movie_browser()
    page = await ctx.new_page()
    try:
        await page.goto(MOVIE_URL, timeout=20000)
        _bring_to_front()
        await page.wait_for_timeout(4000)

        # Check if login needed
        if "einloggen" in (await page.evaluate("() => document.body.innerText")).lower():
            return "Bitte einmalig auf NeueFlix einloggen — das Fenster ist geöffnet."

        # Extract movie titles
        titles = await page.evaluate("""() => {
            const els = document.querySelectorAll('.cardText, .card-text, h3, .itemName, [data-testid="card-title"]');
            return Array.from(els).map(e => e.innerText.trim()).filter(t => t.length > 1).slice(0, 30);
        }""")

        if not titles:
            # Fallback: grab all visible text blocks
            text = await page.evaluate("() => document.body.innerText")
            return f"Filme auf NeueFlix:\n{text[:1500]}"

        if query:
            q = query.lower()
            titles = [t for t in titles if q in t.lower()] or titles

        return "Verfügbare Filme:\n" + "\n".join(f"• {t}" for t in titles[:15])
    except Exception as e:
        return f"Film-Fehler: {e}"
    finally:
        await page.close()

async def play_movie(title: str) -> str:
    """Find and play a movie by title on NeueFlix."""
    ctx  = await _get_movie_browser()
    page = await ctx.new_page()
    try:
        await page.goto(MOVIE_URL, timeout=20000)
        _bring_to_front()
        await page.wait_for_timeout(4000)

        if "einloggen" in (await page.evaluate("() => document.body.innerText")).lower():
            return "Bitte zuerst einloggen."

        # Find and click the movie card
        cards = page.locator('.cardText, .card-text, .itemName')
        count = await cards.count()
        for i in range(count):
            card_text = await cards.nth(i).inner_text()
            if title.lower() in card_text.lower():
                await cards.nth(i).click()
                await page.wait_for_timeout(2000)
                # Click play button if visible
                play_btn = page.locator('[data-action="play"], .btnPlay, button:has-text("Play"), button:has-text("Abspielen")').first
                if await play_btn.count() > 0:
                    await play_btn.click()
                _bring_to_front()
                return f"Spiele: {card_text.strip()}"
        return f"Film nicht gefunden: {title}"
    except Exception as e:
        return f"Wiedergabe-Fehler: {e}"
    finally:
        await page.close()

async def close():
    global _playwright, _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
