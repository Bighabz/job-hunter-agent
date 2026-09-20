#!/usr/bin/env bash
# JobHunter daily scan - 09:00 systemd timer (Linux port of run_daily_scan.cmd).
# Headless: python only, no Claude, no browser, zero tokens. Each step logs
# failures and never aborts the chain (mirrors the .cmd exactly).
SCRIPTS=/opt/job-hunter/scripts
APPS=/opt/job-hunter/applications
ERRLOG="$APPS/_scan_errors.log"
ts() { date "+[%a %m/%d/%Y %H:%M:%S]"; }
echo "$(ts) ===== daily scan start (vps) =====" >> "$ERRLOG"
step() {
  local name="$1"; shift
  python3 "$SCRIPTS/$name" "$@" >/dev/null 2>>"$ERRLOG" || echo "$(ts) $name FAILED" >> "$ERRLOG"
}
step scan_portals.py
step scan_linkedin_guest.py
# Retired 2026-09-12: deleted Supabase project. Local ledger is authoritative.
step make_daily_brief.py
echo "$(ts) ===== daily scan end =====" >> "$ERRLOG"
exit 0
