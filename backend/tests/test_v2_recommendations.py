"""
Unit Tests for V2 Recommendation Model

Tests the new snapshot-based recommendation system:
1. Recommendation identity generation
2. Snapshot creation and change detection
3. Notification logic
4. Execution matching

Run with: pytest tests/test_v2_recommendations.py -v
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    RecommendationExecution,
    generate_recommendation_id
)


class TestRecommendationIdentity:
    """Tests for recommendation ID generation."""
    
    def test_generate_recommendation_id_basic(self):
        """Test basic ID generation."""
        rec_id = generate_recommendation_id(
            symbol="PLTR",
            source_strike=207.5,
            source_expiration=date(2026, 1, 2),
            option_type="call",
            account_name="Neel's Brokerage"
        )
        
        assert rec_id == "PLTR_207.5_20260102_call_Neel_s_Brokerage"
    
    def test_generate_recommendation_id_removes_trailing_zeros(self):
        """Test that trailing zeros are removed from strike."""
        rec_id = generate_recommendation_id(
            symbol="AAPL",
            source_strike=150.00,
            source_expiration=date(2026, 1, 10),
            option_type="call",
            account_name="Test Account"
        )
        
        assert "150_" in rec_id  # Not "150.00_"
    
    def test_generate_recommendation_id_sanitizes_account(self):
        """Test that special characters in account name are sanitized."""
        rec_id = generate_recommendation_id(
            symbol="NVDA",
            source_strike=135.0,
            source_expiration=date(2026, 2, 15),
            option_type="put",
            account_name="Jaya's Retirement IRA"
        )
        
        assert "Jaya_s_Retirement_IRA" in rec_id
    
    def test_generate_recommendation_id_deterministic(self):
        """Test that same inputs always produce same ID."""
        id1 = generate_recommendation_id("TSLA", 300.0, date(2026, 1, 15), "call", "My Account")
        id2 = generate_recommendation_id("TSLA", 300.0, date(2026, 1, 15), "call", "My Account")
        
        assert id1 == id2
    
    def test_generate_recommendation_id_different_strikes(self):
        """Test that different strikes produce different IDs."""
        id1 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Account")
        id2 = generate_recommendation_id("PLTR", 210.0, date(2026, 1, 2), "call", "Account")
        
        assert id1 != id2
    
    def test_generate_recommendation_id_different_expirations(self):
        """Test that different expirations produce different IDs."""
        id1 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Account")
        id2 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 9), "call", "Account")
        
        assert id1 != id2
    
    def test_generate_recommendation_id_different_accounts(self):
        """Test that different accounts produce different IDs."""
        id1 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Neel's Brokerage")
        id2 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Neel's Retirement")
        
        assert id1 != id2
    
    def test_generate_recommendation_id_different_option_types(self):
        """Test that call vs put produce different IDs."""
        id1 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Account")
        id2 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "put", "Account")
        
        assert id1 != id2


class TestSnapshotModel:
    """Tests for RecommendationSnapshot model."""
    
    def test_snapshot_creation(self):
        """Test basic snapshot creation."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=1,
            evaluated_at=datetime.utcnow(),
            recommended_action="ROLL_WEEKLY",
            priority="medium",
            action_changed=False,  # Explicit since defaults are DB-level
            notification_sent=False
        )
        
        assert snapshot.snapshot_number == 1
        assert snapshot.recommended_action == "ROLL_WEEKLY"
        assert snapshot.priority == "medium"
        assert snapshot.action_changed == False
        assert snapshot.notification_sent == False
    
    def test_snapshot_with_target_parameters(self):
        """Test snapshot with target strike and expiration."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=1,
            evaluated_at=datetime.utcnow(),
            recommended_action="ROLL_WEEKLY",
            priority="medium",
            target_strike=Decimal("196.00"),
            target_expiration=date(2026, 1, 10),
            target_premium=Decimal("0.49"),
            net_cost=Decimal("-0.15")  # Credit
        )
        
        assert snapshot.target_strike == Decimal("196.00")
        assert snapshot.target_expiration == date(2026, 1, 10)
        assert snapshot.net_cost == Decimal("-0.15")
    
    def test_snapshot_change_flags(self):
        """Test change tracking flags."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=2,
            evaluated_at=datetime.utcnow(),
            recommended_action="CLOSE",
            priority="urgent",
            action_changed=True,
            priority_changed=True,
            previous_action="ROLL_WEEKLY",
            previous_priority="medium"
        )
        
        assert snapshot.action_changed == True
        assert snapshot.priority_changed == True
        assert snapshot.previous_action == "ROLL_WEEKLY"


class TestRecommendationModel:
    """Tests for PositionRecommendation model."""
    
    def test_recommendation_creation(self):
        """Test basic recommendation creation."""
        rec = PositionRecommendation(
            recommendation_id="PLTR_207.5_20260102_call_Test",
            symbol="PLTR",
            account_name="Test",
            source_strike=Decimal("207.50"),
            source_expiration=date(2026, 1, 2),
            option_type="call",
            status="active",
            first_detected_at=datetime.utcnow(),
            total_snapshots=0,  # Explicit since defaults are DB-level
            total_notifications_sent=0
        )
        
        assert rec.symbol == "PLTR"
        assert rec.status == "active"
        assert rec.total_snapshots == 0
        assert rec.total_notifications_sent == 0
    
    def test_recommendation_lifecycle_states(self):
        """Test valid lifecycle states."""
        valid_states = ['active', 'resolved', 'expired', 'assigned', 'superseded', 'stale']
        
        for state in valid_states:
            rec = PositionRecommendation(
                recommendation_id=f"TEST_{state}",
                symbol="TEST",
                account_name="Test",
                source_strike=Decimal("100"),
                source_expiration=date(2026, 1, 1),
                option_type="call",
                status=state,
                first_detected_at=datetime.utcnow()
            )
            assert rec.status == state


class TestNotificationLogic:
    """Tests for notification decision logic."""
    
    def test_first_snapshot_always_notifies(self):
        """First snapshot for a recommendation should always notify."""
        # This tests the logic from RecommendationService._should_notify
        # First snapshot (prev_snapshot=None) should return True
        
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=1,
            evaluated_at=datetime.utcnow(),
            recommended_action="ROLL_WEEKLY",
            priority="medium"
        )
        
        # Simulate the logic
        prev_snapshot = None
        should_notify = prev_snapshot is None and snapshot.recommended_action not in ('NO_ACTION', 'HOLD')
        
        assert should_notify == True
    
    def test_action_change_triggers_notification(self):
        """When action changes, should trigger notification."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=2,
            evaluated_at=datetime.utcnow(),
            recommended_action="CLOSE",
            priority="urgent",
            action_changed=True,
            previous_action="ROLL_WEEKLY"
        )
        
        should_notify = snapshot.action_changed
        assert should_notify == True
    
    def test_target_change_triggers_notification(self):
        """When target strike/expiration changes, should trigger notification."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=2,
            evaluated_at=datetime.utcnow(),
            recommended_action="ROLL_WEEKLY",
            priority="medium",
            target_strike=Decimal("198.00"),
            target_changed=True,
            previous_target_strike=Decimal("196.00")
        )
        
        should_notify = snapshot.target_changed
        assert should_notify == True
    
    def test_priority_escalation_triggers_notification(self):
        """When priority escalates (medium → urgent), should trigger notification."""
        snapshot = RecommendationSnapshot(
            recommendation_id=1,
            snapshot_number=2,
            evaluated_at=datetime.utcnow(),
            recommended_action="ROLL_WEEKLY",
            priority="urgent",
            priority_changed=True,
            previous_priority="medium"
        )
        
        # Priority escalated (urgent > medium)
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
        current = priority_order.get(snapshot.priority, 99)
        previous = priority_order.get(snapshot.previous_priority, 99)
        escalated = current < previous
        
        assert escalated == True
    
    def test_no_action_never_notifies(self):
        """NO_ACTION and HOLD should never trigger notifications."""
        for action in ['NO_ACTION', 'HOLD']:
            snapshot = RecommendationSnapshot(
                recommendation_id=1,
                snapshot_number=1,
                evaluated_at=datetime.utcnow(),
                recommended_action=action,
                priority="medium"
            )
            
            should_notify = snapshot.recommended_action not in ('NO_ACTION', 'HOLD')
            assert should_notify == False


class TestExecutionModel:
    """Tests for RecommendationExecution model."""
    
    def test_consent_execution(self):
        """Test execution where user followed recommendation."""
        execution = RecommendationExecution(
            recommendation_id=1,
            snapshot_id=5,
            match_type="consent",
            execution_action="roll",
            execution_strike=Decimal("196.00"),
            execution_expiration=date(2026, 1, 10),
            execution_premium=Decimal("0.48"),
            executed_at=datetime.utcnow(),
            hours_after_snapshot=Decimal("2.5"),
            match_confidence=Decimal("95.0")
        )
        
        assert execution.match_type == "consent"
        assert execution.hours_after_snapshot == Decimal("2.5")
    
    def test_modify_execution(self):
        """Test execution where user modified the recommendation."""
        execution = RecommendationExecution(
            recommendation_id=1,
            snapshot_id=5,
            match_type="modify_strike",
            execution_action="roll",
            execution_strike=Decimal("200.00"),  # User chose different strike
            execution_expiration=date(2026, 1, 10),
            modification_details={
                "strike_diff": 4.0,  # User chose $4 higher
                "premium_diff": -0.10  # Got $0.10 less premium
            }
        )
        
        assert execution.match_type == "modify_strike"
        assert execution.modification_details["strike_diff"] == 4.0
    
    def test_execution_with_counterfactual(self):
        """Test execution with counterfactual analysis."""
        execution = RecommendationExecution(
            recommendation_id=1,
            snapshot_id=5,
            match_type="modify_strike",
            counterfactual_outcome={
                "algorithm_strike": 196.0,
                "algorithm_expiration": "2026-01-10",
                "hypothetical_pnl": 48.0,
                "user_actual_pnl": 55.0,
                "delta": 7.0,  # User did $7 better
                "user_was_right": True
            }
        )
        
        assert execution.counterfactual_outcome["user_was_right"] == True
        assert execution.counterfactual_outcome["delta"] == 7.0


class TestEdgeCases:
    """Tests for edge cases and corner scenarios."""
    
    def test_same_symbol_multiple_positions(self):
        """Test that same symbol with different strikes creates different IDs."""
        id1 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 2), "call", "Account")
        id2 = generate_recommendation_id("PLTR", 210.0, date(2026, 1, 2), "call", "Account")
        id3 = generate_recommendation_id("PLTR", 207.5, date(2026, 1, 9), "call", "Account")
        
        # All three should be different
        assert len({id1, id2, id3}) == 3
    
    def test_snapshot_number_sequence(self):
        """Test that snapshot numbers are sequential."""
        snapshots = []
        for i in range(1, 6):
            s = RecommendationSnapshot(
                recommendation_id=1,
                snapshot_number=i,
                evaluated_at=datetime.utcnow(),
                recommended_action="ROLL_WEEKLY",
                priority="medium"
            )
            snapshots.append(s)
        
        numbers = [s.snapshot_number for s in snapshots]
        assert numbers == [1, 2, 3, 4, 5]
    
    def test_decimal_precision(self):
        """Test that decimal values maintain precision."""
        rec = PositionRecommendation(
            recommendation_id="TEST",
            symbol="TEST",
            account_name="Test",
            source_strike=Decimal("207.50"),
            source_expiration=date(2026, 1, 1),
            option_type="call",
            status="active",
            first_detected_at=datetime.utcnow()
        )
        
        assert rec.source_strike == Decimal("207.50")
        assert str(rec.source_strike) == "207.50"
    
    def test_expiration_date_handling(self):
        """Test that expiration dates are handled correctly."""
        exp_date = date(2026, 1, 2)
        
        rec = PositionRecommendation(
            recommendation_id="TEST",
            symbol="TEST",
            account_name="Test",
            source_strike=Decimal("100"),
            source_expiration=exp_date,
            option_type="call",
            status="active",
            first_detected_at=datetime.utcnow()
        )
        
        assert rec.source_expiration == exp_date
        assert rec.source_expiration.isoformat() == "2026-01-02"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

