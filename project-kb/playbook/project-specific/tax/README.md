# How We Do Taxes — Annual Cycle

The tax module forecasts the household return (MFJ, California) all year and is graded once against the filed return. This folder holds the rules learned from those gradings. Universal rules that came out of tax work live under `playbook/universal/` and are linked below.

## The cycle

| When | What | Rule |
|---|---|---|
| All year | Forecast from transaction data; every source filtered to taxable accounts at the query | [filter-taxable-accounts-at-every-tax-source](../../universal/technical/filter-taxable-accounts-at-every-tax-source.md) |
| All year | Options premium: income now, tax when closed | [option-premium-is-taxed-when-the-position-closes](option-premium-is-taxed-when-the-position-closes.md) |
| All year | Watch MAGI cliffs, not just brackets | [magi-cliffs-drive-decisions](magi-cliffs-drive-decisions.md) |
| All year | Compute California separately | [california-is-its-own-computation](california-is-its-own-computation.md) |
| Sept / Jan | Estimated payments; use the annualized method when income is back-loaded | (in `docs/2025-TAX-RETURN-RECONCILIATION.md` §7) |
| Each pay date (open year) | Drop paystub PDFs into `data/tax-documents/<year>/paystubs/`, run `backend/scripts/ingest_paystubs.py`; the forecast reads the latest YTD row per person as tax already paid | (validated against the stub's own totals) |
| Jan–Feb | Drop W-2s, 1099s, 1099-Rs, K-1s into `data/tax-documents/<year>/`, update `INVENTORY.md` | [gross-1099-r-is-not-income](gross-1099-r-is-not-income.md) |
| Feb | Send the CPA package | `INVENTORY.md` "CPA package" section |
| After filing | Reconcile forecast to the filed return line by line, classify every gap | [reconcile-forecast-to-the-filed-return](../../universal/process/reconcile-forecast-to-the-filed-return.md) |
| After filing | Compare like for like: return total tax excludes payroll taxes | [total-tax-means-the-return-total](total-tax-means-the-return-total.md) |

## Gradings so far

- TY2025: `docs/2025-TAX-RETURN-RECONCILIATION.md` — 54% miss, 94% of it one query leaking IRA sales; February's 1099-based grading (`docs/2025-TAX-FORECAST-VS-ACTUAL.md`) had measured 5.2% before that regression. After the fixes the same code lands at +3.7%.
- TY2026 (in progress): `docs/2026-TAX-ESTIMATE.md` — tax paid to date from paystubs, income-to-date liability, full-year scenarios, safe-harbor schedule.
