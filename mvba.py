"""
mvba.py — MVBA Tax Sale Scraper

Two parts:
1. PDF Scraper  : mvbalaw.com/tax-sales/month-sales/ → download PDF → parse (table format)
2. Online Auction: www.mvbataxsales.com → Playwright → card gallery → Lot Details page

MVBA Online text format (from detail page):
  Account No. 000642042/001583846 - MINERAL INTERESTS ONLY - BEING 0.87500 WORKING INTEREST...
  ::::: Suit No. 022445-CCL2, Pine Tree ISD et al v Ableready, Inc et al,
  Judgment Through Tax Year 2025

PDF table format (Calhoun example):
  TRACT | SUIT # | STYLE | DESCRIPTION+ADDR+ACCT | MIN BID
    1   | 16-10-6763 | Calhoun CAD v John Domingo | Lot 16... Acct# | $27,688.60
"""

import re, os, requests, hashlib
from datetime import datetime

import common
from common import (
    make_unique_key, smart_save, save_db, rewrite_csv,
    MONTH_NUM_TO_NAME
)

MVBA_MONTH_SALES_URL = "https://mvbalaw.com/tax-sales/month-sales/"


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — PARSE MVBA MONTHLY PAGE
# ═══════════════════════════════════════════════════════════════════════════

def fetch_mvba_page_with_playwright():
    """
    Fetch MVBA monthly sales page.
    Method 1: requests + BeautifulSoup (fast, no browser needed)
    Method 2: urllib fallback with different headers
    Returns list of raw link dicts: [{href, label}, ...]
    """
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "text/html,*/*",
        },
        {
            "User-Agent": "python-requests/2.31.0",
        },
    ]

    html = ""
    for hdrs in headers_list:
        try:
            resp = requests.get(MVBA_MONTH_SALES_URL, headers=hdrs, timeout=20)
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                print(f"  ✅ MVBA page fetched ({len(html)} chars)")
                break
            else:
                print(f"  ⚠️ HTTP {resp.status_code} — trying next header set")
        except Exception as e:
            print(f"  ⚠️ Request error: {e}")

    if not html:
        try:
            import urllib.request
            req = urllib.request.Request(
                MVBA_MONTH_SALES_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            print(f"  ✅ MVBA page fetched via urllib ({len(html)} chars)")
        except Exception as e:
            print(f"  ❌ urllib error: {e}")

    if not html:
        print(f"  ⚠️ Could not fetch MVBA page — using cached link patterns")
        return []

    raw_links = []
    import html as _html_mod

    anchor_pat = re.compile(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL
    )
    for href, inner in anchor_pat.findall(html):
        href  = href.strip()
        label = re.sub(r'<[^>]+>', '', inner).strip()
        label = _html_mod.unescape(label)
        label = re.sub(r'\s+', ' ', label).strip()
        if href and label and len(label) > 1:
            raw_links.append({"href": href, "label": label})

    print(f"  📋 Found {len(raw_links)} links on MVBA page")
    return raw_links


def _extract_county(label, href):
    """Extract county name from link label or URL."""
    label_clean = re.sub(
        r'\b(county|tax\s*sale|list|pdf|online|auction|printable|info|sale)\b',
        '', label, flags=re.IGNORECASE
    ).strip()
    words = label_clean.split()
    if words:
        candidate = "".join(w.strip(".,;:-") for w in words).lower()
        if len(candidate) >= 3 and candidate.replace("-", "").isalpha():
            return candidate

    url_m = re.search(r'taxuploads/(\w+)', href, re.IGNORECASE)
    if url_m:
        raw = url_m.group(1).lower()
        raw = re.sub(r'(county|taxsale|list|\d{4})', '', raw)
        return raw.strip("_-")

    ge_m = re.search(r'/tx/tx(\w+)/', href, re.IGNORECASE)
    if ge_m:
        return ge_m.group(1).lower()

    mv_m = re.search(r'/auction/(\w+)', href, re.IGNORECASE)
    if mv_m:
        return mv_m.group(1).lower()

    return "unknown"


def parse_mvba_listings_for_month(raw_links, target_month, target_year):
    """
    Parse raw links from MVBA page.
    Returns list of dicts: { county, pdf_url, online_url, online_type, auction_date }
    Only returns PDF and MVBA_ONLINE types — GovEase is completely skipped.
    """
    month_name = MONTH_NUM_TO_NAME[target_month]
    results    = []
    seen_urls  = set()

    SKIP_DOMAINS = [
        'mvbalaw.com/about', 'mvbalaw.com/services', 'mvbalaw.com/blog',
        'mvbalaw.com/contact', 'mvbalaw.com/disclaimer', 'mvbalaw.com/privacy',
        'mvbalaw.com/staff', 'mvbalaw.com/property-tax', 'mvbalaw.com/minerals',
        'mvbalaw.com/bankruptcy', 'mvbalaw.com/education', 'mvbalaw.com/truth',
        'mvbalaw.com/school', 'mvbalaw.com/legislative', 'mvbalaw.com/court',
        'mvbalaw.com/tax-sales', 'mvbalaw.com/#', 'mvbalaw.com/our-',
        'hotdogmarketing', 'facebook.com', 'twitter.com', 'linkedin.com',
        '/register', '/login', '/Bidder/', '/bidder/',
        'govease.com',
        'realauction.com',
        'sheriffsaleauctions',
        'customerservice@', 'info@', 'mailto:',
        'WilliamsonCountySaleInfo',
        'mrf.healthcarebluebook',
        'smith.texas',
    ]

    def should_skip(href, label):
        href_l  = href.lower()
        label_l = label.lower()
        for s in SKIP_DOMAINS:
            if s.lower() in href_l:
                return True
        skip_labels = [
            'registration link', 'register', 'printable list',
            'sale information', 'skip to', 'client login',
            'about us', 'contact', 'blog', 'services',
            'bidder registration', 'bidder-help', 'bidder help',
        ]
        for s in skip_labels:
            if s in label_l:
                return True
        return False

    auction_date = f"{month_name} {target_year}"
    for item in raw_links:
        label = item.get('label', '')
        dm = re.search(
            rf'{month_name}.*?(\w+\s+\d+,\s*\d{{4}})',
            label, re.IGNORECASE
        )
        if dm:
            auction_date = dm.group(1).strip()
            break

    print(f"  📅 Auction date: {auction_date}")

    for item in raw_links:
        href  = item.get('href', '').strip()
        label = item.get('label', '').strip()

        if not href or not label:
            continue
        if href in seen_urls:
            continue

        href_l = href.lower()

        is_pdf_link    = 'taxuploads' in href_l and href_l.endswith('.pdf')
        is_online_link = ('mvbataxsales.com' in href_l
                          and not href_l.startswith('mailto:'))  # catches /auction AND /Bidder, excludes mailto:

        if not is_pdf_link and not is_online_link:
            if should_skip(href, label):
                continue

        mm   = f"{target_month:02d}"
        yy   = str(target_year)[-2:]
        yyyy = str(target_year)

        if 'taxuploads' in href_l and href_l.endswith('.pdf'):
            filename = href_l.split('/')[-1]
            month_prefix = f"{mm}{yy}_"
            month_in_name = month_name.lower() in filename and yyyy in filename
            if not (filename.startswith(month_prefix) or month_in_name):
                print(f"  ⏭️  SKIP PDF (wrong month): {href.split('/')[-1]}")
                continue
            fname = href.split('/')[-1]
            fname_county = re.sub(r'^\d{4}_', '', fname).replace('.pdf', '').lower()
            county = fname_county if fname_county else _extract_county(label, href)
            seen_urls.add(href)
            results.append({
                'county': county, 'pdf_url': href, 'online_url': '',
                'online_type': 'PDF', 'auction_date': auction_date, 'label': label
            })
            print(f"  📋 PDF          | county='{county:15s}' | {fname}")

        elif 'mvbataxsales.com' in href_l:
            print(f"  🔍 MVBA URL found: label='{label[:50]}' | href={href[:80]}")

            # Month check: only skip if this is clearly a dated auction for wrong month.
            # Registration/bidder URLs have no month in the path — always include those.
            has_month = (month_name.lower() in href_l or f"-{mm}-{yyyy}" in href_l
                         or f"/{mm}-{yyyy}" in href_l or f"/{yyyy}" in href_l)
            is_dated_wrong = (
                'auction' in href_l
                and not has_month
                # only skip if another month name is explicitly in URL
                and any(m.lower() in href_l for m in MONTH_NUM_TO_NAME.values()
                        if m.lower() != month_name.lower())
            )
            if is_dated_wrong:
                print(f"  ⏭️  SKIP ONLINE (wrong month): {href[:70]}")
                continue

            county = _extract_county(label, href)
            if county in ('unknown', 'mvba', ''):
                # label like "MVBA Online Sale Registration Link" → try href path
                m_county = re.search(r'/tx[/-]?(\w+?)(?:/|-\d)', href_l)
                if m_county:
                    county = m_county.group(1).replace('tx', '', 1).strip('-')
                if not county or county in ('unknown', ''):
                    print(f"  ⚠️  County detect nahi hua, skip: {href[:70]}")
                    continue

            # Build auction URL: if this is a registration/bidder page, try to
            # construct the bidgallery URL from known MVBA patterns.
            url = href
            if '/bidder' in href_l or '/register' in href_l or '/login' in href_l:
                # Not a direct auction link — we'll still try to scrape with the
                # full URL; scrape_mvba_online_auction handles login walls gracefully.
                # But also try standard bidgallery path for this county.
                constructed = (
                    f"https://www.mvbataxsales.com/auction/tx/"
                    f"tx{county}/{month_name.lower()}-{mm}-{yyyy}/bidgallery/"
                )
                print(f"  🔧 Registration URL detected — will try constructed: {constructed}")
                url = constructed
            elif not url.rstrip('/').endswith('bidgallery'):
                url = url.rstrip('/') + '/bidgallery/'

            seen_urls.add(href)
            results.append({
                'county': county, 'pdf_url': '', 'online_url': url,
                'online_type': 'MVBA_ONLINE', 'auction_date': auction_date, 'label': label
            })
            print(f"  📋 MVBA_ONLINE  | county='{county:15s}' | {url[:60]}")

        elif 'govease.com' in href_l:
            county = _extract_county(label, href)
            print(f"  ⏭️  SKIPPED GOVEASE | county='{county}' | {href[:60]}")
            continue

    print(f"  ✅ MVBA: {len(results)} listings for {month_name} {target_year}")
    return results


def download_pdf(pdf_url, save_dir="mvba_pdfs"):
    os.makedirs(save_dir, exist_ok=True)
    filename   = pdf_url.split("/")[-1].split("?")[0]
    local_path = os.path.join(save_dir, filename)

    try:
        resp = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"  📥 Downloaded: {filename} ({len(resp.content)//1024}KB)")
        return local_path
    except Exception as e:
        print(f"  ❌ PDF download error: {e}")
        return None


def _withdrawn_ids_from_images(pg):
    """
    WITHDRAWN stamps are image objects overlaid on table rows.
    pdfplumber can't extract text from them, but their bounding box tells us
    which rows they cover. Return a set of text tokens (tract numbers, cause
    numbers) that fall inside any stamp bounding box on this page.
    """
    if not pg.images:
        return set()

    page_h = float(pg.height)

    bands = []
    for img in pg.images:
        img_top    = page_h - float(img.get('y1', 0))
        img_bottom = page_h - float(img.get('y0', 0))
        if img_bottom > img_top:
            bands.append((img_top - 5, img_bottom + 5))

    if not bands:
        return set()

    found = set()
    for w in pg.extract_words():
        mid = (w.get('top', 0) + w.get('bottom', 0)) / 2.0
        for (bt, bb) in bands:
            if bt <= mid <= bb:
                found.add(w['text'].strip())
                break

    return found


def _get_withdrawn_y_bands(pg):
    """
    Return Y bands (pdfplumber top-down coords) where WITHDRAWN stamps appear.
    Tries three methods because stamps can be: text (flattened vector graphics),
    raster images, or PDF annotation objects.
    """
    page_h = float(pg.height)
    bands  = []

    # Method A: text words containing WITHDRAWN (flattened vector/text stamps)
    try:
        for w in pg.extract_words():
            if 'WITHDRAWN' in w.get('text', '').upper():
                bands.append((float(w['top']) - 8, float(w['bottom']) + 8))
    except Exception:
        pass

    # Method B: large raster images (JPEG/PNG stamp overlays)
    try:
        for img in pg.images:
            img_top    = page_h - float(img.get('y1', 0))
            img_bottom = page_h - float(img.get('y0', 0))
            height = img_bottom - img_top
            width  = float(img.get('x1', 0)) - float(img.get('x0', 0))
            if height >= 8 and width >= 40 and img_bottom > img_top:
                bands.append((img_top - 8, img_bottom + 8))
    except Exception:
        pass

    # Method C: PDF annotation objects
    try:
        for annot in (getattr(pg, 'annots', None) or []):
            data = annot if isinstance(annot, dict) else {}
            subtype  = str(data.get('Subtype',  data.get('/Subtype',  ''))).upper()
            name     = str(data.get('Name',     data.get('/Name',     ''))).upper()
            contents = str(data.get('Contents', data.get('/Contents', ''))).upper()
            is_stamp = ('WITHDRAWN' in name or 'WITHDRAWN' in contents
                        or 'STAMP' in subtype or 'FREETEXT' in subtype)
            if is_stamp:
                rect = data.get('Rect', data.get('/Rect', []))
                if len(rect) >= 4:
                    ann_top    = page_h - float(rect[3])
                    ann_bottom = page_h - float(rect[1])
                    if ann_bottom > ann_top:
                        bands.append((ann_top - 8, ann_bottom + 8))
    except Exception:
        pass

    return bands


def parse_pdf_properties(pdf_path, county, auction_date):
    try:
        import pdfplumber
    except ImportError:
        print("  ⚠️ Run: pip install pdfplumber")
        return []

    properties = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                page_text   = pg.extract_text() or ""
                withdrawn_ids = _withdrawn_ids_from_images(pg)
                tables = pg.extract_tables()
                if tables:
                    for tbl in tables:
                        properties.extend(
                            _parse_table(tbl, county, auction_date, pdf_path, page_text, withdrawn_ids, pg=pg)
                        )
                    continue
                properties.extend(_parse_text_blocks(page_text, county, auction_date, pdf_path, withdrawn_ids))
    except Exception as e:
        print(f"  ❌ PDF parse error: {e}")

    seen, unique = set(), []
    for p in properties:
        k = p.get("Account Number", "")
        if k and k not in seen:
            seen.add(k)
            unique.append(p)
        elif not k:
            unique.append(p)

    print(f"  ✅ PDF parsed: {len(unique)} properties from {os.path.basename(pdf_path)}")
    return unique


def _parse_table(table, county, auction_date, pdf_path, page_text="", withdrawn_ids=None, pg=None):
    """Parse pdfplumber table — Calhoun/table-format PDFs."""
    if withdrawn_ids is None:
        withdrawn_ids = set()
    properties = []
    if not table or len(table) < 2:
        return properties

    # Precompute WITHDRAWN bands and page words for Y-based detection
    withdrawn_bands = _get_withdrawn_y_bands(pg) if pg else []
    all_page_words  = pg.extract_words() if pg else []

    header_row, data_start = table[0], 1
    for i, row in enumerate(table):
        row_text = " ".join(str(c or "").upper() for c in row)
        if "TRACT" in row_text and ("SUIT" in row_text or "STYLE" in row_text):
            header_row, data_start = row, i + 1
            break

    cols = {}
    for i, h in enumerate(header_row):
        h = str(h or "").upper().strip()
        if "TRACT"       in h: cols["tract"] = i
        if "SUIT"        in h: cols["suit"]  = i
        if "STYLE"       in h: cols["style"] = i
        if "DESCRIPTION" in h or "PROPERTY" in h: cols["desc"] = i
        if "MIN" in h and "BID" in h: cols["bid"] = i
        elif "BID" in h and "WINNING" not in h and "bid" not in cols: cols["bid"] = i

    if not cols:
        cols = {"tract": 0, "suit": 1, "style": 2, "desc": 3, "bid": 4}

    page_upper = page_text.upper()
    withdrawn_positions = [m.start() for m in re.finditer(r'WITHDRAWN', page_upper)]

    # Some Suit #s sell 2-3 tracts at once, and pdfplumber crams all of their
    # Style/Description text into the FIRST tract's row, leaving the other
    # tracts' own rows completely blank (same Suit #, valid Min Bid, nothing
    # else). combined_by_cause remembers that first row's text, split into
    # one segment per "Judgment Through Tax Year: YYYY" block, so the blank
    # sibling rows can claim their own slice instead of falling back to a
    # placeholder with no address/account (see _is_mvba_row in common.py —
    # this is what was losing tracts 10/11 of Suit 2024-1059-6 etc.).
    combined_by_cause = {}

    for row_idx, row in enumerate(table[data_start:], start=data_start):
        if not row or all(not c for c in row):
            continue

        def cell(key, fb=None):
            idx = cols.get(key, fb)
            return str(row[idx] or "").strip() if idx is not None and idx < len(row) else ""

        tract_num    = cell("tract")
        cause_number = cell("suit")
        raw_style    = cell("style")
        min_bid_raw  = cell("bid")

        # A WITHDRAWN stamp overlapping the Suit # cell can bleed a stray
        # "W" into it (e.g. "2025-2493-4W", or "2025-2493W-4" on a sibling
        # row of the same suit) — only strip it when doing so turns the
        # number into MVBA's normal digit-dash shape, so real alphanumeric
        # suit numbers from other counties are left alone.
        if not re.match(r'^\d{4}-\d+-\d+$', cause_number):
            destamped = cause_number.replace('W', '')
            if re.match(r'^\d{4}-\d+-\d+$', destamped):
                cause_number = destamped

        # Normally the desc column is the only thing between STYLE and MIN
        # BID, but pdfplumber occasionally splits it into an extra column
        # (e.g. a WITHDRAWN stamp visually overlapping the cell text pushes
        # part of the description into a neighboring column that's usually
        # blank) — join everything in that span so the real text isn't lost.
        desc_start = cols.get("desc", cols.get("style", 1) + 1)
        bid_idx    = cols.get("bid", len(row) - 1)
        desc_text  = " ".join(
            str(row[i] or "").strip() for i in range(desc_start, min(bid_idx, len(row))) if row[i]
        ).strip()

        if not tract_num or not tract_num[0].isdigit():
            continue
        if "TRACT" in (cause_number or "").upper():
            continue

        # Collect multi-line style by checking continuation rows
        style_text = raw_style
        look_ahead = row_idx + 1
        while look_ahead < len(table):
            next_row = table[look_ahead]
            if not next_row:
                break
            next_tract = str(next_row[cols.get('tract', 0)] or '').strip()
            if next_tract and next_tract[0].isdigit():
                break
            next_style = str(next_row[cols.get('style', 2)] or '').strip()
            next_desc  = str(next_row[cols.get('desc',  3)] or '').strip()
            if next_style:
                style_text = (style_text + ' ' + next_style).strip()
            if next_desc:
                # Always append continuation desc — pdfplumber splits long cells
                # across rows, so the address (after closing paren) may live in
                # row 2 or 3 even when row 1 already has partial desc content.
                desc_text = (desc_text + ' ' + next_desc).strip() if desc_text else next_desc
            look_ahead += 1

        if not style_text.strip() and not desc_text.strip() and cause_number in combined_by_cause:
            entry = combined_by_cause[cause_number]
            if entry["next_idx"] < len(entry["segments"]):
                desc_text  = entry["segments"][entry["next_idx"]]
                style_text = entry["style"]
                entry["next_idx"] += 1
        elif desc_text.strip():
            bounds   = [m.end() for m in re.finditer(r'Judgment Through Tax Year:\s*\d{4}', desc_text)]
            segments = []
            prev = 0
            for end in bounds:
                segments.append(desc_text[prev:end].strip())
                prev = end
            if prev < len(desc_text) and desc_text[prev:].strip():
                if segments:
                    segments[-1] = (segments[-1] + ' ' + desc_text[prev:].strip()).strip()
                else:
                    segments.append(desc_text[prev:].strip())
            if len(segments) > 1:
                combined_by_cause[cause_number] = {"segments": segments, "next_idx": 1, "style": style_text}
                desc_text = segments[0]

        # Check 1: any cell in this row contains WITHDRAWN text
        full_row_text = " ".join(str(c or "") for c in row).upper()
        is_withdrawn  = "WITHDRAWN" in full_row_text

        # Check 2: image-based WITHDRAWN stamp overlaps this row
        if not is_withdrawn and withdrawn_ids:
            if tract_num in withdrawn_ids or (cause_number and cause_number in withdrawn_ids):
                is_withdrawn = True

        # Check 3: WITHDRAWN in full page text near this row's identifiers
        if not is_withdrawn and withdrawn_positions:
            search_keys = [k for k in [tract_num, cause_number] if k and len(k) >= 3]
            for wpos in withdrawn_positions:
                vicinity = page_upper[max(0, wpos - 80): wpos + 80]
                if any(k.upper() in vicinity for k in search_keys):
                    is_withdrawn = True
                    break

        # Extract account early so Check 4 can use it
        account = _extract_account(desc_text)

        # Check 4: Y-band overlap
        if not is_withdrawn and withdrawn_bands and all_page_words:
            acct_digits = re.sub(r'\D', '', account) if account else ''
            lookup_digits = acct_digits if len(acct_digits) >= 4 else re.sub(r'\D', '', cause_number)
            if len(lookup_digits) >= 4:
                for w in all_page_words:
                    w_digits = re.sub(r'\D', '', w['text'])
                    if w_digits and w_digits in lookup_digits and len(w_digits) >= 4:
                        row_y = (w.get('top', 0) + w.get('bottom', 0)) / 2.0
                        for (bt, bb) in withdrawn_bands:
                            if bt <= row_y <= bb:
                                is_withdrawn = True
                                break
                        if is_withdrawn:
                            break

        status = "Withdrawn" if is_withdrawn else "Pending"
        owner  = _extract_owner_from_style(style_text)
        if not account:
            account = f"{cause_number}-T{tract_num}" if cause_number else f"T{tract_num}"
        address = _extract_address(desc_text)
        legal   = _extract_legal(desc_text)
        bid_m   = re.search(r'\$[\d,]+(?:\.\d{2})?', min_bid_raw or desc_text or "")
        min_bid = bid_m.group(0) if bid_m else ""

        prop = _build_prop(make_unique_key(county, account, source="MVBA"),
                           county, cause_number, address, account,
                           legal, owner, min_bid, auction_date, status, pdf_path,
                           item_number=tract_num)
        properties.append(prop)
        _print_prop(tract_num, cause_number, owner, address, min_bid, status)

    return properties


def _parse_text_blocks(full_text, county, auction_date, pdf_path, withdrawn_ids=None):
    """Parse Grimes-style text PDF."""
    if withdrawn_ids is None:
        withdrawn_ids = set()
    properties = []
    blocks = re.split(r'\n(?=\d+\s+(?:TX\d+|\d{2}-\d{2}|\d{4}-\w+))', full_text)

    for block in blocks:
        block = block.strip()
        if len(block) < 20:
            continue
        tract_m = re.match(r'^(\d+)\s+', block)
        if not tract_m:
            continue
        tract_num = tract_m.group(1)
        is_withdrawn = "WITHDRAWN" in block.upper()
        if not is_withdrawn and withdrawn_ids and tract_num in withdrawn_ids:
            is_withdrawn = True
        if not is_withdrawn and "WITHDRAWN" in full_text.upper():
            for wm in re.finditer(r'WITHDRAWN', full_text, re.IGNORECASE):
                vicinity = full_text[max(0, wm.start() - 80): wm.start() + 80].upper()
                if tract_num in vicinity:
                    is_withdrawn = True
                    break
        status = "Withdrawn" if is_withdrawn else "Pending"

        cause_m = re.search(
            r'\b(\d{2}-\d{2}-\d{4}|\d{4}-CV-\d+-\w+|\d{4}-CV-\d+|TX\d{5,}|'
            r'\d{2,3}-\d{2,3}-\d{4,}|[A-Z]{1,3}\d{4,})\b', block)
        cause_number = cause_m.group(1).strip() if cause_m else f"MVBA-{county.upper()}-{tract_num}"

        style_m    = re.search(r'(?:District|Appraisal|County|ISD|City)[^\n]*?\bv\b[^\n]*', block)
        style_text = style_m.group(0).strip() if style_m else ""
        owner      = _extract_owner_from_style(style_text or block)
        legal      = _extract_legal(block)
        address    = _extract_address(block)
        account    = _extract_account(block) or f"{cause_number}-T{tract_num}"

        bid_m   = re.findall(r'\$[\d,]+(?:\.\d{2})?', block)
        min_bid = bid_m[-1] if bid_m else ""

        prop = _build_prop(make_unique_key(county, account, source="MVBA"),
                           county, cause_number, address, account,
                           legal, owner, min_bid, auction_date, status, pdf_path,
                           item_number=tract_num)
        properties.append(prop)
        _print_prop(tract_num, cause_number, owner, address, min_bid, status)

    return properties


# ─── Field extractors ──────────────────────────────────────────────────────

def _extract_owner_from_style(text):
    """
    Extract defendant/owner name from style text like:
      'The County of Hardin, Texas v Jessica S. Rolin AKA Jessica S. Bailey et al'
      'Bell CAD v Lana K. Cox'
      'Tax Appraisal District of\nBell County v Nestor\nMenjivar'  ← pdfplumber multiline

    Returns the FULL name after 'v' with no truncation.
    Flattens mid-word newlines first so names split across lines are joined.
    """
    if not text:
        return ""

    # Flatten newlines that split a name across lines (e.g. "Nestor\nMenjivar")
    text_flat = re.sub(r'(\w)\n([A-Za-z])', r'\1 \2', text)

    m = re.search(r'\bv\.?\s+(.+)', text_flat, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        # Stop at legal description / document keywords to avoid bleed-through
        raw = re.split(
            r'\b(Lot\s|Block\s|Acres|Abstract|Survey|Tract\s|Being\s|'
            r'Judgment|Account|Description|Vol\.|Volume|Document\s*#|'
            r'Official\s+Public|Deed\s+Records|City\s+of|Phase\s)',
            raw, flags=re.IGNORECASE
        )[0]
        raw = raw.rstrip('.,;:-').strip()
        return re.sub(r'\s+', ' ', raw).strip()
    return ""


def _extract_account(text):
    # Some counties (e.g. Eastland) pair a long parcel/geo ID with a short
    # CAD account number, joined by "/" — sometimes with spaces around it
    # from PDF text extraction, e.g. "Account #006510070000000000000 / 22".
    # A flat minimum length on every segment (the old approach) always ends
    # up wrong somewhere: Rusk's plain account numbers can be 4 digits
    # ("#5856"), and the short half of an Eastland pair can be as low as 2
    # digits ("/ 22") — both got silently dropped, falling back to the
    # "{cause_number}-T{tract_num}" placeholder instead of the real account.
    # Fix: only require a minimum length on the FIRST segment; once a "/"
    # has been seen, that's already unambiguous evidence it's a deliberate
    # second account segment, not stray text, so no length floor applies.
    def _first_match(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return ""
        parts = re.split(r'\s*/\s*', m.group(1).strip())
        parts = [p.strip().lstrip('#') for p in parts if p.strip()]
        return "/".join(parts[:3])

    result = _first_match(r'Accounts?\s*#?\s*([\w\-]{3,}(?:\s*/\s*[\w\-]+)*)')
    if result:
        return result
    return _first_match(r'Acct\.?\s*#?\s*([\w\-]{3,}(?:\s*/\s*[\w\-]+)*)')


def _extract_address(text):
    """
    Extract street address from MVBA PDF description text.

    Core rule: legal description ends at "County, Texas" — address follows.

    Priority order:
    1. Text after closing parenthesis ')' before Account #/Judgment
    2. Text after 'County, Texas,' comma (legal ends, address begins)
    3. Text after '; ' semicolon
    4. Standard street-suffix patterns (zip+4 supported)
    5. IH/US/SH highway addresses
    6. Named street without suffix
    7. Label-based fallback

    Newline handling: pdfplumber sometimes wraps a long address across two lines
    within the same cell (e.g. "7787 Scenic\nLakeview Dr, Salado, Texas").
    We pre-flatten word-boundary newlines so the full address is captured.
    """
    if not text:
        return ""

    # ── Flatten intra-address newlines ────────────────────────────────────
    # Collapse \n that appear between word characters (mid-address line wraps).
    # "7787 Scenic\nLakeview Dr"  → "7787 Scenic Lakeview Dr"
    # Also collapse ",\n" which pdfplumber uses when a cell wraps after a comma:
    # "901 S Main St,\nBelton, Texas" → "901 S Main St, Belton, Texas"
    text_flat = re.sub(r'(\w)\n([A-Za-z])', r'\1 \2', text)
    text_flat = re.sub(r',\s*\n\s*', ', ', text_flat)

    def clean(addr):
        addr = re.split(r'\s*;\s*Account', addr, flags=re.IGNORECASE)[0]
        addr = re.split(r'\s*Account\s*#', addr, flags=re.IGNORECASE)[0]
        addr = re.split(r'\s*Judgment\s+Through', addr, flags=re.IGNORECASE)[0]
        addr = addr.strip().rstrip('.,;').strip()
        return re.sub(r'\s+', ' ', addr).strip()

    def _try_paren(t):
        # ── Priority 1: Address after closing parenthesis ')' ─────────────
        # e.g. "...Deed Records, Hardin County, Texas), S Canal Rd Account #..."
        # e.g. "...Bell County, Texas), 21236 S. IH 35 Service Rd, Salado, Texas;"
        m = re.search(r'\)\s*,?\s*([A-Za-z0-9][^\n(]{8,120})', t, re.IGNORECASE)
        if m:
            candidate = clean(m.group(1))
            if len(candidate) >= 5 and (
                re.search(r'\d', candidate) or
                re.match(r'^(N|S|E|W|North|South|East|West)\s', candidate, re.IGNORECASE)
            ):
                return candidate
        return None

    # Try on flattened text first, then original (catches both cases)
    result = _try_paren(text_flat) or _try_paren(text)
    if result:
        return result

    # ── Priority 2: Address after "County, Texas," ────────────────────────
    # e.g. "...Brown County, Texas, 204 Q Hillcrest Road -Mobile Home Park, Early, Texas"
    # e.g. "...Bell County, Texas, 101 Oakhill, Killeen, Texas"
    for t in (text_flat, text):
        county_end = re.search(
            r'\b\w+\s+County,\s*Texas[,)]\s*,?\s*([A-Za-z0-9][^\n(]{5,120})',
            t, re.IGNORECASE
        )
        if county_end:
            candidate = clean(county_end.group(1))
            if (len(candidate) >= 5
                    and re.search(r'[A-Za-z]', candidate)
                    and not candidate.startswith('(')
                    and 'Volume' not in candidate
                    and 'Instrument' not in candidate):
                return candidate

    # ── Priority 3: Address after semicolon ──────────────────────────────
    # e.g. "); 700 S IH 35, Belton, Texas"
    semi_m = re.search(
        r';\s*(\d+\s+[A-Za-z][^\n;(]{5,80}(?:,\s*[A-Za-z][a-z]+){1,2})',
        text_flat, re.IGNORECASE
    )
    if semi_m:
        candidate = clean(semi_m.group(1))
        if len(candidate) >= 8 and re.search(r'\d', candidate):
            return candidate

    # ── Priority 4: Standard street suffix patterns ───────────────────────
    pats = [
        # Full address with city + Texas + zip (supports zip+4 like 76520-2508)
        r'(\d+\s+(?:[NSEW]\s+)?[\w\s]{2,40}?'
        r'(?:St|Ave|Dr|Rd|Ln|Blvd|Hwy|FM|CR|Way|Circle|Loop|LP|Pkwy|Expy|Pass|Trail|Trl|Ct|Cir)'
        r'[^,\n]{0,30},\s*[A-Za-z][a-z]+(?:,\s*Texas\s+\d{5}(?:-\d{4})?)?)',

        # Address ending with just city
        r'(\d+\s+(?:[NSEW]\s+)?[\w\s]{2,30}?'
        r'(?:St|Ave|Dr|Rd|Ln|Blvd|Hwy|FM|CR|Way|Circle|Loop|LP|Pkwy|Expy|Pass|Trail|Trl|Ct|Cir)'
        r'[^,\n]{0,20})',

        # FM/CR/Hwy rural addresses
        r'(\d+\s+(?:FM|CR|Hwy|Highway|County Road)\s+\d+[^,\n]{0,40})',

        # Bare numbered + directional
        r'(\d+\s+(?:North|South|East|West|N\.|S\.|E\.|W\.)\s+\d+\w*\s+'
        r'(?:Street|Avenue|Road|Drive)[^,\n]{0,30})',
    ]
    for pat in pats:
        m = re.search(pat, text_flat, re.IGNORECASE)
        if m:
            addr = clean(m.group(1))
            if len(addr) >= 8 and re.search(r'\d', addr):
                return addr

    # ── Priority 5: IH/US/SH highway addresses ───────────────────────────
    # e.g. "700 S IH 35, Belton" or "20400 IH 35, Salado, Texas"
    hwy_m = re.search(
        r'(\d+\s+(?:[NSEW]\s+)?(?:IH|US|SH|FM|CR|Hwy|Highway|County\s+Road)\s*\d+[^,\n;(]{0,40})',
        text_flat, re.IGNORECASE
    )
    if hwy_m:
        addr = clean(hwy_m.group(1))
        if len(addr) >= 8:
            return addr

    # ── Priority 6: Named street without suffix ───────────────────────────
    # e.g. "8565 Little Mexico, Temple, Texas"
    named_m = re.search(
        r'(\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4},\s*[A-Z][a-z]+(?:,\s*Texas\s*\d{0,5})?)',
        text_flat
    )
    if named_m:
        addr = clean(named_m.group(1))
        if len(addr) >= 10 and re.search(r'\d', addr):
            return addr

    # ── Priority 7: Label-based fallback ─────────────────────────────────
    label_m = re.search(
        r'(?:located\s+at|address[:\s]+|,\s*)(\d+\s+[A-Za-z][^\n,;(]{5,80})',
        text_flat, re.IGNORECASE
    )
    if label_m:
        addr = clean(label_m.group(1))
        if len(addr) >= 8 and re.search(r'\d', addr):
            return addr

    return ""


def _extract_legal(text):
    text = re.sub(r'^\d+\s+\S+\s+', '', text.strip())
    text = re.sub(r'^[^\n]+\bv\b[^\n]+\n?', '', text, flags=re.IGNORECASE)
    text = re.split(r'Account\s*#', text, flags=re.IGNORECASE)[0]
    text = re.split(r'Judgment\s+Through', text, flags=re.IGNORECASE)[0]
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return ' '.join(lines[:6]).strip()[:300]


def _build_prop(uk, county, cause_number, address, account, legal,
                owner, min_bid, auction_date, status, source_path, item_number=""):
    link = (source_path if source_path.startswith("http")
            else f"https://mvbalaw.com/wp-content/TaxUploads/{os.path.basename(source_path)}")
    return {
        "Unique Key": uk, "Source": "MVBA", "County": county.upper(),
        "Cause Number": cause_number, "Item Number": item_number, "Link": link,
        "Auction Date": auction_date, "Status": status,
        "Min Bid": min_bid, "Adjusted Value": "",
        "Property Address": address, "Account Number": account,
        "Legal Description": legal, "Owner Name": owner,
        "Buyer Name": "", "Sold Amount": "", "Winning Bid": "",
        "Sale Date": "", "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Zillow": _make_zillow_link(address),
        "Satellite View": _make_satellite_link(address),
    }


def _print_prop(tract, cause, owner, address, min_bid, status):
    flag = "⚠️ " if status == "Withdrawn" else "  "
    print(f"  {flag}[{tract}] {cause} | '{owner[:35]}' | '{address[:35]}' | {min_bid} | {status}")


def _make_zillow_link(address):
    if not address or len(address) < 5: return ""
    import urllib.parse
    return f"https://www.zillow.com/homes/{urllib.parse.quote(address)}_rb/"


def _make_satellite_link(address):
    if not address or len(address) < 5: return ""
    import urllib.parse
    return f"https://www.google.com/maps?q={urllib.parse.quote(address)}&t=k"


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2b — MVBA ONLINE AUCTION SCRAPER (mvbataxsales.com)
# ═══════════════════════════════════════════════════════════════════════════

_MVBA_GALLERY_JS = r"""
() => {
    var results = [];
    var seen = {};

    var LOT_LABELS = ['lot details', 'lot detail', 'view lot', 'bid now', 'view item'];
    document.querySelectorAll('a, button').forEach(function(el) {
        var txt = (el.innerText || '').trim().toLowerCase();
        if (LOT_LABELS.indexOf(txt) === -1) return;
        var href = el.href || '';
        if (!href && el.tagName === 'BUTTON') {
            var parentLink = el.closest('a[href]');
            if (parentLink) href = parentLink.href;
            if (!href) { var form = el.closest('form'); if (form) href = form.action || ''; }
        }
        if (!href || seen[href]) return;
        seen[href] = true;
        var card = el.closest(
            '[class*="lot-item"],[class*="parcel"],[class*="auction-item"],[class*="item-card"]'
        ) || el.parentElement || el;
        var cardText = (card.innerText || '').substring(0, 1000);
        var lotM  = cardText.match(/Lot #?\s*(\w+)/i);
        var lot   = lotM ? lotM[1] : '';
        var isWithdrawn = cardText.toUpperCase().includes('WITHDRAWN');
        var bidM  = (cardText.match(/(?:Starting|Current)\s+Bid[^$]*\$([\d ,]+)/i) || [])[1] || '';
        results.push({
            href: href, card_text: cardText, lot: lot,
            card_status: isWithdrawn ? 'Withdrawn' : 'Pending',
            card_bid: bidM ? ('$' + bidM.trim().replace(/\s/g,'')) : ''
        });
    });

    if (results.length === 0) {
        document.querySelectorAll('a[href*="/lot/"],a[href*="/item/"],a[href*="lot-details"]')
        .forEach(function(a) {
            // Skip social share links (Facebook, Pinterest, X, etc.)
            // Their href is e.g. facebook.com/sharer?u=mvbataxsales.com/item/...
            // We only want direct mvbataxsales.com links.
            try { if (new URL(a.href).hostname !== 'www.mvbataxsales.com') return; }
            catch(e) { return; }
            if (seen[a.href]) return;
            seen[a.href] = true;
            var card = a.closest('div,li,article') || a;
            var cardText = (card.innerText || '').substring(0, 600);
            var lotM = cardText.match(/Lot #?\s*(\w+)/i);
            var lot  = lotM ? lotM[1] : '';
            var isWithdrawn = cardText.toUpperCase().includes('WITHDRAWN');
            var bidM = (cardText.match(/(?:Starting|Current)\s+Bid[^$]*\$([\d ,]+)/i) || [])[1] || '';
            results.push({
                href: a.href, card_text: cardText, lot: lot,
                card_status: isWithdrawn ? 'Withdrawn' : 'Pending',
                card_bid: bidM ? ('$' + bidM.trim().replace(/\s/g,'')) : ''
            });
        });
    }

    return results;
}
"""


def _normalize_lot_number(raw):
    """
    MVBA online 'Lot #' → Item Number.
    Sequential lot numbers are zero-padded (e.g. '0001', '0038') — strip the
    padding down to a min-2-digit number: '0001' -> '01', '0038' -> '38'.
    Non-sequential item codes (e.g. '99990002') have no leading zeros to
    strip, so they pass through unchanged as the full number.
    """
    if not raw or not raw.isdigit():
        return raw
    return str(int(raw)).zfill(2)


def _get_results_range(page):
    """
    Read the gallery's own "X-Y of Z results" counter — the authoritative
    signal for how many cards THIS page should have (end - start + 1), used
    to tell a fully-hydrated page apart from a partially-rendered one.
    """
    try:
        body = page.inner_text("body")
        m = re.search(r'(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)\s+results', body, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    except Exception:
        pass
    return None


def scrape_mvba_online_auction(page, auction_url, county, auction_date):
    """
    Scrape MVBA bidgallery → click each 'Lot Details' → parse detail text.
    """
    print(f"\n  🌐 MVBA Online: {auction_url[:70]}")
    properties = []

    try:
        page.goto(auction_url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        _dismiss_popups(page)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        _dismiss_popups(page)

        current_url = page.url.lower()
        body_text   = page.inner_text("body")
        body_lower  = body_text.lower()

        # mvbataxsales.com's WAF sometimes serves a bot-protection stub
        # (a bare '{"status":"invalid"}' JSON body, HTTP 400) instead of the
        # real Angular page — before the app JS has even loaded. Retry a few
        # times with fresh navigations; it's usually transient.
        retry = 0
        while retry < 3 and (len(body_text.strip()) < 50 or '"status":"invalid"' in body_lower):
            retry += 1
            print(f"  ⚠️ Blocked/empty response from site (attempt {retry}/3) — retrying...")
            page.wait_for_timeout(2500 * retry)
            page.goto(auction_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            _dismiss_popups(page)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            _dismiss_popups(page)
            current_url = page.url.lower()
            body_text   = page.inner_text("body")
            body_lower  = body_text.lower()

        if len(body_text.strip()) < 50 or '"status":"invalid"' in body_lower:
            print(f"  ❌ Site still blocked after 3 retries — skipping {county.upper()} this run")
            return []

        # Use exact path-segment checks — /account appears in item slugs like
        # /item/account-no-12345/ which is NOT a login page.
        if any(current_url.rstrip('/').endswith(x) or f'{x}/' in current_url
               for x in ['/login', '/signin', '/register']):
            print(f"  ⚠️ Redirected to login page ({page.url}) — site requires registration")
            return []
        if "must be logged in" in body_lower or "please log in" in body_lower or \
           "sign in to" in body_lower or ("login" in body_lower and len(body_text.strip()) < 500):
            print(f"  ⚠️ Login wall detected — site requires registration")
            return []

        # If redirected to a single item page instead of the gallery, navigate
        # back to the auction root so the gallery JS can find all lots. Going
        # to the root (its own Angular client-side redirect eventually lands
        # on /bidgallery/) is more reliable than requesting /bidgallery/
        # directly — a fresh direct request to /bidgallery/ has been observed
        # bouncing right back to a random item page. Landing back on an item
        # page is silent poison: _get_mvba_total_pages() then matches that
        # page's own "NEXT ITEM"/"PREVIOUS ITEM" arrows as if they were
        # gallery pagination, and the scraper "walks" the item ring picking
        # up real hrefs — so owner/address/bid all come through fine — but
        # every card_text is just "PREVIOUS ITEM\nNEXT ITEM", so the Lot #
        # regex never matches and Item Number ends up blank for every lot.
        # Retry a few times since the bounce-back can recur; this has been
        # observed happening identically even in a brand-new browser context
        # (same decoy item served every time), which points to a server/CDN-
        # side anti-bot cooldown rather than anything fixable by retrying
        # harder client-side — so if it's still happening after retries,
        # give up cleanly instead of scraping corrupted data from the decoy
        # item's own prev/next links.
        if '/item/' in current_url:
            base_auction = re.sub(r'/item/.*', '/', page.url)
            print(f"  🔄 Item-page redirect detected — navigating to auction root: {base_auction[:70]}")
            for _attempt in range(3):
                page.goto(base_auction, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                _dismiss_popups(page)
                current_url = page.url.lower()
                if '/item/' not in current_url:
                    break
                print(f"  ⚠️ Still on an item page after navigating to auction root — retrying...")
                page.wait_for_timeout(1500)

            if '/item/' in current_url:
                print(f"  ❌ Site keeps redirecting to a decoy item page instead of the "
                      f"gallery (likely an anti-bot cooldown) — skipping {county.upper()} this run")
                return []

            body_text   = page.inner_text("body")
            body_lower  = body_text.lower()

        all_items      = []
        _seen_lot_urls = set()  # dedup across pages (prevents ?page=N same-content duplicates)
        expected_total = None

        # A single gallery pass (page 1 -> last page via the dropdown) has
        # turned out to be unreliable in ways that more per-page waiting
        # doesn't fix: even with the results-counter checks below, a given
        # run can still land on a page that only partially rendered (this
        # reproduced identically across separate process runs, so it isn't
        # pure timing jitter — something about repeated dropdown selections
        # in one session occasionally starves a later page's own update).
        # Rather than chase that further, treat an incomplete pass as
        # recoverable: reload the gallery from scratch and do another full
        # pass, since _seen_lot_urls carries over and only genuinely missing
        # lots get added. This is what actually gets Bowie's 60 lots (vs 18)
        # reliably instead of only on a lucky run.
        for pass_num in range(3):
            if pass_num > 0:
                print(f"    🔁 Pass {pass_num + 1}/3 — only {len(all_items)}/{expected_total} lots "
                      f"collected so far, reloading gallery from page 1...")
                try:
                    page.goto(auction_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    _dismiss_popups(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"    ⚠️ Reload for retry pass failed ({e}) — stopping retries")
                    break

            total_pages = _get_mvba_total_pages(page)
            print(f"    📊 Gallery: {total_pages} page(s) | {page.url[:55]}")

            _initial_rng = _get_results_range(page)
            per_page     = (_initial_rng[1] - _initial_rng[0] + 1) if _initial_rng else None
            if expected_total is None and _initial_rng:
                expected_total = _initial_rng[2]

            for gallery_page in range(1, total_pages + 1):

                if gallery_page > 1:
                    navigated = False

                    try:
                        dropdowns = page.locator("select")
                        for idx in range(dropdowns.count()):
                            opts = dropdowns.nth(idx).locator("option").all_inner_texts()
                            if str(gallery_page) in [o.strip() for o in opts]:
                                dropdowns.nth(idx).select_option(str(gallery_page))
                                page.wait_for_timeout(1500)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=8000)
                                except Exception:
                                    pass
                                page.wait_for_timeout(1500)
                                navigated = True
                                break
                    except Exception:
                        pass

                    if not navigated:
                        try:
                            nxt = page.locator(
                                "a:has-text('Next'), a:has-text('Next »'), "
                                "a:has-text('Next»'), button:has-text('Next')"
                            )
                            if nxt.count() > 0 and nxt.first.is_enabled():
                                nxt.first.click()
                                page.wait_for_timeout(1500)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=8000)
                                except Exception:
                                    pass
                                page.wait_for_timeout(1500)
                                navigated = True
                            else:
                                print(f"    ✅ No Next button — last page at {gallery_page - 1}")
                                break
                        except Exception:
                            pass

                    if not navigated:
                        try:
                            base   = auction_url.split("?")[0].rstrip("/")
                            pg_url = f"{base}?page={gallery_page}"
                            page.goto(pg_url, timeout=10000)
                            page.wait_for_timeout(2000)
                            navigated = True
                        except Exception:
                            pass

                    if not navigated:
                        print(f"    ⚠️ Cannot navigate to page {gallery_page} — stopping")
                        break

                    _dismiss_popups(page)

                    # Selecting page N and selecting page N+1 seconds later can
                    # race the site's own AJAX calls: if page N's response is
                    # still in flight when page N+1 is requested, the two
                    # responses can land out of order and leave the gallery
                    # showing a corrupted mix. Block on the results counter's
                    # own start index actually reaching this page's expected
                    # range before doing anything else, so we never read cards
                    # while a stale/in-flight response is still on screen.
                    if per_page is not None:
                        expected_start = (gallery_page - 1) * per_page + 1
                        for _range_wait in range(8):
                            rng = _get_results_range(page)
                            if rng and rng[0] == expected_start:
                                break
                            page.wait_for_timeout(1500)
                        else:
                            print(f"    ⚠️ Results counter never reached page {gallery_page}'s "
                                  f"range (expected start {expected_start}) — proceeding anyway")

                print(f"    🗂️  Page {gallery_page}/{total_pages}...")

                # The results counter ("X-Y of Z results") updates as soon as
                # the page/dropdown navigation lands, well before Angular has
                # finished ng-repeat-ing all the lot cards into the DOM — so
                # it tells us exactly how many cards THIS page should end up
                # with once fully hydrated. Without that target, a card-eval
                # that runs mid-render returns a small but non-empty result
                # (e.g. 2 of 12 cards), indistinguishable from "the page
                # genuinely only has 2 lots".
                rng = _get_results_range(page)
                expected_count = (rng[1] - rng[0] + 1) if rng else None

                # Judge readiness by cards NOT already in _seen_lot_urls, not
                # raw card count — mid-transition the DOM can hold a mix of
                # leftover cards from the page we just left plus a few
                # newly-arrived ones, and that mix can already total 12
                # "cards" while being mostly stale.
                items = page.evaluate(_MVBA_GALLERY_JS)
                new_hrefs_this_page = {it['href'] for it in items if it.get('href') and it['href'] not in _seen_lot_urls}
                for _render_attempt in range(8):
                    if expected_count is not None:
                        if len(new_hrefs_this_page) >= expected_count:
                            break
                    elif items:
                        break
                    page.wait_for_timeout(1500)
                    items = page.evaluate(_MVBA_GALLERY_JS)
                    refreshed_new = {it['href'] for it in items if it.get('href') and it['href'] not in _seen_lot_urls}
                    if refreshed_new and refreshed_new == new_hrefs_this_page:
                        # Plateaued (no new cards across a wait) — either this really
                        # is all there is (e.g. a short last page), or the render is
                        # stuck; either way, more waiting won't help further.
                        break
                    new_hrefs_this_page = refreshed_new or new_hrefs_this_page

                if expected_count is not None and len(new_hrefs_this_page) < expected_count:
                    print(f"    ⚠️ Only {len(new_hrefs_this_page)}/{expected_count} new cards rendered "
                          f"on page {gallery_page} after retries — using what loaded")

                if items:
                    new_items = [it for it in items if it.get('href') and it['href'] not in _seen_lot_urls]
                    new_count = len(new_items)
                    for it in new_items:
                        _seen_lot_urls.add(it['href'])
                        all_items.append(it)
                    print(f"    ✅ {new_count} new lots on page {gallery_page} "
                          f"({len(items) - new_count} dupes skipped)")
                    if new_count == 0:
                        if gallery_page == 1 and pass_num > 0:
                            # Page 1 of a retry pass always re-shows the same
                            # items a prior pass already collected — that's
                            # expected, not a sign pagination is exhausted, so
                            # keep going to page 2 instead of stopping here.
                            print(f"    ➡️  Page 1 all-dupes (expected on a retry "
                                  f"pass) — continuing to page 2")
                        else:
                            print(f"    ✅ No new lots — all pages done")
                            break
                else:
                    print(f"    ⚠️ 0 lots on page {gallery_page}")
                    if gallery_page == 1:
                        preview = page.inner_text("body")[:400].replace('\n', ' ').strip()
                        print(f"    Page URL  : {page.url}")
                        print(f"    Page text : {preview}")
                    break  # 0 items on any page = done

            if expected_total is None or len(all_items) >= expected_total:
                break

        print(f"  📊 Total unique lots to process: {len(all_items)}")

        for i, item in enumerate(all_items):
            href        = item.get("href", "")
            card_text   = item.get("card_text", "")
            lot_num     = _normalize_lot_number(item.get("lot", str(i+1)))
            card_status = item.get("card_status", "Pending")
            card_bid    = item.get("card_bid", "")

            print(f"    [{i+1}/{len(all_items)}] Lot #{lot_num} — ", end="")

            prop = None

            if href and href.startswith("http"):
                # "Execution context was destroyed" (an unexpected navigation
                # firing mid-evaluate, e.g. a stray redirect/reload on the lot
                # page) is transient — one retry with a fresh goto clears it
                # rather than losing the lot entirely.
                for detail_attempt in range(2):
                    try:
                        page.goto(href, timeout=40000, wait_until="domcontentloaded")
                        try:
                            page.wait_for_load_state("networkidle", timeout=12000)
                        except Exception:
                            pass
                        page.wait_for_timeout(2000)
                        _dismiss_popups(page)

                        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                        page.wait_for_timeout(2000)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2 / 3)")
                        page.wait_for_timeout(2000)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(2000)

                        try:
                            detail_toggles = page.locator(
                                "h2:has-text('Details'), h3:has-text('Details'), "
                                "[class*='accordion']:has-text('Details'), "
                                "div:has-text('Details') > button, "
                                "button:has-text('Details'), "
                                ".toggle:has-text('Details'), "
                                "a:has-text('Details')"
                            )
                            for ti in range(detail_toggles.count()):
                                tog = detail_toggles.nth(ti)
                                try:
                                    tog_text = tog.inner_text().strip()
                                    if "Transaction" in tog_text or "Disclaimer" in tog_text:
                                        continue
                                    if tog.is_visible():
                                        tog.click()
                                        page.wait_for_timeout(1000)
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(600)

                        detail_text = page.inner_text("body")
                        prop = parse_mvba_online_detail(detail_text, href, county, auction_date, lot_number=lot_num)
                        break
                    except Exception as e:
                        prop = None
                        if detail_attempt == 0:
                            print(f"\n      ⚠️ Detail page failed ({e}) — retrying...")
                            page.wait_for_timeout(2000)
                            continue
                        print(f"\n      ❌ Detail page failed again ({e}) — skipping lot")

                try:
                    if "bidgallery" not in page.url:
                        page.goto(auction_url, timeout=15000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1000)
                except Exception:
                    pass
            else:
                print("no href — skipping")
                continue

            if prop:
                # Gallery card already detected WITHDRAWN — trust it even if
                # detail page didn't repeat the banner (some pages omit it).
                if card_status == "Withdrawn":
                    prop["Status"] = "Withdrawn"
                properties.append(prop)
                print(f"Acct={prop['Account Number']} | "
                      f"Cause={prop['Cause Number']} | "
                      f"Owner='{prop['Owner Name'][:25]}' | "
                      f"Bid={prop['Min Bid']} | {prop['Status']}")
            else:
                print("skipped (no Account No. found)")

    except Exception as e:
        print(f"  ❌ MVBA Online scraper error: {e}")
        import traceback; traceback.print_exc()

    print(f"  ✅ MVBA Online: {len(properties)} properties")
    return properties


def parse_mvba_online_detail(text, source_url, county, auction_date, lot_number=""):
    """Parse MVBA online detail page text."""
    if not text or len(text.strip()) < 15:
        return None

    status = "Withdrawn" if re.search(r'\bWITHDRAWN\b', text, re.IGNORECASE) else "Pending"

    acct_start = re.search(r'Account\s+No\.', text, re.IGNORECASE)

    if not acct_start and ":::::" not in text:
        return None

    lot_text = text[acct_start.start():] if acct_start else text

    acct_m = re.search(
        r'Account\s+No\.?\s*([\d/\-A-Za-z]{2,})',
        lot_text, re.IGNORECASE
    )
    account_number = acct_m.group(1).strip() if acct_m else ""

    if ":::::" in lot_text:
        before_sep = lot_text.split(":::::")[0]
        after_sep  = lot_text.split(":::::", 1)[1]
    else:
        suit_pos = re.search(r'Suit\s+No\.', lot_text, re.IGNORECASE)
        if suit_pos:
            before_sep = lot_text[:suit_pos.start()]
            after_sep  = lot_text[suit_pos.start():]
        else:
            before_sep = lot_text
            after_sep  = ""

    legal_desc = ""
    if before_sep:
        legal_raw = re.sub(
            r'Account\s+No\.?\s*[\d/\-A-Za-z]+\s*[,\-–]?\s*',
            '', before_sep.strip(), flags=re.IGNORECASE, count=1
        ).strip().lstrip(',-').strip()
        legal_desc = re.sub(r'\s+', ' ', legal_raw).strip()[:400]

    cause_m = re.search(r'Suit\s+No\.?\s*([\w\d\-]+)', after_sep or lot_text, re.IGNORECASE)
    cause_number = cause_m.group(1).strip() if cause_m else ""

    owner_name = ""
    style_text = ""
    if after_sep:
        style_raw = re.sub(
            r'^Suit\s+No\.?\s*[\w\d\-]+,?\s*',
            '', after_sep.strip(), flags=re.IGNORECASE
        ).strip()
        style_text = re.split(r',?\s*Judgment\s+Through', style_raw, flags=re.IGNORECASE)[0].strip()

        v_m = re.search(r'\bv\.?\s+(.+)$', style_text, re.IGNORECASE)
        if v_m:
            owner_name = v_m.group(1).rstrip(',').strip()

    bid_m = re.search(r'(?:Starting|Current)\s+Bid[:\s]+\$?([\d,]+(?:\.\d{2})?)', text, re.IGNORECASE)
    if bid_m:
        raw = bid_m.group(1).replace(",", "")
        min_bid = f"${raw}" if "." in raw else f"${raw}.00"
    else:
        bids = re.findall(r'\$[\d,]+\.\d{2}', text)
        min_bid = bids[0] if bids else ""

    addr_m = re.search(r'Approximate\s+Address[:\s]+([^\n]{5,120})', text, re.IGNORECASE)
    address = addr_m.group(1).strip().rstrip('.') if addr_m else ""

    # High Bidder / Current Bid summary box (top of the Lot Details page —
    # same numbers shown as the first row once the Bid History table is
    # opened, e.g. High Bidder "7700" / Current Bid "$77,000.00"). MVBA
    # renders this box in two layouts depending on the page: the "(bids: N)"
    # count sits either before or after the dollar amount, so skip over it
    # with a bounded "any chars up to the next $" gap instead of assuming
    # one fixed order.
    hb_m = re.search(r'High\s+Bidder\s*:?\s*[\r\n]*\s*([A-Za-z0-9/\-]+)', text, re.IGNORECASE)
    buyer_name = hb_m.group(1).strip() if hb_m and hb_m.group(1).strip().upper() not in ("N/A", "NONE", "-") else ""

    cb_m = re.search(r'Current\s+Bid\s*:?[^\$]{0,40}\$\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    winning_bid = f"${cb_m.group(1)}" if cb_m else ""
    if not buyer_name:
        winning_bid = ""

    # "High Bidder" shows the current leader even while a lot is still live,
    # so only treat it as won once the page also shows the auction has
    # actually closed — either "Bidding Ended: <timestamp>" or
    # "Time Remaining: Closed", MVBA uses both phrasings depending on layout.
    # smart_save() only ever persists Buyer Name/Sold Amount when Status is
    # the normalized "Sold" (see common.py SOLD_STATUSES), so without this
    # the fields extracted above would be silently dropped on every save.
    is_closed = bool(re.search(r'Bidding\s+Ended', text, re.IGNORECASE)) or \
                bool(re.search(r'Time\s+Remaining\s*:?\s*[\r\n]*\s*Closed', text, re.IGNORECASE))
    if buyer_name and status != "Withdrawn" and is_closed:
        status = "Sold"

    if not account_number:
        acct2 = re.search(r'(?:Acct|Account)\.?\s*(?:No\.?)?[#:\s]*([\d/]+)', text, re.IGNORECASE)
        if acct2:
            account_number = acct2.group(1).strip()
        else:
            # Python's built-in hash() is randomized per-process (PYTHONHASHSEED),
            # so it produced a different fallback ID for the same URL on every
            # run — causing the same lot to be re-added as a "new" duplicate
            # each scrape. hashlib.md5 is stable across runs/processes.
            stable_hash = int(hashlib.md5(source_url.encode("utf-8")).hexdigest(), 16) % 99999
            account_number = f"MVBA-{county.upper()}-{stable_hash}"

    if not cause_number:
        cause_number = f"MVBA-ONLINE-{county.upper()}"

    uk = make_unique_key(county, account_number, source="MVBA")

    return {
        "Unique Key": uk, "Source": "MVBA", "County": county.upper(),
        "Cause Number": cause_number, "Item Number": lot_number, "Link": source_url,
        "Auction Date": auction_date, "Status": status,
        "Min Bid": min_bid, "Adjusted Value": "",
        "Property Address": address, "Account Number": account_number,
        "Legal Description": legal_desc, "Owner Name": owner_name,
        "Buyer Name": buyer_name, "Sold Amount": winning_bid, "Winning Bid": winning_bid,
        "Sale Date": "", "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Zillow": _make_zillow_link(address),
        "Satellite View": _make_satellite_link(address),
    }


def _get_mvba_total_pages(page):
    try:
        # An item detail page has its own "NEXT ITEM"/"PREVIOUS ITEM" arrows,
        # which the loose has-text('Next') check below would otherwise mistake
        # for gallery pagination — walking the item ring instead of the real
        # gallery pages and leaving every lot's Lot # unextractable (see the
        # item-page-redirect handling in scrape_mvba_online_auction).
        if '/item/' in page.url.lower():
            return 1

        # The results-counter text can lag a beat behind a fresh page load
        # (e.g. right after a reload), so a single immediate read can miss it
        # and fall through to the much less precise Next-button/dropdown
        # fallbacks below (dropdown-size fallback undercounts on the retry
        # path since the dropdown holds page NUMBERS not page COUNT once
        # already navigated, and the Next-button fallback returns a blind
        # upper-bound guess of 50). Retry a few times before giving up on it.
        m = None
        for _wait in range(4):
            body = page.inner_text("body")
            m = re.search(r'(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)\s+results', body, re.IGNORECASE)
            if m:
                break
            page.wait_for_timeout(1000)

        if m:
            per_page = int(m.group(2)) - int(m.group(1)) + 1
            total    = int(m.group(3))
            pages    = max(1, -(-total // per_page))
            print(f"    📊 Results: {total} total, ~{per_page}/page → {pages} pages")
            return pages

        dropdowns = page.locator("select")
        for i in range(dropdowns.count()):
            opts = dropdowns.nth(i).locator("option").all_inner_texts()
            nums = [o.strip() for o in opts if o.strip().isdigit()]
            if nums:
                pages = max(int(n) for n in nums)
                print(f"    📊 Page dropdown: {pages} pages")
                return pages

        nxt = page.locator("a:has-text('Next'), a:has-text('Next »'), button:has-text('Next')")
        if nxt.count() > 0 and nxt.first.is_enabled():
            lot_count = page.locator("a:has-text('Lot Details'), button:has-text('Lot Details')").count()
            print(f"    📊 Next button found, {lot_count} lots/page — will stop when no Next")
            return 50  # upper bound; loop breaks early when Next button disappears or 0 items

        return 1

    except Exception as e:
        print(f"    ⚠️ Page count detection error: {e}")
        return 1


def _dismiss_popups(page):
    for txt in ["By continuing", "I acknowledge", "Continue", "OK", "Accept", "I AGREE"]:
        try:
            btn = page.locator(
                f"button:has-text('{txt}'), input[value='{txt}'], a:has-text('{txt}')"
            )
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(600)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def run_mvba(target_month, target_year, db, csv_rows, preloaded_listings=None):
    """
    Main MVBA entry point.

    Args:
        preloaded_listings: optional pre-filtered list from main.py county selection.
                            If None, fetches and parses all listings as usual.
    """
    print(f"\n{'='*50}")
    print(f"  🟡 MVBA SCRAPER — {MONTH_NUM_TO_NAME[target_month]} {target_year}")
    print(f"{'='*50}")

    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    if preloaded_listings is not None:
        listings = preloaded_listings
        if not listings:
            print(f"  ⚠️ No listings for selected counties")
            return stats
        print(f"  ✅ Using {len(listings)} pre-filtered listing(s)")
    else:
        print(f"  🌐 Fetching MVBA listings page...")
        raw_links = fetch_mvba_page_with_playwright()
        if not raw_links:
            print("  ❌ Could not fetch MVBA page")
            return stats
        listings = parse_mvba_listings_for_month(raw_links, target_month, target_year)
        if not listings:
            print(f"  ⚠️ No MVBA listings for {MONTH_NUM_TO_NAME[target_month]} {target_year}")
            return stats

    pdf_listings    = [l for l in listings if l["online_type"] == "PDF"]
    online_listings = [l for l in listings if l["online_type"] == "MVBA_ONLINE"]

    print(f"\n  Breakdown → PDF:{len(pdf_listings)} | "
          f"MVBA_Online:{len(online_listings)} | GovEase: SKIPPED")

    # ── STEP 1: PDFs ─────────────────────────────────────────────────────
    if pdf_listings:
        print(f"\n{'='*40}")
        print(f"  📄 STEP 1: PDFs ({len(pdf_listings)} counties)")
        print(f"{'='*40}")

        # Sirf selected counties ke PDFs delete karo (baaki counties ke PDFs rehne do)
        pdf_dir = "mvba_pdfs"
        files_to_refresh = {
            lst["pdf_url"].split("/")[-1].split("?")[0]
            for lst in pdf_listings
            if lst.get("pdf_url")
        }
        if os.path.isdir(pdf_dir):
            for fname in os.listdir(pdf_dir):
                if fname.endswith(".pdf") and fname in files_to_refresh:
                    try:
                        os.remove(os.path.join(pdf_dir, fname))
                        print(f"  🗑️  Old PDF deleted: {fname}")
                    except Exception:
                        pass

        for listing in pdf_listings:
            county       = listing["county"]
            pdf_url      = listing["pdf_url"]
            auction_date = listing["auction_date"]
            print(f"\n  📄 PDF: {county.upper()} — {pdf_url.split('/')[-1]}")
            local_pdf = download_pdf(pdf_url)
            if not local_pdf:
                stats["error"] += 1
                continue
            for prop in parse_pdf_properties(local_pdf, county, auction_date):
                r = smart_save(prop, db, csv_rows, "MVBA_PDF")
                stats[r] = stats.get(r, 0) + 1
            rewrite_csv(csv_rows)
            save_db(db)

        print(f"\n  ✅ PDFs done — New={stats['new']} Updated={stats['updated']} "
              f"Skipped={stats['skipped']} Error={stats.get('error', 0)}")
    else:
        print(f"\n  ℹ️  No PDF listings — skipping Step 1")

    # ── STEP 2: MVBA Online ───────────────────────────────────────────────
    if online_listings:
        print(f"\n{'='*40}")
        print(f"  🌐 STEP 2: MVBA Online ({len(online_listings)} counties)")
        print(f"{'='*40}")
        from playwright.sync_api import sync_playwright as _sync_pw
        with _sync_pw() as p:
            browser = p.chromium.launch(headless=False, slow_mo=150)
            page    = browser.new_context().new_page()
            # Prime session cookies on the homepage first — hitting deep
            # auction URLs cold is more likely to trip the site's WAF and
            # get served a bot-protection stub instead of the real page.
            try:
                page.goto("https://www.mvbataxsales.com/", timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  ⚠️ MVBA homepage priming failed ({e}) — continuing anyway")
            for listing in online_listings:
                county       = listing["county"]
                online_url   = listing["online_url"]
                auction_date = listing["auction_date"]
                print(f"\n  🌐 {county.upper()} — {online_url[:60]}")
                for prop in scrape_mvba_online_auction(page, online_url, county, auction_date):
                    r = smart_save(prop, db, csv_rows, "MVBA_ONLINE")
                    stats[r] = stats.get(r, 0) + 1
                rewrite_csv(csv_rows)
                save_db(db)
            browser.close()
    else:
        print(f"\n  ℹ️  No MVBA Online listings — skipping Step 2")

    print(f"\n  ✅ MVBA Done — New={stats['new']} Updated={stats['updated']} "
          f"Skipped={stats['skipped']} Error={stats.get('error', 0)}")
    return stats