import gspread
from google.oauth2.service_account import Credentials


class SheetsHandler:
    def __init__(self, json_keyfile, spreadsheet_url):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.credentials = Credentials.from_service_account_file(
            json_keyfile, scopes=self.scopes
        )
        self.client = gspread.authorize(self.credentials)
        self.spreadsheet = self.client.open_by_url(spreadsheet_url)

    def update_monthly_row(self, sheet_name, month_str, category_totals):
        """
        Finds the row with 'month_str' in Column A and updates columns based on categories.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            print(f"Worksheet '{sheet_name}' not found.")
            return

        # 1. Find the row index for the month
        try:
            # Finding the cell that contains the month string.
            # Convert to string to be safe.
            # Note: This finds the FIRST occurrence.
            cell = worksheet.find(str(month_str))
            row_idx = cell.row
            print(f"Found '{month_str}' at row {row_idx}.")
        except gspread.CellNotFound:
            print(f"Month '{month_str}' not found in '{sheet_name}'.")
            return

        # 2. Map Categories to Columns (Hardcoded based on user headers)
        col_map = {
            "משכורות": "B",
            "הכנסות נוספות": "C",
            "משכנתה": "D",
            "גן": "E",
            "ארנונה": "F",
            "אינטרנט וטלויזיה": "G",
            "מים": "H",
            "חשמל גז": "I",
            "דלק רכב": "J",
            "חדר כושר": "K",
            "יציאות": "L",
            "צרכנות": "M",
            "בריאות": "N",
            "פסיכולוגית": "O",
            "ביטוחים (כולל רכב בריאות)": "P",
            "ועד בית": "Q",
            "משק בית": "R",
            "אוכל בבית": "S",
            "הוצאות כלב": "T",
            "הוצאות חריגות": "U",
            "נוסף טל": "V",
            "נוסף בן": "W",
        }
        
        ordered_cols = [
            "משכורות", "הכנסות נוספות", "משכנתה", "גן", "ארנונה", 
            "אינטרנט וטלויזיה", "מים", "חשמל גז", "דלק רכב", "חדר כושר", 
            "יציאות", "צרכנות", "בריאות", "פסיכולוגית", "ביטוחים (כולל רכב בריאות)", 
            "ועד בית", "משק בית", "אוכל בבית", "הוצאות כלב", "הוצאות חריגות", 
            "נוסף טל", "נוסף בן"
        ]
        
        row_values = []
        for cat in ordered_cols:
            val = category_totals.get(cat, 0)
            # Ensure val is a number (handle NaN)
            try:
                val = float(val)
                import math
                if math.isnan(val): val = 0.0
            except:
                val = 0.0
            row_values.append(round(val, 2))
            
        # Update range B{row}:W{row}
        # B is col 2, W is col 23.
        # worksheet.update(range_name, values)
        range_name = f"B{row_idx}:W{row_idx}"
        print(f"Updating range {range_name}...")
        worksheet.update(range_name=range_name, values=[row_values])
