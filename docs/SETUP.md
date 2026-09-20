# Set up your application assistant

Start with the [job scanner](../README.md#get-started-find-jobs-first). Once it returns useful roles, add your private information and browser connection. Run the commands below from the repository root with your Python environment activated.

## 1. Create your private profile

Copy the templates. This command only creates files that do not already exist:

```bash
python -c "from pathlib import Path; import shutil; pairs=[('master/profile.template.md','master/profile.md'),('master/resume.template.md','master/resume.md'),('scripts/external_policy.example.json','scripts/external_policy.json')]; [shutil.copyfile(a,b) for a,b in pairs if not Path(b).exists()]"
```

Fill in `master/profile.md` with your experience, certifications, contact information, work authorization, and truthful answers to common screening questions. Update `master/resume.md` with your resume text. Put the PDF you want uploaded at `master/resume.pdf`.

These files are ignored by Git. To use a PDF elsewhere, set `HJ_RESUME` to its full path before launching the assistant. The browser helper uses `master/resume.pdf` by default.

You can also ask Claude to help you complete the profile:

> Read the profile template and interview me about my experience and job preferences. Save my confirmed answers in master/profile.md. Ask about anything missing, and let me review the result before using it in an application.

## 2. Choose limits and preferences

Edit your local `scripts/external_policy.json`. Set your timezone, availability, commute preferences, and confirmed personal answers. The example starts with a maximum of five applications per day and one per batch. These are limits, not goals.

The job list and search filters live in `scripts/portals.yml`. Search settings and submission checks serve different purposes: a role appearing in the results does not mean it has passed a full application review.

The current submission checks use California eligibility and weekday availability. Adapt `validate_review` in `scripts/external_guard.py` and the runner instructions if those assumptions do not fit you; changing a postal code alone does not change them.

Check that local tracking is ready:

```bash
python scripts/external_guard.py status
```

It creates the local application database if needed and prints the current counts. It does not open a browser or submit anything.

## 3. Connect Claude Code and Chrome

Install and sign in to [Claude Code](https://code.claude.com/docs/en/quickstart), then follow its [Chrome connection guide](https://code.claude.com/docs/en/chrome). The integration requires a supported Anthropic plan, browser extension, and interactive account sign-in. On Windows, use native PowerShell for this connection; the Chrome integration does not support WSL.

Open Chrome, return to this repository in your terminal, and run:

```bash
claude --chrome
```

Use `/chrome` inside Claude Code to check the connection and site permissions. It reads the repository's `CLAUDE.md` for operating instructions.

## 4. Review one role together

Start with a request such as:

> Read my private profile and the latest scan results. Show me three roles that fit, explain any gaps, and let me choose one. For that role, prepare the application and show me the resume and answers before submitting. Ask me about facts that are missing.

Keep the browser visible. Check the actual answers, uploaded resume, employer, location, and schedule. After an approved submission, verify the employer's confirmation and save the result. An interrupted or ambiguous attempt should be reviewed before trying again.

The separate Playwright helper needs its own browser setup. It starts a dedicated Chrome profile, so it does not automatically inherit Claude in Chrome's signed-in tabs. Install its Python dependency if you plan to use it:

```bash
python -m pip install playwright
```

Google Chrome must also be installed. The helper accepts a private JSON file containing the target form's URL, field mappings, and verified answers. These are specific to a job and should stay under `applications/`; there is no universal form configuration.

```bash
python scratchpad/gh_apply.py applications/your-application.json
```

Without `--submit`, this fills and inspects the configured form. Adding `--submit` attempts a real application and requires the helper's review fields and checks. Only use it after reviewing that application.

## 5. Find your records

| File under `applications/` | What you will find |
| --- | --- |
| `_scan_results_latest.md` | Latest job search results |
| `_daily_brief.md` | A shorter shortlist to review |
| `_run_log.md` | Application notes maintained by the assistant |
| `_external_applications.sqlite3` | Pending, confirmed, and unresolved application attempts |
| `_interview_qa.md` | Readable questions and answers |
| `_interview_qa.sqlite3` | Question and answer history, including revisions |

Run `python scripts/interview_qa.py status` to see the journal count, or `python scripts/interview_qa.py export` to rebuild its readable copy. See the [recording guide](../scripts/INTERVIEW-QA.md) for manual entries.

## Optional features

**Email verification:** the Greenhouse code collector requires a separately configured Gmail connection and explicit authorization to read application codes. Follow the [deployment guide](../deploy/README.md#email-verification). Without it, handle the verification step yourself. Installing the browser extension does not configure the collector.

**PDF generation:** `scripts/generate_pdf.py` converts Markdown into a PDF using Markdown and WeasyPrint. Install those packages in your virtual environment and follow [WeasyPrint's platform setup](https://doc.courtbouillon.org/weasyprint/latest/first_steps.html). Review the resulting PDF before using it. `scripts/render_pdf.py` is an alternative for an existing HTML document and uses Playwright/Chromium.

**Dashboard:** `dashboard/JobHunterDashboard.jsx` is a React component for a separate frontend. The `supabase/` folder contains its older database setup. It takes additional integration work and is not needed for the current local tracking workflow.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `No module named yaml` | Activate `.venv`, then install `requirements.txt`. |
| Policy file missing | Complete step 1 and edit `scripts/external_policy.json`. |
| No useful jobs | Check the board list, title filters, locations, and minimum grade. Try one board first. |
| Browser connection unavailable | Check `/chrome`, account sign-in, extension status, and site permissions. |
| Playwright cannot find Chrome | Install Google Chrome; this helper uses the `chrome` browser channel. |
| The run stops at a question | Supply the missing fact and review the answer; do not guess. |
| An application is still pending | Inspect the employer page and saved evidence before retrying. |
