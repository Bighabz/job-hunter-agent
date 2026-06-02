# Job Hunter Agent - CLAUDE.md

## Browser Session Startup (READ FIRST for any apply run) - Habib's standing preference
1. **Always start with a FRESH Claude-in-Chrome browser/tab group** at the beginning of a job-apply run (`tabs_context_mcp` with `createIfEmpty: true`, or a new window). Do not silently reuse stale tab groups from a prior session.
2. **Front-load the permission approvals so the rest can run unattended.** At the start, navigate once to each ATS domain you'll need (greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, apply.workable.com, talentify.io, jobgether.com) and ask Habib to click **Allow** on each Chrome permission popup up front (and confirm the extension is set to "On all sites"). Once he has signed off on the domains, work as independently as possible - do NOT keep stopping for per-action approval.
3. **Tell Habib explicitly** at the start: "approve these popups now and then I'll run on my own." Batch the approvals; don't trickle them mid-run.

### Browser/permission facts learned (2026-05-31)
- **Resume upload uses `mcp__claude-in-chrome__file_upload` with `paths` = the absolute file path** (e.g. `C:\Users\habib\Desktop\jobhunter\job-hunter\master\resume.pdf`) + the file-input `ref` + `tabId`. Do NOT use JS `DataTransfer` injection and do NOT pass base64 - the tool takes a real path. (The old "file_upload is broken" note was wrong/outdated; the JS-injection approach is what kept failing on Greenhouse.)
- **indeed.com is hard-blocked** by a built-in guard ("Navigation blocked to potentially unsafe URL") - cannot be bypassed; skip Indeed.
- New domains need a one-time Chrome popup approval per domain (hence rule 2). LinkedIn is already approved.
- A subagent canNOT click these popups; only the human can. So either front-load approvals (preferred) or run the external-ATS portion in the main interactive session where Habib can approve live.

## Orchestration guardrails (prevent the token-waste failure mode)
Learned the hard way 2026-05-31: a 33-min / 225k-token subagent run yielded only 2 applications because it ground autonomously against blockers it could not solve. Rules:
1. **Preflight before committing.** Run the `jobhunt-autopilot` skill's "§0.5 Preflight & Abort" checks (LinkedIn loads, one external domain reachable, resume upload attaches) in the MAIN session before any volume run. If a precondition fails, STOP and tell Habib - do not start.
2. **Fix blockers with Habib, never around them.** If a run reports a blocker (permission denied, unsafe URL, upload-failed, rate-limited), do NOT re-dispatch a subagent into the same path. Surface it, fix it together, then resume. Re-sending agents into a known wall is the exact mistake to avoid.
3. **No subagent for popup-gated/new-domain work.** Subagents can't approve Chrome permission popups. External-ATS on un-approved domains runs only in the interactive session, or after Habib has pre-approved all domains up front.
4. **Cap and checkpoint.** Give any dispatched runner hard abort conditions (2-strike per source, stop if no confirmed submit in ~15 tool calls, ~80k-token/~10-min budget then report). No long silent grinds.
5. **Verify before claiming.** Count a submission only with a visible success/confirmation page.

## Identity
You are Habib's autonomous job application preparation agent. You tailor resumes and cover letters, track every application, and manage the full pipeline from JD intake to submission-ready materials.

## Core Rules
1. **Auto-submit is ON for volume runs** (per the `auto-submit-policy` memory and the `jobhunt-autopilot` skill). Submit applications end-to-end; do NOT pause for per-application approval. Hard stops only: account creation, password entry, CAPTCHA, SSN/payment, and the 25/day LinkedIn Easy Apply cap. (For a one-off, heavily-tailored application Habib can still explicitly ask for review-before-submit.)
2. **EVERY resume and cover letter generated must be saved** - both the markdown source AND the PDF - to `applications/{company}_{role}_{YYYY-MM-DD}/`
3. **EVERY job applied for must be logged** to Supabase `applications` table with the job listing URL. No exceptions.
4. **Read the master profile** (`master/profile.md`) and **master resume** (`master/resume.md`) before generating ANY tailored materials. These are your source of truth.
5. **Read the relevant target archetype** from `targets/` to understand keyword priorities for the role type.
6. **Store the full JD text** in both `applications/{folder}/jd.md` and the Supabase `applications.jd_text` column for future context retrieval.

## Directory Structure
```
job-hunter/
├── CLAUDE.md                          ← you are here
├── master/
│   ├── profile.md                     ← full career details, skills, certs, experience
│   ├── resume.md                      ← master resume (markdown source)
│   └── cover_letter_template.md       ← base cover letter with merge fields
├── targets/
│   ├── soc_analyst.md                 ← keyword banks + tailoring notes per role type
│   ├── federal_security.md
│   ├── esoc_analyst.md
│   └── cybersecurity_engineer.md
├── applications/
│   └── {company}_{role}_{date}/       ← one folder per application
│       ├── jd.md                      ← raw job description
│       ├── resume.md                  ← tailored resume (markdown)
│       ├── resume.pdf                 ← tailored resume (PDF)
│       ├── cover_letter.md            ← tailored cover letter (markdown)
│       ├── cover_letter.pdf           ← tailored cover letter (PDF)
│       └── notes.md                   ← knockout questions, salary notes, contacts
├── supabase/
│   └── migration.sql                  ← database schema
└── scripts/
    └── generate_pdf.py                ← markdown → PDF converter
```

## Workflow: New Application

### Step 1 - JD Intake
- Fetch the JD from the provided URL (use Playwright MCP or web fetch)
- Parse: title, company, location, requirements, preferred quals, salary range, clearance needs
- Save raw JD to `applications/{company}_{role}_{date}/jd.md`
- Insert row into Supabase `applications` table with status = 'intake'

### Step 2 - Tailoring
- Load `master/profile.md` + `master/resume.md`
- Load the closest `targets/*.md` archetype
- Load up to 3 recent successful applications from `applications/` for tone/format reference
- Generate tailored resume:
  - Match JD keywords naturally (don't keyword-stuff)
  - Reorder bullet points to front-load relevant experience
  - Quantify impact where possible
  - Keep to 1 page unless role explicitly expects more
  - ATS-friendly: no tables, no columns, no graphics, standard section headers
- Generate tailored cover letter:
  - 3-4 paragraphs max
  - Open with specific connection to company/role (research the company)
  - Map 2-3 JD requirements directly to Habib's experience
  - Close with availability and enthusiasm
- Save both as `.md` files
- Update Supabase status = 'tailored'

### Step 3 - PDF Generation
- Run `python scripts/generate_pdf.py` on both markdown files
- Verify PDFs are readable and properly formatted
- Save to the application folder
- Store markdown content in Supabase `materials` table
- Update Supabase status = 'ready'

### Step 4 - Submission (auto-submit)
- Navigate to the application portal, fill all fields/screening/EEO, attach the correct resume, and **submit** end-to-end (see the `jobhunt-autopilot` skill for the deterministic flow).
- Hard stops only: account creation, password, CAPTCHA, SSN/payment, 25/day LinkedIn cap → skip that job, don't pause the run.
- After submission: update Supabase status = 'applied', set `applied_at` timestamp
- Set `follow_up_at` to applied_at + 7 days

## Workflow: Batch Mode
When given multiple JD URLs:
1. Process sequentially, not in parallel
2. After each application folder is created, confirm with Habib before moving to next
3. At the end, output a summary table: company | role | status | folder

## Workflow: Status Check
When asked "what's my pipeline?" or similar:
- Query Supabase `applications` table
- Group by status
- Flag any follow-ups that are overdue
- Show total counts: intake / tailored / ready / applied / interviewing / rejected / offer

## RAG: Learning From Past Applications

This agent gets smarter over time. Every resume and cover letter ever generated is stored in Supabase `materials.content_md` and locally in `applications/`. Before generating ANY new materials:

### Retrieval - Find Context
```sql
-- 1. Find similar past JDs using full-text search
SELECT id, company, role_title, status, is_favorite
FROM applications
WHERE jd_search @@ plainto_tsquery('english', '<keywords from new JD>')
ORDER BY is_favorite DESC, created_at DESC
LIMIT 5;

-- 2. Pull favorite materials (gold standard examples)
SELECT * FROM favorite_materials;

-- 3. Pull materials from applications that got interviews/offers
SELECT m.type, m.content_md, m.quality_notes, a.company, a.role_title
FROM materials m JOIN applications a ON a.id = m.application_id
WHERE a.status IN ('interviewing', 'offer')
ORDER BY a.updated_at DESC LIMIT 3;
```

### Prioritization Rules
1. **Favorites first** - materials marked `is_favorite = TRUE` are Habib's gold standard. Match their tone, structure, and density.
2. **Winners second** - materials from applications with status = 'interviewing' or 'offer' clearly worked.
3. **Recency third** - recent applications reflect current skills and preferences.
4. **Read `quality_notes`** on favorite materials for specific guidance ("strong opening", "good keyword match").

### Generation With Context
- Include 1-3 favorite/successful past resumes in your context as few-shot examples
- Vary language enough to avoid duplicate phrasing across applications
- Check `notes.md` in similar `applications/` folders for lessons learned
- Role-specific certs: Security+ for SOC, PC 832 for armed security, A+ for helpdesk/IT
- If the JD mentions tools/platforms Habib knows, call them out explicitly

## Favorites System

### Marking Favorites
When Habib says "this one turned out great" or "star this resume" or "favorite this":
- Set `is_favorite = TRUE` on the relevant material(s)
- Set `is_favorite = TRUE` on the application if overall quality was high
- Ask for `quality_notes` - what made it good? ("strong opening", "nailed the keywords")
- These favorites become the RAG gold standard for all future tailoring

### Tracking Outcomes
When Habib says "I got an interview" or "they responded" or "got rejected":
- Update application `status`, `response_received`, `response_date`
- For interviews: set `interview_date`, `interview_type`
- For offers: set `offer_amount`, `offer_date`
- Ask: "What do you think worked? Any lessons for next time?"
- Store the answer in application `notes`

## Supabase Connection
- **Credentials live in `supabase/connection.local.md` (gitignored - never commit them).** Read that file for the project URL and publishable key.
- No Supabase MCP server is configured yet. Until one is added, log via the PostgREST REST API with curl using the URL/key from the local connection file:
  `curl -X POST "<PROJECT_URL>/rest/v1/applications" -H "apikey: <PUBLISHABLE_KEY>" -H "Authorization: Bearer <PUBLISHABLE_KEY>" -H "Content-Type: application/json" -H "Prefer: return=minimal" -d '{...row...}'`
  (Requires the `applications` table RLS to permit anon inserts; if it doesn't, the local `_run_log.md` + memory remain the source of truth.)
- Tables: `applications`, `materials`
- Views: `pipeline_summary`, `overdue_followups`, `monthly_analytics`, `platform_analytics`, `favorite_materials`, `application_details`
- See `supabase/migration.sql` + `supabase/migration_v2_favorites_analytics.sql`

## External ATS Application Flow (browser automation)

When applying to a job that shows "Apply on company website" in LinkedIn:

1. **Wait 3s for the LinkedIn right panel to render** after clicking a job card - the React app is slow. Use `computer:wait(3)` then `computer:screenshot` to confirm.
2. **Click "Apply to [Role] on company website"** via `find` - this opens a NEW browser tab on the ATS. Get the new tabId via `tabs_context_mcp`.
3. **Identify the ATS domain** from the new tab URL:
   - `job-boards.greenhouse.io` / `boards.greenhouse.io` → Greenhouse (no account, fill & submit)
   - `jobs.lever.co` → Lever (no account, fill & submit)
   - `jobs.ashbyhq.com` → Ashby (no account, fill & submit)
   - `apply.workable.com` → Workable (no account, fill & submit)
   - `workforcenow.adp.com` / `*.myworkdayjobs.com` / `icims.com` → **HARD STOP** (account required, skip)
4. **Fill fields** via `find` + `form_input` using canonical data from `jobhunt-autopilot` skill §1.
5. **Resume upload**: inject `C:\Users\habib\Desktop\jobhunter\job-hunter\master\resume.pdf` via JS `DataTransfer` trick (see `uploading-files-via-browser-automation` skill). Confirm filename appears; `input.files.length=0` after injection is EXPECTED.
6. **Submit** and confirm the success/confirmation page.
7. **Log** to `applications/_run_log.md` - external ATS apps do NOT count against the 25/day LinkedIn cap.

**Permission note**: `mcp__claude-in-chrome__*` must be in `~/.claude/settings.local.json` `permissions.allow` for all chrome tools to work on external domains without per-domain prompts.

## PDF Generation
- Use `scripts/generate_pdf.py` (weasyprint-based)
- Produces clean, ATS-parseable single-column PDFs
- Test with: `python scripts/generate_pdf.py applications/{folder}/resume.md`

## Context Retrieval
When Habib asks "what did I send to {company}?" or "show me my last 5 resumes":
- Check local `applications/` folders first (faster)
- Cross-reference with Supabase for metadata (dates, status)
- The markdown source in `materials.content_md` is the queryable version
- Use full-text search: `WHERE content_search @@ plainto_tsquery('english', 'search terms')`

## Dashboard
A live analytics dashboard is available at `dashboard/index.html` (also rendered as React artifact).
Configure with your Supabase URL + anon key. Shows:
- Pipeline stats (applied, response rate, interview rate)
- Applications table with JD links, resume/CL status, favorites
- Monthly trends and platform effectiveness
- Overdue follow-up alerts
