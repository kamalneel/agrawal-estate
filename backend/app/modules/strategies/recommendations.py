"""
Strategy Recommendation System

Generates actionable recommendations for options selling and other strategies.
Transforms the app from reporting to strategy guidance.
"""

from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from decimal import Decimal

from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot, OptionPremiumSetting, StrategyRecommendationRecord
from app.modules.strategies.services import get_sold_options_by_account, calculate_4_week_average_premiums
from app.modules.strategies.option_monitor import OptionRollMonitor, get_positions_from_db
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)


class StrategyRecommendation(BaseModel):
    """Base model for all strategy recommendations."""
    id: str  # Unique identifier
    type: str  # Recommendation type
    category: str  # Category: "income_generation", "risk_management", "optimization"
    priority: str  # "low", "medium", "high", "urgent"
    
    # Content
    title: str
    description: str
    rationale: str
    
    # Action details
    action: str  # Specific action to take
    action_type: str  # "sell", "roll", "adjust", "monitor", "review"
    
    # Impact metrics
    potential_income: Optional[float] = None  # Potential income from action
    potential_risk: Optional[str] = None  # "low", "medium", "high"
    time_horizon: Optional[str] = None  # "immediate", "this_week", "this_month"
    
    # Account/Symbol (extracted from context for easier access)
    symbol: Optional[str] = None
    account_name: Optional[str] = None
    
    # Context
    context: Dict[str, Any]  # Relevant data
    related_data: Optional[Dict[str, Any]] = None
    
    # Metadata - use timezone-aware UTC for correct JS interpretation
    created_at: datetime = None  # Will be set in __init__
    expires_at: Optional[datetime] = None
    applicable: bool = True
    
    def __init__(self, **data):
        if 'created_at' not in data or data['created_at'] is None:
            data['created_at'] = datetime.now(timezone.utc)
        
        # Extract account_name and symbol from context if not explicitly set
        context = data.get('context', {})
        if 'account_name' not in data or data.get('account_name') is None:
            # Try to get from context (check both 'account_name' and 'account' keys)
            account_name = context.get('account_name') or context.get('account')
            if account_name:
                data['account_name'] = account_name
        
        if 'symbol' not in data or data.get('symbol') is None:
            symbol = context.get('symbol')
            if symbol:
                data['symbol'] = symbol
        
        super().__init__(**data)


class OptionsStrategyRecommendationService:
    """Generates actionable recommendations for options selling strategy."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_recommendations(
        self,
        params: Optional[Dict[str, Any]] = None
    ) -> List[StrategyRecommendation]:
        """
        Generate all applicable recommendations based on current state.
        
        Returns prioritized list of recommendations.
        """
        if params is None:
            params = {}
        
        recommendations = []
        
        # 1. Check for unsold contracts (income generation opportunity)
        recommendations.extend(self._check_unsold_contracts(params))
        
        # 2. Check for early roll opportunities
        recommendations.extend(self._check_early_rolls(params))
        
        # 3. Check premium settings accuracy
        recommendations.extend(self._check_premium_settings(params))
        
        # 4. Check diversification
        recommendations.extend(self._check_diversification(params))
        
        # 5. Check expiring options
        recommendations.extend(self._check_expiring_options(params))
        
        # Sort by priority and return
        return self._prioritize(recommendations)
    
    def _check_unsold_contracts(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """Generate recommendations for unsold contracts."""
        recommendations = []
        
        # Get holdings with unsold contracts
        default_premium = params.get("default_premium", 60)
        symbol_premiums = params.get("symbol_premiums", {})
        
        # Load premium settings
        db_premiums = {}
        db_settings = self.db.query(OptionPremiumSetting).all()
        for setting in db_settings:
            db_premiums[setting.symbol] = float(setting.premium_per_contract)
        
        default_symbol_premiums = {
            "AAPL": 50, "TSLA": 150, "NVDA": 100, "IBIT": 40,
            "AVGO": 80, "COIN": 120, "PLTR": 60, "META": 90,
            "MSFT": 60, "MU": 70, "TSM": 50, "MSTR": 200,
        }
        
        effective_premiums = {**default_symbol_premiums, **db_premiums, **symbol_premiums}
        
        def get_premium(symbol):
            return effective_premiums.get(symbol, default_premium)
        
        # Get holdings and sold options
        result = self.db.execute(text("""
            SELECT 
                ia.account_name,
                ih.symbol,
                ih.quantity,
                ih.current_price,
                ih.market_value,
                ih.description
            FROM investment_holdings ih
            JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
            WHERE ih.quantity >= 100
            AND ih.symbol NOT LIKE '%CASH%'
            AND ih.symbol NOT LIKE '%MONEY%'
            AND ih.symbol NOT LIKE '%FDRXX%'
            AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
            ORDER BY ih.market_value DESC
        """))
        
        # Get sold options by account
        sold_by_account = get_sold_options_by_account(self.db)
        
        # Group by symbol across accounts
        symbol_data = {}
        for row in result:
            account_name, symbol, qty, price, value, description = row
            qty = float(qty) if qty else 0
            price = float(price) if price else 0
            
            options_count = int(qty // 100)
            
            if symbol not in symbol_data:
                symbol_data[symbol] = {
                    "symbol": symbol,
                    "description": description or symbol,
                    "total_options": 0,
                    "total_sold": 0,
                    "accounts": []
                }
            
            # Count sold for this account
            account_sold = 0
            if account_name in sold_by_account:
                account_sold_opts = sold_by_account[account_name].get("by_symbol", {}).get(symbol, [])
                account_sold = sum(opt["contracts_sold"] for opt in account_sold_opts)
            
            symbol_data[symbol]["total_options"] += options_count
            symbol_data[symbol]["total_sold"] += account_sold
            
            if account_name not in symbol_data[symbol]["accounts"]:
                symbol_data[symbol]["accounts"].append(account_name)
        
        # Generate recommendations for symbols with unsold contracts
        for symbol, data in symbol_data.items():
            unsold = data["total_options"] - data["total_sold"]
            
            if unsold > 0:
                premium = get_premium(symbol)
                weekly_income = unsold * premium
                yearly_income = weekly_income * 50  # 50 weeks/year
                
                # Determine priority based on potential income
                if yearly_income > 10000:
                    priority = "high"
                elif yearly_income > 5000:
                    priority = "medium"
                else:
                    priority = "low"
                
                recommendation = StrategyRecommendation(
                    id=f"sell_unsold_{symbol}_{date.today().isoformat()}",
                    type="sell_unsold_contracts",
                    category="income_generation",
                    priority=priority,
                    title=f"Sell {unsold} unsold {symbol} covered call(s)",
                    description=(
                        f"You have {unsold} unsold contract(s) for {symbol} that could generate "
                        f"${weekly_income:.0f}/week (${yearly_income:.0f}/year) in additional income."
                    ),
                    rationale=(
                        f"Based on your current premium settings, {symbol} options generate "
                        f"${premium:.0f} per contract per week. Selling these {unsold} contracts "
                        f"would increase your weekly income by ${weekly_income:.0f}."
                    ),
                    action=f"Sell {unsold} {symbol} covered call(s) at delta 10 strike",
                    action_type="sell",
                    potential_income=weekly_income,
                    potential_risk="low",
                    time_horizon="this_week",
                    context={
                        "symbol": symbol,
                        "unsold_contracts": unsold,
                        "total_options": data["total_options"],
                        "sold_contracts": data["total_sold"],
                        "premium_per_contract": premium,
                        "accounts": data["accounts"],
                        "weekly_income": weekly_income,
                        "yearly_income": yearly_income
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations
    
    def _check_early_rolls(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """Generate recommendations for early roll opportunities."""
        recommendations = []
        
        profit_threshold = params.get("profit_threshold", 0.80)
        
        # Get positions from database
        positions = get_positions_from_db(self.db)
        
        if not positions:
            return recommendations
        
        # Use OptionRollMonitor to check positions
        monitor = OptionRollMonitor(profit_threshold=profit_threshold)
        alerts = monitor.check_all_positions(positions)
        
        for alert in alerts:
            pos = alert.position
            
            # Determine priority based on urgency and profit
            if alert.urgency == "high" or alert.profit_percent >= 0.90:
                priority = "urgent"
            elif alert.urgency == "medium":
                priority = "high"
            else:
                priority = "medium"
            
            # Calculate potential income from rolling
            # Estimate: new contract would generate similar premium
            potential_new_income = pos.original_premium * pos.contracts if alert.days_to_expiry >= 3 else 0
            
            recommendation = StrategyRecommendation(
                id=f"roll_early_{pos.symbol}_{pos.strike_price}_{pos.expiration_date.isoformat()}",
                type="early_roll_opportunity",
                category="optimization",
                priority=priority,
                title=f"Roll {pos.symbol} ${pos.strike_price} {pos.option_type.upper()} early - {alert.profit_percent*100:.0f}% profit",
                description=(
                    f"Your {pos.symbol} ${pos.strike_price} {pos.option_type} has reached "
                    f"{alert.profit_percent*100:.0f}% profit with {alert.days_to_expiry} days remaining. "
                    f"Rolling now would capture remaining premium and redeploy capital."
                ),
                rationale=alert.recommendation,
                action=f"Close {pos.contracts} {pos.symbol} ${pos.strike_price} {pos.option_type} and roll to next week",
                action_type="roll",
                potential_income=potential_new_income,
                potential_risk="low",
                time_horizon="immediate" if alert.days_to_expiry <= 2 else "this_week",
                context={
                    "symbol": pos.symbol,
                    "strike_price": pos.strike_price,
                    "option_type": pos.option_type,
                    "expiration_date": pos.expiration_date.isoformat(),
                    "contracts": pos.contracts,
                    "profit_percent": alert.profit_percent * 100,
                    "days_remaining": alert.days_to_expiry,
                    "original_premium": pos.original_premium,
                    "current_premium": alert.current_premium,
                    "profit_amount": alert.profit_amount
                },
                expires_at=datetime.utcnow() + timedelta(days=alert.days_to_expiry)
            )
            recommendations.append(recommendation)
        
        return recommendations
    
    def _check_premium_settings(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """Check if premium settings need adjustment based on actual data."""
        recommendations = []
        
        # Calculate 4-week averages
        averages = calculate_4_week_average_premiums(self.db, weeks=4)
        
        # Get current settings
        settings = self.db.query(OptionPremiumSetting).all()
        settings_dict = {s.symbol: s for s in settings}
        
        for symbol, avg_data in averages.items():
            calculated_premium = avg_data["premium_per_contract"]
            transaction_count = avg_data["transaction_count"]
            
            # Skip if not enough data
            if transaction_count < 3:
                continue
            
            setting = settings_dict.get(symbol)
            
            if setting:
                current_premium = float(setting.premium_per_contract)
                difference = calculated_premium - current_premium
                difference_percent = (difference / current_premium * 100) if current_premium > 0 else 0
                
                # Only recommend if difference is significant (>15%)
                if abs(difference_percent) > 15 and not setting.manual_override:
                    priority = "high" if abs(difference_percent) > 30 else "medium"
                    
                    recommendation = StrategyRecommendation(
                        id=f"adjust_premium_{symbol}_{date.today().isoformat()}",
                        type="adjust_premium_expectation",
                        category="optimization",
                        priority=priority,
                        title=f"Update {symbol} premium setting - actual is {difference_percent:+.0f}% different",
                        description=(
                            f"Your {symbol} premium setting is ${current_premium:.0f}/contract, but "
                            f"4-week average shows ${calculated_premium:.0f}/contract "
                            f"({difference_percent:+.0f}% difference)."
                        ),
                        rationale=(
                            f"Recent market activity shows {symbol} premiums are {difference_percent:+.0f}% "
                            f"different from your setting. Updating will improve income projections accuracy."
                        ),
                        action=f"Update {symbol} premium setting from ${current_premium:.0f} to ${calculated_premium:.0f}",
                        action_type="adjust",
                        potential_income=None,
                        potential_risk="none",
                        time_horizon="immediate",
                        context={
                            "symbol": symbol,
                            "current_setting": current_premium,
                            "calculated_average": calculated_premium,
                            "difference": difference,
                            "difference_percent": difference_percent,
                            "transaction_count": transaction_count,
                            "date_range": avg_data["date_range"]
                        }
                    )
                    recommendations.append(recommendation)
        
        return recommendations
    
    def _check_diversification(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """Check for concentration risk in options portfolio."""
        recommendations = []
        
        # Get income projection data
        default_premium = params.get("default_premium", 60)
        symbol_premiums = params.get("symbol_premiums", {})
        
        # Load premium settings
        db_premiums = {}
        db_settings = self.db.query(OptionPremiumSetting).all()
        for setting in db_settings:
            db_premiums[setting.symbol] = float(setting.premium_per_contract)
        
        default_symbol_premiums = {
            "AAPL": 50, "TSLA": 150, "NVDA": 100, "IBIT": 40,
            "AVGO": 80, "COIN": 120, "PLTR": 60, "META": 90,
            "MSFT": 60, "MU": 70, "TSM": 50, "MSTR": 200,
        }
        
        effective_premiums = {**default_symbol_premiums, **db_premiums, **symbol_premiums}
        
        def get_premium(symbol):
            return effective_premiums.get(symbol, default_premium)
        
        # Get holdings
        result = self.db.execute(text("""
            SELECT 
                ih.symbol,
                ih.quantity
            FROM investment_holdings ih
            JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
            WHERE ih.quantity >= 100
            AND ih.symbol NOT LIKE '%CASH%'
            AND ih.symbol NOT LIKE '%MONEY%'
            AND ih.symbol NOT LIKE '%FDRXX%'
            AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
        """))
        
        # Calculate income by symbol
        symbol_income = {}
        total_income = 0
        
        for row in result:
            symbol, qty = row
            qty = float(qty) if qty else 0
            options_count = int(qty // 100)
            premium = get_premium(symbol)
            weekly_income = options_count * premium
            
            symbol_income[symbol] = weekly_income
            total_income += weekly_income
        
        if total_income == 0:
            return recommendations
        
        # Find concentration
        sorted_symbols = sorted(symbol_income.items(), key=lambda x: x[1], reverse=True)
        top_symbol, top_income = sorted_symbols[0]
        concentration_percent = (top_income / total_income * 100) if total_income > 0 else 0
        
        # Recommend diversification if >35% concentration
        if concentration_percent > 35 and len(sorted_symbols) > 1:
            # Find symbols with unsold contracts
            sold_by_account = get_sold_options_by_account(self.db)
            alternative_symbols = []
            
            for symbol, income in sorted_symbols[1:6]:  # Top 5 alternatives
                # Check if has unsold contracts
                result = self.db.execute(text("""
                    SELECT 
                        ia.account_name,
                        ih.symbol,
                        ih.quantity
                    FROM investment_holdings ih
                    JOIN investment_accounts ia ON ih.account_id = ia.account_id AND ih.source = ia.source
                    WHERE ih.symbol = :symbol
                    AND ih.quantity >= 100
                    AND ia.account_type IN ('brokerage', 'retirement', 'ira', 'roth_ira')
                """), {"symbol": symbol})
                
                for row in result:
                    account_name, sym, qty = row
                    qty = float(qty) if qty else 0
                    options_count = int(qty // 100)
                    
                    # Check sold
                    account_sold = 0
                    if account_name in sold_by_account:
                        account_sold_opts = sold_by_account[account_name].get("by_symbol", {}).get(symbol, [])
                        account_sold = sum(opt["contracts_sold"] for opt in account_sold_opts)
                    
                    if options_count > account_sold:
                        if symbol not in alternative_symbols:
                            alternative_symbols.append(symbol)
                        break
            
            if alternative_symbols:
                recommendation = StrategyRecommendation(
                    id=f"diversify_concentration_{date.today().isoformat()}",
                    type="diversify_holdings",
                    category="risk_management",
                    priority="medium",
                    title=f"Consider diversifying - {concentration_percent:.0f}% of income from {top_symbol}",
                    description=(
                        f"{top_symbol} represents {concentration_percent:.0f}% of your potential options income. "
                        f"Consider selling options on other holdings to reduce concentration risk."
                    ),
                    rationale=(
                        f"Diversification reduces risk from single-stock volatility. You have "
                        f"{len(alternative_symbols)} other symbol(s) with unsold contracts available: "
                        f"{', '.join(alternative_symbols[:3])}."
                    ),
                    action=f"Review and sell options on {', '.join(alternative_symbols[:2])} to diversify",
                    action_type="review",
                    potential_income=None,
                    potential_risk="medium",  # Risk being mitigated
                    time_horizon="this_month",
                    context={
                        "concentrated_symbol": top_symbol,
                        "concentration_percent": concentration_percent,
                        "alternative_symbols": alternative_symbols,
                        "total_symbols": len(sorted_symbols),
                        "top_5_symbols": [s[0] for s in sorted_symbols[:5]]
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations
    
    def _check_expiring_options(
        self,
        params: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        """Check for options expiring soon that need action."""
        recommendations = []
        
        today = date.today()
        friday = today + timedelta(days=(4 - today.weekday()) % 7)  # Next Friday
        
        # Get positions expiring this week
        positions = get_positions_from_db(self.db)
        
        expiring_this_week = [
            p for p in positions
            if p.expiration_date and p.expiration_date <= friday
        ]
        
        if expiring_this_week:
            # Group by expiration date
            by_expiration = {}
            for pos in expiring_this_week:
                exp_date = pos.expiration_date.isoformat()
                if exp_date not in by_expiration:
                    by_expiration[exp_date] = []
                by_expiration[exp_date].append(pos)
            
            for exp_date, positions_list in by_expiration.items():
                days_until = (date.fromisoformat(exp_date) - today).days
                
                priority = "urgent" if days_until <= 1 else "high"
                
                positions_summary = [
                    {
                        "symbol": p.symbol,
                        "strike": p.strike_price,
                        "contracts": p.contracts,
                        "type": p.option_type
                    }
                    for p in positions_list
                ]
                
                recommendation = StrategyRecommendation(
                    id=f"expiring_options_{exp_date}",
                    type="manage_expiring_options",
                    category="income_generation",
                    priority=priority,
                    title=f"{len(positions_list)} position(s) expiring {exp_date} - decide on roll or let expire",
                    description=(
                        f"You have {len(positions_list)} position(s) expiring {exp_date} "
                        f"({days_until} day(s) away). Review profit status and decide whether to roll or let expire."
                    ),
                    rationale=(
                        f"Options expiring {exp_date} need action today or tomorrow to avoid "
                        f"assignment risk or missed roll opportunities."
                    ),
                    action=f"Review {len(positions_list)} expiring positions and decide on roll strategy",
                    action_type="review",
                    potential_income=None,
                    potential_risk="medium",
                    time_horizon="immediate",
                    context={
                        "expiring_count": len(positions_list),
                        "expiration_date": exp_date,
                        "days_until": days_until,
                        "positions": positions_summary
                    },
                    expires_at=datetime.fromisoformat(exp_date) + timedelta(hours=16)  # 4pm on expiration day
                )
                recommendations.append(recommendation)
        
        return recommendations
    
    def _prioritize(
        self,
        recommendations: List[StrategyRecommendation]
    ) -> List[StrategyRecommendation]:
        """Sort recommendations by priority."""
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        
        return sorted(
            recommendations,
            key=lambda r: (
                priority_order.get(r.priority, 99),
                -(r.potential_income or 0),  # Higher income first
                r.created_at  # Older first for same priority
            )
        )
    
    def save_recommendations_to_history(
        self, 
        recommendations: List[StrategyRecommendation]
    ) -> int:
        """
        Save recommendations to the database for history tracking.
        Returns the number of new recommendations saved.
        
        Uses INSERT ON CONFLICT to handle duplicates gracefully.
        The database has a UNIQUE constraint on recommendation_id.
        """
        from sqlalchemy.dialects.postgresql import insert
        from sqlalchemy import inspect
        
        saved_count = 0
        
        for rec in recommendations:
            # Extract symbol and account from context if available
            symbol = rec.context.get("symbol") if rec.context else None
            # Try both "account_name" and "account" keys for compatibility
            account_name = (rec.context.get("account_name") or rec.context.get("account")) if rec.context else None
            
            # Build values for insert
            values = {
                "recommendation_id": rec.id,
                "recommendation_type": rec.type,
                "category": rec.category,
                "priority": rec.priority,
                "title": rec.title,
                "description": rec.description,
                "rationale": rec.rationale,
                "action": rec.action,
                "action_type": rec.action_type,
                "potential_income": rec.potential_income,
                "potential_risk": rec.potential_risk,
                "symbol": symbol,
                "account_name": account_name,
                "status": "new",
                "context_snapshot": rec.context,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at
            }
            
            # Use INSERT ON CONFLICT DO UPDATE to refresh existing recommendations
            # This ensures UI shows the latest data even for recurring recommendations
            insert_stmt = insert(StrategyRecommendationRecord).values(**values)
            
            # Build the update dict using the excluded row (the values that would be inserted)
            update_dict = {
                # Update content (may have changed)
                "title": insert_stmt.excluded.title,
                "description": insert_stmt.excluded.description,
                "rationale": insert_stmt.excluded.rationale,
                "action": insert_stmt.excluded.action,
                "priority": insert_stmt.excluded.priority,
                "potential_income": insert_stmt.excluded.potential_income,
                "context_snapshot": insert_stmt.excluded.context_snapshot,
                # Reset to "new" status and update timestamp
                "status": "new",
                "created_at": insert_stmt.excluded.created_at,
                "expires_at": insert_stmt.excluded.expires_at,
                # Clear any previous acknowledgment
                "acknowledged_at": None,
                "acted_at": None,
            }
            
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=['recommendation_id'],
                set_=update_dict
            )
            
            try:
                result = self.db.execute(stmt)
                if result.rowcount > 0:
                    saved_count += 1
                    logger.info(f"[SAVE_REC] ✅ SAVED/UPDATED: {rec.id} (type={rec.type}, priority={rec.priority})")
                else:
                    logger.warning(f"[SAVE_REC] ⚠️ No rows affected for: {rec.id}")
            except Exception as exec_error:
                logger.error(f"[SAVE_REC] ❌ ERROR executing upsert for {rec.id}: {exec_error}")
        
        try:
            self.db.commit()
            logger.info(f"[SAVE_REC] ═══ SAVE COMPLETE: {saved_count} recommendations saved/updated ═══")
        except Exception as e:
            logger.error(f"Error saving recommendations: {e}")
            self.db.rollback()
            saved_count = 0
        
        return saved_count


def get_recommendation_history(
    db: Session,
    status: Optional[str] = None,
    strategy_type: Optional[str] = None,
    priority: Optional[str] = None,
    symbol: Optional[str] = None,
    days_back: int = 30,
    limit: int = 100
) -> List[StrategyRecommendationRecord]:
    """
    Fetch recommendation history with optional filters.
    """
    query = db.query(StrategyRecommendationRecord)
    
    # Apply filters
    if status:
        query = query.filter(StrategyRecommendationRecord.status == status)
    if strategy_type:
        query = query.filter(StrategyRecommendationRecord.recommendation_type == strategy_type)
    if priority:
        query = query.filter(StrategyRecommendationRecord.priority == priority)
    if symbol:
        query = query.filter(StrategyRecommendationRecord.symbol == symbol)
    
    # Date filter
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    query = query.filter(StrategyRecommendationRecord.created_at > cutoff)
    
    # Order by created_at descending (most recent first)
    query = query.order_by(StrategyRecommendationRecord.created_at.desc())
    
    return query.limit(limit).all()


def update_recommendation_status(
    db: Session,
    record_id: int,
    new_status: str,
    action_taken: Optional[str] = None
) -> Optional[StrategyRecommendationRecord]:
    """
    Update the status of a recommendation.
    new_status: 'acknowledged', 'acted', 'dismissed', 'expired'
    """
    record = db.query(StrategyRecommendationRecord).filter(
        StrategyRecommendationRecord.id == record_id
    ).first()
    
    if not record:
        return None
    
    record.status = new_status
    record.updated_at = datetime.utcnow()
    
    if new_status == 'acknowledged':
        record.acknowledged_at = datetime.utcnow()
    elif new_status == 'acted':
        record.acted_at = datetime.utcnow()
        if action_taken:
            record.action_taken = action_taken
    elif new_status == 'dismissed':
        record.dismissed_at = datetime.utcnow()
    
    try:
        db.commit()
        return record
    except Exception as e:
        logger.error(f"Error updating recommendation status: {e}")
        db.rollback()
        return None

