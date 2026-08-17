"""
rewrite_sheet_from_csv.py
Current CSV se Google Sheet ko pura rewrite karta hai.
"""
import sys, os
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import common

common.MAIN_CSV = "data_july_2026.csv"
common.DB_FILE  = "scraped_db_july_2026.json"

print("Connecting to Google Sheet...")
common.sheet = common.init_sheet("July")

print("Loading CSV...")
csv_rows = common.load_csv_rows()
print(f"CSV rows: {len(csv_rows)}")

wharton = sum(1 for r in csv_rows.values() if r.get("County","").upper() == "WHARTON")
print(f"Wharton rows in CSV: {wharton}")

print("Rewriting sheet from CSV (sheet clear + full rewrite)...")
common.reorder_google_sheet(csv_rows)
print("Done!")
