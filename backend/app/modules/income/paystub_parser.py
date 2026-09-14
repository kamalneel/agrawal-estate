"""Paystub parsers — dated, authoritative facts about pay and tax withheld.

A paystub is the only record of tax already paid for a year that has no W-2
yet. Each parser returns a `PaystubFacts` and must validate the stub against
its own printed totals (playbook: validate-parser-against-source-totals):
the current-period taxes must sum to the stub's "Employee taxes withheld",
and gross − taxes − pre-tax benefits − post-tax deductions must equal net.

Supported formats:
- AdamX Inc. (Gusto-style "Pay summary / Earnings statement"), Neel, 2026.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class PaystubFacts:
    person: str
    employer: str
    pay_date: date
    period_start: date
    period_end: date
    annual_rate: Optional[float]
    gross: float
    net: float
    federal_withheld: float
    state_withheld: float
    social_security: float
    medicare: float
    sdi: float
    retirement_401k: float
    benefits_pretax: float
    post_tax_deductions: float
    gross_ytd: float
    net_ytd: float
    federal_withheld_ytd: float
    state_withheld_ytd: float
    social_security_ytd: float
    medicare_ytd: float
    sdi_ytd: float
    retirement_401k_ytd: float
    benefits_pretax_ytd: float
    source_file: str
    warnings: list = field(default_factory=list)

    @property
    def taxes_current(self) -> float:
        return round(self.federal_withheld + self.state_withheld + self.social_security
                     + self.medicare + self.sdi, 2)

    @property
    def taxes_ytd(self) -> float:
        return round(self.federal_withheld_ytd + self.state_withheld_ytd + self.social_security_ytd
                     + self.medicare_ytd + self.sdi_ytd, 2)

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("warnings")
        return d


class PaystubValidationError(ValueError):
    """The stub's own printed totals do not agree with the rows we extracted."""


_MONEY = r"\$?(-?[\d,]+\.\d{2})"


def _money(s: Optional[str]) -> float:
    if s is None:
        return 0.0
    return float(s.replace("$", "").replace(",", ""))


def _mdy(s: str) -> date:
    s = s.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unparseable date {s!r}")


def _pair(text: str, label: str) -> tuple[float, float]:
    """`<label> $current $ytd` → (current, ytd); (0, 0) when the line is absent."""
    m = re.search(rf"{re.escape(label)}\s+{_MONEY}\s+{_MONEY}", text)
    if not m:
        return 0.0, 0.0
    return _money(m.group(1)), _money(m.group(2))


def _block(text: str, heading: str) -> tuple[float, float]:
    """Gusto summary blocks: `<heading>\n$current\nYTD $ytd`."""
    m = re.search(rf"{re.escape(heading)}\s*\n\s*{_MONEY}\s*\n\s*YTD\s+{_MONEY}", text)
    if not m:
        return 0.0, 0.0
    return _money(m.group(1)), _money(m.group(2))


def normalize_person(name: str) -> str:
    n = name.lower()
    if "neel" in n:
        return "Neel"
    if "jaya" in n:
        return "Jaya"
    return name.strip().title()


def can_parse_adamx(text: str) -> bool:
    return "Earnings statement" in text and "AdamX" in text


def parse_adamx_paystub_text(text: str, source_file: str = "") -> PaystubFacts:
    """Parse the text of one AdamX (Gusto-format) stub. Raises on validation failure."""
    period = re.search(r"Pay period:\s*(\d{2}/\d{2}/\d{2,4})\s*-\s*(\d{2}/\d{2}/\d{2,4})", text)
    pay_date = re.search(r"Pay date:\s*(\d{2}/\d{2}/\d{2,4})", text)
    if not (period and pay_date):
        raise PaystubValidationError(f"{source_file}: no pay period / pay date found")

    name = re.search(r"\n\d{10}\s+([A-Z][A-Za-z]+ [A-Z][A-Za-z]+)\n", text)
    person = normalize_person(name.group(1)) if name else "Unknown"
    employer = re.search(r"\n([A-Za-z0-9 .&]+?(?:Inc\.|LLC|Corp\.?|Ltd\.?))\s", text)
    employer_name = employer.group(1).strip() if employer else "AdamX Inc."

    rate = re.search(r"Salaried\s+\$([\d,]+)\s+Salary", text)
    annual_rate = float(rate.group(1).replace(",", "")) if rate else None

    gross_line = re.search(rf"Salaried Total\s+[\d.]+\s+{_MONEY}\s+[\d.]+\s+{_MONEY}", text)
    if gross_line:
        gross, gross_ytd = _money(gross_line.group(1)), _money(gross_line.group(2))
    else:
        gross, gross_ytd = _block(text, "Gross earnings")

    fed = _pair(text, "Federal Income Tax")
    ss = _pair(text, "Social Security Tax")
    med = _pair(text, "Medicare")
    sdi = _pair(text, "California SDI")
    ca = _pair(text, "California State Tax")
    k401 = _pair(text, "401(k)")

    taxes_block = _block(text, "Employee taxes withheld")
    benefits_block = _block(text, "Employee benefits contributions")
    posttax_block = _block(text, "Post-tax deductions")

    net_m = re.search(r"Net pay\s*\n(?:.*\n)*?\s*\$?([\d,]+\.\d{2})\s*\n", text)
    net = _money(net_m.group(1)) if net_m else 0.0
    net_ytd_m = re.search(r"YTD\s+\$?([\d,]+\.\d{2})\s*\n\s*Medicare", text)
    net_ytd = _money(net_ytd_m.group(1)) if net_ytd_m else 0.0

    facts = PaystubFacts(
        person=person, employer=employer_name,
        pay_date=_mdy(pay_date.group(1)),
        period_start=_mdy(period.group(1)), period_end=_mdy(period.group(2)),
        annual_rate=annual_rate, gross=gross, net=net,
        federal_withheld=fed[0], state_withheld=ca[0], social_security=ss[0],
        medicare=med[0], sdi=sdi[0], retirement_401k=k401[0],
        benefits_pretax=benefits_block[0], post_tax_deductions=posttax_block[0],
        gross_ytd=gross_ytd, net_ytd=net_ytd,
        federal_withheld_ytd=fed[1], state_withheld_ytd=ca[1], social_security_ytd=ss[1],
        medicare_ytd=med[1], sdi_ytd=sdi[1], retirement_401k_ytd=k401[1],
        benefits_pretax_ytd=benefits_block[1],
        source_file=source_file,
    )

    # --- validate against the stub's own totals ---
    problems = []
    if taxes_block[0] and abs(facts.taxes_current - taxes_block[0]) > 0.01:
        problems.append(f"current taxes {facts.taxes_current} != printed {taxes_block[0]}")
    if taxes_block[1] and abs(facts.taxes_ytd - taxes_block[1]) > 0.01:
        problems.append(f"YTD taxes {facts.taxes_ytd} != printed {taxes_block[1]}")
    derived_net = round(gross - facts.taxes_current - facts.benefits_pretax - facts.post_tax_deductions, 2)
    if net and abs(derived_net - net) > 0.01:
        problems.append(f"gross-taxes-deductions {derived_net} != net {net}")
    if gross <= 0:
        problems.append("gross not found")
    if problems:
        raise PaystubValidationError(f"{source_file}: " + "; ".join(problems))
    if not net:
        facts.net = derived_net
        facts.warnings.append("net derived, not printed")
    return facts


def parse_paystub_pdf(path: Path) -> PaystubFacts:
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    if can_parse_adamx(text):
        return parse_adamx_paystub_text(text, source_file=path.name)
    raise PaystubValidationError(f"{path.name}: unrecognised paystub format")
