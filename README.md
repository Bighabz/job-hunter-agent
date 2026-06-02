# Job Hunter Agent

An autonomous job-application system built on [Claude Code](https://claude.com/claude-code). It searches job boards, triages listings against skip rules, tailors materials, fills out applications in a real Chrome browser, and logs everything. It has submitted 99+ real applications (LinkedIn Easy Apply + external ATS portals like Greenhouse, Lever, Ashby, and Workable).

**This is a real, personal system, not a demo.** The personal data that powers it (resume, profile, application history) is gitignored. What's public here is the agent architecture, the runbooks, and the hard-won operational knowledge about what actually works.

---

## How it works

```
job-hunter/
├── CLAUDE.md                    ← the agent's standing instructions (read every session)
├── master/
│   ├── profile.template.md      ← copy to profile.md (gitignored) and fill in
│   ├── resume.template.md       ← copy to resume.md (gitignored) and fill in
│   └── cover_letter_template.md ← base cover letter with merge fields
├── targets/                     ← keyword banks + tailoring notes per role type
├── applications/                ← (gitignored) one folder per application + _run_log.md
├── supabase/                    ← database schema for pipeline tracking
│   └── connection.local.md      ← (gitignored) your Supabase URL + key
├── scripts/                     ← markdown → PDF resume rendering
└── dashboard/                   ← React analytics dashboard (reads Supabase)
```

The agent runs inside Claude Code with two key extensions:

1. **Claude in Chrome** (browser automation MCP): drives a real Chrome browser to search LinkedIn, open applications, fill forms, and submit.
2. **Supabase** (pipeline database): every application is logged with status, materials, and follow-up dates. A local `applications/_run_log.md` is the always-works fallback.

On top of that, reusable **Claude Code skills** encode the runbooks (search → triage → apply → verify → log), so any session, even with a fresh context window, executes the same way.

---

## Setup

### 1. Claude Code

```bash
npm install -g @anthropic-ai/claude-code
cd job-hunter
claude
```

### 2. Claude in Chrome (browser automation MCP)

This is the connector that lets the agent drive your real browser (your logins, your sessions, no headless detection problems).

1. Install the **Claude in Chrome** extension from the Chrome Web Store and sign in with your Anthropic account.
2. In the extension settings, set site access to **"On all sites"** (you will still get per-domain permission popups, see [Permissions](#permissions) below).
3. In Claude Code, the `claude-in-chrome` MCP server is detected automatically when the extension is running. Verify with:
   ```
   > /mcp
   ```
   You should see `claude-in-chrome` listed with tools like `tabs_context_mcp`, `navigate`, `find`, `form_input`, `computer`.

**Important facts learned the hard way:**
- Browser tools only work on tabs inside the MCP tab group that the extension creates. Always start a run by calling `tabs_context_mcp`.
- A subagent (background task) **cannot click Chrome permission popups**. Only you can. Front-load all domain approvals before letting the agent run solo.
- Keep the Chrome window **maximized**. LinkedIn switches to a different (flakier) tablet layout below ~1200px width.

### 3. Supabase (pipeline tracking)

1. Create a free project at [supabase.com](https://supabase.com).
2. In the SQL editor, run `supabase/migration.sql`, then `supabase/migration_v2_favorites_analytics.sql`.
3. Copy your project URL and publishable (anon) key into `supabase/connection.local.md`:
   ```markdown
   # Supabase Connection (LOCAL ONLY - gitignored, never commit)
   - Project URL: https://YOUR-PROJECT.supabase.co
   - Anon (publishable) Key: sb_publishable_XXXX
   ```
   This file is **gitignored**. Never put credentials in `CLAUDE.md` or anything tracked by git.
4. Optional: add a Supabase MCP server for direct SQL access:
   ```bash
   claude mcp add supabase -- npx -y @supabase/mcp-server-supabase --access-token YOUR_PAT
   ```
   Without it, the agent falls back to the PostgREST REST API via curl, which works fine.

### 4. Your personal data: start with a conversation (all gitignored)

Don't fill in the templates by hand. **The best way to bootstrap the system is a conversation with Claude.** Open Claude Code in this folder and say something like:

```
> I want you to be my job application agent. Interview me so you can build my
> profile and resume. I'm targeting [SOC analyst / cloud engineer / data
> engineer / ...] roles, remote, around $XX,000.
```

Claude will interview you: education, every job you've held (with real dates and duties), certifications, projects, tools you've actually used and for how long, salary floor, location constraints, clearance status, and what kinds of roles you do NOT want. From that conversation it writes:

- `master/profile.md`: the single source of truth about you (gitignored)
- `master/resume.md` + `resume.pdf`: your master resume (gitignored)
- The skip rules and screening answers it will use on every application

**Be brutally honest in this conversation.** The profile includes a truthful years-of-experience table; pre-deciding honest answers for every tool you get screened on is what lets the agent apply at volume without ever inflating. Lying on screeners is a hard no; it also gets you auto-rejected when they check.

The more context you give here (what you want, what you hate, which past job titles undersell what you actually did), the better every downstream application gets. This conversation is the highest-leverage 20 minutes in the whole setup.

### 4b. One resume per job (tailoring)

The master resume is the baseline, not what gets submitted everywhere. For roles worth the effort, ask:

```
> Tailor a resume and cover letter for this JD: [paste URL or text]
```

The agent reads the JD, picks the matching archetype from `targets/`, reorders and rewrites bullets to front-load relevant experience, matches keywords naturally (no stuffing), renders a fresh PDF, and saves everything to `applications/{Company}_{Role}_{date}/`. Every tailored resume is kept, so the system learns from past versions (the ones that got interviews become the gold standard for future tailoring).

For high-volume Easy Apply runs, the master resume is used as-is; tailoring is reserved for strong-fit roles where it moves the needle.

### 5. PDF rendering

```bash
pip install markdown weasyprint
```

On Windows, weasyprint needs GTK. If it fails with `cannot load library 'libgobject-2.0-0'`, use an HTML-to-PDF fallback via headless Chrome (see `scripts/render_pdf.py`).

---

## Permissions

This is the part everyone gets wrong, so read it once.

There are **two separate permission layers**:

### Layer 1: Chrome extension per-domain popups
The first time the agent navigates to a new domain (e.g. `job-boards.greenhouse.io`), Chrome shows a permission popup that **only a human can click**. The agent cannot click it. A background agent will silently fail on it.

**The fix: front-load approvals.** At the start of a run, have the agent navigate once to every ATS domain it will need, approve all the popups in one sitting, then let it run unattended:

- `www.linkedin.com`
- `job-boards.greenhouse.io` (and `job-boards.eu.greenhouse.io`, a separate domain!)
- `jobs.lever.co`
- `jobs.ashbyhq.com`
- `apply.workable.com`
- `jobgether.com`

### Layer 2: Claude Code tool allowlist
In `.claude/settings.local.json` (gitignored), allowlist the browser tools and the ATS domains so the agent isn't interrupted by Claude Code's own permission prompts mid-run:

```json
{
  "permissions": {
    "allow": [
      "mcp__claude-in-chrome__*",
      "WebFetch(domain:api.lever.co)",
      "WebFetch(domain:boards-api.greenhouse.io)"
    ]
  }
}
```

Per-domain popup denials are **cached by the extension across sessions**. If a domain got denied once, it stays blocked until you change it in the extension's site settings and restart the browser.

---

## The daily run

```
> run the job autopilot
```

The loop:

1. **Preflight** (5 tool calls max): confirm LinkedIn is logged in, confirm one external ATS page loads, confirm resume attaches. If any check fails, stop and fix it with the human. Never start a volume run on a broken precondition.
2. **Search**: rotate keywords on LinkedIn (`security engineer`, `cloud engineer`, `data engineer`, `SOC analyst`, `systems administrator`, `automation engineer`, ...), sorted by most recent, filtered to remote + entry/associate level.
3. **Triage** each listing against skip rules (below) by reading the job description.
4. **Apply**: LinkedIn Easy Apply flows are submitted end-to-end by the agent. External ATS flows use the prefill workflow (below).
5. **Verify**: an application only counts when a visible confirmation appears ("Your application was sent", a `/confirmation` URL, etc.). Never count from the review screen.
6. **Log**: every application and every skip goes to `applications/_run_log.md` (and Supabase) with the reason.

### LinkedIn: the 25/day cap

**LinkedIn Easy Apply has a soft daily cap of ~25 applications per day.** Going past it risks account restrictions. The agent treats 25 LinkedIn Easy Apply submissions per calendar day as a hard budget.

Two things that do NOT count toward the cap:
- Applications on external ATS sites (Greenhouse/Lever/Ashby/Workable), even when you found the job on LinkedIn
- Searching and triaging

So the strategy is: spend the 25 LinkedIn slots on Easy Apply jobs, and do unlimited external ATS applications on top.

Also worth knowing:
- LinkedIn **throttles hard** after ~25 page loads in quick succession: job pages start serving empty loading skeletons. When that happens, stop and come back in 15-30 minutes. Do not grind against it.
- The Easy Apply pool for a given keyword set gets exhausted fast. Rotate keywords daily and rely on `sortBy=DD` (most recent) to surface fresh postings.

### External ATS: the prefill workflow (the method that actually works)

Modern ATS boards (especially new Greenhouse UIs) run **invisible reCAPTCHA/hCaptcha that silently blocks automated submit clicks**. The form fills fine, but the submit click from automation goes nowhere, or worse, hangs forever.

After much trial and error, the best method is a **human-in-the-loop batch**:

1. The agent finds 5-10 external ATS jobs that pass triage.
2. The agent opens each in its own tab and **prefills everything**: contact info, links, screening questions, EEO disclosures, salary, location typeaheads.
3. The agent hands you the batch: "These N tabs are filled and valid."
4. **You go tab by tab: attach the resume (one click in the OS file picker) and click Submit.** Takes about 30 seconds per tab.
5. The agent verifies each confirmation page and logs everything.

This splits the work optimally: the agent does the 10 minutes of form-filling per application, the human does the 2 clicks that anti-bot systems require to come from a real person.

Per-ATS notes:

| ATS | Behavior |
|---|---|
| Greenhouse (`job-boards.greenhouse.io`) | Older boards accept automated submit. Newer (remix UI) boards silently block it via reCAPTCHA v3: prefill + human click. React-select dropdowns need special handling (the agent knows). |
| Lever (`jobs.lever.co`) | Sometimes accepts automated submit (invisible hCaptcha stays passive when the form is clean). Try once, hand off if it fails. |
| Workable / Ashby | Generally automatable, location typeaheads need care. |
| JazzHR (`applytojob.com`) | Has a visible reCAPTCHA "Human Check": always needs the human for the final step. |
| Workday / iCIMS / ADP | **Require account creation: skip these entirely.** Not worth it at volume. |

### Hard stops (the agent never works around these)

1. **Account creation / passwords**: skip the job.
2. **CAPTCHA**: stop and tell the human, never attempt to solve or bypass.
3. **SSN, banking info, or any fee**: skip.
4. **The LinkedIn 25/day cap**: switch to external-only or stop.
5. **Never fabricate answers** to get past screening questions. Truthful years of experience, always.

### Skip rules (triage)

Skip if the listing shows any of: sales/BD roles, required security clearance, AI-training/data-labeling gigs (Turing, DataAnnotation, etc.), pay clearly below the floor, mandatory onsite outside your area, state-residency locks that exclude you, senior specialist gates (5+ years of a specific tool you lack), required certs/degrees you don't have, or already applied (dedupe by company + role).

Stretch roles (2-3 year asks when you have 1) are applied to anyway. Volume beats perfection; rejection is free.

---

## Operational lessons (the stuff that cost tokens to learn)

- **Time-cap every application.** ~10-15 tool calls max for an external ATS app, ~5 for Easy Apply. If a form fights you after 2-3 distinct approaches, fill what you can, leave the tab for the human, move on.
- **Two-strike rule per blocker.** The same error twice on a source means abandon that source for the session. Never send a fresh agent into a blocker a previous run already hit.
- **Verify before claiming.** A submission without a visible confirmation page did not happen.
- **Checkpoint constantly.** Log every application immediately. Sessions die (context limits, throttling, disconnects); the run log and a resume-state memory file are what let the next session continue seamlessly.
- **LinkedIn JS scraping is intermittently blocked.** The agent falls back between JS extraction, accessibility-tree reads, and screenshots.
- **Job board APIs are cheaper than browsers for triage.** Greenhouse (`boards-api.greenhouse.io/v1/boards/<company>/jobs`) and Lever (`api.lever.co/v0/postings/<company>`) are public JSON APIs. Triaging year-gates/clearance/salary through them costs a fraction of loading pages.
- **Keyword dilution is real.** Generic keywords ("cybersecurity") return mostly sales/HR/spam. Specific role nouns ("SOC analyst", "data engineer", "systems administrator") have much better hit rates.

---

## Dashboard

`dashboard/JobHunterDashboard.jsx` is a React dashboard that reads your Supabase project and shows pipeline stats, response rates, monthly trends, and overdue follow-ups. Point it at your Supabase URL + publishable key.

---

## Disclaimer

This automates *your own* job applications with *your own* truthful information, the same thing you'd do by hand, just faster. It refuses to create accounts, solve CAPTCHAs, fabricate qualifications, or do anything else that crosses from automation into misrepresentation. Use responsibly and respect each site's terms of service.
