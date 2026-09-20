# Run Job Hunter on a Linux server

These are deployment templates based on the current server workflow. The public copy uses an example installation at `/opt/job-hunter`, owned by a dedicated `jobhunter` user. Adjust those paths and the username for your server.

Complete the [local setup](../docs/SETUP.md) first. A successful manual scan and reviewed application are useful checks before scheduling anything.

## Prepare the installation

1. Clone the repository into your chosen directory and give the service user access to it.
2. Create `.venv` there and install `requirements.txt`. Install Playwright and Google Chrome if using the form helper.
3. Create the private profile, approved resume, and `scripts/external_policy.json` as described in the setup guide.
4. Install and sign in to Claude Code as the same service user. Confirm its Chrome connection and permitted employer sites.
5. Provide a graphical browser session. The batch runner expects `DISPLAY=:99`; display and Chrome session management are host setup, not included services.
6. Copy `deploy/job-autopilot/prompt-vps.example.md` to the ignored `prompt-vps.md` beside it. Adapt it to the owner's requirements and authorized scope.

The wrapper finds the repository from its own location. `JOBHUNT_ROOT`, `JOBHUNT_RUNNER`, and `JOBHUNT_PYTHON` can override the project, runner, and Python paths. `HJ_RESUME` selects a different private PDF, and `JOBHUNT_BROWSER_PROFILE` selects the browser helper's private profile directory.

## Schedule discovery

Review `systemd/jobhunter-scan.service` and its timer. The template runs discovery at 09:00 in the server's timezone. After adjusting the paths and user, install just this pair:

```bash
sudo cp deploy/systemd/jobhunter-scan.service deploy/systemd/jobhunter-scan.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobhunter-scan.timer
```

This schedules job discovery and the daily brief. It does not submit applications.

## Schedule application batches

The application service starts a real Claude/browser run. Configure and review the private prompt, submission limits, browser access, and candidate information before enabling it.

`systemd/job-autopilot.timer` uses the source deployment's schedule: hourly at minute 23, from 08:23 through 22:23 in `America/Los_Angeles`. Change it to suit your authorized workflow. The runner prevents overlapping batches, checks daily and batch limits, and stops a Claude run after 45 minutes. The service has a one-hour timeout.

Install the reviewed `job-autopilot.service` and `.timer` pair the same way as the discovery pair. Do not enable every supplied unit without configuring its dependencies.

## Email verification

The Greenhouse collector requires a Gmail connection configured in Claude Code for the service user, plus the owner's explicit permission to read and use application codes.

The `jobhunt-email-verification.path` unit watches for a waiting application request. Its service searches for a recent code matching that employer, then writes a private handoff for the same browser form. It does not poll the inbox continuously or submit a different application.

Review the [email verification instructions](email-verification/SKILL.md), install the matching `.path` and `.service` files, and enable only the `.path` unit after configuring Gmail and authorization. Keep its application directory and user consistent with the application runner.

## Check a scheduled run

```bash
systemctl list-timers jobhunter-scan.timer job-autopilot.timer
systemctl status jobhunter-scan.service
journalctl -u job-autopilot.service --since today
```

Results remain in `applications/`; runner logs are in `deploy/job-autopilot/logs/`. Treat both as private. The older `run.ps1` wrapper is included for a Windows Task Scheduler installation and expects its own ignored `prompt.md`.
