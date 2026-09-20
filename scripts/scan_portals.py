#!/usr/bin/env python3
"""
scan_portals.py - Zero-cost daily job discovery + grading for Habib. (v2, 2026-07-03)

Hits Greenhouse / Lever / Ashby / Workable / SmartRecruiters PUBLIC APIs directly
(no browser, no LLM, no auth), pulls the FULL job description, then grades each job
A-F on its actual JD text: track fit (applied-AI / entry-cyber / cloud / data / IT /
physical-security), pay, workplace + Gardena-local proximity, entry-level signals,
and bonuses for Claude/Claude Code + AI-adoption/consulting.
Hard-drops clearance roles, 4+ year gates, sub-$73k pay, and AI-training/sales shops.

v2 workplace policy (classify_workplace + keep_by_workplace):
    remote  -> keep (US-scoped)
    hybrid  -> keep only if local to Gardena/LA (location.local_cities) and hybrid_ok
    onsite  -> keep only if local
    unknown -> keep if a US signal is present (tagged wp:unknown)

Usage:
    python scan_portals.py                    # grade B+ jobs, fresh since last scan
    python scan_portals.py --min-grade A      # only A-grade
    python scan_portals.py --min-grade C      # widen the net
    python scan_portals.py --all              # include seen-before + dropped (shows reasons)
    python scan_portals.py --days 7           # only postings updated in last N days
    python scan_portals.py --board greenhouse:cybersheath
    python scan_portals.py --workplace onsite,hybrid   # only local in-person/hybrid

Outputs:
    - terminal: grouped by grade, with tags + pay + location + workplace
    - applications/_scan_results_latest.md
    - applications/_scan_results_latest.json  (sidecar incl. workplace/is_local)
    - applications/_scan_history.tsv  (so jobs don't reappear)

Discovery + triage only. Never submits anything.
"""

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import yaml
from polite_http import fetch_json_cached

# Windows consoles default to cp1252; job titles can contain emoji.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APPS = os.path.join(ROOT, "applications")
CONFIG = os.path.join(HERE, "portals.yml")
HISTORY = os.path.join(APPS, "_scan_history_paid_work_20260912.tsv")
RUN_LOG = os.path.join(APPS, "_run_log.md")
RESULTS = os.path.join(APPS, "_scan_results_latest.md")
RESULTS_JSON = os.path.join(APPS, "_scan_results_latest.json")

UA = "Mozilla/5.0 (jobhunter-scan; +local)"
TIMEOUT = 25
GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
MAX_SR_DETAILS = 40   # SmartRecruiters detail fetches per company per run

# Populated by main() before the fetch fan-out; used by scan_smartrecruiters to
# pre-filter titles/history BEFORE paying a detail request per job.
_SR_CFG = {"inc": [], "exc": [], "seen": set()}


# --------------------------------------------------------------------------- #
# HTTP + text helpers
# --------------------------------------------------------------------------- #
def fetch_json(url):
    return fetch_json_cached(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- #
# Per-ATS adapters -> {id,title,location,url,updated,board,company,desc,wp_hint}
# wp_hint is the STRUCTURED workplace signal from the ATS ('remote'|'hybrid'|
# 'onsite'|None) — it outranks any string parsing in classify_workplace.
# --------------------------------------------------------------------------- #
def scan_greenhouse(token):
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "id": str(j.get("id", "")),
            "title": j.get("title", "") or "",
            "location": (j.get("location") or {}).get("name", "") or "",
            "url": j.get("absolute_url", "") or "",
            "updated": j.get("updated_at", "") or "",
            "board": "greenhouse", "company": token,
            "desc": strip_html(j.get("content", "")),
            "wp_hint": None,   # GH public API has no workplace field
        })
    return out


def scan_lever(token):
    data = fetch_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data:
        cats = j.get("categories", {}) or {}
        ms = j.get("createdAt")
        updated = dt.datetime.utcfromtimestamp(ms / 1000).isoformat() if isinstance(ms, (int, float)) else ""
        lists_txt = " ".join(strip_html(l.get("text", "") + " " + l.get("content", "")) for l in (j.get("lists") or []))
        desc = (j.get("descriptionPlain") or strip_html(j.get("description", ""))) + " " + lists_txt
        wp = (j.get("workplaceType") or "").lower()
        wp_hint = {"remote": "remote", "hybrid": "hybrid",
                   "onsite": "onsite", "on-site": "onsite"}.get(wp)
        out.append({
            "id": str(j.get("id", "")),
            "title": j.get("text", "") or "",
            "location": cats.get("location", "") or j.get("workplaceType", "") or "",
            "url": j.get("hostedUrl", "") or "",
            "updated": updated,
            "board": "lever", "company": token,
            "desc": desc.strip(),
            "wp_hint": wp_hint,
        })
    return out


def scan_ashby(token):
    data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        loc = j.get("locationName") or j.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name", "") or ""
        desc = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml") or j.get("description", ""))
        comp = j.get("compensation") or {}
        out.append({
            "id": str(j.get("id", "") or j.get("jobId", "")),
            "title": j.get("title", "") or "",
            "location": loc,
            "url": j.get("jobUrl", "") or j.get("applyUrl", "") or "",
            "updated": j.get("publishedDate", "") or "",
            "board": "ashby", "company": token,
            "desc": (desc + " " + json.dumps(comp)).strip(),
            "wp_hint": "remote" if j.get("isRemote") else None,
        })
    return out


def scan_workable(token):
    # Verified live 2026-07-03: details=true includes the full description per job.
    data = fetch_json(f"https://apply.workable.com/api/v1/widget/accounts/{token}?details=true")
    out = []
    for j in data.get("jobs", []):
        # Workable states the job's country explicitly; a non-US country means the
        # role is located/hired there even when telecommuting=true. Drop early.
        country = (j.get("country") or "").lower()
        if country and country not in ("united states", "united states of america", "us", "usa"):
            continue
        loc = ", ".join(filter(None, [j.get("city"), j.get("state"), j.get("country")]))
        out.append({
            "id": str(j.get("shortcode") or j.get("code") or ""),
            "title": j.get("title", "") or "",
            "location": loc,
            "url": j.get("url") or j.get("application_url") or "",
            "updated": j.get("published_on", "") or "",
            "board": "workable", "company": token,
            "desc": strip_html(j.get("description", "")),
            "wp_hint": "remote" if j.get("telecommuting") else None,
        })
    return out


def scan_smartrecruiters(token):
    # List API has no JD text; a detail call per job is required. Pre-filter hard
    # (US + title + not-in-history) and budget MAX_SR_DETAILS detail fetches.
    base = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
    postings, offset, pages = [], 0, 0
    while pages < 10:
        data = fetch_json(f"{base}?limit=100&offset={offset}")
        content = data.get("content", [])
        if not content:
            break
        postings.extend(content)
        pages += 1
        offset += len(content)
        if offset >= int(data.get("totalFound", 0) or 0):
            break
    inc, exc, seen = _SR_CFG["inc"], _SR_CFG["exc"], _SR_CFG["seen"]
    out, details = [], 0
    for p in postings:
        loc = p.get("location") or {}
        country = (loc.get("country") or "").lower()
        if country not in ("us", "united states", "usa"):
            continue
        name = p.get("name", "") or ""
        if inc and not title_ok(name, inc, exc):
            continue
        pid = str(p.get("id", ""))
        loc_str = loc.get("fullLocation") or ", ".join(
            filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
        wp_hint = "remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else None)
        desc, url = "", f"https://jobs.smartrecruiters.com/{token}/{pid}"
        if f"smartrecruiters:{pid}" not in seen and details < MAX_SR_DETAILS:
            try:
                d = fetch_json(f"{base}/{pid}")
                details += 1
                sections = (d.get("jobAd") or {}).get("sections") or {}
                desc = strip_html(" ".join(
                    (sections.get(k) or {}).get("text", "") for k in
                    ("companyDescription", "jobDescription", "qualifications", "additionalInformation")))
                url = d.get("postingUrl") or url
            except Exception:
                pass  # keep the job with empty desc; grading is conservative without text
        out.append({
            "id": pid,
            "title": name,
            "location": loc_str,
            "url": url,
            "updated": p.get("releasedDate", "") or "",
            "board": "smartrecruiters", "company": token,
            "desc": desc,
            "wp_hint": wp_hint,
        })
    return out


ADAPTERS = {
    "greenhouse": scan_greenhouse,
    "lever": scan_lever,
    "ashby": scan_ashby,
    "workable": scan_workable,
    "smartrecruiters": scan_smartrecruiters,
}


# --------------------------------------------------------------------------- #
# Title filter (pre-grade)
# --------------------------------------------------------------------------- #
# A trailing mid/senior level suffix: roman II-V or arabic 2-9 at the very end.
# "Data Engineer I" / "Tier 1" (entry) and "...O365" (no word boundary) are kept.
# (?<!soc )/(?<!type ): "GRC Analyst - SOC 2" / "SOC 2 Type 2" are compliance
# frameworks, not seniority levels (false-drop fixed cycle 1, 2026-07-05).
_LEVEL_SUFFIX = re.compile(r"(?<!soc )(?<!type )\b(?:ii|iii|iv|v|[2-9])\s*$")


def title_ok(title, inc, exc):
    # Leading pad so space-anchored excludes (" sr ", " tax", " vp") also match
    # title-INITIAL words ("Sr Revenue Operations Analyst" leaked cycle 1).
    t = " " + title.lower()
    if any(x in t for x in exc):
        return False
    if _LEVEL_SUFFIX.search(t):     # "Systems Administrator 3", "Analyst II"
        return False
    return any(x in t for x in inc)


# --------------------------------------------------------------------------- #
# Workplace classification (v2 — replaces location_ok)
# --------------------------------------------------------------------------- #
_REMOTE_LOC = ("remote", "anywhere", "work from home", "wfh")
_ONSITE_LOC = ("on-site", "onsite", "on site", "in office", "in-office", "in person", "in-person")
_DESC_HYBRID = re.compile(r"\bhybrid\b")
_DESC_ONSITE = re.compile(r"\bon-?site\b|\bin[- ]office\b|\bin[- ]person\b")
_DESC_REMOTE = re.compile(r"\b(?:fully|100%)\s+remote\b|\bremote-first\b")
# Any remote-work claim anywhere in the JD. Broad on purpose: used only to VETO a
# demotion, so false positives here just preserve the structured remote hint.
_ANY_REMOTE = re.compile(r"(?:fully|100%|fully-)?\s*remote[- ](?:role|position|job|work|opportunity|first)|"
                        r"(?:role|position|job|work)\s+(?:is\s+)?(?:fully\s+)?remote|"
                        r"work.from.home|\bwfh\b|telecommut|work from anywhere|"
                        r"remotely\s+(?:from|within|across|anywhere)")
# Location parts that name a country/region rather than a concrete place.
_COUNTRY_ONLY = ("united states", "united states of america", "u.s.", "u.s", "us",
                 "usa", "north america", "americas", "amer")


def _local_tier(l, loc_cfg):
    """'core' | 'borderline' | '' for a lowercased location string."""
    for c in loc_cfg.get("local_cities", []):
        if c in l:
            if c == "carson" and "carson city" in l:
                continue  # Carson City, NV is not Carson, CA
            return "core"
    for c in loc_cfg.get("local_borderline", []):
        if c in l:
            return "borderline"
    return ""


def classify_workplace(job, loc_cfg):
    """Classify a job's workplace and locality.

    Returns (workplace, local_tier):
      workplace  - 'remote' | 'hybrid' | 'onsite' | 'unknown'
      local_tier - 'core' | 'borderline' | ''  (Gardena-commute city match)

    Precedence: structured ATS hint (wp_hint) > location-string keywords
    (hybrid > onsite > remote) > desc keywords (first 1500 chars) > fallback
    (concrete city -> onsite; empty/pure-country -> unknown).
    """
    l = (job.get("location") or "").lower()
    tier = _local_tier(l, loc_cfg)

    wp = job.get("wp_hint")
    if wp not in ("remote", "hybrid", "onsite"):
        wp = None
    if wp == "remote":
        # Structured remote flags over-claim: Ashby isRemote is board-wide true
        # (ramp 119/125 incl. "New York, NY (HQ)"; Notion true on SF-hybrid roles
        # - verified 2026-07-05), Workable telecommuting = "remote allowed".
        # Demote when the location names a concrete metro AND a substantial JD
        # never claims remote work anywhere; the string/desc/fallback chain below
        # then reclassifies (typically onsite -> non-local drop).
        parts = [p.strip() for p in re.split(r"[,/;|]", l) if p.strip()]
        concrete = (parts and not all(p in _COUNTRY_ONLY for p in parts)
                    and not any(k in l for k in _REMOTE_LOC))
        full = (job.get("desc") or "").lower()
        if concrete and len(full) >= 200 and not _ANY_REMOTE.search(full):
            wp = None
    if wp is None:
        if "hybrid" in l:
            wp = "hybrid"
        elif any(k in l for k in _ONSITE_LOC):
            wp = "onsite"
        elif any(k in l for k in _REMOTE_LOC):
            wp = "remote"
    if wp is None:
        head = (job.get("desc") or "")[:1500].lower()
        if _DESC_HYBRID.search(head):
            wp = "hybrid"
        elif _DESC_ONSITE.search(head):
            wp = "onsite"
        elif _DESC_REMOTE.search(head):
            wp = "remote"
    if wp is None:
        parts = [p.strip() for p in re.split(r"[,/;|]", l) if p.strip()]
        if not parts or all(p in _COUNTRY_ONLY for p in parts):
            wp = "unknown"
        else:
            wp = "onsite"   # a concrete city/state with no remote/hybrid markers
    return wp, tier


def keep_by_workplace(workplace, local_tier, loc, us, non_us, hybrid_ok):
    """Keep-decision (v2). Returns (keep: bool, drop_reason: str).

    Fixes two v1 bugs: onsite non-local US jobs leaked through (had a us_signal),
    and terse local cities ("Torrance, CA") were silently dropped.
    """
    has_us = any(x in loc for x in us)
    has_non_us = any(x in loc for x in non_us)
    if has_non_us and not has_us:
        return False, "non-US"
    if workplace == "remote":
        return True, ""
    if workplace == "hybrid":
        if not local_tier:
            return False, "hybrid non-local"
        return (True, "") if hybrid_ok else (False, "hybrid disabled")
    if workplace == "onsite":
        return (True, "") if local_tier else (False, "onsite non-local")
    # unknown: keep when US-signaled or location empty; grade normally, tag wp:unknown
    if not loc or has_us:
        return True, ""
    return False, "unknown location, no US signal"


def within_days(updated_iso, days):
    if not days or not updated_iso:
        return True
    try:
        d = dt.datetime.fromisoformat(updated_iso.replace("Z", "").split(".")[0])
        return (dt.datetime.utcnow() - d).days <= days
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Pay parsing + years gate
# --------------------------------------------------------------------------- #
def parse_pay(text):
    """Return annualized top-of-range salary found in JD, or None."""
    t = text.lower()
    vals = []
    for m in re.finditer(r"\$\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kmb](?=\b|\+))?", t):
        num = float(m.group(1).replace(",", ""))
        suffix = m.group(2)
        after = t[m.end():m.end()+45]
        near = t[max(0,m.start()-80):m.end()+80]
        if suffix in ('m', 'b') or re.search(r"^\s*(?:million|billion|/month|per month|monthly|/week|per week)", after):
            continue  # funding, revenue and benefit stipends are not salary
        if suffix == 'k':           # "$120k"
            num *= 1000
        elif num < 1000:         # bare "$45" -> likely hourly
            if not re.search(r"/\s?hr|per hour|/\s?hour|hourly|an hour", near):
                continue
            num *= 2080
        vals.append(num)
    vals = [v for v in vals if 20000 <= v <= 600000]
    return max(vals) if vals else None


def years_gate(text):
    """Highest required years-of-experience >= it implies a gate; 0 if none found."""
    worst = 0
    for m in re.finditer(
        r"(\d{1,2})\+?\s*(?:to|-|–)?\s*\d{0,2}\s*years?(?:\s+of)?\s+"
        r"(?:experience|exp|industry|professional|relevant|hands-on|work)", text.lower()
    ):
        worst = max(worst, int(m.group(1)))
    return worst


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #
def _wb_any(patterns, text):
    """True if any pattern matches text at word boundaries. Prevents the substring
    bug where 'appen' matched 'happen' and 'turing' matched 'manufacturing'."""
    for p in patterns:
        if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text):
            return True
    return False


def grade_job(job, sc):
    title = job["title"].lower()
    blob = (job["title"] + " " + job["desc"]).lower()
    tags, reasons = [], []

    # ---- hard drops ----
    co = job["company"].lower()
    # Gig-mill blocklist + aggregator brands: match the COMPANY NAME ONLY (word-
    # boundary). Old code substring-matched the JD blob too, silently F-dropping
    # legit jobs ('appen'->'happen', 'turing'->'manufacturing', 'scale ai'->'scale
    # AI initiatives'). Gig mills post under their own names, so name-match suffices.
    if _wb_any(sc["drop"]["company_blocklist"], co):
        return "F", 0.0, ["blocklisted"], ["AI-training/sales shop"]
    if _wb_any(sc["drop"].get("aggregator_companies", []), co):
        return "F", 0.0, ["aggregator"], ["reposter/ad-farm source - no real apply path"]
    # Weapons/military-targeting exclusion (Habib's values decision 2026-07-07):
    # no weapons or munitions manufacturers, no military targeting/intel software.
    # Checked against the JD blob too so staffing posts recruiting FOR these
    # companies ("our client Lockheed Martin...") are dropped as well.
    weap_cos = sc["drop"].get("weapons_companies", [])
    if any(w in blob for w in weap_cos) or any(w in job["company"].lower() for w in weap_cos):
        return "F", 0.0, ["weapons-defense"], ["weapons/targeting company (values exclusion)"]
    if any(c in blob for c in sc["drop"]["clearance_patterns"]):
        return "F", 0.0, ["clearance"], ["requires security clearance"]
    # Physical-security-in-disguise: a cyber-sounding TITLE over a guard/GSOC JD
    # body (Habib does not do physical security). >=2 distinct patterns = drop.
    phys_hits = [p for p in sc["drop"].get("physical_security_desc_patterns", []) if p in blob]
    if len(phys_hits) >= 2:
        return "F", 0.0, ["physical-security"], [f"physical-security JD ({', '.join(phys_hits[:3])})"]
    # AI-training/RLHF-rater gig disguised as a real title (e.g. YO HR "Data Analyst
    # (Excel)" whose JD was "help train next-generation AI systems, no AI experience
    # required"). >=2 distinct patterns = drop; a single mention is allowed so real
    # ML/data JDs that touch labeling once aren't nuked.
    ait_hits = [p for p in sc["drop"].get("ai_training_desc_patterns", []) if p in blob]
    if len(ait_hits) >= 2:
        return "F", 0.0, ["ai-training-gig"], [f"AI-training/labeling gig JD ({', '.join(ait_hits[:3])})"]
    # Weapons-program-in-disguise: neutral title, weapons-program JD body (e.g. a
    # generic "Data Analyst" embedded in a missile program). >=2 distinct patterns
    # = drop; single mentions allowed (a cyber JD can mention one legitimately).
    weap_hits = [p for p in sc["drop"].get("weapons_desc_patterns", []) if p in blob]
    if len(weap_hits) >= 2:
        return "F", 0.0, ["weapons-defense"], [f"weapons-program JD ({', '.join(weap_hits[:3])})"]
    yg = years_gate(blob)
    if yg >= sc["drop"]["years_gate"]:
        return "F", 0.0, ["years-gate"], [f"{yg}+ yrs required"]
    pay = parse_pay(blob)
    if pay is not None and pay < sc["drop"]["pay_floor"]:
        return "F", 0.0, ["low-pay"], [f"~${int(pay/1000)}k < floor"]

    # ---- base + track fit (v3: fit-first) ----
    # Track evidence in the TITLE is real fit; evidence only in the JD text is
    # weak (aggregators and boilerplate JDs are keyword soup — the 2026-07-03
    # run graded "Payroll Tax Consulting" A off desc keywords alone).
    score = 2.0
    track_hit = False          # any evidence at all
    title_track_hit = False    # strong evidence: track keyword in the title
    for track, kws in sc["tracks"].items():
        in_title = any(k in title for k in kws)
        if in_title or any(k in blob for k in kws):
            tags.append(track.replace("_", "-"))
            track_hit = True
            title_track_hit = title_track_hit or in_title
    if title_track_hit:
        score += 1.2
    elif track_hit:
        score += 0.4
        reasons.append("track match in JD text only")
    else:
        reasons.append("off-target (no track)")

    # ---- entry-level is the single most important signal for Habib ----
    entry = any(k in blob for k in sc["bonus"]["entry_signal"]) or bool(
        re.search(r"\b(junior|associate|intern|new grad|entry)\b", title)
        or re.search(r"\b(analyst|engineer|specialist|technician)\s+i\b", title)
        or re.search(r",\s*i\b", title)
    )
    if entry:
        score += 1.0
        tags.append("entry")

    # ---- bonuses (small; tooling/fun should not outweigh fit) ----
    if any(k in blob for k in sc["bonus"]["claude_code"]):
        score += 0.4
        tags.append("claude/ai-tooling")
    if any(k in blob for k in sc["bonus"]["ai_adoption"]):
        score += 0.3
        tags.append("ai-adoption")
    if any(k in blob for k in sc["bonus"]["consulting"]):
        score += 0.3
        tags.append("consulting")

    # ---- workplace bonuses (v2: from the classifier, not string sniffing) ----
    wp = job.get("workplace", "unknown")
    local_tier = job.get("local_tier", "")
    if wp == "remote":
        score += 0.7
        tags.append("remote")
    if wp in ("onsite", "hybrid") and local_tier:
        if local_tier == "core":
            score += 0.3
            tags.append("CA-local")
        else:
            score += 0.2
            tags.append("distance-check-required")
    tags.append(f"wp:{wp}")

    # ---- pay band: reward the target range; very high pay = senior signal ----
    senior_pay = False
    if pay is not None:
        tags.append(f"${int(pay/1000)}k")
        if sc["pay_great"] <= pay <= 140000:
            score += 0.6
        elif sc["pay_ok"] <= pay < sc["pay_great"]:
            score += 0.3
        elif 140000 < pay <= 200000:
            pass  # mid-level band, no bonus
        elif pay > 200000:
            score -= 0.5
            senior_pay = True
            reasons.append("very high pay (senior?)")

    # ---- seniority / advanced-degree guards ----
    if re.search(r"master'?s degree (is )?required|ph\.?d\.? required|requires a ph", blob):
        score -= 0.8
        reasons.append("advanced degree required")
    if re.search(r"\b(senior|staff|principal|lead)\b", title):
        score -= 1.5
        reasons.append("senior title")

    # ---- caps ----
    if not track_hit:
        score = min(score, 2.4)            # off-target -> max C
    if senior_pay and not entry:
        score = min(score, 2.4)            # $200k+ and not entry -> max C

    # round BEFORE banding: binary-float sums like 3.9999999999999996 sat just
    # under the 4.0 A cutoff yet displayed as 4.0 after the final round(,1).
    score = round(max(0.0, min(5.0, score)), 3)
    if score >= 4.0:
        g = "A"
    elif score >= 3.0:
        g = "B"
    elif score >= 2.0:
        g = "C"
    elif score >= 1.0:
        g = "D"
    else:
        g = "F"
    # grade A must be genuinely entry-level AND show fit in the TITLE itself —
    # bonus-stacking off a keyword-soup JD can never reach A (v3).
    if g == "A" and not entry:
        g, score = "B", min(score, 3.9)
        reasons.append("not entry -> capped B")
    # "Software Engineer, New Grad (AI)" has no track keyword IN THE TITLE (tracks
    # don't list "software engineer"), but a new-grad SWE at an AI company with JD
    # track fit is exactly Habib's bracket -> let it reach A. Aggregators that would
    # abuse this are already F-dropped above.
    # Exempt genuine junior/new-grad SOFTWARE-ENGINEER/DEVELOPER titles (a target
    # role the tracks don't list) from the title-track A-cap. NOT bare "associate"
    # -> keyword-soup guard: "Operations Associate" over a soc-analyst JD stays capped.
    newgrad_swe = bool(re.search(r"\b(software engineer|software developer|developer|swe)\b", title)
                       and re.search(r"\b(new grad|junior|associate|entry)\b", title))
    if g == "A" and not title_track_hit and not (entry and newgrad_swe):
        g, score = "B", min(score, 3.9)
        reasons.append("no title-level track fit -> capped B")
    return g, round(score, 1), tags, reasons


# --------------------------------------------------------------------------- #
# History / run-log
# --------------------------------------------------------------------------- #
def load_history():
    seen = set()
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2:
                    seen.add(f"{p[0]}:{p[1]}")
    return seen


def append_history(rows):
    new = not os.path.exists(HISTORY)
    with open(HISTORY, "a", encoding="utf-8") as f:
        if new:
            f.write("board\tid\tcompany\tgrade\ttitle\tfirst_seen\n")
        today = dt.date.today().isoformat()
        for r in rows:
            f.write(f"{r['board']}\t{r['id']}\t{r['company']}\t{r['grade']}\t{r['title']}\t{today}\n")


def load_applied_companies():
    return {r[1].lower() for r in log_rows() if r[4].lower().startswith("applied")}


def log_rows():
    """Accept both Markdown tables and the newer unframed pipe-delimited ledger."""
    if not os.path.exists(RUN_LOG):
        return
    with open(RUN_LOG, encoding="utf-8") as f:
        for line in f:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 7 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
                yield cells


def canonical_job_url(url):
    """Remove marketing parameters while preserving IDs on shared application paths."""
    p = urlsplit(url.rstrip("|).,").strip())
    identity = {"for", "token", "gh_jid", "jobid", "job_id", "jk", "requisitionid"}
    query = sorted((k.lower(), v) for k, v in parse_qsl(p.query) if k.lower() in identity)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(query), ""))


# Job-id inside common apply URLs: /jobs/12345, /view/12345, token=12345, /postings/…
_ID_RE = re.compile(r"(?:/jobs/|/view/|token=|/postings/|gh_jid=|jobs/view/)(\d{6,})")


def load_applied_index():
    """Dedup index from _run_log.md, counting ONLY rows whose status cell starts
    with 'applied' (skipped:/blocked:/note rows do NOT count). Returns
    (urls, ids, co_title) for exact-URL, exact-id, and fuzzy company+title matching.
    Row format: | DATE | Company | Role | source | status | pay | url |"""
    urls, ids, co_title = set(), set(), set()
    if not os.path.exists(RUN_LOG):
        return urls, ids, co_title
    for row in log_rows():
            cells = [""] + row
            line = " | ".join(row)
            status = cells[5].lower()
            # prefilled/filled-not-submitted rows: Habib may have clicked submit
            # after (log never updated) -> feed the SOFT (co+title) tier only, never
            # the url/id F-force, since submission is unconfirmed.
            soft = status.startswith(("prefilled", "filled"))
            if not status.startswith("applied") and not soft:
                continue
            if not soft:
                m = re.search(r"https?://\S+", line)
                if m:
                    urls.add(canonical_job_url(m.group(0)))
                ids.update(_ID_RE.findall(line))
            co = re.sub(r"[^a-z0-9]", "", cells[2].lower())
            ti = re.sub(r"\(.*?\)", "", cells[3].lower()).split("—")[0].split(" - ")[0].strip()
            if len(co) >= 4 and len(ti) >= 8:      # length guards vs absurd containment
                co_title.add((co, ti))
    return urls, ids, co_title


def already_applied(job, idx):
    """'url' | 'id' | 'company+title' | '' — how (if at all) this job was already applied."""
    urls, ids, co_title = idx
    u = canonical_job_url(job.get("url") or "")
    if u and u in urls:
        return "url"
    jid = str(job.get("id") or "")
    if jid and jid in ids:
        return "id"
    co = re.sub(r"[^a-z0-9]", "", job.get("company", "").lower())
    ti = re.sub(r"\(.*?\)", "", (job.get("title") or "").lower()).strip()
    if len(co) >= 4 and len(ti) >= 8:
        for aco, ati in co_title:
            # prefix-or-exact company match: keeps atbay->atbayjobs and
            # jobgether->jobgetherpartnerco, kills mid-string FPs (visa->novisa)
            co_match = aco == co or (len(aco) >= 5 and co.startswith(aco)) \
                       or (len(co) >= 5 and aco.startswith(co))
            if co_match and (ati in ti or ti in ati):
                return "company+title"
    return ""


def _host_blocked(url, desc, hosts):
    """True if the apply URL host — or any URL embedded in the JD body (catches
    'Apply at: http://...' redirect fingerprints) — is an account-gated ATS."""
    if not hosts:
        return False
    if any(h in (url or "").lower() for h in hosts):
        return True
    for link in re.findall(r"https?://[^\s\"'<>]+", (desc or "").lower()):
        if any(h in link for h in hosts):
            return True
    return False


def load_triaged_index():
    """Re-use recent explicit qualification knockouts, never temporary failures or old pay rules."""
    out = {}
    hard = ('tool-gate', 'no-fit-wrong-discipline', 'discipline-gate', 'trade-specific-gate',
            'senior-specialist-gate', 'specialist-gate-0-yrs', 'requires-active-ts-clearance',
            'requires-spanish-fluency', 'senior-gate')
    for row in log_rows():
        age = (dt.date.today() - dt.date.fromisoformat(row[0])).days
        if not 0 <= age <= 30:
            continue
        status = row[4].lower()
        if not any(status.startswith('skipped:' + reason) for reason in hard):
            continue
        m = re.search(r'https?://\S+', ' | '.join(row[6:]))
        if m:
            out[canonical_job_url(m.group(0))] = row[4]
    return out


def annotate_submittability(job, sc, applied_idx, triaged_idx=None):
    """Set job['submittable'] (bool) + job['submit_block'] (reason string). Exact
    already-applied url/id FORCE grade F (drop from queue); aggregator / account-gate
    ATS / fuzzy-applied / thin-JD are softer flags that only keep it out of the queue.
    Topical grade stays in grade_job; this is the submittability/source-trust layer."""
    d = sc["drop"]
    hit = already_applied(job, applied_idx)
    if hit in ("url", "id"):
        job["grade"], job["score"] = "F", 0.0
        job.setdefault("tags", []).append("already-applied")
        job["submittable"], job["submit_block"] = False, "already-applied"
        return
    block = ""
    co = job.get("company", "").lower()
    if canonical_job_url(job.get('url') or '') in (triaged_idx or {}):
        block = 'triaged-qualification-gate'
    elif _wb_any(d.get("aggregator_companies", []), co):
        block = "aggregator"
    elif _host_blocked(job.get("url", ""), job.get("desc", ""), d.get("account_required_hosts", [])):
        block = "account-ats"
    elif hit == "company+title":
        block = "already-applied?"
    elif len(job.get("desc") or "") < 400:
        block = "thin-jd"      # any board: an unverifiable JD shouldn't auto-queue
    job["submittable"], job["submit_block"] = (block == ""), block
    # Greenhouse invisible reCAPTCHA v3 is PER-BOARD, not universal (run-log evidence:
    # a genuine trusted-input click PASSED CyberSheath 06-03, At-Bay/GitLab/AvidXchange
    # 06-01, Pie Insurance 07-04; only Affirm + HiddenLayer blocked a real attempt).
    # solo = submit normally; try_then_fallback = ONE real click, then hand to Habib
    # ONLY on a genuine block (jobhunt-autopilot SKILL §6.1 rule 7 - never JS-click,
    # never solve a challenge, never retry); human_only = don't attempt, leave for Habib.
    GH_HUMAN_ONLY = ("affirm", "hiddenlayer")
    if job.get("board") == "greenhouse":
        job["submit_mode"] = ("human_only" if any(h in co for h in GH_HUMAN_ONLY)
                              else "try_then_fallback")
    else:
        job["submit_mode"] = "solo"
    job["needs_human_submit"] = job["submit_mode"] == "human_only"


# --------------------------------------------------------------------------- #
# Output writer (shared with scan_linkedin_guest.py)
# --------------------------------------------------------------------------- #
def emit_outputs(graded, args, n_boards, n_postings, errors, merge_boards=None,
                 report_title="Portal scan"):
    """Write the terminal report, _scan_results_latest.md/.json, and history.

    merge_boards: set of board names. When set and the existing JSON is from
    today, jobs from those boards are REPLACED and everything else is kept
    (the .md gets an appended section instead of a rewrite). Used by
    scan_linkedin_guest.py to merge into the same day's scan.
    """
    floor = GRADE_ORDER[args.min_grade]
    show = [j for j in graded
            if GRADE_ORDER[j["grade"]] >= floor
            and (args.all or j["fresh"])
            and (args.all or j["grade"] != "F")]
    show.sort(key=lambda r: (-r["score"], not r["fresh"]))

    today = dt.date.today().isoformat()
    kept = [j for j in graded if j["grade"] != "F"]
    lines = [f"# {report_title} - {today}", ""]
    lines.append(
        f"{n_boards} boards | {n_postings} postings | {len(kept)} passed filters | "
        f"showing {len(show)} at grade {args.min_grade}+"
    )
    if errors:
        lines.append("")
        lines.append("**Skipped boards:** " + ", ".join(errors))
    lines.append("")

    if not show:
        lines.append("_Nothing at this grade. Try --min-grade C, --days 0, or --all._")
    else:
        cur = None
        for j in show:
            if j["grade"] != cur:
                cur = j["grade"]
                label = {"A": "apply now", "B": "worth applying", "C": "maybe",
                         "D": "weak", "F": "dropped"}[cur]
                lines.append(f"## Grade {cur} - {label}")
            star = "" if j["fresh"] else " (seen)"
            rep = " [SEEN-COMPANY]" if j["repeat_company"] else ""
            meta = ", ".join(j["tags"]) or "no tags"
            why = (" | " + "; ".join(j["reasons"])) if j["reasons"] else ""
            lines.append(f"- **{j['title']}** ({j['score']}) - {j['company']} [{j['board']}]{star}{rep}")
            lines.append(f"  {j['location'] or '?'} - {meta}{why}")
            lines.append(f"  {j['url']}")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    # Structured sidecar for downstream tools (push_scan_to_supabase, daily brief,
    # apply sessions). All non-F jobs, regardless of --min-grade/--fresh.
    payload = [{
        "company": j["company"], "title": j["title"], "url": j["url"],
        "board": j["board"], "location": j["location"], "updated": j["updated"],
        "grade": j["grade"], "score": j["score"], "tags": j["tags"],
        "fresh": j["fresh"], "repeat_company": j["repeat_company"],
        "workplace": j.get("workplace", "unknown"),
        "is_local": bool(j.get("local_tier", "")),
        "submittable": j.get("submittable", True),
        "submit_block": j.get("submit_block", ""),
        "needs_human_submit": j.get("needs_human_submit", False),
        "submit_mode": j.get("submit_mode", "solo"),
    } for j in kept]

    if merge_boards:
        prior = []
        try:
            with open(RESULTS_JSON, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("scanned_at") == today:
                prior = [j for j in data.get("jobs", []) if j.get("board") not in merge_boards]
        except (OSError, json.JSONDecodeError):
            pass
        payload = prior + payload
        with open(RESULTS, "a", encoding="utf-8") as f:
            f.write("\n" + report + "\n")
    else:
        with open(RESULTS, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump({"scanned_at": today, "jobs": payload}, f, indent=2)

    fresh_shown = [j for j in show if j["fresh"]]
    if fresh_shown and not args.all:
        append_history(fresh_shown)
        print(f"\n[written] {RESULTS}\n[history] +{len(fresh_shown)} ids -> {HISTORY}")
    else:
        print(f"\n[written] {RESULTS}")


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-grade", default="B", choices=["A", "B", "C", "D", "F"])
    ap.add_argument("--all", action="store_true", help="include seen-before + dropped jobs")
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--board", default="")
    ap.add_argument("--workplace", default="",
                    help="comma list to keep only: remote,hybrid,onsite,unknown")
    args = ap.parse_args()

    cfg = load_config()
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
    wp_filter = {w.strip() for w in args.workplace.split(",") if w.strip()} or None

    seen = load_history()
    _SR_CFG.update(inc=inc, exc=exc, seen=seen)

    tasks = []
    if args.board:
        b, _, tok = args.board.partition(":")
        tasks.append((b, tok))
    else:
        for board, tokens in cfg["boards"].items():
            for tok in tokens or []:
                tasks.append((board, tok))

    all_jobs, errors = [], []

    def run(task):
        board, tok = task
        fn = ADAPTERS.get(board)
        if not fn:
            return board, tok, None, "no adapter"
        try:
            return board, tok, fn(tok), None
        except urllib.error.HTTPError as e:
            return board, tok, None, f"HTTP {e.code}"
        except Exception as e:
            return board, tok, None, str(e)[:50]

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for board, tok, jobs, err in ex.map(run, tasks):
            if err:
                errors.append(f"{board}:{tok} ({err})")
            else:
                all_jobs.extend(jobs)

    applied = load_applied_companies()
    applied_idx = load_applied_index()
    triaged_idx = load_triaged_index()
    graded = []
    for j in all_jobs:
        if not title_ok(j["title"], inc, exc):
            continue
        wp, tier = classify_workplace(j, loc_cfg)
        j["workplace"], j["local_tier"] = wp, tier
        keep, _why = keep_by_workplace(wp, tier, j["location"].lower(), us, non_us, hybrid_ok)
        if not keep:
            continue
        if wp_filter and wp not in wp_filter:
            continue
        if not within_days(j["updated"], args.days):
            continue
        g, score, tags, reasons = grade_job(j, sc)
        j.update(grade=g, score=score, tags=tags, reasons=reasons,
                 fresh=f"{j['board']}:{j['id']}" not in seen,
                 repeat_company=j["company"].lower() in applied)
        annotate_submittability(j, sc, applied_idx, triaged_idx)   # sets submittable/submit_block; may force F
        graded.append(j)

    emit_outputs(graded, args, len(tasks), len(all_jobs), errors)


if __name__ == "__main__":
    main()
