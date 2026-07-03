---
scope: universal
project: null
category: technical
applies-to: stock lots, realized P/L, income calculations, data-freshness checks
created: 2026-07-03
source-context: "Lot rebuild verification: Neel's IBIT 100 shares and INTC 50 shares off vs holdings; recent assignments missing because last official CSV import predates June 2026"
---

# Assignment Share-Rows Only Arrive via Official CSV

Option assignments produce paired share transactions (put → `BUY` at strike,
call → `SELL` at strike) — but those rows come only from the official
Robinhood activity CSV. The MCP sync does not carry
expirations/assignments/dividends (documented gap in ROBINHOOD_MCP_SYNC.md).

Therefore: **lot accuracy and realized-P/L accuracy are gated by CSV import
freshness.** A stale CSV means recent assignments are invisible, and open-lot
quantities silently drift from actual holdings.

## Why

Rebuild verification (2026-07-03) found Neel's IBIT lots 100 shares short
and INTC 50 shares over vs live holdings — consistent with June 2026
assignments missing because the last CSV import was ~May 2026.

## How to apply

- Before trusting realized P/L or income figures, check the newest official
  CSV row date per account against today.
- The lots-vs-holdings diff (open lot shares vs `investment_holdings`) is
  the standing health check — run it after every rebuild or import; any
  drift usually means a missing assignment row.
- Long-term fix candidate: freshness indicator in the UI + reminder to
  export the activity CSV monthly.
