# Robinhood MCP Sync

Replaces the three manual Robinhood feeds (holdings/options paste, cash
breakdown paste, activity CSV download) with data pulled through Robinhood's
agentic MCP server, fed through the app's existing ingestion endpoints.
First validated end-to-end 2026-07-02 for Jaya's three accounts.

## How it works

```
Claude Code session (connected to robinhood-trading MCP)
  │  pulls raw JSON via MCP tools, writes a "bundle" file
  ▼
scripts/robinhood_mcp_bridge.py  (deterministic, no LLM logic)
  │  synthesizes the three artifact formats the pipeline already accepts
  ├─→ POST /ingestion/robinhood-paste/preview + /save   (holdings + options)
  ├─→ POST /ingestion/robinhood-cash/preview + /save    (cash breakdown)
  └─→ activity CSV → data/inbox/investments/robinhood/ + POST /ingestion/scan
```

No new backend endpoints, no direct DB writes — the paste/cash/CSV parsers,
dedup keys, and ingestion_log provenance all apply unchanged.

## Account mapping

Two Robinhood logins are connected, each as its own MCP server
(`robinhood-trading` = Jaya, `robinhood-trading-neel` = Neel — add via
`claude mcp add --transport http <name> https://agent.robinhood.com/mcp/trading`,
then `/mcp` to authorize as that person).

### Jaya's login (`robinhood-trading`)

| Robinhood account        | account_number | App account     | cash_format |
|--------------------------|----------------|-----------------|-------------|
| Individual (margin)      | ••••2176       | Jaya's Brokerage| brokerage   |
| Traditional IRA          | ••••2659       | Jaya's IRA      | ira         |
| Roth IRA                 | ••••5779       | Jaya's Roth IRA | roth_ira    |

The joint account and the two cash accounts (Airbnb, Agentic) on this login
are not tracked in the app and are skipped.

### Neel's login (`robinhood-trading-neel`)

| Robinhood account        | account_number | App account       | cash_format |
|--------------------------|----------------|-------------------|-------------|
| Individual (margin)      | ••••1773       | Neel's Brokerage  | brokerage   |
| Traditional IRA          | ••••9591       | Neel's Retirement | ira         |
| Roth IRA (no nickname)   | ••••9901       | Neel's Roth IRA   | roth_ira    |

Also on this login: the same joint account visible from Jaya's login (skipped,
already excluded there), an empty "Agentic" cash account (skipped), and an
account nicknamed "Alisha Agrawal" that closely matches `alisha_brokerage`
holdings except missing 2 shares of FIG — left untouched pending user
confirmation; do not sync Alisha's data from this login without resolving
that discrepancy first.

Validated 2026-07-03: user cross-checked MCP-derived option income and cash
figures against their own activity-report paste and Buying Power screen for
all three Neel accounts before any save — see field-mapping notes below for
the one near-miss (a cash paste for "Neel's Retirement" that was actually
Jaya's IRA data, caught by comparing against the MCP figures before saving).

## Sync recipe (for a Claude session)

1. Per account: `get_portfolio`, `get_equity_positions`,
   `get_option_positions(nonzero=true)`, `get_option_orders(created_at_gte=…)`,
   `get_equity_orders(created_at_gte=…)`.
2. Across accounts: `get_option_instruments(ids=…)` for every option_id
   (strike/type), `get_option_quotes` (current marks),
   `get_equity_quotes` (stock prices).
3. Write the bundle JSON — schema per the docstring/sample in
   `scripts/robinhood_mcp_bridge.py`; sample from the first run:
   `scripts/rh_mcp_bundle_sample.json`.
4. Set each account's `activity_since` to the day AFTER its latest imported
   Robinhood transaction (`SELECT account_id, MAX(transaction_date) FROM
   investment_transactions WHERE source='robinhood' GROUP BY account_id`).
5. `python3 scripts/robinhood_mcp_bridge.py bundle.json` (preview) then
   `--save`.
6. **Price history (monthly-ish, or when a new symbol is bought):**
   `get_equity_historicals(symbols≤10, start_time=5y ago, interval=week)`
   for all held symbols, then POST
   `{source:"robinhood_mcp", bars:[{symbol,date,close}]}` to
   `/ingestion/price-history` (upserts `symbol_price_history`). Feeds the
   Investments page YTD/1Y/5Y growth columns (anchors = close ≤ target
   date within 21 days + live synced price). jq transform:
   `jq '{source:"robinhood_mcp", bars:[.data.results[] | .symbol as $s |
   .bars[] | {symbol:$s, date:(.begins_at[:10]),
   close:(.close_price|tonumber)}]}'`.

## Automation (added 2026-07-09)

- **`/refresh` skill** (`.claude/commands/refresh.md`): say "refresh" /
  type `/refresh` in a Claude session and the whole recipe above runs.
- **Scheduled**: launchd agent `com.neelpersonal.rh-refresh` runs
  `scripts/rh_refresh_headless.sh` (headless `claude -p "/refresh"`) at
  **5:40 / 11:40 / 19:40 PT weekdays** — ~20 min before the backend's
  notification scans (`backend/app/core/scheduler.py`: 6:00, 12:00+12:45,
  20:00) so emails see fresh positions. Logs:
  `~/Library/Logs/rh-refresh.log`.
- **Auth prerequisite**: headless runs use the CLI-registered MCP servers
  (`claude mcp list`), NOT claude.ai connectors. Both servers are
  registered project-local; they must be **authorized once via `/mcp` in
  a fresh CLI session** in this directory (and re-authorized if Robinhood
  tokens expire — failed runs say so in the log).
- Disable: `launchctl unload ~/Library/LaunchAgents/com.neelpersonal.rh-refresh.plist`.
- Each run consumes Claude usage (3 sessions/weekday).

## Field-mapping notes

- **Options**: `average_price` from `get_option_positions` is the broker's
  exact average credit; the bridge back-computes the gain% so the paste
  parser reconstructs it exactly (better than the manual paste, which loses
  precision). A drift guard aborts if the parsed original premium deviates
  >0.5% from the broker's figure.
- **Cash, brokerage**: portfolio `cash` is already net of margin
  (true_cash = cash − margin_used). Collateral shown is derived from
  cash-secured short puts (strike × contracts × 100). "Margin total" is not
  exposed via MCP and is left blank.
- **Cash, IRA**: `options_collateral = cash − buying_power` (verified to the
  cent against short-put strikes).
- **Activity**: one CSV row per fill; Trans Code from leg side+effect
  (sell/open→STO, buy/close→BTC, etc.).

## Known gaps / rules

1. **Dividends, interest, expirations (OEXP), assignments are NOT synced** —
   no MCP tool exposes them. They still come from the official activity CSV
   or monthly statements.
2. **Gross vs net amounts are reconciled automatically** (added 2026-07-02,
   validated both directions). Synthesized MCP amounts are gross; the
   official CSV is net of regulatory fees (≈$0.04–0.08/contract). The
   ingestion layer's fee-tolerant dedup (`_reconcile_fee_variant` in
   `backend/app/ingestion/services.py`) pairs such rows — same account,
   date, type, symbol, quantity, strike — and keeps the smaller signed
   (= fee-inclusive, official) amount. So uploading the official CSV over
   an MCP-synced period is safe: trade rows reconcile in place, dividend/
   interest/OEXP rows import normally. `activity_since` in the bundle
   remains as a first-line guard to keep sync windows tidy.
3. **Per-login scope**: one MCP connection sees one Robinhood login. A
   session must have both `robinhood-trading` and `robinhood-trading-neel`
   authorized (via `/mcp`) before their tools appear — a session started
   before a server was added/authorized won't see it; run `claude --continue`
   to reload.
4. **Reads work on all accounts** regardless of the `agentic_allowed` flag
   (that flag only gates placing trades).
5. **The bridge's paste-save call passes `confirm_empty_sections: true`**
   (added when Neel's Roth IRA — genuinely zero open options — tripped the
   app's empty-section safety check). This is safe only because the count
   guard earlier in `sync_account` already aborts if a section's parsed
   count doesn't match the expected MCP count, so a 0 reaching the save
   call is a confirmed-genuine empty, not an accidental clear.
6. **Always independently verify pasted data before saving**, even when it
   "looks plausible" — a cash-balance paste can be copied from the wrong
   account/tab. Cross-check every pasted figure against the live MCP pull
   (portfolio cash/buying-power, or a derived figure like collateral summed
   from strikes) before running `--save`. Caught once already: a paste
   labeled "Neel's Retirement" matched Jaya's IRA to the penny.
