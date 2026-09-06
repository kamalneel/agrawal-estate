---
scope: universal
project: null
category: process
applies-to: every session that reports, reviews, or reasons about income, spending, or portfolio numbers
created: 2026-09-06
source-context: "Neel: 'go into a mode where you are asking me for things you need, rather than me finding out the error and then you fixing it.'"
---

# Check Data Freshness First, and Ask For What Is Missing

Before reporting any financial number, check how current each feeding stream
is. When a stream is stale or a connection has dropped, **ask for the file or
the reconnect up front** — do not report on it, and do not wait for the user
to notice a wrong number and come asking why.

State what you need, why you need it, and what it will change.

## Why

Stale data does not look stale. It looks like a real number.

August 2026 read $0 for dividends, interest and lending. That was not zero
income — it was an activity CSV that had not been imported since July, while
options stayed current to the day because they come from a live MCP feed.
The same session found the rent card wrong because the Monarch export ended
2026-08-26 and the tenant had paid on the 29th and 31st.

In both cases the user discovered the problem by looking at a card and
thinking "that can't be right." That is the wrong direction of travel. Every
one of those gaps was mechanically detectable before anyone looked.

Disconnections are worse than lag: a feed that drops and reconnects leaves a
**hole in the middle** of a date range, not a short tail. Monarch's August
2026 reconnect produced a July file carrying the Robinhood card for the
26th-31st and nothing for the 1st-25th.

## How to apply

At the start of any session that will report numbers, check each stream
against **the cadence it actually refreshes on** — never against today. Then
ask only for what is both missing and obtainable.

### Never ask for data that does not exist yet

Robinhood publishes a monthly statement only after the month closes, and it
takes about two more days: **September's statement appears around October
3rd-4th** (Neel, 2026-09-06). Everything sourced from it is therefore
*expected* to look weeks old for most of a month, and that is not staleness.

Judge a statement-fed stream by "is the last COMPLETED month imported?", not
by the age of its newest row. On 2026-09-06 the freshness check flagged
lending as 30 days behind and dividends as 13 — both false alarms. The
August statements were already imported and validated; there was simply
nothing further to give until October. Asking for them anyway is exactly the
nagging this rule exists to prevent.

| Stream | Refreshed by | Cadence — ask only when |
|---|---|---|
| options, assignments | Robinhood MCP | automatic, current within days; never ask |
| dividends, interest, lending, margin interest, equity buys/sells | Robinhood monthly statement (`scripts/import_robinhood_statement_pdf.py`) | the last completed month's statement is not imported AND it is past ~the 4th of the following month |
| salary, rent, Airbnb, spending | Monarch export (`scripts/import_monarch_spending_csv.py`) | the tail is more than ~a week old |
| lot sales (derived) | rebuild — see [[derived-tables-need-a-rebuild-trigger]] | it lags its source ledger; never ask the user, just rebuild |

### A dead account disappears from a windowed query

Check freshness against **every account ever seen**, not every account seen
recently. A windowed query ("accounts with rows since July") cannot report an
account that stopped in June — it has no rows in the window, so it drops out
of the result entirely and reads as absent rather than as stale.

On 2026-09-06 that blind spot hid two dead Monarch feeds for three months:
`CREDIT CARD (...5149)` (last row 2026-06-19) and `Spending (...dabe)` (last
row 2026-06-06, carrying ~$50K of Robinhood transfers). The same check
correctly flagged two merely-lagging accounts, which made it look like it
was working.

Enumerate accounts over all history, then compute each one's tail.

### An account is not missing just because it is named badly

Monarch labels some card feeds generically. `CREDIT CARD (...2417)` is the
Amazon card — 403 Amazon rows, plus Whole Foods, Audible, Prime Video,
Kindle. Before reporting an account as absent, match on its **merchant
profile**, not its name.

The dangerous inverse is a rename: Monarch renamed
`Robinhood Spending (...2623)` to `Spending (...dabe)` mid-2026. A renamed
account looks like one dead account plus one new one, and silently
double-counts if both names survive in the ledger. `ACCOUNT_ALIASES` in
`scripts/import_monarch_spending_csv.py` exists for exactly this; extend it
whenever a tail goes dead and a new account name appears near the same date.

### When you do ask

- One thing at a time, naming the file and where it goes.
- Say what is affected: "dividends and interest will read low for September
  until the statement lands in early October" beats a silent zero.
- A per-account tail lagging the others by weeks means that feed dropped —
  ask for a reconnect, not a re-export.
- Report the number anyway when asked, but label what is provisional. Never
  present a stale figure as settled.
