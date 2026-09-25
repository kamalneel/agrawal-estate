---
scope: universal
project: null
category: finance
applies-to: any card, table or report that shows growth in dollars next to growth in percent
created: 2026-09-25
source-context: "BBD audit F3: 2025 showed '+$47,809' beside a +25% return because $238K had been withdrawn; 'pure growth' dollars were identical to combined"
---

# Dollar Growth Is Flow-Adjusted, Like the Percent

Growth in dollars is `ending − beginning − net external flows`, the money
the market (or the strategy) made. `ending − beginning` is the change in
balance and is wrong whenever money moved in or out. If the percent is
flow-adjusted (Modified Dietz), the dollars beside it must be too, from
the same flows. A "pure" or "excluding income" variant subtracts that
income as a flow as well.

## Why

The BBD page's percentages were Modified Dietz and correct; its dollar
cards were balance changes. 2025 read "+$47,809" beside "+25.5%" on a
$1.15M base, because Neel had withdrawn $238K during the year. The
"market appreciation only" dollars were byte-identical to the combined
ones. A reader trusts the pair together; when one is right and the other
wrong, both lose credibility.

## How to apply

- Store the period's net flows on the metric row and derive the dollar
  figure from it (`gain_value = actual − baseline − net_flows`), so every
  reader gets the same number.
- Show flows next to the gain in any detail table (Baseline · Actual ·
  Flows · Gain), so a large withdrawal is visible instead of implied.
- Average monthly rates are compound (`(1+cum)^(1/months) − 1`), not
  cumulative ÷ months.
- Check the flows against the ledger once: withdrawals per account per
  year should reconcile to the cash-movement rows.
