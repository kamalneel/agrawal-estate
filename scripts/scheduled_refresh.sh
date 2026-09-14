#!/bin/zsh
# Scheduled Robinhood sync — runs the /refresh skill headlessly.
#
# Neel, 2026-09-14: "make the sync a scheduled job." The Robinhood MCP
# servers are OAuth'd to Claude Code (project scope, ~/.claude.json), not to
# the backend, so the only process that can pull positions is a Claude Code
# session. `claude -p` runs one without a terminal, with the same cached
# OAuth tokens, and the /refresh skill does the rest (pull, verify, bridge,
# detect assignments). Installed via launchd — see
# scripts/com.agrawal.estate.refresh.plist and docs/ROBINHOOD_MCP_SYNC.md.
#
# Failure = non-zero exit, or is_error in the JSON result, or a result that
# does not mention the bridge's "done" line. Any failure emails Neel through
# the backend's notification service so a dead sync is never silent
# (playbook: check-freshness-and-ask-first).
set -u
PROJECT="/Users/neelpersonal/Coding-Projects/agrawal-estate-planner"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$PROJECT" || exit 1
STAMP=$(date +%Y-%m-%d-%H%M)
LOG="$PROJECT/logs/refresh/$STAMP.log"
BUNDLES="/tmp/agrawal-refresh/$STAMP"
mkdir -p "$PROJECT/logs/refresh" "$BUNDLES"

# backend must be up; without it the bridge has nowhere to write
if ! curl -sf -o /dev/null --max-time 5 http://127.0.0.1:8000/api/v1/health 2>/dev/null \
   && ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8000/api/v1/investments/accounts; then
  echo "$(date) backend not reachable on :8000 — skipping" >> "$LOG"
  backend/venv/bin/python - "$LOG" <<'PY'
import sys
sys.path.insert(0, "backend")
from app.shared.services.notifications import get_notification_service
get_notification_service()._send_email(
    subject="Robinhood sync skipped — backend not running",
    html_body="The scheduled sync found nothing on :8000. Start the backend; the next run is in an hour.",
    plain_text="The scheduled sync found nothing on :8000.")
PY
  exit 0
fi

PROMPT="/refresh
Scheduled headless run. Write the two bundle JSON files to $BUNDLES (not a scratchpad). Do every step of the skill including assignment detection and the post-verify. Skip the price-history and earnings-calendar refreshes unless the skill's own conditions say to run them. Finish with a report of at most 15 lines that starts with the line SYNC OK, or SYNC FAILED followed by why, if any gate or save did not pass."

echo "$(date) start" >> "$LOG"
RESULT=$(claude -p "$PROMPT" \
  --allowedTools "mcp__robinhood-trading-jaya,mcp__robinhood-trading-neel,Skill,ToolSearch,Read,Write,Bash(python3 scripts/robinhood_mcp_bridge.py:*),Bash(curl:*),Bash(backend/venv/bin/python:*),Bash(cd:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*)" \
  --max-turns 120 --output-format json 2>>"$LOG")
STATUS=$?
echo "$RESULT" >> "$LOG"

backend/venv/bin/python - "$RESULT" "$STATUS" "$LOG" <<'PY'
import json, sys, datetime, pathlib
raw, status, log = sys.argv[1], int(sys.argv[2]), sys.argv[3]
sys.path.insert(0, "backend")
try:
    d = json.loads(raw)
    text = str(d.get("result", ""))
    err = bool(d.get("is_error")) or status != 0 or "SYNC OK" not in text
    cost = d.get("total_cost_usd")
except Exception:
    text, err, cost = raw[-2000:], True, None
summary = {"ran_at": datetime.datetime.now().isoformat(timespec="seconds"), "ok": not err,
           "cost_usd": cost, "log": log, "report": text[-3000:]}
pathlib.Path("data/refresh_status.json").write_text(json.dumps(summary, indent=2))
print(("OK " if not err else "FAILED ") + f"cost=${cost}")
if err:
    from app.shared.services.notifications import get_notification_service
    get_notification_service()._send_email(
        subject="Robinhood scheduled sync FAILED",
        html_body="<pre>" + (text or "(no output)")[-3000:].replace("<", "&lt;") + "</pre><p>Log: " + log + "</p>",
        plain_text=(text or "(no output)")[-3000:] + "\nLog: " + log)
PY
