# Tax Year 2026 — Document Inventory

**Tax year:** 2026 (filing due April 15, 2027; if extended, October 15, 2027)
**Filers:** Neel Kamal & Jaya Agrawal (MFJ)
**CPA package status:** Not yet assembled

This is the master tracking sheet for all tax-year-2026 paperwork. Update this file whenever a new document is dropped into `data/tax-documents/2026/`.

See `data/tax-documents/2025/INVENTORY.md` for last year's structure and outstanding items to anticipate.

---

## Status legend
- `received` — physical/digital document is in this folder
- `awaiting` — known to be coming, not yet received
- `sent-to-cpa` — included in the CPA package
- `n/a` — informational only, no action needed

---

## Income — W-2

| File | Recipient | Issuer | Received | Status | Notes |
|---|---|---|---|---|---|
| _(Neel W-2, AdamX Inc.)_ | Neel | AdamX Inc. | — | awaiting | Expected late Jan 2027; paystubs below are the interim record |
| _(Jaya W-2, DeWinter)_ | Jaya | DeWinter | — | awaiting | Expected late Jan 2027 |

## Paystubs (interim record of wages and tax withheld until the W-2 arrives)

Ingested into `salary_payslips` with `backend/scripts/ingest_paystubs.py`; the tax forecast reads the latest YTD row per person.

| File | Person | Employer | Pay date | Gross | Fed w/h | CA w/h | YTD gross | YTD fed | YTD CA | Status |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| _(Jun 15 / Jun 30 stubs)_ | Neel | AdamX Inc. | 2026-06-15, 06-30 | 5,000 each | ? | ? | | | | **awaiting** — rows exist gross-only from a screen paste; PDFs needed |
| `paystubs/Neel_AdamX_Paystub_2026-07-15.pdf` | Neel | AdamX Inc. | 2026-07-15 | 5,000.00 | 326.67 | 170.24 | 15,000.00 | 980.01 | 510.72 | ingested 2026-09-12 |
| `paystubs/Neel_AdamX_Paystub_2026-07-31.pdf` | Neel | AdamX Inc. | 2026-07-31 | 5,000.00 | 326.67 | 170.24 | 20,000.00 | 1,306.68 | 680.96 | ingested 2026-09-12 |
| `paystubs/Neel_AdamX_Paystub_2026-08-14.pdf` | Neel | AdamX Inc. | 2026-08-14 | 15,000.00 | 2,569.50 | 1,172.44 | 35,000.00 | 3,876.18 | 1,853.40 | ingested 2026-09-12 |
| `paystubs/Neel_AdamX_Paystub_2026-08-31.pdf` | Neel | AdamX Inc. | 2026-08-31 | 15,000.00 | 2,569.50 | 1,172.44 | 50,000.00 | 6,445.68 | 3,025.84 | ingested 2026-09-12 |
| `paystubs/Neel_AdamX_Paystub_2026-09-15.pdf` | Neel | AdamX Inc. | 2026-09-15 | 15,000.00 | 2,569.50 | 1,172.44 | 65,000.00 | 9,015.18 | 4,198.28 | ingested 2026-09-12 |
| _(Jaya DeWinter stubs, Jun–Sep 2026)_ | Jaya | DeWinter | — | | | | | | | **awaiting** — $150K/yr per projection; no withholding known |

Neel's stubs show $0 of 401(k), benefits, or post-tax deductions; SS 930 / Medicare 217.50 / CA SDI 195 per period at the $360K rate.

## Income — 1099 (Brokerage / Retirement)

| File | Recipient | Issuer | Form | Received | Status | Notes |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

## Schedule K-1 (Partnership / PTP)

| File | Recipient | Issuer | Account | Received | Status | Notes |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

## Rental Real Estate (Schedule E)

| File | Property | Received | Status | Notes |
|---|---|---|---|---|
| _(none yet)_ | | | | |

## Estimated tax payments (recorded in `estimated_tax_payments`)

| Date | Agency | Quarter | Amount | Confirmation | Notes |
|---|---|---|---:|---|---|
| 2026-05-01 | IRS | Q1 | 1,700.00 | — | IRS Direct Pay |
| 2026-05-01 | CA FTB | Q1 | 550.00 | — | FTB Web Pay |
| 2026-09-14 | IRS | Q3 | 10,000.00 | EFT 240665811453052 | IRS Direct Pay, submitted 1:53 PM EDT; screenshot of the status page was shown, not filed (temp file expired) |
| 2026-09-14 | CA FTB | Q3 | 5,000.00 | pending | FTB Web Pay scheduled 09/14/2026; Payment Summary showed it Pending (5 business days to post); screenshot shown, not filed |

## Other

| File | Topic | Received | Status | Notes |
|---|---|---|---|---|
| _(none yet)_ | | | | |

---

## Open items / awaiting

- [ ] Neel's June 2026 AdamX paystubs (06/15, 06/30) — PDFs
- [ ] Jaya's DeWinter paystubs (June 2026 onward)
- [ ] Robinhood 2026 activity CSVs for both brokerage accounts — no dividend (CDIV) or interest (INT) rows exist for 2026 yet
- [ ] All W-2s (Neel + Jaya, ~late January 2027)
- [ ] All 1099s from brokerages (~mid February 2027)
- [ ] K-1s from partnerships (~March–September 2027)
- [ ] Mortgage 1098s
- [ ] Property tax records
- [ ] Estimated tax payment records (federal + CA)
- [ ] Charitable contribution receipts
- [ ] Any major life events (vehicle purchases, property sales, etc.)

## Income — Nonemployee compensation (1099-NEC)

**MapUp Inc. option cash-out.** MapUp was acquired by Bestpass, Inc. (Project Compass). Neel's 112,500 unexercised advisor NSOs (granted 2025-05-11 at $0.71 under the 2023-05-04 advisor agreement, independent contractor) were cancelled at closing for cash. Shares were never issued → ordinary nonemployee compensation, Schedule C + Schedule SE; **not** a capital gain, no QSBS. A pro rata earnout (SPA §2.06) is still contingent.

| File | Recipient | Issuer | Date | Amount | Status | Notes |
|---|---|---|---|---:|---|---|
| `mapup/2023-05-04 MapUp Advisor Agreement (Neel Kamal).pdf` | Neel | MapUp Inc. | 2023-05-04 | — | received | §7: advisor pays self-employment taxes |
| `mapup/2026-09-29 MapUp Option Cancellation Agreement (Neel Kamal).pdf` | Neel | MapUp Inc. | 2026-09-29 | — | received | Exhibit A: 112,500 options @ $0.71; closing + earnout consideration |
| _(bank wire)_ | Neel | TOLLPASS LLC (Bestpass) | 2026-10-02 | 249,062.27 | received | Savings ...7358; = 112,500 × ($2.9239 − $0.71). In `spending_transactions`; rule "MapUp option cash-out" |
| _(Form 1099-NEC, Bestpass/TOLLPASS)_ | Neel | Bestpass / TOLLPASS LLC | — | awaiting | Expected Jan 2027; must show 249,062.27 (plus any earnout paid in 2026) |
| _(earnout payments)_ | Neel | TOLLPASS LLC | — | awaiting | Contingent; each one is more 1099-NEC income in the year paid |

**Estimated-tax note.** No tax was withheld on the wire. Q4 2026 estimate is due 2027-01-15; the Tax page's 2026 forecast carries the SE tax and the ordinary-income effect.
