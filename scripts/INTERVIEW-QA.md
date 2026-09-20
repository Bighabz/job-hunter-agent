# Required interview and screening Q&A recording

The application workflow records each question the assistant receives and the exact
answer it provides. This includes job application
screening questions, recruiter screening exchanges, written interviews, assessments,
and any interview conversation the runner actually handles. Record all employers
and all outcomes, including skipped, unanswered and unsuccessful applications.

The durable journal is:
`/opt/job-hunter/applications/_interview_qa.md`
The authoritative append-only events are in `_interview_qa.sqlite3` alongside it.
Never overwrite or delete past events. No invented transcripts or retroactive guesses.

## Automatic form capture

`scratchpad/gh_apply.py` captures the full visible question/label and actual field
value before filling, after filling, immediately before each submit, and the final
confirmation status. It reads actual selected option labels, not just requested
config values. This applies to every ATS handled by the helper, including
Greenhouse, Lever, Ashby and Workable. If automatic capture misses a custom control,
unlabeled question, previous page, or chat turn, add it with the manual logger below.
Full wording matters: do not truncate or paraphrase questions or answers.

## All other questions/interview exchanges

Immediately after observing a question, log it with `phase: observed` and `answer: null`.
Before advancing a form page or leaving an exchange, save the exact answer. Distinguish
`draft`/`filled` from `provided` (actually sent/spoken), `submitting` (attempt imminent)
and `confirmed` (receipt verified). A draft must never be represented as sent.
Append changes and outcomes under the same session_id so the original is preserved.
Record company, role, job/source URL or thread identifier, stage, and batch/session.
Use `stage: interview` for interviews and `application_screening` for application forms.
Use `phase: skipped` and an explanatory note for unanswered questions you cannot answer.
Record spoken exchanges only from an available transcript or actual text you handled;
this does not enable audio recording or authorize new interviews/messages.

Write a JSON file with this structure (substitute real values, no sample events in
the production journal), then run:

```sh
python3 /opt/job-hunter/scripts/interview_qa.py record --input /path/to/qa.json
```

```json
{
  "session_id": "stable-job-or-interview-id-plus-date",
  "company": "actual employer",
  "title": "actual role",
  "url": "actual job URL or thread identifier",
  "stage": "interview",
  "phase": "draft",
  "source": "actual interview transcript or browser tool readback",
  "records": [
    {"field": "question-1", "question": "Full exact question", "answer": "Full exact answer"}
  ],
  "note": "Optional context; explicitly state any uncertainty"
}
```

Use `phase: outcome`, an empty `records` array and a factual `note` to log the final
result without inventing another question. If a write fails, preserve the JSON and
fix the logging before providing another answer or submitting. Do not silently skip
logging. Never store passwords, OTP/security codes, CAPTCHA tokens, SSNs or banking
identifiers in this journal. This requirement changes recording, not the existing
rules for truthful answers, job selection, submission or recruiter messaging.

End each batch with the Q&A journal path, new event count and any recording gaps.
`python3 scripts/interview_qa.py status` reports the event count; `export` rebuilds
the readable Markdown from the saved events. No prior history is backfilled.
