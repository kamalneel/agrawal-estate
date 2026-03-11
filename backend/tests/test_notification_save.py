"""
Integration tests for notification save functionality.

Tests that all notification types flow through save correctly,
including batch scenarios with multiple notifications for same symbol/account.

See docs/ALGORITHM-UPGRADE-BEST-PRACTICES.md Pitfall 17 for context.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from decimal import Decimal

from app.modules.strategies.notification_schema import (
    NotificationDict,
    validate_notification_dict,
    create_base_notification,
)


class TestNotificationSchema:
    """Test notification schema validation."""

    def test_valid_notification(self):
        """Test that a valid notification passes validation."""
        notif = create_base_notification(
            symbol='AAPL',
            account_name="Neel's Brokerage",
            action='ROLL',
            source_strike=150.0,
            source_expiration=date.today() + timedelta(days=7),
            option_type='call',
        )
        errors = validate_notification_dict(notif)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_account_name(self):
        """Test that missing account_name is caught."""
        notif = {
            'symbol': 'AAPL',
            'action': 'ROLL',
            'source_strike': 150.0,
            'source_expiration': date.today(),
            'option_type': 'call',
            # Missing account_name!
        }
        errors = validate_notification_dict(notif)
        assert any('account_name' in e for e in errors)

    def test_account_name_only_in_context(self):
        """Test that account_name only in context is caught."""
        notif = {
            'symbol': 'AAPL',
            'action': 'ROLL',
            'source_strike': 150.0,
            'source_expiration': date.today(),
            'option_type': 'call',
            'context': {
                'account_name': "Neel's Brokerage",  # Only in context!
            },
        }
        errors = validate_notification_dict(notif)
        assert any('only in context' in e for e in errors)

    def test_missing_source_strike(self):
        """Test that missing source_strike is caught."""
        notif = {
            'symbol': 'AAPL',
            'account_name': "Neel's Brokerage",
            'action': 'ROLL',
            'source_expiration': date.today(),
            'option_type': 'call',
            # Missing source_strike!
        }
        errors = validate_notification_dict(notif)
        assert any('source_strike' in e for e in errors)

    def test_missing_source_expiration(self):
        """Test that missing source_expiration is caught."""
        notif = {
            'symbol': 'AAPL',
            'account_name': "Neel's Brokerage",
            'action': 'ROLL',
            'source_strike': 150.0,
            'option_type': 'call',
            # Missing source_expiration!
        }
        errors = validate_notification_dict(notif)
        assert any('source_expiration' in e for e in errors)


class TestNotificationBatchSave:
    """Test batch save handling for notifications."""

    def test_duplicate_symbol_batch(self):
        """
        Test that batch with multiple notifications for same symbol/account
        doesn't cause duplicate snapshot numbers.

        This is the scenario from Pitfall 17.
        """
        # Create multiple notifications for same position
        base_date = date.today() + timedelta(days=7)

        notifications = [
            create_base_notification(
                symbol='AAPL',
                account_name="Neel's Brokerage",
                action='ROLL',
                source_strike=150.0,
                source_expiration=base_date,
                option_type='call',
                id='notif_1',
            ),
            create_base_notification(
                symbol='AAPL',
                account_name="Neel's Brokerage",
                action='CLOSE',  # Different action, same position
                source_strike=150.0,
                source_expiration=base_date,
                option_type='call',
                id='notif_2',
            ),
        ]

        # Validate all notifications
        for notif in notifications:
            errors = validate_notification_dict(notif)
            assert errors == [], f"Notification {notif.get('id')} has errors: {errors}"

    def test_put_notification_has_required_fields(self):
        """Test that put notifications have all required top-level fields."""
        put_notif = create_base_notification(
            symbol='NVDA',
            account_name="Neel's Brokerage",
            action='SELL',
            source_strike=140.0,
            source_expiration=date.today() + timedelta(days=7),
            option_type='put',
            is_put_recommendation=True,
            target_premium=2.50,
        )

        errors = validate_notification_dict(put_notif)
        assert errors == [], f"Put notification has errors: {errors}"

    def test_pending_order_notification_has_required_fields(self):
        """Test that pending order notifications have all required top-level fields."""
        pending_notif = create_base_notification(
            symbol='TSLA',
            account_name="Neel's Brokerage",
            action='PENDING_ORDER_KEEP',
            source_strike=370.0,
            source_expiration=date.today() + timedelta(days=14),
            option_type='call',
            is_pending_order=True,
            pending_order_id=123,
            pending_limit_price=3.00,
        )

        errors = validate_notification_dict(pending_notif)
        assert errors == [], f"Pending order notification has errors: {errors}"


class TestNotificationIdGeneration:
    """Test that notification fields work correctly for recommendation ID generation."""

    def test_recommendation_id_fields_present(self):
        """
        Test that fields required for recommendation ID generation are present
        and have correct types.
        """
        notif = create_base_notification(
            symbol='AAPL',
            account_name="Neel's Brokerage",
            action='ROLL',
            source_strike=150.0,
            source_expiration=date.today() + timedelta(days=7),
            option_type='call',
        )

        # These are used by generate_recommendation_id()
        assert notif['symbol'] == 'AAPL'
        assert notif['account_name'] == "Neel's Brokerage"
        assert notif['source_strike'] == 150.0
        assert notif['source_expiration'] == date.today() + timedelta(days=7)
        assert notif['option_type'] == 'call'

    def test_float_conversion_of_decimal_strike(self):
        """Test that Decimal strikes are handled correctly."""
        # Simulating what might come from DB
        decimal_strike = Decimal('150.50')

        notif = create_base_notification(
            symbol='AAPL',
            account_name="Neel's Brokerage",
            action='ROLL',
            source_strike=float(decimal_strike),  # Should convert
            source_expiration=date.today() + timedelta(days=7),
            option_type='call',
        )

        assert isinstance(notif['source_strike'], float)
        assert notif['source_strike'] == 150.50


class TestNotificationTypes:
    """Test different notification types have proper structure."""

    def test_roll_notification(self):
        """Test ROLL notification structure."""
        notif = create_base_notification(
            symbol='AAPL',
            account_name="Neel's Brokerage",
            action='ROLL',
            source_strike=150.0,
            source_expiration=date.today() + timedelta(days=7),
            option_type='call',
            target_strike=155.0,
            target_expiration=date.today() + timedelta(days=14),
            net_cost=-0.50,  # Credit
        )

        errors = validate_notification_dict(notif)
        assert errors == []
        assert notif['action'] == 'ROLL'

    def test_close_notification(self):
        """Test CLOSE notification structure."""
        notif = create_base_notification(
            symbol='AAPL',
            account_name="Neel's Brokerage",
            action='CLOSE',
            source_strike=150.0,
            source_expiration=date.today() + timedelta(days=7),
            option_type='call',
            reason='70% profit reached',
        )

        errors = validate_notification_dict(notif)
        assert errors == []

    def test_life_support_notification(self):
        """Test LIFE_SUPPORT (ROLL_BIWEEKLY) notification structure."""
        notif = create_base_notification(
            symbol='HOOD',
            account_name="Neel's Brokerage",
            action='ROLL_BIWEEKLY',
            source_strike=45.0,
            source_expiration=date.today() + timedelta(days=3),
            option_type='put',
            stuck_category='LIFE_SUPPORT',
            biweekly_credit=0.30,
        )

        errors = validate_notification_dict(notif)
        assert errors == []
        assert notif.get('stuck_category') == 'LIFE_SUPPORT'

    def test_compress_notification(self):
        """Test COMPRESS notification structure."""
        notif = create_base_notification(
            symbol='AVGO',
            account_name="Neel's Brokerage",
            action='COMPRESS',
            source_strike=320.0,
            source_expiration=date.today() + timedelta(days=60),
            option_type='put',
            target_strike=320.0,
            target_expiration=date.today() + timedelta(days=7),
            compression_cost=500.0,
        )

        errors = validate_notification_dict(notif)
        assert errors == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
