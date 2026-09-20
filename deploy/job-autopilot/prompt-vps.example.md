# Application batch instructions

Work only within the owner's explicit authorization. Read their private profile,
approved resume, `scripts/external_policy.json`, application queue, and existing log
before beginning. Use the limits in the policy; never apply to an unsuitable role
to reach a count. Ask for missing facts and preserve uncertain attempts for review.

Use the repository identified by `JOBHUNT_ROOT`, or the working directory supplied
by the batch runner. Follow `scripts/INTERVIEW-QA.md` to record the full questions,
actual answers, revisions, and final outcome. Never invent past exchanges.

## Review each role

- Read the current employer description and check experience, qualifications,
  worksite, work authorization, schedule, and the owner's stated preferences.
- The included submission checker assumes California eligibility and weekday
  work. Adapt the checker before using a different set of requirements.
- Use the approved resume from `HJ_RESUME` or `master/resume.pdf`. Review any
  proposed resume changes separately. Use only confirmed personal information.
- LinkedIn discovery and applications are disabled in this configuration.
- Stop for missing answers, accounts, passwords, CAPTCHAs, payments, or a role
  that conflicts with the candidate's requirements.

## Fill, review, and confirm

Use `scratchpad/gh_apply.py` for supported forms. Store each form's configuration
under the private `applications/` directory. Before `--submit`, include `company`,
`title`, and truthful `review` fields expected by `validate_review` in
`scripts/external_guard.py`. Do not mark a check complete without doing the review.

The helper does not validate every mapped answer. Read the final field values and
uploaded resume before submitting. For other browser tools, reserve the attempt
with `external_guard.py reserve` before clicking Submit. Continue only on `GO`.
Respect pacing and cooldowns. Do not change identities or bypass site challenges.

Save the visible employer confirmation and record it with the guard. A filled
form, clicked button, email code, or screenshot file alone is not confirmation.
Keep uncertain outcomes separate and inspect them before trying again.

Only use the email collector if the owner has separately authorized reading and
using application codes and Gmail is configured. Otherwise ask the owner to
complete that step. Do not send email or change account settings.

## Finish the batch

Update `applications/_run_log.md` and the question-and-answer journal. Report
confirmed submissions, unresolved attempts, skipped roles, missing answers, and
any recording gaps. Keep contact details, codes, and private answers out of public
reports. A shortfall is an honest result; do not claim an interview or submission
that was not observed.
