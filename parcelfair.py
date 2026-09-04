"""
parcelfair.py — Parcel Fair Auction Calendar (parcelfair.com)

Logs in, opens the Texas Auction Calendar, and expands a chosen month's
accordion panel. Each expanded month lists every auction happening that
month grouped by day, e.g.:

    Sep 1 (Tuesday)
      Eastland Sheriff Sale (MVBA)   | In-Person Auction | 21 available parcels
        Map -> ../map?countyCode=48133&InventoryType=341786
        List -> ../parcel?countyCode=48133&InventoryType=341786

NOTE: sync_playwright imported LAZILY inside run_parcelfair() only, same
convention as govease.py — avoids circular import with main.py.
"""

import os, re, csv
from dotenv import load_dotenv

from common import MONTH_NUM_TO_NAME

PARCELFAIR_CSV_FIELDS = [
    "Auction Name", "Auction Day", "Auction Type",
    "Parcel Number", "Owner Name", "County", "State", "Availability", "Status",
    "Parcel Type", "Sale Year", "Amount Due", "Acres", "Total Value",
    "Land Value", "Building Value", "ARV Estimate", "Rent Estimate",
    "Address", "Next Auction", "Occupancy",
    "Flood Zone Type", "Flood Zone Desc",
    "Is Vacant", "Owner Occupied", "Absentee Owner",
    "Has Judgment", "Has Foreclosure", "Is Free And Clear",
    "Open Mortgage Balance", "Negative Equity",
    "Corporate Owned", "Deceased Owner", "Taxes Due",
    "Street View Image", "Satellite Image", "Detail URL",
]

# Maps a scraped parcel dict's keys -> the CSV column name above.
_CSV_KEY_MAP = {
    "Auction Name": "_auction_name", "Auction Day": "_auction_day", "Auction Type": "_auction_type",
    "Parcel Number": "parcel_number", "Owner Name": "owner_name", "County": "county", "State": "state",
    "Availability": "availability", "Status": "status", "Parcel Type": "parcel_type",
    "Sale Year": "sale_year", "Amount Due": "amount_due", "Acres": "acres", "Total Value": "total_value",
    "Land Value": "land_value", "Building Value": "building_value", "ARV Estimate": "arv_estimate",
    "Rent Estimate": "rent_estimate", "Address": "address", "Next Auction": "next_auction",
    "Occupancy": "occupancy", "Flood Zone Type": "flood_zone_type", "Flood Zone Desc": "flood_zone_desc",
    "Is Vacant": "is_vacant", "Owner Occupied": "owner_occupied", "Absentee Owner": "absentee_owner",
    "Has Judgment": "has_judgment", "Has Foreclosure": "has_foreclosure",
    "Is Free And Clear": "is_free_and_clear", "Open Mortgage Balance": "open_mortgage_balance",
    "Negative Equity": "negative_equity", "Corporate Owned": "corporate_owned",
    "Deceased Owner": "deceased_owner", "Taxes Due": "taxes_due",
    "Street View Image": "street_view_image_url", "Satellite Image": "satellite_image_url",
    "Detail URL": "detail_url",
}


def save_parcelfair_csv(rows, month_name, year):
    """Write scraped parcel dicts to data_parcelfair_{month}_{year}.csv."""
    path = f"data_parcelfair_{month_name.lower()}_{year}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PARCELFAIR_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(key, "") for col, key in _CSV_KEY_MAP.items()})
    return path

load_dotenv(override=True)
PARCELFAIR_EMAIL    = os.getenv("PARCELFAIR_EMAIL")
PARCELFAIR_PASSWORD = os.getenv("PARCELFAIR_PASSWORD")

CALENDAR_URL = "https://parcelfair.com/Auction/Calendar"

# Values match the <select id="location"> options on the calendar page.
LOCATION_FILTERS = {
    "all":       "All",
    "any":       "All",
    "in-person": "In-Person",
    "inperson":  "In-Person",
    "online":    "Online",
}

_MONTH_PANEL_JS = r"""
(monthText) => {
    const link = Array.from(document.querySelectorAll('.panel-heading a'))
        .find(a => a.innerText.trim().startsWith(monthText));
    if (!link) return null;
    const panel = link.closest('.panel');
    const body  = panel.querySelector('.panel-body, .panel-collapse');
    if (!body) return null;

    const results = [];
    let currentDay = '';
    body.querySelectorAll('.row > *').forEach(() => {}); // no-op, keeps structure explicit

    Array.from(body.children).forEach(row => {
        Array.from(row.children || []).forEach(child => {
            if (child.classList.contains('lead')) {
                currentDay = child.innerText.trim();
                return;
            }
            if (!child.classList.contains('auction')) return;

            const nameEl   = child.querySelector('h5.clickable');
            // Type label is "In-Person Auction" (h5.text-primary) or "Online
            // Auction" (h5.text-success) — class differs by type, so match
            // by elimination instead of a fixed class name.
            const h5s      = Array.from(child.querySelectorAll('h5'));
            const typeEl   = h5s.find(h => !h.classList.contains('clickable') && !h.classList.contains('auction-status'));
            const statusEl = child.querySelector('.auction-status');
            const mapLinks  = Array.from(child.querySelectorAll('.dropdown-menu a[href*="/map"]'))
                .map(a => a.href);
            const listLinks = Array.from(child.querySelectorAll('.dropdown-menu a[href*="/parcel"]'))
                .map(a => a.href);

            const onclick = child.querySelector('.clickable') ? child.querySelector('.clickable').getAttribute('onclick') || '' : '';
            const idM = onclick.match(/openAuctionDetails\((\d+)\)/);

            results.push({
                day: currentDay,
                name: nameEl ? nameEl.innerText.trim() : '',
                auction_type: typeEl ? typeEl.innerText.trim() : '',
                status: statusEl ? statusEl.innerText.trim() : '',
                auction_id: idM ? idM[1] : '',
                map_links: mapLinks,
                list_links: listLinks,
            });
        });
    });

    return results;
}
"""


def login(page):
    """Log into parcelfair.com. Safe to call even if already logged in."""
    page.goto(CALENDAR_URL, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    if "Account/Login" not in page.url:
        print("  ✅ Parcel Fair: already logged in")
        return

    print("  🔐 Parcel Fair: logging in...")
    page.fill("#Email", PARCELFAIR_EMAIL)
    page.fill("#Password", PARCELFAIR_PASSWORD)
    page.click("input[type=submit]")
    page.wait_for_timeout(3000)

    if "Account/Login" in page.url:
        raise RuntimeError("Parcel Fair login failed — check PARCELFAIR_EMAIL/PARCELFAIR_PASSWORD in .env")

    print("  ✅ Parcel Fair: logged in")


def goto_calendar(page, location="All"):
    """
    Navigate to the Auction Calendar page (assumes already logged in).

    Args:
        location: "All" / "In-Person" / "Online" — matches the page's own
            "Any Location / In-Person Only / Online Only" dropdown. Passed
            straight through as the ?location= query param (same as what
            selecting the dropdown does), so no dropdown interaction needed.
    """
    loc = LOCATION_FILTERS.get(location.strip().lower(), location) if location else "All"
    url = f"{CALENDAR_URL}?state=TX&location={loc}"
    if "Auction/Calendar" not in page.url or f"location={loc}" not in page.url:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)


def click_month(page, month_name, year, location="All"):
    """
    Click a month's accordion panel on the Auction Calendar and return its
    expanded auction listings.

    Args:
        month_name: e.g. "July" (case-insensitive, also accepts full "July 2026")
        year: e.g. 2026
        location: "All" / "In-Person" / "Online" — see goto_calendar()

    Returns: list of dicts —
        {day, name, auction_type, status, auction_id, map_links, list_links}
    """
    goto_calendar(page, location=location)

    month_text = month_name.strip()
    if str(year) not in month_text:
        month_text = f"{month_text.title()} {year}"

    link = page.locator(f"a:has-text('{month_text}')").first
    if link.count() == 0:
        raise RuntimeError(f"Month panel not found on calendar: '{month_text}'")

    link.click()
    page.wait_for_timeout(2500)

    listings = page.evaluate(_MONTH_PANEL_JS, month_text)
    if listings is None:
        raise RuntimeError(f"Could not read expanded panel for '{month_text}'")

    print(f"  📅 Parcel Fair {month_text}: {len(listings)} auctions found")
    return listings


# ═══════════════════════════════════════════════════════════════════════════
# PARCEL LIST PAGE (…/parcel?countyCode=X&InventoryType=Y)
# ═══════════════════════════════════════════════════════════════════════════

_LIST_TABLE_JS = r"""
() => {
    const table = document.querySelector('table');
    if (!table) return [];
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        if (cells.length < 21) return null;
        const link = cells[1].querySelector('a');
        const clean = i => (cells[i].innerText || '').trim();
        return {
            parcel_number:  link ? link.innerText.trim() : clean(1),
            detail_url:     link ? link.href : '',
            cs_number:      clean(2),
            pin:            clean(3),
            owner_name:     clean(4),
            county:         clean(5),
            state:          clean(6),
            availability:   clean(7),
            status:         clean(8),
            parcel_type:    clean(9),
            sale_year:      clean(10),
            amount_due:     clean(11),
            acres:          clean(12),
            total_value:    clean(13),
            land_value:     clean(14),
            building_value: clean(15),
            arv_estimate:   clean(16),
            rent_estimate:  clean(17),
            address:        clean(18).replace(/\n+/g, ', '),
            next_auction:   clean(19),
            occupancy:      clean(20),
        };
    }).filter(r => r && r.parcel_number);
}
"""


def open_parcel_list(context, list_links, prefer_auction_only=True):
    """
    Open an auction's parcel list in a new browser tab.

    Args:
        context: Playwright BrowserContext (so the list opens in its own tab,
                 same as clicking the site's "List" dropdown does).
        list_links: the list_links array from a click_month() auction dict —
                 index 0 = "list all parcels in county", index 1 = "only
                 list parcels from this auction". Falls back to whichever
                 one link exists if only one was captured.
        prefer_auction_only: pick the "only this auction" link when both exist.

    Returns: the new Page, already navigated and loaded.
    """
    if not list_links:
        raise ValueError("No list_links provided — pass an auction dict's 'list_links'")

    url = list_links[1] if (prefer_auction_only and len(list_links) > 1) else list_links[0]

    list_page = context.new_page()
    list_page.goto(url, timeout=30000, wait_until="domcontentloaded")
    list_page.wait_for_timeout(2000)
    return list_page


def scrape_parcel_list(list_page):
    """Extract every row of the Parcel Search results table."""
    rows = list_page.evaluate(_LIST_TABLE_JS)
    print(f"  📋 Parcel list: {len(rows)} parcel(s) — {list_page.url[:70]}")
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# PARCEL DETAIL PAGE (/Parcel/Details/{id})
# ═══════════════════════════════════════════════════════════════════════════

def _parse_kv_lines(text):
    """
    Parcel Fair's detail page renders every enrichment section (Land/Lot
    Details, Mortgage Details, Occupancy, Owner Details, ...) as plain
    "Label: Value" lines in the page's visible text — no need to hunt for
    per-field CSS selectors. Sections are ordered with the authoritative
    values (current parcel/auction) first and historical/duplicate blocks
    ("Source: Parcel Shape Data", past auctions, etc.) after, so keeping
    only the FIRST value seen per label is what makes this reliable.
    """
    kv = {}
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r'^([A-Za-z][A-Za-z /\-]{2,40}):\s*(.+)$', line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key not in kv:
                kv[key] = val
    return kv


def scrape_parcel_detail(page, detail_url):
    """
    Open a single parcel's detail page and pull the enrichment fields:
    flood zone, vacancy/occupancy, judgment/foreclosure/mortgage, ownership
    type, taxes due, plus the Street View and satellite (parcel-boundary)
    images shown on the page.
    """
    page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    body_text = page.inner_text("body")
    kv = _parse_kv_lines(body_text)

    images = page.evaluate("""
        () => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const streetview = imgs.find(i => i.src.includes('streetview'));
            const satellite  = imgs.find(i => i.src.includes('staticmap') && i.src.includes('satellite'));
            return {
                street_view_image_url: streetview ? streetview.src : '',
                satellite_image_url:   satellite  ? satellite.src  : '',
            };
        }
    """)

    def yn(key):
        return kv.get(key, "").strip().lower()

    return {
        "flood_zone_type":       kv.get("Flood Zone Type", ""),
        "flood_zone_desc":       kv.get("Flood Zone Description", ""),
        "is_vacant":             yn("Is Vacant"),
        "owner_occupied":        yn("Owner Occupied"),
        "absentee_owner":        yn("Absentee Owner"),
        "has_judgment":          yn("Judgment"),
        "has_foreclosure":       yn("Foreclosure"),
        "is_free_and_clear":     yn("Free and Clear"),
        "open_mortgage_balance": kv.get("Open Mortgage Balance", ""),
        "negative_equity":       yn("Negative Equity"),
        "corporate_owned":       yn("Corporate Owned"),
        "deceased_owner":        yn("Deceased"),
        "taxes_due":             kv.get("Taxes Due", ""),
        "street_view_image_url": images.get("street_view_image_url", ""),
        "satellite_image_url":   images.get("satellite_image_url", ""),
    }


def scrape_auction_parcels(context, list_links, deep=True):
    """
    Full pipeline for one auction: open its parcel list (new tab), then for
    each parcel visit its detail page (a second, reused tab) to merge in the
    enrichment fields from scrape_parcel_detail().

    Args:
        deep: if False, only the list-page table is scraped (fast, no
              per-parcel detail visits).

    Returns: list of merged parcel dicts.
    """
    list_page = open_parcel_list(context, list_links)
    rows = scrape_parcel_list(list_page)

    if not deep or not rows:
        list_page.close()
        return rows

    detail_page = context.new_page()
    for i, row in enumerate(rows):
        if not row.get("detail_url"):
            continue
        print(f"    [{i+1}/{len(rows)}] {row['parcel_number']} — ", end="")
        try:
            extra = scrape_parcel_detail(detail_page, row["detail_url"])
            row.update(extra)
            print(f"flood={extra['flood_zone_type']} vacant={extra['is_vacant']} "
                  f"judgment={extra['has_judgment']} foreclosure={extra['has_foreclosure']}")
        except Exception as e:
            print(f"❌ error: {e}")
    detail_page.close()
    list_page.close()

    return rows


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TEST ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_parcelfair(target_month, target_year, location="All"):
    """Login, open the calendar, click the target month, print what was found."""
    from playwright.sync_api import sync_playwright as _sync_pw

    month_name = MONTH_NUM_TO_NAME[target_month]

    with _sync_pw() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        page = browser.new_context().new_page()

        login(page)
        listings = click_month(page, month_name, target_year, location=location)

        for item in listings:
            print(f"  {item['day']:20s} | {item['name']:40s} | "
                  f"{item['auction_type']:18s} | {item['status']}")

        browser.close()
        return listings


if __name__ == "__main__":
    import sys
    from datetime import datetime
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    now = datetime.now()
    mn = sys.argv[1] if len(sys.argv) > 1 else MONTH_NUM_TO_NAME[now.month]
    yr = int(sys.argv[2]) if len(sys.argv) > 2 else now.year
    from common import MONTH_NAMES
    run_parcelfair(MONTH_NAMES[mn.lower()], yr)
