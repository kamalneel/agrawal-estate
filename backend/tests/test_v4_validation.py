"""
V4 Validation Test Script

Purpose: Validate V4 evaluator output against expected behaviors.
This creates a baseline test set that can be used to verify refactoring doesn't break anything.

Usage:
    cd backend
    python -m tests.test_v4_validation

Expected Output: Table of all positions with V4 decisions for human review.
"""
import asyncio
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.modules.strategies.v4_position_evaluator import V4PositionEvaluator, V4EvaluationResult
from app.modules.strategies.algorithm_config import V4_CONFIG


def get_db_session():
    """Create a database session."""
    # Read database URL from environment or use default
    import os
    database_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://agrawal_user:agrawal_secure_2024@localhost:5432/agrawal_estate'
    )
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def fetch_active_positions(db):
    """Fetch all active sold options."""
    from app.modules.strategies.models import SoldOption

    positions = db.query(SoldOption).filter(
        SoldOption.status == 'open'
    ).all()

    return positions


def fetch_stock_price(symbol: str) -> float:
    """Fetch current stock price."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"  Warning: Could not fetch price for {symbol}: {e}")
    return None


def run_v4_validation():
    """Run V4 evaluator on all positions and output results for validation."""

    print("=" * 80)
    print("V4 VALIDATION TEST")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # Get database session
    db = get_db_session()

    # Fetch positions
    positions = fetch_active_positions(db)
    print(f"Found {len(positions)} active positions")
    print()

    # Initialize evaluator
    evaluator = V4PositionEvaluator(V4_CONFIG)

    # Results storage for baseline
    results = []

    # Process each position
    for position in positions:
        print("-" * 80)

        # Get stock price
        stock_price = fetch_stock_price(position.symbol)
        if not stock_price:
            print(f"SKIP: {position.symbol} - no stock price available")
            continue

        # Position details
        strike = float(position.strike_price) if position.strike_price else 0
        option_type = getattr(position, 'option_type', 'call')
        contracts = getattr(position, 'contracts_sold', 1)
        expiration = position.expiration_date
        account = getattr(position, 'account_name', 'Unknown')
        original_premium = float(position.premium_received) if position.premium_received else 0

        # Calculate days to expiration
        if expiration:
            dte = (expiration - date.today()).days
        else:
            dte = 999

        # Calculate moneyness
        if option_type == 'call':
            itm_pct = ((stock_price - strike) / strike) * 100 if strike > 0 else 0
            moneyness = "ITM" if stock_price > strike else "OTM"
        else:
            itm_pct = ((strike - stock_price) / strike) * 100 if strike > 0 else 0
            moneyness = "ITM" if stock_price < strike else "OTM"

        print(f"POSITION: {position.symbol} ${strike:.0f} {option_type.upper()} exp {expiration}")
        print(f"  Account: {account}")
        print(f"  Stock: ${stock_price:.2f} | {moneyness} by {abs(itm_pct):.1f}%")
        print(f"  DTE: {dte} days | Contracts: {contracts}")
        print(f"  Original Premium: ${original_premium:.2f}")

        # Run V4 evaluator
        try:
            result = evaluator.evaluate(
                position=position,
                stock_price=stock_price,
                option_chain=None  # Will use fallback logic
            )

            if result:
                print()
                print(f"  V4 ACTION: {result.action}")
                print(f"  REASON: {result.reason_short}")
                print(f"  PHILOSOPHY: {result.philosophy_applied}")

                if result.new_strike:
                    print(f"  NEW STRIKE: ${result.new_strike}")
                if result.new_expiration:
                    print(f"  NEW EXPIRATION: {result.new_expiration}")
                if result.net_cost:
                    print(f"  NET COST: ${result.net_cost:.2f}")

                # Store for baseline
                results.append({
                    'symbol': position.symbol,
                    'strike': strike,
                    'option_type': option_type,
                    'expiration': str(expiration),
                    'account': account,
                    'stock_price': stock_price,
                    'dte': dte,
                    'moneyness': moneyness,
                    'itm_pct': itm_pct,
                    # V4 Output
                    'v4_action': result.action,
                    'v4_reason_short': result.reason_short,
                    'v4_philosophy': result.philosophy_applied,
                    'v4_new_strike': result.new_strike,
                    'v4_new_expiration': str(result.new_expiration) if result.new_expiration else None,
                    'v4_intrinsic_pct': result.intrinsic_pct,
                    'v4_time_value': result.time_value,
                })
            else:
                print(f"  V4: No recommendation (filtered)")

        except Exception as e:
            print(f"  V4 ERROR: {e}")

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    action_counts = {}
    for r in results:
        action = r['v4_action']
        action_counts[action] = action_counts.get(action, 0) + 1

    print(f"Total positions evaluated: {len(results)}")
    print()
    print("Actions breakdown:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count}")

    # Save baseline
    baseline_path = Path(__file__).parent / 'v4_baseline.json'
    with open(baseline_path, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'v4_config_version': V4_CONFIG.get('version'),
            'positions': results
        }, f, indent=2, default=str)

    print()
    print(f"Baseline saved to: {baseline_path}")
    print()
    print("NEXT STEPS:")
    print("1. Review each position's V4 action above")
    print("2. Mark any incorrect decisions")
    print("3. Once validated, this baseline can be used for regression testing")

    db.close()
    return results


if __name__ == '__main__':
    run_v4_validation()
