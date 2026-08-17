"""
sync_missing_to_sheet.py
CSV mein jo rows hain lekin sheet mein nahi, unhe push karta hai.
"""
import sys, os, csv
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import common

common.MAIN_CSV = "data_july_2026.csv"
common.DB_FILE  = "scraped_db_july_2026.json"

print("Google Sheet se connect ho raha hoon...")
common.sheet = common.init_sheet("July")

print("CSV load ho raha hai...")
csv_rows = common.load_csv_rows()
print(f"CSV rows: {len(csv_rows)}")

print("Sheet ke saath sync ho raha hai...")
common.sync_csv_to_sheet(csv_rows)
print("Done!")
