#!/usr/bin/env python3
"""
make_daily_brief.py - condense _scan_results_latest.json into applications/_daily_brief.md.

Written for the 09:00 headless scan task (run_daily_scan.cmd). The apply sessions
and Habib read this one file instead of the full scan report. Always exits 0.
"""
import datetime as dt
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.join(os.path.dirname(HERE), "applications")
RESULTS_JSON = os.path.join(APPS, "_scan_results_latest.json")
RESULTS_MD = os.path.join(APPS, "_scan_results_latest.md")
BRIEF = os.path.join(APPS, "_daily_brief.md")

GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def main():
    today = dt.date.today().isoformat()
    lines = [f"# Daily brief - {today}", ""]

    try:
        with open(RESULTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        lines += ["**SCAN FAILED** - no readable _scan_results_latest.json. "
                  "Check applications/_scan_errors.log.", ""]
        with open(BRIEF, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"[written] {BRIEF} (scan missing)")
        return

    jobs = data.get("jobs", [])
    scanned_at = data.get("scanned_at", "?")
    stale = " **(STALE - not today's scan!)**" if scanned_at != today else ""

    by_grade, by_wp = {}, {}
    for j in jobs:
        by_grade[j.get("grade", "?")] = by_grade.get(j.get("grade", "?"), 0) + 1
        by_wp[j.get("workplace", "unknown")] = by_wp.get(j.get("workplace", "unknown"), 0) + 1
    lines.append(f"Scan of {scanned_at}{stale}: **{len(jobs)} jobs** | grades "
                 + " ".join(f"{g}:{by_grade[g]}" for g in sorted(by_grade,
                            key=lambda x: -GRADE_ORDER.get(x, -1)))
                 + " | workplace " + " ".join(f"{w}:{n}" for w, n in sorted(by_wp.items())))

    # surface board errors from the md report
    try:
        with open(RESULTS_MD, encoding="utf-8") as f:
            md = f.read()
        errs = re.findall(r"\*\*Skipped boards:\*\* (.+)", md)
        if errs:
            lines.append("")
            lines.append("Board errors: " + "; ".join(errs))
    except OSError:
        pass

    # Queue = SUBMITTABLE and (A OR B>=3.5). The scanner marks aggregators, AI-training
    # gigs, account-gate ATS, and already-applied jobs submittable:false, so the queue
    # is now genuine fits with a REAL apply path. Vetted B-grades are included (Habib's
    # fix 2026-07-05, after a day the A-queue was 100% unsubmittable junk). The stale-A
    # fallback (re-queued already-applied jobs) is deleted.
    ok = [j for j in jobs if j.get("submittable", True) and j.get("grade") != "F"]
    queue = [j for j in ok if j.get("grade") == "A"
             or (j.get("grade") == "B" and j.get("score", 0) >= 3.5)]
    # solo boards first, then Greenhouse try-then-fallback (one real click, hand to
    # Habib only on a genuine reCAPTCHA block), human-only last (Affirm/HiddenLayer).
    _ord = {"solo": 0, "try_then_fallback": 1, "human_only": 2}
    queue = sorted(queue, key=lambda j: (_ord.get(j.get("submit_mode",
                       "human_only" if j.get("needs_human_submit") else "solo"), 1),
                                         -j.get("score", 0)))
    lines += ["", f"## Apply queue - submittable A + B>=3.5 ({len(queue)})"]
    if not queue:
        lines.append("_No submittable fits this scan._")
    for j in queue[:15]:
        loc_tag = "LOCAL " if j.get("is_local") else ""
        sub_tag = "HUMAN-SUBMIT " if j.get("submit_mode") == "human_only" else ""
        lines.append(f"- **{j['grade']} ({j['score']})** {j['title']} - {j['company']} "
                     f"[{j['board']}] {loc_tag}{sub_tag}{j.get('workplace', '?')} | {j.get('location', '?')}")
        lines.append(f"  {j['url']}")

    local = [j for j in queue if j.get("is_local")]
    local.sort(key=lambda j: -j.get("score", 0))
    lines += ["", f"## Local onsite + hybrid near Gardena - submittable ({len(local)})"]
    if not local:
        lines.append("_None found this scan._")
    for j in local[:20]:
        lines.append(f"- {j['grade']} ({j['score']}) {j['title']} - {j['company']} "
                     f"[{j['board']}] {j.get('workplace', '?')} | {j.get('location', '?')}")
        lines.append(f"  {j['url']}")

    lines.append("")
    with open(BRIEF, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[written] {BRIEF}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never fail the scheduled chain
        try:
            with open(BRIEF, "w", encoding="utf-8") as f:
                f.write(f"# Daily brief\n\nBRIEF GENERATION FAILED: {e!r}\n")
        except OSError:
            pass
        print(f"brief failed: {e!r}")
