#!/usr/bin/env bash
set -u
cd /opt/job-hunter/deploy/job-autopilot
python3 /opt/job-hunter/scripts/external_batch.py
code=$?
chown -R clawd:clawd /home/jobhunter/jobhunter /opt/job-hunter/deploy/job-autopilot 2>/dev/null
chown clawd:clawd /home/jobhunter/ClaudeVault/status/projects/jobhunt.md 2>/dev/null
exit "$code"
