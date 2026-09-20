# External job-application batch template

## Required Q&A recording (Habib, 2026-09-18)

Record every question received and the exact answer provided in all job interviews,
screenings, assessments, recruiter exchanges and application forms from now on.
Read and follow `/opt/job-hunter/scripts/INTERVIEW-QA.md` before answering questions. Keep full wording, company,
role, source, timestamps and draft/submitted/confirmed status; append revisions and
outcomes. The journal is `/opt/job-hunter/applications/_interview_qa.md`.
The form helper captures actual values automatically. Log other exchanges using
`python3 /opt/job-hunter/scripts/interview_qa.py record --input <json-file>`.
Never invent past exchanges, silently omit recording, or store security codes.
This changes recording only; existing submission and messaging permissions still apply.


Your job is to submit real applications and generate interviews for the configured candidate, within their explicit authorization.
Use the existing jobhunt project /opt/job-hunter.
Read master/profile.md, master/resume.md, scripts/external_policy.json,
applications/_external_queue_current.json and applications/_run_log.md.

## Current user instructions override old search and LinkedIn instructions

- Target 100 unique CONFIRMED employer-site applications per Pacific calendar day.
  This batch targets up to 15 confirmed applications within 45 minutes. Count
  confirmations, not forms filled or clicks. Never force unsuitable applications
  to meet a number. Record an honest shortfall and the reasons if the queue runs out.
- NO LINKEDIN. No LinkedIn applications, discovery, login checks, tabs or automated
  requests. External browser access does not depend on LinkedIn preflight.
- Preferred job: REMOTE, eligible to hire a California resident.
- In-person/hybrid acceptable ONLY within the configured distance of the candidate's home location. Confirm the actual
  worksite and distance; a broad Los Angeles city label is insufficient evidence.
- Work availability is Monday-Friday, 9 a.m.-5 p.m. Pacific. Seek regular weekday
  daytime work. Do not promise evenings, weekends, overnight or on-call coverage.
  For remote roles, convert any stated working timezone before accepting a shift.
  An unstated schedule may be considered; state the actual availability wherever
  asked and request clarification rather than asserting the employer's hours fit.
- Use the candidate's confirmed start-date rule and employment constraints from
  their private profile. Do not infer a notice period or employment restrictions.
- No salary floor. Prioritize realistic customer/IT/office support, recruiting
  coordination, administrative/data-entry/operations and junior technical roles.
  Retail/security/dispatch qualify only if their actual hours fit. Avoid 5+ year
  roles and skills/licenses he does not have. Keep prior employer values exclusions.

## Reliable submission, paced and recorded

Use only the candidate's approved resume, supplied by HJ_RESUME or the deployment's
configured resume path. Verify the file against their private source of truth.
Do not substitute another resume without their authorization.

Use /opt/pw-venv/bin/python scratchpad/gh_apply.py for supported ATS forms, with
DISPLAY=:99. The helper includes scripts/external_guard.py, which atomically
reserves before a click and records affirmative confirmation with a unique
evidence screenshot. Existing form sessions should be reused where practical.
Do not apply to the same role again after an uncertain result; inspect receipts.

Each --submit config must include company, title and review:
{"fit_reviewed":true,"schedule_notes":"actual JD schedule or explicitly not stated",
 "schedule_conflict":false,"workplace":"remote","ca_eligible":true}
For onsite/hybrid use workplace accordingly and include verified distance_miles
and distance_evidence instead of assuming a city fits. All entries must reflect
your actual review. Do not set flags just to get past the guard.

Before any OTHER browser submission, call scripts/external_guard.py reserve with
--url, --company, --title and --batch from JOBHUNT_BATCH_ID. Only GO allows a click.
After a visible confirmation, save evidence and call finish --confirmed --evidence
<observed URL/text> --proof <saved file>. Otherwise finish without --confirmed.
Never bypass the guard by rewriting its database, replacing the helper, or using
a direct POST to submit. A completed application still goes into _run_log.md.

The guard sets a 100/day cap, 15/batch cap, 2 applications/employer/day and at least
120 seconds between submission attempts. These are maximums and minimum spacing,
not a promise that any website allows those rates. Site-specific limits prevail.
For WAIT, work on reviewing a different job; avoid tight polling or submitting in
parallel. For a source cooldown, switch to another eligible employer/source.

Never create accounts, enter passwords, disclose SSN/bank details, pay fees or solve
CAPTCHAs. Ordinary email security codes for a job application are authorized: keep the form open and use Gmail to retrieve the matching current message. Stop on CAPTCHA/access challenges. For403/429 or a visible block,
record a source cooldown with external_guard.py block, honoring Retry-After when
provided. Do not rotate proxies, fingerprints or identities to evade a limit.
Do not conceal automation through fabricated personal details or claims.

Use real labels and the public ATS question schema to match fields, not fragile
positional selectors. Read and answer required questions truthfully. Required
answers not in the profile are a reason to queue for user input, never guess.
Write concise role-specific cover letters only if useful (four truthful sentences).
Do not mention financial hardship. Never use generic claims of perfect attendance,
reliable transportation or unknown clinical/industry experience.

## Discovery and continuation

Start with the durable _external_queue_current.json. The wrapper refreshes public
ATS discovery at most every four hours. Cached JSON, per-host pacing and persisted
Retry-After cooldowns reduce repeat traffic. Do not run a full scan each application.
Public APIs already provide structured job data. See applications/_scrapling_notes.md
for the Scrapling design lessons; do not install proxies or challenge solvers.

Read actual fresh employer pages before applying; cached discovery is only a lead.
If the queue cannot supply a batch, search official employer career sites for
additional matching jobs, using Greenhouse, Lever, Ashby or other allowed portals.
Add verified board tokens to scripts/portals.yml when useful; don't invent URLs.
Reject closed roles, duplicates and schedule/geography/qualification mismatches.
Save skipped reasons in the ledger and preserve unattempted viable jobs.

If 15 consecutive tool calls produce no confirmation, checkpoint the blocker and
stop the failing route. Don't spend the whole batch debugging one employer's form.
Never count an absent Submit button as success. The employer must confirm receipt.

## Mailbox and existing work

Read the private application ledger and current mailbox state when separately authorized.
Do not send recruiter messages without the owner's authorization. Preserve existing
drafts, confirmed applications, and unresolved attempts. The public template omits
personal application outcomes, email draft identifiers, and screening answers.

## Automatic email-code skill
Read /opt/job-hunter/deploy/email-verification/SKILL.md when a form requests a code.
The jobhunt-email-verification.path service automatically starts a Gmail reader as soon
as the helper writes a live verification request. Leave the application open; the
helper waits four minutes and consumes the code. Avoid starting another mailbox
reader while jobhunt-email-verification.service is active. The helper uses the actual
employer display name, including Varda Space Industries for the vardaspace board.
Do not rewrite message subjects, change the guard DB, or retry confirmed applications.
If the browser still lacks confirmation after the timeout, report the actual blocker.
The service retrieves codes only; the normal browser helper handles submission proof.
