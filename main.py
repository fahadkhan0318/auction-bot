"""
main.py — Texas Tax Sale Unified Scraper

Sources:
  1. Sheriff / Realforeclose  →  sheriff.py
  2. MVBA (PDF + Online)      →  mvba.py
  3. GovEase Online           →  govease.py
  4. CAD Enrichment           →  cad_scraper.py

All data → one CSV + one Google Sheet tab + one JSON DB per month.

Run: python main.py
"""

import os, re, sys
from datetime import datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright as _sync_playwright

import common
from common import (
    ask_target_month, init_sheet, load_db, save_db,
    load_csv_rows, rewrite_csv, sync_csv_to_sheet,
    reorder_google_sheet, MONTH_NUM_TO_NAME
)


# ═══════════════════════════════════════════════════════════════════════════
# UNIVERSAL COUNTY PICKER
# Same UI used by Sheriff, MVBA, and CAD
# ═══════════════════════════════════════════════════════════════════════════

def pick_counties(label, available, counts=None):
    """
    Generic county picker.

    Args:
        label     : section name shown in header e.g. "MVBA" / "CAD"
        available : ordered list of county name strings (lowercase)
        counts    : optional dict {county: row_count} shown next to each name

    Returns:
        list of selected county names (lowercase)
    """
    if not available:
        return list(available)

    if common.AUTO_MODE:
        print(f"  🤖 AUTO mode — {label}: all {len(available)} counties selected")
        return list(available)

    print(f"\n{'='*50}")
    print(f"  {label} — COUNTY SELECTION")
    print(f"{'='*50}")
    print(f"  Counties available ({len(available)}):\n")
    for i, c in enumerate(available, 1):
        suffix = f"  ({counts[c]} rows)" if counts and c in counts else ""
        print(f"    [{i:2d}] {c.upper()}{suffix}")

    print(f"\n  Options:")
    print(f"    A (or Enter) → All counties")
    print(f"    1,3          → Select by number")
    print(f"    harrison     → Type name(s) comma-separated")
    print(f"\n  > ", end="")
    ui = input("").strip().lower()

    # All
    if ui in ("a", "all", ""):
        print(f"  ✅ All {len(available)} counties selected")
        return list(available)

    # By number  e.g. "1,3,5"
    if re.match(r'^[\d,\s]+$', ui):
        selected = []
        for part in ui.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(available):
                    c = available[idx]
                    if c not in selected:
                        selected.append(c)
        if selected:
            print(f"  ✅ Selected: {', '.join(c.upper() for c in selected)}")
            return selected

    # By name  e.g. "harrison,cherokee"
    typed = [x.strip() for x in ui.split(",") if x.strip()]
    selected = []
    for t in typed:
        for c in available:
            if t in c or c.startswith(t):
                if c not in selected:
                    selected.append(c)
    if selected:
        print(f"  ✅ Selected: {', '.join(c.upper() for c in selected)}")
        return selected

    print(f"  ⚠️  No match found — using all counties")
    return list(available)


# ═══════════════════════════════════════════════════════════════════════════
# SOURCE SELECTION
# ═══════════════════════════════════════════════════════════════════════════

def ask_source():
    if common.AUTO_MODE:
        default = "sheriff,mvba,govease,cad"
        raw = os.getenv("AUTO_SOURCES", default)
        name_map = {
            "sheriff": "sheriff", "mvba": "mvba", "govease": "govease",
            "cad": "cad", "linebarger": "linebarger", "parcelfair": "parcelfair",
        }
        choices = {name_map[p.strip().lower()] for p in raw.split(",")
                   if p.strip().lower() in name_map}
        if not choices:
            choices = {"sheriff", "mvba", "govease", "cad"}
        print(f"  🤖 AUTO mode — sources: {', '.join(sorted(choices)).upper()}")
        return choices

    print(f"\n{'='*50}")
    print(f"  SOURCE SELECTION")
    print(f"{'='*50}")
    print(f"  [1] Sheriff / Realforeclose")
    print(f"  [2] MVBA   (PDF + Online)")
    print(f"  [3] GovEase (Online)")
    print(f"  [4] ALL    (Sheriff + MVBA + GovEase)")
    print(f"  [5] MVBA + GovEase only")
    print(f"  [6] CAD Enrichment")
    print(f"  [7] Linebarger (taxsales.lgbs.com)")
    print(f"  [8] Parcel Fair (Auction Calendar)")
    print(f"\n  Enter number(s) comma-separated (e.g. 2,6):")
    ui = input("  > ").strip()

    choices = set()
    for part in ui.replace(" ", "").split(","):
        if part == "1": choices.add("sheriff")
        elif part == "2": choices.add("mvba")
        elif part == "3": choices.add("govease")
        elif part == "4": choices.update(["sheriff", "mvba", "govease"])
        elif part == "5": choices.update(["mvba", "govease"])
        elif part == "6": choices.add("cad")
        elif part == "7": choices.add("linebarger")
        elif part == "8": choices.add("parcelfair")

    if not choices:
        print("  ⚠️ Invalid — defaulting to ALL")
        choices = {"sheriff", "mvba", "govease"}

    print(f"  ✅ Sources: {', '.join(sorted(choices)).upper()}")
    return choices


# ═══════════════════════════════════════════════════════════════════════════
# SHERIFF RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_sheriff(target_month, target_year, db, csv_rows):
    try:
        import sheriff
    except ImportError:
        print("  ❌ sheriff.py not found")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    from common import SHERIFF_COUNTIES

    print(f"\n{'='*50}")
    print(f"  SHERIFF — RUN MODE")
    print(f"{'='*50}")
    print(f"  [1] All     (poora fresh scrape — har listing ka detail page khulega)")
    print(f"  [2] Update  (fast — sirf status-changes check, naye listings hi full scrape hongi)")
    if common.AUTO_MODE:
        mode = os.getenv("SHERIFF_MODE", "update").strip().lower()
        if mode not in ("all", "update"):
            mode = "update"
        print(f"  🤖 AUTO mode — Mode: {mode.upper()}")
    else:
        mode_choice = input("  > ").strip()
        mode = "update" if mode_choice == "2" else "all"
        print(f"  ✅ Mode: {mode.upper()}")

    counties_to_run = pick_counties("SHERIFF", SHERIFF_COUNTIES)

    print(f"\n{'='*50}")
    print(f"  🔴 SHERIFF — {MONTH_NUM_TO_NAME[target_month]} {target_year}")
    print(f"  Running {len(counties_to_run)} county(ies)  |  Mode: {mode.upper()}")
    print(f"{'='*50}")

    sheriff.sheet    = common.sheet
    sheriff.MAIN_CSV = common.MAIN_CSV
    sheriff.DB_FILE  = common.DB_FILE

    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    with _sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        page    = browser.new_context().new_page()

        for county in counties_to_run:
            try:
                print(f"\n{'='*40}\n  COUNTY: {county.upper()}\n{'='*40}")
                page.goto(sheriff.get_county_url(county))
                sheriff.login(page)
                sheriff.handle_all_popups(page)
                sheriff.go_to_calendar_smart(page)
                sheriff.handle_all_popups(page)
                sheriff.process_calendar(
                    page, county.upper(), db, csv_rows, target_month, target_year, mode=mode
                )
            except Exception as e:
                print(f"  ❌ County error ({county}): {e}")
                import traceback; traceback.print_exc()
                stats["error"] += 1
            finally:
                rewrite_csv(csv_rows)

        browser.close()

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# MVBA RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_mvba_with_selection(target_month, target_year, db, csv_rows):
    try:
        from mvba import (
            run_mvba,
            fetch_mvba_page_with_playwright,
            parse_mvba_listings_for_month,
        )
    except ImportError:
        print("  ❌ mvba.py not found")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    print(f"\n  🌐 Fetching MVBA page to discover counties...")
    raw_links = fetch_mvba_page_with_playwright()

    if not raw_links:
        print("  ❌ Could not fetch MVBA page")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    all_listings = parse_mvba_listings_for_month(raw_links, target_month, target_year)

    if not all_listings:
        print(f"  ⚠️ No MVBA listings found for "
              f"{MONTH_NUM_TO_NAME[target_month]} {target_year}")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    # Build ordered unique county list from fetched listings
    available = []
    for lst in all_listings:
        c = lst["county"]
        if c and c != "unknown" and c not in available:
            available.append(c)

    # Let user pick which counties
    selected = pick_counties("MVBA", available)

    # Filter
    filtered = [lst for lst in all_listings if lst["county"] in selected]

    print(f"\n  📋 MVBA: running {len(filtered)} listing(s) for "
          f"{', '.join(c.upper() for c in selected)}")

    return run_mvba(
        target_month, target_year, db, csv_rows,
        preloaded_listings=filtered,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CAD RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_cad_with_selection(db, csv_rows):
    try:
        from cad_scraper import run_cad_enrichment, SUPPORTED_COUNTIES
    except ImportError:
        print("  ❌ cad_scraper.py not found")
        return {"updated": 0, "skipped": 0, "error": 1, "no_result": 0}

    # Ask which source's rows to enrich — keeps county list scoped to that source
    print(f"\n{'='*50}")
    print(f"  CAD ENRICHMENT — SOURCE FILTER")
    print(f"{'='*50}")
    print(f"  [1] Sheriff")
    print(f"  [2] MVBA")
    print(f"  [3] Linebarger")
    print(f"  [4] All sources (default)")
    if common.AUTO_MODE:
        print(f"  🤖 AUTO mode — Source: ALL")
        source_filter = None
    else:
        src_choice = input("  > ").strip()
        source_map = {"1": "SHERIFF", "2": "MVBA", "3": "LINEBARGER"}
        source_filter = source_map.get(src_choice)
        if source_filter:
            print(f"  ✅ Source: {source_filter}")
        else:
            print(f"  ✅ Source: ALL")

    # Count rows per supported county present in CSV, scoped to the chosen source
    counts = {}
    for row in csv_rows.values():
        if source_filter and row.get("Source", "").strip().upper() != source_filter:
            continue
        c = row.get("County", "").strip().lower().replace(" ", "").replace("_", "")
        if c in SUPPORTED_COUNTIES:
            counts[c] = counts.get(c, 0) + 1

    if not counts:
        label = source_filter or "any source"
        print(f"\n  ⚠️ No rows for CAD-supported counties ({label})")
        return {"updated": 0, "skipped": 0, "error": 0, "no_result": 0}

    available = sorted(counts.keys())

    # Let user pick — show row counts so they know what they're selecting
    selected = pick_counties("CAD ENRICHMENT", available, counts=counts)

    # Build filtered subset (run_cad_enrichment mutates what it receives)
    target_rows = {
        uk: row for uk, row in csv_rows.items()
        if row.get("County", "").strip().lower().replace(" ", "").replace("_", "") in selected
        and (not source_filter or row.get("Source", "").strip().upper() == source_filter)
    }

    total = sum(counts[c] for c in selected)
    print(f"\n  🏛️  CAD: enriching {total} row(s) across "
          f"{', '.join(c.upper() for c in selected)}")

    print("\n  Already enriched rows ko bhi update karna hai?")
    print("  (y = sab update karo  |  Enter = sirf naye/missing update karo): ", end="", flush=True)
    if common.AUTO_MODE:
        force_update = os.getenv("CAD_FORCE_UPDATE", "").strip().lower() == 'y'
        print(f"  🤖 AUTO mode — force_update={force_update}")
    else:
        force_update = input().strip().lower() == 'y'
    if force_update:
        print("  🔄 Force update mode — sab rows re-enrich hongi")
    else:
        print("  ⏭️  Normal mode — already enriched rows skip hongi")

    stats = run_cad_enrichment(target_rows, db, force_update=force_update)

    # Merge enriched rows back into master dict
    csv_rows.update(target_rows)

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# LINEBARGER RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_linebarger_with_selection(target_month, target_year, db, csv_rows):
    try:
        from linebarger import run_linebarger
    except ImportError:
        print("  ❌ linebarger.py not found")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    # Counties already in DB from Sheriff or MVBA — permanently excluded from Linebarger
    sheriff_mvba_counties = set()
    # Counties already scraped by Linebarger — available for update mode
    linebarger_counties = set()

    for v in db.values():
        c   = v.get("county", "").upper().strip()
        src = v.get("source", "").upper().strip()
        if not c:
            continue
        if src in ("SHERIFF", "MVBA"):
            sheriff_mvba_counties.add(c)
        elif src == "LINEBARGER":
            linebarger_counties.add(c)

    # Ask user: new counties only, update existing Linebarger, or both
    print(f"\n{'='*50}")
    print(f"  LINEBARGER — RUN MODE")
    print(f"{'='*50}")
    print(f"  [1] Naye counties sirf  (jo Linebarger mein abhi tak nahi hain)")
    print(f"  [2] Update existing     (jo Linebarger mein hain — status check)")
    print(f"  [3] Dono               (naye + existing Linebarger)")
    print(f"  Note: Sheriff/MVBA counties automatically skip hongi")
    if common.AUTO_MODE:
        mode = os.getenv("LINEBARGER_MODE", "3").strip()
        print(f"  🤖 AUTO mode — mode={mode}")
    else:
        mode = input("  > ").strip()

    def smart_picker(label, available):
        lb_new   = []   # not in DB at all (or not from Linebarger)
        lb_done  = []   # already scraped from Linebarger
        excluded = []   # Sheriff/MVBA — never show

        for c in available:
            clean = re.sub(r'\s+COUNTY,?\s*TX$', '', c, flags=re.IGNORECASE).strip().upper()
            if clean in sheriff_mvba_counties:
                excluded.append(c)
            elif clean in linebarger_counties:
                lb_done.append(c)
            else:
                lb_new.append(c)

        if excluded:
            print(f"\n  ⏭️  Sheriff/MVBA counties — auto-skip ({len(excluded)}):")
            for c in excluded:
                print(f"     {c}")

        if mode == "2":
            if not lb_done:
                print(f"  ✅ Koi Linebarger county DB mein nahi — kuch update karne ko nahi")
                return []
            print(f"\n  ℹ️  Update mode: {len(lb_done)} Linebarger county(ies)")
            return pick_counties(label, lb_done)

        elif mode == "3":
            combined = lb_new + lb_done
            if not combined:
                print(f"  ✅ Koi bhi non-Sheriff/MVBA county nahi")
                return []
            print(f"\n  ℹ️  All mode: {len(combined)} county(ies)")
            return pick_counties(label, combined)

        else:
            # Mode 1: new only
            if not lb_new:
                print(f"  ✅ Sab naye counties already Linebarger mein hain")
                return []
            return pick_counties(label, lb_new)

    # county_picker is called inside run_linebarger after the site loads —
    # single browser session, no double-open.
    return run_linebarger(
        target_month, target_year, db, csv_rows,
        county_picker=smart_picker,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GOVEASE RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_govease_with_selection(target_month, target_year, db, csv_rows):
    try:
        from govease import run_govease, get_govease_urls_from_mvba
    except ImportError:
        print("  ❌ govease.py not found")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    govease_urls = get_govease_urls_from_mvba(target_month, target_year)

    print(f"\n  📌 GovEase URLs from MVBA: {len(govease_urls)}")
    for c, u in govease_urls:
        print(f"     {c.upper()}: {u}")

    if common.AUTO_MODE:
        print(f"  🤖 AUTO mode — skipping custom GovEase URL prompt")
    else:
        print(f"\n  Add custom GovEase URL? (Enter URL or press Enter to skip):")
        custom = input("  > ").strip()
        if custom.startswith("http") and "govease" in custom:
            print(f"  County name for this URL:")
            cname = input("  > ").strip().lower()
            govease_urls.append((cname, custom))
            print(f"  ✅ Added: {cname.upper()} → {custom}")

    if not govease_urls:
        print(f"  ⚠️ No GovEase URLs — skipping")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    return run_govease(target_month, target_year, db, csv_rows, govease_urls)


# ═══════════════════════════════════════════════════════════════════════════
# PARCEL FAIR RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_parcelfair_with_selection(target_month, target_year, db, csv_rows):
    try:
        import parcelfair
    except ImportError:
        print("  ❌ parcelfair.py not found")
        return {"new": 0, "updated": 0, "skipped": 0, "error": 1}

    month_name = MONTH_NUM_TO_NAME[target_month]

    print(f"\n{'='*50}")
    print(f"  🟣 PARCEL FAIR — {month_name} {target_year}")
    print(f"{'='*50}")
    print(f"  [1] Any Location (default)")
    print(f"  [2] In-Person Only")
    print(f"  [3] Online Only")
    if common.AUTO_MODE:
        loc_choice = os.getenv("PARCELFAIR_LOCATION", "1").strip()
    else:
        loc_choice = input("  > ").strip()
    location = {"2": "In-Person", "3": "Online"}.get(loc_choice, "All")
    print(f"  ✅ Location filter: {location}")

    stats = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    with _sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        context = browser.new_context()
        page    = context.new_page()
        try:
            parcelfair.login(page)
            listings = parcelfair.click_month(page, month_name, target_year, location=location)

            if not listings:
                print(f"  ⚠️ No auctions found for {month_name} {target_year}")
                return stats

            print(f"\n  📊 {len(listings)} auction(s) found for {month_name} {target_year}:\n")
            for i, item in enumerate(listings, 1):
                print(f"    [{i:2d}] {item['day']:16s} | {item['name']:42s} | "
                      f"{item['auction_type']:16s} | {item['status']}")

            print(f"\n  Kaunse auction(s) ki parcel list nikalni hai?")
            print(f"    A (or Enter) → sab auctions")
            print(f"    1,3          → number se select karo")
            ui = "" if common.AUTO_MODE else input("  > ").strip().lower()

            if ui in ("a", "all", ""):
                selected = listings
            else:
                selected = []
                for part in ui.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(listings):
                            selected.append(listings[idx])
            if not selected:
                print(f"  ⚠️ Koi auction select nahi hua — using all")
                selected = listings
            print(f"  ✅ Selected {len(selected)} auction(s)")

            print(f"\n  Har parcel ki detail page (flood zone, vacancy, judgment, "
                  f"foreclosure, mortgage, images) bhi scrape karni hai?")
            print(f"    y = full detail (slower)  |  Enter = sirf list (fast)")
            if common.AUTO_MODE:
                deep = os.getenv("PARCELFAIR_DEEP", "").strip().lower() == "y"
            else:
                deep = input("  > ").strip().lower() == "y"

            all_rows = []
            for item in selected:
                print(f"\n  🟣 {item['name']} — {item['day']}")
                try:
                    rows = parcelfair.scrape_auction_parcels(context, item["list_links"], deep=deep)
                except Exception as e:
                    print(f"  ❌ Auction error ({item['name']}): {e}")
                    stats["error"] += 1
                    continue
                for r in rows:
                    r["_auction_name"] = item["name"]
                    r["_auction_day"]  = item["day"]
                    r["_auction_type"] = item["auction_type"]
                all_rows.extend(rows)
                stats["new"] += len(rows)

            if all_rows:
                out_path = parcelfair.save_parcelfair_csv(all_rows, month_name, target_year)
                print(f"\n  ✅ Parcel Fair: {len(all_rows)} parcel(s) saved → {out_path}")

        except Exception as e:
            print(f"  ❌ Parcel Fair error: {e}")
            import traceback; traceback.print_exc()
            stats["error"] += 1
        finally:
            browser.close()

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def run():
    print(f"\n{'='*50}")
    print(f"  🏠 TEXAS TAX SALE UNIFIED SCRAPER")
    print(f"  📅 {datetime.now().strftime('%B %d, %Y %H:%M')}")
    print(f"{'='*50}")

    # Month
    target_month, target_year = ask_target_month()
    month_name = MONTH_NUM_TO_NAME[target_month]

    # Source
    sources = ask_source()

    # Init
    print(f"\n  🔧 Initializing...")
    try:
        common.sheet = init_sheet(month_name)
    except Exception as _sheet_err:
        print(f"  ⚠️  Google Sheets connection failed: {_sheet_err}")
        print(f"  ⚠️  Running in OFFLINE mode — data saved to CSV/DB only")
        common.sheet = None
    db           = load_db()
    csv_rows     = load_csv_rows()
    print(f"  📂 DB: {len(db)} records | CSV: {len(csv_rows)} rows")
    try:
        sync_csv_to_sheet(csv_rows)
    except Exception as _sync_err:
        print(f"  ⚠️  Sheet sync skipped (offline): {_sync_err}")

    grand = {"new": 0, "updated": 0, "skipped": 0, "error": 0}

    def _merge(s):
        for k in s:
            grand[k] = grand.get(k, 0) + s.get(k, 0)

    # ── SHERIFF ───────────────────────────────────────────────────────────
    if "sheriff" in sources:
        _merge(run_sheriff(target_month, target_year, db, csv_rows))
        rewrite_csv(csv_rows)

    # ── MVBA ──────────────────────────────────────────────────────────────
    if "mvba" in sources:
        try:
            _merge(run_mvba_with_selection(target_month, target_year, db, csv_rows))
            rewrite_csv(csv_rows)
        except Exception as e:
            print(f"  ❌ MVBA error: {e}")
            import traceback; traceback.print_exc()

    # ── GOVEASE ───────────────────────────────────────────────────────────
    if "govease" in sources:
        try:
            _merge(run_govease_with_selection(target_month, target_year, db, csv_rows))
            rewrite_csv(csv_rows)
        except Exception as e:
            print(f"  ❌ GovEase error: {e}")
            import traceback; traceback.print_exc()

    # ── LINEBARGER ────────────────────────────────────────────────────────
    if "linebarger" in sources:
        try:
            _merge(run_linebarger_with_selection(target_month, target_year, db, csv_rows))
            rewrite_csv(csv_rows)
        except Exception as e:
            print(f"  ❌ Linebarger error: {e}")
            import traceback; traceback.print_exc()

    # ── PARCEL FAIR ───────────────────────────────────────────────────────
    if "parcelfair" in sources:
        try:
            _merge(run_parcelfair_with_selection(target_month, target_year, db, csv_rows))
        except Exception as e:
            print(f"  ❌ Parcel Fair error: {e}")
            import traceback; traceback.print_exc()

    # ── CAD ───────────────────────────────────────────────────────────────
    if "cad" in sources:
        try:
            s = run_cad_with_selection(db, csv_rows)
            grand["updated"] = grand.get("updated", 0) + s.get("updated", 0)
            grand["skipped"] = grand.get("skipped", 0) + s.get("skipped", 0)
            grand["error"]   = grand.get("error",   0) + s.get("error",   0)
            rewrite_csv(csv_rows)
        except Exception as e:
            print(f"  ❌ CAD error: {e}")
            import traceback; traceback.print_exc()

    # ── FINAL ─────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    rewrite_csv(csv_rows)
    save_db(db)
    try:
        reorder_google_sheet(csv_rows)
    except Exception as _reorder_err:
        print(f"  ⚠️  Sheet reorder skipped (offline): {_reorder_err}")

    print(f"\n{'='*50}")
    print(f"  ✅ ALL DONE!")
    print(f"  📄 CSV   : {common.MAIN_CSV}  ({len(csv_rows)} rows)")
    print(f"  🗄️  DB    : {common.DB_FILE}   ({len(db)} records)")
    print(f"  📊 Sheet : {month_name} tab")
    print(f"  Totals   → New:{grand.get('new',0)}  "
          f"Updated:{grand.get('updated',0)}  "
          f"Skipped:{grand.get('skipped',0)}  "
          f"Errors:{grand.get('error',0)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    run()