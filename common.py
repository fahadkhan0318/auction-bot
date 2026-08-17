"""
common.py — Shared utilities: DB, CSV, Google Sheet, constants
Used by sheriff.py, mvba.py, govease.py and main.py
"""

import os, csv, json, re, time, shutil
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ═══════════════════════════════════════════════════════════════════════════
# GLOBALS (set by main.py after month selection)
# ═══════════════════════════════════════════════════════════════════════════
sheet    = None
MAIN_CSV = ""
DB_FILE  = ""

# When AUTO_RUN=1 (set by the scheduled/CI workflow), all interactive
# input() prompts across main.py are skipped in favor of defaults.
AUTO_MODE = os.getenv("AUTO_RUN") == "1"

# ═══════════════════════════════════════════════════════════════════════════
# COUNTIES
# ═══════════════════════════════════════════════════════════════════════════

SHERIFF_COUNTIES = [
    "angelina", "aransas", "atascosa", "caldwell", "cameron", "dallas",
    "elpaso", "ellis", "galveston", "gregg", "hopkins", "jackson",
    "kaufman", "llano", "matagorda", "montgomery", "nueces", "orange",
    "sanpatricio", "smith", "travis", "tylercounty", "victoria", "wilson"
]

MVBA_KNOWN_COUNTIES = [
    "calhoun", "grimes", "guadalupe", "williamson", "shackelford",
    "panola", "mclennan", "gregg", "hardin", "harrison", "cherokee", "cameron",
    "stephens", "comal", "hill", "bastrop", "bosque", "runnels"
]

GOVEASE_COUNTIES = {
    "denton":    "https://liveauctions.govease.com/tx/txdenton",
    "mclennan":  "https://liveauctions.govease.com/tx/txmclennan",
    "wichita":   "https://liveauctions.govease.com/tx/txwichita",
}

COUNTY_BASE_URLS = {
    "travis":     "https://travis.texas.realforeclose.com/",
    "montgomery": "https://montgomery.texas.realforeclose.com/"
}

# ═══════════════════════════════════════════════════════════════════════════
# CSV FIELDS
# ═══════════════════════════════════════════════════════════════════════════
CSV_FIELDS = [
    "Unique Key", "Source", "County", "Cause Number", "Item Number", "Link", "Auction Date",
    "Status", "Min Bid", "Adjusted Value", "Property Address",
    "Account Number", "Legal Description", "Owner Name", "Buyer Name",
    "Sold Amount", "Winning Bid", "Sale Date", "Last Updated",
    "Zillow", "Realtor", "Satellite View", "Appraisal District",
    # ── CAD enrichment fields ─────────────────────────────────────────────
    "Interactive Map",
    "Improvement Homesite Value",
    "Improvement Non-Homesite",
    "Land Homesite Value",
    "Land Non-Homesite Value",
    "Ag Market Valuation",
]

# Fields that are hyperlinks in the sheet
_LINK_FIELDS = {
    "Zillow":             "Zillow",
    "Realtor":            "Realtor",
    "Satellite View":     "Satellite",
    "Appraisal District": "Appraisal",
    "Interactive Map":    "IntMap",
}

# ═══════════════════════════════════════════════════════════════════════════
# MONTH HELPERS
# ═══════════════════════════════════════════════════════════════════════════
MONTH_NAMES = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
}
MONTH_NUM_TO_NAME = {v: k.title() for k, v in MONTH_NAMES.items()}

# ═══════════════════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════════════════
STATUS_KEYWORDS_ORDERED = [
    ("Struck Off",             "Struck Off"),
    ("Pulling for no bids",    "Pulled for no bids"),
    ("Pulled for no bids",     "Pulled for no bids"),
    ("Cancelled per Attorney", "Cancelled"),
    ("Canceled per Attorney",  "Cancelled"),
    ("Cancelled",              "Cancelled"),
    ("Canceled",               "Cancelled"),
    ("Paid in Full",           "Paid in Full"),
    ("Paid prior to sale",     "Redeemed"),
    ("Payment Arrangement",    "P.Arrangement"),
    # Administrative holds — no bidder was ever involved, treat like Cancelled.
    ("Pulled new heirs/owners located", "Cancelled"),
    ("New heirs/owners located",        "Cancelled"),
    ("Over 65",                         "Cancelled"),
    ("Auction to be rescheduled",       "Cancelled"),
    ("Auction Sold",           "Sold"),
    ("Sold",                   "Sold"),
]

SOLD_STATUSES    = {"Sold"}
NONSOLD_STATUSES = {
    "Struck Off", "Pulled for no bids", "Cancelled",
    "Redeemed", "Paid in Full", "P.Arrangement", "Pending",
}

# Statuses meaning a listing was pulled from the active sale sequence before
# (or without) going to auction — these never hold a stable Item Number and
# are pushed to the bottom of their county+date group. Matched as a
# case-insensitive substring, not an exact set, because raw status text
# differs by source — e.g. Linebarger passes the site's text straight
# through instead of mapping it through STATUS_KEYWORDS_ORDERED, and MVBA
# produces "Withdrawn" directly.
CANCELLED_STATUS_KEYWORDS = [
    "cancel", "withdraw", "pulled", "postpone", "no bid",
    "continuance", "redeem", "paid in full", "arrangement",
]


def is_cancelled_equivalent_status(status):
    s = (status or "").strip().lower()
    return bool(s) and any(kw in s for kw in CANCELLED_STATUS_KEYWORDS)

# ═══════════════════════════════════════════════════════════════════════════
# KEY HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def make_unique_key(county, account_number, source=""):
    src_prefix = f"{source.upper()}_" if source else ""
    return f"{src_prefix}{county.upper()}_{account_number.strip()}"


def normalize_uk(k):
    k = str(k).strip().lstrip("'")
    if "_" in k:
        return k.upper()
    try:
        if "E" in k.upper() and ("+" in k or "-" in k):
            return str(int(float(k)))
        return str(int(k))
    except Exception:
        return k.upper()

# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE SHEET INIT
# ═══════════════════════════════════════════════════════════════════════════

def init_sheet(worksheet_name=None):
    global sheet
    scope  = ["https://spreadsheets.google.com/feeds",
               "https://www.googleapis.com/auth/drive"]
    creds  = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/17J2SZ3khk55iQrgxX9zl3wLUeCHPNqbQD_iG1_fxZZU/edit"
    )
    if worksheet_name:
        try:
            ws = spreadsheet.worksheet(worksheet_name)
            print(f"  📊 Using existing sheet tab: '{worksheet_name}'")
        except Exception:
            ws = spreadsheet.add_worksheet(title=worksheet_name, rows=500, cols=28)
            print(f"  ✅ New sheet tab created: '{worksheet_name}'")
        sheet = ws
        _invalidate_sheet_cache()
        return ws
    sheet = spreadsheet.sheet1
    _invalidate_sheet_cache()
    return sheet

# ═══════════════════════════════════════════════════════════════════════════
# DB (JSON)
# ═══════════════════════════════════════════════════════════════════════════

def load_db():
    if os.path.isfile(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except Exception:
            print("⚠️ DB file corrupt — fresh start")
    return {}


def save_db(db):
    _backup_file(DB_FILE)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════════
# CSV
# ═══════════════════════════════════════════════════════════════════════════

def load_csv_rows():
    rows = {}
    if not os.path.isfile(MAIN_CSV):
        print(f"  📄 New CSV will be created: {MAIN_CSV}")
        return rows
    with open(MAIN_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uk = row.get("Unique Key", "").strip()
            if uk:
                rows[uk] = row
    print(f"  📄 Loaded existing CSV: {MAIN_CSV} ({len(rows)} rows)")
    return rows


def _backup_file(path):
    """Overwrite karne se pehle .bak copy bana do."""
    if os.path.isfile(path):
        shutil.copy2(path, path + ".bak")


def _date_only(s):
    """Strip time-of-day from an Auction Date string, keeping just mm/dd/yyyy.
    Sheriff sites give each case its own start-time (10:00, 10:01, 10:02…),
    so grouping Item Number by the full timestamp splits one auction day
    into many groups. Item Number must be grouped per calendar day, not
    per exact time."""
    m = re.search(r'\d{1,2}/\d{1,2}/\d{4}', s or "")
    return m.group(0) if m else (s or "")


def _item_number_rank(row, inferred=False):
    """Sort helper: numbered rows ascending by number, blank/cancelled rows
    last (tie-broken by Cause Number so ordering stays stable/deterministic).
    inferred=True forces a row to the very end regardless of any Item Number
    already stored on it — used for rows whose Auction Date (and therefore
    group membership) was just guessed, so any old number they're carrying
    was assigned under a different, wrong grouping and can't be trusted."""
    if inferred:
        return (2, 0, row.get("Cause Number", "") or "")
    raw = (row.get("Item Number") or "").strip()
    try:
        return (0, int(raw), "")
    except ValueError:
        return (1, 0, row.get("Cause Number", "") or "")


def _is_mvba_row(row):
    """Every MVBA row — PDF (Tract #, e.g. mvbalaw.com/wp-content/TaxUploads/...)
    or online (Lot #, mvbataxsales.com) — carries a literal number printed on
    the source itself, so it must be left untouched here."""
    return row.get("Source", "").strip().upper() == "MVBA"


def renumber_item_numbers(rows_dict):
    """Recompute every row's Item Number fresh from current data so it's
    always a clean, gapless 1..N per county + auction date (each sale day is
    its own numbering sequence) — regardless of whether a given row was
    freshly scraped this run or is old/unchanged. Only still-active rows get
    numbered; cancelled-equivalent rows are blanked so they're never counted
    and never masquerade as a distinct property to downstream
    item_number-based matching. Blanking also pushes them to the very bottom
    of their group's sort order (see _item_number_rank), which every caller
    that displays rows (rewrite_csv, reorder_google_sheet) sorts by — so a
    cancelled listing always ends up last within its county/date, and every
    active row below its old slot shifts up to close the gap.

    SHERIFF rows go through this same active/cancelled split and gapless
    1..N renumbering, grouped by county + auction date like every other
    source — a cancelled-equivalent SHERIFF listing (Cancelled, Struck Off
    cancellations, "New heirs/owners located", "Over 65", "Auction to be
    rescheduled", etc.) is not left sitting in its site-walk slot; it's
    blanked and sorted last, same as any other source's cancellation.

    MVBA (both PDF and online) rows are still the exception: their Item
    Number is a literal identifier printed on the source itself, not a
    shifting page position, so it's left untouched here.
      - MVBA PDF: the docket's own "Tract #" column, including for
        Withdrawn tracts — the PDF already lists them inline in sequence
        (e.g. tracts 33-36 Withdrawn, then 37 Resales continues), so
        renumbering here would scramble an order that's meant to be read
        strictly in sequence.
      - MVBA online: the site's own literal "Lot #" (normalized by mvba.py's
        _normalize_lot_number — e.g. '01', '99990002'), including for
        withdrawn lots, which still show their Lot # on the site.
    """
    # A row can land here with no Auction Date yet (e.g. its detail-page
    # scrape hasn't resolved one). Grouping it under its own blank-date key
    # would fork it into a second, restarted 1..N sequence for a county that
    # already has a real date — so when a county has exactly one distinct
    # known date, fold blank-date rows into that group instead of giving
    # them their own. Ambiguous (0 or 2+ known dates) counties are left
    # alone since there's no single date to safely assume.
    known_dates_by_county = {}
    for row in rows_dict.values():
        county = row.get("County", "").strip().upper()
        date   = _date_only(row.get("Auction Date", ""))
        if date:
            known_dates_by_county.setdefault(county, set()).add(date)

    groups   = {}
    inferred = set()  # id() of rows folded into a group via a guessed date
    for row in rows_dict.values():
        if _is_mvba_row(row):
            continue
        county = row.get("County", "").strip().upper()
        date   = _date_only(row.get("Auction Date", ""))
        if not date and len(known_dates_by_county.get(county, ())) == 1:
            date = next(iter(known_dates_by_county[county]))
            inferred.add(id(row))
        key = (county, date)
        groups.setdefault(key, []).append(row)

    for rows in groups.values():
        active    = [r for r in rows if not is_cancelled_equivalent_status(r.get("Status", ""))]
        cancelled = [r for r in rows if is_cancelled_equivalent_status(r.get("Status", ""))]
        # Order active rows by whatever raw number the site last showed (the
        # best available signal of true auction sequence), falling back to
        # Cause Number for sources that never expose one — then reassign
        # clean 1..N so cancellations never leave a gap or stale number.
        # Rows with a guessed date always sort last (see _item_number_rank).
        active.sort(key=lambda r: _item_number_rank(r, inferred=id(r) in inferred))
        for i, r in enumerate(active, start=1):
            r["Item Number"] = str(i)
        for r in cancelled:
            r["Item Number"] = ""


def rewrite_csv(rows_dict):
    """Write all rows to CSV, sorted by source → county → date → item number → cause number."""
    renumber_item_numbers(rows_dict)
    _backup_file(MAIN_CSV)

    source_order  = {"SHERIFF": 0, "MVBA": 1, "GOVEASE": 2}
    county_order  = {}
    for i, c in enumerate(SHERIFF_COUNTIES + MVBA_KNOWN_COUNTIES + list(GOVEASE_COUNTIES.keys())):
        county_order.setdefault(c.upper(), i)

    def sort_key(row):
        county = row.get("County", "").upper()
        return (
            source_order.get(row.get("Source", "").upper(), 9),
            county_order.get(county, 999),
            county,
            row.get("Auction Date", "") or "9999",
            _item_number_rank(row),
        )

    with open(MAIN_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows_dict.values(), key=sort_key):
            for field in CSV_FIELDS:
                row.setdefault(field, "")
            writer.writerow(row)

# ═══════════════════════════════════════════════════════════════════════════
# MONTH SELECTION
# ═══════════════════════════════════════════════════════════════════════════

def ask_target_month():
    global MAIN_CSV, DB_FILE
    now = datetime.now()

    if AUTO_MODE:
        month_num = now.month
        year      = now.year
        mn        = MONTH_NUM_TO_NAME[month_num].lower()
        MAIN_CSV  = f"data_{mn}_{year}.csv"
        DB_FILE   = f"scraped_db_{mn}_{year}.json"
        print(f"  🤖 AUTO mode — target: {MONTH_NUM_TO_NAME[month_num]} {year}")
        print(f"  📄 CSV     : {MAIN_CSV}")
        print(f"  🗄️  DB      : {DB_FILE}")
        return month_num, year

    def fuzzy_match(s):
        s = s.lower().strip()
        if s in MONTH_NAMES: return MONTH_NAMES[s]
        for name, num in MONTH_NAMES.items():
            if name.startswith(s) or s.startswith(name[:3]): return num
        for name, num in MONTH_NAMES.items():
            if sum(1 for a,b in zip(s,name) if a==b) >= 3 and len(s) >= 3: return num
        return None

    print(f"\n{'='*45}\n  MONTH SELECTION\n{'='*45}")
    print(f"  Current month: {now.strftime('%B %Y')}")
    print(f"  Enter month name or press Enter for current month:")
    ui = input("  > ").strip().lower()
    year = now.year

    if not ui:
        month_num = now.month
    else:
        month_num = fuzzy_match(ui)
        if month_num is None:
            print(f"  ⚠️ Not understood — retry:")
            month_num = fuzzy_match(input("  > ").strip().lower()) or now.month

    if month_num - now.month > 1:
        print(f"  ⚠️ That month is far ahead — use {MONTH_NUM_TO_NAME[month_num]} {now.year-1}? (y/n):")
        if input("  > ").strip().lower() == "y":
            year = now.year - 1

    mn       = MONTH_NUM_TO_NAME[month_num].lower()
    MAIN_CSV = f"data_{mn}_{year}.csv"
    DB_FILE  = f"scraped_db_{mn}_{year}.json"
    print(f"  ✅ Target  : {MONTH_NUM_TO_NAME[month_num]} {year}")
    print(f"  📄 CSV     : {MAIN_CSV}")
    print(f"  🗄️  DB      : {DB_FILE}")
    return month_num, year

# ═══════════════════════════════════════════════════════════════════════════
# SMART SAVE — unified save for all sources
# ═══════════════════════════════════════════════════════════════════════════

_STATUS_ALIASES = {
    "scheduled for auction": "Pending",
    "scheduled":             "Pending",
    "active":                "Pending",
}

def smart_save(data, db, csv_rows, section_label=""):
    uk         = data["Unique Key"]
    raw_status = data.get("Status", "Pending") or "Pending"
    new_status = _STATUS_ALIASES.get(raw_status.strip().lower(), raw_status)
    data["Status"] = new_status

    # Item Number is never assigned/persisted here — whatever the scraper put
    # in data["Item Number"] (a raw site number, or "" if the source has
    # none) is only an ordering hint. renumber_item_numbers() recomputes the
    # real 1..N sequence fresh, grouped by county+auction-date, every time
    # rewrite_csv()/reorder_google_sheet() runs — see common.py.
    if uk not in db:
        csv_rows[uk] = data
        update_google_sheet(data)
        db[uk] = {
            "status":       new_status,
            "first_seen":   datetime.now().strftime("%Y-%m-%d"),
            "source":       data.get("Source", ""),
            "county":       data.get("County", ""),
            "cause_number": data.get("Cause Number", ""),
            "section":      section_label,
        }
        print(f"  ✅ NEW: {uk} [{new_status}]")
        save_db(db)
        return "new"

    old_status   = db[uk].get("status", "")
    existing_row = csv_rows.get(uk, {})

    missing_buyer  = new_status in SOLD_STATUSES and not existing_row.get("Buyer Name", "").strip()
    missing_amount = new_status in SOLD_STATUSES and not existing_row.get("Sold Amount", "").strip()
    missing_owner  = not existing_row.get("Owner Name", "").strip()

    has_new_buyer  = bool(data.get("Buyer Name", "").strip())
    has_new_amount = bool(data.get("Sold Amount", "").strip())
    has_new_owner  = bool(data.get("Owner Name", "").strip())

    missing_item_num  = not existing_row.get("Item Number", "").strip()
    has_new_item_num  = bool(data.get("Item Number", "").strip())
    # Not just "was missing" — a freshly re-scraped SHERIFF row carries the
    # site's current page position, which shifts over time (cancellations
    # push everything below them up). If that differs from what's stored,
    # it must win even though every other field on this row is unchanged.
    item_num_changed = (
        has_new_item_num
        and data.get("Item Number", "") != existing_row.get("Item Number", "")
    )

    needs_update = (
        old_status != new_status
        or (missing_buyer  and has_new_buyer)
        or (missing_amount and has_new_amount)
        or (missing_buyer  or missing_amount)
        or (missing_owner  and has_new_owner)
        or (missing_item_num and has_new_item_num)
        or item_num_changed
        or (not existing_row.get("Zillow", "")             and data.get("Zillow"))
        or (not existing_row.get("Realtor", "")            and data.get("Realtor"))
        or (not existing_row.get("Satellite View", "")     and data.get("Satellite View"))
        or (not existing_row.get("Appraisal District", "") and data.get("Appraisal District"))
    )

    if needs_update:
        existing = csv_rows.get(uk, data.copy())
        if new_status in SOLD_STATUSES:
            buyer_name  = data.get("Buyer Name",  "") or existing.get("Buyer Name",  "")
            sold_amount = data.get("Sold Amount", "") or existing.get("Sold Amount", "")
            winning_bid = data.get("Winning Bid", "") or existing.get("Winning Bid", "")
        else:
            buyer_name  = ""
            sold_amount = ""
            winning_bid = ""
        existing.update({
            "Status":             new_status,
            # Just an ordering hint for renumber_item_numbers() — prefer the
            # freshest raw number since it best reflects the site's current
            # sequence; the real displayed Item Number is always recomputed
            # from scratch afterward, never taken verbatim from either side.
            "Item Number":        data.get("Item Number", "")         or existing.get("Item Number", ""),
            # Was missing from this merge entirely, so a listing whose first
            # scrape failed to find a date (e.g. a detail-page layout miss)
            # stayed blank forever even after later re-scrapes found it —
            # which also broke renumber_item_numbers()'s county+date
            # grouping for that row. Prefer the freshest value like the
            # other fields below.
            "Auction Date":       data.get("Auction Date", "")       or existing.get("Auction Date", ""),
            "Owner Name":         data.get("Owner Name", "")         or existing.get("Owner Name", ""),
            "Buyer Name":         buyer_name,
            "Sold Amount":        sold_amount,
            "Winning Bid":        winning_bid,
            "Sale Date":          data.get("Sale Date", "")          or existing.get("Sale Date", ""),
            "Last Updated":       data["Last Updated"],
            "Zillow":             data.get("Zillow", "")             or existing.get("Zillow", ""),
            "Realtor":            data.get("Realtor", "")            or existing.get("Realtor", ""),
            "Satellite View":     data.get("Satellite View", "")     or existing.get("Satellite View", ""),
            "Appraisal District": data.get("Appraisal District", "") or existing.get("Appraisal District", ""),
        })
        csv_rows[uk] = existing
        update_google_sheet(existing)
        db[uk]["status"] = new_status
        print(f"  🔄 UPDATED: {uk} [{old_status}→{new_status}] "
              f"Owner='{existing.get('Owner Name','')}' "
              f"Buyer='{existing.get('Buyer Name','')}' "
              f"Amount='{existing.get('Sold Amount','')}'")
        save_db(db)
        return "updated"

    csv_rows.setdefault(uk, data)
    print(f"  ⏭️  SKIP: {uk} [{new_status}]")
    return "skipped"

# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE SHEET UPDATE
# ═══════════════════════════════════════════════════════════════════════════

# In-memory cache of the sheet's current rows so we don't call get_all_values()
# (a full-sheet read) before every single row write. Re-fetching on every save
# was burning through the Sheets API quota during fast back-to-back updates,
# which caused writes to fail silently (see _sheet_write_retry) while the CSV/DB
# still recorded the row as "updated". Cache is kept in sync locally on every
# write/append and only re-fetched when structurally invalidated.
_sheet_cache = {"values": None, "uk_col": None}


def _invalidate_sheet_cache():
    _sheet_cache["values"]  = None
    _sheet_cache["uk_col"]  = None


def _get_sheet_cache():
    if _sheet_cache["values"] is not None:
        return _sheet_cache["values"], _sheet_cache["uk_col"]

    all_values = sheet.get_all_values()
    expected_hdrs = [h for h in CSV_FIELDS if h != "Link"]
    if not all_values:
        sheet.append_row(expected_hdrs)
        all_values = sheet.get_all_values()
    elif "Unique Key" not in [h.strip() for h in all_values[0]]:
        sheet.insert_row(expected_hdrs, 1, value_input_option="RAW")
        all_values = sheet.get_all_values()

    headers = all_values[0]
    try:    uk_col = [h.strip() for h in headers].index("Unique Key")
    except ValueError:
        print("❌ 'Unique Key' column missing in sheet")
        return None, None

    _sheet_cache["values"] = all_values
    _sheet_cache["uk_col"] = uk_col
    return all_values, uk_col


def update_google_sheet(row_data):
    global sheet
    if sheet is None:
        return
    try:
        all_values, uk_col = _get_sheet_cache()
        if all_values is None:
            return

        sheet_headers = [h for h in CSV_FIELDS if h != "Link"]
        link_url      = row_data.get("Link", "")
        cause_number  = row_data.get("Cause Number", "")
        hyperlink     = (f'=HYPERLINK("{link_url}","{cause_number}")'
                         if link_url and cause_number else cause_number)

        def make_row():
            vals = []
            for h in sheet_headers:
                v = row_data.get(h, "") or ""
                if h == "Unique Key"     and v: v = "'" + str(v)
                if h == "Account Number" and v: v = "'" + str(v)
                if h == "Cause Number":         v = hyperlink
                if h in _LINK_FIELDS and str(v).startswith("http"):
                    v = f'=HYPERLINK("{v}","{_LINK_FIELDS[h]}")'
                vals.append(v)
            return vals

        uk_norm = normalize_uk(row_data["Unique Key"])
        for idx, row in enumerate(all_values[1:], start=2):
            if len(row) > uk_col and normalize_uk(row[uk_col]) == uk_norm:
                values = make_row()
                try:
                    _sheet_write_retry(lambda: sheet.update(f"A{idx}", [values], value_input_option="USER_ENTERED"))
                except Exception:
                    # Write ultimately failed after retries — cache may now be
                    # stale/unreliable, force a fresh read next time instead of
                    # silently trusting an unwritten row.
                    _invalidate_sheet_cache()
                    raise
                row[:] = values  # keep cached row in sync
                print(f"  📊 SHEET UPDATED: {row_data['Unique Key']}")
                return

        values = make_row()
        try:
            _sheet_write_retry(lambda: sheet.append_row(values, value_input_option="USER_ENTERED"))
        except Exception:
            _invalidate_sheet_cache()
            raise
        all_values.append(values)  # keep cached row in sync
        print(f"  📊 SHEET NEW: {row_data['Unique Key']}")

    except Exception as e:
        print(f"  ❌ Sheet error: {e}")


def _sheet_write_retry(fn, retries=4):
    """Call a gspread write operation with retry on connection errors.

    Rate-limit / quota errors (HTTP 429, RESOURCE_EXHAUSTED) need a much longer
    backoff than plain connection hiccups — Google's write quota resets on a
    rolling ~60s window, so a 3s/6s retry just fails again immediately.
    """
    global sheet
    delay = 3
    for attempt in range(1, retries + 1):
        try:
            fn()
            return
        except Exception as e:
            err_str = str(e)
            if "10000000" in err_str or "limit of" in err_str.lower():
                print(f"  ❌ Sheet is FULL (10M cell limit). Disabling sheet writes for this run.")
                print(f"  ℹ️  Fix: delete old month tabs in Google Sheets, then re-run.")
                sheet = None
                return
            is_quota_err = (
                "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                or "quota" in err_str.lower() or "rate limit" in err_str.lower()
            )
            if attempt < retries:
                wait = 20 * attempt if is_quota_err else delay
                print(f"  ⚠️  Sheet write attempt {attempt} failed ({e}) — retrying in {wait}s...")
                time.sleep(wait)
                delay *= 2
            else:
                raise


def reorder_google_sheet(csv_rows):
    if not csv_rows or sheet is None:
        return
    try:
        print("\n  🔄 Reordering sheet...")
        renumber_item_numbers(csv_rows)
        source_order = {"SHERIFF": 0, "MVBA": 1, "GOVEASE": 2}
        county_order = {}
        for i, c in enumerate(SHERIFF_COUNTIES + MVBA_KNOWN_COUNTIES + list(GOVEASE_COUNTIES.keys())):
            county_order.setdefault(c.upper(), i)

        def sort_key(r):
            county = r.get("County", "").upper()
            return (
                source_order.get(r.get("Source", "").upper(), 9),
                county_order.get(county, 999),
                county,
                r.get("Auction Date", "") or "9999",
                _item_number_rank(r),
            )

        sheet_headers = [h for h in CSV_FIELDS if h != "Link"]

        def make_row(rd):
            vals         = []
            link_url     = rd.get("Link", "")
            cause_number = rd.get("Cause Number", "")
            for h in sheet_headers:
                v = rd.get(h, "") or ""
                if h == "Unique Key"     and v: v = "'" + str(v)
                if h == "Account Number" and v: v = "'" + str(v)
                if h == "Cause Number":
                    v = (f'=HYPERLINK("{link_url}","{cause_number}")'
                         if link_url and cause_number else cause_number)
                if h in _LINK_FIELDS and str(v).startswith("http"):
                    v = f'=HYPERLINK("{v}","{_LINK_FIELDS[h]}")'
                vals.append(v)
            return vals

        all_data = [sheet_headers] + [make_row(r) for r in sorted(csv_rows.values(), key=sort_key)]

        # Clear sheet first
        for attempt in range(1, 4):
            try:
                sheet.clear()
                break
            except Exception as e:
                if attempt < 3:
                    print(f"  ⚠️  Clear attempt {attempt} failed ({e}) — retrying in {attempt*3}s...")
                    time.sleep(attempt * 3)
                else:
                    raise

        time.sleep(1)

        # Upload in chunks of 200 rows to avoid connection drops
        CHUNK = 200
        for i in range(0, len(all_data), CHUNK):
            chunk      = all_data[i : i + CHUNK]
            start_row  = i + 1
            range_name = f"A{start_row}"
            for attempt in range(1, 4):
                try:
                    sheet.update(range_name, chunk, value_input_option="USER_ENTERED")
                    break
                except Exception as e:
                    if attempt < 3:
                        print(f"  ⚠️  Chunk {i//CHUNK+1} attempt {attempt} failed ({e}) — retrying in {attempt*3}s...")
                        time.sleep(attempt * 3)
                    else:
                        raise
            if i + CHUNK < len(all_data):
                time.sleep(0.5)

        # Sheet now exactly matches all_data — sync the cache instead of
        # forcing a full re-read on the next update_google_sheet() call.
        uk_col = sheet_headers.index("Unique Key")
        _sheet_cache["values"] = all_data
        _sheet_cache["uk_col"] = uk_col

        print(f"  ✅ Reordered: {len(all_data)-1} rows")
    except Exception as e:
        print(f"  ❌ Sheet reorder error: {e}")
        _invalidate_sheet_cache()


def sync_csv_to_sheet(csv_rows):
    if not csv_rows or sheet is None:
        print("  ℹ️  No CSV data to sync.")
        return
    print(f"\n{'='*45}\n📊 Syncing {len(csv_rows)} records to sheet...")
    try:
        all_values = sheet.get_all_values()
        expected_hdrs = [h for h in CSV_FIELDS if h != "Link"]
        if not all_values:
            sheet.append_row(expected_hdrs)
            all_values = sheet.get_all_values()
        elif "Unique Key" not in [h.strip() for h in all_values[0]]:
            sheet.insert_row(expected_hdrs, 1, value_input_option="RAW")
            all_values = sheet.get_all_values()

        headers = all_values[0]
        try:    uk_col = [h.strip() for h in headers].index("Unique Key")
        except ValueError:
            print("❌ 'Unique Key' missing — aborting sync")
            return

        existing = {normalize_uk(r[uk_col]) for r in all_values[1:]
                    if len(r) > uk_col and r[uk_col]}
        added = 0
        for uk, rd in csv_rows.items():
            if normalize_uk(uk) not in existing:
                update_google_sheet(rd)
                existing.add(normalize_uk(uk))
                added += 1

        if added:
            print(f"  ✅ Added {added} rows — reordering...")
            reorder_google_sheet(csv_rows)
        else:
            print(f"  ✅ Nothing new to add.")
    except Exception as e:
        print(f"  ❌ Sync error: {e}")
    print(f"{'='*45}\n")