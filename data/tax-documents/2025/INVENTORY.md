# Tax Year 2025 — Document Inventory

**Tax year:** 2025 (filing due April 15, 2026; if extended, October 15, 2026)
**Filers:** Neel Kamal & Jaya Agrawal (MFJ)
**CPA package status:** Not yet assembled

This is the master tracking sheet for all tax-year-2025 paperwork. Update this file whenever a new document is dropped into `data/tax-documents/2025/`.

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
| `Jaya_Agrawal_W2_2025_Cisco_page1.heic` | Jaya | Cisco | 2026-02-03 | received | W-2 page 1 (HEIC photo) |
| `Jaya_Agrawal_W2_2025_Cisco_page2.heic` | Jaya | Cisco | 2026-02-03 | received | W-2 page 2 (HEIC photo) |
| _(Neel W-2)_ | Neel | _TBD_ | — | awaiting | Confirm whether Neel has W-2 income for TY2025 |

## Income — 1099 (Brokerage / Retirement)

| File | Recipient | Issuer | Form | Received | Status | Notes |
|---|---|---|---|---|---|---|
| `Neels_1099_Robinhood.pdf` | Neel | Robinhood | 1099 Consolidated | 2026-02-13 | received | B/DIV/INT consolidated |
| `Jayas_1099_Robinhood.pdf` | Jaya | Robinhood | 1099 Consolidated | 2026-02-13 | received | B/DIV/INT consolidated |
| `Neel_1099R_2025_Robinhood.pdf` | Neel | Robinhood | 1099-R | 2026-02-13 | received | Retirement distribution |
| `Jaya_1099R_2025_Robinhood.pdf` | Jaya | Robinhood | 1099-R | 2026-02-13 | received | Retirement distribution |

## Schedule K-1 (Partnership / PTP)

| File | Recipient | Issuer | Account | Received | Status | Notes |
|---|---|---|---|---|---|---|
| `Neel_K1_2025_ProShares_AGQ_CoverLetter.heic` | Neel | ProShares Ultra Silver (AGQ) | IRA/Sep/Keogh #98943427 | 2026-04-11 | received | Cover letter / online K-1 access info |
| `Neel_K1_2025_ProShares_AGQ_Form1065.heic` | Neel | ProShares Ultra Silver (AGQ) | IRA/Sep/Keogh #98943427 | 2026-04-11 | received | Schedule K-1 (Form 1065). Partnership EIN 26-2928729. **Held in IRA — informational only unless UBTI > $1,000 (Form 990-T filed by custodian, not on personal return).** Position is 1 share bought 12/29/2025, so UBTI is almost certainly de minimis. |
| `Neel_K1_2025_ProShares_AGQ_Supplemental.heic` | Neel | ProShares Ultra Silver (AGQ) | IRA/Sep/Keogh #98943427 | 2026-04-11 | received | K-1 supplemental info / box-by-box reporting instructions |
| `Neel_K1_2025_ProShares_AGQ_TransactionSchedule.heic` | Neel | ProShares Ultra Silver (AGQ) | IRA/Sep/Keogh #98943427 | 2026-04-11 | received | Transaction schedule: 1 share BUY on 12/29/2025, EOY shares = 1 |

## Rental Real Estate (Schedule E)

| File | Property | Received | Status | Notes |
|---|---|---|---|---|
| `Schedule_E_303_Hartstene_Dr_2025.txt` | 303 Hartstene Dr | 2026-02-13 | received | Working notes for Schedule E |
| _(Airbnb 1099-K)_ | Airbnb | — | awaiting | Check if threshold met for TY2025 |
| _(Property tax / mortgage interest 1098)_ | — | — | awaiting | Need 1098 from lender |

## Vehicles

| File | Topic | Received | Status | Notes |
|---|---|---|---|---|
| `New_Tesla_Purchase_2025.txt` | New Tesla purchase | 2026-02-13 | received | Possible EV credit / sales tax deduction — confirm with CPA |
| `Tesla_Model3_Sale_CarMax_Check.jpg` | Model 3 sale to CarMax | 2026-02-13 | received | Personal vehicle sale — typically nondeductible loss, but document for basis tracking |

## Prior-year reference

| File | Notes |
|---|---|
| `../2025 KAMAL, NEEL Tax Returns.pdf` | Prior-year return (TY2024 filed in 2025). Used for carryovers, AGI reference, estimated payments. |

---

## Open items / awaiting

- [ ] Confirm whether Neel has W-2 income for TY2025
- [ ] Mortgage 1098 for primary residence
- [ ] Mortgage 1098 / property tax for 303 Hartstene Dr
- [ ] Airbnb 1099-K (if issued)
- [ ] Any other K-1s from partnerships held outside IRA
- [ ] FanbaseAI dissolution-related tax docs (if any TY2025 events — see `memory/fanbase-dissolution-filings.md`)
- [ ] Estimated tax payment records for TY2025 (federal + CA)
- [ ] Charitable contribution receipts
- [ ] Childcare / dependent care receipts (if applicable)

## CPA package — when requested

When asked to "prepare CPA package," generate `data/tax-documents/2025/cpa-package/` containing:
1. PDF conversions of all HEIC photos (CPAs can't always open HEIC)
2. A cover sheet summarizing what's included and any open questions
3. This inventory as a manifest
