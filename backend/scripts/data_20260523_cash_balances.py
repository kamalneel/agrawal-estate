"""Update account cash balances as of 2026-05-23.

Values from Robinhood buying power screenshots after May 22 put assignments.
Storing gross cash (before options collateral) — collateral is tracked separately
via the SoldOption table.
"""
from datetime import datetime
from sqlalchemy.orm import Session


def run(db: Session):
    from app.modules.strategies.models import AccountCashBalance

    balances = {
        "Neel's Brokerage":  10417.42,   # Cash line (margin $200K separate)
        "Neel's Retirement": 394009.19,  # Traditional IRA cash
        "Jaya's Brokerage":   3084.42,   # Cash line (margin $150K separate)
        "Jaya's IRA":        209558.27,  # Traditional IRA cash
        "Jaya's Roth IRA":    28850.11,  # Roth IRA cash
    }

    for account_name, cash_balance in balances.items():
        record = db.query(AccountCashBalance).filter(
            AccountCashBalance.account_name == account_name
        ).first()
        if record:
            record.cash_balance = cash_balance
            record.updated_at = datetime.utcnow()
        else:
            db.add(AccountCashBalance(
                account_name=account_name,
                cash_balance=cash_balance,
                notes="Set from Robinhood buying power screenshot 2026-05-23",
            ))

    db.commit()
    print("Cash balances updated:")
    for name, bal in balances.items():
        print(f"  {name}: ${bal:,.2f}")
    print(f"  Total: ${sum(balances.values()):,.2f}")


if __name__ == "__main__":
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        run(db)
    finally:
        db.close()
