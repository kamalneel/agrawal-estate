---
scope: universal
project: null
category: technical
applies-to: any pipeline that filters bookkeeping rows by category kind (spending, income, transfer) before aggregating them
created: 2026-09-06
source-context: "Spending page audit: two $9,000 rent wires filed as Transfer and two $3,455 refunds filed as Income had silently vanished from the page."
---

# Run Counterparty and Refund Rules Before the Category-Kind Filter

When rows are classified by the kind of their bookkeeping category (spending /
income / transfer / business), every rule that can override that kind —
counterparty rules, refund detection — must run **first**. A kind filter that
runs on the raw category throws the row away before any rule can see it.

Order, always:

1. Counterparty rule (landlord, employer, tenant) → kind and label fixed
2. Refund test on the statement text → nets, whatever category it sits in
3. Category kind
4. Display label

## Why

On the Spending page the rulebook (`display_category`) ran *after*
`_base_query` had excluded every Transfer- and Income-kind row. So:

- 2026-07-06 and 07-31: $9,000 rent wires to the new landlord arrived from
  Monarch as `Transfer`. Rent for July and August read $0. July showed
  $9,461 against ~$18,500 real. Every month of 2025 had carried rent.
- 2026-08-28/30: two $3,455 charges were refunded within three days, and
  Monarch filed the refunds as `Business Income` and `Other Income`. The
  charges counted, the refunds vanished, and August read 30% high. Eleven
  such refunds ($13.3K) had accumulated across 2026, mostly airline refunds.

Neither failure produced an error. Both produced a plausible number.

## How to apply

- Put the whole decision in one function (`classify()` in
  `spending/models.py`) that returns kind, label, is-refund and counted, and
  make every consumer go through it — page, reconciliation, downstream
  models. Two consumers with their own filter will disagree.
- Counterparty lists are explicit and commented, so a change of landlord
  fails loudly (see [[category-is-a-ledger-not-a-stream]]).
- A refund filed as income adopts the label of the charge it reverses
  (same merchant, same amount); no match → a visible "Refunds" line, never a
  silent drop.
- Show the count of rows rescued this way on the page until the source
  (Monarch) is corrected. The rule is a safety net, not the fix.
- Restrict refund netting to spending- and income-kind rows. A refund inside
  a business or transfer ledger stays with that ledger.
