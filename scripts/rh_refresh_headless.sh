#!/bin/zsh
# Headless Robinhood MCP sync — invoked by launchd
# (~/Library/LaunchAgents/com.neelpersonal.rh-refresh.plist) at 5:40,
# 11:40, 19:40 PT on weekdays, timed ~20 min before the backend's
# notification scans (backend/app/core/scheduler.py) so emails see fresh
# positions.
#
# Runs the /refresh skill (.claude/commands/refresh.md) in a headless
# Claude session. Requires the robinhood-trading and
# robinhood-trading-neel MCP servers to be registered AND authorized in
# the CLI for this project (claude mcp list; /mcp to authorize). If
# authorization has expired, the run fails and logs — re-run /mcp.

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd /Users/neelpersonal/Coding-Projects/agrawal-estate-planner || exit 1

LOG=~/Library/Logs/rh-refresh.log
echo "===== $(date '+%Y-%m-%d %H:%M:%S') rh-refresh start =====" >> "$LOG"

claude -p "/refresh" \
  --allowedTools "Bash,Read,Write,Edit,ToolSearch,mcp__robinhood-trading,mcp__robinhood-trading-neel" \
  >> "$LOG" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S') rh-refresh exit=$? =====" >> "$LOG"
