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
