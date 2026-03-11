"""
V4 Baseline Regression Test

Purpose: Validate that V4 evaluator produces expected results.
Uses the baseline captured in v4_baseline.json to detect regressions.

Usage:
    cd backend
    python -m pytest tests/test_v4_baseline.py -v

    Or run directly:
    python -m tests.test_v4_baseline
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_db_session():
    """Create a database session."""
    database_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://agrawal_user:agrawal_secure_2024@localhost:5432/agrawal_estate'
    )
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def load_baseline():
    """Load the baseline JSON file."""
    baseline_path = Path(__file__).parent / 'v4_baseline.json'
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline file not found: {baseline_path}")

    with open(baseline_path) as f:
        return json.load(f)


class TestV4Baseline:
    """Test V4 evaluator against baseline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.db = get_db_session()
        self.baseline = load_baseline()
        yield
        self.db.close()

    def test_baseline_exists(self):
        """Verify baseline file exists and is valid."""
        assert 'positions' in self.baseline
        assert len(self.baseline['positions']) > 0
        print(f"Baseline has {len(self.baseline['positions'])} positions")

    def test_v4_actions_valid(self):
        """Verify all V4 actions are valid action codes."""
        valid_actions = {'HOLD', 'ROLL', 'COMPRESS', 'LET_EXPIRE', 'CLOSE',
                        'WAIT_FOR_PULLBACK', 'WAIT_FOR_RECOVERY'}

        for pos in self.baseline['positions']:
            action = pos['v4_action']
            assert action in valid_actions, f"Invalid action '{action}' for {pos['symbol']}"

    def test_roll_has_urgency(self):
        """Verify ROLL actions with <=2 days have high urgency."""
        for pos in self.baseline['positions']:
            if pos['v4_action'] == 'ROLL' and pos['days_to_exp'] <= 2:
                assert pos['urgency'] == 'high', \
                    f"ROLL with {pos['days_to_exp']}d should be high urgency: {pos['symbol']}"

    def test_should_notify_logic(self):
        """Verify should_notify is True for non-HOLD actions."""
        for pos in self.baseline['positions']:
            if pos['v4_action'] != 'HOLD':
                assert pos['should_notify'] == True, \
                    f"{pos['v4_action']} should generate notification: {pos['symbol']}"

    def test_itm_positions_not_held_near_expiry(self):
        """Verify ITM positions near expiry trigger action."""
        for pos in self.baseline['positions']:
            if pos['moneyness'] == 'ITM' and pos['days_to_exp'] <= 2:
                # ITM positions near expiry should not be HOLD
                assert pos['v4_action'] != 'HOLD', \
                    f"ITM position expiring in {pos['days_to_exp']}d should not HOLD: {pos['symbol']}"

    def test_regression_against_baseline(self):
        """
        Run V4 evaluator on current positions and compare to baseline.

        This is the main regression test - it verifies that refactoring
        doesn't change V4 behavior.
        """
        from app.modules.strategies.v4_position_evaluator import V4PositionEvaluator
        from app.modules.strategies.models import SoldOption

        # Get positions that exist in baseline
        baseline_ids = {p['id'] for p in self.baseline['positions']}

        positions = self.db.query(SoldOption).filter(
            SoldOption.id.in_(baseline_ids),
            SoldOption.status == 'open'
        ).all()

        if not positions:
            pytest.skip("No baseline positions still active")

        evaluator = V4PositionEvaluator(db=self.db)

        # Map baseline by ID
        baseline_map = {p['id']: p for p in self.baseline['positions']}

        mismatches = []
        for pos in positions:
            if pos.id not in baseline_map:
                continue

            baseline_pos = baseline_map[pos.id]

            # Skip if position has expired since baseline
            if pos.expiration_date < date.today():
                continue

            result = evaluator.evaluate(position=pos)

            if result:
                if result.action != baseline_pos['v4_action']:
                    mismatches.append({
                        'symbol': pos.symbol,
                        'id': pos.id,
                        'expected': baseline_pos['v4_action'],
                        'actual': result.action,
                        'reason': result.reason_short
                    })

        if mismatches:
            print("\n=== REGRESSIONS DETECTED ===")
            for m in mismatches:
                print(f"{m['symbol']} (id={m['id']}): expected {m['expected']}, got {m['actual']}")
                print(f"  Reason: {m['reason']}")

        # Allow some variance (market conditions change) but flag significant regressions
        regression_rate = len(mismatches) / len(positions) if positions else 0
        assert regression_rate < 0.1, f"Too many regressions: {len(mismatches)}/{len(positions)} ({regression_rate:.1%})"


class TestV4NotificationFlow:
    """Test the V4 notification pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.db = get_db_session()
        yield
        self.db.close()

    def test_v4_notification_service_exists(self):
        """Verify V4 notification service can be instantiated."""
        from app.modules.strategies.v4_notification_service import get_v4_notification_service

        service = get_v4_notification_service(self.db)
        assert service is not None

    def test_evaluate_and_notify_returns_notifications(self):
        """Verify evaluate_and_notify returns notification items."""
        from app.modules.strategies.v4_notification_service import get_v4_notification_service
        from app.modules.strategies.models import SoldOption

        # Get a few active positions
        positions = self.db.query(SoldOption).filter(
            SoldOption.status == 'open',
            SoldOption.expiration_date >= date.today()
        ).limit(5).all()

        if not positions:
            pytest.skip("No active positions")

        service = get_v4_notification_service(self.db)
        notifications = service.evaluate_and_notify(positions)

        # Should get notifications for all positions
        assert len(notifications) == len(positions), \
            f"Expected {len(positions)} notifications, got {len(notifications)}"

        # Each notification should have required fields
        for notif in notifications:
            assert 'action' in notif, "Missing action field"
            assert 'symbol' in notif, "Missing symbol field"
            assert 'reason_short' in notif, "Missing reason_short field"
            assert notif['action'] in {'HOLD', 'ROLL', 'COMPRESS', 'LET_EXPIRE', 'CLOSE',
                                       'WAIT_FOR_PULLBACK', 'WAIT_FOR_RECOVERY'}, \
                f"Invalid action: {notif['action']}"


def run_validation_report():
    """Run a comprehensive validation report."""
    baseline = load_baseline()

    print("=" * 70)
    print("V4 BASELINE VALIDATION REPORT")
    print("=" * 70)
    print(f"Generated: {baseline['generated_at']}")
    print(f"Total positions: {baseline['total_positions']}")
    print(f"Evaluated: {baseline['evaluated']}")
    print()

    print("Action Distribution:")
    for action, count in sorted(baseline['summary']['by_action'].items()):
        pct = count / baseline['evaluated'] * 100
        print(f"  {action}: {count} ({pct:.1f}%)")
    print()

    print(f"Should notify: {baseline['summary']['should_notify']}")
    print(f"High urgency: {baseline['summary']['by_urgency']['high']}")
    print()

    # Validate action consistency
    print("Validation Checks:")

    # Check 1: All actions are valid
    valid_actions = {'HOLD', 'ROLL', 'COMPRESS', 'LET_EXPIRE', 'CLOSE',
                    'WAIT_FOR_PULLBACK', 'WAIT_FOR_RECOVERY'}
    invalid = [p for p in baseline['positions'] if p['v4_action'] not in valid_actions]
    print(f"  ✓ Valid actions: {len(baseline['positions']) - len(invalid)}/{len(baseline['positions'])}")
    if invalid:
        print(f"  ✗ Invalid actions: {len(invalid)}")
        for p in invalid[:5]:
            print(f"    - {p['symbol']}: {p['v4_action']}")

    # Check 2: ITM near expiry should not HOLD
    itm_near_expiry = [p for p in baseline['positions']
                      if p['moneyness'] == 'ITM' and p['days_to_exp'] <= 2]
    itm_holding = [p for p in itm_near_expiry if p['v4_action'] == 'HOLD']
    print(f"  ✓ ITM near expiry actions: {len(itm_near_expiry) - len(itm_holding)}/{len(itm_near_expiry)}")
    if itm_holding:
        print(f"  ⚠ ITM near expiry still holding: {len(itm_holding)}")
        for p in itm_holding[:3]:
            print(f"    - {p['symbol']} {p['option_type']} ${p['strike']} exp {p['expiration']}")

    # Check 3: ROLL urgency
    rolls_near_expiry = [p for p in baseline['positions']
                        if p['v4_action'] == 'ROLL' and p['days_to_exp'] <= 2]
    high_urgency_correct = [p for p in rolls_near_expiry if p['urgency'] == 'high']
    print(f"  ✓ ROLL urgency correct: {len(high_urgency_correct)}/{len(rolls_near_expiry)}")

    print()
    print("=" * 70)


if __name__ == '__main__':
    run_validation_report()
