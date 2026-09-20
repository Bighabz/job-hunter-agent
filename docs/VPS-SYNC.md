# VPS source synchronization

This snapshot was read from the active personal VPS on September 20, 2026. It includes the current source and deployment wiring, including changes that were still untracked in the VPS Git checkout.

## Included

- All source, configuration, documentation, and parser fixtures under the VPS project's `scripts/`, except the private policy file.
- `scratchpad/gh_apply.py`, the actual Playwright application helper used by the runner.
- Current question/answer capture and journal modules, including the September 18 recording instructions.
- The Linux and legacy Windows wrappers from the separate `job-autopilot` directory.
- The active systemd services, timers, and email-verification path unit.
- The daily discovery wrapper and the event-driven Gmail code collector.
- The two target-archetype files with their current VPS updates.

[vps-source-manifest.json](vps-source-manifest.json) records source hashes, published hashes, and every deliberate difference. Runtime source files are copied without changing their logic. One scanner regression assertion is updated from the obsolete `OC-borderline` tag to the current `distance-check-required` tag.

## Private configuration

`scripts/external_policy.example.json` retains the deployed operational limits but replaces the candidate's postal code and removes confirmed personal answers. Copy it to gitignored `scripts/external_policy.json` and supply your own verified facts.

`deploy/job-autopilot/prompt-vps.example.md` is derived from the live prompt with private application history, draft identifiers, resume fingerprint, and screening answers removed. The email skill is similarly redacted. The root `CLAUDE.md` is a public operating guide, not a copy of private candidate context.

Candidate documents, application folders, generated per-application scripts/configurations, journals, SQLite databases, logs, credentials, browser state, and historical private Git backups are excluded.

## Deployment layout

The exact source retains the running VPS's paths:

| Repository content | Source deployment location |
| --- | --- |
| Project root | `/opt/job-hunter` |
| `deploy/job-autopilot/` | `/opt/job-hunter/deploy/job-autopilot` |
| `deploy/run_daily_scan.sh` | `/home/jobhunter/jobhunter/run_daily_scan.sh` |
| `deploy/email-verification/` | `/opt/job-hunter/deploy/email-verification` |
| `deploy/systemd/` | `/etc/systemd/system` |

The active application timer runs hourly at minute 23 from 08:23 through 22:23 Pacific. The discovery timer runs at 09:00 in the server timezone. The live policy uses a 100/day ceiling, 15/batch ceiling, at least 120 seconds between submission attempts, and 2 applications per employer per day. These limits do not imply that any site permits those rates or that the target is reached.

The Linux batch wrapper uses `fcntl` locking, a 45-minute runner timeout, `DISPLAY=:99`, and an existing Chrome service. The Gmail collector depends on the owner's separately configured Gmail MCP connection. `alert@.service`, Chrome/display services, authentication, and candidate files are host dependencies and are not part of this application repository.

The legacy Windows wrapper expects its own private `prompt.md`; the current Linux wrapper reads `prompt-vps.md`. Copy and adapt the example only after configuring the intended deployment. This source sync does not install services, launch applications, or change the active VPS.

## Current versus legacy components

- LinkedIn is disabled in the checked-in `portals.yml`. Its parser and fixtures remain for source/history coverage.
- The active daily scan no longer pushes to Supabase. The local ledger is authoritative; the old schema, dashboard, and sync script remain available.
- Scanner documentation contains historical v2 notes. The checked-in configuration and current runner instructions take precedence.
- The personal-answer validation gap described in the root README remains present in the running source; this synchronization does not claim to fix it.

## Verification

Run `python -m unittest discover -s scripts -p "test_*.py"`. PyYAML is required for scanner tests; Playwright and Chrome are required for browser fixture tests. Browser tests render synthetic local HTML and do not contact job boards or submit applications.

The snapshot is also checked against the manifest and parsed for Python syntax. Public-copy testing uses an isolated temporary directory on the VPS, away from its live candidate data and application state.

Verified September 20: all 63 tests are covered. System Python passes 58 tests and skips the five browser fixtures; the existing Playwright environment then passes all 10 question/answer tests, including those five browser fixtures. No applications or mailbox reads are performed by these tests.
