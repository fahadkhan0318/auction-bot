"""
cad_scraper.py — CAD (Central Appraisal District) Enrichment
"""

import re
from datetime import datetime
from playwright.sync_api import sync_playwright

CURRENT_YEAR = str(datetime.now().year)

SUPPORTED_COUNTIES = {
    "bell",
    "hardin", "galveston", "cherokee", "gregg", "llano",
    "milam", "brown", "browntrust", "shackelford",
    "aransas", "harrison",
    "henderson", "bastrop", "anderson",
    "nueces", "wilson", "matagorda",
    "ellis",
    "travis",      # Prodigy CAD
    "midland",     # ISW / Southwest Data Solutions
    "comal", "taylor",
    "stephens",    # Southwest Data Solutions (new portal)
    "williamson",  # WCAD portal — search.wcad.org
    "dallas",      # Dallas CAD — dallascad.org direct URL
    "hill",        # Hill CAD — esearch.hillcad.org
    "lampasas",    # Lampasas CAD — esearch.lampasascad.com
    "cameron",     # Cameron CAD — cameroncad.org
    "atascosa",    # Atascosa CAD — esearch.atascosacad.com
    "jackson",     # Jackson CAD — esearch.jacksoncad.org
    "brooks",      # Brooks CAD — esearch.brookscad.org (Geo ID)
    "cass",        # Cass CAD — esearch.casscad.org (Geo ID)
    "kleberg",     # Kleberg CAD — esearch.kleberg-cad.org
    "lamar",       # Lamar CAD — esearch.lamarcad.org
    "rains",       # Rains CAD — esearch.rainscad.org
    "upshur",      # Upshur CAD — esearch.upshur-cad.org
    "starr",       # Starr CAD — esearch.starrcad.org
    "tomgreen",    # Tom Green CAD — southwestdatasolution.com (Geo ID portal)
    "limestone",   # Limestone CAD — limestonecad.com (Prodigy engine)
    "valverde",    # Val Verde CAD — valverdecad.org (Angular Material, Geo ID 4-4-4)
    "rusk",        # Rusk CAD    — Home/Search portal (ruskcad.org)
    "goliad",      # Goliad CAD  — Home/Search portal (goliadcad.org)
    "dewitt",      # DeWitt CAD  — Home/Search portal (dewittcad.org)
    "eastland",    # Eastland CAD — Home/Search portal (eastlandcad.org)
    "coryell",     # Coryell CAD — esearch.coryellcad.org
    "bowie",       # Bowie CAD — bowieappraisal.com (AG Grid SPA)
    "wharton",     # Wharton CAD — whartoncad.net (Prodigy engine)
    "guadalupe",   # Guadalupe CAD — esearch.guadalupead.org
    "kaufman",     # Kaufman CAD — esearch.kaufman-cad.org
    "mclennan",    # McLennan CAD — mclennancad.org (True Prodigy engine)
    "bosque",      # Bosque CAD — esearch.bosquecad.com
    "runnels",     # Runnels CAD — Southwest Data Solutions (Azure Front Door), Property ID search
    "smith",       # Smith CAD — smithcad-search.gsacorp.io (direct /parcel/{id} URL)
    "elpaso",      # El Paso CAD — epcad.org/Search (Cloudflare-protected)
    "jasper",      # Jasper CAD — esearch.jaspercad.org
    "leon",        # Leon CAD — leoncad.org (Home/Search portal, same engine as Rusk/Goliad/DeWitt/Eastland)
    "comanche",    # Comanche CAD — esearch.comanchecad.org
    "hays",        # Hays County Tax Office — tax.co.hays.tx.us (Orion Public Access JSON search API)
    "orange",      # Orange CAD — esearch.orangecad.net
    "medina",      # Medina CAD — esearch.medinacad.org
}

BIS_URLS = {
    # bell moved to esearch below
}

# Counties whose CAD account numbers are plain digits (no R prefix).
# Upshur uses 10-digit zero-padded numeric IDs (e.g. 0000012112).
# McLennan's compound search only accepts the numeric Geo ID half of a
# "PropID/GeoID" composite (e.g. "R08335/460520000002003") — not the R-prefixed half.
PLAIN_NUMERIC_COUNTIES = {"dallas", "upshur", "mclennan"}

# Counties whose esearch portal expects the account number WITH its leading
# R prefix intact — the generic esearch handler otherwise strips it.
KEEP_R_PREFIX_COUNTIES = {"bosque"}

# Counties whose esearch portal's "By ID" tab doesn't actually search by
# account number (orangecad.net's By ID tab only takes its own "Quick Ref
# ID" and misses on our stored account format) — the account number has to
# be typed into the default general Search box instead, which is already
# active on page load.
SKIP_BYID_TAB_COUNTIES = {"orange"}

ESEARCH_URLS = {
    "bell":        "https://esearchgsa.bellcad.org",
    "hardin":      "https://esearch.hardin-cad.org",
    "galveston":   "https://esearch.galvestoncad.org",
    "cherokee":    "https://esearch.cherokeecad.com",
    "gregg":       "https://esearch.gcad.org",
    "llano":       "https://esearch.llanocad.net",
    "milam":       "https://esearch.milamad.org",
    "brown":       "https://esearch.brown-cad.org",
    "browntrust":  "https://esearch.brown-cad.org",
    "shackelford": "https://esearch.shackelfordcad.com",
    "aransas":     "https://esearch.aransascad.org",
    "henderson":   "https://esearch.henderson-cad.org",
    "bastrop":     "https://esearch.bastropcad.org",
    "nueces":      "https://esearch.nuecescad.net",
    "wilson":      "https://esearch.wilson-cad.org",
    "matagorda":   "https://esearch.matagorda-cad.org",
    "comal":       "https://esearch.comalad.org",
    "taylor":      "https://esearch.taylor-cad.org",
    "hill":        "https://esearch.hillcad.org",
    "lampasas":    "https://esearch.lampasascad.com",
    "atascosa":    "https://esearch.atascosacad.com",
    "brooks":      "https://esearch.brookscad.org",
    "cass":        "https://esearch.casscad.org",
    "kleberg":     "https://esearch.kleberg-cad.org",
    "lamar":       "https://esearch.lamarcad.org",
    "rains":       "https://esearch.rainscad.org",
    "upshur":      "https://esearch.upshur-cad.org",
    "starr":       "https://esearch.starrcad.org",
    "coryell":     "https://esearch.coryellcad.org",
    "guadalupe":   "https://esearch.guadalupead.org",
    "kaufman":     "https://esearch.kaufman-cad.org",
    "bosque":      "https://esearch.bosquecad.com",
    "jasper":      "https://esearch.jaspercad.org",
    "comanche":    "https://esearch.comanchecad.org",
    "orange":      "https://esearch.orangecad.net",
    "medina":      "https://esearch.medinacad.org",
}

# Counties that use a Geographic ID field instead of plain account number.
GEO_ID_COUNTIES = {"galveston", "hardin", "nueces", "wilson", "brooks", "cass", "rains"}

# Tom Green CAD — Southwest Data Solutions geo-id portal
TOMGREEN_SEARCH_BASE = "https://www.southwestdatasolution.com/webSearchGeoID.aspx"
TOMGREEN_DBKEY       = "TOMGREENCAD"

# Limestone CAD — Prodigy engine
LIMESTONE_BASE_URL   = "https://www.limestonecad.com"
_LIMESTONE_HOME_URLS = {
    "https://www.limestonecad.com",
    "https://limestonecad.com",
    "https://www.limestonecad.com/property-search",
    "https://limestonecad.com/property-search",
}

# Wharton CAD — Prodigy engine
WHARTON_BASE_URL   = "https://www.whartoncad.net"
_WHARTON_HOME_URLS = {
    "https://www.whartoncad.net",
    "https://whartoncad.net",
    "https://www.whartoncad.net/property-search",
    "https://whartoncad.net/property-search",
}

# Ellis CAD base URL — uses /property-detail/{id}/{year} pattern
ELLIS_BASE_URL = "https://www.elliscad.org"

# Travis CAD — Prodigy CAD engine, same /property-detail/{id}/{year} pattern
TRAVIS_BASE_URL = "https://travis.prodigycad.com"

# McLennan CAD — True Prodigy engine (same API shape as Travis)
MCLENNAN_BASE_URL = "https://mclennancad.org"

# Midland CAD — ISW / Southwest Data Solutions portal
MIDLAND_SEARCH_URL = "https://iswdataclient.azurewebsites.net/webindex.aspx?dbkey=MIDLANDCAD"

# Stephens CAD — Southwest Data Solutions (new SPA portal)
STEPHENS_SEARCH_URL = "https://stephenscad.southwestdatasolutions.com/PropertySearch"

# Runnels CAD — Southwest Data Solutions portal, served behind Azure Front Door
RUNNELS_SEARCH_BASE = "https://azurefrontdoor-gwbqhvc2fyhaghgf.z01.azurefd.net/webSearchID.aspx"
RUNNELS_DBKEY        = "RUNNELSCAD"

# Williamson CAD — WCAD portal
# URL pattern: /Property-Detail/PropertyQuickRefID/{account}
WILLIAMSON_DETAIL_BASE = "https://search.wcad.org/Property-Detail/PropertyQuickRefID"

# Dallas CAD — direct URL by account ID
DALLAS_CAD_DETAIL_URL = "https://www.dallascad.org/AcctDetailRes.aspx"

# Smith CAD — GSA Corp portal, direct URL by plain-digit parcel id
# URL pattern: /parcel/{account_number} (e.g. /parcel/100000001201172000,
# which displays on-page as "Parcel 1.00000.0012.01.172000" — same digits,
# dots removed)
SMITH_BASE_URL = "https://smithcad-search.gsacorp.io"

# Cameron CAD — migrated to the ProdigyCAD portal (was Angular Material,
# embedded via <iframe> on cameroncad.org). Hit the portal domain directly.
CAMERON_SEARCH_URL = "https://cameron.prodigycad.com/property-search"

# Val Verde CAD — Angular Material search portal (same engine as Cameron)
VALVERDE_SEARCH_URL = "https://www.valverdecad.org/property-search"

# Home/Search portal — Rusk, Goliad, DeWitt, Eastland, Leon CADs (same engine)
HOMESEARCH_URLS = {
    "rusk":     "https://www.ruskcad.org",
    "goliad":   "https://goliadcad.org",
    "dewitt":   "https://www.dewittcad.org",
    "eastland": "https://eastlandcad.org",
    "leon":     "https://www.leoncad.org",
}



# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def format_geo_id_galveston(account_number):
    acct = account_number.strip()
    if re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}$', acct):
        return acct
    digits = re.sub(r'\D', '', acct)
    digits = digits.zfill(15)
    return f"{digits[0:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:15]}"


def format_geo_id_hardin(account_number):
    acct = account_number.strip()
    if re.match(r'^\d{6}-\d{6}$', acct):
        return acct
    digits = re.sub(r'\D', '', acct)
    digits = digits.zfill(12)
    return f"{digits[0:6]}-{digits[6:12]}"


def format_geo_id_nueces(account_number):
    """Nueces geo id — user pastes the correct geo id directly in the sheet."""
    return account_number.strip()


def format_geo_id_wilson(account_number):
    """Wilson geo id — user pastes the correct geo id directly in the sheet."""
    return account_number.strip()


def format_geo_id_brooks(account_number):
    """Brooks CAD geo id — format: XXXXX-XXXX-XXX-XX (5-4-3-2 = 14 digits)."""
    acct = account_number.strip()
    if re.match(r'^\d{5}-\d{4}-\d{3}-\d{2}$', acct):
        return acct
    digits = re.sub(r'\D', '', acct).zfill(14)
    return f"{digits[0:5]}-{digits[5:9]}-{digits[9:12]}-{digits[12:14]}"


def format_geo_id_cass(account_number):
    """Cass CAD geo id — format: XXXXX-XXXXX-XXXXX-XXXXXX (5-5-5-6 = 21 digits)."""
    acct = account_number.strip()
    if re.match(r'^\d{5}-\d{5}-\d{5}-\d{6}$', acct):
        return acct
    digits = re.sub(r'\D', '', acct).zfill(21)
    return f"{digits[0:5]}-{digits[5:10]}-{digits[10:15]}-{digits[15:21]}"


def format_geo_id_rains(account_number):
    """Rains CAD geo id — user provides geo id as-is from the sheet."""
    return account_number.strip()


def format_geo_id_tomgreen(account_number):
    """Tom Green CAD geo id — format: XX-XXXXX-XXXX-XXX-XX (2-5-4-3-2 = 16 digits)."""
    acct = account_number.strip()
    if re.match(r'^\d{2}-\d{5}-\d{4}-\d{3}-\d{2}$', acct):
        return acct
    digits = re.sub(r'\D', '', acct).zfill(16)
    return f"{digits[0:2]}-{digits[2:7]}-{digits[7:11]}-{digits[11:14]}-{digits[14:16]}"


def extract_market_value(text):
    patterns = [
        r'Total\s+Market\s+Value[:\s]+\$?([\d,]+)',
        r'Total\s+Appraised\s+Value[:\s]+\$?([\d,]+)',
        r'Market\s+Value[:\s]+\$?([\d,]+)',
        r'Appraised\s+Value[:\s]+\$?([\d,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}"
            except Exception:
                pass
    return ""


def build_google_maps_url(address):
    """Build a Google Maps search URL from a property address."""
    if not address:
        return ""
    import urllib.parse
    return f"https://maps.google.com/maps?q={urllib.parse.quote(address)}"


def build_zillow_url(address):
    if not address:
        return ""
    import urllib.parse
    slug = address.strip().replace(" ", "-").replace(",", "")
    slug = re.sub(r'-+', '-', slug)
    encoded = urllib.parse.quote(slug)
    return f"https://www.zillow.com/homes/{encoded}_rb/"


def build_realtor_search_url(address):
    """Realtor.com keyword search URL — used by fetch_realtor_direct_url to find the listing."""
    if not address:
        return ""
    import urllib.parse
    m = re.match(r'^(.+?),\s*([^,]+?),\s*([A-Z]{2})\s*(\d{5})?$', address.strip(), re.IGNORECASE)
    if m:
        street  = urllib.parse.quote_plus(m.group(1).strip())
        city    = m.group(2).strip().title().replace(' ', '-')
        state   = m.group(3).upper()
        return f"https://www.realtor.com/realestateandhomes-search/{city}_{state}/?keywords={street}"
    keyword = urllib.parse.quote_plus(address.strip())
    return f"https://www.realtor.com/realestateandhomes-search/?keywords={keyword}"


def build_realtor_url(address):
    """Google search URL that finds the Realtor.com property page."""
    if not address:
        return ""
    import urllib.parse
    query = f'site:realtor.com {address}'
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"


def fetch_realtor_direct_url(page, address):
    """
    Google search: site:realtor.com + address
    Click the first result heading → follow redirect → return final Realtor.com URL.
    """
    if not address:
        return ""
    import urllib.parse

    query      = f'site:realtor.com {address}'
    google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"

    try:
        page.goto(google_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        # Click the first result title (h3) — Google follows redirect to realtor.com
        first_h3 = page.locator("#search h3, div.g h3, h3").first
        first_h3.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(1500)

        final_url = page.url
        if "realestateandhomes-detail" in final_url:
            print(f"    🏠 Realtor direct: {final_url[:90]}")
            return final_url

        print(f"    ⚠️  Realtor: landed on unexpected URL: {final_url[:60]}")
    except Exception as e:
        print(f"    ⚠️  Realtor fetch error: {e}")
    return ""


# harrisoncad.net renders these exact strings as a template default/skeleton
# for the Address and Mailing Address fields before the per-property AJAX
# data finishes loading (they are the appraisal district's OWN office
# address/PO box, not a real situs address) — they showed up identically
# across dozens of unrelated accounts in the sheet, proving they're not real.
#
# '400 ferris avenue' is the same failure mode on elliscad.org: when the
# per-property LOCATION > Address value hasn't populated (slow load, no
# record for that year, etc.), _extract_direct_url_detail()'s DOM-wide
# label scan falls through to the site's global footer, which always
# renders the Ellis CAD office's own "Address: 400 Ferris Avenue,
# Waxahachie, Texas" contact block — clobbering the real sheriff-scraped
# situs address with the appraisal district's mailing address.
_KNOWN_PLACEHOLDER_ADDRESSES = {
    '201 w. grand', '201 w grand', 'p.o. box 818', 'po box 818',
    '400 ferris avenue',
}


def _has_real_address(addr):
    """True only if addr has content beyond a bare 'TX' / 'Texas' or is empty."""
    if not addr:
        return False
    cleaned = re.sub(r'[\s,]*(TX|Texas)[\s,]*$', '', addr.strip(), flags=re.IGNORECASE).strip().rstrip(',').strip()
    if len(cleaned) <= 3:
        return False
    # Reject known garbage values scraped in the past:
    #  - "P.O. Box 818" etc. — MVBA's own mailing address, not a property situs
    #  - "Market Area:" / "Market Area" / "CD:" / "Map ID:" — a neighboring
    #    field LABEL leaked into the address by a DOM-scrape mispair, not a value
    if re.match(r'^P\.?\s*O\.?\s*Box\b', cleaned, re.IGNORECASE):
        return False
    if cleaned.rstrip(':').strip().lower() in ('market area', 'cd', 'map id'):
        return False
    # "2 of the Northwest 1/4 of Section 28, BBB..." — a legal-description
    # fragment (fraction-of-a-survey wording), not a street address. MVBA's
    # own address regex falls back to grabbing this shape when a listing has
    # no real situs address in the PDF at all. A genuine street address is
    # never phrased "<number> of (the) ...", so this is a safe reject.
    if re.match(r'^\d+(/\d+)?\s+of\s+(the\s+)?', cleaned, re.IGNORECASE):
        return False
    # Strip a trailing city/zip fragment (e.g. "201 W. Grand, Marshall, TX 75670")
    # before comparing so partial matches from different truncation points still hit.
    street_part = cleaned.split(',')[0].strip().lower()
    if street_part in _KNOWN_PLACEHOLDER_ADDRESSES:
        return False
    return True


def _address_strength(addr):
    """
    Rough score for picking the stronger of two candidate addresses (existing
    sheet value vs. a freshly scraped CAD value) when neither should blindly
    win just by being present. El Paso CAD's "Location > Address" field is
    frequently just a bare "TX {zip}" on vacant-land parcels with no situs
    address on file — real per the loose _has_real_address() check, but far
    weaker than a full street address already sitting in the sheet.
    """
    if not addr or not _has_real_address(addr):
        return 0
    score = 0
    if re.match(r'^\d', addr.strip()):
        score += 2
    score += len([p for p in addr.split(',') if p.strip()])
    if len(addr.strip()) > 15:
        score += 1
    return score


def _has_real_owner(name):
    """True only if name looks like a real owner, not an async-load placeholder."""
    if not name:
        return False
    cleaned = name.strip()
    if len(cleaned) < 3:
        return False
    if 'loading' in cleaned.lower():
        return False
    return True


def _filter_valid_accounts(raw_account, county):
    """
    Split a "/" joined account field and return only parts that match the county format.
    Most TX counties use R-prefix real-property accounts (R######); other prefixes
    like D (deed), B (business) are not searchable in the CAD portal and get dropped.
    A plain digit part (no letter prefix at all) is kept alongside an R-prefixed part
    rather than dropped — MVBA rows often pair an R-prefixed Property ID with a plain
    numeric Geo ID (e.g. "R484031/8716229"), and either one can be the value that
    actually resolves in a given CAD's search — both get tried and scored by owner
    match in run_cad_enrichment.
    PLAIN_NUMERIC_COUNTIES (dallas) use plain digit IDs exclusively instead.
    Returns a deduplicated ordered list; empty means nothing valid found.
    """
    parts = [p.strip() for p in raw_account.split('/') if p.strip()]
    if len(parts) <= 1:
        return parts

    if county == "eastland":
        # MVBA pairs a long parcel/lease tracking ID with the actual short
        # CAD Geo ID, e.g. "215480001000000000000000001/52840" — only the
        # short trailing segment is searchable on eastlandcad.org (the long
        # one isn't a real Geo ID and just wastes a search attempt), so use
        # that alone rather than trying both.
        return [parts[-1]]

    if county in PLAIN_NUMERIC_COUNTIES:
        numeric = [p for p in parts if re.match(r'^\d+$', p)]
        if numeric:
            # Keep only the longest parts — these are the properly zero-padded
            # account numbers; shorter parts are incomplete/non-standard IDs.
            max_len = max(len(p) for p in numeric)
            valid = [p for p in numeric if len(p) == max_len]
        else:
            valid = []
    else:
        valid = [p for p in parts if re.match(r'^[Rr]\d', p) or re.match(r'^\d+$', p)]

    seen, result = set(), []
    for p in valid:
        if p not in seen:
            seen.add(p)
            result.append(p)

    skipped = [p for p in parts if p not in result]
    if skipped:
        print(f"    🚫 Skipping non-matching accounts: {', '.join(skipped)}")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# SHARED DOM + TEXT EXTRACTOR
# (used by Anderson, Harrison, and Ellis — same site engine)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_direct_url_detail(page, url, county_label):
    """
    Generic detail extractor for CADs that use the
    /property-detail/{id}/{year} URL pattern (Anderson, Harrison, Ellis).
    """
    address      = ""
    owner        = ""
    market_value = ""

    try:
        scraped = page.evaluate("""
            () => {
                var result = { address: '', mailingAddress: '', owner: '', value: '' };
                var allText = document.body.innerText || '';
                var labelEls = [...document.querySelectorAll(
                    'th, td, dt, label, .label, .field-label, ' +
                    '[class*="label"], [class*="header"], strong, b'
                )];
                for (var el of labelEls) {
                    var lbl = (el.innerText || '').trim().toLowerCase();
                    var valEl = el.nextElementSibling;
                    if (!valEl) {
                        var row = el.closest('tr');
                        if (row) {
                            var tds = row.querySelectorAll('td');
                            if (tds.length >= 2) valEl = tds[tds.length - 1];
                        }
                    }
                    var val = valEl ? (valEl.innerText || '').trim() : '';
                    if (!val || val.length < 2) continue;
                    // valEl fallback (nextElementSibling / last <td>) sometimes lands on
                    // the NEXT field's label instead of an actual value (e.g. "Address:"
                    // row has no value cell, so we grab "Market Area:" by mistake).
                    // A value ending in ':' is itself a label — never trust it.
                    if (val.trim().endsWith(':')) continue;
                    // Situs/property address is the real thing we want. "Mailing
                    // Address" is the OWNER's mailing address (often a PO box, and
                    // often rendered BEFORE the situs address in DOM order) — keep
                    // it separate so it can only be used as a last-resort fallback,
                    // never let it beat a real situs address just by appearing first.
                    if (!result.address && (lbl.includes('situs') || lbl === 'property address' || lbl === 'address')) {
                        result.address = val;
                    }
                    if (!result.mailingAddress && lbl === 'mailing address') {
                        result.mailingAddress = val;
                    }
                    if (!result.owner && (lbl.includes('owner') || lbl === 'name') && !val.toLowerCase().includes('loading')) {
                        result.owner = val;
                    }
                    if (!result.value && (lbl.includes('market value') || lbl === 'market' || lbl.includes('appraised value') || lbl.includes('total value'))) {
                        result.value = val;
                    }
                }
                if (!result.address) {
                    var m = allText.match(/(?:Situs\s+Address|(?:^|\\n)\\s*Address)[:\\s]+([^\\n]{5,120})/im);
                    if (m) result.address = m[1].trim();
                }
                if (!result.address && result.mailingAddress) {
                    result.address = result.mailingAddress;
                }
                if (!result.owner) {
                    var m = allText.match(/Owner(?:\\s+Name)?[:\\s]+([A-Z][^\\n]{2,80})/i);
                    if (m) result.owner = m[1].trim().split(/\\s{3,}/)[0];
                }
                if (!result.value) {
                    var m = allText.match(/(?:Total\\s+)?(?:Market|Appraised)\\s+(?:Value\\s+)?([\\d,]+)/i);
                    if (!m) m = allText.match(/\\bMarket\\s+([\\d,]+)/);
                    if (m) result.value = m[1];
                }
                return result;
            }
        """)
        address = scraped.get("address", "").strip().rstrip(",")
        owner   = scraped.get("owner", "").strip()
        raw_val = scraped.get("value", "").replace(",", "").replace("$", "").strip()
        if raw_val.isdigit():
            market_value = f"${int(raw_val):,}"
        if address:
            address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
            address = address.split('\n')[0].strip()
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
            print(f"    🏠 {county_label} address: {address}")
        if owner:
            print(f"    👤 {county_label} owner: {owner}")
        if market_value:
            print(f"    💰 {county_label} value: {market_value}")
    except Exception as e:
        print(f"    ⚠️  {county_label} DOM extraction error: {e}")

    text = ""
    try:
        text = page.inner_text("body")
    except Exception:
        pass

    if not address and text:
        # Situs/Property address first — "Mailing Address" (often a PO box) can
        # appear earlier in the page text and must never win over a real situs
        # address just because it comes first.
        addr_m = re.search(r'(?:Situs\s+Address|Property\s+Address)[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
        if not addr_m:
            addr_m = re.search(r'(?:^|\n)\s*Address[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
        if not addr_m:
            addr_m = re.search(r'Mailing\s+Address[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
        address = addr_m.group(1).strip().rstrip(',') if addr_m else ""
        address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
        address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
    if not owner and text:
        owner_m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
        owner = owner_m.group(1).strip() if owner_m else ""
        owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', owner)[0].strip()
        if len(owner) < 3 or 'loading' in owner.lower():
            owner = ""
    if not market_value and text:
        market_value = extract_market_value(text)

    def _val(label):
        m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}"
            except Exception:
                pass
        return ""

    imp_homesite     = _val(r'Improvement\s+Homesite(?:\s+Value)?')
    imp_nonhomesite  = _val(r'Improvement\s+Non-?Homesite(?:\s+Value)?')
    land_homesite    = _val(r'Land\s+Homesite(?:\s+Value)?')
    land_nonhomesite = _val(r'Land\s+Non-?Homesite(?:\s+Value)?')
    ag_market        = _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

    if not market_value and text:
        m = re.search(r'(?:^|\n)\s*Market\s+([\d,]+)', text)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                market_value = f"${int(raw):,}"
            except Exception:
                pass

    interactive_map = ""
    google_maps_url = ""
    property_map    = ""

    if url and '/property-detail/' in url:
        interactive_map = url.rstrip('/') + '/gis'
        property_map    = interactive_map
        print(f"    🗺️  {county_label} GIS Map: {interactive_map}")

    if not google_maps_url and address:
        google_maps_url = build_google_maps_url(address)
        if not property_map:
            property_map = google_maps_url
        print(f"    🗺️  Google Maps (built from address): {google_maps_url[:80]}")

    zillow_url = build_zillow_url(address)
    if zillow_url:
        print(f"    🏡 Zillow: {zillow_url[:80]}")

    print(f"    🔗 Canonical: {url}")
    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         url,
        "Property Map":               property_map,
        "Interactive Map":            interactive_map,
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        ag_market,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ANDERSON CAD — DIRECT URL SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

def _anderson_clean_id(raw):
    clean = re.sub(r'^[Rr]', '', raw.strip())
    clean = clean.lstrip('0') or '0'
    return clean


def _scrape_anderson_property(page, account_number):
    clean = _anderson_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse Anderson account: {account_number}")
        return None
    print(f"    🔍 Anderson account: {clean}")
    _anderson_homes = {
        "https://andersoncad.net", "https://www.andersoncad.net",
        "https://andersoncad.net/property-search",
        "https://www.andersoncad.net/property-search",
    }
    for year in [CURRENT_YEAR, str(int(CURRENT_YEAR) - 1)]:
        url = f"https://andersoncad.net/property-detail/{clean}/{year}"
        try:
            print(f"    🌐 Trying: {url}")
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            body = page.inner_text("body")
            redirected_home = re.sub(r'/$', '', page.url) in _anderson_homes
            has_error = re.search(r'not found|404|no property|page not found', body, re.IGNORECASE)
            if not redirected_home and not has_error:
                print(f"    ✅ Anderson detail loaded: {page.url[:80]}")
                return _extract_direct_url_detail(page, page.url, "Anderson")
            print(f"    🔄 {clean}/{year} not found — trying next year")
        except Exception as e:
            print(f"    ⚠️  Anderson load error {clean}/{year}: {e}")
    print(f"    ❌ Anderson property not found: {account_number}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# ELLIS CAD — DIRECT URL SCRAPER
# URL pattern: https://www.elliscad.org/property-detail/{id}/{year}
# ═══════════════════════════════════════════════════════════════════════════

def _ellis_clean_id(raw):
    """Strip leading R/r and leading zeros from Ellis account numbers."""
    clean = re.sub(r'^[Rr]', '', raw.strip())
    clean = clean.lstrip('0') or '0'
    return clean


_ELLIS_HOME_URLS = {
    "https://www.elliscad.org",
    "https://elliscad.org",
    "https://www.elliscad.org/property-search",
    "https://elliscad.org/property-search",
}


def _ellis_fmt_money(n):
    try:
        return f"${int(round(float(n))):,}"
    except (TypeError, ValueError):
        return ""


def _ellis_fetch_api_record(page, pid):
    """
    Query Ellis CAD's own TrueProdigy public API for a property's values/owner/
    address, run from inside the page (fetch calls made via page.evaluate reuse
    the browser's network stack/CORS context, unlike Playwright's request API).

    The property-detail page's "CURRENT VALUES" panel is populated client-side
    and intermittently never fills in — the label renders (e.g. "Land Homesite")
    but its value <span> stays empty even minutes after the rest of the page has
    loaded — while this API (the same one the page itself calls) reliably
    returns the data. Used as the source of truth for the numeric value fields.
    """
    try:
        results = page.evaluate("""
            async (pid) => {
                const tokenResp = await fetch('https://prod-container.trueprodigyapi.com/trueprodigy/cadpublic/auth/token', {
                    method: 'POST',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({office: 'Ellis'})
                });
                const tokenJson = await tokenResp.json();
                const token = tokenJson && tokenJson.user && tokenJson.user.token;
                if (!token) return null;
                const searchResp = await fetch('https://prod-container.trueprodigyapi.com/public/property/search', {
                    method: 'POST',
                    headers: {'content-type': 'application/json', 'authorization': token},
                    body: JSON.stringify({pid: {operator: '=', value: String(pid)}})
                });
                if (!searchResp.ok) return null;
                const searchJson = await searchResp.json();
                return searchJson.results || [];
            }
        """, pid)
    except Exception as e:
        print(f"    ⚠️  Ellis API error: {e}")
        return None
    if not results:
        return None
    rec = next((r for r in results if str(r.get("pYear")) == CURRENT_YEAR), None)
    if not rec:
        rec = max(results, key=lambda r: str(r.get("pYear", "")))
    return rec


def _scrape_ellis_property(page, account_number, row=None):
    clean = _ellis_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse Ellis account: {account_number}")
        return None
    print(f"    🔍 Ellis account: {clean}")

    for year in [CURRENT_YEAR, str(int(CURRENT_YEAR) - 1)]:
        url = f"{ELLIS_BASE_URL}/property-detail/{clean}/{year}"
        try:
            print(f"    🌐 Trying: {url}")
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)

            body = page.inner_text("body")
            redirected_home = re.sub(r'/$', '', page.url) in _ELLIS_HOME_URLS
            has_error = re.search(r'not found|404|no property|page not found', body, re.IGNORECASE)

            if not redirected_home and not has_error:
                print(f"    ✅ Ellis detail loaded: {page.url[:80]}")
                result = _extract_direct_url_detail(page, page.url, "Ellis")
                rec = _ellis_fetch_api_record(page, clean)
                if rec:
                    land_value = float(rec.get("landValue") or 0)
                    imp_value  = float(rec.get("improvementValue") or 0)
                    land_pct   = float(rec.get("landHomesitePct") or 0) / 100
                    imp_pct    = float(rec.get("structureHomesitePct") or 0) / 100
                    result["Land Homesite Value"]        = _ellis_fmt_money(land_value * land_pct)
                    result["Land Non-Homesite Value"]    = _ellis_fmt_money(land_value * (1 - land_pct))
                    result["Improvement Homesite Value"] = _ellis_fmt_money(imp_value * imp_pct)
                    result["Improvement Non-Homesite"]   = _ellis_fmt_money(imp_value * (1 - imp_pct))
                    if rec.get("appraisedValue") is not None:
                        result["Adjusted Value"] = _ellis_fmt_money(rec["appraisedValue"])
                    if not result.get("Owner Name") and rec.get("displayName"):
                        result["Owner Name"] = rec["displayName"].strip()
                    if not result.get("Property Address") and rec.get("fullSitus"):
                        addr = rec["fullSitus"].strip().lstrip(",").strip()
                        result["Property Address"] = addr
                        if addr:
                            result["Zillow"]  = result.get("Zillow") or build_zillow_url(addr)
                            result["Realtor"] = result.get("Realtor") or build_realtor_search_url(addr)
                            gmaps = build_google_maps_url(addr)
                            result["Satellite View"] = result.get("Satellite View") or gmaps
                            result["Property Map"]   = result.get("Property Map") or gmaps
                    print(f"    💰 Ellis API values: land={result['Land Non-Homesite Value']} imp={result['Improvement Non-Homesite']}")

                # elliscad.org's LOCATION panel frequently lacks a house
                # number (rural/land parcels), unlike the sheriff auction
                # site's fuller listing address — never let a weaker CAD
                # address (e.g. "FM 780, FERRIS TX 75125") downgrade a
                # stronger one already on the sheet ("2421 FM 780, FERRIS,
                # TX 75125"). Same pattern as El Paso's _address_strength()
                # check above.
                existing_address = (row.get("Property Address", "") if row else "").strip()
                cad_address       = result.get("Property Address", "").strip()
                if cad_address and existing_address and _address_strength(existing_address) > _address_strength(cad_address):
                    print(f"    🏠 Ellis: keeping existing address (stronger than CAD's '{cad_address}')")
                    result["Property Address"] = ""

                return result

            print(f"    🔄 {clean}/{year} not found — trying next year")
        except Exception as e:
            print(f"    ⚠️  Ellis load error {clean}/{year}: {e}")

    print(f"    ❌ Ellis property not found: {account_number}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# TRAVIS CAD — PRODIGY CAD ENGINE
# URL pattern: https://travis.prodigycad.com/property-detail/{id}/{year}
# Account format: numeric (e.g. 181238) — strip leading R if present
# ═══════════════════════════════════════════════════════════════════════════

def _travis_clean_id(raw):
    """Strip leading R/r and leading zeros from Travis account numbers."""
    clean = re.sub(r'^[Rr]', '', raw.strip())
    clean = clean.lstrip('0') or '0'
    return clean


def _travis_money(v):
    try:
        return f"${int(round(float(v))):,}"
    except Exception:
        return ""


def _scrape_travis_property(page, account_number):
    """
    Travis CAD's site (Prodigy CAD SPA) indexes properties by a short
    Property ID / Geo ID — NOT the longer Tax Office ID we store as
    "Account Number" (e.g. account "02452105020000" vs Geo ID
    "0245210502", which is just the account's first 10 digits).
    Navigating straight to /property-detail/{account}/{year} with the
    Tax Office ID silently loads a page whose data never populates
    (wrong id), which is why address/owner/values were always blank.

    Fix: on the /property-search page, explicitly select the "Tax Office
    ID" field from the search-field dropdown and search with the exact
    stored account number (no guessing/truncation needed — the site
    supports searching that field directly), then read the property
    record straight out of the site's own JSON search API response
    (captured via page.on("response")). Falls back to a derived-Geo-ID
    compound search if the dropdown flow doesn't work for some reason.
    """
    clean = _travis_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse Travis account: {account_number}")
        return None
    raw_account = account_number.strip()
    print(f"    🔍 Travis account: {raw_account}")

    captured = {}

    def _on_response(resp):
        if "public/property/search" in resp.url and resp.request.method == "POST":
            try:
                captured["data"] = resp.json()
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        # The Prodigy CAD SPA is occasionally slow to hydrate under
        # automation — retry a couple of times before giving up.
        for attempt in range(3):
            try:
                page.goto(f"{TRAVIS_BASE_URL}/property-search", timeout=30000)
                dropdown = page.locator('[role="combobox"]').first
                dropdown.wait_for(state="visible", timeout=15000)
                dropdown.click()
                option = page.get_by_role("option", name="Tax Office ID", exact=True)
                option.wait_for(state="visible", timeout=5000)
                option.click()

                search_box = page.locator('input[type="text"]').first
                search_box.wait_for(state="visible", timeout=5000)
                search_box.click()
                search_box.fill(raw_account)
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
                if captured.get("data") is not None:
                    break
            except Exception as e:
                print(f"    ⚠️  Travis search attempt {attempt + 1} failed: {e}")

        if captured.get("data") is None:
            search_term = clean[:10] if len(clean) >= 10 else clean
            print(f"    🔄 Falling back to compound search: {search_term}")
            try:
                page.goto(TRAVIS_BASE_URL, timeout=30000)
                box = page.locator('input[placeholder*="Account Number"]')
                box.wait_for(state="visible", timeout=15000)
                box.click()
                box.fill(search_term)
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
            except Exception as e:
                print(f"    ⚠️  Travis fallback search failed: {e}")
    finally:
        try:
            page.remove_listener("response", _on_response)
        except Exception:
            pass

    results = ((captured.get("data") or {}).get("results")) or []
    if not results:
        print(f"    ❌ Travis property not found: {account_number}")
        return None

    entry = next(
        (r for r in results if str(r.get("refID2", "")).lstrip("0") == clean.lstrip("0")),
        results[0],
    )

    pid  = entry.get("pid")
    year = entry.get("pYear", CURRENT_YEAR)
    detail_url = f"{TRAVIS_BASE_URL}/property-detail/{pid}/{year}"

    owner = (entry.get("name") or "").strip()

    address = (entry.get("fullSitus") or "").strip()
    address = re.sub(r'\s*,\s*TX\s*,\s*', ', TX ', address, flags=re.IGNORECASE)
    address = re.sub(r'\s+', ' ', address).strip(', ').strip()
    if address:
        print(f"    🏠 Travis address: {address}")
    if owner:
        print(f"    👤 Travis owner: {owner}")

    land_value  = entry.get("landValue") or 0
    imp_value   = entry.get("improvementValue") or 0
    land_hs_pct = float(entry.get("landHomesitePct") or 0) / 100
    imp_hs_pct  = float(entry.get("structureHomesitePct") or 0) / 100

    land_homesite    = _travis_money(land_value * land_hs_pct)
    land_nonhomesite = _travis_money(land_value * (1 - land_hs_pct))
    imp_homesite     = _travis_money(imp_value * imp_hs_pct)
    imp_nonhomesite  = _travis_money(imp_value * (1 - imp_hs_pct))
    market_value     = _travis_money(entry.get("appraisedValue") or entry.get("marketValue") or 0)

    lat, lon = entry.get("latitude"), entry.get("longitude")
    if lat and lon:
        google_maps_url = f"https://maps.google.com/maps?q={lat},{lon}"
    else:
        google_maps_url = build_google_maps_url(address) if address else ""

    # Pull the real "GIS Map" link off the property page's Maps dropdown
    # (Property | {pid} > Maps > GIS Map) instead of guessing a URL.
    interactive_map = ""
    try:
        page.goto(detail_url, timeout=20000)
        page.wait_for_timeout(4000)
        maps_btn = page.locator("text=Maps").first
        maps_btn.click(timeout=5000)
        page.wait_for_timeout(500)
        gis_href = page.eval_on_selector(
            "text=GIS Map",
            "el => { const a = el.closest('a'); return a ? a.href : null; }"
        )
        if gis_href:
            interactive_map = gis_href
            print(f"    🗺️  Travis GIS Map: {interactive_map}")
    except Exception as e:
        print(f"    ⚠️  Travis GIS map link error: {e}")

    zillow_url  = build_zillow_url(address) if address else ""
    realtor_url = build_realtor_search_url(address) if address else ""

    print(f"    🔗 Canonical: {detail_url}")
    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         detail_url,
        "Property Map":               google_maps_url,
        "Interactive Map":            interactive_map,
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Realtor":                    realtor_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# McLENNAN CAD — mclennancad.org (True Prodigy engine, same API as Travis)
# Search: {base}/property-search → fill #searchInput (default "Compound Text
#         Search" field already accepts a plain Geo ID) → Enter → read the
#         property record straight out of the site's own JSON search API
#         response (public/property/searchfulltext), same as Travis.
# Account format: MVBA sometimes exports "PropID/GeoID" (e.g.
#   "R08335/460520000002003") — only the digits after the slash are
#   searchable; the compound search rejects the PropID half.
# ═══════════════════════════════════════════════════════════════════════════

def _mclennan_clean_id(raw):
    """Extract the numeric Geo ID McLennan's compound search expects."""
    part = raw.strip().rsplit('/', 1)[-1]
    return re.sub(r'\D', '', part)


def _scrape_mclennan_property(page, account_number):
    clean = _mclennan_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse McLennan account: {account_number}")
        return None
    print(f"    🔍 McLennan account: {account_number} → Geo ID: {clean}")

    captured = {}

    def _on_response(resp):
        if "searchfulltext" in resp.url and resp.request.method == "POST":
            try:
                captured["data"] = resp.json()
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        for attempt in range(3):
            try:
                page.goto(f"{MCLENNAN_BASE_URL}/property-search", timeout=30000)
                search_input = page.locator("#searchInput")
                search_input.wait_for(state="visible", timeout=15000)
                search_input.click()
                search_input.fill(clean)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)
                if captured.get("data") is not None:
                    break
            except Exception as e:
                print(f"    ⚠️  McLennan search attempt {attempt + 1} failed: {e}")
    finally:
        try:
            page.remove_listener("response", _on_response)
        except Exception:
            pass

    results = ((captured.get("data") or {}).get("results")) or []
    if not results:
        print(f"    ❌ McLennan property not found: {account_number}")
        return None

    entry = next((r for r in results if str(r.get("geoID", "")) == clean), results[0])

    pid  = entry.get("pid")
    year = entry.get("pYear", CURRENT_YEAR)
    detail_url = f"{MCLENNAN_BASE_URL}/property-detail/{pid}/{year}"

    owner = (entry.get("name") or "").strip()

    address = (entry.get("fullSitus") or "").strip()
    address = re.sub(r'\s*,\s*TX\s*,\s*', ', TX ', address, flags=re.IGNORECASE)
    address = re.sub(r'\s+', ' ', address).strip(', ').strip()
    if address:
        print(f"    🏠 McLennan address: {address}")
    if owner:
        print(f"    👤 McLennan owner: {owner}")

    land_value  = entry.get("landValue") or 0
    imp_value   = entry.get("improvementValue") or 0
    land_hs_pct = float(entry.get("landHomesitePct") or 0) / 100
    imp_hs_pct  = float(entry.get("structureHomesitePct") or 0) / 100

    land_homesite    = _travis_money(land_value * land_hs_pct)
    land_nonhomesite = _travis_money(land_value * (1 - land_hs_pct))
    imp_homesite     = _travis_money(imp_value * imp_hs_pct)
    imp_nonhomesite  = _travis_money(imp_value * (1 - imp_hs_pct))
    market_value     = _travis_money(entry.get("appraisedValue") or entry.get("marketValue") or 0)

    lat, lon = entry.get("latitude"), entry.get("longitude")
    if lat and lon:
        google_maps_url = f"https://maps.google.com/maps?q={lat},{lon}"
    else:
        google_maps_url = build_google_maps_url(address) if address else ""

    zillow_url  = build_zillow_url(address) if address else ""
    realtor_url = build_realtor_search_url(address) if address else ""

    print(f"    🔗 Canonical: {detail_url}")
    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         detail_url,
        "Property Map":               google_maps_url,
        "Interactive Map":            "",
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Realtor":                    realtor_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# MIDLAND CAD — ISW / SOUTHWEST DATA SOLUTIONS PORTAL
# Search: https://iswdataclient.azurewebsites.net/webindex.aspx?dbkey=MIDLANDCAD
# Account format: R########  (e.g. R00210892)
# Address source: "Approximate Address" field in property description
# ═══════════════════════════════════════════════════════════════════════════

def _midland_clean_id(raw):
    """
    Midland accounts: keep the leading R, strip extra spaces.
    ISW portal searches by Property ID or Account Number as-is.
    """
    return raw.strip()


def _scrape_midland_property(page, account_number):
    clean = _midland_clean_id(account_number)
    print(f"    🔍 Midland account: {clean}")

    try:
        page.goto(MIDLAND_SEARCH_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # ISW portal: find the search input — try multiple selectors
        search_input = page.locator(
            "input[name='txtAccountNum'], input[id='txtAccountNum'], "
            "input[name*='account' i], input[placeholder*='account' i], "
            "input[name*='id' i], input[type='text']"
        )
        visible_inputs = [search_input.nth(i) for i in range(search_input.count())
                          if search_input.nth(i).is_visible()]
        if not visible_inputs:
            print(f"    ⚠️  Midland: no search input found")
            return None

        visible_inputs[0].clear()
        visible_inputs[0].fill(clean)
        print(f"    ✏️  Entered account: {clean}")

        # Submit — try button first, then Enter
        submit = page.locator(
            "input[type='submit'], button[type='submit'], "
            "button:has-text('Search'), input[value='Search']"
        )
        clicked = False
        for i in range(submit.count()):
            el = submit.nth(i)
            if el.is_visible():
                el.click()
                clicked = True
                print(f"    🖱️  Search submitted")
                break
        if not clicked:
            page.keyboard.press("Enter")
            print(f"    ⌨️  Enter pressed")

        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        # Try to click first result link
        result_link = page.locator(
            "a[href*='webproperty'], a[href*='Property'], "
            "a[href*='detail'], table a"
        )
        if result_link.count() > 0:
            result_link.first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)
            print(f"    🖱️  Clicked result link")
        else:
            print(f"    ℹ️  No result link — may already be on detail page")

        text = page.inner_text("body")
        final_url = page.url

        # ── Address: prefer "Approximate Address" (shown in Midland documents)
        # then fall back to Situs Address / Property Address
        address = ""
        approx_m = re.search(
            r'Approximate\s+Address[:\s]+([^\n]{5,120})', text, re.IGNORECASE
        )
        if approx_m:
            address = approx_m.group(1).strip().rstrip(',')
            address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
            print(f"    🏠 Midland Approximate Address: {address}")

        if not address:
            situs_m = re.search(
                r'(?:Situs\s+Address|Property\s+Address)[:\s]+([^\n]{5,120})',
                text, re.IGNORECASE
            )
            if situs_m:
                address = situs_m.group(1).strip().rstrip(',')
                address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
                address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
                print(f"    🏠 Midland Situs Address: {address}")

        # Also try DOM scraping for address
        if not address:
            try:
                dom_addr = page.evaluate("""
                    () => {
                        var els = [...document.querySelectorAll('td, th, span, div, label')];
                        for (var el of els) {
                            var t = (el.innerText || '').trim().toLowerCase();
                            if (t.includes('approximate address') || t.includes('situs address') || t.includes('property address')) {
                                var next = el.nextElementSibling;
                                if (next) return (next.innerText || '').trim();
                                var row = el.closest('tr');
                                if (row) {
                                    var tds = row.querySelectorAll('td');
                                    if (tds.length >= 2) return (tds[tds.length-1].innerText || '').trim();
                                }
                            }
                        }
                        return '';
                    }
                """)
                if dom_addr and len(dom_addr) > 4:
                    address = dom_addr.strip().rstrip(',')
                    address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
                    print(f"    🏠 Midland DOM address: {address}")
            except Exception as e:
                print(f"    ⚠️  Midland DOM addr error: {e}")

        # Owner
        owner = ""
        owner_m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
        if owner_m:
            owner = owner_m.group(1).strip()
            owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', owner)[0].strip()
            if len(owner) < 3:
                owner = ""
        if owner:
            print(f"    👤 Midland owner: {owner}")

        # Market value
        market_value = extract_market_value(text)
        if market_value:
            print(f"    💰 Midland value: {market_value}")

        def _val(label):
            m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite     = _val(r'Improvement\s+Homesite(?:\s+Value)?')
        imp_nonhomesite  = _val(r'Improvement\s+Non-?Homesite(?:\s+Value)?')
        land_homesite    = _val(r'Land\s+Homesite(?:\s+Value)?')
        land_nonhomesite = _val(r'Land\s+Non-?Homesite(?:\s+Value)?')
        ag_market        = _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        property_map    = google_maps_url

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")
        print(f"    🔗 Canonical: {final_url}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Midland scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# HARRISON CAD — DIRECT URL SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

def _harrison_clean_id(raw):
    clean = re.sub(r'^[Rr]', '', raw.strip())
    clean = clean.lstrip('0')
    return clean


def _harrison_load_page(page, prop_id):
    for year in [CURRENT_YEAR, str(int(CURRENT_YEAR) - 1)]:
        url = f"https://harrisoncad.net/property-detail/{prop_id}/{year}"
        try:
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            # Owner/Address/Value data all load via async JS after the shell
            # renders. The shell shows "Loading ..." text for the owner section,
            # but the Address/Mailing Address fields default to the appraisal
            # district's OWN office address ("201 W. Grand" / "P.O. Box 818")
            # as a template skeleton — no "loading" word, so wait for those
            # exact placeholders to be replaced too, not just the word "loading".
            try:
                page.wait_for_function(
                    "() => { var t = document.body.innerText.toLowerCase(); "
                    "return !/loading/.test(t) && !t.includes('201 w. grand') "
                    "&& !t.includes('201 w grand') && !t.includes('po box 818') "
                    "&& !t.includes('p.o. box 818'); }",
                    timeout=8000
                )
            except Exception:
                pass
            page.wait_for_timeout(500)
            redirected_home = page.url.rstrip('/') == "https://harrisoncad.net"
            body = page.inner_text("body")
            has_error = re.search(r'not found|404|no property|page not found', body, re.IGNORECASE)
            if not redirected_home and not has_error:
                return page.url, body
            print(f"    🔄  {prop_id}/{year} not found — trying next")
        except Exception as e:
            print(f"    ⚠️  Load error {prop_id}/{year}: {e}")
    return None, None


def _owner_similarity(name_a, name_b):
    if not name_a or not name_b:
        return 0.0
    words_a = set(re.sub(r'[^a-z0-9 ]', '', name_a.lower()).split())
    words_b = set(re.sub(r'[^a-z0-9 ]', '', name_b.lower()).split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


def _scrape_harrison_property(page, account_number, expected_owner=""):
    raw_accounts = [a.strip() for a in account_number.strip().split('/') if a.strip()]

    if len(raw_accounts) == 1:
        clean = _harrison_clean_id(raw_accounts[0])
        if not clean:
            print(f"    ⚠️  Could not parse Harrison account: {account_number}")
            return None
        print(f"    🔍 Harrison single account: {clean}")
        loaded_url, _ = _harrison_load_page(page, clean)
        if not loaded_url:
            print(f"    ❌ Harrison property not found: {account_number}")
            return None
        print(f"    ✅ Harrison detail loaded: {loaded_url[:80]}")
        return _extract_direct_url_detail(page, loaded_url, "Harrison")

    print(f"    🔀 Harrison multi-account ({len(raw_accounts)}): {account_number}")
    candidates = []
    for raw in raw_accounts:
        clean = _harrison_clean_id(raw)
        if not clean:
            continue
        print(f"    🔍 Checking Harrison account: {clean}")
        loaded_url, _ = _harrison_load_page(page, clean)
        if not loaded_url:
            print(f"    ⚠️  Skipping {clean} — not found")
            continue
        result = _extract_direct_url_detail(page, loaded_url, "Harrison")
        if result:
            scraped_owner = result.get("Owner Name", "")
            score = _owner_similarity(expected_owner, scraped_owner) if expected_owner else 0.0
            candidates.append((score, clean, loaded_url, result))
            print(f"    👤 Account {clean} owner: '{scraped_owner}' — match score: {score:.2f}")

    if not candidates:
        print(f"    ❌ No valid Harrison accounts found for: {account_number}")
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_id, _, best_result = candidates[0]
    if expected_owner and best_score == 0.0:
        print(f"    ⚠️  No owner match found — using first loaded account: {best_id}")
    else:
        print(f"    ✅ Best match: account {best_id} (score={best_score:.2f})")
    return best_result


# ═══════════════════════════════════════════════════════════════════════════
# BIS DETAIL EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════

def _extract_bis_detail(text, url, _searched_account=None, page=None):
    addr_m  = re.search(r'Situs\s+Address[:\s]+([^\n]{5,100})', text, re.IGNORECASE)
    address = addr_m.group(1).strip().rstrip(',') if addr_m else ""
    address = re.sub(r',?\s*(TX|Texas)\s*$', ', TX', address, flags=re.IGNORECASE).strip()

    owner_m = re.search(r'\bName[:\s]+([A-Z][^\n]{2,60})', text)
    owner   = owner_m.group(1).strip() if owner_m else ""
    if owner.lower().startswith("name") or len(owner) < 3:
        owner = ""

    market_value = extract_market_value(text)

    def _val(label):
        m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}"
            except Exception:
                pass
        return ""

    imp_homesite     = _val(r'Improvement\s+Homesite\s+Value')
    imp_nonhomesite  = _val(r'Improvement\s+Non-Homesite\s+Value')
    land_homesite    = _val(r'Land\s+Homesite\s+Value')
    land_nonhomesite = _val(r'Land\s+Non-Homesite\s+Value')
    ag_market        = _val(r'Agricultural\s+Market\s+Valuation')

    interactive_map = ""
    property_map    = ""

    if page:
        try:
            view_map_btn = page.locator(
                "#map-links .dropdown-toggle, #map-links button, "
                "button:has-text('View Map'), a:has-text('View Map'), "
                "[class*='viewMap'], [id*='viewMap'], button.dropdown-toggle:has-text('Map')"
            )
            if view_map_btn.count() > 0:
                btn = view_map_btn.first
                try:
                    btn.wait_for(state="visible", timeout=5000)
                    btn.click()
                    page.wait_for_timeout(1500)
                    print(f"    🗺️  'View Map' dropdown opened")
                except Exception:
                    print(f"    ⚠️  Map button found but not visible — skipping click")
            else:
                print(f"    ⚠️  'View Map' button not found — trying DOM href scan")

            map_href = page.evaluate("""
                () => {
                    var candidates = [...document.querySelectorAll('a, button, li, [role="menuitem"]')];
                    for (var el of candidates) {
                        var txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        if (txt === 'interactive map' || txt.includes('interactive map')) {
                            if (el.tagName === 'A' && el.href && !el.href.startsWith('javascript')) return el.href;
                            var parent = el.closest('a');
                            if (parent && parent.href && !parent.href.startsWith('javascript')) return parent.href;
                            var child = el.querySelector('a');
                            if (child && child.href && !child.href.startsWith('javascript')) return child.href;
                            var oc = el.getAttribute('onclick') || '';
                            if (oc) return '__onclick__:' + oc;
                        }
                    }
                    return '';
                }
            """)

            if map_href and not map_href.startswith('__onclick__:'):
                interactive_map = map_href
                property_map    = map_href
                print(f"    🗺️  Interactive Map (href): {map_href[:80]}")
            elif map_href and map_href.startswith('__onclick__:'):
                onclick_code = map_href.replace('__onclick__:', '')
                with page.context.expect_page() as new_page_info:
                    page.evaluate(onclick_code)
                new_tab = new_page_info.value
                new_tab.wait_for_load_state("domcontentloaded", timeout=15000)
                captured = new_tab.url
                new_tab.close()
                if captured and captured not in ("about:blank", ""):
                    interactive_map = captured
                    property_map    = captured
                    print(f"    🗺️  Interactive Map (new tab): {captured[:80]}")
            else:
                interactive_map_el = page.locator(
                    "a:has-text('Interactive Map'), li:has-text('Interactive Map'), "
                    "button:has-text('Interactive Map'), [role='menuitem']:has-text('Interactive Map')"
                )
                if interactive_map_el.count() > 0:
                    with page.context.expect_page() as new_page_info:
                        interactive_map_el.first.click(modifiers=["Control"])
                    new_tab = new_page_info.value
                    try:
                        new_tab.wait_for_load_state("domcontentloaded", timeout=15000)
                        captured = new_tab.url
                    except Exception:
                        captured = new_tab.url
                    finally:
                        new_tab.close()
                    if captured and captured not in ("about:blank", ""):
                        interactive_map = captured
                        property_map    = captured
                        print(f"    🗺️  Interactive Map (ctrl+click): {captured[:80]}")
        except Exception as e:
            print(f"    ⚠️  Map capture error: {e}")

        if not interactive_map:
            try:
                fallback_href = page.evaluate("""
                    () => {
                        var allLinks = document.querySelectorAll('a[href]');
                        var patterns = [
                            /gis\\.bisclient\\.com/i, /arcgis/i, /esri/i,
                            /maps\\.google/i, /bing\\.com\\/maps/i,
                            /mapviewer/i, /parcelviewer/i, /\\/gis\\//i, /MapService/i,
                        ];
                        for (var a of allLinks) {
                            for (var p of patterns) { if (p.test(a.href)) return a.href; }
                        }
                        for (var a of allLinks) {
                            if (/map/i.test(a.href) && a.href.startsWith('http')) return a.href;
                        }
                        return '';
                    }
                """)
                if fallback_href:
                    interactive_map = fallback_href
                    property_map    = fallback_href
                    print(f"    🗺️  Interactive Map (DOM fallback): {fallback_href[:80]}")
            except Exception as e:
                print(f"    ⚠️  DOM fallback error: {e}")

    google_maps = build_google_maps_url(address)
    if not property_map and google_maps:
        property_map = google_maps
        print(f"    🗺️  Property Map (address fallback): {google_maps[:80]}")

    zillow_url = build_zillow_url(address)
    if zillow_url:
        print(f"    🏡 Zillow: {zillow_url[:80]}")

    prop_id_m = re.search(r'/Property/View/(\d+)', url, re.IGNORECASE)
    canonical_url = url
    if prop_id_m:
        owner_id_m  = re.search(r'[?&]ownerId=(\w+)', url)
        host_full_m = re.search(r'(https?://[^/]+)', url)
        if host_full_m and owner_id_m:
            canonical_url = (
                f"{host_full_m.group(1)}"
                f"/Property/View/{prop_id_m.group(1)}"
                f"?year={CURRENT_YEAR}&ownerId={owner_id_m.group(1)}"
            )
            print(f"    🔗 Canonical URL (year={CURRENT_YEAR}): {canonical_url[:80]}")

    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         canonical_url,
        "Property Map":               property_map,
        "Interactive Map":            interactive_map,
        "Satellite View":             google_maps,
        "Zillow":                     zillow_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        ag_market,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ESEARCH DETAIL EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════

def _extract_esearch_detail(text, url, page=None):
    addr_m = re.search(r'(?:Situs\s+Address)[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
    address = addr_m.group(1).strip().rstrip(',') if addr_m else ""
    address = re.sub(r',?\s*(TX|Texas)\s*$', ', TX', address, flags=re.IGNORECASE).strip()

    if not address and page:
        try:
            dom_address = page.evaluate("""
                () => {
                    var rows = [...document.querySelectorAll('tr, .detail-row, .property-row')];
                    for (var row of rows) {
                        var cells = row.querySelectorAll('td, th, .label, .value');
                        for (var i = 0; i < cells.length - 1; i++) {
                            var label = (cells[i].innerText || '').trim().toLowerCase();
                            if (label.includes('situs') || label.includes('situs address')) {
                                var val = (cells[i+1].innerText || '').trim();
                                if (val.length > 4) return val;
                            }
                        }
                    }
                    var dts = [...document.querySelectorAll('dt, .field-label')];
                    for (var dt of dts) {
                        if (/situs/i.test(dt.innerText || '')) {
                            var dd = dt.nextElementSibling;
                            if (dd) return (dd.innerText || '').trim();
                        }
                    }
                    return '';
                }
            """)
            if dom_address and len(dom_address) > 4:
                address = dom_address.strip().rstrip(',')
                address = re.sub(r',?\s*(TX|Texas)\s*$', ', TX', address, flags=re.IGNORECASE).strip()
                print(f"    🏠 Address from DOM: {address}")
        except Exception as e:
            print(f"    ⚠️  DOM address error: {e}")

    owner_m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
    owner = owner_m.group(1).strip() if owner_m else ""
    if not owner:
        # BIS Consultants layout: "Owner" heading, then "Owner ID:\t123", then "Name:\tJOHN DOE"
        name_m = re.search(
            r'Owner\s*\n\s*Owner\s*ID[:\s]+\S+\s*\n\s*Name[ \t:]+([^\n]{2,100})',
            text, re.IGNORECASE
        )
        owner = name_m.group(1).strip() if name_m else ""
    owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', owner)[0].strip()
    if len(owner) < 3:
        owner = ""

    market_value = extract_market_value(text)

    def _val(label):
        m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}"
            except Exception:
                pass
        return ""

    imp_homesite     = _val(r'Improvement\s+Homesite\s+Value')
    imp_nonhomesite  = _val(r'Improvement\s+Non-?Homesite\s+Value')
    land_homesite    = _val(r'Land\s+Homesite\s+Value')
    land_nonhomesite = _val(r'Land\s+Non-?Homesite\s+Value')
    ag_market        = _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

    interactive_map = ""
    google_maps_url = ""
    property_map    = ""

    if page:
        try:
            view_map_btn = page.locator(
                "#map-links .dropdown-toggle, #map-links button, "
                "button:has-text('View Map'), a:has-text('View Map'), "
                ".dropdown-toggle:has-text('Map'), button:has-text('Map')"
            )
            if view_map_btn.count() > 0:
                btn = view_map_btn.first
                try:
                    btn.wait_for(state="visible", timeout=5000)
                    btn.click()
                    page.wait_for_timeout(500)
                    print(f"    🗺️  View Map dropdown opened")
                except Exception:
                    print(f"    ⚠️  Map button not visible — using DOM scan")
            else:
                print(f"    ⚠️  No map button found — using DOM scan")

            maps = page.evaluate("""
                () => {
                    var result = { interactive: '', google: '', bing: '' };
                    var mapDiv = document.getElementById('map-links');
                    if (mapDiv) {
                        var links = mapDiv.querySelectorAll('a[href]');
                        for (var a of links) {
                            var txt = (a.innerText || a.textContent || '').trim().toLowerCase();
                            var href = a.href || '';
                            if (!href || href.startsWith('javascript')) continue;
                            if (txt.includes('interactive') || /gis\\./i.test(href) || /bisclient/i.test(href)) {
                                result.interactive = href;
                            } else if (txt.includes('google') || /maps\\.google/i.test(href)) {
                                result.google = href;
                            } else if (txt.includes('bing') || /bing\\.com\\/maps/i.test(href)) {
                                result.bing = href;
                            }
                        }
                    }
                    if (!result.google && !result.interactive) {
                        var all = [...document.querySelectorAll('a[href]')];
                        for (var a of all) {
                            var href = a.href || '';
                            var txt  = (a.innerText || a.textContent || '').trim().toLowerCase();
                            if (!href.startsWith('http')) continue;
                            if (/gis\\./i.test(href) || /bisclient/i.test(href) || /arcgis/i.test(href)) {
                                result.interactive = result.interactive || href;
                            }
                            if (/maps\\.google/i.test(href) || txt.includes('google maps')) {
                                result.google = result.google || href;
                            }
                            if (/bing\\.com\\/maps/i.test(href) || txt.includes('bing maps')) {
                                result.bing = result.bing || href;
                            }
                        }
                    }
                    return result;
                }
            """)
            interactive_map = maps.get("interactive", "")
            google_maps_url = maps.get("google", "") or maps.get("bing", "")
            property_map    = google_maps_url or interactive_map
            if interactive_map:
                print(f"    🗺️  Interactive Map: {interactive_map[:80]}")
            if google_maps_url:
                print(f"    🗺️  Google/Bing Map: {google_maps_url[:80]}")
        except Exception as e:
            print(f"    ⚠️  Map capture error: {e}")

    if not google_maps_url and address:
        google_maps_url = build_google_maps_url(address)
        property_map    = google_maps_url
        print(f"    🗺️  Google Maps (built from address): {google_maps_url[:80]}")

    zillow_url = build_zillow_url(address)
    if zillow_url:
        print(f"    🏡 Zillow: {zillow_url[:80]}")

    prop_id_m  = re.search(r'/Property/View/(\d+)', url, re.IGNORECASE)
    owner_id_m = re.search(r'[?&]ownerId=(\w+)', url)
    host_m     = re.search(r'(https?://[^/]+)', url)
    canonical_url = url
    if prop_id_m and owner_id_m and host_m:
        canonical_url = (
            f"{host_m.group(1)}"
            f"/Property/View/{prop_id_m.group(1)}"
            f"?year={CURRENT_YEAR}&ownerId={owner_id_m.group(1)}"
        )
        print(f"    🔗 Canonical: {canonical_url[:80]}")

    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         canonical_url,
        "Property Map":               property_map,
        "Interactive Map":            interactive_map,
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        ag_market,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ESEARCH PROPERTY SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_esearch_property(page, base_url, account_number, county):
    """
    Search an esearch-style CAD portal.
    Geo-id counties (nueces, wilson, galveston, hardin): account_number IS the geo id.
    All others: plain numeric account number.
    """
    print(f"    🔍 Searching {county.upper()} (esearch): {account_number}")

    # kaufman-cad.org has a very slow, occasionally flaky server (~10s+ TTFB,
    # sometimes 40s+ to domcontentloaded, and it can time out entirely on a
    # given attempt) — retry the initial load a couple of times before giving up.
    for attempt in range(3):
        try:
            page.goto(base_url, timeout=60000, wait_until="domcontentloaded")
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"    🔄 {county.upper()} homepage load attempt {attempt + 1} failed, retrying: {e}")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    if county in SKIP_BYID_TAB_COUNTIES:
        print(f"    ℹ️  Skipping 'By ID' tab for {county} — using default Search box")
    else:
        by_id_tab = page.locator(
            "a[data-filter='search-id'], a[data-filter*='id'], "
            "a:has-text('By ID'), button:has-text('By ID')"
        )
        if by_id_tab.count() > 0:
            by_id_tab.first.click()
            page.wait_for_timeout(700)
            print(f"    🔘 By ID tab clicked")
        else:
            print(f"    ℹ️  No By ID tab found")

    if county in KEEP_R_PREFIX_COUNTIES:
        clean_account = account_number.strip()
    else:
        clean_account = re.sub(r'^[Rr][Cc]?', '', account_number).strip()
        if clean_account != account_number:
            print(f"    ✂️  Stripped R/RC prefix: {account_number} → {clean_account}")

    if county in GEO_ID_COUNTIES:
        if county == "hardin":
            geo_id = format_geo_id_hardin(clean_account)
        elif county == "galveston":
            geo_id = format_geo_id_galveston(clean_account)
        elif county == "nueces":
            geo_id = format_geo_id_nueces(clean_account)
        elif county == "wilson":
            geo_id = format_geo_id_wilson(clean_account)
        elif county == "brooks":
            geo_id = format_geo_id_brooks(clean_account)
        elif county == "cass":
            geo_id = format_geo_id_cass(clean_account)
        elif county == "rains":
            geo_id = format_geo_id_rains(clean_account)
        else:
            geo_id = clean_account
        print(f"    🗺️  Geo ID → input: {geo_id}")

        geo_input_id = page.evaluate("""
            () => {
                var labels = [...document.querySelectorAll('label')];
                for (var lbl of labels) {
                    if (/geographic/i.test(lbl.innerText || lbl.textContent || '')) {
                        var f = lbl.getAttribute('for');
                        if (f) return f;
                    }
                }
                return '';
            }
        """)
        if geo_input_id:
            target_input = page.locator(f"#{geo_input_id}")
            print(f"    🔎 Geo input by label[for=#{geo_input_id}]")
        else:
            all_inputs = page.locator("#search-id input[type='text'], input[type='text']")
            visible = [all_inputs.nth(i) for i in range(all_inputs.count()) if all_inputs.nth(i).is_visible()]
            target_input = visible[1] if len(visible) >= 2 else (visible[0] if visible else None)
            print(f"    🔎 Geo input: 2nd visible fallback")

        if target_input is None:
            print(f"    ⚠️  No Geographic ID input found")
            return None
        target_input.clear()
        target_input.fill(geo_id)

    else:
        all_inputs = page.locator(
            "#search-id input[type='text'], "
            "input[name='prop_id'], input[id='prop_id'], "
            "input[placeholder*='id' i], input[placeholder*='account' i], "
            "input[type='text']"
        )
        visible = [all_inputs.nth(i) for i in range(all_inputs.count()) if all_inputs.nth(i).is_visible()]
        if not visible:
            print(f"    ⚠️  No visible input found")
            return None
        visible[0].fill(clean_account)

    page.wait_for_timeout(300)

    submit_btn = page.locator(
        "button[onclick*='AdvancedSearch'], button[onclick*='Search'], "
        "button[value='Search'], button[type='submit'], "
        "input[type='submit'], button:has-text('Search')"
    )
    clicked = False
    for i in range(submit_btn.count()):
        el = submit_btn.nth(i)
        if el.is_visible():
            el.click()
            clicked = True
            print(f"    🖱️  Search button clicked")
            break
    if not clicked:
        page.keyboard.press("Enter")
        print(f"    ⌨️  Enter pressed (no visible Search button)")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    if "/Property/View/" in page.url:
        print(f"    ✅ Auto-navigated to detail: {page.url[:80]}")
        return _extract_esearch_detail(page.inner_text("body"), page.url, page)

    try:
        # Some portals (e.g. kaufman-cad.org) navigate to a full results page
        # server-side rather than loading the table via fast AJAX, and that
        # navigation alone can take 15-30s — 8s was too short and made the
        # scraper give up before the list ever rendered.
        page.wait_for_selector("tbody#resultListDiv tr[onclick]", timeout=45000)
    except Exception:
        link = page.locator("a[href*='/Property/View/'], a[href*='/Details/']")
        if link.count() > 0:
            link.first.click()
            print(f"    🖱️  Clicked <a> result link (fallback)")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1000)
            if "/Property/View/" in page.url:
                return _extract_esearch_detail(page.inner_text("body"), page.url, page)
        print(f"    ⚠️  No results found for: {account_number} ({county})")
        return None

    result_row = page.locator("tbody#resultListDiv tr[onclick]").first
    try:
        with page.expect_navigation(timeout=45000):
            result_row.click()
        print(f"    🖱️  Clicked result row → navigating")
    except Exception as nav_err:
        print(f"    ⚠️  expect_navigation timeout ({nav_err}) — checking URL anyway")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    if "/Property/View/" in page.url:
        print(f"    ✅ Detail page loaded: {page.url[:80]}")
        return _extract_esearch_detail(page.inner_text("body"), page.url, page)

    print(f"    ❌ Failed to reach detail page. Current URL: {page.url}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# BIS PROPERTY SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_bis_property(page, base_url, account_number, county):
    search_url = f"{base_url}/Property/Search"
    print(f"    🔍 Searching {county.upper()} CAD (BIS): {account_number}")
    page.goto(search_url, timeout=30000)
    page.wait_for_load_state("domcontentloaded")

    acct_input = page.locator(
        "input[placeholder*='account' i], input[name*='account' i], "
        "input[id*='account' i], input[type='search']"
    )
    if acct_input.count() == 0:
        print(f"    ⚠️  No search input found at {search_url}")
        return None

    acct_input.first.fill(account_number)
    page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    result_link = page.locator("a[href*='/Property/View/']")
    if result_link.count() == 0:
        print(f"    ⚠️  No results for account {account_number} ({county})")
        return None

    result_link.first.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    text      = page.inner_text("body")
    final_url = page.url
    return _extract_bis_detail(text, final_url, account_number, page)


# ═══════════════════════════════════════════════════════════════════════════
# STEPHENS CAD — SOUTHWEST DATA SOLUTIONS (SPA portal)
# URL: https://stephenscad.southwestdatasolutions.com/PropertySearch
# Account format: R######  (e.g. R000015326)
# Steps: click "Property ID" chip → type account → Search → click result row
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_stephens_property(page, account_number):
    clean = account_number.strip()
    print(f"    🔍 Stephens account: {clean}")

    try:
        page.goto(STEPHENS_SEARCH_URL, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")

        # Wait for the main search box to be visible (SPA may still be rendering)
        # Stephens CAD search box has placeholder="Search"
        search_input = page.locator("input[placeholder='Search']")
        try:
            search_input.wait_for(state="visible", timeout=15000)
            print(f"    ✅ Search page ready")
        except Exception:
            print(f"    ⚠️  Search input not visible — retrying once")
            page.reload()
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            try:
                search_input.wait_for(state="visible", timeout=15000)
            except Exception:
                print(f"    ❌ Stephens: search page did not load")
                return None

        search_input.click()
        search_input.fill(clean)
        print(f"    ✏️  Entered: {clean}")
        page.wait_for_timeout(400)

        # Click the blue Search button next to the input
        search_btn = page.locator("button:has-text('Search')")
        try:
            search_btn.wait_for(state="visible", timeout=5000)
            search_btn.click()
            print(f"    🖱️  Search clicked")
        except Exception:
            search_input.press("Enter")
            print(f"    ⌨️  Enter pressed")

        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # Wait for at least one result row to appear
        try:
            page.wait_for_selector("tbody tr", timeout=8000)
        except Exception:
            print(f"    ⚠️  Stephens: results table did not appear for: {clean}")
            return None

        # Try 1: click a link that contains the account number (e.g. R000015326)
        clicked_row = False
        acct_link = page.locator(f"a:has-text('{clean}'), td:has-text('{clean}')")
        if acct_link.count() > 0:
            try:
                acct_link.first.click()
                clicked_row = True
                print(f"    🖱️  Clicked account cell: {clean}")
            except Exception as e:
                print(f"    ⚠️  Account cell click failed: {e}")

        # Try 2: click first tbody tr that is NOT the header (skip rows with filter icons)
        if not clicked_row:
            rows = page.locator("tbody tr")
            for i in range(min(rows.count(), 15)):
                row_el = rows.nth(i)
                row_text = ""
                try:
                    row_text = (row_el.inner_text() or "").strip()
                except Exception:
                    continue
                # Skip header-like rows (contain "Property Id" or have very short text)
                if not row_text or len(row_text) < 5:
                    continue
                if re.search(r'\bProperty\s+Id\b|\bOwner\s+Name\b|\bGeo\s+Id\b', row_text, re.IGNORECASE):
                    continue
                try:
                    row_el.click()
                    clicked_row = True
                    print(f"    🖱️  Clicked result row: {row_text[:60]}")
                    break
                except Exception as e:
                    print(f"    ⚠️  Row {i} click failed: {e}")

        if not clicked_row:
            print(f"    ⚠️  No result row found for: {clean}")
            return None

        # Wait for URL to change away from search page (SPA navigation)
        try:
            page.wait_for_url(
                lambda url: "PropertySearch" not in url and "PropertyView" in url,
                timeout=10000
            )
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        # Also wait for PROPERTY VIEW heading to confirm detail page is loaded
        try:
            page.wait_for_selector("text=PROPERTY VIEW", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        # Build direct CAD detail URL from account number — more reliable than page.url
        final_url = f"https://stephenscad.southwestdatasolutions.com/PropertyView?propertyId={clean}"
        # Use actual page URL if it landed on PropertyView
        actual_url = page.url
        if "PropertyView" in actual_url:
            final_url = actual_url
        print(f"    🔗 Detail URL: {final_url}")
        text = page.inner_text("body")

        # ── Owner ─────────────────────────────────────────────────────────────
        # Page layout: "OWNERSHIP\n\nREYES SERGIO & OLGA\n3696 CR 263\nBRECKENRIDGE, TX 76424"
        owner = ""
        own_m = re.search(r'OWNERSHIP\s*\n+([A-Z][A-Z &\-]+)\n', text)
        if own_m:
            owner = own_m.group(1).strip()
        if not owner:
            # fallback: any all-caps name line after OWNERSHIP heading
            own_m2 = re.search(r'OWNERSHIP[\s\S]{0,50}?\n([A-Z][A-Z &\-]{3,60})\n', text)
            if own_m2:
                owner = own_m2.group(1).strip()
        if not owner:
            # generic fallback
            om = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
            if om:
                owner = om.group(1).strip()
                owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', owner)[0].strip()
                if len(owner) < 3:
                    owner = ""
        if owner:
            print(f"    👤 Stephens owner: {owner}")

        # ── Address — SITUS only ──────────────────────────────────────────────
        # "Situs: Situs 1410 W WALKER Map Number: CITY"
        # Owner mailing address is IGNORED (owner may live in another city).
        # Stephens County → Breckenridge, TX 76424
        address = ""

        situs_m = re.search(
            r'Situs[:\s]+(?:Situs\s+)?([^\n]+?)(?:\s+Map\s+Number|\s*$)',
            text, re.IGNORECASE | re.MULTILINE
        )
        if situs_m:
            situs_street = situs_m.group(1).strip()
            situs_street = re.sub(r'^Situs\s*', '', situs_street, flags=re.IGNORECASE).strip()
            situs_street = situs_street.lstrip(':').strip()
            if situs_street:
                address = situs_street

        if address:
            print(f"    🏠 Stephens situs address: {address}")

        # ── Values from PROPERTY VALUE HISTORY table ──────────────────────────
        # Stephens layout:  Improvements | Land | Total Market | Total Assessed
        def _tval(label):
            m = re.search(label + r'\s+\$?([\d,]+)', text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        # Adjusted Value = Total Assessed (user requirement)
        market_value = _tval(r'Total\s+Assessed')
        if not market_value:
            market_value = _tval(r'Total\s+Market')
        if not market_value:
            market_value = extract_market_value(text)
        if market_value:
            print(f"    💰 Stephens Total Assessed: {market_value}")

        # Map Stephens table rows to existing sheet columns
        imp_homesite     = _tval(r'Improvements')          # Improvements → Improvement Homesite
        imp_nonhomesite  = ""                               # no equivalent
        land_homesite    = _tval(r'Land')                  # Land → Land Homesite
        land_nonhomesite = ""                               # no equivalent
        ag_market        = _tval(r'Production\s+Market')   # Production Market → Ag Market

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        property_map    = google_maps_url
        interactive_map = f"https://gis.bisclient.com/STEPHENSCAD/?find={clean}"

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")
        print(f"    🗺️  Interactive Map: {interactive_map}")
        print(f"    🔗 Canonical: {final_url}")

        realtor_url = build_realtor_search_url(address)

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            interactive_map,
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Stephens scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WILLIAMSON CAD — WCAD PORTAL
# URL: https://search.wcad.org/Property-Detail/PropertyQuickRefID/{account}
# Account format: R###### (e.g. R509650)
# Collects: Owner, Property Address, VALUE HISTORY (most recent year),
#           Market Data Map link → Interactive Map
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_williamson_property(page, account_number):
    clean = account_number.strip()
    print(f"    🔍 Williamson account: {clean}")

    direct_url = f"{WILLIAMSON_DETAIL_BASE}/{clean}"

    try:
        print(f"    🌐 Navigating to: {direct_url}")
        page.goto(direct_url, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        body_text = page.inner_text("body")
        if re.search(r'not found|404|no property|no record', body_text, re.IGNORECASE):
            print(f"    ❌ Williamson: property not found: {clean}")
            return None

        # Build the canonical URL with both PropertyQuickRefID and PartyQuickRefID
        # WCAD may redirect and include PartyQuickRefID in the URL automatically
        final_url = page.url
        if "PartyQuickRefID" not in final_url:
            try:
                party_id = page.evaluate("""
                    () => {
                        // Check the current URL first (after any redirect)
                        var m = window.location.href.match(/PartyQuickRefID\\/([^\\/\\?#]+)/i);
                        if (m) return m[1];
                        // Look for any <a> or link on page containing PartyQuickRefID
                        for (var a of document.querySelectorAll('a[href*="PartyQuickRefID"]')) {
                            var m2 = a.href.match(/PartyQuickRefID\\/([^\\/\\?#]+)/i);
                            if (m2) return m2[1];
                        }
                        return '';
                    }
                """)
                if party_id:
                    final_url = (
                        f"https://search.wcad.org/Property-Detail"
                        f"/PropertyQuickRefID/{clean}/PartyQuickRefID/{party_id}"
                    )
            except Exception as e:
                print(f"    ⚠️  PartyQuickRefID extraction error: {e}")
        print(f"    ✅ Landed on: {final_url[:100]}")

        # ── Owner — from "OWNER INFORMATION" section (tab-separated label:value) ─
        owner = ""
        owner_m = re.search(r'Owner Name\s*\t\s*([^\n\t]+)', body_text, re.IGNORECASE)
        if owner_m:
            owner = owner_m.group(1).strip()
        if not owner:
            om2 = re.search(r'Owner(?:\s+Name)?[:\s]+([A-Z][^\n]{2,80})', body_text, re.IGNORECASE)
            if om2:
                owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', om2.group(1))[0].strip()
                if len(owner) < 3:
                    owner = ""
        if owner:
            print(f"    👤 Williamson owner: {owner}")

        # ── Address — TX zip pattern in the header area (before VALUE HISTORY) ──
        address = ""
        vh_pos = body_text.upper().find("VALUE HISTORY")
        header_text = body_text[:vh_pos] if vh_pos > 0 else body_text[:5000]
        addr_m = re.search(r'\d+\s+[A-Z0-9][^\n,]+,\s*[A-Z][^\n,]+,\s*TX\s+\d{5}', header_text, re.IGNORECASE)
        if addr_m:
            address = addr_m.group(0).strip()
        if address:
            print(f"    🏠 Williamson address: {address}")

        # ── Scroll so lazy-loaded VALUE HISTORY renders ──────────────────────
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
        body_text = page.inner_text("body")

        # ── VALUE HISTORY — regex on inner_text ─────────────────────────────
        # WCAD inner_text renders the table with each cell on its own line:
        # VALUE HISTORY\n\nYEAR\nIMPROVEMENT\nLAND\nMARKET\n...ASSESSED\n
        # 2025\n$354,720\n$101,500\n$456,220\n$0\n...\n$456,220\n
        vh_m = re.search(
            r'VALUE\s+HISTORY\s+'
            r'YEAR\s+IMPROVEMENT\s+LAND\s+MARKET\s+AG\s+MARKET\s+AG\s+USE\s+'
            r'TIM\s+MARKET\s+TIM\s+USE\s+APPRAISED\s+HS\s+CAP\s+LOSS\s+CBL\s+CAP\s+LOSS\s+ASSESSED\s+'
            r'(\d{4})\s+'          # group 1 — YEAR
            r'\$([\d,]+)\s+'       # group 2 — IMPROVEMENT
            r'\$([\d,]+)\s+'       # group 3 — LAND
            r'\$([\d,]+)\s+'       # group 4 — MARKET
            r'\$([\d,]+)\s+'       # group 5 — AG MARKET
            r'\$([\d,]+)\s+'       # group 6 — AG USE
            r'\$([\d,]+)\s+'       # group 7 — TIM MARKET
            r'\$([\d,]+)\s+'       # group 8 — TIM USE
            r'\$([\d,]+)\s+'       # group 9 — APPRAISED
            r'\$([\d,]+)\s+'       # group 10 — HS CAP LOSS
            r'\$([\d,]+)\s+'       # group 11 — CBL CAP LOSS
            r'\$([\d,]+)',          # group 12 — ASSESSED
            body_text, re.IGNORECASE
        )

        def _dollar(raw):
            if not raw:
                return ""
            cleaned = raw.replace(",", "").replace("$", "").strip()
            try:
                return f"${int(cleaned):,}" if cleaned else ""
            except Exception:
                return ""

        market_value  = ""
        imp_homesite  = ""
        land_homesite = ""

        if vh_m:
            year        = vh_m.group(1)
            mkt_raw     = vh_m.group(4).replace(",", "")
            assessed_raw= vh_m.group(12).replace(",", "")
            print(f"    📊 VALUE HISTORY {year}: Market=${mkt_raw}, Assessed=${assessed_raw}")

            # MARKET first; if $0 fallback to ASSESSED
            market_value  = _dollar(mkt_raw) if mkt_raw and mkt_raw != "0" else _dollar(assessed_raw)
            imp_homesite  = _dollar(vh_m.group(2))
            land_homesite = _dollar(vh_m.group(3))
        else:
            # Final fallback: generic market value extractor on full body
            market_value = extract_market_value(body_text)
            print(f"    ⚠️  VALUE HISTORY regex not matched — using text fallback")

        if market_value:
            print(f"    💰 Williamson Adjusted Value: {market_value}")

        # ── Market Data Map link → Interactive Map ───────────────────────────
        interactive_map = ""
        try:
            map_href = page.evaluate("""
                () => {
                    // Find "Market Data Map" anchor by text content
                    for (var a of document.querySelectorAll('a')) {
                        var txt = (a.innerText || a.textContent || '').trim();
                        if (/market data map/i.test(txt)) {
                            return a.href || '';
                        }
                    }
                    // Also check title/aria-label attributes
                    var els = [...document.querySelectorAll('[title*="Market Data Map" i], [aria-label*="Market Data Map" i]')];
                    if (els.length) {
                        var ca = els[0].tagName === 'A' ? els[0] : els[0].closest('a');
                        if (ca) return ca.href || '';
                    }
                    return '';
                }
            """)
            if map_href:
                # Resolve relative URLs
                if map_href.startswith("/"):
                    map_href = "https://search.wcad.org" + map_href
                if map_href.startswith("http"):
                    interactive_map = map_href
                    print(f"    🗺️  Market Data Map: {interactive_map[:100]}")
        except Exception as e:
            print(f"    ⚠️  Market Data Map link error: {e}")

        # ── Build listing links ──────────────────────────────────────────────
        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""
        property_map    = google_maps_url

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")
        print(f"    🔗 Canonical: {final_url}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            interactive_map,
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        "",
        }

    except Exception as e:
        print(f"    ❌ Williamson scrape error: {e}")
        import traceback; traceback.print_exc()
        return None

# ═══════════════════════════════════════════════════════════════════════════
# JACKSON CAD — esearch.jacksoncad.org
# Search: /Property-Search-Result/searchtext/{account}
# Detail: /Property-Detail/PropertyQuickRefID/{id}/PartyQuickRefID/{party}
# ═══════════════════════════════════════════════════════════════════════════

JACKSON_BASE_URL   = "https://esearch.jacksoncad.org"
JACKSON_SEARCH_URL = "https://esearch.jacksoncad.org/Property-Search-Result/searchtext"


def _scrape_jackson_property(page, account_number):
    clean = account_number.strip()
    print(f"    🔍 Jackson account: {clean}")

    search_url = f"{JACKSON_SEARCH_URL}/{clean}"
    print(f"    🌐 Searching: {search_url}")

    try:
        page.goto(search_url, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # The result grid is a Kendo grid with no real <a href> or onclick
        # attribute on its rows (navigation happens via a JS click handler
        # bound to the row) — so we have to actually click it rather than
        # scrape a link out of the DOM.
        row = page.locator(f'tr[data-uid] td:has-text("{clean}")').first
        if row.count() == 0:
            print(f"    ❌ Jackson: no result row found for {clean}")
            return None
        row.click(timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        final_url = page.url
        print(f"    ✅ Loaded: {final_url[:100]}")

        body_text = page.inner_text("body")

        if re.search(r'not found|404|no property|no record', body_text, re.IGNORECASE):
            print(f"    ❌ Jackson: property not found: {clean}")
            return None

        # Owner — the summary card's owner name lives in a stable-suffixed
        # div (id like dnn_ctr364_View_divOwnersLabel); the module instance
        # number in the middle varies, so match on the id suffix.
        owner = ""
        owner_el = page.locator('[id$="_View_divOwnersLabel"]').first
        if owner_el.count() > 0:
            owner = (owner_el.inner_text() or "").strip()
        if not owner:
            owner_m = re.search(r'Owner\s+Name\s*\t\s*([^\n\t]+)', body_text, re.IGNORECASE)
            if owner_m:
                owner = owner_m.group(1).strip()
        if owner:
            print(f"    👤 Jackson owner: {owner}")

        # Situs / Property Address — same story: summary card cell id
        # dnn_ctr364_View_tdPropertyAddress (module id varies).
        address = ""
        addr_el = page.locator('[id$="_View_tdPropertyAddress"]').first
        if addr_el.count() > 0:
            address = (addr_el.inner_text() or "").strip()
            address = re.sub(r'^Property\s+Address:\s*', '', address, flags=re.IGNORECASE).strip()
        if not address:
            m = re.search(r'Situs\s+Address[:\s]+([^\n]{5,100})', body_text, re.IGNORECASE)
            if m:
                address = m.group(1).strip().rstrip(',')
        if address and not re.search(r'TX|Texas', address, re.IGNORECASE):
            address = address + ', TX'
        if address:
            print(f"    🏠 Jackson address: {address}")

        # Assessed / Market value
        market_value = ""
        val_m = re.search(r'\d{4}\s+Assessed\s+Value\s*[\n\t\s]+\$([\d,]+)', body_text, re.IGNORECASE)
        if val_m:
            raw = val_m.group(1).replace(',', '')
            try:
                market_value = f"${int(raw):,}"
            except Exception:
                pass
        if not market_value:
            market_value = extract_market_value(body_text)
        if market_value:
            print(f"    💰 Jackson value: {market_value}")

        def _val(label):
            m = re.search(label + r'[\s\t:]+\$?([\d,]+)', body_text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite     = _val(r'Improvement\s+Homesite\s+Value')
        imp_nonhomesite  = _val(r'Improvement\s+Non-?Homesite\s+(?:Value)?')
        land_homesite    = _val(r'Land\s+Homesite\s+Value')
        land_nonhomesite = _val(r'Land\s+Non-?Homesite\s+Value')
        ag_market        = _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               google_maps_url,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Jackson scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# DALLAS CAD — DIRECT URL SCRAPER
# URL: https://www.dallascad.org/AcctDetailRes.aspx?ID={account_number}
# NOTE: "Adjusted Value" is intentionally left blank so the existing
#       sheriff-sale value is never overwritten.
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_dallas_property(page, account_number):
    clean = account_number.strip()
    url   = f"{DALLAS_CAD_DETAIL_URL}?ID={clean}"
    print(f"    🔍 Dallas CAD account: {clean}")
    print(f"    🌐 {url}")

    try:
        page.goto(url, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        body = page.inner_text("body")

        if re.search(r'no record|not found|invalid account|error loading', body, re.IGNORECASE):
            print(f"    ❌ Dallas CAD: no data for {clean}")
            return None

        # ── Query the exact span IDs that Dallas CAD uses for values ──────────
        # Confirmed from page DevTools:
        #   ValueSummary1_lblImpVal          → Improvement  e.g. "$0"
        #   ValueSummary1_pnlValue_lblLandVal → Land         e.g. "$10,730"
        #   ValueSummary1_pnlValue_lblTotalVal→ Market Value e.g. "$10,730"
        vals = page.evaluate("""
            () => {
                function txt(id) {
                    var el = document.getElementById(id);
                    return el ? (el.innerText || '').replace(/[^0-9]/g, '') : '';
                }
                return {
                    improvement: txt('ValueSummary1_lblImpVal'),
                    land:        txt('ValueSummary1_pnlValue_lblLandVal'),
                    market:      txt('ValueSummary1_pnlValue_lblTotalVal')
                };
            }
        """)

        def _fmt(raw):
            s = str(raw or '').strip()
            try:
                return f"${int(s):,}" if s else ""
            except Exception:
                return ""

        improvement  = _fmt(vals.get('improvement', ''))
        land         = _fmt(vals.get('land', ''))
        market_value = _fmt(vals.get('market', ''))

        if improvement:
            print(f"    🏗️  Improvement: {improvement}")
        if land:
            print(f"    🌿 Land: {land}")
        if market_value:
            print(f"    💰 Market Value: {market_value}")

        # Property address — "Address:" label inside Property Location section
        address = ""
        addr_el = page.evaluate("""
            () => {
                var els = [...document.querySelectorAll('span, td, div')];
                for (var el of els) {
                    var t = (el.innerText || '').trim();
                    if (/^Address:/i.test(t)) {
                        return t.replace(/^Address:/i, '').trim();
                    }
                }
                return '';
            }
        """)
        if addr_el and len(addr_el) > 4:
            address = addr_el.strip()
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, re.IGNORECASE).strip()
        if address:
            print(f"    🏠 Address: {address}")

        # Owner name — read the text node right after span#lblOwner, up to its
        # first <br>. A body-text regex isn't safe here: the page also has a
        # "Multi-Owner" table with an "Owner Name | Ownership %" header row,
        # and a naive "Owner...[ \t:]+(...)" regex matches that header first,
        # capturing the literal string "Ownership %" as the owner.
        owner = ""
        try:
            owner = (page.evaluate("""
                () => {
                    var lbl = document.getElementById('lblOwner');
                    if (!lbl) return '';
                    var node = lbl.nextSibling;
                    var text = '';
                    while (node) {
                        if (node.nodeType === 1 && node.tagName === 'BR') break;
                        if (node.nodeType === 3) text += node.textContent;
                        node = node.nextSibling;
                    }
                    return text.trim();
                }
            """) or "").strip()
        except Exception:
            owner = ""
        if not owner:
            m = re.search(r'Owner\s*\(Current\s*\d{4}\)\s*\n\s*([A-Z][^\n]{2,80})', body)
            if m:
                owner = m.group(1).strip()
        if owner:
            print(f"    👤 Owner: {owner}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        print(f"    🔗 Appraisal District: {url}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             "",        # never overwrite sheriff-sale value
            "Appraisal District":         url,
            "Property Map":               google_maps_url,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Improvement Homesite Value": improvement,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        "",
        }

    except Exception as e:
        print(f"    ❌ Dallas scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# CAMERON CAD — cameron.prodigycad.com (ProdigyCAD portal)
# Cameron migrated off the old Angular Material site; cameroncad.org now just
# embeds this domain in an <iframe>, so we hit it directly instead.
# Search type: Geographic ID (typed into the single "compound" search box)
# Account format: 16-digit numeric  →  XX-XXXX-XXXX-XXXX-XX
# Steps: open search page → type GEO ID into #searchInput → click search
#        → intercept the /public/property/search JSON response (it already
#          contains owner/address/value — no need to open the detail page,
#          whose sub-API calls (general/value/land/...) are CORS/rate-limit
#          flaky when hit directly).
# ═══════════════════════════════════════════════════════════════════════════

def format_geo_id_cameron(account_number):
    """Convert 16-digit Cameron account number to GEO ID with dashes.

    Example: 9712200090016000  ->  97-1220-0090-0160-00
    """
    an = re.sub(r'\D', '', account_number).zfill(16)
    return f"{an[0:2]}-{an[2:6]}-{an[6:10]}-{an[10:14]}-{an[14:16]}"


def _scrape_cameron_property(page, account_number):
    geo_id = format_geo_id_cameron(account_number)
    print(f"    🔍 Cameron account: {account_number} → GEO ID: {geo_id}")

    try:
        page.goto(CAMERON_SEARCH_URL, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")

        search_input = page.locator("#searchInput")
        search_input.wait_for(state="visible", timeout=15000)
        search_input.click()
        search_input.fill(geo_id)
        page.wait_for_timeout(300)
        print(f"    ✏️  GEO ID entered: {geo_id}")

        search_btn = page.locator("button[aria-label='Search properties']").first
        try:
            with page.expect_response(
                lambda r: "public/property/search" in r.url, timeout=20000
            ) as resp_info:
                search_btn.click()
            data = resp_info.value.json()
        except Exception as e:
            print(f"    ⚠️  Cameron search request failed: {e}")
            return None

        results = data.get("results") or []
        if not results:
            print(f"    ⚠️  No results for GEO ID: {geo_id}")
            return None

        rec = sorted(results, key=lambda r: r.get("pYear", ""))[-1]

        # Click the PropID link to open the detail page. The detail page's
        # own value/general-info widgets are currently CORS-broken on
        # Cameron's side (confirmed even via the official cameroncad.org
        # embed), so the data below is still taken from the search response
        # above rather than re-scraped from this page — this click is just
        # to land on the record's own detail URL / leave the browser there.
        try:
            prop_link = page.get_by_role("link", name=str(rec.get("pid") or ""), exact=True)
            if prop_link.count() == 0:
                prop_link = page.locator(".ag-row").first
            prop_link.first.click()
            page.wait_for_timeout(1500)
            print(f"    🖱️  Opened PropID: {rec.get('pid')}")
        except Exception as e:
            print(f"    ⚠️  Could not open PropID link: {e}")

        pid   = rec.get("pid")
        pyear = rec.get("pYear")
        owner = (rec.get("displayName") or rec.get("name") or "").strip()

        # fullSitus inconsistently includes a trailing ", TX" and/or zip
        # depending on the parcel — strip it off and re-append uniformly.
        situs = (rec.get("fullSitus") or "").strip()
        situs = re.sub(r',?\s*TX(?:,?\s*\d{5}(?:-\d{4})?)?\s*$', '', situs, flags=re.IGNORECASE)
        situs = situs.strip(', ').strip()
        address = f"{situs}, TX" if situs else ""

        def _money(x):
            try:
                return f"${int(x):,}"
            except (TypeError, ValueError):
                return ""

        val = rec.get("marketValue")
        if val in (None, ""):
            val = rec.get("appraisedValue")
        market_value = _money(val)

        # The detail page's /propertyaccount/{id}/land and /improvement
        # endpoints (which would give the homesite/non-homesite split) are
        # currently CORS-broken on Cameron's own site, even in a real
        # browser hitting the official cameroncad.org embed. The search
        # response only has combined totals, so — matching the Dallas CAD
        # convention above — put the total in the "Homesite" slot and leave
        # "Non-Homesite" blank rather than showing nothing at all.
        land_total = _money(rec.get("landValue"))
        imp_total  = _money(rec.get("improvementValue"))

        detail_url = (
            f"https://cameron.prodigycad.com/property-detail/{pid}/{pyear}"
            if pid else CAMERON_SEARCH_URL
        )
        print(f"    🔗 Detail URL: {detail_url}")

        if address:
            print(f"    🏠 Address: {address}")
        if owner:
            print(f"    👤 Owner: {owner}")
        if market_value:
            print(f"    💰 Value: {market_value}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         detail_url,
            "Property Map":               google_maps_url,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_total,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land_total,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        "",
        }

    except Exception as e:
        print(f"    ❌ Cameron scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# VAL VERDE CAD — valverdecad.org Angular Material portal (same engine as Cameron)
# Search type: Geographic ID
# Account format: 12-digit numeric  →  XXXX-XXXX-XXXX
# Steps: open search page → select Geographic ID from mat-select (or native select)
#        → fill GEO ID → click search → click PropID link → scrape detail
# ═══════════════════════════════════════════════════════════════════════════

def format_geo_id_valverde(account_number):
    """Convert Val Verde account number to Geo ID format XXXX-XXXX-XXXX (4-4-4).

    Example: 631000500180 -> 6310-0050-0180
    """
    an = re.sub(r'\D', '', account_number).zfill(12)
    return f"{an[0:4]}-{an[4:8]}-{an[8:12]}"


def _scrape_valverde_property(page, account_number):
    geo_id = format_geo_id_valverde(account_number)
    print(f"    🔍 Val Verde account: {account_number} → GEO ID: {geo_id}")

    try:
        # Use domcontentloaded (not "load") — avoids timeout waiting for slow resources
        try:
            page.goto(VALVERDE_SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as nav_err:
            print(f"    ⚠️  First nav attempt failed ({nav_err}) — retrying")
            try:
                page.goto(VALVERDE_SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
            except Exception as nav_err2:
                print(f"    ❌ Navigation failed: {nav_err2}")
                return None

        # Wait for the search type combobox to be rendered (React SPA needs time)
        try:
            page.wait_for_selector(
                "[role='combobox'][aria-label='Search type']", timeout=15000
            )
        except Exception:
            print(f"    ⚠️  Search form not ready — retrying page load")
            try:
                page.goto(VALVERDE_SEARCH_URL, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_selector(
                    "[role='combobox'][aria-label='Search type']", timeout=15000
                )
            except Exception:
                print(f"    ❌ Search form failed to load")
                return None

        page.wait_for_timeout(500)

        # Select "Geographic ID" from the search type dropdown
        # Target specifically by aria-label="Search type" to avoid hitting the year dropdown
        selected_geo = False
        try:
            combobox = page.locator("[role='combobox'][aria-label='Search type']")
            current_text = (combobox.inner_text() or "").strip()
            if "Geographic ID" in current_text:
                selected_geo = True
                print(f"    ✅ Geographic ID already selected")
            else:
                combobox.click()
                page.wait_for_timeout(600)
                # Options appear in MUI listbox overlay
                geo_opt = page.locator("[role='listbox'] [role='option']").filter(has_text="Geographic ID")
                if geo_opt.count() == 0:
                    geo_opt = page.locator("[role='option']").filter(has_text="Geographic ID")
                if geo_opt.count() > 0:
                    geo_opt.first.click()
                    selected_geo = True
                    page.wait_for_timeout(400)
                    print(f"    ✅ Selected 'Geographic ID'")
                else:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    print(f"    ⚠️  Geographic ID option not found in listbox")
        except Exception as e:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            print(f"    ⚠️  Dropdown error: {e}")

        if not selected_geo:
            print(f"    ⚠️  Could not select 'Geographic ID' — proceeding anyway")

        # Find the actual search text input.
        # The MUI Select has hidden native inputs (aria-hidden=true, tabindex=-1, class MuiSelect-nativeInput)
        # The real text input has none of these attributes.
        # Try multiple selectors from most specific to least.
        target_input = None
        for sel in [
            "input.MuiInputBase-input:not(.MuiSelect-nativeInput)",
            "input[type='text']:not([aria-hidden='true'])",
            "input:not([aria-hidden='true']):not([tabindex='-1']):not([type='hidden'])",
        ]:
            loc = page.locator(sel)
            try:
                loc.first.wait_for(state="visible", timeout=3000)
                target_input = loc.first
                print(f"    🔎 Text input found via: {sel}")
                break
            except Exception:
                continue

        if target_input is None:
            # Last resort: use JavaScript to find any non-hidden text input
            js_input_found = page.evaluate("""
                () => {
                    var inputs = [...document.querySelectorAll('input')];
                    var good = inputs.find(i =>
                        i.type !== 'hidden' &&
                        !i.getAttribute('aria-hidden') &&
                        i.tabIndex !== -1 &&
                        !i.classList.contains('MuiSelect-nativeInput')
                    );
                    if (good) { good.focus(); return true; }
                    return false;
                }
            """)
            if js_input_found:
                print(f"    🔎 Text input focused via JS")
                page.wait_for_timeout(200)
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                page.keyboard.type(geo_id, delay=50)
                print(f"    ✏️  GEO ID entered via keyboard: {geo_id}")
            else:
                print(f"    ⚠️  Search text input not found — skipping")
                return None
        else:
            # Use force=True to bypass any intercepting overlays
            target_input.click(force=True)
            page.wait_for_timeout(200)
            target_input.press("Control+a")
            target_input.press("Delete")
            page.wait_for_timeout(100)
            target_input.press_sequentially(geo_id, delay=50)
            print(f"    ✏️  GEO ID entered: {geo_id}")

        page.wait_for_timeout(500)

        # Click search button — MUI icon button (aria-label="Search properties", no text)
        # Strategy 1: JS .click() — most reliable for MUI buttons
        search_clicked = page.evaluate("""
            () => {
                var btn = document.querySelector('button[aria-label="Search properties"]');
                if (!btn) btn = document.querySelector('button[aria-label*="search" i]');
                if (btn) { btn.click(); return true; }
                return false;
            }
        """)
        if search_clicked:
            print(f"    🖱️  Search button clicked (JS)")
        else:
            # Strategy 2: Playwright force click
            try:
                page.locator("button[aria-label='Search properties']").click(force=True, timeout=5000)
                search_clicked = True
                print(f"    🖱️  Search button clicked (force)")
            except Exception:
                # Strategy 3: Enter on the input
                target_input.press("Enter")
                print(f"    ⌨️  Enter pressed (fallback)")

        # Wait for ag-Grid results to populate — PropID is a <button> inside col-id="pid"
        try:
            page.wait_for_selector('[col-id="pid"] button', timeout=10000)
        except Exception:
            body_text = page.inner_text("body")
            if re.search(r'no rows|no results|no data', body_text, re.IGNORECASE):
                print(f"    ⚠️  No results for GEO ID: {geo_id}")
                return None
            page.wait_for_timeout(3000)

        # Click the PropID button in the first result row
        prop_btn = page.locator('[col-id="pid"] button').first
        if prop_btn.count() == 0:
            print(f"    ⚠️  No PropID button found for GEO ID: {geo_id}")
            return None

        prop_id_text = (prop_btn.inner_text() or "").strip()
        print(f"    🖱️  Clicking PropID button: {prop_id_text}")
        prop_btn.click()

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        final_url = page.url
        print(f"    🔗 Detail URL: {final_url}")

        # Scroll down to ensure CURRENT VALUES section is rendered
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

        text = page.inner_text("body")

        # ── GIS Map — click Maps button → capture GIS Map href ───────────────
        gis_map_url    = ""
        google_map_url = ""
        try:
            maps_btn = page.locator("button:has-text('Maps'), a:has-text('Maps')")
            if maps_btn.count() > 0:
                maps_btn.first.click()
                page.wait_for_timeout(700)
                print(f"    🗺️  Maps dropdown opened")

            gis_href = page.evaluate("""
                () => {
                    var all = [...document.querySelectorAll('a, [role="menuitem"], li, button')];
                    for (var el of all) {
                        var txt = (el.innerText || el.textContent || '').trim();
                        if (/^GIS\s+Map$/i.test(txt)) {
                            if (el.tagName === 'A' && el.href) return el.href;
                            var p = el.closest('a');
                            if (p && p.href) return p.href;
                        }
                    }
                    return '';
                }
            """)
            if gis_href and gis_href.startswith('http'):
                gis_map_url = gis_href
                print(f"    🗺️  GIS Map: {gis_map_url[:100]}")

            gmaps_href = page.evaluate("""
                () => {
                    var all = [...document.querySelectorAll('a, [role="menuitem"], li, button')];
                    for (var el of all) {
                        var txt = (el.innerText || el.textContent || '').trim();
                        if (/^Google\s+Map$/i.test(txt)) {
                            if (el.tagName === 'A' && el.href) return el.href;
                            var p = el.closest('a');
                            if (p && p.href) return p.href;
                        }
                    }
                    return '';
                }
            """)
            if gmaps_href and gmaps_href.startswith('http'):
                google_map_url = gmaps_href
                print(f"    🗺️  Google Map: {google_map_url[:100]}")

            # Close the dropdown by pressing Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception as e:
            print(f"    ⚠️  Maps dropdown error: {e}")

        # ── Extract address and owner from DOM ────────────────────────────────
        scraped = page.evaluate("""
            () => {
                var r = { address: '', owner: '' };
                var allEls = [...document.querySelectorAll('*')];
                for (var el of allEls) {
                    var txt = (el.innerText || '').trim();
                    if (!txt || el.children.length > 3) continue;
                    var lbl = txt.toLowerCase();
                    var next = el.nextElementSibling;
                    var val  = next ? (next.innerText || '').trim() : '';
                    if (!r.address && (lbl === 'situs address' || lbl === 'address' ||
                        lbl.includes('situs'))) {
                        if (val.length > 4) r.address = val;
                    }
                    if (!r.owner && (lbl === 'owner' || lbl === 'owner name')) {
                        if (val.length > 2) r.owner = val;
                    }
                }
                return r;
            }
        """)
        address = scraped.get("address", "").strip().rstrip(",")
        owner   = scraped.get("owner",   "").strip()

        # Regex fallbacks on full page text
        if not address:
            m = re.search(r'(?:Situs\s+Address|Property\s+Address|Address)[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
            address = m.group(1).strip().rstrip(',') if m else ""
        if not owner:
            m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
            if m:
                owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', m.group(1))[0].strip()
                if len(owner) < 3:
                    owner = ""

        if address:
            address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
            print(f"    🏠 Address: {address}")
        if owner:
            print(f"    👤 Owner: {owner}")

        # ── CURRENT VALUES section ────────────────────────────────────────────
        def _dollar(raw):
            raw = re.sub(r'[,$\s]', '', raw)
            return f"${int(raw):,}" if raw.isdigit() else ""

        def _cv(label):
            """Extract a value from the CURRENT VALUES block by label name."""
            m = re.search(
                label + r'\s+([\d,]+)',
                text, re.IGNORECASE
            )
            return _dollar(m.group(1)) if m else ""

        land_homesite    = _cv(r'Land\s+Homesite')
        land_nonhomesite = _cv(r'Land\s+Non-Homesite')
        imp_homesite     = _cv(r'Improvement\s+Homesite')
        imp_nonhomesite  = _cv(r'Improvement\s+Non-Homesite')
        market_value     = _cv(r'Net\s+Appraised') or _cv(r'Appraised') or _cv(r'\bMarket\b')

        if land_homesite:    print(f"    🌿 Land Homesite: {land_homesite}")
        if land_nonhomesite: print(f"    🌿 Land Non-Homesite: {land_nonhomesite}")
        if imp_homesite:     print(f"    🏗️  Imp Homesite: {imp_homesite}")
        if imp_nonhomesite:  print(f"    🏗️  Imp Non-Homesite: {imp_nonhomesite}")
        if market_value:     print(f"    💰 Net Appraised: {market_value}")

        google_maps_url = google_map_url or (build_google_maps_url(address) if address else "")
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""
        interactive_map = gis_map_url
        property_map    = gis_map_url or google_maps_url

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            interactive_map,
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        "",
        }

    except Exception as e:
        print(f"    ❌ Val Verde scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# TOM GREEN CAD — Southwest Data Solutions geo-id portal
# Search: webSearchGeoID.aspx?dbkey=TOMGREENCAD&stype=geoid&sdata={geo_id}&time={ts}
# Detail: webProperty.aspx?dbkey=TOMGREENCAD&...&id={prop_id}
# Geo ID format: XX-XXXXX-XXXX-XXX-XX  (e.g. 16-30900-0072-009-00)
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_tomgreen_property(page, account_number):
    geo_id    = format_geo_id_tomgreen(account_number)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S0")
    search_url = (
        f"{TOMGREEN_SEARCH_BASE}"
        f"?dbkey={TOMGREEN_DBKEY}&stype=geoid&sdata={geo_id}&time={timestamp}#top"
    )
    print(f"    🔍 Tom Green GEO ID: {geo_id}")
    print(f"    🌐 {search_url}")

    try:
        page.goto(search_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # Extract owner name from search results table (col index 3)
        owner = ""
        try:
            owner = page.evaluate("""
                () => {
                    var rows = [...document.querySelectorAll('table tbody tr')];
                    if (!rows.length) rows = [...document.querySelectorAll('table tr')];
                    for (var row of rows) {
                        var cells = row.querySelectorAll('td');
                        if (cells.length >= 4) {
                            var txt = (cells[3].innerText || '').trim();
                            if (txt && txt.length > 2 && !/owner name|geographic|property id/i.test(txt))
                                return txt;
                        }
                    }
                    return '';
                }
            """)
        except Exception:
            pass
        if owner:
            print(f"    👤 Tom Green owner: {owner}")

        # Click "View Property"
        view_link = page.locator("a:has-text('View Property')")
        if view_link.count() == 0:
            print(f"    ❌ Tom Green: no result for GEO ID: {geo_id}")
            return None
        view_link.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        final_url = page.url
        text      = page.inner_text("body")
        print(f"    🔗 Detail: {final_url}")

        # Situs address
        address = ""
        situs_m = re.search(r'Situs[:\s]+([^\n]+)', text, re.IGNORECASE)
        if situs_m:
            address = situs_m.group(1).strip()
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, re.IGNORECASE).strip()
            if address and not re.search(r'\bTX\b', address, re.IGNORECASE):
                address += ', TX'
        if address:
            print(f"    🏠 Tom Green address: {address}")

        # Owner fallback from detail page
        if not owner:
            om = re.search(r'Owner(?:\s+Name)?[:\s]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
            if om:
                owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', om.group(1))[0].strip()
                if len(owner) < 3:
                    owner = ""

        # Values — first $ amount in each row = most recent year (2026)
        def _first_val(label_pat):
            m = re.search(label_pat + r'[\s\S]{0,40}?\$([\d,]+)', text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite  = _first_val(r'Improvements')
        land_homesite = _first_val(r'\bLand\b')
        ag_market     = _first_val(r'Production\s+Market')
        market_value  = _first_val(r'Total\s+Market')
        if not market_value:
            market_value = _first_val(r'Total\s+Assessed')

        if imp_homesite:
            print(f"    🏗️  Improvements: {imp_homesite}")
        if land_homesite:
            print(f"    🌿 Land: {land_homesite}")
        if market_value:
            print(f"    💰 Total Market: {market_value}")

        # Map/GIS link from nav bar
        interactive_map = ""
        try:
            map_href = page.evaluate("""
                () => {
                    for (var a of document.querySelectorAll('a')) {
                        var txt = (a.innerText || a.textContent || '').trim();
                        if (/^Map\\/GIS$/i.test(txt) || /^Map\\s*\\/\\s*GIS$/i.test(txt)) {
                            return a.href || '';
                        }
                    }
                    return '';
                }
            """)
            if map_href and map_href.startswith('http'):
                interactive_map = map_href
                print(f"    🗺️  Map/GIS: {interactive_map[:100]}")
        except Exception as e:
            print(f"    ⚠️  Map/GIS error: {e}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""
        property_map    = google_maps_url

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            interactive_map,
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Tom Green scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# RUNNELS CAD — Southwest Data Solutions portal (Azure Front Door alias)
# Search: webSearchID.aspx?dbkey=RUNNELSCAD&stype=id&sdata={account}&time={ts}
# Same engine/template as Tom Green — results table → "View Property" link →
# detail page with a multi-year "Values by Year" table where the current year
# (2026) is the leftmost/first value in each row.
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_runnels_property(page, account_number):
    account   = account_number.strip()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S0")
    search_url = (
        f"{RUNNELS_SEARCH_BASE}"
        f"?dbkey={RUNNELS_DBKEY}&stype=id&sdata={account}&time={timestamp}#top"
    )
    print(f"    🔍 Runnels Property ID: {account}")
    print(f"    🌐 {search_url}")

    try:
        page.goto(search_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # Extract owner name from the results table by locating the
        # "Owner Name" header cell and reading the same column from the
        # data row beneath it. This page is a legacy ASP.NET layout with
        # tables nested many levels deep inside single <td> cells, so we
        # must use the native (non-recursive) table.rows / row.cells APIs
        # — a querySelectorAll('tr')/('th,td') scan would recurse into
        # nested tables and badly miscount column indexes.
        owner = ""
        try:
            owner = page.evaluate("""
                () => {
                    for (var table of document.querySelectorAll('table')) {
                        var rows = table.rows;
                        if (!rows || rows.length < 2) continue;
                        var headerCells = rows[0].cells;
                        var headerColIdx = -1;
                        for (var j = 0; j < headerCells.length; j++) {
                            if ((headerCells[j].innerText || '').trim().toLowerCase() === 'owner name') {
                                headerColIdx = j; break;
                            }
                        }
                        if (headerColIdx === -1) continue;
                        for (var i = 1; i < rows.length; i++) {
                            var cells = rows[i].cells;
                            if (cells.length > headerColIdx) {
                                var txt = (cells[headerColIdx].innerText || '').trim();
                                if (txt && txt.length > 2) return txt;
                            }
                        }
                    }
                    return '';
                }
            """)
        except Exception:
            pass
        if owner:
            print(f"    👤 Runnels owner: {owner}")

        # Click "View Property"
        view_link = page.locator("a:has-text('View Property')")
        if view_link.count() == 0:
            print(f"    ❌ Runnels: no result for Property ID: {account}")
            return None
        view_link.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)

        final_url = page.url
        text      = page.inner_text("body")
        print(f"    🔗 Detail: {final_url}")

        # Situs address
        address = ""
        situs_m = re.search(r'Situs[:\s]+([^\n]+)', text, re.IGNORECASE)
        if situs_m:
            address = situs_m.group(1).strip()
            address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
            if address and not re.search(r'\bTX\b', address, re.IGNORECASE):
                address += ', TX'
        if address:
            print(f"    🏠 Runnels address: {address}")

        # Owner fallback from detail page
        if not owner:
            om = re.search(r'Owner(?:\s+Name)?[:\s]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
            if om:
                owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', om.group(1))[0].strip()
                if len(owner) < 3:
                    owner = ""

        # Values by Year table lists the current year (2026) as the leftmost
        # column, so the first "$" amount after each row label is 2026's value.
        def _first_val(label_pat):
            m = re.search(label_pat + r'[\s\S]{0,40}?\$([\d,]+)', text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite  = _first_val(r'Improvements')
        land_homesite = _first_val(r'\bLand\b')
        ag_market     = _first_val(r'Production\s+Market')
        market_value  = _first_val(r'Total\s+Market')
        if not market_value:
            market_value = _first_val(r'Total\s+Assessed')

        if imp_homesite:
            print(f"    🏗️  Improvements: {imp_homesite}")
        if land_homesite:
            print(f"    🌿 Land: {land_homesite}")
        if market_value:
            print(f"    💰 Total Market: {market_value}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""
        property_map    = google_maps_url

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               property_map,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Runnels scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# LIMESTONE CAD — Prodigy engine
# URL: https://www.limestonecad.com/property-detail/{id}/{year}
# Account: R18580 → strip R + leading zeros → 18580
# VALUE HISTORY columns: Year|Land Market|Improvement|Special Use Excl|Appraised|Val Lim Adj|Net Appraised
# Maps dropdown → GIS Map link
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_limestone_property(page, account_number):
    clean = re.sub(r'^[Rr]', '', account_number.strip()).lstrip('0') or '0'
    print(f"    🔍 Limestone account: {clean}")

    for year in [CURRENT_YEAR, str(int(CURRENT_YEAR) - 1)]:
        url = f"{LIMESTONE_BASE_URL}/property-detail/{clean}/{year}"
        try:
            print(f"    🌐 Trying: {url}")
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)

            body = page.inner_text("body")
            redirected_home = re.sub(r'/$', '', page.url) in _LIMESTONE_HOME_URLS
            has_error = re.search(r'not found|404|no property|page not found', body, re.IGNORECASE)
            if not redirected_home and not has_error:
                print(f"    ✅ Limestone detail loaded: {page.url[:80]}")
                return _extract_limestone_detail(page, page.url, body)
            print(f"    🔄 {clean}/{year} not found — trying next year")
        except Exception as e:
            print(f"    ⚠️  Limestone load error {clean}/{year}: {e}")

    print(f"    ❌ Limestone property not found: {account_number}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# WHARTON CAD — Prodigy engine
# URL: https://www.whartoncad.net/property-detail/{id}/{year}
# Account: strip leading R + leading zeros (same as Limestone)
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_wharton_property(page, account_number):
    clean = re.sub(r'^[Rr]', '', account_number.strip()).lstrip('0') or '0'
    print(f"    🔍 Wharton account: {clean}")

    for year in [CURRENT_YEAR, str(int(CURRENT_YEAR) - 1)]:
        url = f"{WHARTON_BASE_URL}/property-detail/{clean}/{year}"
        try:
            print(f"    🌐 Trying: {url}")
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)

            body = page.inner_text("body")
            redirected_home = re.sub(r'/$', '', page.url) in _WHARTON_HOME_URLS
            has_error = re.search(r'not found|404|no property|page not found', body, re.IGNORECASE)
            if not redirected_home and not has_error:
                print(f"    ✅ Wharton detail loaded: {page.url[:80]}")
                return _extract_limestone_detail(page, page.url, body)
            print(f"    🔄 {clean}/{year} not found — trying next year")
        except Exception as e:
            print(f"    ⚠️  Wharton load error {clean}/{year}: {e}")

    print(f"    ❌ Wharton property not found: {account_number}")
    return None


def _extract_limestone_detail(page, url, text):
    def _dollar(raw):
        cleaned = re.sub(r'[,$\s]', '', str(raw))
        if not cleaned or cleaned == '0':
            return ""
        try:
            return f"${int(cleaned):,}"
        except Exception:
            return ""

    # ── Owner ─────────────────────────────────────────────────────────────
    owner = ""
    try:
        owner = page.evaluate("""
            () => {
                var els = [...document.querySelectorAll('th, td, dt, label, .label, strong, b')];
                for (var el of els) {
                    var lbl = (el.innerText || '').trim().toLowerCase();
                    if (lbl === 'name' || lbl === 'owner name') {
                        var next = el.nextElementSibling;
                        if (next) return (next.innerText || '').trim();
                        var row = el.closest('tr');
                        if (row) {
                            var tds = row.querySelectorAll('td');
                            if (tds.length >= 2) return (tds[tds.length-1].innerText || '').trim();
                        }
                    }
                }
                return '';
            }
        """)
    except Exception:
        pass
    if not owner:
        om = re.search(r'(?:^|\n)\s*Name[:\s]+([A-Z][^\n]{2,80})', text, re.IGNORECASE | re.MULTILINE)
        if om:
            owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', om.group(1))[0].strip()
            if len(owner) < 3:
                owner = ""
    if owner:
        print(f"    👤 Limestone owner: {owner}")

    # ── Situs Address ──────────────────────────────────────────────────────
    address = ""
    try:
        dom_addr = page.evaluate("""
            () => {
                var els = [...document.querySelectorAll('th, td, dt, label, .label, strong, b')];
                for (var el of els) {
                    var lbl = (el.innerText || '').trim().toLowerCase();
                    if (lbl.includes('situs') || lbl === 'property address' || lbl === 'address') {
                        var next = el.nextElementSibling;
                        if (next) return (next.innerText || '').trim();
                        var row = el.closest('tr');
                        if (row) {
                            var tds = row.querySelectorAll('td');
                            if (tds.length >= 2) return (tds[tds.length-1].innerText || '').trim();
                        }
                    }
                }
                return '';
            }
        """)
        if dom_addr and len(dom_addr) > 4:
            address = dom_addr.strip().rstrip(',')
    except Exception:
        pass
    if not address:
        m = re.search(r'(?:Situs\s+Address|Property\s+Address|Situs)[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
        if m:
            address = m.group(1).strip().rstrip(',')
    if address:
        address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
        address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
        print(f"    🏠 Limestone address: {address}")

    # ── CURRENT VALUES section (plain numbers, no $ sign) ────────────────
    # Labels visible on page: Land Homesite | Land Non-Homesite | Total Land
    #   Improvement Homesite | Improvement Non-Homesite | Total Improvement
    #   Market | Appraised
    def _cv(label):
        """Extract the first plain number that follows a label in the page text."""
        m = re.search(re.escape(label) + r'\s+([\d,]+)', text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}" if raw and raw != '0' else ""
            except Exception:
                return ""
        return ""

    land_homesite    = _cv('Land Homesite')
    land_nonhomesite = _cv('Land Non-Homesite')
    imp_homesite     = _cv('Improvement Homesite')
    imp_nonhomesite  = _cv('Improvement Non-Homesite')
    market_value     = _cv('Appraised') or _cv('Market')

    # Fallback: VALUE HISTORY 2026 row via JavaScript table parsing
    if not (land_homesite or land_nonhomesite or imp_homesite or imp_nonhomesite):
        try:
            vh = page.evaluate("""
                () => {
                    var r = { land:'', imp:'', appraised:'', net:'' };
                    for (var tbl of document.querySelectorAll('table')) {
                        var rows = [...tbl.querySelectorAll('tr')];
                        if (!rows.length) continue;
                        var hdrs = [...rows[0].querySelectorAll('th,td')]
                            .map(h => (h.innerText||'').trim().toLowerCase());
                        if (!hdrs.some(h => h.includes('land market') || h === 'improvement'))
                            continue;
                        var yi = hdrs.findIndex(h => h === 'year');
                        var li = hdrs.findIndex(h => h.includes('land market'));
                        var ii = hdrs.findIndex(h => h === 'improvement');
                        var ai = hdrs.findIndex(h => h === 'appraised');
                        var ni = hdrs.findIndex(h => h.includes('net appraised'));
                        for (var row of rows.slice(1)) {
                            var c = [...row.querySelectorAll('td,th')];
                            var yr = yi >= 0 && c[yi] ? (c[yi].innerText||'').trim()
                                   : c[0] ? (c[0].innerText||'').trim() : '';
                            if (yr !== '2026') continue;
                            r.land      = li >= 0 && c[li] ? (c[li].innerText||'').trim() : '';
                            r.imp       = ii >= 0 && c[ii] ? (c[ii].innerText||'').trim() : '';
                            r.appraised = ai >= 0 && c[ai] ? (c[ai].innerText||'').trim() : '';
                            r.net       = ni >= 0 && c[ni] ? (c[ni].innerText||'').trim() : '';
                            break;
                        }
                        if (r.land || r.imp) break;
                    }
                    return r;
                }
            """)
            land_nonhomesite = land_nonhomesite or _dollar(vh.get('land', ''))
            imp_nonhomesite  = imp_nonhomesite  or _dollar(vh.get('imp', ''))
            market_value     = market_value     or _dollar(vh.get('net', '') or vh.get('appraised', ''))
        except Exception as e:
            print(f"    ⚠️  VALUE HISTORY DOM error: {e}")

    # Last-resort regex on VALUE HISTORY row: 2026  3,960  7,624  0  11,584  0  11,584
    if not (land_nonhomesite or land_homesite):
        vh_m = re.search(
            r'(?:^|\n)\s*2026\s+([\d,]+)\s+([\d,]+)\s+[\d,]+\s+([\d,]+)\s+[\d,]+\s+([\d,]+)',
            text, re.MULTILINE
        )
        if vh_m:
            land_nonhomesite = land_nonhomesite or _dollar(vh_m.group(1))
            imp_nonhomesite  = imp_nonhomesite  or _dollar(vh_m.group(2))
            market_value     = market_value     or _dollar(vh_m.group(4))

    if not market_value:
        market_value = extract_market_value(text)

    if land_homesite:
        print(f"    🌿 Land Homesite: {land_homesite}")
    if land_nonhomesite:
        print(f"    🌿 Land Non-Homesite: {land_nonhomesite}")
    if imp_homesite:
        print(f"    🏗️  Improvement Homesite: {imp_homesite}")
    if imp_nonhomesite:
        print(f"    🏗️  Improvement Non-Homesite: {imp_nonhomesite}")
    if market_value:
        print(f"    💰 Appraised: {market_value}")

    # ── GIS Map — click Maps dropdown → grab "GIS Map" href ───────────────
    interactive_map = ""
    try:
        maps_btn = page.locator(
            "button:has-text('Maps'), a:has-text('Maps'), "
            "[class*='map'] button, nav a:has-text('Maps')"
        )
        if maps_btn.count() > 0:
            maps_btn.first.click()
            page.wait_for_timeout(600)

        gis_href = page.evaluate("""
            () => {
                for (var a of document.querySelectorAll('a, [role="menuitem"], li')) {
                    var txt = (a.innerText || a.textContent || '').trim();
                    if (/^GIS\s+Map$/i.test(txt)) {
                        if (a.tagName === 'A' && a.href) return a.href;
                        var parent = a.closest('a');
                        if (parent && parent.href) return parent.href;
                        var child = a.querySelector('a');
                        if (child && child.href) return child.href;
                    }
                }
                return '';
            }
        """)
        if gis_href and gis_href.startswith('http'):
            interactive_map = gis_href
            print(f"    🗺️  GIS Map: {interactive_map[:100]}")
    except Exception as e:
        print(f"    ⚠️  GIS Map error: {e}")

    # Fallback: Prodigy pattern appends /gis to the detail URL
    if not interactive_map and '/property-detail/' in url:
        interactive_map = url.rstrip('/') + '/gis'
        print(f"    🗺️  GIS Map (URL fallback): {interactive_map}")

    google_maps_url = build_google_maps_url(address) if address else ""
    zillow_url      = build_zillow_url(address) if address else ""
    realtor_url     = build_realtor_search_url(address) if address else ""
    property_map    = google_maps_url or interactive_map

    if google_maps_url:
        print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
    if zillow_url:
        print(f"    🏡 Zillow: {zillow_url[:80]}")
    print(f"    🔗 Canonical: {url}")

    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         url,
        "Property Map":               property_map,
        "Interactive Map":            interactive_map,
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Realtor":                    realtor_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        "",
    }

# ═══════════════════════════════════════════════════════════════════════════
# HOME/SEARCH PORTAL SCRAPER — Rusk, Goliad, DeWitt CADs
# These portals share the same engine:
#   Search page : {base}/Home/Search   (input#Keyword + button#btnsubmit)
#   Results     : property cards appear below; each card has an <a> link
#   Detail page : contains Owner, Situs Address, Appraised Value
# ═══════════════════════════════════════════════════════════════════════════

def _extract_homesearch_detail(page, final_url, county_label):
    """Extract property data from a Home/Search portal detail page."""
    address      = ""
    owner        = ""
    market_value = ""

    imp_homesite = imp_nonhomesite = land_homesite = land_nonhomesite = ag_market = ""

    try:
        # This engine (Rusk/Goliad/DeWitt) renders every field as a plain
        # <table class="table"><tbody><tr><td>Label</td><td>Value</td></tr>
        # ...</tbody></table> — one table per section (ACCOUNT / OWNER /
        # LOCATION / VALUES). Section headings like
        # <h3 class="property-title">OWNER</h3> sit OUTSIDE those tables. The
        # old selector (`[class*="title"]`, `strong`, etc.) matched that
        # heading as if it were a field label, and its nextElementSibling —
        # the *entire* owner table wrapper — became the "owner" value, i.e.
        # the whole "Owner ID / Name / Care of / Mailing Address / ..." block
        # got dumped into one field. Scanning only <tr> label/value pairs
        # can't make that mistake since headings aren't rows.
        scraped = page.evaluate("""
            () => {
                var r = { address: '', owner: '', value: '',
                          impHs: '', impNhs: '', landHs: '', landNhs: '', agVal: '' };
                var rows = [...document.querySelectorAll('table tbody tr')];
                for (var row of rows) {
                    var tds = row.querySelectorAll('td');
                    if (tds.length < 2) continue;
                    var lbl = (tds[0].innerText || '').trim().toLowerCase();
                    var val = (tds[tds.length - 1].innerText || '').trim();
                    if (!lbl || !val) continue;

                    if (!r.address && ['location', 'address', 'property address',
                            'situs address', 'street address', 'situs'].includes(lbl)) {
                        r.address = val;
                    }
                    if (!r.owner && (lbl === 'name' || lbl === 'owner name')) {
                        r.owner = val;
                    }
                    if (!r.value && (lbl === 'market value' || lbl === 'appraised value')) {
                        r.value = val;
                    }
                    if (!r.impHs   && lbl === 'improvement hs')  r.impHs   = val;
                    if (!r.impNhs  && lbl === 'improvement nhs') r.impNhs  = val;
                    if (!r.landHs  && lbl === 'land hs')         r.landHs  = val;
                    if (!r.landNhs && lbl === 'land nhs')        r.landNhs = val;
                    if (!r.agVal   && (lbl === 'ag/timber value' || lbl === 'ag market valuation'))
                        r.agVal = val;
                }
                return r;
            }
        """)
        address = scraped.get("address", "").strip().rstrip(",")
        owner   = scraped.get("owner", "").strip()
        raw_val = scraped.get("value", "").replace(",", "").replace("$", "").strip()
        if raw_val.isdigit():
            market_value = f"${int(raw_val):,}"

        def _fmt(raw):
            raw = (raw or "").replace(",", "").replace("$", "").strip()
            return f"${int(raw):,}" if raw.isdigit() else ""

        imp_homesite     = _fmt(scraped.get("impHs"))
        imp_nonhomesite  = _fmt(scraped.get("impNhs"))
        land_homesite    = _fmt(scraped.get("landHs"))
        land_nonhomesite = _fmt(scraped.get("landNhs"))
        ag_market        = _fmt(scraped.get("agVal"))
    except Exception as e:
        print(f"    ⚠️  {county_label} DOM extraction error: {e}")

    # Fallback via inner_text()
    text = ""
    try:
        text = page.inner_text("body")
    except Exception:
        pass

    if not address and text:
        m = re.search(
            r'(?:Situs\s+Address|Property\s+Address|Street\s+Address|Location)[:\s]+([^\n]{5,120})',
            text, re.IGNORECASE
        )
        address = m.group(1).strip().rstrip(',') if m else ""

    if address:
        address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
        address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()
        print(f"    🏠 {county_label} address: {address}")

    if not owner and text:
        m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
        if m:
            owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', m.group(1))[0].strip()
            if len(owner) < 3:
                owner = ""
    if owner:
        print(f"    👤 {county_label} owner: {owner}")

    if not market_value and text:
        market_value = extract_market_value(text)
    if market_value:
        print(f"    💰 {county_label} value: {market_value}")

    def _val(label):
        m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                return f"${int(raw):,}"
            except Exception:
                pass
        return ""

    imp_homesite     = imp_homesite     or _val(r'Improvement\s+Homesite(?:\s+Value)?')
    imp_nonhomesite  = imp_nonhomesite  or _val(r'Improvement\s+Non-?Homesite(?:\s+Value)?')
    land_homesite    = land_homesite    or _val(r'Land\s+Homesite(?:\s+Value)?')
    land_nonhomesite = land_nonhomesite or _val(r'Land\s+Non-?Homesite(?:\s+Value)?')
    ag_market        = ag_market        or _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

    google_maps_url = build_google_maps_url(address) if address else ""
    zillow_url      = build_zillow_url(address) if address else ""
    realtor_url     = build_realtor_search_url(address) if address else ""
    property_map    = google_maps_url

    if google_maps_url:
        print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
    if zillow_url:
        print(f"    🏡 Zillow: {zillow_url[:80]}")
    print(f"    🔗 Canonical: {final_url}")

    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         final_url,
        "Property Map":               property_map,
        "Interactive Map":            "",
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Realtor":                    realtor_url,
        "Improvement Homesite Value": imp_homesite,
        "Improvement Non-Homesite":   imp_nonhomesite,
        "Land Homesite Value":        land_homesite,
        "Land Non-Homesite Value":    land_nonhomesite,
        "Ag Market Valuation":        ag_market,
    }


def _scrape_homesearch_property(page, base_url, account_number, county_label):
    """
    Scrape a Home/Search portal CAD (Rusk, Goliad, DeWitt).

    Flow:
      1. Go to {base_url}/Home/Search
      2. Type account number into input#Keyword
      3. Click button#btnsubmit (or fallback Search button)
      4. Wait for result cards/links to appear
      5. Click first result
      6. Extract detail page data
    """
    clean = account_number.strip()
    search_url = f"{base_url}/Home/Search"
    print(f"    🔍 {county_label} account: {clean}")

    try:
        page.goto(search_url, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        # Fill the Keyword input
        keyword_input = page.locator(
            "input#Keyword, input[name='Keyword'], "
            "input[placeholder='Keyword'], input[placeholder*='keyword' i]"
        )
        try:
            keyword_input.first.wait_for(state="visible", timeout=10000)
        except Exception:
            print(f"    ⚠️  {county_label}: Keyword input not found at {search_url}")
            return None
        keyword_input.first.clear()
        keyword_input.first.fill(clean)
        print(f"    ✏️  Entered: {clean}")
        page.wait_for_timeout(300)

        # Submit
        submit_btn = page.locator(
            "button#btnsubmit, input#btnsubmit, "
            "button:has-text('Search'), input[value='Search'], "
            "button[type='submit'], input[type='submit']"
        )
        clicked = False
        for i in range(submit_btn.count()):
            el = submit_btn.nth(i)
            if el.is_visible():
                el.click()
                clicked = True
                print(f"    🖱️  Search submitted")
                break
        if not clicked:
            keyword_input.first.press("Enter")
            print(f"    ⌨️  Enter pressed")

        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)

        # Wait for the results table body to appear.
        # The portal renders a data table with columns:
        #   Parcel ID | Sequence | Account | Owner ID | Property Type |
        #   Owner Name | Property Address | Legal | Actions
        # The Parcel ID cell (first column) is the clickable link we want.
        try:
            page.wait_for_selector("tbody tr td a", timeout=10000)
        except Exception:
            print(f"    ⚠️  {county_label}: results table did not appear for: {clean}")
            return None

        # Use JavaScript to find the first data-row link — skip any header rows.
        # Priority order:
        #   0. If multiple rows came back, the row whose Parcel ID (first
        #      column) is an EXACT match for the searched account
        #   1. First <a> inside a <td> in <tbody> (Parcel ID link)
        #   2. Any <a> whose text is a short numeric/alphanumeric ID
        #   3. Any <a> that looks like an action icon
        clicked_result = False

        # Strategy 0: disambiguate multi-row results. This portal's search
        # matches loosely against several columns at once (Parcel ID, Owner
        # ID, Geo ID, address...), so searching a short Geo ID like "52542"
        # can also match an unrelated row whose Owner ID happens to contain
        # the same digits (e.g. "R52542") — and that unrelated row can sort
        # first, silently attaching the wrong owner/address/value to this
        # account. When more than one row comes back, prefer the one whose
        # Parcel ID column is an exact match for what was actually searched.
        all_rows = page.locator("tbody tr")
        row_count = all_rows.count()
        if row_count > 1:
            for i in range(row_count):
                try:
                    row = all_rows.nth(i)
                    first_cell = row.locator("td").first.inner_text().strip()
                    if first_cell != clean:
                        continue
                    link = row.locator("a").first
                    href = link.get_attribute("href") or ""
                    if not href or href in ("#", "javascript:void(0)"):
                        continue
                    txt = (link.inner_text() or "").strip()
                    link.click()
                    clicked_result = True
                    print(f"    🎯 {county_label}: {row_count} results — matched exact Parcel ID row: {clean} → {href[:80]}")
                    break
                except Exception:
                    continue
            if not clicked_result:
                print(f"    ⚠️  {county_label}: {row_count} results for '{clean}', none had an exact Parcel ID match — falling back to first result")

        # Strategy 1: first <td> <a> in <tbody> (Parcel ID column)
        first_td_link = page.locator("tbody tr td:first-child a")
        if first_td_link.count() == 0:
            first_td_link = page.locator("tbody tr td a")

        for i in range(0 if clicked_result else min(first_td_link.count(), 5)):
            el = first_td_link.nth(i)
            try:
                if not el.is_visible():
                    continue
                txt  = (el.inner_text() or "").strip()
                href = el.get_attribute("href") or ""
                if not href or href in ("#", "javascript:void(0)"):
                    continue
                if href.startswith("mailto") or href.startswith("tel"):
                    continue
                el.click()
                clicked_result = True
                print(f"    🖱️  Clicked Parcel ID: {txt} → {href[:80]}")
                break
            except Exception:
                continue

        # Strategy 2: fallback — any visible <a> in the page body that has
        # a numeric-looking text or a detail/view href pattern
        if not clicked_result:
            fallback = page.locator(
                "tbody tr a, "
                "a[href*='Search'], a[href*='Detail'], a[href*='detail'], "
                "a[href*='Parcel'], a[href*='parcel'], "
                "a[href*='View'], a[href*='view']"
            )
            for i in range(min(fallback.count(), 20)):
                el = fallback.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    txt  = (el.inner_text() or "").strip()
                    href = el.get_attribute("href") or ""
                    if not href or href in ("#", "javascript:void(0)"):
                        continue
                    if href.startswith("mailto") or href.startswith("tel"):
                        continue
                    # Skip pure nav links (no digit in text and no detail-like href)
                    if not re.search(r'\d', txt) and not re.search(
                            r'detail|parcel|view|property', href, re.IGNORECASE):
                        continue
                    el.click()
                    clicked_result = True
                    print(f"    🖱️  Clicked fallback link: {txt[:60]} → {href[:80]}")
                    break
                except Exception:
                    continue

        if not clicked_result:
            print(f"    ⚠️  {county_label}: could not click any result link for: {clean}")
            return None

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        final_url = page.url
        print(f"    ✅ {county_label} detail loaded: {final_url[:90]}")
        return _extract_homesearch_detail(page, final_url, county_label)

    except Exception as e:
        print(f"    ❌ {county_label} scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# LEON CAD — leoncad.org (same Home/Search engine as Rusk/Goliad/DeWitt/Eastland)
# MVBA sometimes exports an over-long compound number for Leon instead of the
# plain 6-digit Property ID — e.g. "975913000001" — where only the leading 6
# digits ("975913") are the real, searchable Property ID and the rest is a
# zero-padded tract/sequence suffix. Searching with the full number returns
# no match, so it's trimmed down to the first 6 digits before searching.
# ═══════════════════════════════════════════════════════════════════════════

def _leon_clean_id(raw):
    digits = re.sub(r'\D', '', raw.strip())
    if len(digits) > 6:
        return digits[:6]
    return digits


def _scrape_leon_property(page, account_number):
    clean = _leon_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse Leon account: {account_number}")
        return None
    if clean != account_number.strip():
        print(f"    ✂️  Leon account trimmed: {account_number} → {clean}")
    return _scrape_homesearch_property(page, HOMESEARCH_URLS["leon"], clean, "Leon CAD")


# ═══════════════════════════════════════════════════════════════════════════
# BOWIE CAD — bowieappraisal.com (AG Grid / React SPA)
# Search: https://bowieappraisal.com/property-search
# Flow  : enter account/GEO ID → click search → click PropID link → detail
# ═══════════════════════════════════════════════════════════════════════════

def _scrape_bowie_property(page, account_number):
    clean = re.sub(r'^[Rr]', '', account_number.strip())
    print(f"    🔍 Bowie account: {clean}")

    try:
        page.goto(
            "https://bowieappraisal.com/property-search",
            timeout=60000,
            wait_until="domcontentloaded",
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2500)

        # ── Find and fill the search text input ──────────────────────────
        # Angular SPA — use JS native setter so Angular change detection fires
        filled = page.evaluate("""
            (val) => {
                var inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
                var inp = inputs.find(i => i.offsetParent !== null && i.offsetWidth > 100);
                if (!inp) inp = inputs.find(i => i.offsetParent !== null);
                if (!inp) return false;
                inp.focus();
                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(inp, val);
                inp.dispatchEvent(new Event('input',  { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
        """, clean)
        if not filled:
            print(f"    ⚠️  Bowie: JS fill failed — trying Playwright fill")
            inp_loc = page.locator("input[type='text'], input:not([type])")
            visible = [inp_loc.nth(i) for i in range(inp_loc.count())
                       if inp_loc.nth(i).is_visible()]
            if not visible:
                print(f"    ⚠️  Bowie: no search input found")
                return None
            visible[0].click()
            visible[0].fill(clean)
        print(f"    ✏️  Entered: {clean}")
        page.wait_for_timeout(500)

        # ── Click the search (magnifying glass) button ───────────────────
        # Try JS click on the button with a search icon
        btn_clicked = page.evaluate("""
            () => {
                var btns = [...document.querySelectorAll('button')];
                // prefer button that contains an svg or mat-icon or search-related class
                var b = btns.find(b => b.offsetParent !== null && (
                    b.querySelector('svg, mat-icon, [class*="search" i], [class*="magnif" i]') ||
                    (b.getAttribute('aria-label') || '').toLowerCase().includes('search') ||
                    (b.className || '').toLowerCase().includes('search')
                ));
                if (!b) b = btns.find(b => b.offsetParent !== null && b.type === 'submit');
                if (!b) return false;
                b.click();
                return true;
            }
        """)
        if btn_clicked:
            print(f"    🖱️  Search button clicked (JS)")
        else:
            page.keyboard.press("Enter")
            print(f"    ⌨️  Enter pressed (no button found)")

        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # ── Wait for AG Grid results rows ─────────────────────────────────
        try:
            page.wait_for_selector(
                ".ag-row, table tbody tr, [class*='ag-row']",
                timeout=10000
            )
        except Exception:
            print(f"    ⚠️  Bowie: no results appeared for: {clean}")
            return None

        # ── Click the first PropID link in the results ────────────────────
        prop_link = page.locator(
            ".ag-cell a, [col-id='propId'] a, "
            "table tbody td a, .ag-row a"
        )
        if prop_link.count() == 0:
            # Fallback: any anchor in the grid/table area
            prop_link = page.locator(".ag-center-cols-container a, tbody a")
        if prop_link.count() == 0:
            print(f"    ⚠️  Bowie: no PropID link found in results")
            return None

        prop_id_text = ""
        try:
            prop_id_text = prop_link.first.inner_text().strip()
        except Exception:
            pass
        prop_link.first.click()
        print(f"    🖱️  Clicked PropID: {prop_id_text}")

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)

        # Scroll to trigger lazy-loaded sections
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

        final_url = page.url
        text = page.inner_text("body")
        print(f"    🔗 Detail URL: {final_url}")

        # ── Owner ─────────────────────────────────────────────────────────
        owner = ""
        owner_m = re.search(r'(?:Owner\s+Name|Owner(?!\s*ID\b))[ \t:]+([A-Z][^\n]{2,80})', text, re.IGNORECASE)
        if owner_m:
            owner = re.split(r'\s{3,}|\bMailing\b|\bAddress\b', owner_m.group(1))[0].strip()
            if len(owner) < 3:
                owner = ""
        if not owner:
            try:
                owner = page.evaluate("""
                    () => {
                        for (var el of document.querySelectorAll('td, th, span, div, label')) {
                            var t = (el.innerText || '').trim().toLowerCase();
                            if (t === 'owner name' || t === 'owner') {
                                var nx = el.nextElementSibling;
                                if (nx) return (nx.innerText || '').trim();
                                var row = el.closest('tr');
                                if (row) {
                                    var tds = row.querySelectorAll('td');
                                    if (tds.length >= 2) return (tds[tds.length-1].innerText||'').trim();
                                }
                            }
                        }
                        return '';
                    }
                """) or ""
                if len(owner) < 3:
                    owner = ""
            except Exception:
                pass
        if owner:
            print(f"    👤 Owner: {owner}")

        # ── Address ───────────────────────────────────────────────────────
        address = ""
        for pat in [
            r'(?:Situs|Property)\s+Address[:\s]+([^\n]{5,120})',
            r'\bAddress[:\s]+(\d[^\n]{5,120})',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                address = m.group(1).strip().rstrip(',')
                address = re.sub(r'\s+USA\b', '', address, flags=re.IGNORECASE)
                address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, re.IGNORECASE).strip()
                break
        if not address:
            try:
                address = page.evaluate("""
                    () => {
                        for (var el of document.querySelectorAll('td, th, span, div, label')) {
                            var t = (el.innerText || '').trim().toLowerCase();
                            if (t.includes('situs address') || t.includes('property address') || t === 'address') {
                                var nx = el.nextElementSibling;
                                if (nx) return (nx.innerText || '').trim();
                                var row = el.closest('tr');
                                if (row) {
                                    var tds = row.querySelectorAll('td');
                                    if (tds.length >= 2) return (tds[tds.length-1].innerText||'').trim();
                                }
                            }
                        }
                        return '';
                    }
                """) or ""
                if address:
                    address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, re.IGNORECASE).strip()
                if len(address) < 4:
                    address = ""
            except Exception:
                pass
        if address:
            print(f"    🏠 Address: {address}")

        # ── Values ────────────────────────────────────────────────────────
        market_value = extract_market_value(text)
        if market_value:
            print(f"    💰 Value: {market_value}")

        def _val(label):
            m = re.search(label + r'[:\s]+\$?([\d,]+)', text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '')
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite     = _val(r'Improvement\s+Homesite(?:\s+Value)?')
        imp_nonhomesite  = _val(r'Improvement\s+Non-?Homesite(?:\s+Value)?')
        land_homesite    = _val(r'Land\s+Homesite(?:\s+Value)?')
        land_nonhomesite = _val(r'Land\s+Non-?Homesite(?:\s+Value)?')
        ag_market        = _val(r'Ag(?:ricultural)?\s+Market\s+Val(?:uation)?')

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""

        if google_maps_url:
            print(f"    🗺️  Google Maps: {google_maps_url[:80]}")
        if zillow_url:
            print(f"    🏡 Zillow: {zillow_url[:80]}")

        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               google_maps_url,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ Bowie scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# SMITH CAD — GSA CORP DIRECT URL SCRAPER
# URL pattern: https://smithcad-search.gsacorp.io/parcel/{account_number}
# Account format: plain digits, no R prefix (e.g. 100000001201172000).
# Server-rendered HTML (no client-side hydration/loading placeholders) —
# "Location" (Parcel Summary table) is the situs address; "Total Building
# Value" / "Total Land Value" (Preliminary Values table) are improvement/land;
# the "County GIS" nav link (points at smithcad.org's own WAB map, not the
# in-site "Interactive GIS" link) is what feeds Interactive Map.
# ═══════════════════════════════════════════════════════════════════════════

def _smith_clean_id(raw):
    """Smith CAD parcel ids are plain digits — strip any dots/dashes/spaces."""
    return re.sub(r'\D', '', raw.strip())


def _scrape_smith_property(page, account_number):
    clean = _smith_clean_id(account_number)
    if not clean:
        print(f"    ⚠️  Could not parse Smith account: {account_number}")
        return None
    print(f"    🔍 Smith account: {clean}")

    url = f"{SMITH_BASE_URL}/parcel/{clean}"
    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(400)

        if not page.query_selector("section.title"):
            print(f"    ❌ Smith property not found: {account_number}")
            return None

        scraped = page.evaluate("""
            () => {
                var result = { owner: '', location: '', building: '', land: '', total: '', countyGis: '' };

                var ownDiv = document.querySelector('.ownership > div');
                if (ownDiv) {
                    result.owner = (ownDiv.innerText || '').split('\\n')[0].trim();
                }

                // "Value History" (prior years) is a second table further down
                // the page using the SAME row labels as "Preliminary Values"
                // (current year) — take the first match only so the current
                // year's numbers win instead of being overwritten by history.
                var rows = [...document.querySelectorAll('table.grid tr, table.grid-transposed tr')];
                for (var row of rows) {
                    var th = row.querySelector('th');
                    var tds = row.querySelectorAll('td');
                    if (!th || !tds.length) continue;
                    var label = (th.innerText || '').trim().toLowerCase();
                    var val = (tds[0].innerText || '').trim();
                    if (label === 'location' && !result.location) result.location = val;
                    if (label === 'total building value' && !result.building) result.building = val;
                    if (label === 'total land value' && !result.land) result.land = val;
                    if (label === 'total property value' && !result.total) result.total = val;
                }

                var links = [...document.querySelectorAll('section.nav a')];
                for (var a of links) {
                    if ((a.innerText || '').trim().toLowerCase() === 'county gis') {
                        result.countyGis = a.href;
                        break;
                    }
                }
                return result;
            }
        """)

        owner = (scraped.get("owner") or "").strip()

        address = (scraped.get("location") or "").strip()
        address = re.sub(r'\s+', ' ', address).strip()
        address = re.sub(r',?\s*(TX|Texas)\s*\d*\s*$', ', TX', address, flags=re.IGNORECASE).strip()

        if owner:
            print(f"    👤 Smith owner: {owner}")
        if address:
            print(f"    🏠 Smith address: {address}")

        def _money(raw_val):
            raw_val = (raw_val or "").replace(",", "").replace("$", "").strip()
            try:
                return f"${int(round(float(raw_val))):,}" if raw_val else ""
            except Exception:
                return ""

        improvement  = _money(scraped.get("building"))
        land         = _money(scraped.get("land"))
        market_value = _money(scraped.get("total"))

        if improvement:
            print(f"    🏗️  Smith improvement: {improvement}")
        if land:
            print(f"    🌿 Smith land: {land}")
        if market_value:
            print(f"    💰 Smith total value: {market_value}")

        interactive_map = scraped.get("countyGis") or ""
        if interactive_map:
            print(f"    🗺️  Smith County GIS: {interactive_map}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""

        print(f"    🔗 Canonical: {url}")
        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         url,
            "Property Map":               google_maps_url,
            "Interactive Map":            interactive_map,
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": improvement,
            "Improvement Non-Homesite":   "",
            "Land Homesite Value":        land,
            "Land Non-Homesite Value":    "",
            "Ag Market Valuation":        "",
        }

    except Exception as e:
        print(f"    ❌ Smith scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# EL PASO CAD (EPCAD) — epcad.org/Search PORTAL
# Search: https://epcad.org/Search → fill the search box → click search →
#         click "Details" on the result row → lands on
#         /Search/Details/{PropertyID}/{Year} (Property tab, default). Click
#         the "Values" tab for the Improvement/Land value breakdown.
# Account format: user pastes the Geographic ID as-is (e.g.
#   "S922999003D2500") — same convention as Nueces/Wilson/Rains.
# The site sits behind Cloudflare's bot-management JS challenge; a real
# (non-headless) browser normally clears it after a couple seconds, so every
# navigation is followed by _epcad_clear_cloudflare(). Under a burst of rapid
# requests Cloudflare can escalate to an interactive "Verify you are human"
# checkbox — that gets clicked once if present.
# EPCAD's own "Location > Address" field is frequently just a bare
# "TX {zip}" (vacant-land parcels with no situs on file), which is weaker
# than a real address MVBA already has on the sheet — the stronger of the
# two (via _address_strength) wins rather than letting EPCAD always
# overwrite.
# ═══════════════════════════════════════════════════════════════════════════

EPCAD_BASE_URL   = "https://epcad.org"
EPCAD_SEARCH_URL = f"{EPCAD_BASE_URL}/Search"


def _epcad_clear_cloudflare(page, timeout_ms=25000):
    """
    Wait out Cloudflare's automatic JS challenge ("Performing security
    verification"). If it has escalated to an interactive Turnstile
    checkbox, click it once. Returns True once real page content has
    loaded, False if still blocked after timeout_ms.
    """
    import time
    deadline = time.time() + (timeout_ms / 1000)
    clicked = False
    while time.time() < deadline:
        try:
            title   = page.title()
            content = page.content()
        except Exception:
            page.wait_for_timeout(500)
            continue
        if 'Performing security verification' not in content and 'Just a moment' not in title:
            return True
        if not clicked:
            try:
                checkbox = page.frame_locator('iframe[title*="challenge" i]').locator('input[type="checkbox"]')
                if checkbox.count() > 0:
                    checkbox.click(timeout=3000)
                    clicked = True
                    print("    🤖 El Paso: clicked Cloudflare verification checkbox")
            except Exception:
                pass
        page.wait_for_timeout(1500)
    return False


def _scrape_elpaso_property(page, account_number, row=None):
    clean = account_number.strip()
    print(f"    🔍 El Paso account: {clean}")

    try:
        page.goto(EPCAD_SEARCH_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        if not _epcad_clear_cloudflare(page):
            print(f"    ⚠️  El Paso: blocked by Cloudflare — skipping")
            return None

        search_box = page.get_by_placeholder("Search by Name, Address, PropertyId, or GeoID")
        search_box.wait_for(state="visible", timeout=15000)
        search_box.click()
        search_box.fill(clean)
        page.wait_for_timeout(300)

        page.locator('#remote button.btn-primary').click()
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        if not _epcad_clear_cloudflare(page):
            print(f"    ⚠️  El Paso: blocked by Cloudflare on results page — skipping")
            return None
        page.wait_for_timeout(800)

        details_link = page.locator('a:has-text("Details")').first
        if details_link.count() == 0:
            print(f"    ❌ El Paso: no results for {clean}")
            return None

        details_link.click()
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        if not _epcad_clear_cloudflare(page):
            print(f"    ⚠️  El Paso: blocked by Cloudflare on detail page — skipping")
            return None
        page.wait_for_timeout(1000)

        final_url = page.url
        print(f"    ✅ El Paso detail loaded: {final_url[:100]}")

        text = page.inner_text("body")

        # Property tab renders three labeled sections in order: Account,
        # Location, Owners. Slice on those headers rather than relying on
        # exact DOM structure so label/value pairs can't cross sections.
        loc_section = text.split("Location", 1)[1] if "Location" in text else text
        own_section = loc_section.split("Owners", 1)[1] if "Owners" in loc_section else ""
        loc_section = loc_section.split("Owners", 1)[0] if "Owners" in loc_section else loc_section

        situs_m = re.search(r'Address:\s*\n?\s*([^\n]+)', loc_section)
        situs_address = situs_m.group(1).strip() if situs_m else ""

        mail_m = re.search(r'Mailing Address:\s*\n?\s*([^\n]+)', own_section)
        mailing_address = mail_m.group(1).strip() if mail_m else ""

        name_m = re.search(r'Name:\s*\n?\s*([^\n]+)', own_section)
        owner = name_m.group(1).strip() if name_m else ""

        # Situs address wins over the owner's mailing address unless it's
        # actually weaker (e.g. bare "TX 79904" vs. a full mailing address).
        if _address_strength(situs_address) >= _address_strength(mailing_address):
            cad_address = situs_address or mailing_address
        else:
            cad_address = mailing_address

        existing_address = (row.get("Property Address", "") if row else "").strip()
        if _address_strength(cad_address) >= _address_strength(existing_address):
            address = cad_address.rstrip(",").strip()
            if address:
                print(f"    🏠 El Paso address (CAD wins): {address}")
        else:
            address = ""
            print(f"    🏠 El Paso: keeping existing address (stronger than CAD's '{cad_address}')")

        if owner:
            print(f"    👤 El Paso owner: {owner}")

        # ── Values tab ──────────────────────────────────────────────────
        values_tab = page.locator('a:has-text("Values")').first
        if values_tab.count() > 0:
            values_tab.click()
            page.wait_for_timeout(1200)

        values_text = page.inner_text("body")

        def _val(label):
            m = re.search(label + r'[:\s]*[+\-=]?\s*\$?([\d,]+(?:\.\d{1,2})?)', values_text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',', '').split('.')[0]
                try:
                    return f"${int(raw):,}"
                except Exception:
                    pass
            return ""

        imp_homesite     = _val(r'Improvement\s+Homesite\s+Value')
        imp_nonhomesite  = _val(r'Improvement\s+Non\s*Homesite\s+Value')
        land_homesite    = _val(r'Land\s+Homesite\s+Value')
        land_nonhomesite = _val(r'Land\s+Non\s*Homesite\s+Value')
        ag_market        = _val(r'Agricultural\s+Market\s+Valuation')
        market_value     = _val(r'Market\s+Value') or _val(r'Appraised\s+Value')

        if market_value:
            print(f"    💰 El Paso value: {market_value}")

        google_maps_url = build_google_maps_url(address) if address else ""
        zillow_url      = build_zillow_url(address) if address else ""
        realtor_url     = build_realtor_search_url(address) if address else ""

        print(f"    🔗 Canonical: {final_url}")
        return {
            "Property Address":           address,
            "Owner Name":                 owner,
            "Adjusted Value":             market_value,
            "Appraisal District":         final_url,
            "Property Map":               google_maps_url,
            "Interactive Map":            "",
            "Satellite View":             google_maps_url,
            "Zillow":                     zillow_url,
            "Realtor":                    realtor_url,
            "Improvement Homesite Value": imp_homesite,
            "Improvement Non-Homesite":   imp_nonhomesite,
            "Land Homesite Value":        land_homesite,
            "Land Non-Homesite Value":    land_nonhomesite,
            "Ag Market Valuation":        ag_market,
        }

    except Exception as e:
        print(f"    ❌ El Paso scrape error: {e}")
        import traceback; traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# HAYS COUNTY — tax.co.hays.tx.us (Tyler Technologies "Orion Public Access")
# This is the county Tax Assessor-Collector's own parcel portal, not the
# Hays CAD proper (hayscad.com, which 403s every request — Cloudflare-
# blocked) — but it carries the same owner/situs/market-value data keyed by
# the same CAD account number ("R44371") already stored as the sheet's
# Account Number for Hays rows.
#
# The site's own Property-Detail page (Property-Detail/PropertyQuickRefID/
# {id}/PartyQuickRefID/{partyId}/SearchTaxYear/{year}) is broken site-side —
# it never even fires its own data-fetch call and always shows "Details for
# {id} could not be loaded", reproduced consistently in both headless and
# headed runs. The Advanced Search page's results grid gets its data from a
# separate, working JSON endpoint instead (Proxy/Search/Properties/
# advancedsearch), which returns everything needed — owner, situs address,
# market/assessed value — in one call, so that's used directly rather than
# trying to load the broken detail page. No Land/Improvement value
# breakdown is available from this source (it's tax-office data, not the
# CAD's own appraisal roll), so those sub-fields are left blank.
# ═══════════════════════════════════════════════════════════════════════════

HAYS_SEARCH_PAGE_URL = "https://tax.co.hays.tx.us/Advanced-Search"


def _hays_format_address(situs):
    """'421 PARKER DR SAN MARCOS 78666' -> '421 PARKER DR SAN MARCOS, TX 78666'."""
    situs = (situs or "").strip()
    m = re.match(r'^(.*?)\s+(\d{5}(?:-\d{4})?)$', situs)
    if m:
        return f"{m.group(1).strip()}, TX {m.group(2)}"
    return situs


def _scrape_hays_property(page, account_number):
    account = account_number.strip()
    print(f"    🔍 Hays account: {account}")

    try:
        page.goto(HAYS_SEARCH_PAGE_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        result = page.evaluate("""
            async (args) => {
                const [acct, year] = args;
                const body = 'pn=1&PropertyID=&CADID=' + encodeURIComponent(acct) +
                    '&NameFirst=&NameLast=&PropertyOwnerID=&BusinessName=&StreetNoFrom=&StreetNoTo=' +
                    '&StreetName=&City=&ZipCode=&Neighborhood=&pStatus=All&AbstractSubdivisionCode=' +
                    '&AbstractSubdivisionName=&Block=&TractLot=&AcresFrom=&AcresTo=' +
                    '&ty=' + encodeURIComponent(year) + '&pvty=' + encodeURIComponent(year) +
                    '&pt=RP%3BMH%3BNR%3BPP&st=9&so=1&take=20&skip=0&page=1&pageSize=20';
                const resp = await fetch('/Proxy/Search/Properties/advancedsearch', {
                    method: 'POST',
                    headers: {'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                    body: body
                });
                if (!resp.ok) return null;
                return await resp.json();
            }
        """, [account, CURRENT_YEAR])
    except Exception as e:
        print(f"    ⚠️  Hays search error: {e}")
        return None

    results = (result or {}).get("ResultList") or []
    if not results:
        print(f"    ❌ Hays property not found: {account}")
        return None

    rec = next((r for r in results if r.get("PropertyQuickRefID") == account), results[0])

    owner   = (rec.get("OwnerName") or "").strip()
    address = _hays_format_address(rec.get("SitusAddress"))
    raw_val = rec.get("MarketValue") or rec.get("AssessedValue") or rec.get("PropertyValue") or 0
    try:
        market_value = f"${int(round(float(raw_val))):,}"
    except (TypeError, ValueError):
        market_value = ""

    if address:
        print(f"    🏠 Hays address: {address}")
    if owner:
        print(f"    👤 Hays owner: {owner}")
    if market_value:
        print(f"    💰 Hays value: {market_value}")

    pid      = rec.get("PropertyQuickRefID", account)
    party_id = rec.get("PartyQuickRefID", "")
    tax_year = rec.get("TaxYear", CURRENT_YEAR)
    detail_url = (
        f"https://tax.co.hays.tx.us/Property-Detail/PropertyQuickRefID/{pid}"
        f"/PartyQuickRefID/{party_id}/SearchTaxYear/{tax_year}"
    )

    google_maps_url = build_google_maps_url(address) if address else ""
    zillow_url       = build_zillow_url(address) if address else ""
    realtor_url      = build_realtor_search_url(address) if address else ""

    print(f"    🔗 Canonical: {detail_url}")
    return {
        "Property Address":           address,
        "Owner Name":                 owner,
        "Adjusted Value":             market_value,
        "Appraisal District":         detail_url,
        "Property Map":               google_maps_url,
        "Interactive Map":            "",
        "Satellite View":             google_maps_url,
        "Zillow":                     zillow_url,
        "Realtor":                    realtor_url,
        "Improvement Homesite Value": "",
        "Improvement Non-Homesite":   "",
        "Land Homesite Value":        "",
        "Land Non-Homesite Value":    "",
        "Ag Market Valuation":        "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# COUNTY SCRAPER DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════

def _call_county_scraper(page, county, account, row):
    """Dispatch to the right county scraper for a single account number."""
    account_plain = re.sub(r'^[Rr]', '', account)
    if county == "wharton":
        return _scrape_wharton_property(page, account)
    elif county == "limestone":
        return _scrape_limestone_property(page, account)
    elif county == "tomgreen":
        return _scrape_tomgreen_property(page, account)
    elif county == "runnels":
        return _scrape_runnels_property(page, account)
    elif county == "cameron":
        return _scrape_cameron_property(page, account)
    elif county == "valverde":
        return _scrape_valverde_property(page, account)
    elif county == "dallas":
        return _scrape_dallas_property(page, account)
    elif county == "bowie":
        return _scrape_bowie_property(page, account)
    elif county == "harrison":
        expected_owner = row.get("Owner Name", "") or row.get("Defendant", "") or ""
        return _scrape_harrison_property(page, account_plain, expected_owner=expected_owner)
    elif county == "anderson":
        return _scrape_anderson_property(page, account)
    elif county == "ellis":
        return _scrape_ellis_property(page, account, row)
    elif county == "travis":
        return _scrape_travis_property(page, account)
    elif county == "mclennan":
        return _scrape_mclennan_property(page, account)
    elif county == "midland":
        return _scrape_midland_property(page, account)
    elif county == "stephens":
        return _scrape_stephens_property(page, account)
    elif county == "williamson":
        return _scrape_williamson_property(page, account)
    elif county == "jackson":
        return _scrape_jackson_property(page, account)
    elif county == "smith":
        return _scrape_smith_property(page, account)
    elif county == "elpaso":
        return _scrape_elpaso_property(page, account, row)
    elif county == "leon":
        return _scrape_leon_property(page, account)
    elif county == "hays":
        return _scrape_hays_property(page, account)
    elif county in HOMESEARCH_URLS:
        base_url = HOMESEARCH_URLS[county]
        label    = county.title() + " CAD"
        return _scrape_homesearch_property(page, base_url, account, label)
    elif county in ESEARCH_URLS:
        base_url = ESEARCH_URLS[county]
        return _scrape_esearch_property(page, base_url, account, county)
    elif county in BIS_URLS:
        base_url = BIS_URLS[county]
        return _scrape_bis_property(page, base_url, account_plain, county)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_cad_enrichment(target_rows, _db=None, force_update=False):
    """
    Enrich rows with CAD property data.

    Address rules:
      - Blank on sheet  → fill from CAD Situs Address
      - Already filled  → never overwrite

    Always refreshed (even if already set):
      Appraisal District URL, Property Map, Interactive Map,
      Satellite View (Google Maps), Zillow,
      Adjusted Value and all sub-values.

    Zillow & Satellite View are built from the effective address
    (existing sheet address if present, else scraped address).
    """
    stats = {"updated": 0, "skipped": 0, "error": 0, "no_result": 0}
    rows_list = list(target_rows.items())

    print(f"\n  🏛️  CAD enrichment starting — {len(rows_list)} row(s)")

    with sync_playwright() as p:
        def _launch_browser():
            browser = p.chromium.launch(
                headless=False,
                slow_mo=150,
                args=["--host-resolver-rules=MAP bowieappraisal.com 13.33.109.54"],
            )
            context = browser.new_context()
            page    = context.new_page()
            return browser, context, page

        browser, context, page = _launch_browser()

        for uk, row in rows_list:
            county  = row.get("County", "").strip().lower().replace(" ", "").replace("_", "")
            account = row.get("Account Number", "").strip()

            # MVBA fallback IDs look like "MVBA-COMAL-33982" when the real CAD
            # account wasn't found on the listing page. The trailing number is
            # an arbitrary hash, not a real account — searching CAD with it can
            # coincidentally match an unrelated property and attach that
            # property's owner/value/address to the wrong lot. Treat these as
            # having no usable account rather than searching CAD with them.
            if re.match(r'^MVBA-[A-Z]+-\d+$', account, re.IGNORECASE):
                print(f"  ⚠️  MVBA fallback ID, not a real account — skipping: {uk}")
                stats["skipped"] += 1
                continue

            account_plain = re.sub(r'^[Rr]', '', account)

            if county not in SUPPORTED_COUNTIES:
                print(f"  ⏭️  Unsupported county ({county}): {uk}")
                stats["skipped"] += 1
                continue

            if not account:
                print(f"  ⚠️  No account number: {uk}")
                stats["skipped"] += 1
                continue

            raw_existing_address = row.get("Property Address", "").strip()
            current_address = raw_existing_address
            if not _has_real_address(current_address):
                current_address = ""
            existing_address_was_garbage = bool(raw_existing_address) and not current_address

            already_has_address   = bool(current_address)
            already_has_url       = row.get("Appraisal District", "").startswith("http")
            already_has_sat       = bool(row.get("Satellite View", "").strip())
            already_has_zillow    = bool(row.get("Zillow", "").strip())
            already_has_owner     = _has_real_owner(row.get("Owner Name", ""))
            already_has_adj_value = bool(row.get("Adjusted Value", "").strip())

            # Stephens, Williamson, and Dallas always re-enrich on every run
            if county not in ("stephens", "williamson", "dallas"):
                if (already_has_address and already_has_url and already_has_sat and
                        already_has_zillow and already_has_owner and already_has_adj_value):
                    if force_update:
                        print(f"  🔄 Force re-enriching: {uk}")
                    else:
                        print(f"  ⏭️  Already fully enriched: {uk}")
                        stats["skipped"] += 1
                        continue

            try:
                result = None

                # ── Multi-account handling ────────────────────────────────────
                # Some auction records store multiple account numbers joined by "/".
                # Harrison handles this internally; all others are handled here.
                # Only R-prefix accounts (real property) are valid for standard TX
                # counties; accounts with other prefixes (D, B, A…) are skipped.
                # If the county format matches none of the parts, skip the row.
                if county != "harrison" and '/' in account:
                    valid_accounts = _filter_valid_accounts(account, county)
                    if not valid_accounts:
                        print(f"  ⚠️  No valid {county} account format in: {account}")
                        stats["skipped"] += 1
                        continue
                    elif len(valid_accounts) == 1:
                        account = valid_accounts[0]
                        account_plain = re.sub(r'^[Rr]', '', account)
                        print(f"  ✂️  Single valid account: {account}")
                    else:
                        print(f"  🔀 {len(valid_accounts)} accounts to try: {', '.join(valid_accounts)}")
                        expected_owner = row.get("Owner Name", "") or row.get("Defendant", "") or ""
                        candidates = []
                        for acct in valid_accounts:
                            print(f"  🔍 Trying account: {acct}")
                            try:
                                r = _call_county_scraper(page, county, acct, row)
                                if r:
                                    owner = r.get("Owner Name", "")
                                    score = _owner_similarity(expected_owner, owner) if expected_owner else 0.0
                                    candidates.append((score, acct, r))
                                    print(f"  👤 {acct}: owner='{owner}' score={score:.2f}")
                            except Exception as acct_err:
                                print(f"  ⚠️  Error on {acct}: {acct_err}")
                        if not candidates:
                            print(f"  ❌ No results for any account in: {account}")
                            stats["no_result"] += 1
                            continue
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        _, best_acct, result = candidates[0]
                        account = best_acct
                        account_plain = re.sub(r'^[Rr]', '', account)
                        print(f"  ✅ Best match: {account}")

                if result is None:
                    if county == "wharton":
                        result = _scrape_wharton_property(page, account)
                    elif county == "limestone":
                        result = _scrape_limestone_property(page, account)
                    elif county == "tomgreen":
                        result = _scrape_tomgreen_property(page, account)
                    elif county == "runnels":
                        result = _scrape_runnels_property(page, account)
                    elif county == "cameron":
                        result = _scrape_cameron_property(page, account)
                    elif county == "valverde":
                        result = _scrape_valverde_property(page, account)
                    elif county == "dallas":
                        result = _scrape_dallas_property(page, account)
                    elif county == "bowie":
                        result = _scrape_bowie_property(page, account)
                    elif county == "harrison":
                        expected_owner = row.get("Owner Name", "") or row.get("Defendant", "") or ""
                        result = _scrape_harrison_property(page, account_plain, expected_owner=expected_owner)
                    elif county == "anderson":
                        result = _scrape_anderson_property(page, account)
                    elif county == "ellis":
                        result = _scrape_ellis_property(page, account, row)
                    elif county == "travis":
                        result = _scrape_travis_property(page, account)
                    elif county == "mclennan":
                        result = _scrape_mclennan_property(page, account)
                    elif county == "midland":
                        result = _scrape_midland_property(page, account)
                    elif county == "stephens":
                        result = _scrape_stephens_property(page, account)
                    elif county == "williamson":
                        result = _scrape_williamson_property(page, account)
                    elif county == "jackson":
                        result = _scrape_jackson_property(page, account)
                    elif county == "smith":
                        result = _scrape_smith_property(page, account)
                    elif county == "elpaso":
                        result = _scrape_elpaso_property(page, account, row)
                    elif county == "leon":
                        result = _scrape_leon_property(page, account)
                    elif county == "hays":
                        result = _scrape_hays_property(page, account)
                    elif county in HOMESEARCH_URLS:
                        base_url = HOMESEARCH_URLS[county]
                        label    = county.title() + " CAD"
                        result   = _scrape_homesearch_property(page, base_url, account, label)
                    elif county in ESEARCH_URLS:
                        base_url = ESEARCH_URLS[county]
                        result   = _scrape_esearch_property(page, base_url, account, county)
                    elif county in BIS_URLS:
                        base_url = BIS_URLS[county]
                        result   = _scrape_bis_property(page, base_url, account_plain, county)
                    else:
                        print(f"  ⚠️  No URL configured for county: {county}")
                        stats["skipped"] += 1
                        continue

                if result is None:
                    stats["no_result"] += 1
                    continue

                always_refresh = {
                    "Appraisal District", "Interactive Map",
                    "Satellite View", "Zillow", "Realtor",
                    "Property Map",
                    "Improvement Homesite Value", "Improvement Non-Homesite",
                    "Land Homesite Value", "Land Non-Homesite Value",
                    "Ag Market Valuation", "Adjusted Value",
                }

                scraped_address = result.get("Property Address", "").strip()

                if scraped_address and not _has_real_address(scraped_address):
                    print(f"    ⚠️  Discarding garbage CAD address: '{scraped_address}' (keeping existing)")
                    scraped_address = ""

                # Address rule (per docstring above): blank on sheet → fill
                # from CAD; already filled → keep whichever of the two is
                # actually the better/more complete address (via
                # _address_strength — same idiom used for Ellis/El Paso
                # above), not just whichever got there first. MVBA's own
                # scrape often only captures a bare street ("204 Little St")
                # while the CAD's situs address is the full verified one
                # ("204 LITTLE ST RANGER TX 76470") — that fuller one should
                # win. Whichever one ends up "effective" is what the
                # Zillow/Realtor/Satellite/Map links get rebuilt from, since
                # the scraper always builds those off its own scraped
                # address even when we end up keeping the existing one.
                if current_address:
                    effective_address = current_address
                    if scraped_address and scraped_address != current_address:
                        if _address_strength(scraped_address) > _address_strength(current_address):
                            effective_address       = scraped_address
                            row["Property Address"]  = scraped_address
                            print(f"    📍 Address upgraded (CAD more complete): '{current_address}' → '{scraped_address}'")
                        else:
                            print(f"    📍 Keeping existing address (already as good or better): '{current_address}' (CAD had: '{scraped_address}')")
                    else:
                        print(f"    📍 Address: {current_address}")
                elif scraped_address:
                    effective_address       = scraped_address
                    row["Property Address"] = scraped_address
                    print(f"    📍 Address filled from CAD: {scraped_address}")
                else:
                    # No usable CAD address. If the sheet's existing value was
                    # itself garbage (e.g. a stale "201 W. Grand" from before
                    # this fix), wipe it instead of leaving it in place forever.
                    effective_address = ""
                    if existing_address_was_garbage:
                        row["Property Address"] = ""
                        print(f"    🧹 Cleared stale garbage address: '{raw_existing_address}'")

                if effective_address:
                    result["Zillow"]         = build_zillow_url(effective_address)
                    result["Realtor"]        = build_realtor_search_url(effective_address)
                    result["Satellite View"] = build_google_maps_url(effective_address)
                    result["Property Map"]   = build_google_maps_url(effective_address)
                    print(f"    🏡 Zillow: {result['Zillow'][:80]}")
                    print(f"    🏠 Realtor: {result['Realtor'][:80]}")
                    print(f"    🗺️  Google Maps: {result['Satellite View'][:80]}")

                for field, value in result.items():
                    if field == "Property Address":
                        pass  # already handled above
                    elif field == "Owner Name" and value and not _has_real_owner(value):
                        print(f"    ⚠️  Discarding garbage CAD owner: '{value}' (keeping existing)")
                    elif field == "Owner Name" and already_has_owner:
                        pass  # existing owner name (e.g. from MVBA) wins — only fill when missing
                    elif value and (not row.get(field, "").strip() or field in always_refresh):
                        row[field] = value

                row["Last Updated"] = datetime.now().strftime("%Y-%m-%d")
                target_rows[uk]    = row
                stats["updated"]  += 1
                print(f"  ✅ Enriched: {uk} — {result.get('Property Address', 'no address')}")

            except Exception as e:
                print(f"  ❌ Error enriching {uk}: {e}")
                import traceback; traceback.print_exc()
                stats["error"] += 1
                if not browser.is_connected() or page.is_closed():
                    print(f"  🔄 Browser/page died — relaunching browser and continuing...")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser, context, page = _launch_browser()

        browser.close()

    print(f"\n  CAD done — Updated:{stats['updated']}  "
          f"Skipped:{stats['skipped']}  No result:{stats['no_result']}  "
          f"Errors:{stats['error']}")
    return stats