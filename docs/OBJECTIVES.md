# Application Objectives — North Star

Captured from Neel, 2026-07-03. This is the definition of what the application
is *for*. Every feature should trace back to one of these objectives; anything
that doesn't is a candidate for removal.

## 1. Income — one place, weekly / monthly / annual

Bring **all income into one place**, viewable weekly, monthly, and annually.

- **Fixed income**: salary, rent, and similar recurring sources.
- **Dynamic income**: everything realized from trading —
  - Options premium (selling options).
  - **Stock sales**: selling a stock creates income (positive or negative).
    Holding a stock is *not* income.
  - **Forced assignments**: when a call is assigned, the resulting
    gain/loss is income — categorized as equity-sale income, like any
    normal stock sale (put assignment just creates a holding; not income).

The test: "What did I earn this week / this month / this year, across all
sources, fixed + dynamic, in one view?"

## 2. Options Execution — daily guidance against explicit yield targets

Help with **what I am doing daily** on options: what should I be doing, am I
making a mistake, what are the guidelines?

Driven by two explicit targets:

- **1% per month on all holdings** (stock collateral → covered calls etc.).
  $1,000,000 in stock should earn $10,000/month.
- **2% per month on all cash** (cash collateral → cash-secured puts).
  $100,000 in cash should earn $2,000/month.

The system should measure actuals against these targets and steer daily
execution toward them.

## 3. Investment — show what I've done, enforce the policy

Show current investments and support making changes, against a stated policy:

- **Owning stock**: only the **trillion-dollar club** — companies above
  $1T market cap.
- **Selling puts**: target whatever is **most volatile / hot at the time**
  (collateral rules per account type still apply).

## 4. Spending — high-level categorization

Categorize spending so I can see, at a high level, what I'm spending on and
whether I'm spending in the right places. Nothing deeper needed.

## 5. Buy-Borrow-Die — adherence and risk check

Verify I am **following BBD principles** and surface whether doing so would
**create any problems** (margin stress, expense coverage, income shortfall).

## Operational (not objectives, just plumbing)

- **Notifications** — delivery mechanism for the above.
- **Data import** (statements, CSVs, Robinhood MCP sync) — how data gets in.

These exist to serve objectives 1–5 and should stay as thin as possible.
