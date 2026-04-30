# Expenses Dashboard — Project Guide

## Project Overview

Local expense tracking dashboard for Israeli banks. Fetches transaction data from Bank Hapoalim, Cal (Visa), and Max, categorizes them into Hebrew spending categories, and displays them in a browser-based UI.

**Stack:** Python + Flask + vanilla JS (single-page, RTL Hebrew UI)  
**Location:** `D:/projects/Projects/Expenses/`  
**Run:** `python app.py` → opens `http://127.0.0.1:5050` in browser

---

## File Structure

```
Expenses/
├── app.py              # Flask server + full HTML/JS dashboard (single file)
├── processor.py        # CSVProcessor: parsing Poalim/Cal/Max + BUSINESS_MAP + categorization
├── downloader.py       # Playwright: opens Chrome, user logs in/OTPs, captures downloads
├── sheets_handler.py   # Google Sheets upload (gspread)
├── setup_credentials.py
├── credentials.json    # Google Sheets service account key
├── inputs/             # Bank Excel exports land here + processed CSV exports
│   ├── poalim_apr_26.xlsx
│   ├── cal_apr_26.xlsx
│   └── max_apr_26.xlsx
└── _tmp_downloads/     # Playwright staging folder (auto-cleaned)
```

---

## Billing Cycle Logic

Different per bank — this is critical:

| Bank | Period | Example (May 10th fetch) |
|------|--------|--------------------------|
| Poalim | Calendar month (1st–last day) | April 1–30 |
| Cal | 11th to 10th billing cycle | April 11 – May 10 |
| Max | 11th to 10th billing cycle | April 11 – May 10 |

**Typical workflow:** On the 10th of each month, fetch previous month's data.  
File naming suffix: `apr_26` = April 2026.

---

## How the Downloader Works (`downloader.py`)

Uses Playwright (non-headless Chrome):

1. Opens each bank URL in Chrome
2. Pauses and prints instructions — user logs in + completes OTP manually
3. User clicks Export in the bank's UI
4. Script captures the downloaded file and moves it to `inputs/` with correct name
5. After all banks done → launches `app.py`

**Run manually from terminal:**
```bash
python downloader.py                          # current billing period, all banks
python downloader.py --month apr_26           # specific month
python downloader.py --banks cal,max          # skip Poalim
```

---

## Planned Features (not yet implemented)

### 1. "Fetch" Button in Dashboard
- Add **הורד נתונים** button to the Flask UI
- New `/fetch` POST endpoint spawns `downloader.py` as a subprocess
- Dashboard polls `/fetch/status` every 2s — shows live banner:
  - "פותח פועלים..." → "ממתין ל-OTP..." → "הורדה הושלמה ✅"
- After all 3 banks complete → auto-reloads dashboard data (calls `process_all()`)
- Browser window still opens for OTP (Playwright stays non-headless)

### 2. Billing Cycle Split in `downloader.py`
- `poalim_period(month_override)` → returns calendar month range (1st to last day)
- `card_period(month_override)` → returns 11th–10th range (existing logic)
- Each bank handler calls the appropriate function

### 3. Drag & Drop Re-categorization of Classified Transactions
- Currently drag & drop only works for **unclassified** items (the yellow warning box)
- Planned: add **"שנה קטגוריה ▼"** dropdown button on each transaction row in the drawer (sidebar)
- Selecting a new category calls `/classify` with that merchant name
- `/classify` already writes to `BUSINESS_MAP` in `processor.py` and reprocesses — no changes needed there
- The re-classification persists permanently (written to source code)

### 4. Auto CSV Export to `inputs/`
- After each fetch+process cycle, auto-save to `inputs/`:
  - `expenses_APR_26.csv` — all transactions with date, description, amount, category, source
  - `summary_APR_26.csv` — totals per category
- Triggered automatically when `/fetch` completes, or via manual button

---

## Category System (`processor.py`)

### Classification Priority
1. **`BUSINESS_MAP`** — exact partial match on merchant name (Hebrew dict, ~200 entries)
2. **`self.categories`** — English keyword fallback
3. **Unclassified** → shown in yellow warning box on dashboard, user drags to correct category

### Drag & Drop Classification (existing)
- Unclassified item dragged onto a category card → POST `/classify`
- `/classify` endpoint: writes new entry to `BUSINESS_MAP` in `processor.py`, reloads module, reprocesses all files
- Changes are permanent (written to source code)

### Income vs Expense
```python
INCOME_CATEGORIES = {"משכורות", "הכנסות נוספות"}
EXCLUDED_CATEGORIES = {"לא לחישוב"}   # ignored from balance and display
```

### Key Categories (Hebrew)
| Category | Notes |
|----------|-------|
| אוכל בבית | Groceries: Rami Levy, Shufersal, etc. |
| יציאות | Dining out, delivery (Wolt), cafes |
| דלק רכב | Fuel, parking, tolls, car expenses |
| אינטרנט וטלויזיה | Cellcom, YES, streaming, iCloud |
| חשמל גז | Electric company, gas |
| מים | Water (Mei Avivim) |
| ביטוחים (כולל רכב בריאות) | All insurance |
| בריאות | Pharmacy, Maccabi, doctors |
| צרכנות | General shopping, PayPal, AliExpress |
| משק בית | PayBox, Bit transfers, home goods |
| גן | Kindergarten, Netaim |
| שכירות / משכנתה | Rent or mortgage |
| משכורות | Salaries (income) |
| הכנסות נוספות | Child allowance, other income |
| התעלם | Filtered out silently (internal transfers, etc.) |

---

## Flask Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Dashboard HTML |
| `/data` | GET | All processed data as JSON |
| `/classify` | POST | Map business → category, reprocess |
| `/upload` | POST | Push month to Google Sheets |
| `/debug-data` | GET | Raw totals dump |
| `/debug-raw` | GET | Poalim file raw rows |
| `/debug-max-tabs` | GET | MAX file all sheet tabs |
| `/fetch` | POST | **[planned]** Trigger downloader |
| `/fetch/status` | GET | **[planned]** Poll download progress |

---

## Google Sheets Integration

- **Sheet ID:** `1aDkWugFrJfVjsNkstXnh_D0DbuHy05ymCmyx2U_Z6gs`
- **Credentials:** `credentials.json` (service account)
- **Handler:** `sheets_handler.py` → `SheetsHandler.update_monthly_row(year, month_label, totals)`
- Upload is manual (button in UI) — sends current month's category totals

---

## Development Notes

- App uses `sys.stdout.reconfigure(encoding="utf-8")` — required for Hebrew on Windows
- All HTML is inline in `app.py` as `HTML_TEMPLATE` string — no separate template files
- NaN sanitization via `_sanitize()` applied to all RESULTS before serving JSON
- Module reload pattern: `/classify` uses `importlib.reload()` to pick up new BUSINESS_MAP entries without restart
- Playwright downloads go to `_tmp_downloads/` first, then moved to `inputs/` with correct name
- CAL card ID is hardcoded in `downloader.py`: update `card_id` if card changes
