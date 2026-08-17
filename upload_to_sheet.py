import gspread
from oauth2client.service_account import ServiceAccountCredentials
import csv
import os
import time

SHEET_URL = "https://docs.google.com/spreadsheets/d/17J2SZ3khk55iQrgxX9zl3wLUeCHPNqbQD_iG1_fxZZU/edit"

CSV_FIELDS = [
    "Unique Key",
    "Source",
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
    "Zillow",
    "Satellite View",
    "Appraisal District",
    "Property Map",
    "Interactive Map",
    "Improvement Homesite Value",
    "Improvement Non-Homesite",
    "Land Homesite Value",
    "Land Non-Homesite Value",
    "Ag Market Valuation",
]

# Sheet mein Link column nahi hoga - Cause Number pe hyperlink lagega
SHEET_FIELDS = [f for f in CSV_FIELDS if f != "Link"]

# Yeh columns plain text mein rakho
TEXT_COLUMNS = {
    "Unique Key",
    "Source",
    "Account Number",
    "County",
    "Cause Number",
    "Property Address",
    "Legal Description",
    "Owner Name",
    "Buyer Name",
}


def init_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).sheet1


def retry(fn, retries=5, delay=5):
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            print(f"  ⚠️ Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                wait = delay * attempt
                print(f"  ⏳ {wait} seconds wait kar raha hai...")
                time.sleep(wait)
            else:
                raise


def col_letter(col_idx_1based):
    result = ""
    n = col_idx_1based
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def format_all_columns(sheet):
    try:
        for col_name in TEXT_COLUMNS:
            if col_name in SHEET_FIELDS:
                idx = SHEET_FIELDS.index(col_name) + 1
                letter = col_letter(idx)
                sheet.format(f"{letter}:{letter}", {"numberFormat": {"type": "TEXT"}})
                print(f"  ✅ '{col_name}' ({letter}) -> TEXT")
                time.sleep(0.3)
    except Exception as e:
        print(f"  ⚠️ Format error: {e}")


def clean_value(val):
    if val is None:
        return ""
    val = str(val).strip()
    val = val.replace("\n", " ").replace("\r", " ")
    return val


def sort_rows_by_county(rows):
    """
    Rows ko county ke hisaab se group karo.
    Ek county ke saare records saath aayenge,
    phir next county, phir next — alphabetical order mein.
    Har county ke andar Auction Date se sort.
    """
    from collections import defaultdict

    county_groups = defaultdict(list)

    for row in rows:
        county = clean_value(row.get("County", "")).upper()
        county_groups[county].append(row)

    # Har county ke andar Auction Date se sort karo
    for county in county_groups:
        county_groups[county].sort(key=lambda r: clean_value(r.get("Auction Date", "")))

    # Counties alphabetically sort karo
    sorted_counties = sorted(county_groups.keys())

    print(f"\n  📋 County order:")
    sorted_rows = []
    for county in sorted_counties:
        count = len(county_groups[county])
        print(f"     {county}: {count} rows")
        sorted_rows.extend(county_groups[county])

    return sorted_rows


def upload_csv_to_sheet(csv_file):
    if not os.path.isfile(csv_file):
        print(f"❌ CSV file nahi mila: {csv_file}")
        return

    print(f"📄 Reading CSV: {csv_file}")
    rows = []
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"📊 Total rows in CSV: {len(rows)}")

    # ✅ County ke hisaab se sort karo
    rows = sort_rows_by_county(rows)

    print("🔗 Google Sheet se connect ho raha hai...")
    sheet = init_sheet()

    # Step 1: Sheet clear karo
    retry(lambda: sheet.clear())
    print("🧹 Sheet clear ho gayi")
    time.sleep(3)

    # Step 2: TEXT format lagao
    print("🔧 Columns TEXT format set kar raha hai...")
    format_all_columns(sheet)
    time.sleep(2)

    # Step 3: Headers daalo
    retry(lambda: sheet.append_row(SHEET_FIELDS, value_input_option="RAW"))
    print(f"✅ Headers add kiye: {len(SHEET_FIELDS)} columns")
    time.sleep(2)

    if not rows:
        print("⚠️ CSV mein koi data nahi mila")
        return

    cn_col_idx = SHEET_FIELDS.index("Cause Number")
    zillow_col_idx = SHEET_FIELDS.index("Zillow")
    sat_col_idx = SHEET_FIELDS.index("Satellite View")

    all_values = []
    for row in rows:
        values = []
        for field in SHEET_FIELDS:
            val = clean_value(row.get(field, ""))

            if field in {"Unique Key", "Account Number"} and val:
                val = "'" + val

            values.append(val)

        # Cause Number pe hyperlink
        link_url = clean_value(row.get("Link", ""))
        cause_number = clean_value(row.get("Cause Number", ""))
        if link_url and cause_number:
            safe_link = link_url.replace('"', "%22")
            safe_cn = cause_number.replace('"', "'")
            values[cn_col_idx] = f'=HYPERLINK("{safe_link}","{safe_cn}")'

        # Zillow hyperlink
        zillow_url = clean_value(row.get("Zillow", ""))
        if zillow_url:
            safe_zillow = zillow_url.replace('"', "%22")
            values[zillow_col_idx] = f'=HYPERLINK("{safe_zillow}","Zillow")'

        # Satellite View hyperlink
        sat_url = clean_value(row.get("Satellite View", ""))
        if sat_url:
            safe_sat = sat_url.replace('"', "%22")
            values[sat_col_idx] = f'=HYPERLINK("{safe_sat}","Satellite View")'

        all_values.append(values)

    CHUNK_SIZE = 50
    total_chunks = (len(all_values) + CHUNK_SIZE - 1) // CHUNK_SIZE

    uploaded = 0
    for i in range(0, len(all_values), CHUNK_SIZE):
        chunk = all_values[i : i + CHUNK_SIZE]
        chunk_num = (i // CHUNK_SIZE) + 1
        print(f"  📤 Chunk {chunk_num}/{total_chunks} ({len(chunk)} rows)...")

        retry(lambda c=chunk: sheet.append_rows(c, value_input_option="USER_ENTERED"))
        uploaded += len(chunk)
        print(f"  ✅ {uploaded}/{len(all_values)} rows uploaded")

        if i + CHUNK_SIZE < len(all_values):
            time.sleep(1)

    print(f"\n{'='*40}")
    print(f"✅ DONE!")
    print(f"📊 Sheet URL: {SHEET_URL}")
    print(f"📄 Total rows uploaded: {uploaded}")
    print(f"{'='*40}")


if __name__ == "__main__":
    csv_files = [
        f for f in os.listdir(".") if f.startswith("data_") and f.endswith(".csv")
    ]

    if not csv_files:
        print("❌ Koi CSV file nahi mili folder mein")
        exit()

    print(f"\n{'='*40}")
    print(f"  CSV FILES FOUND:")
    for i, f in enumerate(csv_files):
        print(f"  {i+1}. {f}")
    print(f"{'='*40}")

    if len(csv_files) == 1:
        selected = csv_files[0]
        print(f"  Auto-selecting: {selected}")
    else:
        choice = input("  Konsa CSV upload karna hai? (number enter karo): ").strip()
        try:
            selected = csv_files[int(choice) - 1]
        except:
            print("❌ Invalid choice")
            exit()

    print(f"\n  📄 Selected: {selected}")
    upload_csv_to_sheet(selected)