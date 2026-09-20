# Job Hunter Agent operating instructions

## Current question and answer recording

Follow [scripts/INTERVIEW-QA.md](scripts/INTERVIEW-QA.md). Record the full question and exact answer for application forms, interviews, screenings, assessments, and authorized recruiter exchanges. Preserve revisions and distinguish observed, draft, filled, submitted, confirmed, and outcome states. The current form helper captures browser field values into the private SQLite/Markdown journal. Never log passwords, verification codes, or financial identifiers.

## Scope and source of truth

Use this repository to prepare and track job applications for its owner. Read the owner's explicit current instructions, private `master/profile.md`, and private `master/resume.md` before preparing materials. The public templates and target archetypes are prompts for tailoring, not evidence of the owner's qualifications.

This repository's current workflow is employer-ATS focused. LinkedIn is disabled in the example policy. Do not change that scope or activate a scheduler merely because a runbook describes one.

## Authorization and truthful answers

- Follow the owner's requested approval or submission policy. A repository checkout alone does not authorize sending applications or contacting recruiters.
- Never invent credentials, experience, work authorization, employment restrictions, personal narratives, or availability.
- Ask for unknown required personal facts. Previously supplied facts do not need repeated confirmation.
- Stop for account creation, password entry, CAPTCHA, payments, or sensitive data outside the authorized scope. Do not bypass access controls or challenges.

## Application workflow

1. Verify browser access, required domain permissions, and resume upload support before an application run.
2. Read the full job description. Check qualifications, location, work authorization, compensation, and schedule against the owner's profile.
3. Deduplicate by canonical job URL and the private ledger. Reserve the application before interacting with a submission flow.
4. Preserve the owner's approved resume and verify its configured path. Do not generate or substitute a resume unless explicitly instructed. Save the job description, any authorized cover-letter text, and notes under `applications/{company}_{role}_{date}/`.
5. Review every final browser field against the authoritative profile. The helper's `unmapped_required` check does not validate all mapped answers.
6. Submit only within the owner's explicit scope. Treat unknown required answers as a hold.
7. Require a visible confirmation and saved evidence before recording `confirmed`. A click, timeout, or filled form is not evidence of success.
8. Log confirmed, skipped, blocked, and unresolved states immediately. Never turn an unresolved attempt into a new submission without reconciliation.

## Runtime limits

Load candidate-specific limits from gitignored `scripts/external_policy.json`. Keep application state under `JOBHUNT_APPLICATIONS` or the gitignored `applications/` directory. Respect host cooldowns, `Retry-After`, daily/batch budgets, and the configured spacing between attempts.

Use bounded batches and checkpoint on failures. Do not repeatedly dispatch work into a known permission, upload, CAPTCHA, or rate-limit blocker.

## Email verification

Use `email_verification.py` only for an existing waiting application and a separately authorized mailbox collector. Match the sender, employer-specific subject, freshness, and unused status. Never print or commit verification codes. Resuming a form still requires confirmation before the application can be counted.

## Privacy and publishing

Keep real profiles, resumes, cover letters, application records, policies, credentials, browser state, mailbox data, and logs out of Git. The public repository contains reusable code and examples. A production runner must remain separately configured.

Before publishing changes, inspect the staged diff for personal data and secrets, and run the relevant offline tests. Documentation updates must distinguish shipped public files from private deployment components.
