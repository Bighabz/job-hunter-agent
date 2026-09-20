# Job Hunter Agent

Job hunting involves a lot of repeated work: finding openings, checking requirements, answering the same questions, and remembering where you applied. I built Job Hunter to help with that process and keep a clear record of each application.

It combines a job scanner with a Claude Code assistant and browser tools. The scanner builds a shortlist. The assistant can help review roles, prepare materials, and fill employer forms using information you've provided. You decide which jobs to pursue and how much the assistant is allowed to do.

This is a working personal project with source from its current server deployment. You can run job discovery on its own or set up the application workflow. Browser access, your resume, and your job preferences need to be configured on your own machine.

## What it can do

| Feature | How it helps |
| --- | --- |
| **Find openings** | Searches configured employer boards on Greenhouse, Lever, Ashby, Workable, and SmartRecruiters. You can use this part without an AI account or browser session. |
| **Build a useful shortlist** | Filters by job title, location, remote/on-site work, experience, and other preferences. Grades help decide what to read first; you still review the actual job description. |
| **Prepare application materials** | Uses your private profile, resume, and templates to help write relevant answers and cover letters. The application runner uses your approved resume. Resume changes need a separate review. |
| **Help fill applications** | Uses browser automation for supported employer forms, including text fields, dropdowns, and resume uploads. Different sites may need different field mappings. |
| **Avoid duplicate applications** | Keeps a local record of jobs that are pending, submitted, or unresolved. That record survives restarts, so a failed run does not automatically mean applying again. |
| **Check what actually happened** | Saves confirmation evidence and keeps uncertain attempts separate from confirmed submissions. |
| **Handle an email verification step** | With a separately connected Gmail account and your authorization, the Greenhouse workflow can find the matching recent code and resume the waiting form. |
| **Remember questions and answers** | Saves the wording of application questions, the answers actually entered, later changes, and the final result. Other interview exchanges can be logged when their text is available. |
| **Produce a daily brief** | Saves a readable summary of new roles and a shortlist to review. |
| **Run on a schedule** | Includes Linux service templates for discovery and application batches, with limits on how many applications a run can attempt. |

Optional extras include PDF helpers, a React dashboard component, and older Supabase tracking scripts. The current workflow uses local files and SQLite, a small database stored on disk. LinkedIn discovery and applications are disabled in the included configuration.

## A typical session

1. Run a scan and read the shortlist.
2. Ask the assistant to compare a few roles with your experience and preferences.
3. Review the resume, proposed answers, location, schedule, and any requirements it is unsure about.
4. Let it fill an application within the scope you've approved. Supply missing answers yourself.
5. Check the result. A confirmed application gets a saved receipt or screenshot; an uncertain result stays marked for review.

The question-and-answer journal gives you a record to revisit when preparing for an interview.

## Get started: find jobs first

You need **Git and Python 3.11 or later**. These commands start in a terminal:

```bash
git clone https://github.com/Bighabz/job-hunter-agent.git
cd job-hunter-agent
python -m venv .venv
```

Activate the environment:

| Terminal | Command |
| --- | --- |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

Then install the scanner's dependencies:

```bash
python -m pip install -r requirements.txt
```

Open [`scripts/portals.yml`](scripts/portals.yml) and choose the companies, job titles, and locations you want. The included settings are a starting point for US-based searches; update them for your own situation.

Run a scan, then make a daily brief:

```bash
python scripts/scan_portals.py --min-grade B
python scripts/make_daily_brief.py
```

Read `applications/_scan_results_latest.md` for the results and `applications/_daily_brief.md` for the summary. These commands fetch public job listings and save them locally. They do not submit applications.

For more search options, see the [scanner guide](scripts/README_scan.md).

## Set up the application assistant

The [step-by-step setup guide](docs/SETUP.md) walks through:

1. Creating your private profile and choosing your resume.
2. Setting job preferences and application limits.
3. Connecting Claude Code to your browser.
4. Reviewing one application before enabling a larger workflow.
5. Adding optional email verification, PDF generation, or a dashboard.

For a server installation, use the [deployment guide](deploy/README.md). The [source notes](docs/VPS-SYNC.md) explain what came from the running server and which settings were made portable for this public copy.

## Things to know

Employer forms change. Login prompts, CAPTCHAs, unusual fields, and missing personal answers can require your attention. The current fit checks include assumptions about California eligibility and weekday work; review those before using the application runner elsewhere.

Some safeguards still rely on the supervising assistant or a person. The answer checker does not validate every field against your profile, and an evidence file by itself does not prove an application succeeded. Review the filled answers and the actual confirmation. The tool cannot promise interviews or a hiring outcome.

Your resume, contact details, answers, application history, browser sessions, and email codes belong in the ignored local files. The public repository contains source code and templates.

## For developers and employers

The main engineering work is in keeping a browser-driven process understandable when a site changes or a run stops midway:

- [`scan_portals.py`](scripts/scan_portals.py) collects and ranks openings.
- [`external_guard.py`](scripts/external_guard.py) records attempts, checks duplicates, and enforces configured limits.
- [`gh_apply.py`](scratchpad/gh_apply.py) handles supported browser forms and captures results.
- [`interview_qa.py`](scripts/interview_qa.py) preserves questions, answer revisions, and outcomes.
- [`external_batch.py`](scripts/external_batch.py) coordinates a timed Linux application run.

Run the tests from the repository root:

```bash
python -m unittest discover -s scripts -p "test_*.py"
```

The tests use sample records and local browser fixtures. Browser checks need Playwright and Chrome; otherwise those checks are skipped. They do not submit real applications or read a mailbox.
