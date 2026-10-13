"""Dogfood osu! coach in a real (headless) Chrome: scan + analyse demo replays,
visit every page, screenshot it and collect exceptions / console errors.

    python dev_tools/dogfood.py [URL] [OUT_DIR]      (set CHROME=... to pick the browser)
"""
import os
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def find_chrome() -> str | None:
    cands = [os.environ.get("CHROME"), shutil.which("google-chrome"), shutil.which("chromium"),
             shutil.which("chrome"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome"]
    return next((c for c in cands if c and Path(c).exists()), None)

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "dogfood")
OUT.mkdir(parents=True, exist_ok=True)
PAGES = ["Replays", "Detailed Map Analysis", "Overview", "Progress", "Aim", "Tapping", "Sliders & Reading",
         "Tips & Setup", "Map Suggestion", "Skill Development"]


def settle(page, extra=1.5):
    page.wait_for_timeout(500)
    for _ in range(240):   # wait while Streamlit shows its "running" indicator
        if not page.locator('[data-testid="stStatusWidget"]').count():
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(int(extra * 1000))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=find_chrome(), headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 2600}, device_scale_factor=1)
    console = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error",) else None)
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
    page.goto(URL)
    page.get_by_role("button", name="Scan").wait_for(timeout=60000)
    page.get_by_role("button", name="Scan").click()
    page.get_by_role("button", name="Analyse replays").wait_for(timeout=120000)
    settle(page)
    page.screenshot(path=str(OUT / "00-scanned.png"), full_page=True)
    t0 = time.time()
    page.get_by_role("button", name="Analyse replays").click()
    done = page.get_by_text("Analysed", exact=False).first
    exc_loc = page.locator('[data-testid="stException"]')
    for _ in range(600):
        if done.count() or exc_loc.count():
            break
        page.wait_for_timeout(500)
    print(f"analysis finished after {time.time() - t0:.0f}s; exceptions: {exc_loc.all_inner_texts()[:1]}")
    settle(page)
    report = []
    for i, name in enumerate(PAGES):
        page.locator('[data-testid="stSidebar"] [data-testid="stRadioGroup"]').get_by_text(name, exact=True).click()
        settle(page, 2.5)
        shot = OUT / f"{i + 1:02d}-{name.replace(' ', '_').replace('&', 'and')}.png"
        page.screenshot(path=str(shot), full_page=True)
        exc = page.locator('[data-testid="stException"]').all_inner_texts()
        h = page.evaluate("document.body.scrollHeight")
        report.append((name, shot.name, h, exc))
    for name, shot, h, exc in report:
        print(f"{name:<20} {shot:<32} height={h:<6} exceptions={len(exc)} {exc[:1]}")
    print("console errors:", len(console))
    for c in console[:15]:
        print("  ", c[:300])
    browser.close()
