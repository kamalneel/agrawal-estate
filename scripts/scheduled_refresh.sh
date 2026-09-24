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
#
# Sync → wait → email (Neel, 2026-09-17). When the run finishes the script
# POSTs /strategies/notify/after-sync. At the four decision-point slots
# (6:40, 7:50, 11:50, 19:50 — the email lands ~6 min later, where Neel's
# 6:50 / 8:00 / 12:00 / 8:00 PM scans used to be) that sends the full scan
# email on the data just synced. Every other run is silent on success
# (Neel, 2026-09-18: the per-run "sync complete" note "is not needed");
# a FAILED run always emails, flagged.
set -u
PROJECT="/Users/neelpersonal/Coding-Projects/agrawal-estate-planner"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$PROJECT" || exit 1
STAMP=$(date +%Y-%m-%d-%H%M)
LOG="$PROJECT/logs/refresh/$STAMP.log"
BUNDLES="/tmp/agrawal-refresh/$STAMP"
mkdir -p "$PROJECT/logs/refresh" "$BUNDLES"

# One sync at a time. The page's Sync button (POST /strategies/sync, Neel
# 2026-09-18) can start this script while the hourly launchd run is still
# going; two bridges writing the same snapshots would double-count.
# mkdir is atomic and macOS has no flock(1). A lock older than 30 minutes
# is a crashed run (the watchdog below kills a hung claude at 20) and is
# taken over.
LOCK="$PROJECT/data/refresh.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then
    rm -rf "$LOCK" && mkdir "$LOCK"
  else
    echo "$(date) another sync is running (lock $LOCK) — skipping" >> "$LOG"
    exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT
# Tell the page a sync is in flight; the end of the run overwrites this.
backend/venv/bin/python - <<PY
import json, datetime, pathlib
prev = {}
try: prev = json.loads(pathlib.Path("data/refresh_status.json").read_text())
except Exception: pass
prev.update({"running": True, "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
             "trigger": "${REFRESH_TRIGGER:-scheduled}", "mode": "${REFRESH_MODE:-full}"})
pathlib.Path("data/refresh_status.json").write_text(json.dumps(prev, indent=2))
PY

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

# Sync modes (Neel, 2026-09-18: "rather than one sync button, we have
# multiple sync buttons"). REFRESH_MODE from the environment:
#   full   — the whole /refresh skill (scheduled runs; default)
#   state  — account state: positions, cash and FILLS for all six accounts,
#            bridged and saved, assignment detection, post-verify. No
#            implied-vol pass, no price-history/earnings refresh.
#   prices — live prices only: equity quotes + ATM implied vol for every
#            tracked symbol (held + allocation targets + policy), written
#            to symbol_price_history through the bridge. No account calls.
#   chains — option chains for tracked symbols (not built yet; see skill).
MODE="${REFRESH_MODE:-full}"
case "$MODE" in
  state)
    OK_MARK="SYNC OK"; WATCHDOG_S=1200
    PROMPT="/refresh
Headless ACCOUNT-STATE run (mode=state). Do steps 1, 2, 3, 4, 5, 6 and 7 of the skill for all six accounts: positions, cash, orders since activity_since, instruments and quotes needed for the paste, the collateral gate, bridge preview then --save for both logins, assignment detection, post-verify. Step 3 must quote EVERY tracked symbol from /strategies/sync/tracked-symbols, not only the ones the accounts hold. SKIP step 3b (implied vol), step 8 and step 9. Write the two bundle JSON files to $BUNDLES (not a scratchpad). Finish with a report of at most 12 lines that starts with the line SYNC OK, or SYNC FAILED followed by why."
    ;;
  prices)
    OK_MARK="PRICES OK"; WATCHDOG_S=600
    PROMPT="/refresh
Headless PRICES-ONLY run (mode=prices). Do NOT call any per-account tool (no get_portfolio, no positions, no orders) and do NOT run assignment detection. Steps: (a) GET http://127.0.0.1:8000/api/v1/strategies/sync/tracked-symbols with curl — it returns the symbol list to price. (b) get_equity_quotes for all of them (either login). (c) Skill step 3b for every symbol: at-the-money implied vol from one call quote at the nearest Friday with >= 3 days left. (d) Write ONE bundle to $BUNDLES/bundle_prices.json with as_of (ISO timestamp now), source_login, instruments: [], option_marks: {}, equity_marks: {SYMBOL: price}, implied_vols: {SYMBOL: fraction}, accounts: []. (e) Run python3 scripts/robinhood_mcp_bridge.py $BUNDLES/bundle_prices.json --save. Finish with a report of at most 8 lines that starts with the line PRICES OK (then the count of symbols priced and how many carry implied vol), or PRICES FAILED followed by why."
    ;;
  chains)
    echo "$(date) mode=chains is not implemented yet" >> "$LOG"
    backend/venv/bin/python - <<PY
import json, datetime, pathlib
pathlib.Path("data/refresh_status.json").write_text(json.dumps({
  "ran_at": datetime.datetime.now().isoformat(timespec="seconds"), "ok": False, "running": False,
  "mode": "chains", "trigger": "${REFRESH_TRIGGER:-scheduled}", "cost_usd": 0, "log": "$LOG",
  "report": "CHAINS NOT BUILT — option-chain sync is not implemented yet."}, indent=2))
PY
    exit 0
    ;;
  *)
    MODE="full"; OK_MARK="SYNC OK"; WATCHDOG_S=1200
    PROMPT="/refresh
Scheduled headless run. Write the two bundle JSON files to $BUNDLES (not a scratchpad). Do every step of the skill including assignment detection and the post-verify. Step 3 must quote EVERY tracked symbol from /strategies/sync/tracked-symbols (not only what the accounts hold) and step 3b must compute implied vol for every one of them. Skip the price-history and earnings-calendar refreshes unless the skill's own conditions say to run them. Finish with a report of at most 15 lines that starts with the line SYNC OK, or SYNC FAILED followed by why, if any gate or save did not pass."
    ;;
esac

# which email follows this run: decision-point slot → that scan; else none
# unless it failed. ±10 min tolerance around the slot so a launchd run that
# started late still gets its scan; a manual run at 9:12 does not.
NOW=$(( 10#$(date +%H) * 60 + 10#$(date +%M) ))
SCAN=""
for pair in 400:6am_main 470:8am_post_open 710:12pm_midday 1190:8pm_evening; do
  slot=${pair%%:*}
  if (( NOW >= slot - 10 && NOW <= slot + 10 )); then SCAN=${pair##*:}; fi
done
[[ -n "${1:-}" ]] && SCAN="$1"     # ./scheduled_refresh.sh 8pm_evening  forces one
# A manual run is silent by default (Neel, 2026-09-18). REFRESH_EMAIL=1 asks
# for the action-queue email anyway — "I just synced, tell me what to do now"
# (Neel, 2026-09-24).
[[ "${REFRESH_EMAIL:-0}" == "1" && -z "$SCAN" ]] && SCAN="manual"
[[ "$MODE" == "prices" ]] && SCAN=""   # a prices pull never triggers a scan email

echo "$(date) start mode=$MODE scan=${SCAN:-none}" >> "$LOG"
# hard stop: a headless run that hangs (a prompt it cannot answer, a stuck
# MCP call) must not sit forever and block the next slot — 2026-09-17 the
# 7:05 run hung for 3 hours with 5s of CPU. 20 minutes is 4x a normal run.
( sleep "$WATCHDOG_S"; pkill -P $$ claude 2>/dev/null; pkill -f "claude -p /refresh" 2>/dev/null ) &
WATCHDOG=$!
RESULT=$(claude -p "$PROMPT" \
  --allowedTools "mcp__robinhood-trading-jaya,mcp__robinhood-trading-neel,Skill,ToolSearch,Read,Write,Bash(python3 scripts/robinhood_mcp_bridge.py:*),Bash(curl:*),Bash(backend/venv/bin/python:*),Bash(cd:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*)" \
  --max-turns 120 --output-format json 2>>"$LOG")
STATUS=$?
kill $WATCHDOG 2>/dev/null
echo "$RESULT" >> "$LOG"

backend/venv/bin/python - "$RESULT" "$STATUS" "$LOG" "$OK_MARK" "$MODE" <<'PY'
import json, sys, datetime, pathlib, os
raw, status, log, ok_mark, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
try:
    d = json.loads(raw)
    text = str(d.get("result", ""))
    err = bool(d.get("is_error")) or status != 0 or ok_mark not in text
    cost = d.get("total_cost_usd")
except Exception:
    text, err, cost = raw[-2000:], True, None
summary = {"ran_at": datetime.datetime.now().isoformat(timespec="seconds"), "ok": not err,
           "running": False, "trigger": os.environ.get("REFRESH_TRIGGER", "scheduled"), "mode": mode,
           "cost_usd": cost, "log": log, "report": text[-3000:]}
pathlib.Path("data/refresh_status.json").write_text(json.dumps(summary, indent=2))
print(("OK " if not err else "FAILED ") + f"cost=${cost}")
PY

# the email — a scan, or a failure notice — comes from the backend, which reads
# data/refresh_status.json just written. If that call itself fails, fall
# back to a bare failure email so the run is never silent.
NOTIFY=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 -X POST \
  "http://127.0.0.1:8000/api/v1/strategies/notify/after-sync${SCAN:+?scan_type=$SCAN}")
echo "$(date) notify scan=${SCAN:-none} http=$NOTIFY" >> "$LOG"
if [[ "$NOTIFY" != "200" ]]; then
  backend/venv/bin/python - "$LOG" "$NOTIFY" <<'PY'
import sys, json
sys.path.insert(0, "backend")
log, code = sys.argv[1], sys.argv[2]
st = json.load(open("data/refresh_status.json"))
from app.shared.services.notifications import get_notification_service
get_notification_service()._send_email(
    subject=("Robinhood sync " + ("OK" if st.get("ok") else "FAILED")) + f" — but the email step returned HTTP {code}",
    html_body="<pre>" + (st.get("report") or "(no output)").replace("<", "&lt;") + "</pre><p>Log: " + log + "</p>",
    plain_text=(st.get("report") or "(no output)") + "\nLog: " + log)
PY
fi
