#!/usr/bin/env python3
"""
push_scan_to_supabase.py - Push graded scan results into Supabase `applications`.

Reads applications/_scan_results_latest.json (produced by scan_portals.py), keeps only
grade A/B jobs, dedupes against jd_urls already in Supabase, and inserts the rest as
status='saved'. Idempotent: re-running never creates duplicates.

Usage:
    python scan_portals.py              # produce the json first
    python push_scan_to_supabase.py            # dry-run: show what WOULD be inserted
    python push_scan_to_supabase.py --push      # actually insert
    python push_scan_to_supabase.py --min-grade A --push   # only A
    python push_scan_to_supabase.py --grades AB --push     # default A+B

Connection (URL + anon key) is read at runtime from supabase/connection.local.md.
The key is never printed, committed, or stored elsewhere.
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APPS = os.path.join(ROOT, "applications")
SCAN_JSON = os.path.join(APPS, "_scan_results_latest.json")
CONN = os.path.join(ROOT, "supabase", "connection.local.md")


def load_conn():
    txt = open(CONN, encoding="utf-8").read()
    url = re.search(r"(https://[a-z0-9]+\.supabase\.co)", txt).group(1)
    key = re.search(r"(sb_publishable_[A-Za-z0-9_\-]+)", txt).group(1)
    return url, key


def api(method, url, key, path, body=None, prefer=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def existing_urls(url, key):
    """Page through all jd_urls already in the table."""
    seen, offset, page = set(), 0, 1000
    while True:
        s, data = api("GET", url, key, f"/rest/v1/applications?select=jd_url&limit={page}&offset={offset}")
        if s != 200 or not data:
            break
        seen.update(r["jd_url"] for r in data if r.get("jd_url"))
        if len(data) < page:
            break
        offset += page
    return seen


def salary_from_tags(tags):
    for t in tags:
        if t.startswith("$"):
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="actually insert (default is dry-run)")
    ap.add_argument("--grades", default="AB", help="which grades to push, e.g. AB or A")
    ap.add_argument("--min-grade", default="", help="alias: A pushes only A; B pushes A+B")
    args = ap.parse_args()

    grades = set(args.grades.upper())
    if args.min_grade:
        grades = {"A"} if args.min_grade.upper() == "A" else {"A", "B"}

    if not os.path.exists(SCAN_JSON):
        print(f"No scan json at {SCAN_JSON}. Run: python scan_portals.py")
        return
    data = json.load(open(SCAN_JSON, encoding="utf-8"))
    jobs = [j for j in data["jobs"] if j["grade"] in grades]
    if not jobs:
        print(f"No grade-{''.join(sorted(grades))} jobs in latest scan.")
        return

    url, key = load_conn()
    try:
        have = existing_urls(url, key)
    except urllib.error.URLError as e:
        # DNS/connection failure (e.g. project paused or deleted -> hostname NXDOMAIN).
        # Degrade cleanly instead of dumping a stack trace: the daily scan chain
        # continues, and applications/_run_log.md stays the source of truth.
        print(f"Supabase unreachable ({e.reason}); skipping push. "
              f"Local _run_log.md remains the source of truth.")
        return
    new = [j for j in jobs if j["url"] not in have]
    dup = len(jobs) - len(new)

    print(f"Scan: {len(data['jobs'])} kept | grade {''.join(sorted(grades))}: {len(jobs)} "
          f"| already in Supabase: {dup} | new to insert: {len(new)}")
    print("-" * 70)
    for j in new:
        print(f"  [{j['grade']}] {j['score']} {j['title']} - {j['company']} ({j['location'] or '?'})")
        print(f"        {', '.join(j['tags'])}")

    if not args.push:
        print("\n[dry-run] nothing inserted. Re-run with --push to insert.")
        return
    if not new:
        print("\nNothing new to insert.")
        return

    ok = err = 0
    for j in new:
        row = {
            "company": j["company"],
            "role_title": j["title"],
            "jd_url": j["url"],
            "platform": j["board"].capitalize(),
            "location": j["location"] or None,
            "salary_range": salary_from_tags(j["tags"]),
            "status": "saved",
            "jd_keywords": [{"keyword": t, "category": "scanner"} for t in j["tags"]],
            "notes": f"auto-discovered by scanner; grade {j['grade']} ({j['score']})",
        }
        s, _ = api("POST", url, key, "/rest/v1/applications", row, prefer="return=minimal")
        if s in (200, 201):
            ok += 1
        else:
            err += 1
            print(f"  ! insert failed ({s}): {j['title']}")
    print(f"\nInserted {ok} | failed {err}. Status='saved' in Supabase `applications`.")


if __name__ == "__main__":
    main()
