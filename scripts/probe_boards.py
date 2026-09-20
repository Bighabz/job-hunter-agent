#!/usr/bin/env python3
"""Probe candidate ATS board tokens against the live PUBLIC APIs.

Confirms which Greenhouse/Lever/Ashby board slugs are real + reachable, how many
postings they carry, and a sample of entry-ish titles — so we only add VALID,
fit-bearing boards to portals.yml. Zero browser, zero auth, zero LLM.

Usage: python probe_boards.py
Edit CANDIDATES below to test new companies.
"""
import json
import urllib.request
import urllib.error

# Companies that tend to hire ENTRY/MID remote SOC / security / IT / data roles
# (MSSPs, mid-market security vendors, SaaS). Tokens are best-guess slugs; the
# probe tells us which are real.
CANDIDATES = {
    "greenhouse": [
        "arcticwolf", "huntress", "deepwatch", "redcanary", "binarydefense",
        "criticalstart", "pondurance", "expel", "recordedfuture", "rapid7",
        "tenable", "sentinelone", "abnormalsecurity", "wiz", "netskope",
        "snyk", "sumologic", "cribl", "sysdig", "orcasecurity", "semgrep",
        "bugcrowd", "hackerone", "synack", "optiv", "secureworks", "mandiant",
        "datadog", "elastic", "hashicorp", "okta", "cloudflareinc", "fastly",
        "grafanalabs", "confluent", "mongodb", "twilio", "fivetran", "dbtlabs",
        "starburst", "lacework", "coalition", "vannevarlabs", "scaleai",
    ],
    "lever": [
        "plaid", "brex", "ramp", "attentive", "huntress", "deepwatch",
        "coalition", "vannevar",
    ],
    "ashby": [
        "ramp", "notion", "runway", "openai", "anthropic", "cohere",
        "deepwatch", "coalition", "huntress",
    ],
    # v2 (2026-07-03): Workable widget API — MSSP/security/staffing candidates
    "workable": [
        "criticalstart", "silversky", "cyderes", "guidepoint-security",
        "evolve-security", "bishopfox", "blackpoint-cyber", "todyl", "redscan",
        "nettitude",
    ],
    # v2: SmartRecruiters — identifier is CASE-SENSITIVE; probe both casings.
    # Physical-security giants (Habib's esoc/federal archetypes) + big IT.
    "smartrecruiters": [
        "AlliedUniversal", "alliedu", "GardaWorld", "gardaworld", "Prosegur",
        "Pinkerton", "InterConSecurity", "intercon", "ParagonSystems",
        "paragonsystems", "Experian", "Equinix", "McKesson", "AECOM",
        "PaloAltoNetworks2",
    ],
}

UA = {"User-Agent": "Mozilla/5.0 (board-probe)"}


def fetch(url, method="GET", data=None):
    req = urllib.request.Request(url, headers=UA, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(data).encode()
    with urllib.request.urlopen(req, data=data, timeout=15) as r:
        return json.loads(r.read().decode())


ENTRY = ("analyst i", "soc analyst", "junior", "associate", "entry", "tier 1",
         "i,", "i ", "new grad", "support", "early career", "ii")


def sample_titles(titles):
    hits = [t for t in titles if any(k in t.lower() for k in ENTRY)]
    return hits[:6]


def probe_greenhouse(tok):
    data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs")
    jobs = data.get("jobs", [])
    return [j.get("title", "") for j in jobs]


def probe_lever(tok):
    data = fetch(f"https://api.lever.co/v0/postings/{tok}?mode=json")
    return [j.get("text", "") for j in data]


def probe_ashby(tok):
    data = fetch(
        f"https://api.ashbyhq.com/posting-api/job-board/{tok}?includeCompensation=true"
    )
    jobs = data.get("jobs", [])
    return [j.get("title", "") for j in jobs]


def probe_workable(tok):
    # cheap probe: no details=true (titles only)
    data = fetch(f"https://apply.workable.com/api/v1/widget/accounts/{tok}")
    return [j.get("title", "") for j in data.get("jobs", [])]


def probe_smartrecruiters(tok):
    data = fetch(f"https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit=100")
    total = data.get("totalFound")
    print(f"          totalFound={total}")
    return [p.get("name", "") for p in data.get("content", [])]


PROBERS = {"greenhouse": probe_greenhouse, "lever": probe_lever, "ashby": probe_ashby,
           "workable": probe_workable, "smartrecruiters": probe_smartrecruiters}

for ats, tokens in CANDIDATES.items():
    print(f"\n===== {ats.upper()} =====")
    for tok in tokens:
        try:
            titles = PROBERS[ats](tok)
            samp = sample_titles(titles)
            flag = "  <-- entry fits" if samp else ""
            print(f"  OK  {tok:20s} {len(titles):4d} jobs{flag}")
            for s in samp:
                print(f"          - {s[:70]}")
        except urllib.error.HTTPError as e:
            print(f"  --  {tok:20s} HTTP {e.code}")
        except Exception as e:
            print(f"  --  {tok:20s} {type(e).__name__}")
