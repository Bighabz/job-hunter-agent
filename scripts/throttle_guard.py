#!/usr/bin/env python3
"""EA throttle guard — rate-limit LinkedIn Easy Apply to avoid the anti-bot wall.

LinkedIn's "We limit daily submissions to maintain quality and prevent bots"
wall is a DAILY quota (verified 2026-06-04: ~10 automated EA tripped it and
5 hours of waiting did NOT clear it — it resets overnight). A SEPARATE, softer
render throttle (job panels won't hydrate, screenshots time out, the Easy
Apply button is NOT greyed) clears in ~1-2 h. This guard self-paces the
autopilot and backs off correctly for each, with state that survives across
runs and sessions (so a scheduled re-run won't immediately re-hit the wall).

Usage (run from anywhere; state lives next to _run_log.md):
  python throttle_guard.py check          -> GO:... | WAIT:<sec>:... | STOP:...  (exit 0/2/1)
  python throttle_guard.py record         -> record a CONFIRMED submission (only after success)
  python throttle_guard.py cooldown       -> the WALL was seen (greyed EA button or "limit
                                             daily submissions"/"apply tomorrow" text):
                                             stop EA until tomorrow morning
  python throttle_guard.py cooldown soft  -> render throttle (panels won't hydrate, EA button
                                             NOT greyed): back off 90 min (180 after a recent hit)
  python throttle_guard.py status         -> summary; skills read the daily budget from `caps:`
  python throttle_guard.py reset          -> clear all state (manual override)

Runbook contract:
  - Before opening the Easy Apply modal for a job, run `check`.
      GO    -> proceed.
      WAIT:<sec> -> if sec <= 240, pace (wait then re-check); if larger, stop the
                    LinkedIn-EA channel for now and switch to external portals or end.
      STOP  -> do NOT submit; stop the LinkedIn-EA channel (reason printed).
  - After a CONFIRMED "Your application was sent" page, run `record`.
  - Greyed Easy Apply button or "limit daily submissions" / "apply tomorrow" text
    -> run `cooldown` and stop EA for the day (it will NOT clear today).
  - Panels won't hydrate / screenshots time out but the EA button looks normal
    -> run `cooldown soft`.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta

# --- Tunable safeguards (SINGLE SOURCE for every cap; skills and CLAUDE.md read
# --- them here or via the `caps:` line of `status` — never restate the numbers) --
DAILY_CAP = 9           # LinkedIn's wall verified 2026-06-04: trips at ~10 automated EA/day
HOURLY_CAP = 4          # rolling-60-min anti-burst cap
MIN_GAP_SEC = 120       # base spacing between submissions
GAP_JITTER_SEC = 90     # random 0-90s added per gap (persisted so re-checks agree)
COOLDOWN_SOFT_MIN = 90  # render-throttle back-off; doubles if any hit in the last 7 days
WALL_RESUME_HOUR = 6    # the wall resets at midnight; resume next day at 06:00
TIGHTEN_HITS = 2        # >=2 wall hits in 7 days -> halve caps until 7 clean days
SESSION_CAP = 5         # max EA submissions in one session (run two sessions/day)
# ---------------------------------------------------------------------------------

STATE = os.environ.get("EA_THROTTLE_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "applications", "_ea_throttle_state.json",
)

EMPTY = {
    "submissions": [],
    "cooldown_until": None,
    "cooldown_kind": None,
    "hits": [],
    "next_gap_sec": None,
}


def load():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    for k, v in EMPTY.items():
        s.setdefault(k, [] if isinstance(v, list) else v)
    return s


def save(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def _parse(ts):
    return datetime.fromisoformat(ts)


def _subs(s):
    out = []
    for t in s.get("submissions", []):
        try:
            out.append(_parse(t))
        except ValueError:
            pass
    return out


def _safe_after(ts, cutoff):
    try:
        return _parse(ts) >= cutoff
    except (ValueError, TypeError):
        return False


def _recent_hits(s, days=7, kind=None):
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for h in s.get("hits", []):
        if not isinstance(h, dict) or not _safe_after(h.get("t"), cutoff):
            continue
        if kind is None or h.get("kind") == kind:
            out.append(h)
    return out


def _effective_caps(s):
    """Halve the caps while there are TIGHTEN_HITS+ wall hits in the last 7 days."""
    if len(_recent_hits(s, 7, "wall")) >= TIGHTEN_HITS:
        return max(1, DAILY_CAP // 2), max(1, HOURLY_CAP // 2), True
    return DAILY_CAP, HOURLY_CAP, False


def check(s):
    now = datetime.now()
    daily_cap, hourly_cap, tight = _effective_caps(s)
    tag = " [TIGHTENED: 2+ wall hits in 7d]" if tight else ""

    # 1. Active cooldown (wall or render throttle detected recently)?
    cu = s.get("cooldown_until")
    if cu:
        try:
            cu_dt = _parse(cu)
            if now < cu_dt:
                kind = s.get("cooldown_kind") or "throttle"
                mins = int((cu_dt - now).total_seconds() // 60) + 1
                return "STOP", (
                    f"{kind} cooldown active: {mins} min left "
                    f"(resume EA after {cu_dt.strftime('%a %H:%M')}){tag}"
                )
        except ValueError:
            pass

    subs = _subs(s)
    today = [t for t in subs if t.date() == now.date()]

    # 2. Daily cap (stays under LinkedIn's observed ~10/day tripwire).
    if len(today) >= daily_cap:
        return "STOP", f"daily cap reached ({len(today)}/{daily_cap}); resets at midnight{tag}"

    # 3. Rolling-hour rate cap — the main burst preventer.
    last_hour = [t for t in subs if now - t < timedelta(hours=1)]
    if len(last_hour) >= hourly_cap:
        wait = int((min(last_hour) + timedelta(hours=1) - now).total_seconds())
        return "WAIT", (
            f"{wait}:hourly cap ({len(last_hour)}/{hourly_cap}); "
            f"next slot in ~{wait // 60 + 1}m — switch channel or pause EA{tag}"
        )

    # 4. Jittered minimum spacing. The target persists in state so repeated
    #    checks report a consistent countdown; `record` clears it so the next
    #    submission gets a fresh random gap (breaks the robotic fixed cadence).
    if subs:
        gap_target = s.get("next_gap_sec")
        if not gap_target:
            gap_target = MIN_GAP_SEC + random.randint(0, GAP_JITTER_SEC)
            s["next_gap_sec"] = gap_target
            save(s)
        gap = (now - max(subs)).total_seconds()
        if gap < gap_target:
            return "WAIT", (
                f"{int(gap_target - gap)}:pacing (last submit {int(gap)}s ago, "
                f"gap target {gap_target}s)"
            )

    return "GO", f"today {len(today)}/{daily_cap}, last hour {len(last_hour)}/{hourly_cap}{tag}"


def record(s):
    now = datetime.now()
    daily_cap, _, _ = _effective_caps(s)
    subs = s.get("submissions", [])
    subs.append(now.replace(microsecond=0).isoformat())
    # Prune submissions older than 2 days and hits older than 14 to keep the file small.
    s["submissions"] = [t for t in subs if _safe_after(t, now - timedelta(days=2))]
    s["hits"] = [
        h for h in s.get("hits", [])
        if isinstance(h, dict) and _safe_after(h.get("t"), now - timedelta(days=14))
    ]
    s["next_gap_sec"] = None  # fresh random gap for the next submission
    # A successful submit means we're through any expired cooldown.
    if s.get("cooldown_until"):
        try:
            if now >= _parse(s["cooldown_until"]):
                s["cooldown_until"] = None
                s["cooldown_kind"] = None
        except ValueError:
            s["cooldown_until"] = None
            s["cooldown_kind"] = None
    save(s)
    n_today = len([t for t in _subs(s) if t.date() == now.date()])
    return f"recorded; today {n_today}/{daily_cap}"


def cooldown(s, kind="wall"):
    now = datetime.now()
    s.setdefault("hits", []).append(
        {"t": now.replace(microsecond=0).isoformat(), "kind": kind}
    )
    if kind == "wall":
        # The wall is a daily quota: waiting it out same-day never works
        # (verified 2026-06-04). Resume tomorrow morning.
        until = (now + timedelta(days=1)).replace(
            hour=WALL_RESUME_HOUR, minute=0, second=0, microsecond=0
        )
        why = "the daily-submissions wall resets overnight"
    else:
        mins = COOLDOWN_SOFT_MIN
        if len(_recent_hits(s, 7)) > 1:  # any earlier hit this week besides this one
            mins = COOLDOWN_SOFT_MIN * 2
        until = (now + timedelta(minutes=mins)).replace(microsecond=0)
        why = f"render throttle, backing off {mins} min"
    s["cooldown_until"] = until.isoformat()
    s["cooldown_kind"] = kind
    save(s)
    return f"{kind} cooldown set: no LinkedIn EA until {until.strftime('%a %H:%M')} ({why})"


def status(s):
    now = datetime.now()
    daily_cap, hourly_cap, tight = _effective_caps(s)
    subs = _subs(s)
    today = [t for t in subs if t.date() == now.date()]
    last_hour = [t for t in subs if now - t < timedelta(hours=1)]
    lines = [
        f"caps:       daily {daily_cap}, hourly {hourly_cap} "
        f"(tightened: {'yes' if tight else 'no'}; session cap {SESSION_CAP})",
        f"today:      {len(today)}/{daily_cap}",
        f"last hour:  {len(last_hour)}/{hourly_cap}",
        f"last submit:{(' ' + max(subs).strftime('%H:%M:%S')) if subs else ' none'}",
        f"hits 7d:    wall {len(_recent_hits(s, 7, 'wall'))}, "
        f"soft {len(_recent_hits(s, 7, 'soft'))}",
    ]
    cu = s.get("cooldown_until")
    if cu:
        try:
            cu_dt = _parse(cu)
            kind = s.get("cooldown_kind") or "throttle"
            if now < cu_dt:
                lines.append(f"COOLDOWN:   {kind}, active until {cu_dt.strftime('%a %H:%M')}")
            else:
                lines.append(f"cooldown:   {kind}, expired (clear)")
        except ValueError:
            pass
    else:
        lines.append("cooldown:   none")
    return "\n".join(lines)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    s = load()
    if cmd == "check":
        verdict, msg = check(s)
        print(f"{verdict}:{msg}")
        sys.exit({"GO": 0, "WAIT": 2, "STOP": 1}.get(verdict, 1))
    elif cmd == "record":
        print(record(s))
    elif cmd == "cooldown":
        kind = sys.argv[2] if len(sys.argv) > 2 else "wall"
        if kind not in ("wall", "soft"):
            print(f"unknown cooldown kind '{kind}' (use: cooldown | cooldown soft)")
            sys.exit(1)
        print(cooldown(s, kind))
    elif cmd == "status":
        print(status(s))
    elif cmd == "reset":
        save(dict(EMPTY))
        print("state cleared")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
