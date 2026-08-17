"""
linebarger.py — Linebarger Goggan Blair & Sampson Tax Sale Scraper
Website: taxsales.lgbs.com  (AngularJS SPA)

DOM facts (from DevTools inspection):
  cards  : article.result  (ng-repeat="property in map.properties")
  modal  : opened via  a.view-more  (ng-click="listing.openDetailModal()")
  legal  : click  a  with text "more"  inside modal to expand

Flow per county:
  1. Select county in Sale County dropdown (filter to items ending ", TX")
  2. Count visible  article.result  cards
  3. For each card:
       a. read address from card heading (before key-value rows)
       b. click  a.view-more  → modal opens
       c. click "more..." → full legal description loads
       d. parse every field from modal text
       e. close modal  (button.close / × / Escape)
"""

import re, calendar
from datetime import datetime

import common
from common import make_unique_key, smart_save, save_db, rewrite_csv, MONTH_NUM_TO_NAME

LGBS_BASE = "https://taxsales.lgbs.com/"
LGBS_URL  = (
    "https://taxsales.lgbs.com/map"
    "?lat=39.576604&lon=-96.721782&zoom=4&offset=0"
    "&ordering=precinct,sale_nbr,uid"
    "&sale_type=SALE,RESALE,STRUCK%20OFF,FUTURE%20SALE"
    "&in_bbox=-137.239360125,17.020699535177002,"
    "-56.204203875,56.63547564938025"
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_first_tuesday(month, year):
    """Return first Tuesday of given month, e.g. 'Jul 7, 2026'."""
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        if week[calendar.TUESDAY] != 0:
            day = week[calendar.TUESDAY]
            abbr = datetime(year, month, day).strftime("%b")
            return f"{abbr} {day}, {year}"
    return None


def _make_zillow_link(address):
    if not address or len(address) < 5:
        return ""
    import urllib.parse
    return f"https://www.zillow.com/homes/{urllib.parse.quote(address)}_rb/"


def _field(label, text, default=""):
    """
    Extract value after a labelled field in modal text.
    Handles two layouts produced by inner_text():
      (a) same-line  → 'Sale Number: 2026-001'
      (b) next-line  → 'Sale Number\n2026-001'   (AngularJS dl/dt/dd)
    """
    # Same-line with colon separator
    m = re.search(
        rf'{re.escape(label)}\s*:\s*([^\n\r]+)',
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    # Next-line: label on its own line, value on the very next non-empty line
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if re.match(rf'^\s*{re.escape(label)}\s*$', line, re.IGNORECASE):
            # Look ahead for first non-empty line
            for nxt in lines[idx + 1:]:
                v = nxt.strip()
                if v:
                    return v
            break

    return default


def _dismiss_popups(page):
    for txt in ["Accept", "OK", "I Agree", "Continue", "Close", "Got it"]:
        try:
            btn = page.locator(
                f"button:has-text('{txt}'), "
                f"input[value='{txt}'], a:has-text('{txt}')"
            )
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(400)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# DROPDOWN — SALE DATE
# ═══════════════════════════════════════════════════════════════════════════

def select_sale_date(page, target_date_str):
    """
    Click the Sale Date filter header and pick the matching date.
    target_date_str  : 'Jul 7, 2026'
    DOM may render it as 'JUL 7, 2026' via CSS text-transform — match both.
    """
    print(f"  📅 Selecting sale date: {target_date_str}")
    target_upper = target_date_str.upper()  # "JUL 7, 2026"

    try:
        page.locator("text=Sale Date").first.click()
        page.wait_for_timeout(3000)

        # Try matching by inner text (case-insensitive loop)
        for sel in [
            "ul.dropdown-menu li",
            "[role='listbox'] li",
            "[role='option']",
            ".dropdown-menu a",
            "ul li",
        ]:
            items = page.locator(sel)
            for i in range(items.count()):
                try:
                    txt = items.nth(i).inner_text().strip().upper()
                    if txt == target_upper:
                        items.nth(i).click()
                        page.wait_for_timeout(2500)
                        print(f"  ✅ Date selected")
                        return True
                except Exception:
                    pass

        # Playwright text selector fallback
        for candidate in [target_date_str, target_upper]:
            opt = page.locator(f"text={candidate}").first
            if opt.count() > 0 and opt.is_visible():
                opt.click()
                page.wait_for_timeout(2500)
                print(f"  ✅ Date selected")
                return True

        # Nothing matched — report available dates
        body = page.inner_text("body")
        found = re.findall(
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b',
            body, re.IGNORECASE
        )
        if found:
            print(f"  ⚠️ '{target_date_str}' not in dropdown. "
                  f"Available: {list(dict.fromkeys(f.upper() for f in found))}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return False

    except Exception as e:
        print(f"  ❌ Date select error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# DROPDOWN — SALE COUNTY
# ═══════════════════════════════════════════════════════════════════════════

def get_available_counties(page):
    """
    Open the Sale County dropdown.
    Return ONLY items that end with 'COUNTY, TX' — skip share/export/status items.
    Example: ['ARANSAS COUNTY, TX', 'DALLAS COUNTY, TX', ...]
    """
    counties = []
    try:
        page.locator("text=Sale County").first.click()
        page.wait_for_timeout(3000)

        for sel in [
            "ul.dropdown-menu li",
            "[role='listbox'] li",
            "[role='option']",
            ".dropdown-menu a",
            "ul li",
        ]:
            items = page.locator(sel)
            if items.count() > 0:
                for i in range(items.count()):
                    try:
                        txt = items.nth(i).inner_text().strip().upper()
                        if re.search(r'COUNTY,\s*TX$', txt):
                            if txt not in counties:
                                counties.append(txt)
                    except Exception:
                        pass
                if counties:
                    break

        # Fallback: scan body text
        if not counties:
            body = page.inner_text("body").upper()
            counties = list(dict.fromkeys(
                re.findall(r'[A-Z][A-Z ]+COUNTY,\s*TX', body)
            ))

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    except Exception as e:
        print(f"  ❌ County list error: {e}")

    print(f"  📋 {len(counties)} counties found")
    return counties


def select_county(page, county_name):
    """
    Open Sale County dropdown and click the named county.
    county_name is uppercase e.g. 'ARANSAS COUNTY, TX'.
    """
    try:
        sale_county = page.locator("text=Sale County").first
        sale_county.wait_for(state="visible", timeout=8000)
        sale_county.click(timeout=8000)
        page.wait_for_timeout(800)

        target = county_name.strip().upper()

        for sel in [
            "ul.dropdown-menu li",
            "[role='listbox'] li",
            "[role='option']",
            ".dropdown-menu a",
            "ul li",
        ]:
            items = page.locator(sel)
            for i in range(items.count()):
                try:
                    txt = items.nth(i).inner_text().strip().upper()
                    if txt == target:
                        items.nth(i).click()
                        page.wait_for_timeout(2500)
                        # Make sure dropdown is fully closed
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                        # Wait for new county's cards to appear
                        try:
                            page.wait_for_selector("article.result", timeout=10000)
                            page.wait_for_selector(
                                "a.view-more, a:has-text('More details')",
                                timeout=8000
                            )
                            page.wait_for_timeout(800)
                        except Exception:
                            pass
                        print(f"  ✅ County selected: {county_name}")
                        return True
                except Exception:
                    pass

        # Playwright text selector fallback
        for candidate in [county_name, county_name.title()]:
            opt = page.locator(f"text={candidate}").first
            if opt.count() > 0 and opt.is_visible():
                opt.click()
                page.wait_for_timeout(2500)
                print(f"  ✅ County selected: {county_name}")
                return True

        print(f"  ⚠️ County not found in dropdown: {county_name}")
        page.keyboard.press("Escape")
        return False

    except Exception as e:
        print(f"  ❌ County select error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# CARD ADDRESS EXTRACTION  (before opening modal)
# ═══════════════════════════════════════════════════════════════════════════

_CARD_ADDRESS_JS = """
(function(index) {
    var cards = document.querySelectorAll('article.result');
    if (index >= cards.length) return '';
    var card = cards[index];

    // Try dedicated heading/title elements first
    var heading = card.querySelector(
        '.result-title, h2, h3, h4, [class*="title"], [class*="address"]'
    );
    if (heading) return heading.innerText.trim();

    // Fallback: first text line that looks like an address
    // (contains a digit, is long enough, and is NOT a key-value label)
    var skipPat = /^(Sale Date|Sale Type|Adjudged|Cause Number|Precinct|Sale Number|Est\\.\\s*min|Status|GET UPDATES|More details|No Image)/i;
    var lines = (card.innerText || '').split('\\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line.length > 8 && /\\d/.test(line) && !skipPat.test(line)) {
            return line;
        }
    }
    return '';
})(CARD_INDEX)
"""


def _get_card_address(page, card_index):
    try:
        js = _CARD_ADDRESS_JS.replace("CARD_INDEX", str(card_index))
        return page.evaluate(js) or ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# MODAL — OPEN / PARSE / CLOSE
# ═══════════════════════════════════════════════════════════════════════════

def _open_detail_modal(page, card_index):
    """Click the index-th  a.view-more  link and wait for modal."""
    # Close any stale modal that may still be open
    if _modal_is_open(page):
        _close_modal(page)
        page.wait_for_timeout(400)

    try:
        links = page.locator("a.view-more, a:has-text('More details')")
        if card_index >= links.count():
            return False
        link = links.nth(card_index)
        link.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        link.click()
        # Wait for modal to become visible
        try:
            page.wait_for_selector(
                ".modal.in, .modal-dialog, [role='dialog'], "
                "[class*='modal'][aria-modal='true']",
                timeout=6000
            )
        except Exception:
            pass
        page.wait_for_timeout(600)
        return _modal_is_open(page)  # confirm it actually opened
    except Exception as e:
        print(f"      ❌ open modal error: {e}")
        return False


def _expand_legal_desc(page):
    """Click 'more...' inside the open modal to load the full legal description."""
    try:
        more = page.locator(
            ".modal a:has-text('more'), "
            ".modal a:has-text('more...'), "
            "[role='dialog'] a:has-text('more')"
        )
        if more.count() > 0 and more.first.is_visible():
            more.first.click()
            page.wait_for_timeout(800)
    except Exception:
        pass


def _modal_is_open(page):
    """Return True if a modal dialog is currently visible on screen."""
    try:
        return bool(page.evaluate("""
            () => {
                var m = document.querySelector('.modal.in, .modal.show');
                if (m && m.offsetWidth > 0) return true;
                var md = document.querySelector('.modal-dialog');
                if (md && md.offsetParent !== null) return true;
                var rd = document.querySelector('[role="dialog"]');
                if (rd && rd.offsetWidth > 0) return true;
                return false;
            }
        """))
    except Exception:
        return False


def _close_modal(page):
    """
    Close the Property Details modal.
    Method 1: AngularJS $dismiss via JavaScript (most reliable for ng modal)
    Method 2: click button.close / [data-dismiss]
    Method 3: Escape key
    Method 4: click backdrop corner
    Verifies closure after each attempt; retries up to 3 rounds.
    """
    for attempt in range(3):
        if not _modal_is_open(page):
            return  # already closed

        # ── Method 1: JavaScript / AngularJS dismiss ──────────────────────
        try:
            page.evaluate("""
                () => {
                    // Try Angular $dismiss on the modal scope
                    try {
                        var candidates = document.querySelectorAll(
                            '.modal.in, .modal.show, .modal-dialog, [role="dialog"]'
                        );
                        for (var el of candidates) {
                            var scope = angular && angular.element(el).scope();
                            if (!scope) continue;
                            if (scope.$dismiss) { scope.$dismiss('cancel'); scope.$apply(); return; }
                            if (scope.$close)   { scope.$close();           scope.$apply(); return; }
                            // Walk parent scopes
                            var ps = scope.$parent;
                            while (ps) {
                                if (ps.$dismiss) { ps.$dismiss('cancel'); ps.$apply(); return; }
                                ps = ps.$parent;
                            }
                        }
                    } catch(e) {}

                    // DOM click fallback
                    var btn = document.querySelector(
                        'button.close, [data-dismiss="modal"], .modal-header button, '
                        + '[ng-click*="close"], [ng-click*="dismiss"], [ng-click*="cancel"]'
                    );
                    if (btn && btn.offsetParent !== null) { btn.click(); }
                }
            """)
            page.wait_for_timeout(700)
            if not _modal_is_open(page):
                return
        except Exception:
            pass

        # ── Method 2: Playwright selector click ───────────────────────────
        for sel in [
            "button.close", ".modal-header .close", ".modal .close",
            "button[aria-label='Close']", "[data-dismiss='modal']",
            ".modal-header button",
        ]:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(force=True)
                    page.wait_for_timeout(600)
                    if not _modal_is_open(page):
                        return
                    break
            except Exception:
                pass

        # ── Method 3: Escape ──────────────────────────────────────────────
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            if not _modal_is_open(page):
                return
        except Exception:
            pass

    # ── Method 4: click far outside (backdrop) ────────────────────────────
    try:
        page.mouse.click(5, 5)
        page.wait_for_timeout(500)
    except Exception:
        pass


def _parse_modal(page, county_name, card_address, auction_date):
    """
    Extract all fields from the open Property Details modal.
    Modal structure (from screenshots):
      County | Sale Type | Sale Date | Account Number | Adjudged Value
      Est. Minimum Bid | Status | Link to Online Auction Site
      --- Sale Information ---
      Sale Number | Cause Number | Court Number | Precinct
      Case Style  | Judgment Date | Legal Description
      [Property Location on Google Maps] button
    """
    # Only read from the MODAL element — never fall back to full body text.
    # Falling back to body causes account numbers from list cards to leak in
    # and every subsequent card appears as a duplicate.
    modal_text = ""
    for sel in [
        ".modal.in .modal-body",
        ".modal.show .modal-body",
        ".modal-dialog .modal-body",
        ".modal.in",
        ".modal.show",
        ".modal-dialog",
        "[role='dialog']",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                t = el.inner_text()
                if t and len(t.strip()) > 30:
                    modal_text = t
                    break
        except Exception:
            pass

    if not modal_text:
        return None  # modal is not open — skip this card cleanly

    # ── Google Maps link from "Property Location on Google Maps" button ───
    maps_url = ""
    try:
        maps_btn = page.locator(
            "a:has-text('Property Location on Google Maps'), "
            ".modal a[href*='google.com/maps'], "
            ".modal a[href*='maps.google']"
        )
        if maps_btn.count() > 0:
            maps_url = maps_btn.first.get_attribute("href") or ""
    except Exception:
        pass

    # ── Online Auction Site link ───────────────────────────────────────────
    auction_link = ""
    try:
        al = page.locator(
            "a:has-text('Link to Online Auction Site'), "
            ".modal a[href*='auction']"
        )
        if al.count() > 0:
            auction_link = al.first.get_attribute("href") or ""
    except Exception:
        pass

    # ── Field extraction ──────────────────────────────────────────────────
    account_number = _field("Account Number", modal_text)
    adjudged_val   = _field("Adjudged Value",  modal_text)
    min_bid        = _field("Est. Minimum Bid", modal_text)
    status_raw     = _field("Status",           modal_text)
    sale_date_val  = _field("Sale Date",        modal_text)
    sale_type      = _field("Sale Type",        modal_text)
    sale_number    = _field("Sale Number",      modal_text)
    cause_number   = _field("Cause Number",     modal_text)
    court_number   = _field("Court Number",     modal_text)
    precinct       = _field("Precinct",         modal_text)
    case_style     = _field("Case Style",       modal_text)
    judgment_date  = _field("Judgment Date",    modal_text)
    legal_desc     = _field("Legal Description", modal_text)
    # Strip trailing "more..." if still present
    legal_desc = re.sub(r'\s*more\.{0,3}$', '', legal_desc, flags=re.IGNORECASE).strip()

    # ── Owner Name from Case Style (after "VS") ────────────────────────────
    owner_name = ""
    if case_style:
        vs_m = re.search(r'\bVS\.?\s+(.+)', case_style, re.IGNORECASE | re.DOTALL)
        if vs_m:
            owner_name = vs_m.group(1).strip()

    # ── Address: try modal heading first, then card address ──────────────
    # Modal shows address as a large heading above the County/Sale Type fields
    address = ""
    try:
        for sel in [
            ".modal h1", ".modal h2", ".modal h3", ".modal h4",
            ".modal .property-title", ".modal [class*='title']",
            ".modal-body h1", ".modal-body h2", ".modal-body h3",
        ]:
            el = page.locator(sel).first
            if el.count() > 0:
                txt = el.inner_text().strip()
                # Skip "Property Details" and similar non-address headings
                if txt and "Property Details" not in txt and len(txt) > 5:
                    address = txt
                    break
    except Exception:
        pass

    if not address:
        address = card_address  # fallback to card heading extracted before modal

    if not address:
        # Last resort: regex scan of modal text for address-like pattern
        addr_m = re.search(
            r'(\d+\s+[A-Za-z][^\n]{5,80}(?:TX|Texas)(?:\s*\d{5})?)',
            modal_text, re.IGNORECASE
        )
        if addr_m:
            address = addr_m.group(1).strip()

    # ── Normalise county ──────────────────────────────────────────────────
    # When county_name is None (all-at-once mode), extract it from modal text
    if county_name:
        county_clean = re.sub(r'\s+COUNTY,?\s*TX$', '', county_name, flags=re.IGNORECASE).strip().upper()
    else:
        county_raw   = _field("County", modal_text)
        county_clean = re.sub(r'\s+COUNTY,?\s*TX$', '', county_raw, flags=re.IGNORECASE).strip().upper()
        if not county_clean:
            county_clean = "UNKNOWN"

    if not account_number:
        account_number = (
            sale_number
            or cause_number
            or f"LGBS-{county_clean}-{abs(hash(modal_text[:80])) % 999999}"
        )

    uk = make_unique_key(county_clean.lower(), account_number, source="LINEBARGER")

    return {
        "Unique Key":        uk,
        "Source":            "LINEBARGER",
        "County":            county_clean,
        "Cause Number":      cause_number,
        "Item Number":       sale_number,
        "Link":              auction_link,
        "Auction Date":      auction_date,
        "Status":            status_raw or "Pending",
        "Min Bid":           min_bid,
        "Adjusted Value":    adjudged_val,
        "Property Address":  address,
        "Account Number":    account_number,
        "Legal Description": legal_desc,
        "Owner Name":        owner_name,
        "Buyer Name":        "",
        "Sold Amount":       "",
        "Winning Bid":       "",
        "Sale Date":         sale_date_val,
        "Last Updated":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Zillow":            _make_zillow_link(address),
        "Satellite View":    maps_url or (
            f"https://www.google.com/maps?q={__import__('urllib.parse').parse.quote(address)}&t=k"
            if address else ""
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# SCRAPE ONE COUNTY
# ═══════════════════════════════════════════════════════════════════════════

def scrape_county_properties(page, county_name, auction_date):
    """
    After county is already selected in the filter:
    - Wait for cards to load
    - For each  article.result  card:
        1. Read address from card heading
        2. Click  a.view-more  → modal opens
        3. Click 'more...' → full legal description
        4. Parse all modal fields
        5. Close modal
    - Handle Next-page pagination if present
    """
    properties = []

    page.wait_for_timeout(2000)

    # Read total property count shown in results header ("6 properties")
    try:
        body = page.inner_text("body")
        total_m = re.search(r'(\d+)\s+propert', body, re.IGNORECASE)
        total_reported = int(total_m.group(1)) if total_m else "?"
    except Exception:
        total_reported = "?"
    label = county_name if county_name else "All Counties"
    print(f"    📊 {total_reported} properties reported for {label}")

    page_num = 0
    while True:
        page_num += 1

        # Wait for cards
        try:
            page.wait_for_selector("article.result", timeout=8000)
        except Exception:
            print(f"    ℹ️ No article.result cards found — done")
            break

        card_count = page.locator("article.result").count()
        if card_count == 0:
            print(f"    ℹ️ 0 cards on page {page_num} — done")
            break

        print(f"    🗂️  Page {page_num} — {card_count} cards")

        for i in range(card_count):
            print(f"    [Card {i+1}/{card_count}] ", end="", flush=True)

            try:
                card_address = _get_card_address(page, i)

                if not _open_detail_modal(page, i):
                    print("could not open modal — skip")
                    continue

                if not _modal_is_open(page):
                    print("modal not visible — skip")
                    continue

                _expand_legal_desc(page)

                prop = _parse_modal(page, county_name, card_address, auction_date)

                if prop:
                    properties.append(prop)
                    print(
                        f"Acct={prop['Account Number']} | "
                        f"Cause={prop['Cause Number']} | "
                        f"Owner='{prop['Owner Name'][:30]}' | "
                        f"{prop['Status']}"
                    )
                else:
                    print("no data parsed")

                _close_modal(page)
                page.wait_for_timeout(400)

            except Exception as e:
                print(f"\n      ❌ Card {i} error: {e}")
                try:
                    _close_modal(page)
                    page.wait_for_timeout(400)
                except Exception:
                    pass

        # ── Pagination ────────────────────────────────────────────────────
        # Wait a moment for AngularJS to finish rendering the pagination bar
        page.wait_for_timeout(800)

        pg_info = page.evaluate("""
            () => {
                var active = document.querySelector(
                    '.pagination .active a, .pagination .active span'
                );
                var cur = active ? (parseInt(active.textContent.trim()) || 1) : 1;

                var nums = Array.from(document.querySelectorAll(
                    '.pagination li a, .pagination li span'
                )).map(function(el){ return parseInt(el.textContent.trim()); })
                  .filter(function(n){ return !isNaN(n) && n > 0; });

                var total = nums.length ? Math.max.apply(null, nums) : 1;
                return [cur, total];
            }
        """)
        cur_pg, total_pg = pg_info[0], pg_info[1]

        # If pagination shows only 1 page but a Next link exists, trust Next
        if total_pg == 1:
            next_exists = page.locator("a:has-text('Next'), button:has-text('Next')").count() > 0
            if not next_exists:
                print(f"    ✅ Single page — done")
                break
            # Can't determine total — let Next drive pagination
            total_pg = cur_pg + 1

        print(f"    (page {cur_pg}/{total_pg})")

        if cur_pg >= total_pg:
            print(f"    ✅ Last page reached")
            break

        next_page = cur_pg + 1

        # Click the specific page-number button (more reliable than "Next")
        pg_btn = page.locator(
            f"ul.pagination li:not(.active) a:has-text('{next_page}'), "
            f"ul.pagination li:not(.active) span:has-text('{next_page}')"
        )
        if pg_btn.count() > 0:
            # Get first card text before click to detect reload
            try:
                card_before = page.locator("article.result").first.inner_text()
            except Exception:
                card_before = ""
            pg_btn.first.click()
        else:
            # Fallback: click Next
            next_btn = page.locator("a:has-text('Next'), button:has-text('Next')")
            if next_btn.count() == 0:
                break
            try:
                card_before = page.locator("article.result").first.inner_text()
            except Exception:
                card_before = ""
            next_btn.first.click()

        # Wait for cards to change (AngularJS re-renders list after page change)
        for _ in range(15):
            page.wait_for_timeout(500)
            try:
                card_after = page.locator("article.result").first.inner_text()
                if card_after != card_before:
                    break
            except Exception:
                pass

        # Confirm page advanced
        new_pg = page.evaluate("""
            () => {
                var a = document.querySelector(
                    '.pagination .active a, .pagination .active span'
                );
                return a ? (parseInt(a.textContent.trim()) || 0) : 0;
            }
        """)
        if new_pg > 0 and new_pg <= cur_pg:
            print(f"    ⚠️ Page did not advance ({cur_pg} → {new_pg}) — stopping")
            break

    label = county_name if county_name else "All Counties"
    print(f"  ✅ {label}: {len(properties)} properties scraped")
    return properties


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_linebarger(target_month, target_year, db, csv_rows,
                   selected_counties=None, county_picker=None):
    """
    Main Linebarger entry point.

    Args:
        selected_counties : pre-filtered county list (skips discovery step).
        county_picker     : callable(label, county_list) → selected_list.
                            If provided (and selected_counties is None), the
                            counties are discovered from the live site first,
                            then the picker is called so the user can filter —
                            all within the same browser session.
    """
    from playwright.sync_api import sync_playwright as _sync_pw

    print(f"\n{'='*50}")
    print(f"  🔶 LINEBARGER — {MONTH_NUM_TO_NAME[target_month]} {target_year}")
    print(f"{'='*50}")

    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    target_date_str = get_first_tuesday(target_month, target_year)
    if not target_date_str:
        print(f"  ❌ Cannot determine first Tuesday for "
              f"{MONTH_NUM_TO_NAME[target_month]} {target_year}")
        return stats
    print(f"  📅 First Tuesday: {target_date_str}")

    with _sync_pw() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        page    = browser.new_context().new_page()

        try:
            print(f"\n  🌐 Loading taxsales.lgbs.com…")

            # Step 1: Load homepage first so AngularJS app initialises
            # (direct deep-link with long query string sometimes times out)
            loaded = False
            for attempt, (url, label) in enumerate([
                (LGBS_BASE, "homepage"),
                ("https://taxsales.lgbs.com/map", "map (no params)"),
                (LGBS_URL,  "map (full URL)"),
            ], start=1):
                try:
                    print(f"  🔄 Attempt {attempt}: {label}")
                    page.goto(url, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    _dismiss_popups(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    _dismiss_popups(page)
                    loaded = True
                    print(f"  ✅ Loaded: {page.url}")
                    break
                except Exception as _nav_err:
                    print(f"  ⚠️ Attempt {attempt} failed: {_nav_err}")
                    page.wait_for_timeout(3000)

            if not loaded:
                raise RuntimeError("Could not load taxsales.lgbs.com after 3 attempts")

            # Step 2: If we landed on homepage (not map), navigate to map
            if "/map" not in page.url:
                print(f"  ↩️ Not on map page ({page.url!r}) — navigating to map…")
                try:
                    page.goto(LGBS_URL, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    _dismiss_popups(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                except Exception:
                    # Fallback: map without query params, let filters be set manually
                    page.goto("https://taxsales.lgbs.com/map", timeout=90000,
                              wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

            # Step 3: Confirm map is ready (Sale Date filter visible)
            try:
                page.wait_for_selector("text=Sale Date", timeout=20000)
            except Exception:
                print("  ⚠️ Sale Date filter not visible — page may not have loaded correctly")

            print(f"  ✅ Map page loaded: {page.url}")

            # ── 1. Select target sale date ────────────────────────────────
            select_sale_date(page, target_date_str)

            # ── 2. Determine which counties to process ────────────────────
            if selected_counties is not None:
                all_available = selected_counties
                counties      = selected_counties
            else:
                all_available = get_available_counties(page)
                if county_picker and all_available:
                    counties = county_picker("LINEBARGER", all_available)
                else:
                    counties = all_available

            if not counties:
                print(f"  ❌ No counties to process — stopping")
                return stats

            # ── 3. Process each county one by one ────────────────────────
            print(f"\n  📍 {len(counties)} county(ies) selected\n")
            for county in counties:
                print(f"\n  {'─'*40}")
                print(f"  📍 {county}")

                # If the page navigated away from the map, re-navigate and
                # re-apply the date filter before selecting the next county.
                if "/map" not in page.url:
                    print(f"  ↩️  Off map page ({page.url!r}) — re-navigating…")
                    page.goto(LGBS_URL, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    select_sale_date(page, target_date_str)

                # Also verify the Sale County filter is actually visible;
                # if not, the map view hasn't rendered — try a reload once.
                if page.locator("text=Sale County").count() == 0:
                    print(f"  ⚠️  Sale County filter missing — reloading map…")
                    page.goto(LGBS_URL, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    select_sale_date(page, target_date_str)

                try:
                    if not select_county(page, county):
                        stats["error"] += 1
                        continue

                    props = scrape_county_properties(page, county, target_date_str)

                    for prop in props:
                        r = smart_save(prop, db, csv_rows, "LINEBARGER")
                        stats[r] = stats.get(r, 0) + 1

                    rewrite_csv(csv_rows)
                    save_db(db)

                except Exception as e:
                    print(f"  ❌ County '{county}' error: {e}")
                    import traceback; traceback.print_exc()
                    stats["error"] += 1

        except Exception as e:
            print(f"  ❌ Linebarger scraper fatal error: {e}")
            import traceback; traceback.print_exc()

        finally:
            browser.close()

    print(f"\n{'='*50}")
    print(f"  ✅ Linebarger Done — "
          f"New={stats['new']} Updated={stats['updated']} "
          f"Skipped={stats['skipped']} Error={stats.get('error', 0)}")
    return stats
