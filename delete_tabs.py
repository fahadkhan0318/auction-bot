import sys
import gspread
from oauth2client.service_account import ServiceAccountCredentials

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SHEET_URL = "https://docs.google.com/spreadsheets/d/17J2SZ3khk55iQrgxX9zl3wLUeCHPNqbQD_iG1_fxZZU/edit"
TABS_TO_DELETE = ["Sheriff", "MVBA"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_url(SHEET_URL)

for tab_name in TABS_TO_DELETE:
    try:
        ws = spreadsheet.worksheet(tab_name)
        spreadsheet.del_worksheet(ws)
        print(f"✅ Deleted tab: '{tab_name}'")
    except Exception:
        print(f"⚠️  Tab not found (already deleted?): '{tab_name}'")

print("\nDone!")
