import pandas as pd
import os
import re
import datetime

# ---------------------------------------------------------------------------
# BUSINESS MAP: exact (partial) name -> Hebrew category
# Checked first before keyword fallback. Add new businesses here.
# ---------------------------------------------------------------------------
BUSINESS_MAP = {
    # אוכל בבית
    "רמי לוי - רמת":           "אוכל בבית",
    "רמי לוי אינטרנט":         "אוכל בבית",   # ארנק / קניות אונליין
    "רמי לוי":                  "אוכל בבית",
    "כל בו זול":                "אוכל בבית",
    "אורי עזריה":               "אוכל בבית",
    "(שוק נווה שרת )טירני ימין": "אוכל בבית",
    "carrefour":                "אוכל בבית",
    "החישוק":                   "אוכל בבית",
    "הירקן החייכן":             "אוכל בבית",
    "מינימרקט אדל":             "אוכל בבית",
    'קפה רות בע"מ':             "אוכל בבית",

    # יציאות (מסעדות, קפה, משלוחים)
    "wolt":                     "יציאות",
    "yango deli":               "יציאות",
    "אושר בפיתה":               "יציאות",
    "בוטיק פטיסרי":             "יציאות",
    "בלונזרי 96":               "יציאות",
    "יאמי מחברים":              "יציאות",
    "מאפיית המשפחה":            "יציאות",
    "מגזינו":                   "יציאות",
    "פרנק נקניקייה":            "יציאות",
    "קופי טיים":                "יציאות",
    "קפה דודה":                 "יציאות",
    "אוטלו גולף":               "יציאות",
    "א. א גרציאני":             "יציאות",
    "עלמה רמת השרון":           "יציאות",
    "רוג'ר פארק":               "יציאות",
    "tomoko":                   "יציאות",
    "אוטלו כיכר המושבה":        "יציאות",
    "אפטר תשע":                 "יציאות",
    "גו נודלס":                 "יציאות",
    "מסעדת כחול חוף תל ברוך":   "יציאות",
    "מקדונלד'ס":                "יציאות",
    "מתחת לעץ אפקה":            "יציאות",
    "נונומימי כיכר המושבה":     "יציאות",
    "פורת יעקב והראל":          "יציאות",
    "פיצה שמש":                 "יציאות",
    'רביבה וסיליה':             "יציאות",
    "שווארמה אליהו":            "יציאות",

    # דלק רכב (דלק, חניה, אגרת כביש, תחבורה)
    "סונול":                    "דלק רכב",
    "דלק מיקה":                 "דלק רכב",
    "פנגו":                     "דלק רכב",
    "מוביט":                    "דלק רכב",
    "דרך ארץ":                  "דלק רכב",
    "משרד התחבורה":             "דלק רכב",
    "אחוזות החוף":              "דלק רכב",   # חניון
    "אחוזת חוף":                "דלק רכב",   # חניון
    "חניון מגדל":               "דלק רכב",   # חניון
    "מבדק":                     "דלק רכב",   # בדיקת רכב / טסט
    "בררת משפט":                "דלק רכב",   # קנס תנועה
    "הדר אביזרי רכב":           "דלק רכב",
    "חניון כיכר המושבה":        "דלק רכב",
    "מוסכי רמת החייל":          "דלק רכב",
    "עתידים חניון":             "דלק רכב",
    "פז yellow":                "דלק רכב",
    "רן צמיג ותקר":             "דלק רכב",

    # אינטרנט וטלויזיה
    "yes":                      "אינטרנט וטלויזיה",
    "סלקום":                    "אינטרנט וטלויזיה",
    "google one":               "אינטרנט וטלויזיה",

    # חשמל גז
    "חברת החשמל":               "חשמל גז",
    'ש.א.מ. מרכז הגז':          "חשמל גז",

    # מים
    "מי אביבים":                "מים",

    # ביטוחים (כולל רכב בריאות)
    "ביטוח ישיר":               "ביטוחים (כולל רכב בריאות)",
    "הראל-ביטוח":               "ביטוחים (כולל רכב בריאות)",
    "ליברה ביטוח":              "ביטוחים (כולל רכב בריאות)",
    "ליברה עסקאות ביטוח":       "ביטוחים (כולל רכב בריאות)",
    "בטוח לאומי":               "ביטוחים (כולל רכב בריאות)",
    "מס הכנסה -ביטוח חפצים ביתיים": "ביטוחים (כולל רכב בריאות)",

    # בריאות
    "סופר פארם":                "בריאות",
    "קרן מכבי":                 "בריאות",
    "דיאט אנג'ל":               "בריאות",
    'בית מרקחת יהודית':         "בריאות",
    "סופרפארם שיכון דן":        "בריאות",
    'קופת חולים מכבי':          "בריאות",

    # הוצאות כלב
    "מרפאט":                    "הוצאות כלב",

    # צרכנות
    "aliexpress":               "צרכנות",
    "paypal":                   "צרכנות",
    "טרמינל איקס":              "צרכנות",
    "שילב":                     "צרכנות",
    "bit":                      "צרכנות",
    "שרותי הדר":                "צרכנות",
    "סיטונאות חד פעמי נווה שרת": "צרכנות",

    # משק בית
    "paybox":                   "משק בית",

    # חדר כושר / ספורט
    "בריכת און":                "חדר כושר",
    "מ. התחבורה":               "חדר כושר",   # upapp/memobi?
    "upapp":                    "חדר כושר",
    "מ.קהילתי":                 "חדר כושר",

    # גן / חינוך
    "מחוג חינוך":               "גן",
    "נטעים":                    "גן",   # catches: עמותת נטעים, נטעים עמותה, etc.
    "בביקו קר":                  "גן",
    "המשכיל":                   "גן",

    # ספורט / חדר כושר
    "מוסדות חינוך":             "חדר כושר",   # unified under חדר כושר

    # ועד בית
    "association tmb":          "הוצאות חריגות",   # מסווג ידני
    "ועד הבית כורזים":          "ועד בית",

    # פסיכולוגית — שמות מטפלות + החזר ביטוח לאומי מקזז
    "גלי גורן":                 "פסיכולוגית",
    "הילה פרנס":                "פסיכולוגית",
    "בטוח לאומי":               "פסיכולוגית",   # כל ווריאנט (חד/חודשי) מקזז עלות טיפול

    # שכירות
    "שכירות":                   "שכירות",

    # משכנתה — כל הווריאנטים הנפוצים
    "לאומי למשכנתא":            "משכנתה",
    "לאומי למשכנתאות":          "משכנתה",
    "משכנתאות":                  "משכנתה",
    "mashkanta":                 "משכנתה",
    "הלוואת משכנתא":             "משכנתה",

    # הכנסות נוספות
    "קצבת ילדים":               "הכנסות נוספות",
    "אריאל טלילה":              "הכנסות נוספות",

    # משכורות
    "מאיר בית חולים":           "משכורות",
    "שרותי בריאות כ עבור: בכור טל מזהה 312491392": "משכורות",
    "שרותי בריאות כללית":       "משכורות",
    "בכור טל":                  "משכורות",

    # אינטרנט / מנויים (חו"ל)
    "amazon prime":             "אינטרנט וטלויזיה",
    "amazon":                   "אינטרנט וטלויזיה",
    "apple.com":                "אינטרנט וטלויזיה",   # iCloud, Apple Music, Apple TV
    "icloud":                   "אינטרנט וטלויזיה",

    # יציאות / אוכל מחוץ לבית (חו"ל)
    "wolt":                     "יציאות",

    # אוכל בבית (חו"ל)
    "yango deli":               "אוכל בבית",
    "yango":                    "אוכל בבית",

    # צרכנות (חו"ל) — כל PayPal + חנויות ספציפיות
    "paypal":                   "צרכנות",     # כולל temu, next, myprotein, אחרים
    "next online":              "צרכנות",
    "temu":                     "צרכנות",

    # משק בית — העברות דיגיטליות (paybox/bit לחברים, שכנים, שירותים)
    "paybox":                   "משק בית",
    "bit":                      "משק בית",
    
    # הוצאות נוספות
    "כספומט הפועלים":           "הוצאות נוספות",
    "לובי 99":                  "הוצאות נוספות",

    # === עדכונים רלוונטיים חדשים ===
    "א.ש. אביעם  סחר  בע''ם-מי":                "צרכנות",
    "claude":                   "צרכנות",
    "anthropic":                "צרכנות",
    "myprotein":                "אוכל בבית",
    'א.ש אביעם סחר בע"מ':       "צרכנות",
    "מסעדת למעלה":              "יציאות",
    "דראגסטור מאיר":            "בריאות",
    "בן פיצה":                  "יציאות",
    "דיילי מאיר":               "יציאות",
    "דלתא":                     "צרכנות",
    "העב' קרולין אדרי":         "צרכנות",
    "העברה רוני בירנבוים":      "התעלם",
    "בובש טל":                  "התעלם",
    "חומוס יוסף":               "יציאות",
    "חניון הנצח":               "דלק רכב",
    "טעימים":                   "יציאות",
    "כספומט לאומי":             "משק בית",
    "מקדונלדס":                 "יציאות",
    "מש-קר":                    "יציאות",
    "משיכה מבנקט":              "משק בית",
    "משקט":                     "יציאות",
    "צ'יקטי":                   "יציאות",
    "קוק סטוק":                 "אוכל בבית",
    "שופרסל שלי צהלה":          "אוכל בבית",
    "שייק שאק":                 "יציאות",

    "אביעם סחר":                "צרכנות",
    "אחוזות חוף":               "דלק רכב",
    "דראגסטורס מאיר":           "בריאות",
    "קרולין אדרי":              "צרכנות",
    "רוני בירנבוים":            "התעלם",
    "מש - קר":                  "יציאות",
}

# ---------------------------------------------------------------------------
# INCOME_CATEGORIES: categories where positive amounts = income (not refunds)
# Used by aggregate_data() and app.py display logic.
# ---------------------------------------------------------------------------
INCOME_CATEGORIES = {"משכורות", "הכנסות נוספות"}
EXCLUDED_CATEGORIES = {"לא לחישוב"}  # Like "התעלם" — filtered from balance & display

class CSVProcessor:
    def __init__(self):
        # Tracks businesses that couldn't be classified this run
        self.unclassified_businesses = set()

        # Maps keyword -> Hebrew category (fallback when BUSINESS_MAP has no match)
        self.categories = {
            "אוכל בבית":                    ["shufersal", "super", "remy", "machsane", "makolet", "store", "market", "coop", "food", "zol"],
            "דלק רכב":                       ["pango", "moovit", "lime", "bird", "fuel", "dor", "delek", "paz", "sonol", "ten"],
            "יציאות":                        ["pizza", "burger", "aroma", "cafe", "restaurant", "coffee", "mcdonald", "arcaffe", "landwer", "greg"],
            "אינטרנט וטלויזיה":             ["telecom", "bezeq", "hot", "partner", "cellcom", "netflix", "disney", "spotify"],
            "חשמל גז":                       ["electric", "iec", "gas", "pazgas", "amisragas"],
            "מים":                           ["water", "mei", "hagihon"],
            "ארנונה":                        ["arnona", "muni"],
            "ביטוחים (כולל רכב בריאות)":   ["insurance", "harel", "migdal", "menora", "clal", "fenix", "bituach"],
            "בריאות":                        ["pharm", "super-pharm", "maccabi", "clalit", "meuhedet", "leumit", "health", "doctor"],
            "צרכנות":                        ["zara", "h&m", "fox", "castro", "asos", "amazon", "aliexpress", "paypal", "temu", "shein", "ksp", "ivory"],
            "משק בית":                       ["ikea", "ace", "home center", "stock"],
            "הוצאות כלב":                   ["dog", "pet", "vet", "chayat"],
            "חדר כושר":                     ["gym", "fit", "studio", "holmes", "go active"],
            "גן":                            ["gan", "wizo", "naamat"],
            "ועד בית":                       ["vaad", "committee"],
            "משכורות":                       ["salary", "maskoret"],
        }

    def categorize(self, description, amount):
        """
        Classification priority:
          1. BUSINESS_MAP  – partial match on known business names
          2. self.categories  – keyword fallback
          3. Added to self.unclassified_businesses → shown in popup at end of run

        ❌ NEVER returns "הוצאות חריגות" automatically.
        """
        desc_lower = str(description).strip().lower()

        # Custom explicit logic for Tel Aviv Municipality (salary vs arnona)
        if "עיריית" in desc_lower and "ת" in desc_lower and "א" in desc_lower:
            return "משכורות" if amount > 0 else "ארנונה"

        # 1. Exact business map (partial match)
        for biz_name, category in BUSINESS_MAP.items():
            if biz_name.lower() in desc_lower:
                return category

        # 2. Keyword fallback
        for category, keywords in self.categories.items():
            if any(kw in desc_lower for kw in keywords):
                return category

        # 3. Unknown – collect for popup alert at end of run
        self.unclassified_businesses.add(str(description).strip())
        return "לא מסווג"

    def show_unclassified_alert(self):
        """
        Call this once after all files are processed.
        Shows a tkinter popup listing every business that couldn't be classified.
        If tkinter is unavailable, prints to terminal instead.
        """
        if not self.unclassified_businesses:
            return  # Nothing to report

        names = sorted(self.unclassified_businesses)
        message = (
            "⚠️  העסקים הבאים לא סווגו — אנא עדכן את BUSINESS_MAP ב-processor.py:\n\n"
            + "\n".join(f"  • {n}" for n in names)
        )

        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()  # Hide the empty root window
            root.attributes("-topmost", True)
            messagebox.showwarning(
                title="⚠️  עסקאות לא מסווגות",
                message=message,
            )
            root.destroy()
        except Exception:
            # Fallback: print to terminal if tkinter not available
            print("\n" + "=" * 50)
            print(message)
            print("=" * 50 + "\n")


    def aggregate_data(self, all_transactions):
        """
        Aggregates transactions by category.
        - Income categories (INCOME_CATEGORIES): positive amounts add to total.
        - Expense categories: negative amounts add (as abs). Positive amounts
          SUBTRACT (they are refunds/reimbursements, e.g. בט"ל החזר).
        Returns: { "CategoryName": NetAmount }
        """
        totals = {}
        for t in all_transactions:
            cat = t['Category']
            amount = t['Amount']
            if pd.isna(amount): amount = 0

            if cat in INCOME_CATEGORIES:
                # Income: only count credits (positive)
                val = amount if amount > 0 else 0
            else:
                # Expense: debit (negative) → add abs value
                #          credit (positive) → subtract (it's a refund)
                val = abs(amount) if amount < 0 else -amount

            totals[cat] = totals.get(cat, 0) + val

        return totals

    def clean_currency(self, val):
        """Parse a currency value to float. Never returns NaN."""
        if pd.isna(val) if hasattr(pd, 'isna') else val != val:
            return 0.0
        if isinstance(val, str):
            val = re.sub(r'[^\d.-]', '', val)
            try:
                return float(val)
            except ValueError:
                return 0.0
        try:
            f = float(val)
            return 0.0 if f != f else f  # guard against NaN
        except (TypeError, ValueError):
            return 0.0

    def load_file(self, file_path):
        """
        Loads CSV, XLS, or XLSX into a DataFrame.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.xls', '.xlsx']:
            # Excel files usually handle encoding correctly
            return pd.read_excel(file_path, header=None)
        else:
            # CSV Fallback
            try:
                return pd.read_csv(file_path, encoding='cp1255', header=None)
            except Exception:
                return pd.read_csv(file_path, encoding='utf-8', header=None, on_bad_lines='skip')

    def parse_hapoalim(self, file_path):
        """
        Parses Bank Hapoalim Excel/CSV.
        Detects column positions dynamically from the header row so it works
        regardless of whether the file has 1 or 2 date columns.
        """
        df = self.load_file(file_path)

        # ── Find header row (contains "תאריך") ───────────────────────────────
        header_row_idx = -1
        header_values = []
        for i, row in df.iterrows():
            row_str = " ".join([str(x) for x in row.values])
            if "תאריך" in row_str or "Date" in row_str:
                header_row_idx = i
                header_values = [str(x).strip() for x in row.values]
                break

        if header_row_idx != -1:
            df = df.iloc[header_row_idx + 1:]

        # ── Detect column indices from header ─────────────────────────────────
        def col_idx(keywords):
            """Return first column index whose header contains any keyword."""
            for kw in keywords:
                for i, h in enumerate(header_values):
                    if kw in h:
                        return i
            return None

        date_col   = col_idx(["תאריך"]) or 0
        desc_col   = col_idx(["תיאור", "description"]) or 1
        detail_col = col_idx(["פרטים", "detail", "מסמך"]) or (desc_col + 1)
        debit_col  = col_idx(["חובה", "debit"]) or 4
        credit_col = col_idx(["זכות", "credit"]) or 5

        processed_data = []

        for _, row in df.iterrows():
            row_list = row.values.tolist()
            if len(row_list) <= desc_col:
                continue

            date        = str(row_list[date_col])
            description = str(row_list[desc_col])
            details     = str(row_list[detail_col]) if len(row_list) > detail_col else ""

            # Classification uses description + details so beneficiary names
            # in the details column (e.g. עמותת נטעים) are matched
            classification_text = f"{description} {details}".strip()

            if "תאריך" in date or date == "nan":
                continue
            try:
                if pd.isna(date):
                    continue
            except Exception:
                pass

            debit_val  = row_list[debit_col]  if len(row_list) > debit_col  else 0
            credit_val = row_list[credit_col] if len(row_list) > credit_col else 0

            debit  = self.clean_currency(debit_val)
            credit = self.clean_currency(credit_val)
            amount = credit - debit

            # Filter out credit card bill payments
            if "כרטיסי אשראי" in description or "מקס איט" in description:
                continue

            category = self.categorize(classification_text, amount)
            if category in ("התעלם", "לא לחישוב"):
                continue

            # Display: show description with details when meaningful
            display_desc = description
            if details and details not in ("nan", "", description):
                display_desc = f"{description} | {details}"

            processed_data.append({
                "Date":        date,
                "Description": display_desc,
                "Amount":      amount,
                "Category":    category,
            })

        return processed_data


    def parse_scraped_json(self, file_path):
        """
        Parses JSON output from israeli-bank-scrapers (scraper.js).
        Each transaction has: date, description, memo, chargedAmount, status.
        Negative chargedAmount = expense, positive = income/refund.
        """
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            txns = json.load(f)

        processed_data = []
        for t in txns:
            if t.get("status") == "pending":
                continue

            date_raw    = str(t.get("date", ""))[:10]   # "2026-04-15T..." → "2026-04-15"
            description = str(t.get("description", "")).strip()
            memo        = str(t.get("memo", "")).strip()
            amount      = float(t.get("chargedAmount") or 0)

            classification_text = f"{description} {memo}".strip()
            category = self.categorize(classification_text, amount)
            if category in ("התעלם", "לא לחישוב"):
                continue

            display_desc = description
            if memo and memo not in ("", "nan", description):
                display_desc = f"{description} | {memo}"

            processed_data.append({
                "Date":        date_raw,
                "Description": display_desc,
                "Amount":      amount,
                "Category":    category,
            })

        return processed_data

    def parse_cal(self, file_path):
        return self._parse_generic_card(file_path, "CAL", charge_col_idx=3)

    def parse_max(self, file_path):
        return self._parse_generic_card(file_path, "MAX", charge_col_idx=5)

    def _parse_card_sheet(self, df, charge_col_idx):
        """Parse a single card sheet DataFrame into transaction list."""
        # Find header row containing "תאריך עסקה"
        header_row_idx = -1
        for i, row in df.iterrows():
            row_str = " ".join([str(x) for x in row.values])
            if "תאריך" in row_str and "עסקה" in row_str:
                header_row_idx = i
                break

        if header_row_idx != -1:
            df = df.iloc[header_row_idx + 1:]

        date_pattern = re.compile(r'^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}')
        processed_data = []

        for _, row in df.iterrows():
            row_list = row.values.tolist()

            raw_date = row_list[0]
            if isinstance(raw_date, (pd.Timestamp, datetime.datetime)):
                date = raw_date.strftime("%d/%m/%Y")
            else:
                date = str(raw_date).strip()
                if not date_pattern.match(date):
                    continue

            description = str(row_list[1])

            amount = 0
            try:
                if len(row_list) > charge_col_idx:
                    val = self.clean_currency(row_list[charge_col_idx])
                    if val != 0:
                        amount = -val   # positive = expense, negative = refund
            except:
                amount = 0

            category = self.categorize(description, amount)
            if category in ("התעלם", "לא לחישוב"):
                continue
            processed_data.append({
                "Date": date,
                "Description": description,
                "Amount": amount,
                "Category": category,
            })

        return processed_data

    def _parse_generic_card(self, file_path, source_name, charge_col_idx=3):
        """
        Generic parser for card Excel/CSV.
        If the file has multiple sheets, ALL sheets are parsed and merged.
        This handles MAX's 'עסקאות חול' tab automatically.
        """
        ext = os.path.splitext(file_path)[1].lower()
        all_data = []

        if ext in ['.xls', '.xlsx']:
            xl = pd.ExcelFile(file_path)
            sheet_names = xl.sheet_names
            print(f"  [{source_name}] {len(sheet_names)} sheet(s): {sheet_names}")
            for sheet_name in sheet_names:
                df = xl.parse(sheet_name, header=None)
                rows = self._parse_card_sheet(df, charge_col_idx)
                if rows:
                    print(f"    sheet '{sheet_name}': {len(rows)} transactions")
                all_data.extend(rows)
        else:
            # CSV — single sheet only
            try:
                df = pd.read_csv(file_path, encoding='cp1255', header=None)
            except Exception:
                df = pd.read_csv(file_path, encoding='utf-8', header=None, on_bad_lines='skip')
            all_data = self._parse_card_sheet(df, charge_col_idx)

        return all_data


# ---------------------------------------------------------------------------
# all_display_categories(): every category that should appear in the UI,
# even when it has no transactions in the selected month — so the user can
# always drag an unclassified expense onto it (e.g. חשמל גז).
# Sources: BUSINESS_MAP values + keyword-fallback categories + income cats.
# ---------------------------------------------------------------------------
def all_display_categories():
    cats = set(BUSINESS_MAP.values())
    cats |= set(CSVProcessor().categories.keys())
    cats |= set(INCOME_CATEGORIES)
    cats -= {"התעלם", "לא לחישוב", "לא מסווג"}
    return sorted(cats)
