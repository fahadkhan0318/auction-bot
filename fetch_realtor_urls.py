"""
fetch_realtor_urls.py — one-shot script
Fetches direct Realtor.com property URLs for all rows that have an address.
Updates CSV and syncs to Google Sheet.
"""
import sys, io, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
import common
from cad_scraper import fetch_realtor_direct_url, build_realtor_search_url

CSV_FILE = 'data_july_2026.csv'

common.MAIN_CSV = CSV_FILE
common.DB_FILE  = 'scraped_db_july_2026.json'
common.sheet    = common.init_sheet('July')

rows = {}
fields = []
with open(CSV_FILE, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames)
    for row in reader:
        rows[row['Unique Key']] = row

# Only process rows that have an address but no proper Realtor direct link yet
to_fetch = {
    uk: row for uk, row in rows.items()
    if row.get('Property Address', '').strip()
    and 'realestateandhomes-detail' not in row.get('Realtor', '')
}

print(f"\nFetching Realtor URLs for {len(to_fetch)} rows...\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=100)
    page    = browser.new_context().new_page()

    for uk, row in to_fetch.items():
        address = row['Property Address'].strip()
        print(f"  {uk} | {address}")
        url = fetch_realtor_direct_url(page, address)
        if not url:
            url = build_realtor_search_url(address)
            print(f"    ⚠️  Fallback search URL used")
        rows[uk]['Realtor'] = url

    browser.close()

# Save CSV
with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows.values():
        writer.writerow(row)
print('\nCSV saved.')

# Sync to sheet
csv_rows = common.load_csv_rows()
common.reorder_google_sheet(csv_rows)
print('Sheet synced!')
