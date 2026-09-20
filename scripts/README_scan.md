# Find and review job openings

The scanner reads public employer job boards and saves a shortlist. It runs without Claude, a browser, or an employer account. It does not submit applications.

Supported board types are Greenhouse, Lever, Ashby, Workable, and SmartRecruiters. The company list is in [`portals.yml`](portals.yml).

## Run a search

Complete the [basic installation](../README.md#get-started-find-jobs-first), then run these commands from the repository root:

```bash
python scripts/scan_portals.py
python scripts/make_daily_brief.py
```

Read `applications/_scan_results_latest.md` and `applications/_daily_brief.md`. A JSON copy of the results is available for the application runner. Previous scans and application records help avoid showing the same jobs repeatedly.

## Change what you see

| Command option | Effect |
| --- | --- |
| `--min-grade A` | Show the strongest matches under the configured scoring rules. |
| `--min-grade C` | Include more possibilities for manual review. |
| `--all` | Include previously seen and excluded results, with reasons. |
| `--days 7` | Filter by recent posting updates where the source provides them. |
| `--workplace remote` | Show remote roles. |
| `--workplace onsite,hybrid` | Show those work arrangements. |
| `--board greenhouse:cybersheath` | Search one configured board. |

For example:

```bash
python scripts/scan_portals.py --board greenhouse:cybersheath --min-grade C
```

## Make the results fit your search

Edit `portals.yml`:

- `boards`: companies to search, grouped by their hiring platform. Use the real board name from the employer's careers page.
- `filters`: words to include or exclude in job titles.
- `location`: country signals, local cities, and acceptable work arrangements.
- `scoring`: which skills, experience levels, and role types should rank higher.

A grade is a reading priority, not a hiring prediction or an eligibility decision. The scoring rules reflect the configured search. Check the full description, exact worksite, hours, and required experience before applying. Broad city labels do not establish a commute distance.

## Current and older features

LinkedIn discovery is disabled in the checked-in configuration. Its parser and sample pages remain for maintenance and testing. The current daily scan also does not send results to Supabase.

For an existing older Supabase installation, `push_scan_to_supabase.py` can preview matching leads and optionally upload them. That needs your own private connection file and database setup. Local scans and daily briefs do not require it.

The [Linux deployment guide](../deploy/README.md) describes scheduled discovery. Start with a manual scan so you can check your search settings first.
