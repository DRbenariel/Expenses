"""
app.py — Expense Dashboard Web UI
Processes all input files, then opens a beautiful Hebrew RTL browser UI.
Click the upload button to send data to Google Sheets.
"""
import os
import sys
import json
import threading
import webbrowser
import asyncio
import subprocess

# ── Fix encoding ──────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "inputs")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
SPREADSHEET_KEY = "1aDkWugFrJfVjsNkstXnh_D0DbuHy05ymCmyx2U_Z6gs"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_KEY}"

STATUS_FILE   = os.path.join(BASE_DIR, "_fetch_status.json")
CONTINUE_FILE = os.path.join(BASE_DIR, "_fetch_continue")
_fetch_proc   = None

sys.path.insert(0, BASE_DIR)
from processor import CSVProcessor, INCOME_CATEGORIES, BUSINESS_MAP

try:
    from flask import Flask, jsonify, request, render_template_string
except ImportError:
    print("Flask not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, jsonify, request, render_template_string

# ── Hebrew month mapping ───────────────────────────────────────────────────────
HEBREW_MONTHS = {
    "JAN": "ינואר", "FEB": "פברואר", "MAR": "מרץ", "APR": "אפריל",
    "MAY": "מאי",  "JUN": "יוני",   "JUL": "יולי", "AUG": "אוגוסט",
    "SEP": "ספטמבר","OCT": "אוקטובר","NOV": "נובמבר","DEC": "דצמבר",
}

# ── Process all input files ───────────────────────────────────────────────────
def process_all():
    import re
    processor = CSVProcessor()
    monthly = {}

    for filename in os.listdir(INPUT_FOLDER):
        ext = filename.lower()
        is_excel = ext.endswith(".xls") or ext.endswith(".xlsx") or ext.endswith(".csv")
        is_scraped = filename.lower().startswith("scraped_") and ext.endswith(".json")
        if not (is_excel or is_scraped):
            continue

        file_path = os.path.join(INPUT_FOLDER, filename)
        match = re.search(r"([a-zA-Z]{3}_\d{2})", filename)
        month_key = match.group(1).upper() if match else "UNKNOWN"

        try:
            fn = filename.lower()
            if fn.endswith(".json") and fn.startswith("scraped_"):
                data = processor.parse_scraped_json(file_path)
            elif "poalim" in fn or "bank" in fn:
                data = processor.parse_hapoalim(file_path)
            elif "cal" in fn:
                data = processor.parse_cal(file_path)
            elif "max" in fn:
                data = processor.parse_max(file_path)
            else:
                data = processor.parse_hapoalim(file_path)

            monthly.setdefault(month_key, []).extend(data)
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    results = {}
    for month_key, transactions in monthly.items():
        totals = processor.aggregate_data(transactions)

        try:
            eng_mon, yy = month_key.split("_")
            heb_mon = HEBREW_MONTHS.get(eng_mon, eng_mon)
            month_label = f"{heb_mon} 20{yy}"
        except Exception:
            month_label = month_key

        results[month_key] = {
            "label": month_label,
            "totals": totals,
            "transactions_count": len(transactions),
        }

    unclassified = sorted(processor.unclassified_businesses)

    # Build per-category transaction list for drill-down
    for month_key in results:
        txns = monthly[month_key]
        by_cat = {}
        for t in txns:
            cat = t["Category"]
            if cat not in by_cat:
                by_cat[cat] = []
            raw_amt = t.get("Amount", 0)
            try:
                amt = float(raw_amt)
                if amt != amt:  # NaN check (NaN != NaN is True)
                    amt = 0.0
            except (TypeError, ValueError):
                amt = 0.0
            by_cat[cat].append({
                "date": str(t.get("Date", "")),
                "description": str(t.get("Description", "")),
                "amount": amt,
            })
        results[month_key]["by_category"] = by_cat


    return results, unclassified


# ── List all businesses with their categories (replaces list_businesses.py) ───
def list_businesses_with_categories():
    """
    Scans all input files and returns sorted list of
    {name, category, file} for every unique business description.
    """
    processor = CSVProcessor()
    seen = {}  # description -> {category, file}

    for filename in os.listdir(INPUT_FOLDER):
        fn = filename.lower()
        if not (fn.endswith(".xls") or fn.endswith(".xlsx") or fn.endswith(".csv")):
            continue
        file_path = os.path.join(INPUT_FOLDER, filename)
        try:
            if "poalim" in fn or "bank" in fn:
                data = processor.parse_hapoalim(file_path)
            elif "cal" in fn:
                data = processor.parse_cal(file_path)
            elif "max" in fn:
                data = processor.parse_max(file_path)
            else:
                data = processor.parse_hapoalim(file_path)

            for t in data:
                desc = t["Description"].strip()
                if desc not in seen:
                    seen[desc] = {"category": t["Category"], "file": filename}
        except Exception as e:
            print(f"list_businesses error {filename}: {e}")

    return sorted(
        [{"name": k, "category": v["category"], "file": v["file"]} for k, v in seen.items()],
        key=lambda x: x["name"]
    )


# ── Run processing once at startup ────────────────────────────────────────────
print("Processing expense files...")
RESULTS, UNCLASSIFIED = process_all()
BUSINESSES = list_businesses_with_categories()
ALL_CATEGORIES = sorted(set(BUSINESS_MAP.values()) - {"התעלם", "לא לחישוב", "לא מסווג"})

# Convert numpy/NaN types so Flask jsonify can serialize valid JSON
def _sanitize(obj):
    """Recursively replace NaN/numpy with clean Python types."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:   # NaN != NaN is the only reliable NaN test
            return 0.0
        return obj
    if isinstance(obj, str):
        return obj       # keep strings as-is
    try:
        return float(obj)
    except (TypeError, ValueError):
        return obj

# Apply to ALL of RESULTS (totals + by_category)
for _mk in RESULTS:
    RESULTS[_mk] = _sanitize(RESULTS[_mk])

def generate_insights(results):
    insights_by_month = {}
    for month_key, month_data in results.items():
        totals = month_data["totals"]
        by_cat = month_data.get("by_category", {})
        
        other_months = [v["totals"] for k, v in results.items() if k != month_key]
        
        history_avg = {}
        if other_months:
            for cat in totals.keys():
                sum_cat = sum(m.get(cat, 0) for m in other_months)
                history_avg[cat] = sum_cat / len(other_months)
        else:
            history_avg = {
                "צרכנות": 1000, "אוכל בבית": 4000, "יציאות": 1500,
                "דלק רכב": 1500, "ביטוחים (כולל רכב בריאות)": 1000,
            }

        max_diff = 0
        anomaly_cat = None
        anomaly_val = 0
        anomaly_avg = 0
        for cat, val in totals.items():
            if cat in INCOME_CATEGORIES or cat == 'לא מסווג': continue
            avg_val = history_avg.get(cat, val)
            diff = val - avg_val
            if diff > max_diff and diff > 100:
                max_diff = diff
                anomaly_cat = cat
                anomaly_val = val
                anomaly_avg = avg_val
        if anomaly_cat:
            anomaly_text = f'שמת לב? ההוצאה על "{anomaly_cat}" זינקה ב-{max_diff:,.0f} ש"ח ביחס לממוצע הרגיל שלכם.'
        else:
            anomaly_text = 'אין חריגות משמעותיות החודש בהוצאות ביחס לממוצע. כל הכבוד!'

        efficiency_text = ""
        food_txns = by_cat.get("אוכל בבית", [])
        small_food_sum = 0
        small_food_count = 0
        for t in food_txns:
            amt = abs(t["amount"])
            desc = t["description"].lower()
            if 0 < amt < 150 and "רמי לוי" not in desc and "שופרסל" not in desc:
                small_food_sum += amt
                small_food_count += 1
        if small_food_sum > 300:
            efficiency_text = f'קניות קטנות במכולות ובתי עסק שונים הצטברו החודש ל-{small_food_sum:,.0f} ש"ח ({small_food_count} פעולות). אלו קניות שלרוב יקרות ב-20% מרשתות דיסקאונט.'
        else:
            efficiency_text = 'הרגלי הקניות שלכם נראים ממוקדים! לא זיהינו זליגות משמעותיות של קניות קטנות ויקרות.'

        max_drop = 0
        positive_cat = None
        for cat, val in totals.items():
            if cat in INCOME_CATEGORIES or cat == 'לא מסווג': continue
            avg_val = history_avg.get(cat, val)
            drop = avg_val - val
            if drop > max_drop and drop > 100:
                max_drop = drop
                positive_cat = cat
        if positive_cat:
            pct = (max_drop / history_avg[positive_cat]) * 100 if history_avg[positive_cat] > 0 else 0
            positive_text = f'סעיף ה"{positive_cat}" ירד החודש ב-{pct:.0f}% (חסכון של {max_drop:,.0f} ש"ח) - אלופים!'
        else:
            positive_text = 'אתם שומרים על יציבות בהוצאות שלכם בהשוואה לממוצע.'

        all_expenses = []
        all_incomes = []
        for m in results.values():
            m_totals = m["totals"]
            all_expenses.append(sum(v for k,v in m_totals.items() if k not in INCOME_CATEGORIES and k != 'לא מסווג'))
            all_incomes.append(sum(v for k,v in m_totals.items() if k in INCOME_CATEGORIES))
        
        avg_expense = sum(all_expenses) / len(all_expenses) if all_expenses else 0
        avg_income = sum(all_incomes) / len(all_incomes) if all_incomes else 0
        
        if len(all_expenses) >= 1:
            if avg_expense > avg_income:
                projection_text = f'קצב שריפת המזומנים השנתי (Burn rate) גבוה משכר הנטו. בהתבסס על הוצאות של {avg_expense:,.0f} ש"ח לעומת הכנסות של {avg_income:,.0f} ש"ח, הגירעון השנתי לקצב זה הוא כ-{(avg_expense - avg_income)*12:,.0f} ש"ח.'
            else:
                projection_text = f'על סמך הנתונים, קצב שריפת המזומנים (Burn rate) הממוצע שלכם הוא {avg_expense:,.0f} ש"ח, אל מול משכורות של {avg_income:,.0f} ש"ח. הפוטנציאל לחסכון שנתי עומד על כ-{(avg_income - avg_expense)*12:,.0f} ש"ח.'
        else:
             projection_text = 'אין מספיק נתונים לחיזוי התקציב כרגע.'

        insights_by_month[month_key] = {
            "anomaly": anomaly_text,
            "efficiency": efficiency_text,
            "positive": positive_text,
            "projection": projection_text,
            "history_avgs": history_avg
        }
    return insights_by_month

INSIGHTS = generate_insights(RESULTS)

print(f"Done. {len(RESULTS)} month(s) found. {len(BUSINESSES)} unique businesses.")



# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>מנהל הוצאות</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --card:     #22263a;
    --border:   #2e3350;
    --accent:   #6c63ff;
    --income:   #22c55e;
    --expense:  #f87171;
    --text:     #e8eaf6;
    --muted:    #7b82a8;
    --warning:  #fbbf24;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Heebo', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 24px;
    direction: rtl;
  }

  /* ─── Header ─── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 36px;
    flex-wrap: wrap;
    gap: 16px;
  }
  .header h1 {
    font-size: 2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #6c63ff, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header .subtitle { color: var(--muted); font-size: .9rem; margin-top: 4px; }

  /* ─── Month Tabs ─── */
  .tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 28px;
    flex-wrap: wrap;
  }
  .tab {
    padding: 8px 20px;
    border-radius: 50px;
    border: 1.5px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    cursor: pointer;
    font-family: 'Heebo', sans-serif;
    font-size: .9rem;
    font-weight: 500;
    transition: all .2s;
  }
  .tab:hover { border-color: var(--accent); color: var(--text); }
  .tab.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    font-weight: 700;
  }

  /* ─── Summary Bar ─── */
  .summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }
  .summary-card {
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 16px;
    padding: 20px 24px;
    transition: transform .2s;
  }
  .summary-card:hover { transform: translateY(-2px); }
  .summary-card .label { font-size: .8rem; color: var(--muted); margin-bottom: 6px; }
  .summary-card .value { font-size: 1.5rem; font-weight: 700; }
  .summary-card.income .value { color: var(--income); }
  .summary-card.expense .value { color: var(--expense); }
  .summary-card.balance .value { color: var(--accent); }

  /* ─── Category Grid ─── */
  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 14px;
    text-transform: uppercase;
    letter-spacing: .05em;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
    margin-bottom: 32px;
  }
  .cat-card {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    transition: all .2s;
    position: relative;
    overflow: hidden;
  }
  .cat-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 4px; height: 100%;
    border-radius: 0 14px 14px 0;
  }
  .cat-card.income::before  { background: var(--income); }
  .cat-card.expense::before { background: var(--accent); }
  .cat-card:hover { transform: translateY(-3px); border-color: var(--accent); box-shadow: 0 8px 24px rgba(108,99,255,.15); }
  .cat-card .name { font-size: .95rem; font-weight: 600; margin-bottom: 10px; }
  .cat-card .amount-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .cat-card .amount {
    font-size: 1.3rem;
    font-weight: 800;
  }
  .cat-card.income  .amount { color: var(--income); }
  .cat-card.expense .amount { color: var(--text); }
  .cat-card .trend-arrow {
    font-size: 1rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(255,255,255,.05);
  }
  .cat-card .trend-arrow.up.bad { color: var(--expense); background: rgba(248,113,113,.15); }
  .cat-card .trend-arrow.down.good { color: var(--income); background: rgba(34,197,94,.15); }
  .cat-card .trend-arrow.up.good { color: var(--income); background: rgba(34,197,94,.15); }
  .cat-card .trend-arrow.down.bad { color: var(--expense); background: rgba(248,113,113,.15); }
  .cat-card .trend-arrow.flat { color: var(--muted); }
  
  .cat-card .bar-wrap {
    background: rgba(255,255,255,.06);
    border-radius: 4px;
    height: 4px;
    margin-top: 10px;
    overflow: hidden;
  }
  .cat-card .bar {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, #6c63ff, #a78bfa);
    transition: width .6s ease;
  }
  .cat-card.income .bar { background: linear-gradient(90deg, #22c55e, #86efac); }

  /* ─── Insights Panel ─── */
  .insights-panel {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }
  .insight-card {
    background: linear-gradient(145deg, var(--surface) 0%, var(--card) 100%);
    border: 1.5px solid var(--border);
    border-radius: 16px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .insight-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0; width: 4px; height: 100%;
    border-radius: 0 16px 16px 0;
  }
  .insight-card.anomaly::before { background: var(--expense); }
  .insight-card.efficiency::before { background: var(--warning); }
  .insight-card.positive::before { background: var(--income); }
  .insight-card.projection::before { background: var(--accent); }
  
  .insight-title {
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .insight-title.anomaly { color: var(--expense); }
  .insight-title.efficiency { color: var(--warning); }
  .insight-title.positive { color: var(--income); }
  .insight-title.projection { color: var(--accent); }
  
  .insight-body {
    font-size: 0.9rem;
    color: var(--text);
    line-height: 1.5;
  }

  /* ─── Unclassified ─── */
  .warn-box {
    background: rgba(251,191,36,.08);
    border: 1.5px solid rgba(251,191,36,.3);
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 28px;
  }
  .warn-box h3 { color: var(--warning); margin-bottom: 12px; font-size: .95rem; }
  .warn-box ul { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; }
  .warn-box li {
    background: rgba(251,191,36,.1);
    border: 1px solid rgba(251,191,36,.3);
    border-radius: 8px;
    padding: 4px 12px;
    font-size: .85rem;
    color: var(--warning);
    cursor: grab;
    user-select: none;
    transition: opacity .15s, transform .15s;
  }
  .warn-box li:active { cursor: grabbing; }
  .warn-box li.dragging { opacity: .4; transform: scale(.95); }

  /* ─── Drag-over highlight on category cards ─── */
  .cat-card.drag-over {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(108,99,255,.35);
    transform: translateY(-4px);
  }

  /* ─── "לא לחישוב" drop zone ─── */
  .ignore-zone {
    border: 2px dashed rgba(255,255,255,.18);
    border-radius: 14px;
    padding: 18px 24px;
    margin-bottom: 32px;
    display: flex;
    align-items: center;
    gap: 14px;
    color: var(--muted);
    font-size: .9rem;
    transition: border-color .2s, background .2s;
    min-height: 64px;
  }
  .ignore-zone.drag-over {
    border-color: rgba(248,113,113,.6);
    background: rgba(248,113,113,.06);
    color: var(--expense);
  }
  .ignore-zone .iz-icon { font-size: 1.4rem; flex-shrink: 0; }
  .ignore-zone .iz-label { font-weight: 600; }
  .ignore-zone .iz-hint { font-size: .8rem; opacity: .7; margin-top: 2px; }

  /* ─── Upload Button ─── */
  .actions {
    display: flex;
    gap: 14px;
    align-items: center;
    flex-wrap: wrap;
  }
  .btn-upload {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 14px 32px;
    background: linear-gradient(135deg, #6c63ff, #a78bfa);
    color: #fff;
    border: none;
    border-radius: 12px;
    font-family: 'Heebo', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: all .2s;
    box-shadow: 0 4px 20px rgba(108,99,255,.4);
  }
  .btn-upload:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(108,99,255,.5); }
  .btn-upload:disabled { opacity: .5; cursor: not-allowed; transform: none; }

  .status {
    font-size: .9rem;
    padding: 10px 18px;
    border-radius: 10px;
    display: none;
  }
  .status.success { background: rgba(34,197,94,.15); color: var(--income); border: 1px solid rgba(34,197,94,.3); display: block; }
  .status.error   { background: rgba(248,113,113,.15); color: var(--expense); border: 1px solid rgba(248,113,113,.3); display: block; }
  .status.loading { background: rgba(108,99,255,.15); color: #a78bfa; border: 1px solid rgba(108,99,255,.3); display: block; }

  /* ─── Transaction Drawer ─── */
  .backdrop {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.6); backdrop-filter: blur(4px); z-index: 100;
  }
  .backdrop.open { display: block; }
  .drawer {
    position: fixed; top: 0; left: 0;
    width: min(460px, 100vw); height: 100vh;
    background: var(--surface); border-right: 1.5px solid var(--border);
    z-index: 101; display: flex; flex-direction: column;
    transform: translateX(-100%);
    transition: transform .3s cubic-bezier(.4,0,.2,1);
    direction: rtl;
  }
  .drawer.open { transform: translateX(0); }
  .drawer-head {
    padding: 24px 24px 16px; border-bottom: 1px solid var(--border);
    display: flex; align-items: flex-start; justify-content: space-between;
  }
  .drawer-title { font-size: 1.1rem; font-weight: 700; }
  .drawer-total { font-size: .9rem; color: var(--accent); font-weight: 600; margin-top: 4px; }
  .btn-close {
    background: none; border: none; cursor: pointer;
    color: var(--muted); font-size: 1.4rem; line-height: 1; padding: 0;
  }
  .btn-close:hover { color: var(--text); }
  .drawer-body { flex: 1; overflow-y: auto; padding: 12px 24px; }
  .txn-row {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 12px; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,.05);
  }
  .txn-row:last-child { border-bottom: none; }
  .txn-desc { font-size: .88rem; flex: 1; }
  .txn-date { font-size: .76rem; color: var(--muted); margin-top: 2px; }
  .txn-amount { font-size: .9rem; font-weight: 700; white-space: nowrap; }
  .txn-amount.credit { color: var(--income); }
  .cat-card { cursor: pointer; }

  /* ─── Fetch Banner ─── */
  .fetch-banner {
    display: none;
    align-items: center;
    gap: 16px;
    padding: 14px 20px;
    border-radius: 12px;
    margin-bottom: 20px;
    font-size: .92rem;
    font-weight: 500;
    border: 1.5px solid;
  }
  .fetch-loading  { background: rgba(108,99,255,.12); border-color: rgba(108,99,255,.4); color: #a78bfa; }
  .fetch-waiting  { background: rgba(251,191,36,.10); border-color: rgba(251,191,36,.4); color: var(--warning); }
  .fetch-success  { background: rgba(34,197,94,.10);  border-color: rgba(34,197,94,.4);  color: var(--income); }
  .fetch-error    { background: rgba(248,113,113,.10);border-color: rgba(248,113,113,.4);color: var(--expense); }

  .btn-fetch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 11px 22px;
    background: rgba(108,99,255,.15);
    color: #a78bfa;
    border: 1.5px solid rgba(108,99,255,.4);
    border-radius: 12px;
    font-family: 'Heebo', sans-serif;
    font-size: .95rem;
    font-weight: 700;
    cursor: pointer;
    transition: all .2s;
    white-space: nowrap;
  }
  .btn-fetch:hover  { background: rgba(108,99,255,.28); border-color: var(--accent); color: var(--text); }
  .btn-fetch:disabled { opacity: .4; cursor: not-allowed; }

  .btn-continue {
    padding: 8px 18px;
    background: var(--warning);
    color: #000;
    border: none;
    border-radius: 8px;
    font-family: 'Heebo', sans-serif;
    font-weight: 700;
    font-size: .88rem;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .btn-continue:hover { opacity: .85; }

  /* ─── Re-categorize ─── */
  .btn-recat {
    background: none;
    border: 1px solid transparent;
    cursor: pointer;
    opacity: 0;
    font-size: .8rem;
    padding: 2px 7px;
    border-radius: 6px;
    transition: opacity .15s, background .15s, border-color .15s;
    color: var(--muted);
    flex-shrink: 0;
  }
  .txn-row:hover .btn-recat { opacity: 1; }
  .btn-recat:hover { background: rgba(255,255,255,.08); border-color: var(--border); color: var(--text); }

  .recat-select {
    background: var(--card);
    border: 1.5px solid var(--accent);
    border-radius: 6px;
    color: var(--text);
    font-family: 'Heebo', sans-serif;
    font-size: .82rem;
    padding: 3px 6px;
    cursor: pointer;
    flex-shrink: 0;
  }
</style>
</head>
<body>

<!-- Transaction Drawer -->
<div class="backdrop" id="backdrop" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
  <div class="drawer-head">
    <div>
      <div class="drawer-title" id="drawer-title"></div>
      <div class="drawer-total" id="drawer-total"></div>
    </div>
    <button class="btn-close" onclick="closeDrawer()">✕</button>
  </div>
  <div class="drawer-body" id="drawer-body"></div>
</div>

<div class="header">
  <div>
    <h1>📊 מנהל הוצאות</h1>
    <div class="subtitle">עיין בנתונים ואשר לפני השליחה לגוגל שיטס</div>
  </div>
  <button class="btn-fetch" id="fetchBtn" onclick="startFetch()">⬇ הורד נתונים</button>
</div>

<!-- Fetch Status Banner -->
<div class="fetch-banner" id="fetch-banner">
  <span id="fetch-message" style="flex:1"></span>
  <button class="btn-continue" id="fetch-continue-btn" onclick="continueFetch()" style="display:none">המשך ▶</button>
</div>

<!-- Month Tabs -->
<div class="tabs" id="tabs"></div>

<!-- Summary -->
<div class="summary" id="summary"></div>

<!-- Insights Panel -->
<div class="section-title">פינת הבוט הפיננסי 🤖</div>
<div class="insights-panel" id="insights-panel"></div>

<!-- Unclassified warning -->
<div id="unclassified-section"></div>

<!-- Expense categories -->
<div class="section-title">הוצאות</div>
<div class="grid" id="expense-grid"></div>

<!-- Income categories -->
<div class="section-title">הכנסות</div>
<div class="grid" id="income-grid"></div>

<!-- לא לחישוב drop zone -->
<div class="ignore-zone" id="ignore-zone"
     ondragover="zoneDragOver(event)" ondragleave="zoneDragLeave(event)" ondrop="zoneDrop(event)">
  <div class="iz-icon">🗑️</div>
  <div>
    <div class="iz-label">לא לחישוב</div>
    <div class="iz-hint">גרור עסקה לכאן כדי להוציא אותה מהחישוב לצמיתות</div>
  </div>
</div>

<!-- Actions -->
<div class="actions">
  <button class="btn-upload" id="uploadBtn" onclick="upload()">
    <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path d="M12 16V4m0 0L8 8m4-4l4 4M4 20h16"/>
    </svg>
    שלח ל-Google Sheets
  </button>
  <span class="status" id="status"></span>
</div>

<script>
let DATA = {};
let INCOME_CATS = [];
let UNCLASSIFIED = [];
let INSIGHTS = {};
let ALL_CATEGORIES = [];
let currentMonth = '';

// Fetch all data from the server API (avoids template escaping issues)
fetch('/data?t=' + Date.now())
  .then(r => r.json())
  .then(d => {
    DATA = d.results;
    INCOME_CATS = d.income_categories;
    UNCLASSIFIED = d.unclassified;
    INSIGHTS = d.insights;
    ALL_CATEGORIES = d.all_categories || [];
    // Default to the most recent month
    const keys = Object.keys(DATA).sort((a, b) => monthSortKey(a) - monthSortKey(b));
    currentMonth = keys[keys.length - 1] || '';
    renderAll();
  })
  .catch(e => document.body.innerHTML += '<p style="color:red">Error loading data: ' + e + '</p>');

function fmt(n) {
  return '₪' + Number(n).toLocaleString('he-IL', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

const MONTH_ORDER = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

function monthSortKey(key) {
  // key format: "JAN_26"
  const parts = key.split('_');
  const yr = parseInt(parts[1] || '0', 10);
  const mo = MONTH_ORDER.indexOf(parts[0]);
  return yr * 100 + (mo === -1 ? 0 : mo);
}

function renderTabs() {
  const tabs = document.getElementById('tabs');
  tabs.innerHTML = '';
  // Sort oldest→newest; RTL layout renders them visually Jan(right)→Dec(left)
  const sorted = Object.keys(DATA).sort((a, b) => monthSortKey(b) - monthSortKey(a));
  sorted.forEach(key => {
    const val = DATA[key];
    const t = document.createElement('button');
    t.className = 'tab' + (key === currentMonth ? ' active' : '');
    t.textContent = val.label;
    t.onclick = () => { currentMonth = key; renderAll(); };
    tabs.appendChild(t);
  });
}

function renderAll() {
  renderTabs();
  const d = DATA[currentMonth];
  const totals = d.totals;

  // ── Summary ──
  let incomeTotal = 0, expenseTotal = 0;
  Object.entries(totals).forEach(([cat, val]) => {
    if (cat === 'לא מסווג') return;
    if (INCOME_CATS.includes(cat)) incomeTotal += val;
    else expenseTotal += val;
  });
  const balance = incomeTotal - expenseTotal;

  document.getElementById('summary').innerHTML = `
    <div class="summary-card income">
      <div class="label">סה"כ הכנסות</div>
      <div class="value">${fmt(incomeTotal)}</div>
    </div>
    <div class="summary-card expense">
      <div class="label">סה"כ הוצאות</div>
      <div class="value">${fmt(expenseTotal)}</div>
    </div>
    <div class="summary-card balance">
      <div class="label">יתרה</div>
      <div class="value">${fmt(balance)}</div>
    </div>
    <div class="summary-card">
      <div class="label">עסקאות</div>
      <div class="value">${d.transactions_count}</div>
    </div>
  `;

  // ── Insights ──
  const inst = INSIGHTS[currentMonth] || {};
  document.getElementById('insights-panel').innerHTML = `
    <div class="insight-card anomaly">
      <div class="insight-title anomaly">📉 החריגה של החודש</div>
      <div class="insight-body">${inst.anomaly || ''}</div>
    </div>
    <div class="insight-card efficiency">
      <div class="insight-title efficiency">💡 המלצת התייעלות</div>
      <div class="insight-body">${inst.efficiency || ''}</div>
    </div>
    <div class="insight-card positive">
      <div class="insight-title positive">🎉 טפיחה על השכם</div>
      <div class="insight-body">${inst.positive || ''}</div>
    </div>
    <div class="insight-card projection">
      <div class="insight-title projection">🔮 חיזוי תקציב</div>
      <div class="insight-body">${inst.projection || ''}</div>
    </div>
  `;

  // ── Unclassified ──
  const uSection = document.getElementById('unclassified-section');
  if (UNCLASSIFIED.length > 0) {
    const items = UNCLASSIFIED.map((n, i) => {
      const safe = n.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return `<li draggable="true" data-idx="${i}" ondragstart="itemDragStart(event)">${safe}</li>`;
    }).join('');
    uSection.innerHTML = `
      <div class="warn-box">
        <h3>⚠️ עסקאות שלא סווגו — גרור כל פריט לקטגוריה המתאימה</h3>
        <ul id="unclassified-list">${items}</ul>
      </div>`;
  } else {
    uSection.innerHTML = '';
  }

  // ── Categories ──
  const expenses = Object.entries(totals).filter(([c]) => !INCOME_CATS.includes(c) && c !== 'לא מסווג');
  const incomes  = Object.entries(totals).filter(([c]) =>  INCOME_CATS.includes(c));

  const maxExp = Math.max(...expenses.map(([,v]) => v), 1);
  const maxInc = Math.max(...incomes.map(([,v]) => v), 1);

  expenses.sort((a,b) => b[1] - a[1]);
  incomes.sort((a,b) => b[1] - a[1]);
  
  const history_avgs = INSIGHTS[currentMonth]?.history_avgs || {};

  function makeCard(cat, val, max, type) {
    const pct = Math.min(Math.max(val / max, 0) * 100, 100);
    const safecat = cat.replace(/'/g, "\\'");
    
    // Trend Logic
    let trendHtml = '';
    const avg = history_avgs[cat];
    if (avg !== undefined) {
      // Allow a small 5% buffer to be considered "flat"
      const diff = val - avg;
      const isIncome = INCOME_CATS.includes(cat);
      if (Math.abs(diff) < (avg * 0.05) || Math.abs(diff) < 50) {
         trendHtml = '<div class="trend-arrow flat" title="אזור הממוצע">➖</div>';
      } else if (diff > 0) {
         // Val > Avg
         const classes = isIncome ? 'up good' : 'up bad';
         trendHtml = `<div class="trend-arrow ${classes}" title="מעל הממוצע (${fmt(avg)})">⬆️</div>`;
      } else {
         // Val < Avg
         const classes = isIncome ? 'down bad' : 'down good';
         trendHtml = `<div class="trend-arrow ${classes}" title="מתחת לממוצע (${fmt(avg)})">⬇️</div>`;
      }
    }

    return `<div class="cat-card ${type}" onclick="openDrawer('${safecat}')"
        ondragover="cardDragOver(event)" ondragleave="cardDragLeave(event)" ondrop="cardDrop(event,'${safecat}')">
        <div class="name">${cat}</div>
        <div class="amount-row">
          <div class="amount">${fmt(val)}</div>
          ${trendHtml}
        </div>
        <div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div>
      </div>`;
  }

  document.getElementById('expense-grid').innerHTML = expenses.map(([c,v]) => makeCard(c, v, maxExp, 'expense')).join('');
  document.getElementById('income-grid').innerHTML  = incomes.map(([c,v]) => makeCard(c, v, maxInc, 'income')).join('');
}

function openDrawer(cat) {
  const byCategory = (DATA[currentMonth] || {}).by_category || {};
  const txns = byCategory[cat] || [];
  const net = txns.reduce((s, t) => {
    if (INCOME_CATS.includes(cat)) return s + (t.amount > 0 ? t.amount : 0);
    return s + (t.amount < 0 ? Math.abs(t.amount) : -t.amount);
  }, 0);
  document.getElementById('drawer-title').textContent = cat;
  document.getElementById('drawer-total').textContent = 'סה"כ: ' + fmt(net);
  const sorted = [...txns].sort((a,b) => new Date(a.date) - new Date(b.date));
  document.getElementById('drawer-body').innerHTML = sorted.length === 0
    ? '<p style="color:var(--muted);text-align:center;margin-top:40px">אין עסקאות</p>'
    : sorted.map(t => {
        const encDesc = htmlEnc(t.description);
        return '<div class="txn-row">' +
          '<div style="flex:1;min-width:0">' +
            '<div class="txn-desc">' + t.description + '</div>' +
            '<div class="txn-date">' + t.date + '</div>' +
          '</div>' +
          '<div style="display:flex;align-items:center;gap:8px;flex-shrink:0">' +
            '<div class="txn-amount' + (t.amount > 0 ? ' credit' : '') + '">' + fmt(Math.abs(t.amount)) + '</div>' +
            '<button class="btn-recat" onclick="openRecat(this, &quot;' + encDesc + '&quot;)" title="שנה קטגוריה">&#9998;</button>' +
          '</div>' +
        '</div>';
      }).join('');
  document.getElementById('drawer').classList.add('open');
  document.getElementById('backdrop').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('backdrop').classList.remove('open');
}

// ── Drag & Drop ──────────────────────────────────────────────────────────────
let draggedBusiness = null;

function itemDragStart(event) {
  const idx = parseInt(event.target.dataset.idx, 10);
  draggedBusiness = UNCLASSIFIED[idx];
  event.target.classList.add('dragging');
  event.dataTransfer.setData('text/plain', String(idx));
  event.dataTransfer.effectAllowed = 'move';
}

document.addEventListener('dragend', function(event) {
  if (event.target && event.target.classList) {
    event.target.classList.remove('dragging');
  }
});

function cardDragOver(event) {
  if (!draggedBusiness) return;
  event.preventDefault();
  event.currentTarget.classList.add('drag-over');
}

function cardDragLeave(event) {
  event.currentTarget.classList.remove('drag-over');
}

function cardDrop(event, category) {
  event.preventDefault();
  event.currentTarget.classList.remove('drag-over');
  if (!draggedBusiness) return;
  classify(draggedBusiness, category);
}

function zoneDragOver(event) {
  if (!draggedBusiness) return;
  event.preventDefault();
  document.getElementById('ignore-zone').classList.add('drag-over');
}

function zoneDragLeave(event) {
  document.getElementById('ignore-zone').classList.remove('drag-over');
}

function zoneDrop(event) {
  event.preventDefault();
  document.getElementById('ignore-zone').classList.remove('drag-over');
  if (!draggedBusiness) return;
  classify(draggedBusiness, 'לא לחישוב');
}

function classify(business, category) {
  fetch('/classify', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ business, category })
  })
  .then(r => r.json())
  .then(d => {
    draggedBusiness = null;
    if (d.success) {
      UNCLASSIFIED = d.unclassified;
      DATA = d.results;
      renderAll();
    } else {
      alert('שגיאה בסיווג: ' + d.error);
    }
  })
  .catch(e => {
    draggedBusiness = null;
    alert('שגיאת רשת: ' + e);
  });
}

// ── Fetch / Download ─────────────────────────────────────────────────────────
let fetchPolling = null;

function startFetch() {
  const btn = document.getElementById('fetchBtn');
  btn.disabled = true;
  showFetchBanner('loading', 'מאתחל הורדה מהבנקים...');
  fetch('/fetch', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
    .then(r => r.json())
    .then(d => {
      if (d.success) {
        fetchPolling = setInterval(pollFetch, 1500);
      } else {
        showFetchBanner('error', 'שגיאה: ' + d.error);
        btn.disabled = false;
      }
    })
    .catch(e => { showFetchBanner('error', 'שגיאת רשת: ' + e); btn.disabled = false; });
}

function pollFetch() {
  fetch('/fetch/status')
    .then(r => r.json())
    .then(d => {
      if (d.done) {
        clearInterval(fetchPolling); fetchPolling = null;
        showFetchBanner('success', 'הורדה הושלמה! מרענן נתונים...');
        document.getElementById('fetchBtn').disabled = false;
        setTimeout(() => location.reload(), 1800);
      } else if (d.status === 'waiting') {
        showFetchBanner('waiting', d.message, d.bank);
      } else if (d.status === 'error') {
        clearInterval(fetchPolling); fetchPolling = null;
        showFetchBanner('error', d.message);
        document.getElementById('fetchBtn').disabled = false;
      } else {
        showFetchBanner('loading', d.message || 'מוריד נתונים...', d.bank);
      }
    })
    .catch(() => {}); // ignore transient network errors during polling
}

function continueFetch() {
  fetch('/fetch/continue', {method: 'POST'});
  document.getElementById('fetch-continue-btn').style.display = 'none';
  showFetchBanner('loading', 'ממשיך...');
}

function showFetchBanner(type, message, bank) {
  const banner = document.getElementById('fetch-banner');
  const msg    = document.getElementById('fetch-message');
  const btn    = document.getElementById('fetch-continue-btn');
  banner.style.display = 'flex';
  banner.className = 'fetch-banner fetch-' + type;
  msg.textContent = (bank ? '[' + bank + '] ' : '') + message;
  btn.style.display = (type === 'waiting') ? 'inline-flex' : 'none';
}

// ── Re-categorize ─────────────────────────────────────────────────────────────
function htmlEnc(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML.replace(/"/g, '&quot;');
}

function openRecat(btn, description) {
  const opts = ALL_CATEGORIES.map(c => '<option value="' + c + '">' + c + '</option>').join('');
  const sel = document.createElement('select');
  sel.className = 'recat-select';
  sel.innerHTML = '<option value="">העבר לקטגוריה...</option>' + opts;
  sel.onchange = function() { if (sel.value) reclassify(description, sel.value); };
  sel.onblur   = function() { sel.replaceWith(btn); }; // restore button if user cancels
  btn.parentNode.replaceChild(sel, btn);
  sel.focus();
}

function reclassify(description, category) {
  fetch('/classify', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({business: description, category: category})
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      DATA = d.results; UNCLASSIFIED = d.unclassified;
      closeDrawer();
      renderAll();
    } else { alert('שגיאה בסיווג: ' + d.error); }
  })
  .catch(e => alert('שגיאת רשת: ' + e));
}

function upload() {
  const btn = document.getElementById('uploadBtn');
  const status = document.getElementById('status');
  btn.disabled = true;
  status.className = 'status loading';
  status.textContent = '⏳ מעלה ל-Google Sheets...';

  fetch('/upload', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ month_key: currentMonth })
  })
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      status.className = 'status success';
      status.textContent = '✅ הועלה בהצלחה ל-Google Sheets!';
    } else {
      status.className = 'status error';
      status.textContent = '❌ שגיאה: ' + d.error;
    }
    btn.disabled = false;
  })
  .catch(e => {
    status.className = 'status error';
    status.textContent = '❌ שגיאת רשת: ' + e;
    btn.disabled = false;
  });
}

</script>
</body>
</html>
"""


@app.route("/")
def index():
    resp = render_template_string(HTML_TEMPLATE)
    if isinstance(resp, str):
        from flask import make_response
        resp = make_response(resp)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/data")
def data():
    """Returns all processed data as clean JSON — avoids Jinja2 escaping issues."""
    return jsonify({
        "results": RESULTS,
        "income_categories": list(INCOME_CATEGORIES),
        "unclassified": UNCLASSIFIED,
        "insights": INSIGHTS,
        "all_categories": ALL_CATEGORIES,
    })


@app.route("/debug-data")
def debug_data():
    """Raw dump of RESULTS totals — open in browser to diagnose empty UI."""
    out = {}
    for mk, v in RESULTS.items():
        out[mk] = {
            "label": v["label"],
            "transactions_count": v["transactions_count"],
            "totals": v["totals"],
        }
    return jsonify(out)


@app.route("/debug-raw")
def debug_raw():
    """Reads the Hapoalim file raw and returns first 30 rows with column indices.
    Open http://127.0.0.1:5050/debug-raw to see exactly what the parser reads."""
    import pandas as _pd
    results = {}
    inputs_dir = os.path.join(BASE_DIR, "inputs")
    for fname in os.listdir(inputs_dir):
        if "poalim" not in fname.lower() and "hapoalim" not in fname.lower():
            continue
        fpath = os.path.join(inputs_dir, fname)
        try:
            df = _pd.read_excel(fpath, header=None)
        except Exception as e:
            results[fname] = {"error": str(e)}
            continue
        rows = []
        for i, row in df.head(30).iterrows():
            row_dict = {f"col_{j}": str(v) for j, v in enumerate(row.values)}
            rows.append({"row_index": i, "cols": row_dict})
        results[fname] = rows
    return jsonify(results)


@app.route("/debug-max-tabs")
def debug_max_tabs():
    """Reads ALL sheets from the MAX file. Helps identify עסקאות חול column structure."""
    import pandas as _pd
    results = {}
    inputs_dir = os.path.join(BASE_DIR, "inputs")
    for fname in os.listdir(inputs_dir):
        if "max" not in fname.lower():
            continue
        fpath = os.path.join(inputs_dir, fname)
        try:
            xl = _pd.ExcelFile(fpath)
            sheet_data = {}
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name, header=None)
                rows = []
                for i, row in df.head(25).iterrows():
                    row_dict = {f"col_{j}": str(v) for j, v in enumerate(row.values)}
                    rows.append({"row_index": i, "cols": row_dict})
                sheet_data[sheet_name] = rows
            results[fname] = sheet_data
        except Exception as e:
            results[fname] = {"error": str(e)}
    return jsonify(results)


@app.route("/classify", methods=["POST"])
def classify():
    """
    Receives { "business": "<full description>", "category": "<Hebrew category>" }
    Writes the mapping into BUSINESS_MAP in processor.py, then re-processes all files.
    Returns { "success": true, "unclassified": [...] }
    """
    global RESULTS, UNCLASSIFIED, BUSINESSES, INSIGHTS
    try:
        data = request.json or {}
        business = str(data.get("business", "")).strip()
        category = str(data.get("category", "")).strip()

        if not business or not category:
            return jsonify({"success": False, "error": "חסר שם עסק או קטגוריה"})

        # Write to BUSINESS_MAP in processor.py
        processor_path = os.path.join(BASE_DIR, "processor.py")
        with open(processor_path, "r", encoding="utf-8") as f:
            source = f.read()

        anchor = "    # === עדכונים רלוונטיים חדשים ==="
        if anchor not in source:
            return jsonify({"success": False, "error": "לא נמצא anchor ב-processor.py"})

        # Escape the business name for safe insertion into Python source
        safe_business = business.replace("\\", "\\\\").replace('"', '\\"')
        safe_category = category.replace("\\", "\\\\").replace('"', '\\"')
        new_line = f'    "{safe_business}":                "{safe_category}",\n'

        # Insert after the anchor line
        source = source.replace(
            anchor + "\n",
            anchor + "\n" + new_line,
            1
        )

        with open(processor_path, "w", encoding="utf-8") as f:
            f.write(source)

        # Reload processor module so the new BUSINESS_MAP takes effect
        import importlib, sys
        if "processor" in sys.modules:
            importlib.reload(sys.modules["processor"])

        # Re-process all input files
        RESULTS, UNCLASSIFIED = process_all()
        BUSINESSES = list_businesses_with_categories()
        INSIGHTS = generate_insights(RESULTS)
        for _mk in RESULTS:
            RESULTS[_mk] = _sanitize(RESULTS[_mk])

        return jsonify({"success": True, "unclassified": UNCLASSIFIED, "results": RESULTS})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/fetch", methods=["POST"])
def fetch_banks():
    global _fetch_proc
    if _fetch_proc and _fetch_proc.poll() is None:
        return jsonify({"success": False, "error": "הורדה כבר רצה"})

    for f in [STATUS_FILE, CONTINUE_FILE]:
        if os.path.exists(f):
            os.remove(f)

    data = request.json or {}
    month = data.get("month", "")
    banks = data.get("banks", "hapoalim,cal,max")

    cmd = ["node", os.path.join(BASE_DIR, "scraper.js"), "--no-launch",
           "--banks", banks]
    if month:
        cmd += ["--month", month]

    _fetch_proc = subprocess.Popen(cmd)
    return jsonify({"success": True})


@app.route("/fetch/status")
def fetch_status():
    global RESULTS, UNCLASSIFIED, BUSINESSES, INSIGHTS, ALL_CATEGORIES
    if not os.path.exists(STATUS_FILE):
        return jsonify({"status": "idle", "bank": "", "message": "", "done": False})
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("done"):
            RESULTS, UNCLASSIFIED = process_all()
            BUSINESSES = list_businesses_with_categories()
            INSIGHTS = generate_insights(RESULTS)
            for _mk in RESULTS:
                RESULTS[_mk] = _sanitize(RESULTS[_mk])
            import importlib
            if "processor" in sys.modules:
                mod = importlib.reload(sys.modules["processor"])
                ALL_CATEGORIES = sorted(
                    set(mod.BUSINESS_MAP.values()) - {"התעלם", "לא לחישוב", "לא מסווג"}
                )
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "bank": "", "message": str(e), "done": False})


@app.route("/fetch/continue", methods=["POST"])
def fetch_continue():
    with open(CONTINUE_FILE, "w") as f:
        f.write("go")
    return jsonify({"success": True})


@app.route("/upload", methods=["POST"])
def upload():
    try:
        month_key = request.json.get("month_key")
        if month_key not in RESULTS:
            return jsonify({"success": False, "error": "חודש לא נמצא"})

        month_data = RESULTS[month_key]
        totals = month_data["totals"]
        month_label = month_data["label"]

        if not os.path.exists(CREDENTIALS_FILE):
            # Save locally as fallback
            out = os.path.join(BASE_DIR, f"debug_{month_key}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(totals, f, ensure_ascii=False, indent=2)
            return jsonify({"success": False, "error": f"אין credentials.json — נשמר מקומית ב-{out}"})

        from sheets_handler import SheetsHandler
        sheets = SheetsHandler(CREDENTIALS_FILE, SPREADSHEET_URL)
        sheets.update_monthly_row("2026", month_label, totals)
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5050")


if __name__ == "__main__":
    print("✅ Starting Expense Dashboard at http://127.0.0.1:5050")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(port=5050, debug=False)
