"""
restore_from_sheet.py
Google Sheet se July 2026 data restore karta hai CSV aur JSON DB mein.
"""
import sys, os, csv, json
from datetime import datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_URL  = "https://docs.google.com/spreadsheets/d/17J2SZ3khk55iQrgxX9zl3wLUeCHPNqbQD_iG1_fxZZU/edit"
TAB_NAME   = "July"
CSV_FILE   = "data_july_2026.csv"
DB_FILE    = "scraped_db_july_2026.json"
TODAY      = datetime.now().strftime("%Y-%m-%d")

CSV_FIELDS = [
    "Unique Key", "Source", "County", "Cause Number", "Item Number", "Link", "Auction Date",
    "Status", "Min Bid", "Adjusted Value", "Property Address",
    "Account Number", "Legal Description", "Owner Name", "Buyer Name",
    "Sold Amount", "Winning Bid", "Sale Date", "Last Updated",
    "Zillow", "Realtor", "Satellite View", "Appraisal District",
    "Interactive Map",
    "Improvement Homesite Value",
    "Improvement Non-Homesite",
    "Land Homesite Value",
    "Land Non-Homesite Value",
    "Ag Market Valuation",
]

def clean(v):
    if not v:
        return ""
    v = str(v).strip()
    # Sheet mein hyperlink formulas hoti hain, plain text nikalo
    if v.startswith("=HYPERLINK("):
        import re
        # =HYPERLINK("url","label") => url
        m = re.search(r'=HYPERLINK\("([^"]+)"', v)
        if m:
            return m.group(1)
    # Single quote prefix from sheet (Unique Key / Account Number)
    if v.startswith("'"):
        v = v[1:]
    return v

def run():
    print("Google Sheet se connect ho raha hoon...")
    scope  = ["https://spreadsheets.google.com/feeds",
               "https://www.googleapis.com/auth/drive"]
    creds  = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)

    spreadsheet = client.open_by_url(SHEET_URL)
    try:
        ws = spreadsheet.worksheet(TAB_NAME)
        print(f"Tab found: '{TAB_NAME}'")
    except Exception:
        print(f"Tab '{TAB_NAME}' nahi mila! Available tabs:")
        for s in spreadsheet.worksheets():
            print(f"  - {s.title}")
        sys.exit(1)

    print("Sheet data download ho raha hai...")
    all_values = ws.get_all_values()
    if not all_values:
        print("Sheet empty hai!")
        sys.exit(1)

    headers = [h.strip() for h in all_values[0]]
    print(f"Sheet headers: {len(headers)} columns")
    print(f"Sheet rows (incl header): {len(all_values)}")

    # Find Unique Key column
    try:
        uk_col = headers.index("Unique Key")
    except ValueError:
        # Try without exact case
        uk_col = next((i for i, h in enumerate(headers) if "unique" in h.lower()), None)
        if uk_col is None:
            print("'Unique Key' column nahi mila!")
            print(f"Available headers: {headers}")
            sys.exit(1)

    # Build rows dict
    rows = {}
    skipped = 0
    for raw_row in all_values[1:]:
        # Pad short rows
        while len(raw_row) < len(headers):
            raw_row.append("")

        row_dict = {headers[i]: clean(raw_row[i]) for i in range(len(headers))}

        uk = row_dict.get("Unique Key", "").strip()
        if not uk:
            skipped += 1
            continue

        # Map sheet columns to CSV fields
        out = {f: "" for f in CSV_FIELDS}
        for field in CSV_FIELDS:
            if field in row_dict:
                out[field] = row_dict[field]
            elif field == "Link":
                # Link column might not be in sheet (it's the hyperlink source)
                out[field] = row_dict.get("Link", "")

        out["Unique Key"] = uk
        rows[uk] = out

    print(f"Rows loaded from sheet: {len(rows)}  (skipped empty: {skipped})")

    if len(rows) == 0:
        print("Koi data nahi mila — sheet empty ya format mismatch")
        sys.exit(1)

    # ── Write CSV ─────────────────────────────────────────────────────────────
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows.values():
            writer.writerow(row)
    print(f"CSV saved: {CSV_FILE} ({len(rows)} rows)")

    # ── Rebuild JSON DB ───────────────────────────────────────────────────────
    # Load existing DB to preserve any extra fields
    db = {}
    if os.path.isfile(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    db = json.loads(content)
            print(f"Existing DB loaded: {len(db)} records")
        except Exception as e:
            print(f"DB load error (fresh start): {e}")

    added = 0
    for uk, row in rows.items():
        if uk not in db:
            db[uk] = {
                "status":       row.get("Status", "Pending"),
                "first_seen":   row.get("Last Updated", TODAY),
                "source":       row.get("Source", ""),
                "county":       row.get("County", ""),
                "cause_number": row.get("Cause Number", ""),
                "section":      "restored from sheet",
            }
            added += 1
        else:
            db[uk]["status"] = row.get("Status", db[uk].get("status", "Pending"))

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    print(f"DB  saved: {DB_FILE} ({len(db)} records, {added} newly added)")
    print(f"\nRestore complete! {len(rows)} rows restored from Google Sheet.")


if __name__ == "__main__":
    run()
