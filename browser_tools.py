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

_playwright = None
_browser = None
_context = None

def _bring_to_front():
    try:
        subprocess.run(["xdotool", "search", "--name", "Chromium", "windowactivate"], capture_output=True, timeout=2)
    except Exception:
        try:
            subprocess.run(["wmctrl", "-a", "Chromium"], capture_output=True, timeout=2)
        except Exception:
            pass

async def _get_browser():
    global _playwright, _browser, _context
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=False,
            args=["--start-maximized", "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        _context = await _browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            no_viewport=True,
        )
    return _context

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
            text = await page.evaluate("""
                () => {
                    const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) return el.innerText.trim();
                    }
                    return document.body?.innerText?.trim() || '';
                }
            """)
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
        text = await page.evaluate("""
            () => {
                const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) return el.innerText.trim();
                }
                return document.body?.innerText?.trim() || '';
            }
        """)
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
        text = await page.evaluate("""
            () => {
                const teasers = document.querySelectorAll('.teaser__headline, .teaser-xs__headline, h2, h3');
                const headlines = [];
                teasers.forEach(el => {
                    const t = el.innerText.trim();
                    if (t.length > 10 && t.length < 200) headlines.push(t);
                });
                return headlines.slice(0, 15).join('\n');
            }
        """)
        if not text or len(text) < 50:
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
