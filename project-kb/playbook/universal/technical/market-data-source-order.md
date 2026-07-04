---
scope: universal
project: null
category: technical
applies-to: any code or session fetching quotes, historical prices, option chains, or fundamentals
created: 2026-07-04
source-context: "Transfer-date basis resolution: yfinance was blocked/rate-limited by Yahoo on every request; Robinhood MCP historicals returned all prices (back to 2018) in one round. Neel confirmed repeated past Yahoo failures."
---

# Market Data Source Order: Robinhood, then Schwab — Never Yahoo for Must-Succeed Paths

For prices, historicals, chains, and quotes, prefer in order:

1. **Robinhood MCP** (`get_equity_quotes`, `get_equity_historicals` — split-
   adjusted daily bars verified back to 2018, `get_option_quotes`/chains)
2. **Schwab API** (`strategies/schwab_service.py`) as the second source
3. **Yahoo/yfinance — only as a last-resort convenience**, never in a path
   that must succeed (ingestion, basis resolution, scheduled jobs)

## Why

Yahoo aggressively rate-limits and blocks programmatic access; yfinance
fails with opaque errors ("Expecting value", "possibly delisted") once
blocked. Neel has hit this repeatedly; it also failed live on 2026-07-04
while Robinhood historicals succeeded immediately. The brokers are also
authoritative for the family's own positions in a way Yahoo never is.

## How to apply

- New code needing market data: call the Robinhood MCP (in-session) or
  schwab_service (in-backend) first; do not add new yfinance call sites.
- The existing `strategies/yahoo_cache.py` dependency is a flagged refactor
  candidate — migrate consumers to Robinhood/Schwab over time.
- If a fallback chain is built, Yahoo may sit at the end, but a Yahoo
  failure must degrade gracefully, never block a pipeline.
