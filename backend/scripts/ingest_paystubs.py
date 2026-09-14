#!/usr/bin/env python
"""Ingest paystub PDFs into salary_payslips (upsert on person + pay_date + period_start).

Usage:
    PYTHONPATH=. venv/bin/python scripts/ingest_paystubs.py <pdf-or-directory> [...]

Each stub is validated against its own printed totals before anything is
written; a stub that fails validation is reported and skipped. Rows that
already exist (e.g. gross-only rows entered from a screen) are updated in
place with the stub's withholding and YTD figures.
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import SessionLocal  # noqa: E402
from app.modules.income.paystub_parser import parse_paystub_pdf, PaystubValidationError  # noqa: E402

UPSERT = text("""
INSERT INTO salary_payslips (person, employer, pay_date, period_start, period_end, gross, net, source,
    annual_rate, federal_withheld, state_withheld, social_security, medicare, sdi, retirement_401k,
    benefits_pretax, post_tax_deductions, gross_ytd, net_ytd, federal_withheld_ytd, state_withheld_ytd,
    social_security_ytd, medicare_ytd, sdi_ytd, retirement_401k_ytd, benefits_pretax_ytd, source_file)
VALUES (:person, :employer, :pay_date, :period_start, :period_end, :gross, :net, :source,
    :annual_rate, :federal_withheld, :state_withheld, :social_security, :medicare, :sdi, :retirement_401k,
    :benefits_pretax, :post_tax_deductions, :gross_ytd, :net_ytd, :federal_withheld_ytd, :state_withheld_ytd,
    :social_security_ytd, :medicare_ytd, :sdi_ytd, :retirement_401k_ytd, :benefits_pretax_ytd, :source_file)
ON CONFLICT ON CONSTRAINT uq_salary_payslip DO UPDATE SET
    employer = EXCLUDED.employer, period_end = EXCLUDED.period_end, gross = EXCLUDED.gross,
    net = EXCLUDED.net, source = EXCLUDED.source, annual_rate = EXCLUDED.annual_rate,
    federal_withheld = EXCLUDED.federal_withheld, state_withheld = EXCLUDED.state_withheld,
    social_security = EXCLUDED.social_security, medicare = EXCLUDED.medicare, sdi = EXCLUDED.sdi,
    retirement_401k = EXCLUDED.retirement_401k, benefits_pretax = EXCLUDED.benefits_pretax,
    post_tax_deductions = EXCLUDED.post_tax_deductions, gross_ytd = EXCLUDED.gross_ytd,
    net_ytd = EXCLUDED.net_ytd, federal_withheld_ytd = EXCLUDED.federal_withheld_ytd,
    state_withheld_ytd = EXCLUDED.state_withheld_ytd, social_security_ytd = EXCLUDED.social_security_ytd,
    medicare_ytd = EXCLUDED.medicare_ytd, sdi_ytd = EXCLUDED.sdi_ytd,
    retirement_401k_ytd = EXCLUDED.retirement_401k_ytd, benefits_pretax_ytd = EXCLUDED.benefits_pretax_ytd,
    source_file = EXCLUDED.source_file, updated_at = now()
""")


def collect(paths):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            yield from sorted(p.glob("*.pdf"))
        elif p.suffix.lower() == ".pdf":
            yield p


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    db = SessionLocal()
    ok = skipped = 0
    try:
        for pdf in collect(argv):
            try:
                facts = parse_paystub_pdf(pdf)
            except PaystubValidationError as e:
                print(f"SKIP  {e}")
                skipped += 1
                continue
            row = facts.to_row()
            row["source"] = f"paystub PDF {facts.source_file}"
            db.execute(UPSERT, row)
            ok += 1
            print(f"OK    {facts.person} {facts.employer} pay {facts.pay_date} "
                  f"gross {facts.gross:,.2f} fed {facts.federal_withheld:,.2f} ca {facts.state_withheld:,.2f} "
                  f"| YTD gross {facts.gross_ytd:,.2f} fed {facts.federal_withheld_ytd:,.2f} ca {facts.state_withheld_ytd:,.2f}"
                  + (f"  ({'; '.join(facts.warnings)})" if facts.warnings else ""))
        db.commit()
    finally:
        db.close()
    print(f"{ok} ingested, {skipped} skipped")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
