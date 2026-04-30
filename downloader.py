"""
downloader.py — Opens each bank in Chrome, user logs in and exports.
Script intercepts the download and saves to inputs/ with the correct name.

When spawned from Flask (--no-launch flag), uses status/signal files instead
of terminal input() prompts. The dashboard shows a "Continue" button.

Usage:
    python downloader.py               # terminal mode
    python downloader.py --month apr_26
    python downloader.py --banks cal,max
    python downloader.py --no-launch   # spawned by Flask dashboard
"""

import sys
import json
import asyncio
import argparse
import shutil
import subprocess
import time
import calendar
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR  = Path(__file__).parent
INPUT_DIR = BASE_DIR / "inputs"
INPUT_DIR.mkdir(exist_ok=True)
TMP_DIR   = BASE_DIR / "_tmp_downloads"
TMP_DIR.mkdir(exist_ok=True)
STATUS_FILE   = BASE_DIR / "_fetch_status.json"
CONTINUE_FILE = BASE_DIR / "_fetch_continue"

try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chrome"])
    from playwright.async_api import async_playwright

MONTH_ABBR = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]

# ── Mode flag (set in main) ───────────────────────────────────────────────────
NO_LAUNCH = False  # True when spawned from Flask

# ── Status / signal helpers ───────────────────────────────────────────────────

def write_status(status: str, bank: str, message: str, done: bool = False):
    """Write fetch status to file (read by Flask /fetch/status endpoint)."""
    if not NO_LAUNCH:
        return
    STATUS_FILE.write_text(
        json.dumps({"status": status, "bank": bank, "message": message, "done": done},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def wait_for_signal(bank: str, message: str):
    """
    --no-launch mode: write 'waiting' status, block until Flask drops CONTINUE_FILE.
    terminal mode: use input() as before.
    """
    if NO_LAUNCH:
        if CONTINUE_FILE.exists():
            CONTINUE_FILE.unlink()
        write_status("waiting", bank, message)
        while not CONTINUE_FILE.exists():
            time.sleep(0.3)
        CONTINUE_FILE.unlink()
        write_status("running", bank, "ממשיך...")
    else:
        input(f"\n  {message}\n  >> Press Enter to continue: ")


# ── Billing period helpers ────────────────────────────────────────────────────

def card_period(override=None):
    """
    Card billing cycle: 11th of month M to 10th of month M+1.
    File suffix = start month, e.g. apr_26 = 11/04/2026 – 10/05/2026.

    On the 10th (fetch day): day < 11, so returns previous month → apr_26.
    """
    if override:
        parts = override.lower().split("_")
        m = MONTH_ABBR.index(parts[0]) + 1
        y = 2000 + int(parts[1])
    else:
        today = datetime.now()
        if today.day >= 11:
            m, y = today.month, today.year
        else:
            m = today.month - 1 or 12
            y = today.year if today.month > 1 else today.year - 1

    end_m = m % 12 + 1
    end_y = y + 1 if m == 12 else y
    start_str = f"11/{m:02d}/{y}"
    end_str   = f"10/{end_m:02d}/{end_y}"
    suffix    = f"{MONTH_ABBR[m-1]}_{str(y)[-2:]}"
    return start_str, end_str, suffix


def poalim_period(override=None):
    """
    Poalim: full calendar month matching the card billing period suffix.
    e.g. card suffix apr_26 → Poalim: April 1–30 2026.
    """
    _, _, suffix = card_period(override)
    parts = suffix.split("_")
    m = MONTH_ABBR.index(parts[0]) + 1
    y = 2000 + int(parts[1])
    last_day = calendar.monthrange(y, m)[1]
    start_str = f"01/{m:02d}/{y}"
    end_str   = f"{last_day}/{m:02d}/{y}"
    return start_str, end_str, suffix


# ── File helpers ──────────────────────────────────────────────────────────────

def clear_tmp():
    for f in TMP_DIR.iterdir():
        try:
            f.unlink()
        except Exception:
            pass


def wait_for_file(timeout_sec=120) -> Path | None:
    downloads = Path.home() / "Downloads"
    cutoff    = time.time()
    print("  Waiting for download", end="", flush=True)
    for _ in range(timeout_sec * 2):
        time.sleep(0.5)
        print(".", end="", flush=True)
        for f in TMP_DIR.iterdir():
            if f.suffix.lower() in (".xlsx", ".xls", ".csv") and f.stat().st_mtime >= cutoff:
                print()
                return f
        try:
            for f in downloads.iterdir():
                if f.suffix.lower() in (".xlsx", ".xls", ".csv") and f.stat().st_mtime >= cutoff:
                    print()
                    return f
        except Exception:
            pass
    print("\n  Timed out.")
    return None


# ── Bank handlers ─────────────────────────────────────────────────────────────

async def download_hapoalim(context, start: str, end: str, suffix: str):
    print("\n── Bank Hapoalim ──")
    clear_tmp()
    dest = INPUT_DIR / f"poalim_{suffix}.xlsx"

    write_status("running", "פועלים", "פותח את אתר בנק הפועלים...")
    page = await context.new_page()
    await page.goto("https://login.bankhapoalim.co.il/", wait_until="domcontentloaded")

    wait_for_signal(
        "פועלים",
        f"התחבר לפועלים → תנועות בחשבון → {start} עד {end} → ייצוא ל-Excel → לחץ המשך"
    )
    await page.wait_for_timeout(2000)

    found = wait_for_file(timeout_sec=60)
    if found:
        shutil.move(str(found), str(dest))
        write_status("running", "פועלים", "פועלים הושלם ✓")
        print(f"  Saved -> inputs/{dest.name}")
    else:
        write_status("error", "פועלים", "לא נמצא קובץ — העתק ידנית ולחץ המשך")
        print(f"  Please copy manually to: inputs/{dest.name}")
        wait_for_signal("פועלים", f"העתק את הקובץ ידנית ל: inputs/{dest.name} → לחץ המשך")

    await page.close()


async def download_max(context, suffix: str):
    print("\n── MAX ──")
    clear_tmp()
    dest = INPUT_DIR / f"max_{suffix}.xlsx"

    write_status("running", "Max", "פותח את אתר Max...")
    page = await context.new_page()
    await page.goto("https://www.max.co.il/", wait_until="domcontentloaded")

    wait_for_signal(
        "Max",
        "התחבר ל-Max (ת.ז. + מספר חשבון + OTP) → עסקאות → אשר שהתקופה נכונה → ייצוא ל-Excel → לחץ המשך"
    )
    await page.wait_for_timeout(2000)

    found = wait_for_file(timeout_sec=60)
    if found:
        shutil.move(str(found), str(dest))
        write_status("running", "Max", "Max הושלם ✓")
        print(f"  Saved -> inputs/{dest.name}")
    else:
        write_status("error", "Max", "לא נמצא קובץ — העתק ידנית ולחץ המשך")
        print(f"  Please copy manually to: inputs/{dest.name}")
        wait_for_signal("Max", f"העתק את הקובץ ידנית ל: inputs/{dest.name} → לחץ המשך")

    await page.close()


async def download_cal(context, suffix: str):
    HEBREW_MONTHS = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני",
                     "יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
    m_idx        = MONTH_ABBR.index(suffix.split("_")[0])
    target_month = HEBREW_MONTHS[(m_idx + 1) % 12]
    card_id      = "33072111445402024340"   # update if card changes

    print(f"\n── CAL ── (target month: {target_month})")
    clear_tmp()
    dest = INPUT_DIR / f"cal_{suffix}.xlsx"

    download_holder = []
    async def on_download(dl):
        if not download_holder:
            download_holder.append(dl)
    context.on("download", on_download)

    write_status("running", "CAL", "פותח את אתר CAL...")
    page = await context.new_page()
    await page.goto("https://www.cal-online.co.il/", wait_until="domcontentloaded")

    wait_for_signal("CAL", "התחבר ל-CAL (ת.ז. + 4 ספרות + OTP) → לחץ המשך")
    await page.wait_for_timeout(1500)

    write_status("running", "CAL", f"מנווט לעסקאות ({target_month})...")
    print("  Navigating to transactions page...")
    await page.goto(
        f"https://digital-web.cal-online.co.il/transactions?cardUniqueId={card_id}",
        wait_until="domcontentloaded",
    )
    await page.wait_for_timeout(3000)

    content = await page.content()
    if target_month not in content:
        wait_for_signal("CAL", f"בחר את חודש {target_month} בחצים → לחץ המשך")
        await page.wait_for_timeout(1000)

    write_status("running", "CAL", "לוחץ על כפתור ה-Excel...")
    print("  Clicking Excel download icon (div.half.left)...")
    try:
        await page.click("div.half.left", timeout=8000)
    except Exception as e:
        print(f"  Auto-click failed ({e})")
        wait_for_signal("CAL", "לחץ על סמל ה-Excel ב-CAL → לחץ המשך")

    print("  Waiting for CAL download", end="", flush=True)
    for _ in range(60):
        await page.wait_for_timeout(500)
        print(".", end="", flush=True)
        if download_holder:
            break
    print()

    if download_holder:
        dl  = download_holder[0]
        tmp = TMP_DIR / (dl.suggested_filename or f"cal_{suffix}.xlsx")
        await dl.save_as(str(tmp))
        shutil.move(str(tmp), str(dest))
        write_status("running", "CAL", "CAL הושלם ✓")
        print(f"  Saved -> inputs/{dest.name}")
    else:
        print("  Download not captured — checking Downloads folder...")
        found = wait_for_file(timeout_sec=15)
        if found:
            shutil.move(str(found), str(dest))
            write_status("running", "CAL", "CAL הושלם ✓")
            print(f"  Saved -> inputs/{dest.name}")
        else:
            write_status("error", "CAL", "לא נמצא קובץ — העתק ידנית ולחץ המשך")
            print(f"  Please copy manually to: inputs/{dest.name}")
            wait_for_signal("CAL", f"העתק את הקובץ ידנית ל: inputs/{dest.name} → לחץ המשך")

    await page.close()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(month_override, banks, no_launch):
    global NO_LAUNCH
    NO_LAUNCH = no_launch

    p_start, p_end, suffix = poalim_period(month_override)
    c_start, c_end, _      = card_period(month_override)

    print(f"\nPoalim period : {p_start}  ->  {p_end}  (calendar month)")
    print(f"Card period   : {c_start}  ->  {c_end}  (billing cycle)")
    print(f"File suffix   : {suffix}")
    print(f"Banks         : {', '.join(banks)}")

    write_status("running", "", "מאתחל דפדפן...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
            downloads_path=str(TMP_DIR),
        )
        context = await browser.new_context(accept_downloads=True, no_viewport=True)

        if "hapoalim" in banks:
            await download_hapoalim(context, p_start, p_end, suffix)
        if "max" in banks:
            await download_max(context, suffix)
        if "cal" in banks:
            await download_cal(context, suffix)

        await browser.close()

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    write_status("done", "", "כל הבנקים הושלמו — מרענן נתונים...", done=True)
    print("\nAll done.\n")

    if not no_launch:
        subprocess.Popen([sys.executable, str(BASE_DIR / "app.py")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month",     default=None,
                        help="e.g. apr_26  (default: auto from today)")
    parser.add_argument("--banks",     default="hapoalim,max,cal",
                        help="Comma-separated, e.g. --banks max,cal")
    parser.add_argument("--no-launch", action="store_true",
                        help="Don't relaunch app.py when done (used when spawned from Flask)")
    args = parser.parse_args()
    banks = [b.strip().lower() for b in args.banks.split(",")]
    asyncio.run(main(args.month, banks, args.no_launch))
