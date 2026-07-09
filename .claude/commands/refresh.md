# Refresh — full Robinhood MCP sync

When this skill is invoked, run the complete Robinhood data sync:
pull live data for all six tracked accounts from both Robinhood MCP
logins, verify it, feed it through the bridge into the app, and report
what changed. The authoritative recipe is `docs/ROBINHOOD_MCP_SYNC.md`
— consult it if anything below seems stale (it wins on conflict).

## Prerequisites (check, don't assume)

- Both MCP servers must be authorized in this session:
  `robinhood-trading` (= Jaya's login) and `robinhood-trading-neel`
  (= Neel's login). If a server's tools are missing, tell Neel to run
  `/mcp` to authorize it — do not proceed with half the accounts.
- Backend must be running on :8000 (`curl -s localhost:8000/api/v1/investments/accounts`).

## Accounts

| App account       | Login | account_number | cash_format |
|-------------------|-------|----------------|-------------|
| Jaya's Brokerage  | jaya  | 701552176      | brokerage   |
| Jaya's IRA        | jaya  | 534052659      | ira         |
| Jaya's Roth IRA   | jaya  | 704155779      | roth_ira    |
| Neel's Brokerage  | neel  | 5XE31773       | brokerage   |
| Neel's Retirement | neel  | 439569591      | ira         |
| Neel's Roth IRA   | neel  | 514429901      | roth_ira    |

Never sync Alisha's account from Neel's login (known share-count
discrepancy, unresolved — see the sync doc).

## Steps

1. **activity_since per account** (day AFTER latest imported row):
   `SELECT account_id, MAX(transaction_date) FROM investment_transactions
   WHERE source='robinhood' GROUP BY account_id;`
2. **Per account, on its login**: `get_portfolio`, `get_equity_positions`,
   `get_option_positions(nonzero=true)`,
   `get_option_orders(created_at_gte=activity_since)`,
   `get_equity_orders(created_at_gte=activity_since)`.
3. **Across accounts** (either login): `get_option_instruments(ids=…)`
   for every unique position option_id; `get_option_quotes` for marks
   (≤20 ids per call); `get_equity_quotes` for every held/underlying
   symbol.
4. **Verify BEFORE saving** (hard gate, never skip): for each IRA,
   `cash − buying_power` must equal short-put collateral
   (Σ strike × contracts × 100) **to the cent**. If it doesn't, stop and
   investigate — do not save.
5. **Write bundles** (schema: `scripts/rh_mcp_bundle_sample.json`; one
   bundle per login, into the session scratchpad) and run
   `python3 scripts/robinhood_mcp_bridge.py <bundle> ` (preview) — check
   every section count matches (`stocks=N/N options=M/M`) — then rerun
   with `--save` for both bundles.
6. **Post-verify**: activity_since query again (dates should advance for
   accounts that traded); `curl /api/v1/strategies/v6/action-queue` —
   confirm `data_as_of` is today and skim the summary.
7. **Monthly-ish, or when a NEW symbol is held**: refresh price history
   (sync doc step 6 — `get_equity_historicals` 5y weekly → POST
   `/ingestion/price-history`). Skip on routine refreshes.

## Report back

Lead with what changed: new fills imported (symbol, qty, account),
notable position changes (rolls, assignments, new positions), and the
Action Queue delta (urgent/high counts vs. before the sync). Mention
the collateral verification passed. Remind Neel that open browser tabs
need a reload; the pages themselves read live.

## Known gaps (from the sync doc — don't re-derive)

- Dividends, interest, OEXP, assignments do NOT come via MCP — official
  activity CSV / statements only. If assignments are suspected (deep ITM
  puts through an expiry), say so in the report.
- MCP amounts are gross; the official CSV is net of fees — the ingestion
  layer reconciles fee variants automatically, so later CSV uploads over
  a synced period are safe.
