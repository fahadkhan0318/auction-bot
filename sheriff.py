"""
sheriff.py — Sheriff / Realforeclose Scraper Module

Called by main.py — do NOT run directly.
All shared state (sheet, MAIN_CSV, DB_FILE) injected by main.py.

FIX: Removed top-level `from playwright.sync_api import sync_playwright`
     because main.py owns the Playwright context and passes `page` in.
     This eliminates the circular import error.
"""

from dotenv import load_dotenv
import os, csv, json, re
from datetime import datetime

import common
from common import (
    make_unique_key, smart_save, save_db, rewrite_csv, update_google_sheet,
    MONTH_NAMES, MONTH_NUM_TO_NAME, SOLD_STATUSES, NONSOLD_STATUSES,
    STATUS_KEYWORDS_ORDERED, CSV_FIELDS
)

# ── globals injected by main.py ───────────────────────────────────────────
sheet    = None
MAIN_CSV = ""
DB_FILE  = ""

load_dotenv()
USERNAME = os.getenv("USER")
PASSWORD = os.getenv("PASS")

COUNTY_BASE_URLS = {
    "travis":     "https://travis.texas.realforeclose.com/",
    "montgomery": "https://montgomery.texas.realforeclose.com/"
}


def get_county_url(county):
    return COUNTY_BASE_URLS.get(county, f"https://{county}.texas.sheriffsaleauctions.com/")


# ═══════════════════════════════════════════════════════════════════════════
# BROWSER HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def login(page):
    page.fill("#LogName", USERNAME)
    page.fill("#LogPass", PASSWORD)
    page.click("#LogButton")
    page.wait_for_timeout(2000)


def handle_all_popups(page):
    for _ in range(15):
        try:
            handled = False
            btn = page.locator("#BNOTACC")
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(force=True)
                page.wait_for_timeout(800)
                handled = True
                continue
            for txt in ["OK", "Confirm", "I AGREE", "Agree", "Understood"]:
                el = page.locator(f"input[value='{txt}']")
                if el.count() > 0 and el.first.is_visible():
                    el.first.click(force=True)
                    page.wait_for_timeout(800)
                    handled = True
                    break
            if not handled:
                break
        except Exception:
            break


def go_to_calendar_smart(page):
    page.wait_for_timeout(1500)
    handle_all_popups(page)
    try:
        page.click("text=Calendar")
        page.wait_for_timeout(1500)
    except Exception:
        print("  Calendar link not found")


def navigate_to_month(page, target_month, target_year):
    print(f"  📅 Navigating to {MONTH_NUM_TO_NAME[target_month]} {target_year}")
    try:
        dropdown = page.locator("select").filter(has_text=re.compile(r"\d{4}"))
        if dropdown.count() == 0:
            dropdown = page.locator("select")
        if dropdown.count() > 0:
            for opt in dropdown.first.locator("option").all_inner_texts():
                if (MONTH_NUM_TO_NAME[target_month].lower() in opt.lower()
                        and str(target_year) in opt):
                    dropdown.first.select_option(label=opt)
                    page.wait_for_timeout(2000)
                    handle_all_popups(page)
                    print(f"  ✅ Dropdown: '{opt}'")
                    return True
    except Exception as e:
        print(f"  Dropdown error: {e}")

    for _ in range(24):
        try:
            m = re.search(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+(\d{4})",
                page.inner_text("body"),
            )
            if not m:
                return False
            cur_m = MONTH_NAMES[m.group(1).lower()]
            cur_y = int(m.group(2))
            if cur_m == target_month and cur_y == target_year:
                return True
            if (cur_y * 12 + cur_m) < (target_year * 12 + target_month):
                nb = page.locator("a:has-text('>>'), a[href*='next'], td.month_Next a")
                if nb.count() > 0: nb.first.click()
                else: return False
            else:
                pb = page.locator("a:has-text('<<'), a[href*='prev'], td.month_Prev a")
                if pb.count() > 0: pb.first.click()
                else: return False
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  Navigate error: {e}")
            return False
    return False


# ═══════════════════════════════════════════════════════════════════════════
# STATUS EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_status(full_text):
    try:
        section = full_text.split("Auction Status")[1]
        line    = section.split("\n")[0].strip()
        for kw, val in STATUS_KEYWORDS_ORDERED:
            if kw.lower() in line.lower():
                print(f"    [STATUS] '{val}' (from Auction Status section)")
                return val
    except Exception:
        pass
    for kw, val in STATUS_KEYWORDS_ORDERED:
        if kw in full_text:
            print(f"    [STATUS] '{val}' (full text match)")
            return val
    print(f"    [STATUS] Pending (no match)")
    return "Pending"


def status_from_card_text(text):
    t = text.lower()
    if "struck off"           in t: return "Struck Off"
    if "paid in full"         in t: return "Paid in Full"
    if "paid prior to sale"   in t: return "Redeemed"
    if "pulled for no bids"   in t: return "Pulled for no bids"
    if "pulling for no bids"  in t: return "Pulled for no bids"
    if "payment arrangement"  in t: return "P.Arrangement"
    if "cancelled"            in t: return "Cancelled"
    if "canceled"             in t: return "Cancelled"
    # Administrative holds — no bidder was ever involved, treat like Cancelled.
    if "new heirs"            in t: return "Cancelled"
    if "over 65"              in t: return "Cancelled"
    if "to be rescheduled"    in t: return "Cancelled"
    # "Auction Sold" is just the generic closed-auction timestamp header — it
    # appears on Struck Off cards too. Only "Sold To: 3rd Party Bidder" (or an
    # explicit "sold to" line) means an actual buyer, so those checks above
    # (struck off / cancelled / etc.) must win first; only fall through to
    # "Sold" when none of the no-bidder outcomes matched.
    if "sold to"              in t: return "Sold"
    if "auction sold"         in t: return "Sold"
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# CARD DATA (index page)
# ═══════════════════════════════════════════════════════════════════════════

def extract_card_data(page, href):
    """Find the card container for the link with the given href attribute value."""
    result = {"status": "", "sold_amount": "", "sold_to_text": "", "p_list": None, "site_number": ""}
    try:
        escaped = href.replace("\\", "\\\\").replace("'", "\\'")
        data = page.evaluate(f"""
            () => {{
                var targetHref = '{escaped}';
                var links = document.querySelectorAll('a[href*="zaction=auction"]');
                var link = null;
                for (var li = 0; li < links.length; li++) {{
                    if ((links[li].getAttribute('href') || '') === targetHref) {{
                        link = links[li]; break;
                    }}
                }}
                if (!link) return null;
                var container = link;
                for (var d = 0; d < 30; d++) {{
                    if (!container.parentElement) break;
                    container = container.parentElement;
                    var id  = (container.id  || '').toUpperCase();
                    var cls = (container.className || '').toUpperCase();
                    if (id.includes('AUCTION_ITEM')  || id.includes('AITEM')  ||
                        cls.includes('AUCTION_ITEM') || cls.includes('AITEM') ||
                        id.includes('LISTITEM')      || cls.includes('LISTITEM')) break;
                }}
                var cardText = (container.innerText || container.textContent || '').trim();
                var pListEl  = container.querySelector('[p_list]');
                var pList    = pListEl ? pListEl.getAttribute('p_list') : null;
                // $0.00 is filtered out here — it's the unset default on every
                // card's "My Proxy Bid" line, never a real sold amount, and
                // picking it up as the last $-match was making every listing
                // look like it sold for $0.00.
                var amounts  = (cardText.match(/\\$[\\d,]+\\.\\d{{2}}/g) || []).filter(function(a){{ return a !== '$0.00'; }});
                var amount   = amounts.length ? amounts[amounts.length - 1] : '';
                var amtLabel = cardText.match(/Amount[\\s\\n\\r]+\\$([\\d,]+\\.\\d{{2}})/i);
                if (amtLabel && amtLabel[1] !== '0.00') amount = '$' + amtLabel[1];
                var soldToMatch = cardText.match(/Sold\\s+To[:\\s]+([^\\n\\r]+)/i);
                var soldTo      = soldToMatch ? soldToMatch[1].trim() : '';
                // Site's own literal auction-day sequence number — printed on
                // every card (active AND cancelled) as "Precinct/Sale Number: /N".
                var pcMatch  = cardText.match(/Precinct\\/Sale Number:\\s*\\/?\\s*(\\d+)/i);
                var siteNum  = pcMatch ? pcMatch[1] : '';
                return {{ raw: cardText.substring(0, 1500), amount, sold_to: soldTo, p_list: pList, site_number: siteNum }};
            }}
        """)
        if not data:
            return result
        raw = data.get("raw", "")
        result["sold_amount"]  = data.get("amount", "")
        result["sold_to_text"] = data.get("sold_to", "")
        result["p_list"]       = data.get("p_list")
        result["site_number"]  = data.get("site_number", "")
        result["status"]       = status_from_card_text(raw)
        if result["status"] == "Struck Off":
            result["sold_amount"] = ""
        print(f"    [CARD] status='{result['status']}' | "
              f"amount='{result['sold_amount']}' | p_list='{result['p_list']}' | "
              f"site_number='{result['site_number']}'")
    except Exception as e:
        print(f"    [CARD] Error for href {href[:60]}: {e}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# BID HISTORY POPUP
# ═══════════════════════════════════════════════════════════════════════════

def _popup_is_open(page):
    return page.evaluate("""
        () => {
            var p = document.querySelector('div#pWin1, div#pWin2, div[id^="pWin"]');
            if (p && (p.offsetWidth > 0 || p.offsetHeight > 0) && p.style.display !== 'none')
                return true;
            var dlgs = document.querySelectorAll('.ui-dialog');
            for (var d of dlgs) {
                if (d.style.display !== 'none' && d.offsetWidth > 0) {
                    var title = ((d.querySelector('.ui-dialog-title') || {}).innerText || '').toLowerCase();
                    var body  = (d.innerText || '').toLowerCase();
                    if (title.includes('bid') || title.includes('history') ||
                        body.includes('winning bid') || body.includes('final bid') ||
                        body.includes('auction closed'))
                        return true;
                }
            }
            var candidates = document.querySelectorAll(
                '[class*="modal"],[class*="popup"],[class*="dialog"],[class*="overlay"]'
            );
            for (var el of candidates) {
                if (el.offsetWidth > 0 && el.offsetHeight > 0 && el.style.display !== 'none') {
                    var t = (el.innerText || '').toLowerCase();
                    if (t.includes('bid history') || t.includes('winning bid') || t.includes('final bid'))
                        return true;
                }
            }
            return false;
        }
    """)


def open_bid_history_popup(page, p_list_val, cause_number):
    def _check_open():
        page.wait_for_timeout(2500)
        return _popup_is_open(page)

    # ── Primary: click by exact AuctionID (p_list attribute) ────────────────
    # This is always unique per parcel — never use cause_number when this works.
    if p_list_val:
        clicked = page.evaluate(f"""
            () => {{
                var els = document.querySelectorAll('[p_list]');
                for (var e of els) {{
                    if (e.getAttribute('p_list') === '{p_list_val}') {{
                        e.click(); return true;
                    }}
                }}
                return false;
            }}
        """)
        if clicked and _check_open():
            return True

        # Try also matching p_list inside the href (some sites embed it there)
        clicked = page.evaluate(f"""
            () => {{
                var links = document.querySelectorAll('a[href*="{p_list_val}"]');
                for (var lk of links) {{
                    var t = (lk.innerText || lk.href || '').toLowerCase();
                    if (t.includes('bid') || t.includes('history') || t.includes('zbid')) {{
                        lk.click(); return true;
                    }}
                }}
                return false;
            }}
        """)
        if clicked and _check_open():
            return True

    # ── Fallback: cause_number text match (only when no p_list available) ────
    # CAUTION: cause_number is NOT unique for multi-parcel cases (e.g. 2024-DCL-06710
    # covers /15 /16 /17 /18…). Only use this when p_list_val was unavailable.
    if cause_number and not p_list_val:
        cn_escaped = cause_number.replace("'", "\\'")
        clicked = page.evaluate(f"""
            () => {{
                var aLinks = document.querySelectorAll('a[href*="zaction=auction"]');
                for (var link of aLinks) {{
                    if (link.innerText.trim() !== '{cn_escaped}') continue;
                    var el = link;
                    for (var d = 0; d < 20; d++) {{
                        el = el.parentElement;
                        if (!el) break;
                        var s = el.querySelector('span[p_list], span.popup_Bid, span.bidHistory');
                        if (s) {{ s.click(); return 'span'; }}
                        var a = el.querySelector('a[href*="bidHistory"]');
                        if (a) {{ a.click(); return 'link'; }}
                    }}
                }}
                return false;
            }}
        """)
        if clicked and _check_open():
            return True

    # ── Single-element shortcut ──────────────────────────────────────────────
    # On a detail page, there is exactly ONE [p_list] trigger. If only one
    # exists on the current page it's safe to click it regardless of its value.
    # On an index page with 10 listings this would be 10 elements → skip.
    single_clicked = page.evaluate("""
        () => {
            var els = document.querySelectorAll('[p_list]');
            if (els.length === 1) { els[0].click(); return true; }
            return false;
        }
    """)
    if single_clicked and _check_open():
        return True

    # ── Last resort: generic "Bid History" link/button ───────────────────────
    for selector in [
        "text=Bid History", "a:has-text('Bid History')",
        "span:has-text('Bid History')", "button:has-text('Bid History')",
        "input[value*='Bid']", "a[href*='ZBID']",
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(force=True)
                if _check_open():
                    return True
        except Exception:
            pass

    return False


def close_popup(page):
    try:
        btn = page.locator("a.ui-dialog-titlebar-close, span.ui-icon-closethick")
        if btn.count() > 0:
            btn.first.click(force=True)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(600)
    except Exception:
        pass


def extract_from_popup(page):
    page.evaluate("""
        () => {
            ['div#pWin1','div#pWin2','div[id^="pWin"]'].forEach(function(sel){
                var el = document.querySelector(sel);
                if (el) el.scrollTop = 99999;
            });
            document.querySelectorAll('.ui-dialog, .ui-dialog-content').forEach(function(el){
                el.scrollTop = 99999;
            });
        }
    """)
    page.wait_for_timeout(1000)

    result = page.evaluate("""
        () => {
            // ── locate popup ────────────────────────────────────────────────
            var popup = null;
            var pw = document.querySelector('div#pWin1, div#pWin2, div[id^="pWin"]');
            if (pw && pw.offsetWidth > 0 && pw.style.display !== 'none') popup = pw;
            if (!popup) {
                var dlgs = document.querySelectorAll('.ui-dialog');
                for (var d of dlgs) {
                    if (d.style.display !== 'none' && d.offsetWidth > 0) {
                        var body = (d.innerText || '').toLowerCase();
                        if (body.includes('bid') || body.includes('auction')) {
                            popup = d.querySelector('.ui-dialog-content') || d; break;
                        }
                    }
                }
            }
            if (!popup) return null;

            var buyer  = '';
            var amount = '';

            // ── PRIMARY: DOM-targeted extraction from the summary table ──────
            // The bid history popup ends with a summary table whose rows hold
            // "The final bid was made by…" (label td) + buyer name (value td)
            // and "In the total amount of:" + dollar amount.
            // We find that table by walking ALL tables bottom-up and stopping at
            // the first one that mentions "total amount" or "final bid".
            var tables = Array.from(popup.querySelectorAll('table'));
            var summaryTable = null;
            for (var ti = tables.length - 1; ti >= 0; ti--) {
                var tt = (tables[ti].innerText || '').toLowerCase();
                if (tt.includes('total amount') || tt.includes('final bid')) {
                    summaryTable = tables[ti]; break;
                }
            }

            if (summaryTable) {
                // Each row has: [label td] [value td with <span>]
                var rows = summaryTable.querySelectorAll('tr');
                for (var ri = 0; ri < rows.length; ri++) {
                    var cells = rows[ri].querySelectorAll('td');
                    if (cells.length < 2) continue;
                    var labelText = (cells[0].innerText || '').toLowerCase().trim();
                    var valSpan   = cells[cells.length - 1].querySelector('span') || cells[cells.length - 1];
                    var valText   = (valSpan.innerText || valSpan.textContent || '').trim();

                    if (!valText) continue;

                    if ((labelText.includes('final bid') || labelText.includes('made by')) && !valText.startsWith('$')) {
                        // Skip "the plaintiff" rows — those are not 3rd-party buyers
                        if (!valText.toLowerCase().includes('plaintiff')) {
                            buyer = valText;
                        }
                    } else if (labelText.includes('total amount') && valText.startsWith('$')) {
                        amount = valText;
                    }
                }
            }

            // ── FALLBACK: regex on full popup text ───────────────────────────
            if (!buyer || !amount) {
                var fullText = (popup.innerText || popup.textContent || '');

                if (!buyer) {
                    var m1 = fullText.match(
                        /final\\s+bid\\s+was\\s+made\\s+by\\s+3rd\\s+party\\s+bidder[^:]*:[\\s\\t\\n\\r]*([^\\n\\r\\t$]{2,80})/i
                    );
                    if (!m1) {
                        // Broader match: any "made by …:" followed by a name
                        m1 = fullText.match(
                            /final\\s+bid\\s+was\\s+made\\s+by[^:\\n]{0,40}:[\\s\\t\\n\\r]*([^\\n\\r\\t$]{2,80})/i
                        );
                    }
                    if (m1) {
                        var cand = m1[1].trim();
                        if (cand && !cand.startsWith('$') && !cand.toLowerCase().includes('plaintiff')) {
                            buyer = cand;
                        }
                    }
                }

                if (!amount) {
                    var m2 = fullText.match(/total\\s+amount\\s+of[:\\s\\t\\n\\r]*(\\$[\\d,]+\\.\\d{2})/i);
                    if (m2) {
                        amount = m2[1];
                    } else {
                        var allAmts = fullText.match(/\\$[\\d,]+\\.\\d{2}/g);
                        if (allAmts) amount = allAmts[allAmts.length - 1];
                    }
                }
            }

            // -- Extract case number from popup header for caller validation --
            // Header: 'Case Number: 2024-DCL-06710 (17)   Case ID: ...'
            // Use string ops only -- no regex literal with non-ASCII bytes.
            var popupCaseNum = '';
            try {
                var rawT = (popup.innerText || popup.textContent || '');
                // Normalise non-breaking spaces (U+00A0) used as field separators
                rawT = rawT.split(String.fromCharCode(160)).join(' ');
                var cnPos = rawT.indexOf('Case Number');
                if (cnPos >= 0) {
                    var colonPos = rawT.indexOf(':', cnPos);
                    if (colonPos >= 0) {
                        var after = rawT.substring(colonPos + 1).trimLeft();
                        var stopAt = after.indexOf('Case ID');
                        if (stopAt > 0) after = after.substring(0, stopAt);
                        popupCaseNum = after.replace(/[ 	]{2,}/g, ' ').trim();
                        if (popupCaseNum.length > 60) popupCaseNum = '';
                    }
                }
            } catch(e) {}

            // Clean up buyer: "N/A" or "n/a" means no disclosed 3rd-party buyer
            var naValues = ['n/a', 'na', 'n.a.', 'none', '-', 'unknown'];
            if (naValues.indexOf(buyer.toLowerCase()) !== -1) buyer = '';

            // Reject buyer text that's actually a mis-parsed table label, not a
            // real bidder name. Happens when a listing has no real bid-history
            // data yet (e.g. a Pending/future auction) and the fallback regex
            // grabs a neighbouring label like "In the total amount of:" instead
            // of an empty value cell. A real name never contains a colon or
            // these boilerplate phrases.
            var bLower = buyer.toLowerCase();
            var LABEL_FRAGMENTS = ['final bid', 'total amount', 'made by',
                                    'in the total', 'winning bid', 'auction closed'];
            if (buyer.indexOf(':') !== -1 || LABEL_FRAGMENTS.some(function(f){ return bLower.indexOf(f) !== -1; })) {
                buyer = '';
            }

            // A real winning bid is never exactly $0.00 — that's the unset
            // default shown on every card's "My Proxy Bid" line, not a sale
            // amount, and picking it up here falsely implies a completed sale.
            if (amount === '$0.00') amount = '';

            return { buyer: buyer.trim(), amount: amount.trim(), popup_case_num: popupCaseNum };
        }
    """)

    if not result:
        return "", "", ""
    buyer         = result.get("buyer",        "").strip()
    amount        = result.get("amount",       "").strip()
    popup_case_num = result.get("popup_case_num", "").strip()
    print(f"    [POPUP] Buyer='{buyer}' | Amount='{amount}' | PopupCase='{popup_case_num}'")
    return buyer, amount, popup_case_num


def _case_num_matches(cause_number, popup_case_num):
    """True if popup case number belongs to this listing's cause number.

    The popup shows the parcel variant, e.g. cause_number='2024-DCL-06710'
    and popup shows '2024-DCL-06710 (17)' — the base must match.
    Also handles '26,289-A' vs '26,289-A (16)' style.
    """
    if not popup_case_num:
        return True  # Can't validate → optimistic
    cn  = cause_number.strip().upper()
    pcn = popup_case_num.strip().upper()
    # Strip the parcel suffix "(NN)" from the popup value
    pcn_base = re.sub(r'\s*\(\d+\)\s*$', '', pcn).strip()
    return cn == pcn or cn == pcn_base or pcn.startswith(cn) or pcn_base.startswith(cn)


def fetch_bid_history(page, index_page_url, p_list_val, cause_number, card_sold_data,
                      detail_url="", index_page_num=1, index_page_input_id="",
                      section_base_url=""):
    buyer_name   = ""
    final_amount = card_sold_data.get("sold_amount", "")

    def _try_popup_on_page(target_url, label):
        nonlocal buyer_name, final_amount
        try:
            if target_url == index_page_url and index_page_num > 1 and index_page_input_id:
                # JS pagination doesn't change the URL — navigate to the correct page
                # explicitly so we find this listing's [p_list] trigger, not page 1's.
                _navigate_to_page(page, section_base_url or index_page_url,
                                  index_page_num, index_page_input_id)
                page.wait_for_timeout(500)
                handle_all_popups(page)
            else:
                page.goto(target_url)
                page.wait_for_timeout(2500)
                handle_all_popups(page)
            if not open_bid_history_popup(page, p_list_val, cause_number):
                return False
            b, a, pcn = extract_from_popup(page)

            # Validate the popup belongs to this listing, not a neighbour
            if not _case_num_matches(cause_number, pcn):
                print(f"    ⚠️ [POPUP MISMATCH] cause={cause_number} but popup shows={pcn} — discarding")
                close_popup(page)
                return False

            if not b and a:
                page.wait_for_timeout(1500)
                b, a, pcn = extract_from_popup(page)
            if not b:
                close_popup(page)
                page.wait_for_timeout(1000)
                if open_bid_history_popup(page, p_list_val, cause_number):
                    page.wait_for_timeout(2000)
                    b, a, pcn = extract_from_popup(page)
            close_popup(page)
            if b: buyer_name   = b
            if a: final_amount = a
            return bool(b or a)
        except Exception as e:
            print(f"    ❌ [{label}] Error: {e}")
            return False

    _try_popup_on_page(index_page_url, "INDEX")
    if not buyer_name and detail_url and detail_url != index_page_url:
        _try_popup_on_page(detail_url, "DETAIL")

    print(f"    📦 [BID RESULT] Buyer='{buyer_name}' | Amount='{final_amount}'")
    return buyer_name, final_amount


# ═══════════════════════════════════════════════════════════════════════════
# PROPERTY LINKS
# ═══════════════════════════════════════════════════════════════════════════

def scrape_property_links(page):
    zillow = satellite = appraisal_district = property_map = ""
    try:
        zillow = page.evaluate("""
            () => {
                for (var a of document.querySelectorAll('a')) {
                    var txt = (a.innerText||'').trim().toLowerCase();
                    var href = a.href || '';
                    if (txt.includes('zillow') || href.includes('zillow.com')) return href;
                }
                return '';
            }
        """)
    except Exception: pass
    try:
        satellite = page.evaluate("""
            () => {
                for (var a of document.querySelectorAll('a')) {
                    var txt = (a.innerText||'').trim().toLowerCase();
                    var href = a.href || '';
                    if (txt.includes('satellite')) return href;
                    if (href.includes('maps.google') && (href.includes('satellite') || href.includes('t=k'))) return href;
                }
                for (var a of document.querySelectorAll('a')) {
                    if ((a.href||'').includes('google.com/maps')) return a.href;
                }
                return '';
            }
        """)
    except Exception: pass
    try:
        appraisal_district = page.evaluate("""
            () => {
                for (var a of document.querySelectorAll('a')) {
                    var txt = (a.innerText||'').trim().toLowerCase();
                    if (txt === 'appraisal district' || txt.includes('appraisal district')) return a.href;
                }
                return '';
            }
        """)
    except Exception: pass
    try:
        property_map = page.evaluate("""
            () => {
                for (var a of document.querySelectorAll('a')) {
                    var txt = (a.innerText||'').trim().toLowerCase();
                    if (txt === 'property map' || txt === 'property map link') return a.href;
                }
                return '';
            }
        """)
    except Exception: pass
    return zillow, satellite, appraisal_district, property_map


# ═══════════════════════════════════════════════════════════════════════════
# DETAIL PAGE
# ═══════════════════════════════════════════════════════════════════════════

def scrape_property_detail(page, county_name, cause_number):
    try:
        full_text = page.evaluate(r"""
            () => {
                var clone = document.body.cloneNode(true);
                clone.querySelectorAll('br').forEach(br => br.replaceWith(' '));
                return clone.innerText || clone.textContent || '';
            }
        """)
        if not full_text or len(full_text) < 50:
            raise ValueError("empty body")
    except Exception:
        full_text = page.inner_text("body")

    def _extract(label):
        try:    return full_text.split(label)[1].split("\n")[0].strip().lstrip(":").strip()
        except: return ""

    def _extract_address():
        try:
            addr = page.evaluate(r"""
                () => {
                    for (var th of document.querySelectorAll('th.AD_LBL, td.AD_LBL')) {
                        if ((th.innerText||'').trim().replace(/:$/,'').trim() !== 'Property Address') continue;
                        var parts = [];
                        var row = th.closest('tr');
                        if (!row) continue;
                        var td = row.querySelector('td.AD_DTA');
                        if (td) parts.push((td.innerText||'').replace(/\s+/g,' ').trim());
                        var nr = row.nextElementSibling;
                        while (nr) {
                            var nl = nr.querySelector('th.AD_LBL,td.AD_LBL');
                            var lb = nl ? (nl.innerText||'').trim() : '';
                            if (lb && lb !== ':') break;
                            var nd = nr.querySelector('td.AD_DTA');
                            if (nd) parts.push((nd.innerText||'').replace(/\s+/g,' ').trim());
                            nr = nr.nextElementSibling;
                        }
                        if (parts.length) return parts.join(', ');
                    }
                    return null;
                }
            """)
            if addr and len(addr) > 3:
                return re.sub(r'\s+', ' ', re.sub(r',\s*,', ',', addr)).strip()
        except Exception:
            pass
        try:
            val   = full_text.split("Property Address")[1].lstrip(":\n\r\t ").strip()
            lines = [l.strip() for l in val.split("\n") if l.strip()]
            if lines:
                parts = [lines[0]]
                if len(lines) >= 2 and (re.search(r'TX\s+\d{5}', lines[1]) or re.search(r',\s*TX', lines[1])):
                    parts.append(lines[1])
                return ", ".join(parts)
        except Exception:
            pass
        return _extract("Property Address")

    account_number = _extract("Account Number") or cause_number
    unique_key     = make_unique_key(county_name, account_number, source="SHERIFF")

    # Owner from Case Style
    owner = ""
    try:
        case_style = page.evaluate(r"""
            () => {
                var labels = document.querySelectorAll('th.AD_LBL, td.AD_LBL, th, td');
                for (var lbl of labels) {
                    var txt = (lbl.innerText || lbl.textContent || '').trim().replace(/:$/, '').trim();
                    if (txt.toLowerCase() === 'case style') {
                        var row = lbl.closest('tr');
                        if (row) {
                            var dta = row.querySelector('td.AD_DTA, td:not(:first-child)');
                            if (dta) { var val = (dta.innerText || '').trim(); if (val && val.length > 3) return val; }
                        }
                        var sib = lbl.nextElementSibling;
                        if (sib) { var val = (sib.innerText || '').trim(); if (val && val.length > 3) return val; }
                    }
                }
                return null;
            }
        """)
        if not case_style:
            try:
                cs_raw  = full_text.split("Case Style")[1].lstrip(":\n\r\t ").strip()
                cs_lines = []
                for ln in cs_raw.split("\n"):
                    ln = ln.strip()
                    if not ln: continue
                    if re.search(r'^(Account|Adjudged|Est\.|Sale |Court|Precinct|Judgment|Property|Legal|School|Class)', ln): break
                    cs_lines.append(ln)
                    if len(cs_lines) == 3: break
                case_style = " ".join(cs_lines).strip()
            except Exception:
                pass

        if case_style:
            m = re.search(r'\bVS\.?\s+(.+)', case_style, re.IGNORECASE)
            if m:
                owner = m.group(1).strip()
            elif re.search(r'\bVS\b', case_style, re.IGNORECASE):
                parts = re.split(r'\bVS\.?\b', case_style, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    owner = parts[-1].strip()
            if owner:
                owner = re.sub(r'\s+', ' ', owner).strip()
    except Exception as e:
        print(f"    [OWNER] Error: {e}")

    # Auction Date — same AD_LBL/AD_DTA table layout as Case Style/Property
    # Address above. Try the structured DOM lookup first (reliable regardless
    # of how many blank lines separate label from value in the plain text),
    # falling back to the old line-based text search for pages that don't
    # use this table structure.
    auction_date = ""
    for label in ("Auction Starts", "Auction Date"):
        if auction_date: break
        try:
            auction_date = (page.evaluate(r"""
                (label) => {
                    var labels = document.querySelectorAll('th.AD_LBL, td.AD_LBL, th, td');
                    for (var lbl of labels) {
                        var txt = (lbl.innerText || lbl.textContent || '').trim().replace(/:$/, '').trim();
                        if (txt.toLowerCase() !== label.toLowerCase()) continue;
                        var row = lbl.closest('tr');
                        if (row) {
                            var dta = row.querySelector('td.AD_DTA, td:not(:first-child)');
                            if (dta) { var val = (dta.innerText || '').trim(); if (val) return val; }
                        }
                        var sib = lbl.nextElementSibling;
                        if (sib) { var val = (sib.innerText || '').trim(); if (val) return val; }
                    }
                    return null;
                }
            """, label) or "").strip()
        except Exception:
            pass
    for label in ("Auction Starts", "Auction Date"):
        if auction_date: break
        try:
            lines = full_text.split("\n")
            for i, line in enumerate(lines):
                if label in line:
                    same = line.split(label)[-1].strip().lstrip(":").strip()
                    if same:
                        auction_date = same
                        break
                    for j in range(1, 4):
                        if i + j < len(lines) and lines[i+j].strip():
                            auction_date = lines[i+j].strip()
                            break
                    break
        except Exception:
            pass

    zillow, satellite, appraisal_district, property_map = scrape_property_links(page)

    return {
        "Unique Key":         unique_key,
        "Source":             "SHERIFF",
        "County":             county_name,
        "Cause Number":       cause_number,
        "Item Number":        "",
        "Link":               page.url,
        "Auction Date":       auction_date,
        "Status":             extract_status(full_text),
        "Min Bid":            _extract("Est. Min. Bid"),
        "Adjusted Value":     _extract("Adjudged Value"),
        "Property Address":   _extract_address(),
        "Account Number":     account_number,
        "Legal Description":  _extract("Legal Description"),
        "Owner Name":         owner,
        "Buyer Name":         "",
        "Sold Amount":        "",
        "Winning Bid":        "",
        "Sale Date":          _extract("Auction Sold"),
        "Last Updated":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Zillow":             zillow,
        "Satellite View":     satellite,
        "Appraisal District": appraisal_district,
        "Property Map":       property_map,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PAGINATION
# ═══════════════════════════════════════════════════════════════════════════

def _get_max_pages(page, preferred_id):
    try:
        el = page.locator(f"#{preferred_id}")
        if el.count() > 0:
            val = el.first.inner_text().strip()
            if val.isdigit(): return int(val)
    except Exception: pass
    try:
        body = page.inner_text("body")
        m    = re.search(r'page\s+\d+\s+of\s+(\d+)', body, re.IGNORECASE)
        if m: return int(m.group(1))
    except Exception: pass
    return 1


def _first_listing_signature(page):
    """href+text of the first listing link — used to detect whether the grid
    has actually re-rendered for a new page yet (AJAX pagination keeps the
    old rows' selector matching until the new data finishes swapping in)."""
    try:
        links = page.locator("a[href*='zaction=auction']")
        if links.count() == 0:
            return ""
        return (links.first.get_attribute("href") or "") + "|" + links.first.inner_text().strip()
    except Exception:
        return ""


def _wait_for_grid_change(page, before_sig, steps=8):
    for _ in range(steps):
        page.wait_for_timeout(400)
        sig = _first_listing_signature(page)
        if sig and sig != before_sig:
            return True
    return False


def _click_next_page(page):
    """Click whatever the site's 'next page' control is. Returns True if a
    clickable control was found (not whether the grid actually changed —
    caller verifies that separately)."""
    for sel in [
        "a:has-text('Next')", "a:has-text('Next>')", "a:has-text('Next »')",
        "a:has-text('>')", "a[title*='Next' i]", "img[alt*='Next' i]",
        "a.next", ".pager a:has-text('>')",
    ]:
        try:
            el = page.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(force=True)
                return True
        except Exception:
            continue
    return False


def _navigate_to_page(page, section_base_url, pg, page_input_id):
    """Jump to page `pg` of a paginated listing section.

    Tries the numeric page-input field first, then falls back to clicking a
    Next-page control repeatedly from page 1. The input-field method turned
    out to silently do nothing on some sections (grid stayed on page 1 for
    every "page" requested) — this always verifies the grid content actually
    changed before trusting either method, and returns False if neither
    worked so the caller can skip a page rather than re-scrape page 1's data
    under a different page number.
    """
    page.goto(section_base_url)
    page.wait_for_timeout(1500)
    handle_all_popups(page)
    if pg == 1:
        return True

    before_sig = _first_listing_signature(page)

    # ── Method 1: numeric page-input field + Enter ──────────────────────────
    try:
        inp = page.locator(f"#{page_input_id}")
        if inp.count() == 0:
            for alt in ["#curPage", "#pageNum", ".pageInput"]:
                inp = page.locator(alt)
                if inp.count() > 0: break
        if inp.count() > 0:
            inp.first.fill(str(pg))
            inp.first.press("Enter")
            if _wait_for_grid_change(page, before_sig):
                handle_all_popups(page)
                return True
    except Exception as e:
        print(f"    Page input error pg={pg}: {e}")

    # ── Method 2: click Next repeatedly from page 1 ──────────────────────────
    # The page-input's Enter key isn't wired to anything on some sections —
    # it just displays the current page number without accepting jumps.
    print(f"    ↪️ Page-input jump to {pg} had no effect — trying Next-button clicks")
    page.goto(section_base_url)
    page.wait_for_timeout(1500)
    handle_all_popups(page)
    for step in range(2, pg + 1):
        step_before = _first_listing_signature(page)
        if not _click_next_page(page):
            print(f"    ⚠️ No 'Next' control found — cannot reach page {pg}")
            return False
        if not _wait_for_grid_change(page, step_before):
            print(f"    ⚠️ Next-click to page {step} did not change the grid")
            return False
    handle_all_popups(page)
    return True


def collect_all_listing_urls(page, section_base_url, page_input_id, max_pages_id):
    all_entries = []
    seen_p_lists = set()  # deduplicate: cancelled items appear as sticky footer on every page

    page.goto(section_base_url)
    page.wait_for_timeout(2000)
    handle_all_popups(page)
    try:
        page.wait_for_selector("a[href*='zaction=auction']", timeout=5000)
    except Exception:
        print(f"  ⚠️ No listings found in section")
        return all_entries

    max_pages = _get_max_pages(page, max_pages_id)
    print(f"  📄 Section pages: {max_pages}  (id=#{max_pages_id})")

    for pg in range(1, max_pages + 1):
        print(f"  🔗 Collecting page {pg}/{max_pages}...")
        if pg > 1:
            if not _navigate_to_page(page, section_base_url, pg, page_input_id):
                print(f"    ⏭️  Skipping page {pg} — could not verify navigation away from page 1 "
                      f"(would have re-collected page 1's rows as duplicates)")
                continue
            try:
                page.wait_for_selector("a[href*='zaction=auction']", timeout=5000)
            except Exception:
                continue

        index_url = page.url
        links     = page.locator("a[href*='zaction=auction']")
        count     = links.count()
        print(f"  Found {count} listings on page {pg}")

        for i in range(count):
            try:
                cause_number = links.nth(i).inner_text().strip()
                href         = links.nth(i).get_attribute("href") or ""
                card         = extract_card_data(page, href)

                # Prefer AuctionID from href — definitive unique ID per parcel.
                m_aid      = re.search(r'[Aa]uction[Ii][Dd]=(\d+)', href)
                p_list_val = m_aid.group(1) if m_aid else card["p_list"]

                # Skip duplicates — cancelled items appear as a sticky footer on
                # every paginated page, so the same p_list would otherwise be
                # collected once per page.
                if p_list_val and p_list_val in seen_p_lists:
                    continue
                if p_list_val:
                    seen_p_lists.add(p_list_val)

                if href.startswith("http"):
                    full_url = href
                elif href:
                    base     = section_base_url.split("?")[0].rsplit("/", 1)[0]
                    full_url = base + "/" + href.lstrip("/")
                else:
                    continue

                all_entries.append((cause_number, full_url, p_list_val, index_url, card["status"], card, pg))
            except Exception as e:
                print(f"  ⚠️ Error collecting index {i}: {e}")

    print(f"  ✅ Total listings collected: {len(all_entries)}")
    return all_entries


# ═══════════════════════════════════════════════════════════════════════════
# PROCESS SINGLE LISTING
# ═══════════════════════════════════════════════════════════════════════════

def process_listing_url(
    page, county_name, cause_number, detail_url, p_list_val, index_page_url,
    db, csv_rows, section_name, index_status="", card_data=None,
    index_page_num=1, index_page_input_id="", section_base_url="", site_seq=None,
):
    if card_data is None:
        card_data = {"status": "", "sold_amount": "", "sold_to_text": "", "p_list": None, "site_number": ""}
    try:
        page.goto(detail_url)
        page.wait_for_timeout(2000)
        handle_all_popups(page)
        data = scrape_property_detail(page, county_name, cause_number)
        # Item Number = this listing's position within the Closed tab's own
        # walk order (1-indexed, counted across pages in the order
        # collect_all_listing_urls() found them — includes cancelled cards,
        # they occupy a real slot too). NOT the card's printed "Precinct/Sale
        # Number" — that field is a global Waiting+Closed counter that keeps
        # shifting for items still on the site as unrelated Waiting-tab
        # listings resolve into Closed, so it drifts run to run even for
        # already-scraped rows. Position within the Closed tab alone is not
        # affected by that churn. This is only a raw ordering hint, though —
        # common.renumber_item_numbers() (run at the end of every scrape via
        # rewrite_csv()/reorder_google_sheet()) recomputes the real displayed
        # Item Number from scratch: gapless 1..N over active rows, with
        # cancelled-equivalent rows blanked and sorted last.
        data["Item Number"] = str(site_seq) if site_seq else ""

        final_status = data["Status"]
        if index_status in (SOLD_STATUSES | NONSOLD_STATUSES):
            final_status   = index_status
            data["Status"] = index_status

        # Resolve "Pending" for items in the Closed section — they have been
        # auctioned so "Pending" is never correct. Check bid history popup to
        # determine whether the property sold or was struck off.
        #
        # Guard: some counties' "Closed" listing (&ztype=C) returns the exact
        # same rows as "Waiting" instead of only truly-closed auctions — e.g.
        # Dallas returned all 11 Waiting-section listings under Closed too,
        # for an auction date weeks in the future. Resolving those via the
        # bid-history popup was mislabeling still-pending listings as
        # "Struck Off"/"Sold" (only saved by the Waiting-section pass running
        # afterward and overwriting it back). If the auction date is still in
        # the future, there is nothing to resolve — trust "Pending" as-is.
        auction_is_future = False
        try:
            m_date = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', data.get("Auction Date", ""))
            if m_date:
                mo, dy, yr = (int(x) for x in m_date.groups())
                auction_is_future = datetime(yr, mo, dy) > datetime.now()
        except Exception:
            pass

        if final_status == "Pending" and section_name == "Closed" and auction_is_future:
            print(f"    [PENDING RESOLVE] Skipped — auction date {data.get('Auction Date','')} "
                  f"hasn't happened yet for {cause_number}")
        elif final_status == "Pending" and section_name == "Closed":
            print(f"    [PENDING RESOLVE] Closed-section item still Pending — checking bid history for {cause_number}")
            try:
                _navigate_to_page(page, section_base_url or index_page_url,
                                  index_page_num, index_page_input_id)
                page.wait_for_timeout(500)
                handle_all_popups(page)
                if open_bid_history_popup(page, p_list_val, cause_number):
                    b, a, pcn = extract_from_popup(page)
                    # Discard if popup belongs to a different listing
                    if not _case_num_matches(cause_number, pcn):
                        print(f"    ⚠️ [PENDING RESOLVE MISMATCH] cause={cause_number} popup={pcn} — treating as Struck Off")
                        b = a = ""
                    close_popup(page)
                    if b:
                        final_status        = "Sold"
                        data["Status"]      = "Sold"
                        data["Buyer Name"]  = b
                        data["Sold Amount"] = a
                        data["Winning Bid"] = a
                        print(f"    [PENDING RESOLVE] → Sold | Buyer='{b}' | Amount='{a}'")
                    else:
                        # Auction closed, no 3rd-party buyer → Struck Off
                        final_status   = "Struck Off"
                        data["Status"] = "Struck Off"
                        print(f"    [PENDING RESOLVE] → Struck Off (no buyer found)")
                else:
                    # Cannot open popup → safest fallback for a closed-section item
                    final_status   = "Struck Off"
                    data["Status"] = "Struck Off"
                    print(f"    [PENDING RESOLVE] → Struck Off (popup unavailable)")
            except Exception as e:
                print(f"    [PENDING RESOLVE] Error: {e} — defaulting to Struck Off")
                final_status   = "Struck Off"
                data["Status"] = "Struck Off"

        if final_status in SOLD_STATUSES:
            buyer, amount = fetch_bid_history(
                page, index_page_url, p_list_val, cause_number, card_data,
                detail_url=detail_url,
                index_page_num=index_page_num,
                index_page_input_id=index_page_input_id,
                section_base_url=section_base_url,
            )
            if not amount:
                page.goto(detail_url)
                page.wait_for_timeout(1500)
                handle_all_popups(page)
                body    = page.inner_text("body")
                amounts = re.findall(r'\$[\d,]+\.\d{2}', body)
                if amounts: amount = amounts[-1]

            data["Buyer Name"]  = buyer
            data["Sold Amount"] = amount
            data["Winning Bid"] = amount

            if not buyer and not amount:
                try:
                    if "struck off" in page.inner_text("body").lower():
                        data["Status"] = "Struck Off"
                        final_status   = "Struck Off"
                except Exception:
                    pass
        else:
            data["Buyer Name"]  = ""
            data["Sold Amount"] = ""
            data["Winning Bid"] = ""

        # NOTE: Item Number (set above from site_seq) is saved as-is here even
        # for Cancelled-equivalent rows — this raw value is only ever a hint
        # for common.renumber_item_numbers()'s active-row sort order. That
        # function (run at the end of every scrape) is what actually blanks
        # Cancelled-equivalent rows and pushes them to the bottom, and
        # gaplessly renumbers the active rows below them — same as every
        # other source, no SHERIFF-specific carve-out anymore.

        return smart_save(data, db, csv_rows, section_name)

    except Exception as e:
        print(f"  ❌ Error [{cause_number}] @ {detail_url}: {e}")
        return "error"


# ═══════════════════════════════════════════════════════════════════════════
# FAST UPDATE MODE — status-only refresh, no detail-page visits
# ═══════════════════════════════════════════════════════════════════════════

def build_cause_index(db, county_name, source="SHERIFF"):
    """Map cause_number -> uk for listings already known in DB for this county.

    Card-level index-page data only gives us cause_number (no Account Number,
    which lives on the detail page) — so in Update mode this is how we check
    "have we already saved this listing?" without opening a detail page.

    One cause number can cover multiple parcels (multi-property lawsuits —
    e.g. Ellis cause 22329TX has two separate accounts/uks). A plain
    cause_number -> uk map can't tell those apart, so it would silently
    collapse both cards onto whichever uk happened to be written last —
    misattributing status/amount updates and Item Number refreshes between
    the two rows. Ambiguous cause numbers are left out of the index
    entirely so the caller's `.get()` returns None for every card sharing
    them, forcing the slower-but-correct full detail-page scrape (which
    resolves its own uk from the account number) instead of a fast-path
    guess.
    """
    idx = {}
    ambiguous = set()
    cu = county_name.upper()
    for uk, rec in db.items():
        if uk == "__item_counters__":
            continue
        if rec.get("source", "").upper() != source:
            continue
        if rec.get("county", "").upper() != cu:
            continue
        cn = (rec.get("cause_number") or "").strip()
        if not cn:
            continue
        if cn in idx and idx[cn] != uk:
            ambiguous.add(cn)
            continue
        idx[cn] = uk
    for cn in ambiguous:
        idx.pop(cn, None)
    return idx


def _refresh_item_number_only(csv_rows, uk, position):
    """A status-unchanged ('skipped') listing can still have moved to a new
    page position since the last run (e.g. an earlier cause number on the
    site got cancelled and everything below it shifted up, or a Waiting-tab
    item resolved into Closed ahead of it). The position is known for free
    while walking collect_all_listing_urls()'s entries — no detail-page
    visit needed — so keep it in sync here too, not just on real status
    changes. Cancelled rows get refreshed too — they occupy a real numbered
    slot on the site, not just active ones."""
    row = csv_rows.get(uk)
    if row is None:
        return
    new_num = str(position)
    if row.get("Item Number", "") == new_num:
        return
    row["Item Number"] = new_num
    update_google_sheet(row)


def apply_lightweight_status_update(page, uk, cause_number, card_data, db, csv_rows,
                                     index_url, p_list_val, pg, page_input_id, section_base_url,
                                     site_seq=None):
    """Update Status (+ Buyer/Amount if newly Sold) for a listing we already
    have full data for — never opens the detail page. Cancelled/Struck Off/etc.
    are a pure status flip (nobody bids on those); Sold pulls buyer+amount from
    the card text first, falling back to the bid-history popup opened directly
    on the index page.
    """
    row = csv_rows.get(uk)
    if row is None:
        return None  # caller falls back to a full scrape to rebuild this row

    new_status = card_data.get("status") or ""
    buyer      = card_data.get("sold_to_text", "").strip()
    amount     = card_data.get("sold_amount", "").strip()

    # "Sold To: 3rd Party Bidder" is a generic placeholder, not the actual
    # buyer's name — the real name only lives in the bid-history popup.
    if buyer.lower() in ("3rd party bidder", "third party bidder"):
        buyer = ""

    if not new_status or new_status == "Sold":
        if not buyer or not amount:
            b, a = fetch_bid_history(
                page, index_url, p_list_val, cause_number, card_data,
                detail_url="", index_page_num=pg,
                index_page_input_id=page_input_id,
                section_base_url=section_base_url,
            )
            buyer  = buyer  or b
            amount = amount or a
        # A buyer name is what actually proves a sale (it only ever comes from
        # a real "Sold To:" card line or a winning-bid popup). `amount` alone
        # is not enough — extract_card_data()'s regex grabs the LAST dollar
        # figure on the card unconditionally, so a Cancelled listing whose
        # "Auction Status" label the DOM-container walk missed (status came
        # back blank here) still has its "Est. Min. Bid" picked up as
        # `amount`, which used to be read as "this sold" and got written out
        # as a fake Sold Amount equal to the minimum bid, with no buyer.
        new_status = "Sold" if buyer else (new_status or "Struck Off")

    row["Status"] = new_status
    if new_status in SOLD_STATUSES:
        row["Buyer Name"]  = buyer  or row.get("Buyer Name", "")
        row["Sold Amount"] = amount or row.get("Sold Amount", "")
        row["Winning Bid"] = amount or row.get("Winning Bid", "")
    row["Item Number"] = str(site_seq) if site_seq else row.get("Item Number", "")
    row["Last Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    csv_rows[uk] = row
    update_google_sheet(row)
    db[uk]["status"] = new_status
    save_db(db)
    print(f"  ⚡ FAST UPDATE: {uk} → {new_status}")
    return "updated"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION / CALENDAR
# ═══════════════════════════════════════════════════════════════════════════

def scrape_section(page, county_name, db, csv_rows, section_base_url,
                   section_name, page_input_id, max_pages_id, mode="all"):
    emoji = "🔵" if section_name == "Waiting" else "🔴"
    print(f"\n  {emoji} {section_name.upper()} SECTION")
    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    page.goto(section_base_url)
    page.wait_for_timeout(2000)
    handle_all_popups(page)

    try:
        page.wait_for_selector("a[href*='zaction=auction']", timeout=5000)
    except Exception:
        print(f"  ⚠️ No listings in {section_name}")
        return stats

    entries = collect_all_listing_urls(page, section_base_url, page_input_id, max_pages_id)
    if not entries:
        return stats

    total = len(entries)

    if mode == "update":
        cause_index = build_cause_index(db, county_name)
        for i, (cause_number, detail_url, p_list_val, index_url, index_status, card, pg) in enumerate(entries):
            uk = cause_index.get(cause_number.strip())

            if uk is None:
                print(f"\n  [{i+1}/{total}] {section_name}: {cause_number} (NEW)")
                result = process_listing_url(
                    page, county_name, cause_number, detail_url, p_list_val,
                    index_url, db, csv_rows, section_name,
                    index_status=index_status, card_data=card,
                    index_page_num=pg, index_page_input_id=page_input_id,
                    section_base_url=section_base_url, site_seq=i + 1,
                )
                stats[result] = stats.get(result, 0) + 1
                continue

            old_status = db[uk].get("status", "")

            if section_name == "Waiting":
                # Still pending (no status keyword on the card) → nothing changed.
                if not card["status"] or card["status"] == old_status:
                    _refresh_item_number_only(csv_rows, uk, i + 1)
                    stats["skipped"] = stats.get("skipped", 0) + 1
                    continue
            elif card["status"] and card["status"] == old_status:
                _refresh_item_number_only(csv_rows, uk, i + 1)
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue

            print(f"\n  [{i+1}/{total}] {section_name}: {cause_number} "
                  f"({old_status or '?'} → checking...)")
            result = apply_lightweight_status_update(
                page, uk, cause_number, card, db, csv_rows,
                index_url, p_list_val, pg, page_input_id, section_base_url,
                site_seq=i + 1,
            )
            if result is None:
                # DB knows this uk but the CSV row is missing — rebuild it safely.
                result = process_listing_url(
                    page, county_name, cause_number, detail_url, p_list_val,
                    index_url, db, csv_rows, section_name,
                    index_status=index_status, card_data=card,
                    index_page_num=pg, index_page_input_id=page_input_id,
                    section_base_url=section_base_url, site_seq=i + 1,
                )
            stats[result] = stats.get(result, 0) + 1

        return stats

    for i, (cause_number, detail_url, p_list_val, index_url, index_status, card, pg) in enumerate(entries):
        print(f"\n  [{i+1}/{total}] {section_name}: {cause_number}")
        result = process_listing_url(
            page, county_name, cause_number, detail_url, p_list_val,
            index_url, db, csv_rows, section_name,
            index_status=index_status, card_data=card,
            index_page_num=pg, index_page_input_id=page_input_id,
            section_base_url=section_base_url, site_seq=i + 1,
        )
        stats[result] = stats.get(result, 0) + 1

    return stats


def process_auction_day(page, county_name, db, csv_rows, auction_day_url, mode="all"):
    handle_all_popups(page)
    totals = {"new": 0, "updated": 0, "skipped": 0, "error": 0}
    for section_name, url_suffix, inp_id, max_id in [
        ("Closed",  "&ztype=C", "curPCA", "maxCA"),
        ("Waiting", "",         "curPWA", "maxWA"),
    ]:
        stats = scrape_section(
            page, county_name, db, csv_rows,
            auction_day_url + url_suffix, section_name, inp_id, max_id, mode=mode,
        )
        for k in stats:
            totals[k] = totals.get(k, 0) + stats[k]
    return totals


def process_calendar(page, county_name, db, csv_rows, target_month, target_year, mode="all"):
    handle_all_popups(page)
    if not navigate_to_month(page, target_month, target_year):
        print(f"  ⚠️ {county_name}: Month navigation failed — trying anyway")

    # NOTE: "text=Tax Sale" also matches the calendar's legend footer
    # ("TS = Tax Sale" inside div.CALKEY), which is not a real auction day.
    # "b:has-text('Tax Sale')" matches only the actual day links, which are
    # rendered as <b>Tax Sale</b>.
    try:
        page.wait_for_selector("b:has-text('Tax Sale')", timeout=5000)
    except Exception:
        print("  No Tax Sale in this month/county")
        return

    calendar_url  = page.url
    days          = page.locator("b:has-text('Tax Sale')")
    total_days    = days.count()
    print(f"  📅 Tax Sale days: {total_days}")

    tax_sale_urls = []
    for i in range(total_days):
        try:
            page.locator("b:has-text('Tax Sale')").nth(i).scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            page.locator("b:has-text('Tax Sale')").nth(i).click(force=True)
            page.wait_for_timeout(2000)
            handle_all_popups(page)
            tax_sale_urls.append(page.url)
            page.goto(calendar_url)
            page.wait_for_timeout(2000)
            handle_all_popups(page)
            navigate_to_month(page, target_month, target_year)
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  Day URL collect error {i}: {e}")

    for i, url in enumerate(tax_sale_urls):
        try:
            print(f"\n  📅 Processing Day {i+1}/{len(tax_sale_urls)}: {url}")
            page.goto(url)
            page.wait_for_timeout(2000)
            handle_all_popups(page)
            stats = process_auction_day(page, county_name, db, csv_rows, url, mode=mode)
            print(f"\n📊 {county_name} Day {i+1}: "
                  f"New={stats['new']} Updated={stats['updated']} "
                  f"Skipped={stats['skipped']} Error={stats.get('error',0)}")
        except Exception as e:
            print(f"  Day {i+1} error: {e}")