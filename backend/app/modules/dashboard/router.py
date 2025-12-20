"""
Dashboard API routes.
Provides wealth summary and overview data for the Agrawal family.
Aggregates data from investments, real estate, equity, cash, and income modules.
All data is retrieved from the database - no hardcoded values.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.cache import cached_response
from app.modules.investments.services import get_holdings_summary
from app.modules.income.services import get_income_service
from app.modules.india_investments.services import get_dashboard_india_investments

router = APIRouter()


def get_real_estate_summary(db: Session) -> dict:
    """Get real estate summary from the real estate service (database)."""
    try:
        from app.modules.real_estate.services import get_property_summary
        return get_property_summary(db)
    except Exception as e:
        print(f"Warning: Could not load real estate data: {e}")
        return {"total_equity": 0, "total_value": 0, "properties": []}


def get_startup_equity_summary(db: Session) -> dict:
    """Get startup equity summary from the equity module."""
    try:
        from app.modules.equity.services import get_equity_summary
        return get_equity_summary(db)
    except Exception as e:
        print(f"Warning: Could not load equity data: {e}")
        return {"total_estimated_value": 0, "holdings_by_company": []}


def get_cash_summary(db: Session) -> dict:
    """Get cash summary from the cash module."""
    try:
        from app.modules.cash.services import get_all_cash_balances
        return get_all_cash_balances(db)
    except Exception as e:
        print(f"Warning: Could not load cash data: {e}")
        return {"total_cash": 0, "accounts": []}


@router.get("/summary")
@cached_response(base_ttl=60, extended_ttl=300, key_prefix="dashboard:")
async def get_wealth_summary(db: Session = Depends(get_db)):
    """
    Get comprehensive wealth summary.
    Aggregates data from all modules: investments, real estate, equity, cash, income.
    All data comes from the database.
    """
    # Get investment data (public stocks)
    investment_summary = get_holdings_summary(db)
    investment_value = investment_summary.get('totalValue', 0)
    
    # Get startup equity data
    equity_summary = get_startup_equity_summary(db)
    startup_equity_value = equity_summary.get('total_estimated_value', 0)
    
    # Get cash data
    cash_summary = get_cash_summary(db)
    cash_value = cash_summary.get('total_cash', 0)
    
    # Get India investments data (only Neel's accounts, converted to USD)
    india_investments_data = {}
    india_investments_value_usd = 0
    try:
        india_data = get_dashboard_india_investments(db)
        india_investments_value_usd = india_data.get('total_value_usd', 0)
        india_investments_data = {
            'total_value_inr': india_data.get('total_value_inr', 0),
            'total_value_usd': india_investments_value_usd,
            'exchange_rate': india_data.get('exchange_rate', 83.0),
            'breakdown': {
                'cash': sum(acc['cash_balance'] for acc in india_data.get('bank_accounts', [])),
                'stocks': sum(stock['current_value'] for stock in india_data.get('stocks', [])),
                'mutual_funds': sum(mf['current_value'] for mf in india_data.get('mutual_funds', [])),
                'fixed_deposits': sum(fd['current_value'] for fd in india_data.get('fixed_deposits', [])),
            }
        }
    except Exception as e:
        print(f"Warning: Could not load India investments data: {e}")
    
    # Get real estate data FROM DATABASE
    real_estate_summary = get_real_estate_summary(db)
    real_estate_equity = real_estate_summary.get('total_equity', 0)
    real_estate_mortgage = real_estate_summary.get('total_mortgage_balance', 0)
    
    # Get income data
    income_service = get_income_service()
    income_summary = income_service.get_income_summary()
    
    # Calculate totals (including all asset types)
    total_assets = investment_value + real_estate_summary.get('total_value', 0) + startup_equity_value + cash_value + india_investments_value_usd
    total_liabilities = real_estate_mortgage  # Currently just mortgages
    total_net_worth = total_assets - total_liabilities
    
    return {
        "total_net_worth": total_net_worth,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        
        "assets": {
            "public_equity": {
                "label": "Public Equity",
                "description": "Robinhood, Schwab Brokerage",
                "value": investment_value,
                "by_owner": investment_summary.get('byOwner', {}),
                "by_type": investment_summary.get('byType', {}),
                "account_count": investment_summary.get('accountCount', 0),
            },
            "real_estate": {
                "label": "Real Estate",
                "description": "Properties & Home Equity",
                "value": real_estate_equity,
                "properties": [
                    {
                        "id": p['id'],
                        "address": p['full_address'],
                        "value": p['value'],
                        "mortgage_balance": p['mortgage_balance'],
                        "equity": p['equity'],
                        "type": p['property_type']
                    }
                    for p in real_estate_summary.get('properties', [])
                ],
            },
            "startup_equity": {
                "label": "Startup Equity",
                "description": "Stock Options & Private Company Shares",
                "value": startup_equity_value,
                "companies": equity_summary.get('holdings_by_company', []),
                "num_companies": equity_summary.get('num_companies', 0),
            },
            "cash": {
                "label": "Cash & Savings",
                "description": "Bank Accounts & Brokerage Cash",
                "value": cash_value,
                "accounts": cash_summary.get('accounts', []),
                "by_owner": cash_summary.get('by_owner', {}),
            },
            "india_investments": {
                "label": "India Investments",
                "description": "Indian Stocks, Mutual Funds, FDs & Cash",
                "value": india_investments_value_usd,
                "value_inr": india_investments_data.get('total_value_inr', 0),
                "exchange_rate": india_investments_data.get('exchange_rate', 83.0),
                "breakdown": india_investments_data.get('breakdown', {}),
            },
        },
        
        "liabilities": {
            "mortgages": {
                "label": "Mortgages",
                "description": "Home Loans Outstanding",
                "value": real_estate_mortgage,
            },
            "other_loans": {
                "label": "Other Loans",
                "description": "Auto, Personal, Credit Lines",
                "value": 0,
            },
        },
        
        "income": {
            "total_investment_income": income_summary.get('total_investment_income', 0),
            "options_income": income_summary.get('options_income', 0),
            "dividend_income": income_summary.get('dividend_income', 0),
            "interest_income": income_summary.get('interest_income', 0),
            "stock_lending": income_summary.get('stock_lending', 0),
        },
        
        "last_updated": datetime.utcnow().isoformat(),
    }


@router.get("/wealth-history")
@cached_response(base_ttl=300, extended_ttl=1800, key_prefix="dashboard:")
async def get_wealth_history(db: Session = Depends(get_db)):
    """
    Get historical net worth data for the wealth journey chart.
    Uses portfolio snapshots for investment history, property valuations for real estate.
    """
    from datetime import date
    from sqlalchemy import func
    from app.modules.investments.models import PortfolioSnapshot
    from app.modules.real_estate.models import Property, PropertyValuation
    
    # Neel's date of birth for accurate age calculation
    BIRTH_DATE = date(1980, 7, 21)
    
    # Get property valuation history from database
    properties = db.query(Property).filter(Property.is_active == 'Y').all()
    
    # Build real estate value by year from database
    yearly_real_estate = {}
    for prop in properties:
        valuations = db.query(PropertyValuation).filter(
            PropertyValuation.property_id == prop.id
        ).order_by(PropertyValuation.valuation_date).all()
        
        for val in valuations:
            year = val.valuation_date.year
            if year not in yearly_real_estate:
                yearly_real_estate[year] = 0
            # Use the latest valuation for each property in each year
            yearly_real_estate[year] = float(val.value)
    
    # Get historical investment values from portfolio snapshots
    yearly_investment_values = {}
    monthly_snapshots = db.query(
        PortfolioSnapshot.statement_date,
        func.sum(PortfolioSnapshot.portfolio_value).label('total_value')
    ).group_by(
        PortfolioSnapshot.statement_date
    ).order_by(
        PortfolioSnapshot.statement_date
    ).all()
    
    for snap in monthly_snapshots:
        year = snap.statement_date.year
        value = float(snap.total_value or 0)
        yearly_investment_values[year] = value
    
    # Get CURRENT values from the actual services
    current_investment_value = 0
    try:
        investment_summary = get_holdings_summary(db)
        current_investment_value = investment_summary.get('totalValue', 0)
    except Exception as e:
        print(f"Warning: Could not load investment holdings: {e}")
    
    current_startup_equity = 0
    try:
        equity_summary = get_startup_equity_summary(db)
        current_startup_equity = equity_summary.get('total_estimated_value', 0)
    except Exception as e:
        print(f"Warning: Could not load startup equity: {e}")
    
    current_cash = 0
    try:
        cash_summary = get_cash_summary(db)
        current_cash = cash_summary.get('total_cash', 0)
    except Exception as e:
        print(f"Warning: Could not load cash: {e}")
    
    current_real_estate = 0
    try:
        re_summary = get_real_estate_summary(db)
        current_real_estate = re_summary.get('total_equity', 0)
    except Exception as e:
        print(f"Warning: Could not load real estate: {e}")
    
    # Determine the start year from the earliest property purchase or valuation
    start_year = 2011  # Default
    if yearly_real_estate:
        start_year = min(yearly_real_estate.keys())
    
    # Calculate age for each year
    def calculate_age(year):
        end_of_year = date(year, 12, 31)
        age = end_of_year.year - BIRTH_DATE.year
        if (end_of_year.month, end_of_year.day) < (BIRTH_DATE.month, BIRTH_DATE.day):
            age -= 1
        return age
    
    # Calculate current age
    today = date.today()
    current_age = today.year - BIRTH_DATE.year
    if (today.month, today.day) < (BIRTH_DATE.month, BIRTH_DATE.day):
        current_age -= 1
    
    current_year = datetime.now().year
    wealth_history = []
    
    # Use the last known real estate value for years without data
    last_re_value = 0
    
    for year in range(start_year, current_year + 1):
        age = calculate_age(year)
        
        # Real estate value from database (or carry forward last known value)
        re_value = yearly_real_estate.get(year, last_re_value)
        if re_value > 0:
            last_re_value = re_value
        
        # For current year, use actual values from services
        if year == current_year:
            inv_value = current_investment_value
            startup_value = current_startup_equity
            cash_value = current_cash
            re_value = current_real_estate
        else:
            inv_value = yearly_investment_values.get(year, 0)
            startup_value = 0  # We don't have historical startup equity data
            cash_value = 0     # We don't have reliable historical cash data
        
        net_worth = re_value + inv_value + startup_value + cash_value
        
        wealth_history.append({
            "year": year,
            "age": age,
            "netWorth": net_worth,
            "realEstate": re_value,
            "investments": inv_value,
            "startupEquity": startup_value,
            "cash": cash_value,
        })
    
    return {
        "history": wealth_history,
        "current_age": current_age,
        "start_year": start_year,
        "birth_date": BIRTH_DATE.isoformat(),
    }


@router.get("/recent-activity")
async def get_recent_activity(db: Session = Depends(get_db), limit: int = 10):
    """Get recent financial activity across all modules."""
    from app.modules.investments.models import InvestmentTransaction
    
    transactions = db.query(InvestmentTransaction).order_by(
        InvestmentTransaction.transaction_date.desc()
    ).limit(limit).all()
    
    activities = []
    for t in transactions:
        activities.append({
            "type": "investment",
            "date": t.transaction_date.isoformat() if t.transaction_date else None,
            "description": f"{t.transaction_type}: {t.symbol}",
            "amount": float(t.amount) if t.amount else None,
        })
    
    return {
        "activities": activities,
        "total_count": len(activities)
    }


@router.get("/alerts")
async def get_alerts(db: Session = Depends(get_db)):
    """Get important alerts and reminders."""
    alerts = []
    reminders = []
    
    # Check for any data quality issues
    investment_summary = get_holdings_summary(db)
    
    if investment_summary.get('accountCount', 0) == 0:
        alerts.append({
            "type": "warning",
            "message": "No investment holdings found. Consider importing brokerage statements.",
            "action": "/data-ingestion"
        })
    
    # Check if real estate data exists
    re_summary = get_real_estate_summary(db)
    if re_summary.get('property_count', 0) == 0:
        alerts.append({
            "type": "warning",
            "message": "No real estate properties found. Run /api/real-estate/seed to initialize.",
            "action": "/api/real-estate/seed"
        })
    
    return {
        "alerts": alerts,
        "reminders": reminders
    }


@router.get("/insights")
async def get_insights(db: Session = Depends(get_db), limit: int = 5):
    """
    Get automatically discovered insights about the family's finances.
    
    Uses statistical analysis and pattern detection to surface interesting
    facts like record-breaking months, trend changes, milestones, and
    unusual performance patterns.
    
    Returns up to `limit` most important insights, excluding archived ones.
    """
    from app.modules.dashboard.insights import get_daily_insights, get_archived_count
    
    try:
        insights = get_daily_insights(db, limit=limit)
        archived_count = get_archived_count()
        return {
            "insights": insights,
            "count": len(insights),
            "archived_count": archived_count,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"Error generating insights: {e}")
        import traceback
        traceback.print_exc()
        return {
            "insights": [],
            "count": 0,
            "archived_count": 0,
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


@router.get("/insights/all")
async def get_all_insights(db: Session = Depends(get_db)):
    """
    Get all insights split into active and archived.
    Returns both lists so the UI can display archive if needed.
    """
    from app.modules.dashboard.insights import get_insights_with_archive
    
    try:
        result = get_insights_with_archive(db)
        result["generated_at"] = datetime.utcnow().isoformat()
        return result
    except Exception as e:
        print(f"Error generating insights: {e}")
        import traceback
        traceback.print_exc()
        return {
            "active": [],
            "archived": [],
            "active_count": 0,
            "archived_count": 0,
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


@router.post("/insights/{insight_id}/archive")
async def archive_insight_endpoint(insight_id: str):
    """
    Archive an insight by marking it as read/dismissed.
    The insight will no longer appear in the main insights list.
    """
    from app.modules.dashboard.insights import archive_insight
    
    try:
        success = archive_insight(insight_id)
        return {
            "success": success,
            "insight_id": insight_id,
            "action": "archived"
        }
    except Exception as e:
        print(f"Error archiving insight: {e}")
        return {
            "success": False,
            "insight_id": insight_id,
            "error": str(e)
        }


@router.post("/insights/{insight_id}/unarchive")
async def unarchive_insight_endpoint(insight_id: str):
    """
    Restore an archived insight back to the active list.
    """
    from app.modules.dashboard.insights import unarchive_insight
    
    try:
        success = unarchive_insight(insight_id)
        return {
            "success": success,
            "insight_id": insight_id,
            "action": "unarchived"
        }
    except Exception as e:
        print(f"Error unarchiving insight: {e}")
        return {
            "success": False,
            "insight_id": insight_id,
            "error": str(e)
        }


@router.post("/insights/clear-archive")
async def clear_insights_archive():
    """
    Clear all archived insights, restoring them to active status.
    """
    from app.modules.dashboard.insights import clear_archive
    
    try:
        count = clear_archive()
        return {
            "success": True,
            "cleared_count": count
        }
    except Exception as e:
        print(f"Error clearing archive: {e}")
        return {
            "success": False,
            "error": str(e)
        }
