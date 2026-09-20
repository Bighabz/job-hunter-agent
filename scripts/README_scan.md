# Portal Scanner — zero-cost daily job discovery

`scan_portals.py` hits Greenhouse / Lever / Ashby / Workable / SmartRecruiters **public
APIs** directly. No browser, no LLM tokens, no login. It pulls every posting from the
boards in `portals.yml`, filters by title + workplace/location, drops jobs you've already
seen, and prints a clean list of fresh, qualifying roles. Built 2026-06-03; v2 2026-07-03
added workplace-aware local/hybrid discovery, two new ATS families, and the LinkedIn
guest scanner.

## v2: workplace-aware keep matrix (classify_workplace + keep_by_workplace)

Every job is classified `remote | hybrid | onsite | unknown` (structured ATS fields
first — Lever workplaceType, Ashby isRemote, Workable telecommuting, SR location.remote/
hybrid — then location/desc strings) and matched against the Gardena commute list
(`portals.yml location.local_cities` + `local_borderline`):

| workplace | kept? |
|---|---|
| remote | always (US-scoped) |
| hybrid | only if LOCAL (and `location.hybrid_ok`) |
| onsite | only if LOCAL — fixes v1 silently dropping "Torrance, CA" AND leaking onsite New York |
| unknown | if a US signal is present (tagged `wp:unknown`) |

New CLI flag: `--workplace onsite,hybrid` (filter output). The JSON sidecar now carries
`workplace` and `is_local` per job. New scoring track `physical_security` (GSOC/officer/
access-control roles per targets/esoc_analyst.md + federal_security.md).

## v2: LinkedIn guest scanner (`scan_linkedin_guest.py`)

Zero-auth discovery over LinkedIn's public guest endpoints (search cards + /jobs/view
detail). Query sets in `portals.yml linkedin:`: **remote** (US, f_WT=2), **hybrid_local**
and **onsite_local** (Gardena + 25 mi, f_WT=3/1 — incl. security-officer/GSOC keywords).
Anti-block budgets: ≤3 pages/query, ≤4 keywords/set/run (rotation persisted in
`_li_rotation.json`), ≤60 detail fetches/run, 1.5–2.5 s jittered delay per request.
Cards don't reveal workplace, so the query's f_WT is stamped as the hint. On 429/999/
authwall the run stops gracefully (partial results written, note in the report, exit 0).
Results merge into the SAME `_scan_results_latest.{md,json}` with `board: linkedin`.

```bash
python scan_linkedin_guest.py                        # all sets
python scan_linkedin_guest.py --set onsite_local --max-details 5 --dry
```

## v2: daily brief + schedule

`make_daily_brief.py` condenses the JSON into `applications/_daily_brief.md` (counts,
top-10 fresh queue, every local onsite/hybrid job). The whole chain runs headless at
09:00 via the "JobHunter Daily Scan" Windows task (`run_daily_scan.cmd`; errors append
to `applications/_scan_errors.log`); apply sessions run at 10:00/18:00. Tests:
`python -m unittest test_scan_v2 -v`.

## Run it

```bash
cd job-hunter/scripts
python scan_portals.py                 # grade B+ jobs, fresh since last scan
python scan_portals.py --min-grade A   # only the best fits
python scan_portals.py --min-grade C   # widen the net
python scan_portals.py --all           # include seen-before + dropped (shows WHY dropped)
python scan_portals.py --days 7        # only postings updated in last 7 days (GH/Lever)
python scan_portals.py --board greenhouse:cybersheath   # one board
```

Outputs:
- terminal: grouped by **grade A-F**, each with score, tags, pay, location
- `applications/_scan_results_latest.md` — same report, saved
- `applications/_scan_history.tsv` — every job id ever seen (so it won't reappear)

## Grading (A-F, zero LLM)

Each job is scored on its actual JD text (pulled free in the same API call):

- **Track fit** (required, else capped at C): applied-AI / entry-cyber / cloud-devops / data / IT-support
- **Entry-level** (+1.0, and required for grade A): "junior/associate/entry/new grad/Analyst I/0-2 yrs"
- **CA proximity** (+0.5): Gardena/LA/Hawthorne/Irvine/etc.  **Remote** (+0.3)
- **Claude / AI-tooling** (+0.4): mentions Claude, Claude Code, MCP, Cursor, agents
- **AI-adoption / consulting** (+0.3 each): the "fun" buckets
- **Pay band**: $85-140k +0.6, $73-85k +0.3, $140-200k neutral, **>$200k -0.5 (senior signal)**

**Hard-dropped (graded F, hidden unless `--all`):** security clearance required, 5+ years
experience, pay below $73k, advanced-degree-required, and AI-training/data-labeling/sales
shops (Turing, DataAnnotation, etc.). Senior/Staff/Principal/VP/Research titles are excluded
up front. High pay and prestige are treated as SENIOR signals, not fit — grade A means
"realistic entry-level job," not "impressive job."

Tune any of this in `portals.yml` under `scoring:`.

## The daily flow this enables

1. `python scan_portals.py` → free list of new jobs (~10s, no browser).
2. Triage the survivors with guest WebFetch (read the JD from `linkedin.com/jobs/view/<id>`
   or the greenhouse/lever URL) to kill fake-entry-level (6yr+CISSP) traps.
3. Open ONLY the real fits in the browser to apply — **with the Chrome window visible**
   (LinkedIn/Greenhouse won't render apply buttons in a background tab).

## Push graded leads to Supabase

`push_scan_to_supabase.py` reads the scan's JSON sidecar, keeps grade A/B, dedupes against
`jd_url`s already in the `applications` table, and inserts the rest as `status='saved'`.
Idempotent — re-running never duplicates. Connection (URL + anon key) is read at runtime
from `supabase/connection.local.md`; the key is never printed or committed.

```bash
python scan_portals.py                       # produce the JSON first
python push_scan_to_supabase.py              # dry-run: show what WOULD insert
python push_scan_to_supabase.py --grades A --push   # insert grade A (recommended; B is noisy)
python push_scan_to_supabase.py --grades AB --push  # insert A+B
```

Confirmed working 2026-06-03: anon key allows insert (RLS not blocking); 16 grade-A leads
pushed. Grade B leaks $175k senior SpaceX SWE + payroll/benefits analysts (the `applied-ai`
track over-fires on any JD mentioning "AI") — push A only until that's tightened.

## Tuning `portals.yml`

- **Add a company:** find its careers page, spot the ATS, add the board token under
  `greenhouse:` / `lever:` / `ashby:`. Dead boards are skipped, never fatal.
- **Too noisy?** The mega-boards (Anduril, SpaceX) post hundreds of defense/hardware roles.
  Drop them from `portals.yml`, or skim them — the cyber-focused boards stay tight (1-11 each).
- **Filters:** `filters.include` = title must contain one; `filters.exclude` = title must
  contain none (seniority + wrong-function gates, incl. `" ii"/" iii"` to keep it entry-level).
  `location.us_signals` / `non_us_signals` keep US/remote and drop foreign-country postings.

This is discovery + triage only. It never submits anything.
