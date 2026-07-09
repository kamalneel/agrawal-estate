"""
Cost Basis Tracking Service

Handles all logic for stock lot tracking, gain/loss calculations,
and lot matching (FIFO, LIFO, specific ID).
"""

from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, extract, func

from app.modules.tax.models import StockLot, StockLotSale


class CostBasisService:
    """Service for managing cost basis tracking and capital gains calculations."""

    def __init__(self, db: Session):
        self.db = db

    # ===== Lot Management =====

    def create_lot(
        self,
        symbol: str,
        purchase_date: date,
        quantity: Decimal,
        cost_basis: Decimal,
        source: str,
        account_id: Optional[str] = None,
        purchase_transaction_id: Optional[int] = None,
        lot_method: str = "FIFO",
        notes: Optional[str] = None
    ) -> StockLot:
        """
        Create a new stock lot.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            purchase_date: Date shares were purchased
            quantity: Number of shares purchased
            cost_basis: Total cost basis (including fees)
            source: Source of data ('robinhood', 'etrade', 'manual')
            account_id: Account identifier
            purchase_transaction_id: Link to original transaction
            lot_method: Default lot matching method
            notes: Additional notes

        Returns:
            Created StockLot instance
        """
        cost_per_share = cost_basis / quantity if quantity > 0 else Decimal(0)

        lot = StockLot(
            symbol=symbol.upper(),
            purchase_date=purchase_date,
            quantity=quantity,
            cost_basis=cost_basis,
            cost_per_share=cost_per_share,
            account_id=account_id,
            source=source,
            purchase_transaction_id=purchase_transaction_id,
            quantity_remaining=quantity,
            status='open',
            lot_method=lot_method,
            notes=notes
        )

        self.db.add(lot)
        self.db.commit()
        self.db.refresh(lot)

        return lot

    def get_open_lots(
        self,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> List[StockLot]:
        """
        Get all open lots (partially or fully available for sale).

        Args:
            symbol: Filter by symbol
            source: Filter by source
            account_id: Filter by account

        Returns:
            List of open StockLot instances
        """
        query = self.db.query(StockLot).filter(
            StockLot.quantity_remaining > 0
        )

        if symbol:
            query = query.filter(StockLot.symbol == symbol.upper())
        if source:
            query = query.filter(StockLot.source == source)
        if account_id:
            query = query.filter(StockLot.account_id == account_id)

        # Order by purchase date (FIFO default)
        return query.order_by(StockLot.purchase_date.asc()).all()

    def get_closed_lots(
        self,
        symbol: Optional[str] = None,
        year: Optional[int] = None
    ) -> List[StockLot]:
        """Get all closed lots (fully sold)."""
        query = self.db.query(StockLot).filter(
            StockLot.quantity_remaining == 0,
            StockLot.status == 'closed'
        )

        if symbol:
            query = query.filter(StockLot.symbol == symbol.upper())

        return query.order_by(StockLot.purchase_date.desc()).all()

    # ===== Sale Processing =====

    def process_sale(
        self,
        symbol: str,
        sale_date: date,
        quantity_sold: Decimal,
        proceeds: Decimal,
        source: Optional[str] = None,
        account_id: Optional[str] = None,
        sale_transaction_id: Optional[int] = None,
        lot_method: str = "FIFO",
        notes: Optional[str] = None
    ) -> List[StockLotSale]:
        """
        Process a stock sale by matching to lots.

        Args:
            symbol: Stock symbol
            sale_date: Date of sale
            quantity_sold: Number of shares sold
            proceeds: Total proceeds from sale (after fees)
            source: Data source
            account_id: Account identifier
            sale_transaction_id: Link to original transaction
            lot_method: 'FIFO', 'LIFO', or 'specific_id'
            notes: Additional notes

        Returns:
            List of created StockLotSale instances
        """
        # Get available lots
        lots = self.get_open_lots(symbol=symbol, source=source, account_id=account_id)

        if lot_method == "LIFO":
            lots = sorted(lots, key=lambda x: x.purchase_date, reverse=True)

        if not lots:
            raise ValueError(f"No open lots available for {symbol}")

        # Calculate proceeds per share
        proceeds_per_share = proceeds / quantity_sold if quantity_sold > 0 else Decimal(0)

        # Match sale to lots
        remaining_to_sell = quantity_sold
        sales = []
        tax_year = sale_date.year

        for lot in lots:
            if remaining_to_sell <= 0:
                break

            # Determine how much to sell from this lot
            quantity_from_lot = min(remaining_to_sell, lot.quantity_remaining)

            # Calculate cost basis for this portion
            cost_basis_portion = lot.cost_per_share * quantity_from_lot
            proceeds_portion = proceeds_per_share * quantity_from_lot

            # Calculate gain/loss
            gain_loss = proceeds_portion - cost_basis_portion

            # Calculate holding period
            holding_period_days = (sale_date - lot.purchase_date).days
            is_long_term = holding_period_days > 365

            # Create sale record
            sale = StockLotSale(
                lot_id=lot.lot_id,
                sale_date=sale_date,
                sale_transaction_id=sale_transaction_id,
                quantity_sold=quantity_from_lot,
                proceeds=proceeds_portion,
                proceeds_per_share=proceeds_per_share,
                cost_basis=cost_basis_portion,
                gain_loss=gain_loss,
                holding_period_days=holding_period_days,
                is_long_term=is_long_term,
                tax_year=tax_year,
                wash_sale=False,  # TODO: Implement wash sale detection
                notes=notes
            )

            self.db.add(sale)
            sales.append(sale)

            # Update lot
            lot.quantity_remaining -= quantity_from_lot
            if lot.quantity_remaining == 0:
                lot.status = 'closed'
            elif lot.quantity_remaining < lot.quantity:
                lot.status = 'partial'

            remaining_to_sell -= quantity_from_lot

        if remaining_to_sell > 0:
            raise ValueError(
                f"Insufficient shares to sell. Needed {quantity_sold}, "
                f"but only {quantity_sold - remaining_to_sell} available in lots."
            )

        self.db.commit()

        return sales

    # ===== Capital Gains Reporting =====

    def get_realized_gains(
        self,
        year: int,
        symbol: Optional[str] = None,
        is_long_term: Optional[bool] = None
    ) -> List[StockLotSale]:
        """
        Get all realized capital gains for a tax year.

        Args:
            year: Tax year
            symbol: Filter by symbol
            is_long_term: Filter by long-term (True) or short-term (False)

        Returns:
            List of StockLotSale instances
        """
        query = self.db.query(StockLotSale).join(StockLot).filter(
            StockLotSale.tax_year == year
        )

        if symbol:
            query = query.filter(StockLot.symbol == symbol.upper())

        if is_long_term is not None:
            query = query.filter(StockLotSale.is_long_term == is_long_term)

        return query.order_by(StockLotSale.sale_date).all()

    def get_capital_gains_summary(self, year: int) -> Dict:
        """
        Get capital gains summary for a tax year.

        Returns dict with:
        - total_short_term_gain
        - total_long_term_gain
        - total_gain
        - total_proceeds
        - total_cost_basis
        - num_transactions
        - by_symbol breakdown
        """
        sales = self.get_realized_gains(year)

        short_term_gain = Decimal(0)
        long_term_gain = Decimal(0)
        total_proceeds = Decimal(0)
        total_cost_basis = Decimal(0)

        by_symbol = {}

        for sale in sales:
            lot = self.db.query(StockLot).filter(StockLot.lot_id == sale.lot_id).first()
            symbol = lot.symbol if lot else "UNKNOWN"

            if sale.is_long_term:
                long_term_gain += Decimal(str(sale.gain_loss))
            else:
                short_term_gain += Decimal(str(sale.gain_loss))

            total_proceeds += Decimal(str(sale.proceeds))
            total_cost_basis += Decimal(str(sale.cost_basis))

            # By symbol breakdown
            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "short_term_gain": Decimal(0),
                    "long_term_gain": Decimal(0),
                    "total_gain": Decimal(0),
                    "proceeds": Decimal(0),
                    "cost_basis": Decimal(0),
                    "num_sales": 0
                }

            if sale.is_long_term:
                by_symbol[symbol]["long_term_gain"] += Decimal(str(sale.gain_loss))
            else:
                by_symbol[symbol]["short_term_gain"] += Decimal(str(sale.gain_loss))

            by_symbol[symbol]["total_gain"] += Decimal(str(sale.gain_loss))
            by_symbol[symbol]["proceeds"] += Decimal(str(sale.proceeds))
            by_symbol[symbol]["cost_basis"] += Decimal(str(sale.cost_basis))
            by_symbol[symbol]["num_sales"] += 1

        return {
            "tax_year": year,
            "total_short_term_gain": float(short_term_gain),
            "total_long_term_gain": float(long_term_gain),
            "total_gain": float(short_term_gain + long_term_gain),
            "total_proceeds": float(total_proceeds),
            "total_cost_basis": float(total_cost_basis),
            "num_transactions": len(sales),
            "by_symbol": {
                symbol: {
                    "short_term_gain": float(data["short_term_gain"]),
                    "long_term_gain": float(data["long_term_gain"]),
                    "total_gain": float(data["total_gain"]),
                    "proceeds": float(data["proceeds"]),
                    "cost_basis": float(data["cost_basis"]),
                    "num_sales": data["num_sales"]
                }
                for symbol, data in by_symbol.items()
            }
        }

    # ===== Unrealized Gains =====

    def get_unrealized_gains(
        self,
        current_prices: Dict[str, Decimal],
        symbol: Optional[str] = None
    ) -> Dict:
        """
        Calculate unrealized gains for open positions.

        Args:
            current_prices: Dict of {symbol: current_price}
            symbol: Filter by symbol

        Returns:
            Dict with unrealized gain/loss information
        """
        lots = self.get_open_lots(symbol=symbol)

        total_unrealized = Decimal(0)
        total_market_value = Decimal(0)
        total_cost_basis = Decimal(0)

        by_symbol = {}

        for lot in lots:
            if lot.quantity_remaining <= 0:
                continue

            current_price = current_prices.get(lot.symbol, Decimal(0))
            market_value = current_price * lot.quantity_remaining
            cost_basis = lot.cost_per_share * lot.quantity_remaining
            unrealized_gain = market_value - cost_basis

            total_unrealized += unrealized_gain
            total_market_value += market_value
            total_cost_basis += cost_basis

            if lot.symbol not in by_symbol:
                by_symbol[lot.symbol] = {
                    "quantity": Decimal(0),
                    "cost_basis": Decimal(0),
                    "market_value": Decimal(0),
                    "unrealized_gain": Decimal(0),
                    "num_lots": 0
                }

            by_symbol[lot.symbol]["quantity"] += lot.quantity_remaining
            by_symbol[lot.symbol]["cost_basis"] += cost_basis
            by_symbol[lot.symbol]["market_value"] += market_value
            by_symbol[lot.symbol]["unrealized_gain"] += unrealized_gain
            by_symbol[lot.symbol]["num_lots"] += 1

        return {
            "total_unrealized_gain": float(total_unrealized),
            "total_market_value": float(total_market_value),
            "total_cost_basis": float(total_cost_basis),
            "by_symbol": {
                symbol: {
                    "quantity": float(data["quantity"]),
                    "cost_basis": float(data["cost_basis"]),
                    "market_value": float(data["market_value"]),
                    "unrealized_gain": float(data["unrealized_gain"]),
                    "unrealized_gain_pct": float(
                        (data["unrealized_gain"] / data["cost_basis"] * 100)
                        if data["cost_basis"] > 0 else 0
                    ),
                    "num_lots": data["num_lots"]
                }
                for symbol, data in by_symbol.items()
            }
        }

    # ===== Import/Export =====

    def import_robinhood_transactions(
        self,
        transactions: List[Dict],
        account_id: str = "robinhood_main"
    ) -> Tuple[int, int]:
        """
        Import Robinhood transactions and create lots/sales.

        Args:
            transactions: List of transaction dicts with keys:
                - symbol, date, type, quantity, price, amount
            account_id: Account identifier

        Returns:
            Tuple of (lots_created, sales_created)
        """
        lots_created = 0
        sales_created = 0

        for txn in transactions:
            symbol = txn["symbol"]
            txn_date = txn["date"]
            txn_type = txn["type"].upper()
            quantity = Decimal(str(txn["quantity"]))
            amount = abs(Decimal(str(txn["amount"])))

            if txn_type in ["BUY", "BOUGHT"]:
                # Create lot
                self.create_lot(
                    symbol=symbol,
                    purchase_date=txn_date,
                    quantity=quantity,
                    cost_basis=amount,
                    source="robinhood",
                    account_id=account_id,
                    lot_method="FIFO"
                )
                lots_created += 1

            elif txn_type in ["SELL", "SOLD"]:
                # Process sale
                sales = self.process_sale(
                    symbol=symbol,
                    sale_date=txn_date,
                    quantity_sold=quantity,
                    proceeds=amount,
                    source="robinhood",
                    account_id=account_id,
                    lot_method="FIFO"
                )
                sales_created += len(sales)

        return (lots_created, sales_created)


# ===== Realized P/L by period (income unification Phase 2) =====

# Friday-ending weeks (Sat-Fri), per docs/INCOME-UNIFICATION-SPEC.md.
_PERIOD_EXPR = {
    "week": "(s.sale_date + ((5 - EXTRACT(DOW FROM s.sale_date)::int + 7) % 7)"
            " * INTERVAL '1 day')::date",
    "month": "date_trunc('month', s.sale_date)::date",
    "year": "date_trunc('year', s.sale_date)::date",
}


def get_realized_pnl_by_period(
    db: Session,
    granularity: str = "month",
    account_id: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    taxable_only: bool = False,
) -> List[Dict]:
    """Realized stock-sale P/L aggregated by period across ALL accounts
    (retirement included — income is tax-independent; see the
    definition-of-income playbook rule). Rows still flagged BASIS_UNKNOWN
    are excluded from P/L and reported via unresolved_count/proceeds.
    """
    from sqlalchemy import text as _text

    if granularity not in _PERIOD_EXPR:
        raise ValueError(f"granularity must be one of {list(_PERIOD_EXPR)}")
    where, params = [], {}
    if account_id:
        where.append("l.account_id = :acct")
        params["acct"] = account_id
    if start:
        where.append("s.sale_date >= :start")
        params["start"] = start
    if end:
        where.append("s.sale_date <= :end")
        params["end"] = end
    if taxable_only:
        where.append("""l.account_id IN (
            SELECT account_id FROM investment_accounts
            WHERE account_type NOT IN ('ira', 'roth_ira', 'traditional_ira',
                                       '401k', 'hsa', 'retirement'))""")
    where_sql = ("AND " + " AND ".join(where)) if where else ""

    rows = db.execute(_text(f"""
        SELECT {_PERIOD_EXPR[granularity]} AS period,
               l.account_id,
               COALESCE(SUM(s.gain_loss) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN'), 0) AS realized_pnl,
               COALESCE(SUM(s.proceeds) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN'), 0) AS proceeds,
               COALESCE(SUM(s.cost_basis) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN'), 0) AS cost_basis,
               COUNT(*) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN') AS sales_count,
               COUNT(*) FILTER (WHERE s.notes = 'BASIS_UNKNOWN') AS unresolved_count,
               COALESCE(SUM(s.proceeds) FILTER (WHERE s.notes = 'BASIS_UNKNOWN'), 0) AS unresolved_proceeds
        FROM stock_lot_sale s
        JOIN stock_lot l ON l.lot_id = s.lot_id
        WHERE TRUE {where_sql}
        GROUP BY 1, 2 ORDER BY 1, 2
    """), params).fetchall()

    return [{
        "period": str(r.period), "account_id": r.account_id,
        "realized_pnl": float(r.realized_pnl), "proceeds": float(r.proceeds),
        "cost_basis": float(r.cost_basis), "sales_count": r.sales_count,
        "unresolved_count": r.unresolved_count,
        "unresolved_proceeds": float(r.unresolved_proceeds),
    } for r in rows]


# ===== Pure investment performance (Investments page) =====
# See docs/INVESTMENTS-PAGE-SPEC.md. Value − cost basis is structurally
# independent of income (premium/dividends never touch cost basis) — this
# is exact, not an approximation that backs cash flows out of a series.
# Assignment lots use strike-price basis as-is (definition-of-income rule).

def get_pure_performance(db: Session) -> Dict:
    """Current holdings vs. cost basis (open + closed, symbol-aggregated
    across accounts), plus a value-vs-invested-capital time series."""
    from sqlalchemy import text as _text

    open_rows = db.execute(_text("""
        SELECT l.symbol, l.quantity_remaining, l.cost_per_share, h.current_price
        FROM stock_lot l
        LEFT JOIN investment_holdings h
          ON h.source = l.source AND h.account_id = l.account_id AND h.symbol = l.symbol
        WHERE l.quantity_remaining > 0
    """)).fetchall()

    by_symbol: Dict[str, Dict] = {}
    for r in open_rows:
        qty = float(r.quantity_remaining)
        d = by_symbol.setdefault(r.symbol, {"shares": 0.0, "cost_basis": 0.0, "value": 0.0, "priced": True})
        d["shares"] += qty
        d["cost_basis"] += qty * float(r.cost_per_share)
        if r.current_price is None:
            d["priced"] = False
        else:
            d["value"] += qty * float(r.current_price)

    priced_value = sum(d["value"] for d in by_symbol.values() if d["priced"])
    priced_cost_basis = sum(d["cost_basis"] for d in by_symbol.values() if d["priced"])
    unpriced_cost_basis = sum(d["cost_basis"] for d in by_symbol.values() if not d["priced"])
    unpriced_count = sum(1 for d in by_symbol.values() if not d["priced"])

    open_positions = []
    for sym, d in by_symbol.items():
        gain = (d["value"] - d["cost_basis"]) if d["priced"] else None
        gain_pct = round(gain / d["cost_basis"] * 100, 2) if (gain is not None and d["cost_basis"]) else None
        open_positions.append({
            "symbol": sym, "status": "open", "shares": round(d["shares"], 4),
            "cost_basis": round(d["cost_basis"], 2),
            "value": round(d["value"], 2) if d["priced"] else None,
            "gain": round(gain, 2) if gain is not None else None,
            "gain_pct": gain_pct,
            "weight_pct": round(d["value"] / priced_value * 100, 2) if (d["priced"] and priced_value) else None,
        })
    open_positions.sort(key=lambda p: (p["gain_pct"] is None, -(p["gain_pct"] or 0)))

    closed_rows = db.execute(_text("""
        WITH totals AS (
            SELECT symbol, SUM(quantity_remaining) AS remaining FROM stock_lot GROUP BY symbol
        )
        SELECT l.symbol,
               SUM(s.proceeds) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN') AS proceeds,
               SUM(s.cost_basis) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN') AS cost_basis,
               SUM(s.gain_loss) FILTER (WHERE s.notes IS DISTINCT FROM 'BASIS_UNKNOWN') AS gain,
               MAX(s.sale_date) AS last_sale_date
        FROM stock_lot_sale s
        JOIN stock_lot l ON l.lot_id = s.lot_id
        JOIN totals t ON t.symbol = l.symbol AND t.remaining = 0
        GROUP BY l.symbol
    """)).fetchall()
    closed_positions = []
    for r in closed_rows:
        cb = float(r.cost_basis or 0)
        gain = float(r.gain or 0)
        closed_positions.append({
            "symbol": r.symbol, "status": "closed",
            "proceeds": round(float(r.proceeds or 0), 2), "cost_basis": round(cb, 2),
            "gain": round(gain, 2), "gain_pct": round(gain / cb * 100, 2) if cb else None,
            "closed_date": str(r.last_sale_date) if r.last_sale_date else None,
        })
    closed_positions.sort(key=lambda p: (p["gain_pct"] is None, -(p["gain_pct"] or 0)))

    # Value over time (investment_holdings_history) vs. capital invested
    # over time, reconstructed from each lot's purchase/sale timeline —
    # not a snapshot backed into the past, a real trajectory.
    hist_rows = db.execute(_text("""
        SELECT snapshot_date, SUM(market_value) AS value
        FROM investment_holdings_history GROUP BY snapshot_date ORDER BY snapshot_date
    """)).fetchall()
    lot_rows = db.execute(_text(
        "SELECT lot_id, purchase_date, quantity, cost_per_share FROM stock_lot")).fetchall()
    sale_rows = db.execute(_text(
        "SELECT lot_id, sale_date, quantity_sold FROM stock_lot_sale ORDER BY lot_id, sale_date")).fetchall()
    sales_by_lot: Dict[int, List[Tuple[date, float]]] = {}
    for r in sale_rows:
        sales_by_lot.setdefault(r.lot_id, []).append((r.sale_date, float(r.quantity_sold)))

    chart = []
    for hr in hist_rows:
        d = hr.snapshot_date
        invested = 0.0
        for lr in lot_rows:
            if lr.purchase_date > d:
                continue
            sold = sum(q for sd, q in sales_by_lot.get(lr.lot_id, []) if sd <= d)
            remaining = max(float(lr.quantity) - sold, 0.0)
            invested += remaining * float(lr.cost_per_share)
        chart.append({"date": str(d), "value": round(float(hr.value or 0), 2), "invested": round(invested, 2)})

    overall_gain = priced_value - priced_cost_basis
    return {
        "as_of": str(date.today()),
        "current_value": round(priced_value, 2),
        "cost_basis": round(priced_cost_basis, 2),
        "gain": round(overall_gain, 2),
        "gain_pct": round(overall_gain / priced_cost_basis * 100, 2) if priced_cost_basis else None,
        "unpriced_count": unpriced_count,
        "unpriced_cost_basis": round(unpriced_cost_basis, 2),
        "chart": chart,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
    }
