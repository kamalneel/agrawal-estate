---
scope: universal
project: null
category: finance
applies-to: every covered call in a taxable account; assignment detection; the lot engine
created: 2026-09-13
source-context: "Jaya's 3 × TSLA $340 calls expiring 9/18: FIFO realises +$76K of long-term gain, the put-assignment lots realise −$18K. Neel: 'make a rule that every time there is a call assignment ... send me a note regarding the tax implications.'"
---

# Every Call Assignment in a Taxable Account Gets a Tax-Lot Notice, Before the Deadline

A covered call that is assigned sells shares. In a taxable account, *which*
shares decides the tax, and Robinhood decides for you unless told
otherwise. So every call assignment — better, every in-the-money short
call about to expire — in Neel's, Jaya's or Alisha's brokerage produces one
notice: FIFO vs Highest Cost on the exact lots, the deadline, and the
support message to paste. Implemented in
`backend/app/modules/tax/assignment_tax_notice_service.py`; runs daily
6:30 AM PT and after MCP assignment detection; `POST
/api/v1/tax/assignment-lot-notices?dry_run=true` previews.

## Why

Robinhood's rules (support article *Tax lots*, read 2026-09-13):
- The account's **default disposal method applies to "shares resulting
  from options exercise or assignment."** Default is **FIFO** — oldest,
  lowest-basis lots first. Options: FIFO, LIFO, Highest Cost, Lowest Cost.
- Changing the default **before 8 PM ET applies to that day's trades**.
  App/web: Account → (Menu →) Investing → Tax lots disposal method → Edit.
- An executed order's lots can be corrected only by contacting support
  **before 9 PM ET on the settlement date** (T+1). Support is in-app or
  robinhood.com/contact — 24/7 chat, callback 7 AM–9 PM ET weekdays.
  **There is no support email.**

Jaya's TSLA: four lots — 630 @ $85.39 (2024), 70 @ $396.89, 200 @ $375,
100 @ $435 (put assignments). Three $340 calls assign 300 shares. FIFO
takes the 2024 lot: **+$76,383 long-term gain**. Highest Cost takes the
put-assignment lots: **−$18,032 short-term loss**, harvestable against
option premium. A **$94K swing in taxable income**, ~$34K of tax, decided
by a setting nobody had looked at.

## How to apply

- **Set the default to Highest Cost on every taxable account** and leave
  it. Assignments then pick the right lots without a support message.
  Verify it is still set whenever a taxable account is opened or migrated.
- The notice still goes out every time — it is the check that the setting
  held, and it carries the deadline and the message for when it did not.
- Put-assignment lots are the usual highest-cost lots (assigned above
  market by definition); they are what a call assignment should deliver.
- **The lot engine uses the same method as the broker.** The per-account
  method and effective date live in `data/goal_settings.json`
  (`lot_disposal_method`); `scripts/rebuild_stock_lots.py` consumes lots
  FIFO before the effective date and by the named method from it, so
  realised P/L matches what the 1099-B will say. Neel set Neel's and
  Jaya's brokerages to Highest Cost on 2026-09-13 (effective 2026-09-14).
  **When a method is changed at the broker, change it there the same day.**
- Sheltered accounts (IRA, Roth, HSA) are out of scope — no tax on lots.
- Related: [[definition-of-income]] (assignment = income at sale),
  [[buy-in-round-lots-of-100]], [[lot-quantities-are-post-split-units]].
