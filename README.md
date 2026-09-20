# Job Hunter Agent

A personal job-search and application system built around **Claude Code**, browser automation, reusable runbooks, and application tracking. It discovers roles, checks fit, prepares truthful application materials, fills employer forms, and records confirmation evidence.

## Current workflow

The current operating workflow focuses on **employer ATS portals**. LinkedIn discovery and applications are disabled in this configuration. Earlier versions used LinkedIn Easy Apply and manual submission batches; those are no longer the default.

1. **Discover:** collect public employer/ATS listings, cache responses, normalize URLs, and exclude previously handled roles.
2. **Review:** check qualifications, work authorization, worksite or remote eligibility, schedule, and candidate-provided answers.
3. **Prepare:** tailor the resume and cover letter from a private master profile and save each version with the job description.
4. **Reserve:** claim a job in a SQLite ledger before attempting an application. Pending and unresolved attempts survive process restarts and prevent duplicate submissions.
5. **Apply:** use an authenticated browser within the candidate's authorized scope. Stop for account creation, passwords, CAPTCHA, payments, or unknown personal answers.
6. **Verify:** record a submission only after visible confirmation and a saved evidence file. A filled form or a clicked Submit button is not confirmation.
7. **Track:** preserve outcomes, unresolved attempts, and follow-up dates in the private application log and pipeline database.

## What is in this repository

This is the public, reusable portion of a personal system. It includes templates, runbooks, database migrations, a dashboard component, and current application-accounting helpers. The private deployment also has scheduled discovery and browser orchestration; those machine-specific runners and candidate data are not bundled here.

```text
job-hunter-agent/
├── CLAUDE.md                         # reusable operating instructions
├── master/                           # profile/resume/cover-letter templates
├── targets/                          # role-specific tailoring notes
├── scripts/
│   ├── external_guard.py             # SQLite reservations, dedupe, limits, evidence
│   ├── external_policy.example.json  # copy to gitignored external_policy.json
│   ├── polite_http.py                # cached HTTPS JSON retrieval and backoff
│   ├── email_verification.py         # matching-code continuation for a waiting form
│   ├── test_external_workflow.py     # offline accounting/cache regression tests
│   ├── test_email_verification.py    # offline code-matching/continuation tests
│   ├── generate_pdf.py
│   └── render_pdf.py
├── supabase/                         # application-tracking schema
└── dashboard/JobHunterDashboard.jsx  # React dashboard component
```

The runtime helper snapshot was refreshed in September 2026. Public adaptations remove personal policy values, add `JOBHUNT_POLICY` for configuration, and keep tests independent of a candidate's local policy.

## Setup

### Claude Code and the private profile

Install [Claude Code](https://claude.com/claude-code), clone this repository, and start Claude in its root directory. Ask it to interview you about your actual experience, qualifications, target roles, work preferences, and application limits. Use the templates to create gitignored `master/profile.md` and `master/resume.md`.

Supply your own browser connector and authenticated session. The personal deployment uses Claude in Chrome. Verify the currently available upload tool schema and required domain permissions before relying on browser automation.

### Accounting helpers

Use Python 3.11 or later. On Windows, install `tzdata` for IANA timezone support.

```bash
python -m pip install tzdata
cp scripts/external_policy.example.json scripts/external_policy.json
# Edit your local policy before connecting any application runner.
python scripts/external_guard.py status
```

`JOBHUNT_APPLICATIONS` can point to an alternative private application directory; `JOBHUNT_POLICY` can point to your local policy file. The guard's CLI records accounting state; it does not browse sites or submit applications.

The example limits are configurable budgets, not submission targets or promises. The current fit-review helper assumes California eligibility and weekday business hours. Adapt that logic to your own requirements before reuse.

### Optional tracking and presentation

The `supabase/` migrations define the pipeline database. Keep your connection details in gitignored `supabase/connection.local.md`. The React dashboard is a component for integration into your own frontend, not a separately packaged application.

The PDF scripts are optional and have separate rendering dependencies. Check their module documentation before use and verify every generated document visually.

## Reliability helpers

- **Durable accounting:** canonical job keys, transactional reservations, daily and batch limits, employer limits, pacing, and persistent cooldowns.
- **Conservative status:** pending and unconfirmed attempts remain distinct from confirmed submissions. Unresolved attempts are not retried blindly.
- **HTTP discovery:** HTTPS JSON caching and per-host pacing; `Retry-After` and error cooldowns persist across restarts.
- **Email verification:** a waiting Greenhouse form can resume only with a recent, unused code matching the expected sender and employer-specific subject. Used code values are removed from the local code file.

The email helper does not fetch email or provide a mailbox connection. A separately authorized collector must supply the private code file. Codes and mailbox data must never be committed.

## Known limitations

The personal-answer validator currently checks `unmapped_required` questions. It is **not a complete validation of every mapped answer**, and the confirmation guard requires evidence files but does not establish that their contents prove success. A supervising runner must check final field values against the candidate's authoritative profile and inspect the actual confirmation.

Browser challenges and ATS changes can still prevent completion. No application count, interview rate, or hiring outcome is guaranteed.

## Offline tests

```bash
python -m unittest discover -s scripts -p "test_*.py"
```

The included tests use temporary files, synthetic application records, and stubbed HTTP responses. They do not contact employers, submit applications, or read a mailbox.

## Privacy

Real resumes, application histories, screening answers, mailbox codes, credentials, and deployment logs stay local or in the private deployment. `.gitignore` excludes the corresponding paths. Review every staged file before publishing a fork.
