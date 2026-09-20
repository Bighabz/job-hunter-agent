#!/usr/bin/env python3
"""
scan_linkedin_guest.py - LinkedIn job discovery via the PUBLIC guest endpoints. (v1, 2026-07-03)

Unauthenticated, zero-browser, zero-token discovery that feeds the same pipeline
as scan_portals.py (title filter -> workplace classify -> grade -> shared outputs,
board="linkedin"). Covers what the ATS boards can't: local in-person jobs near
Gardena 90247 (incl. physical-security/GSOC roles) and the general LinkedIn pool,
WITHOUT burning authenticated page loads that feed LinkedIn's anti-bot throttle.

Endpoints (public guest pages, verified live 2026-07-03):
  search: linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?...&start=N   (HTML cards)
  detail: linkedin.com/jobs/view/<jobId>                                           (full JD)

Volume is deliberately conservative (budgets + jittered delays below, configured
in portals.yml `linkedin:`). On the first 429/999/authwall the run stops
gracefully: partial results are written, the block is noted, exit code stays 0.

NOTE: cards do NOT reveal workplace type (a remote job still shows a metro
string), so each query set's f_WT value is stamped as the workplace hint.

Usage:
    python scan_linkedin_guest.py                       # all enabled query sets
    python scan_linkedin_guest.py --set onsite_local    # one set
    python scan_linkedin_guest.py --max-details 5 --dry # parse only, write nothing
"""

import argparse
import datetime as dt
import html as html_mod
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import scan_portals as sp

# Windows consoles default to cp1252; job titles can contain emoji.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APPS = sp.APPS
ROTATION = os.path.join(APPS, "_li_rotation.json")
ERRLOG = os.path.join(APPS, "_scan_errors.log")

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
VIEW = "https://www.linkedin.com/jobs/view/{job_id}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
F_WT_HINT = {1: "onsite", 2: "remote", 3: "hybrid"}

_DELAY = (1.5, 2.5)  # overridden from config in main()


class LinkedInBlocked(Exception):
    """Raised on 429/999/authwall — abort remaining queries gracefully."""


def fetch_html(url):
    time.sleep(random.uniform(*_DELAY))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (429, 999):
            raise LinkedInBlocked(f"HTTP {e.code}")
        raise
    if "authwall" in body[:4000].lower():
        raise LinkedInBlocked("authwall")
    return body


# --------------------------------------------------------------------------- #
# Parsers (locked against scripts/fixtures/li_search.html + li_view.html)
# --------------------------------------------------------------------------- #
_RE_URN = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
_RE_HREF = re.compile(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"')
_RE_TITLE = re.compile(r'<h3[^>]*base-search-card__title[^>]*>(.*?)</h3>', re.S)
_RE_COMPANY = re.compile(r'<h4[^>]*base-search-card__subtitle[^>]*>(.*?)</h4>', re.S)
_RE_LOC = re.compile(r'<span[^>]*job-search-card__location[^>]*>(.*?)</span>', re.S)
_RE_DATE = re.compile(r'<time[^>]*datetime="(\d{4}-\d{2}-\d{2})"')
_RE_DESC = re.compile(r'show-more-less-html__markup[^>]*>(.*?)</div>', re.S)
_RE_SALARY = re.compile(r'compensation__salary[^>]*>(.*?)<', re.S)
_RE_CRITERIA = re.compile(r'description__job-criteria-text[^>]*>(.*?)</span>', re.S)


def _clean(fragment):
    return sp.strip_html(html_mod.unescape(fragment or ""))


def parse_cards(page):
    """Parse guest-search HTML into card dicts: job_id/title/company/location/url/date."""
    cards = []
    for block in page.split("<li")[1:]:
        urn = _RE_URN.search(block)
        href = _RE_HREF.search(block)
        title = _RE_TITLE.search(block)
        if not title or not (urn or href):
            continue
        if urn:
            job_id = urn.group(1)
        else:
            m = re.search(r"-(\d{7,})(?:$|[/?])", href.group(1).split("?")[0])
            if not m:
                continue
            job_id = m.group(1)
        comp = _RE_COMPANY.search(block)
        loc = _RE_LOC.search(block)
        date = _RE_DATE.search(block)
        cards.append({
            "job_id": job_id,
            "title": _clean(title.group(1)),
            "company": _clean(comp.group(1)) if comp else "",
            "location": _clean(loc.group(1)) if loc else "",
            "url": VIEW.format(job_id=job_id),
            "date": date.group(1) if date else "",
        })
    return cards


def parse_detail(page):
    """Full JD text from a guest /jobs/view page (+ salary/criteria if shown)."""
    m = _RE_DESC.search(page)
    desc = _clean(m.group(1)) if m else ""
    extras = []
    sal = _RE_SALARY.search(page)
    if sal:
        extras.append(_clean(sal.group(1)))
    extras.extend(_clean(c) for c in _RE_CRITERIA.findall(page)[:4])
    if extras:
        desc = (desc + " | " + " | ".join(e for e in extras if e)).strip()
    return desc


# --------------------------------------------------------------------------- #
# Query runner
# --------------------------------------------------------------------------- #
def load_rotation():
    try:
        with open(ROTATION, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_rotation(rot):
    with open(ROTATION, "w", encoding="utf-8") as f:
        json.dump(rot, f, indent=2)


def search_url(qs, keyword, start, days):
    params = {"keywords": keyword, "location": qs["location"],
              "f_TPR": f"r{days * 86400}", "f_WT": str(qs["f_wt"]), "start": str(start)}
    if qs.get("distance"):
        params["distance"] = str(qs["distance"])
    return SEARCH + "?" + urllib.parse.urlencode(params)


def run_query_set(name, qs, li_cfg, inc, exc, blocklist, seen, budget, emitted):
    """Yield job dicts for one query set, spending from the shared detail budget."""
    rot = load_rotation()
    keywords = qs.get("keywords", [])
    if not keywords:
        return []
    k_per_run = int(li_cfg.get("keywords_per_set_per_run", 4))
    start_idx = int(rot.get(name, 0)) % len(keywords)
    picked = [keywords[(start_idx + i) % len(keywords)] for i in range(min(k_per_run, len(keywords)))]
    rot[name] = (start_idx + len(picked)) % len(keywords)
    if not budget["dry"]:
        save_rotation(rot)

    max_pages = int(li_cfg.get("max_pages_per_query", 3))
    days = int(li_cfg.get("days", 1))
    wp_hint = F_WT_HINT.get(int(qs["f_wt"]))
    jobs = []
    for kw in picked:
        for page_i in range(max_pages):
            page = fetch_html(search_url(qs, kw, page_i * 25, days))
            cards = parse_cards(page)
            if not cards:
                break
            fresh_cards = [c for c in cards
                           if f"linkedin:{c['job_id']}" not in seen
                           and c["job_id"] not in emitted]
            if not fresh_cards:
                break  # this query is mined out for today
            for c in fresh_cards:
                if not sp.title_ok(c["title"], inc, exc):
                    continue
                if sp._wb_any(blocklist, c["company"].lower()):
                    continue
                if budget["details_left"] <= 0:
                    budget["exhausted"] = True
                    return jobs
                desc = parse_detail(fetch_html(c["url"]))
                budget["details_left"] -= 1
                emitted.add(c["job_id"])
                # LinkedIn cards carry NO workplace type, so f_WT was stamped as the
                # hint — but posters tag onsite jobs "remote" (RealmOne SysAdmin 3 was
                # "remote" yet Aurora CO onsite). Demote a "remote" hint when the JD
                # says on-site, or when the card names a concrete metro and the JD
                # never says "remote"; then classify_workplace decides from location.
                hint = wp_hint
                if hint == "remote" and desc:
                    # JD affirmatively says on-site -> drop the hint. The
                    # metro-card + JD-never-says-remote demotion now lives in
                    # sp.classify_workplace (whole-desc window, 200-char floor).
                    head = desc[:1500].lower()
                    if sp._DESC_ONSITE.search(head) and not sp._DESC_REMOTE.search(head):
                        hint = None
                jobs.append({
                    "id": c["job_id"],
                    "title": c["title"],
                    "location": c["location"],
                    "url": c["url"],
                    "updated": c["date"] or dt.date.today().isoformat(),
                    "board": "linkedin", "company": c["company"],
                    "desc": desc,
                    "wp_hint": hint,
                })
    return jobs


def log_err(msg):
    try:
        with open(ERRLOG, "a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] scan_linkedin_guest: {msg}\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    global _DELAY
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="", help="run one query set (remote|hybrid_local|onsite_local)")
    ap.add_argument("--max-details", type=int, default=0, help="override max_details_per_run")
    ap.add_argument("--dry", action="store_true", help="parse + print only; write nothing")
    ap.add_argument("--min-grade", default="B", choices=["A", "B", "C", "D", "F"])
    args = ap.parse_args()

    cfg = sp.load_config()
    li = cfg.get("linkedin") or {}
    if not li.get("enabled", False):
        print("linkedin: disabled in portals.yml — nothing to do")
        return
    _DELAY = tuple(li.get("delay_sec", [1.5, 2.5]))

    inc = [s.lower() for s in cfg["filters"]["include"]]
    exc = [s.lower() for s in cfg["filters"]["exclude"]]
    us = [s.lower() for s in cfg["location"]["us_signals"]]
    non_us = [s.lower() for s in cfg["location"]["non_us_signals"]]
    loc_cfg = {
        "local_cities": [s.lower() for s in cfg["location"].get("local_cities", [])],
        "local_borderline": [s.lower() for s in cfg["location"].get("local_borderline", [])],
    }
    hybrid_ok = bool(cfg["location"].get("hybrid_ok", True))
    sc = cfg["scoring"]
    # Aggregators added here too so their cards are skipped BEFORE spending a detail
    # fetch (they're the bulk of LinkedIn "hirer" reposts).
    blocklist = [b.lower() for b in sc["drop"]["company_blocklist"]] + \
                [a.lower() for a in sc["drop"].get("aggregator_companies", [])]

    sets = li.get("query_sets", {})
    if args.set:
        sets = {args.set: sets[args.set]} if args.set in sets else {}
        if not sets:
            print(f"unknown query set '{args.set}'")
            sys.exit(1)

    seen = sp.load_history()
    budget = {
        "details_left": args.max_details or int(li.get("max_details_per_run", 60)),
        "exhausted": False,
        "dry": args.dry,
    }
    emitted = set()
    collected, errors, blocked = [], [], None
    total_details = budget["details_left"]
    for set_index, (name, qs) in enumerate(sets.items()):
        # Reserve a fair share for each location mode. Remote previously consumed
        # the entire budget before the local query sets could fetch any details.
        remaining_sets = len(sets) - set_index
        allocation = max(1, total_details // remaining_sets) if total_details else 0
        budget["details_left"] = allocation
        budget["exhausted"] = False
        try:
            collected.extend(run_query_set(name, qs, li, inc, exc, blocklist, seen, budget, emitted))
            total_details -= allocation - budget["details_left"]
        except LinkedInBlocked as e:
            blocked = str(e)
            errors.append(f"linkedin:{name} (blocked: {blocked} — skipped rest of run)")
            log_err(f"blocked during set '{name}': {blocked}")
            break
        except Exception as e:  # a single set must not kill the run
            errors.append(f"linkedin:{name} ({type(e).__name__})")
            log_err(f"set '{name}' failed: {e!r}")
    if budget["exhausted"]:
        errors.append("linkedin (detail budget exhausted — rest deferred to next run)")

    applied = sp.load_applied_companies()
    applied_idx = sp.load_applied_index()
    triaged_idx = sp.load_triaged_index()
    graded = []
    for j in collected:
        wp, tier = sp.classify_workplace(j, loc_cfg)
        j["workplace"], j["local_tier"] = wp, tier
        keep, _why = sp.keep_by_workplace(wp, tier, j["location"].lower(), us, non_us, hybrid_ok)
        if not keep:
            continue
        g, score, tags, reasons = sp.grade_job(j, sc)
        j.update(grade=g, score=score, tags=tags, reasons=reasons,
                 fresh=True,  # card-level history check already skipped seen ids
                 repeat_company=j["company"].lower() in applied)
        sp.annotate_submittability(j, sc, applied_idx, triaged_idx)   # submittable/submit_block; may force F
        graded.append(j)

    if args.dry:
        print(f"[dry] {len(collected)} detail-fetched, {len(graded)} kept after workplace filter"
              + (f" | BLOCKED: {blocked}" if blocked else ""))
        for j in graded:
            print(f"  {j['grade']} ({j['score']}) {j['title']} - {j['company']} "
                  f"[{j['workplace']}{'/local' if j['local_tier'] else ''}] {j['location']}")
        return

    ns = argparse.Namespace(min_grade=args.min_grade, all=False)
    sp.emit_outputs(graded, ns, n_boards=len(sets), n_postings=len(collected),
                    errors=errors, merge_boards={"linkedin"},
                    report_title="LinkedIn guest scan")

    # Record EVERY processed id in history (not just the shown ones) so the
    # detail budget is never re-spent on a job we already graded — including
    # F-drops and below-min-grade jobs.
    now_seen = sp.load_history()
    rest = [j for j in graded if f"linkedin:{j['id']}" not in now_seen]
    dropped = [j for j in collected if "grade" not in j]
    for j in dropped:
        j.setdefault("grade", "F")
        j.setdefault("title", "")
    if rest or dropped:
        sp.append_history(rest + dropped)


if __name__ == "__main__":
    main()
