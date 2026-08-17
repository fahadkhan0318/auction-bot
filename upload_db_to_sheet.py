import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import csv
import os

SHEET_URL = "https://docs.google.com/spreadsheets/d/17J2SZ3khk55iQrgxX9zl3wLUeCHPNqbQD_iG1_fxZZU/edit"

CSV_FIELDS = [
    "Unique Key",
    "County",
    "Cause Number",
    "Link",
    "Auction Date",
    "Status",
    "Min Bid",
    "Adjusted Value",
    "Property Address",
    "Account Number",
    "Legal Description",
    "Owner Name",
    "Buyer Name",
    "Sold Amount",
    "Winning Bid",
    "Sale Date",
    "Last Updated",
]

SHEET_HEADERS = [h for h in CSV_FIELDS if h != "Link"]


def init_sheet(worksheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(SHEET_URL)

    try:
        ws = spreadsheet.worksheet(worksheet_name)
        print(f"  📊 Existing tab found: '{worksheet_name}'")
    except Exception:
        ws = spreadsheet.add_worksheet(title=worksheet_name, rows=2000, cols=20)
        print(f"  ✅ New tab created: '{worksheet_name}'")

    return ws


def load_csv(csv_file):
    rows = {}
    if os.path.isfile(csv_file):
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                account = row.get("Account Number", "").strip()
                if account:
                    rows[account] = row
        print(f"  📄 CSV loaded: {csv_file} ({len(rows)} rows)")
    return rows


def make_hyperlink(link, cause_number):
    if link and cause_number:
        safe = cause_number.replace('"', "'")
        return f'=HYPERLINK("{link}","{safe}")'
    return cause_number or ""


def upload(db_file, csv_file, worksheet_name):
    if not os.path.isfile(db_file):
        print(f"❌ DB file not found: {db_file}")
        return

    with open(db_file, "r", encoding="utf-8") as f:
        db = json.load(f)
    print(f"🗄️  DB records: {len(db)}")

    csv_rows = load_csv(csv_file) if csv_file else {}

    rows_to_upload = []
    for account_num, db_entry in db.items():
        if account_num.startswith("__"):
            continue
        if account_num in csv_rows:
            row = csv_rows[account_num]
        else:
            row = {
                "Unique Key":        account_num,
                "Account Number":    account_num,
                "Cause Number":      db_entry.get("cause_number", ""),
                "Link":              db_entry.get("link", ""),
                "Status":            db_entry.get("status", ""),
                "County":            "",
                "Auction Date":      "",
                "Min Bid":           "",
                "Adjusted Value":    "",
                "Property Address":  "",
                "Legal Description": "",
                "Owner Name":        "",
                "Buyer Name":        "",
                "Sold Amount":       "",
                "Winning Bid":       "",
                "Sale Date":         "",
                "Last Updated":      db_entry.get("first_seen", ""),
            }

        link_url     = row.get("Link", "")
        cause_number = row.get("Cause Number", "")
        hyperlink    = make_hyperlink(link_url, cause_number)

        values = []
        for h in SHEET_HEADERS:
            if h == "Cause Number":
                values.append(hyperlink)
            else:
                values.append(row.get(h, ""))
        rows_to_upload.append(values)

    print(f"📊 Rows to upload: {len(rows_to_upload)}")
    print(f"🔗 Connecting to Google Sheet...")

    ws = init_sheet(worksheet_name)

    ws.clear()
    ws.append_row(SHEET_HEADERS)
    print(f"  ✅ Headers written")

    if rows_to_upload:
        ws.append_rows(rows_to_upload, value_input_option="USER_ENTERED")
        print(f"  ✅ {len(rows_to_upload)} rows uploaded to '{worksheet_name}' tab!")

    print(f"\n{'='*40}")
    print(f"✅ DONE! Data is now in the '{worksheet_name}' sheet tab.")
    print(f"{'='*40}")


if __name__ == "__main__":
    db_files = sorted([
        f for f in os.listdir(".")
        if f.startswith("scraped_db_") and f.endswith(".json") and f != "scraped_db.json"
    ])

    if not db_files:
        print("❌ No DB files found")
        exit()

    print(f"\n{'='*40}")
    print(f"  AVAILABLE DB FILES:")
    for i, f in enumerate(db_files):
        print(f"  {i+1}. {f}")
    print(f"{'='*40}")

    if len(db_files) == 1:
        selected_db = db_files[0]
        print(f"  Auto-selected: {selected_db}")
    else:
        choice = input("  Which DB to upload? (number): ").strip()
        try:
            selected_db = db_files[int(choice) - 1]
        except Exception:
            print("❌ Invalid choice")
            exit()

    # scraped_db_april_2026.json  ->  month_part = "april_2026"
    # sheet tab name              ->  "April 2026"
    month_part = selected_db.replace("scraped_db_", "").replace(".json", "")   # april_2026
    parts = month_part.split("_")          # ["april", "2026"]
    worksheet_name = f"{parts[0].title()} {parts[1]}"  # "April 2026"

    matching_csv = f"data_{month_part}.csv"
    if os.path.isfile(matching_csv):
        print(f"  ✅ Matching CSV found: {matching_csv}")
    else:
        print(f"  ⚠️  CSV not found ({matching_csv}), using DB data only")
        matching_csv = None

    print(f"  📋 Sheet tab: '{worksheet_name}'")
    upload(selected_db, matching_csv, worksheet_name)
