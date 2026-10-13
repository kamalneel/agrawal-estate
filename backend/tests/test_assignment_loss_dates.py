"""Assignment loss is priced on the day the assignment happened — never
after the contract's expiry (Neel, 2026-10-12: the CBRS $165 put expiring
Fri 10/9 was recorded Sun 10/11 by the MCP sync and priced at Monday's
$146.62, a $1,838 "loss" for a real $87)."""
from datetime import date

from app.modules.strategies.assignment_loss_service import assignment_date


def test_late_recorded_assignment_snaps_to_expiry():
    assert assignment_date(date(2026, 10, 11), "CBRS 10/9/2026 Put $165.00") == date(2026, 10, 9)


def test_early_assignment_keeps_its_own_date():
    assert assignment_date(date(2026, 10, 7), "INTC 10/16/2026 Put $105.00") == date(2026, 10, 7)


def test_expiry_day_assignment_unchanged():
    assert assignment_date(date(2026, 10, 9), "CBRS 10/9/2026 Put $165.00") == date(2026, 10, 9)


def test_unparseable_description_falls_back_to_recorded_date():
    assert assignment_date(date(2026, 10, 11), "CBRS assignment") == date(2026, 10, 11)
