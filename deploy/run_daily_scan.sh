#!/usr/bin/env bash
# Collect job leads and a daily brief. This does not submit applications.
set -u
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${JOBHUNT_ROOT:-$(cd -- "$DEPLOY_DIR/.." && pwd)}"
SCRIPTS="$PROJECT_DIR/scripts"
APPS="$PROJECT_DIR/applications"
mkdir -p "$APPS"
ERRLOG="$APPS/_scan_errors.log"
ts() { date '+[%Y-%m-%d %H:%M:%S]'; }
step() {
  local name="$1"; shift
  "${JOBHUNT_PYTHON:-python3}" "$SCRIPTS/$name" "$@" >/dev/null 2>>"$ERRLOG" || echo "$(ts) $name failed" >> "$ERRLOG"
}
echo "$(ts) Daily scan started" >> "$ERRLOG"
step scan_portals.py
step scan_linkedin_guest.py
step make_daily_brief.py
echo "$(ts) Daily scan finished" >> "$ERRLOG"
