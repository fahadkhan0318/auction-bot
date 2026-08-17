"""
govease.py — GovEase Online Tax Sale Scraper

GovEase URL pattern:
  https://liveauctions.govease.com/tx/tx{county}/{auction_id}/browse
  https://liveauctions.govease.com/tx/tx{county}/{auction_id}/browsestandard

No login needed to browse listings.

Steps:
1. Discover current auction ID for a county
2. Browse listings (paginated)
3. Click each property for details
4. Extract: Parcel#, Owner, Address, Min Bid, Status, Sold Amount

NOTE: sync_playwright imported LAZILY inside run_govease() only — avoids circular import.
"""

import re
from datetime import datetime
# No top-level playwright import — done lazily inside run_govease()

import common
from common import (
    make_unique_key, smart_save, save_db, rewrite_csv,
    MONTH_NUM_TO_NAME, GOVEASE_COUNTIES, SOLD_STATUSES
)

GOVEASE_BASE = "https://liveauctions.govease.com"

# ═══════════════════════════════════════════════════════════════════════════
# URL / AUCTION DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def build_govease_url(county_key, auction_id, mode="browse"):
    """Build GovEase browse URL."""
    base = GOVEASE_COUNTIES.get(county_key, "")
    if not base:
        return ""
    return f"{base}/{auction_id}/{mode}"


def discover_auction_id(page, county_key, target_month, target_year):
    """
    Discover the current auction ID for a county by browsing GovEase.
    Returns (auction_id, browse_url) or (None, None).
    """
    base_url    = GOVEASE_COUNTIES.get(county_key, "")
    month_name  = MONTH_NUM_TO_NAME[target_month]

    if not base_url:
        return None, None

    print(f"  🔍 GovEase: Discovering auction ID for {county_key} ({month_name} {target_year})")

    try:
        page.goto(GOVEASE_BASE + "/tx", timeout=15000)
        page.wait_for_timeout(2000)
        _dismiss_govease_popups(page)

        links = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('a[href*="/browse"]'))
                    .map(a => a.href)
                    .filter(h => h.includes('/tx/'))
                    .slice(0, 30);
            }
        """)

        for link in links:
            m = re.search(r'/tx/tx\w+/(\d+)/', link)
            if m:
                aid = m.group(1)
                test_url = link if "/browse" in link else link + "/browse"
                page.goto(test_url, timeout=10000)
                page.wait_for_timeout(1500)
                txt = page.inner_text("body").lower()
                if month_name.lower() in txt or str(target_year) in txt:
                    print(f"  ✅ Found auction ID: {aid} at {test_url}")
                    return aid, test_url

    except Exception as e:
        print(f"  ⚠️ GovEase discovery error: {e}")

    return None, None


# ═══════════════════════════════════════════════════════════════════════════
# POPUP / UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _dismiss_govease_popups(page):
    """Dismiss GovEase accessibility/disclaimer popups."""
    for btn_text in ["By continuing", "I acknowledge", "Continue", "OK", "Accept", "Close"]:
        try:
            btn = page.locator(
                f"button:has-text('{btn_text}'), "
                f"a:has-text('{btn_text}'), "
                f"input[value='{btn_text}']"
            )
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(800)
        except Exception:
            pass

    try:
        overlay = page.locator(".modal-overlay, .disclaimer-overlay, #disclaimer")
        if overlay.count() > 0 and overlay.first.is_visible():
            overlay.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY LISTING EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def collect_govease_listings(page, browse_url):
    """
    Collect all property listings from a GovEase browse page.
    Returns list of dicts: {parcel_id, url, text}.
    """
    all_listings = []

    page.goto(browse_url, timeout=20000)
    page.wait_for_timeout(3000)
    _dismiss_govease_popups(page)

    page_num  = 1
    max_pages = 50

    while page_num <= max_pages:
        print(f"  📄 GovEase page {page_num}: {page.url[:70]}")

        listings = page.evaluate("""
            () => {
                var results = [];

                var selectors = [
                    '.parcel-browse-item',
                    '.auction-parcel',
                    '.parcel-item',
                    '[class*="parcel-row"]',
                    '[class*="browse-item"]',
                    'tr.parcel',
                    '.property-listing-item'
                ];

                var items = [];
                for (var sel of selectors) {
                    var found = document.querySelectorAll(sel);
                    if (found.length > 0) { items = found; break; }
                }

                if (items.length === 0) {
                    var links = document.querySelectorAll('a[href*="/parcel/"], a[href*="/property/"]');
                    for (var lk of links) {
                        results.push({
                            parcel_id: (lk.innerText || '').trim().split('\\n')[0].trim(),
                            url: lk.href,
                            text: (lk.closest('tr,div,li') || lk).innerText || ''
                        });
                    }
                    return results;
                }

                for (var item of items) {
                    var link    = item.querySelector('a[href*="/parcel/"], a[href*="/property/"], a[href*="/item/"]');
                    var pidEl   = item.querySelector('[class*="parcel-id"], [class*="parcel_id"], .parcel-number');
                    var pid     = pidEl ? (pidEl.innerText||'').trim() : '';
                    if (!pid && link) pid = (link.innerText||'').trim().split('\\n')[0].trim();

                    results.push({
                        parcel_id: pid,
                        url: link ? link.href : '',
                        text: (item.innerText || '').trim().substring(0, 800)
                    });
                }
                return results;
            }
        """)

        if listings:
            all_listings.extend(listings)
            print(f"    Found {len(listings)} listings on page {page_num}")
        else:
            body = page.inner_text("body")
            if "no properties" in body.lower() or "no parcels" in body.lower():
                print(f"  ℹ️ No more properties")
                break
            if page_num == 1:
                print(f"  ⚠️ No listings found — trying table extraction")
                listings = _extract_table_listings(page)
                all_listings.extend(listings)
            break

        next_clicked = _click_next_page(page)
        if not next_clicked:
            break

        page.wait_for_timeout(2000)
        _dismiss_govease_popups(page)
        page_num += 1

    print(f"  ✅ Total GovEase listings collected: {len(all_listings)}")
    return all_listings


def _extract_table_listings(page):
    """Fallback: extract listings from table structure."""
    return page.evaluate("""
        () => {
            var results = [];
            var rows = document.querySelectorAll('table tr');
            for (var row of rows) {
                var cells = row.querySelectorAll('td');
                if (cells.length < 2) continue;
                var link = row.querySelector('a');
                var text = (row.innerText || '').trim();
                if (text.includes('$') || text.length > 30) {
                    results.push({
                        parcel_id: cells[0] ? (cells[0].innerText||'').trim() : '',
                        url: link ? link.href : '',
                        text: text.substring(0, 600)
                    });
                }
            }
            return results;
        }
    """)


def _click_next_page(page):
    """Click next page button. Returns True if clicked."""
    for selector in [
        "a:has-text('Next')", "a:has-text('NEXT')", "a:has-text('>')",
        "button:has-text('Next')", ".next-page", "[aria-label='Next page']",
        "a[rel='next']", ".pagination-next",
    ]:
        try:
            btn = page.locator(selector)
            if btn.count() > 0 and btn.first.is_visible() and btn.first.is_enabled():
                btn.first.click()
                page.wait_for_timeout(1500)
                return True
        except Exception:
            pass
    return False


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY DETAIL EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def scrape_govease_property(page, listing, county, auction_date):
    """
    Scrape a single GovEase property (from listing card or detail page).
    Returns property dict or None.
    """
    parcel_id  = listing.get("parcel_id", "").strip()
    detail_url = listing.get("url", "").strip()
    card_text  = listing.get("text", "").strip()

    detail_text = card_text
    if detail_url and detail_url.startswith("http"):
        try:
            page.goto(detail_url, timeout=15000)
            page.wait_for_timeout(2000)
            _dismiss_govease_popups(page)
            detail_text = page.inner_text("body")
        except Exception as e:
            print(f"    ⚠️ Detail page error: {e}")

    if not detail_text and not card_text:
        return None

    text = detail_text or card_text

    def _find(patterns, default=""):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return default

    account = parcel_id or _find([
        r'Parcel[:\s#]+([A-Za-z0-9\-]+)',
        r'Account[:\s#]+([A-Za-z0-9\-]+)',
        r'Parcel\s+No\.?[:\s]+([A-Za-z0-9\-]+)',
    ])

    if not account:
        account = f"GE-{county.upper()}-{hash(detail_url or card_text) % 99999}"

    cause_number = _find([
        r'Case\s*(?:No\.?|Number)[:\s]+([A-Za-z0-9\-]+)',
        r'Suit\s*(?:No\.?|#)[:\s]+([A-Za-z0-9\-]+)',
        r'\b(TX\d{5,})\b',
    ], account)

    owner = _find([
        r'Owner[:\s]+([^\n\$]{3,60})',
        r'Defendant[:\s]+([^\n\$]{3,60})',
        r'vs?\.?\s+([^\n\$]{3,60})',
    ])

    address = _find([
        r'(?:Property\s+)?Address[:\s]+([^\n]{5,80})',
        r'Location[:\s]+([^\n]{5,80})',
        r'(\d+\s+[A-Za-z][^,\n]{5,50}(?:St|Ave|Dr|Rd|Ln|Blvd|Hwy|FM|CR)[^\n,]*)',
    ])

    bids    = re.findall(r'\$[\d,]+\.\d{2}', text)
    min_bid = bids[0] if bids else ""

    status = _extract_govease_status(text)

    sold_amount = ""
    buyer_name  = ""
    if status == "Sold" and len(bids) >= 2:
        sold_amount = bids[-1]
        bm = re.search(r'(?:Sold\s+To|Winner|Buyer|Winning\s+Bidder)[:\s]+([^\n\$]{3,60})', text, re.IGNORECASE)
        if bm:
            buyer_name = bm.group(1).strip()

    legal = _find([
        r'Legal\s+Description[:\s]+([^\n]{10,200})',
        r'Description[:\s]+([^\n]{10,200})',
    ])

    unique_key = make_unique_key(county, account, source="GOVEASE")

    return {
        "Unique Key":        unique_key,
        "Source":            "GOVEASE",
        "County":            county.upper(),
        "Cause Number":      cause_number,
        "Link":              detail_url or "",
        "Auction Date":      auction_date,
        "Status":            status,
        "Min Bid":           min_bid,
        "Adjusted Value":    "",
        "Property Address":  address,
        "Account Number":    account,
        "Legal Description": legal,
        "Owner Name":        owner,
        "Buyer Name":        buyer_name,
        "Sold Amount":       sold_amount,
        "Winning Bid":       sold_amount,
        "Sale Date":         "",
        "Last Updated":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Zillow":             _make_zillow_link(address),
        "Satellite View":     _make_satellite_link(address),
        "Appraisal District": "",
        "Property Map":       "",
    }


def _extract_govease_status(text):
    """Extract status from GovEase property text."""
    t = text.lower()
    if "sold"          in t: return "Sold"
    if "struck off"    in t: return "Struck Off"
    if "cancelled"     in t: return "Cancelled"
    if "canceled"      in t: return "Cancelled"
    if "withdrawn"     in t: return "Cancelled"
    if "paid"          in t: return "Paid in Full"
    if "redeemed"      in t: return "Redeemed"
    if "no bid"        in t: return "Pulled for no bids"
    return "Pending"


def _make_zillow_link(address):
    if not address or len(address) < 5:
        return ""
    import urllib.parse
    q = urllib.parse.quote(address)
    return f"https://www.zillow.com/homes/{q}_rb/"


def _make_satellite_link(address):
    if not address or len(address) < 5:
        return ""
    import urllib.parse
    q = urllib.parse.quote(address)
    return f"https://www.google.com/maps?q={q}&t=k"


# ═══════════════════════════════════════════════════════════════════════════
# GOVEASE URLs — from MVBA page
# ═══════════════════════════════════════════════════════════════════════════

def get_govease_urls_from_mvba(target_month, target_year):
    """
    Check MVBA page for GovEase auction URLs for target month.
    Returns list of (county, url) tuples.
    """
    from mvba import fetch_mvba_page_with_playwright, parse_mvba_listings_for_month

    raw_links = fetch_mvba_page_with_playwright()
    if not raw_links:
        return []

    listings = parse_mvba_listings_for_month(raw_links, target_month, target_year)
    return [
        (l["county"], l["online_url"])
        for l in listings
        if l["online_type"] == "GOVEASE"
    ]


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_govease(target_month, target_year, db, csv_rows, govease_urls=None):
    """
    Main GovEase scraper entry point.
    govease_urls: optional list of (county, url)
    """
    print(f"\n{'='*45}")
    print(f"  🟢 GOVEASE SCRAPER — {MONTH_NUM_TO_NAME[target_month]} {target_year}")
    print(f"{'='*45}")

    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    if not govease_urls:
        govease_urls = get_govease_urls_from_mvba(target_month, target_year)

    # Add configured counties not already in the list
    config_counties = set(c for c, _ in govease_urls)
    for county_key, base_url in GOVEASE_COUNTIES.items():
        if county_key not in config_counties:
            govease_urls.append((county_key, None))

    if not govease_urls:
        print(f"  ⚠️ No GovEase URLs found for {MONTH_NUM_TO_NAME[target_month]} {target_year}")
        return stats

    print(f"\n  📊 GovEase counties to scrape: {len(govease_urls)}")
    for county, url in govease_urls:
        print(f"     {county.upper()}: {(url or 'auto-discover')[:60]}")

    # Lazy import — no circular import risk
    from playwright.sync_api import sync_playwright as _sync_pw
    with _sync_pw() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        context = browser.new_context()
        page    = context.new_page()

        for county, url in govease_urls:
            try:
                print(f"\n  🟢 GovEase County: {county.upper()}")
                auction_date = f"{MONTH_NUM_TO_NAME[target_month]} {target_year}"

                # Resolve browse URL
                if url and "/browse" in url:
                    browse_url = url
                elif url:
                    browse_url = url if url.endswith("/browse") else url + "/browse"
                else:
                    auction_id, browse_url = discover_auction_id(
                        page, county, target_month, target_year
                    )
                    if not browse_url:
                        print(f"  ⚠️ Could not discover auction for {county}")
                        continue

                listings = collect_govease_listings(page, browse_url)

                if not listings:
                    print(f"  ⚠️ No listings found for {county}")
                    continue

                total = len(listings)
                for i, listing in enumerate(listings):
                    print(f"    [{i+1}/{total}] Parcel: {listing.get('parcel_id','?')}")
                    try:
                        prop = scrape_govease_property(page, listing, county, auction_date)
                        if prop:
                            result = smart_save(prop, db, csv_rows, "GOVEASE")
                            stats[result] = stats.get(result, 0) + 1
                            print(f"      Status='{prop['Status']}' | "
                                  f"Addr='{prop['Property Address'][:40]}' | "
                                  f"MinBid='{prop['Min Bid']}'")
                    except Exception as e:
                        print(f"      ❌ Property error: {e}")
                        stats["error"] += 1

                rewrite_csv(csv_rows)

            except Exception as e:
                print(f"  ❌ GovEase county error ({county}): {e}")
                stats["error"] += 1

        browser.close()

    print(f"\n  ✅ GovEase Done: New={stats['new']} Updated={stats['updated']} "
          f"Skipped={stats['skipped']} Error={stats.get('error',0)}")
    return stats