# Where the current source comes from

The public source was refreshed from the running Job Hunter server on September 20, 2026, including source files that had not yet been committed on that server.

It includes the job scanners, application helper, duplicate checks, batch runner, email verification collector, question-and-answer journal, parser fixtures, and deployment schedules. The current workflow uses local tracking; LinkedIn is disabled and the older Supabase integration is optional.

## Changes made for this public copy

- Personal profiles, resumes, screening answers, application records, browser sessions, email data, credentials, and logs are excluded.
- Machine-specific paths are replaced with configurable paths or deployment examples.
- Services use an example dedicated user. Host-specific ownership commands and unrelated host service dependencies are omitted.
- The example policy starts with five applications per day and one per batch. The live server's private policy is not published.
- Runner prompts contain reusable instructions instead of the owner's application history and personal requirements.
- Documentation explains the current workflow. Scanner tests use the current location tag and explicit limits.
- The Workable discovery helper parses company data without executing Python expressions. A regression test checks malicious input.

The [manifest](vps-source-manifest.json) records source and public file hashes. Files marked `adapted` include privacy, portability, documentation, or example-configuration changes. These public-copy changes do not alter the running server.

## Check the copy

Run `python -m unittest discover -s scripts -p "test_*.py"` from the repository root. Install `requirements.txt` first; the browser fixtures additionally need Playwright and Chrome.

The tests use synthetic records, local HTML, and stubbed responses. They do not submit applications or read a mailbox. Deployment instructions are in [deploy/README.md](../deploy/README.md).
