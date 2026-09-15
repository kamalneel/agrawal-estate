---
scope: universal
project: null
category: process
applies-to: any change to a recommendation engine (options strategy, rebalancing, notifications)
created: 2026-09-15
source-context: "V7 built 2026-09-13 as a preview beside live V6; two trading days of Neel's feedback produced seven rule changes a spec review found none of. Neel: 'this process is working, we should continue doing that.'"
---

# Test a Strategy Engine Live, Beside the Old One, One Observation at a Time

A new engine version runs on real data and shows its cards on its own
page while the old version keeps sending the notifications. The owner
trades his real accounts, looks at both, and sends one observation at a
time. Each observation is answered with the logic and live numbers, one
question is asked back, the rule is agreed, then encoded — as a knob when
the number is a guess — pushed, and captured in the running draft doc.
The switch to live happens only when the owner says so.

## Why

Rules look complete on paper and fail on the first real day: V7 said
"roll" on a call the owner had decided to let assign; re-capped a stock
he had just uncapped on purpose; capped a 3× ETF at a cost-basis floor
that was never the goal; re-sold a call into the same dip he had just
bought back on. None of these were visible in the spec. All of them were
visible in ten minutes of a trading morning.

## How to apply

- Preview page + live page, same layout, so the two are comparable at a
  glance. Cards carry an "assumption" chip wherever the engine guessed.
- One observation → explain first (with live chain quotes when they
  change the answer) → one question → agree → build → push → capture.
  Never a list of questions; never build before the "yes".
- Every number that came out of the conversation is a knob with a label,
  unit, range and one-line description, editable from the page and
  written back to the policy file so git shows the change.
- Decisions the engine cannot see (a planned assignment, a runaway
  thesis) get a declared entry in the policy file, not a special case.
- Related: [[document-philosophy-before-coding]] (the spec still comes
  first — it is just not the last word), [[algorithm-upgrade-checklist]].
