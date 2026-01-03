"""
Reconciliation Service - Core RLHF Engine

This service matches algorithm recommendations to user executions,
enabling learning and pattern detection.

Key responsibilities:
1. Match recommendations to executions (daily job)
2. Classify match types (consent, modify, reject, independent)
3. Track position outcomes
4. Generate weekly learning summaries
5. Detect patterns in user behavior

Design Philosophy:
- Observe, don't judge (data collection, not rule enforcement)
- Algorithm stays pure (changes are proposed, not automatic)
- Human decides (weekly review of patterns and candidates)
"""

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, extract

from app.modules.strategies.learning_models import (
    RecommendationExecutionMatch,
    PositionOutcome,
    WeeklyLearningSummary,
    AlgorithmChange,
)
from app.modules.strategies.models import (
    StrategyRecommendationRecord,
    RecommendationNotification,
)
from app.modules.investments.models import InvestmentTransaction, InvestmentAccount

logger = logging.getLogger(__name__)


class MatchType(str, Enum):
    """Classification of how user responded to recommendation."""
    CONSENT = "consent"        # User followed recommendation closely
    MODIFY = "modify"          # User executed with modifications
    REJECT = "reject"          # Recommendation ignored, no action
    INDEPENDENT = "independent"  # User acted without recommendation
    NO_ACTION = "no_action"    # Recommendation sent, position resolved itself


@dataclass
class MatchResult:
    """Result of matching a recommendation to an execution."""
    match_type: MatchType
    confidence: float  # 0-100
    recommendation: Optional[StrategyRecommendationRecord] = None
    execution: Optional[InvestmentTransaction] = None
    modification_details: Dict[str, Any] = field(default_factory=dict)
    hours_to_execution: Optional[float] = None


class ReconciliationService:
    """
    Core service for matching recommendations to executions.
    
    Run daily at 9 PM PT after market close to reconcile
    the day's recommendations with actual trades.
    """
    
    # Matching thresholds
    STRIKE_TOLERANCE_PCT = 0.03  # 3% strike difference = still consent
    EXPIRATION_TOLERANCE_DAYS = 2  # ±2 days = still consent
    PREMIUM_TOLERANCE_PCT = 0.15  # 15% premium difference = still consent
    
    # Time windows
    MAX_HOURS_FOR_MATCH = 48  # Look up to 48 hours for matching execution
    
    def __init__(self, db: Session):
        self.db = db
    
    def reconcile_day(self, target_date: date) -> Dict[str, Any]:
        """
        Reconcile all recommendations and executions for a specific day.
        
        This is the main entry point, typically called at 9 PM PT.
        
        Returns summary of reconciliation results.
        """
        logger.info(f"Starting reconciliation for {target_date}")
        
        # 1. Get recommendations sent on this day
        recommendations = self._get_recommendations_for_date(target_date)
        logger.info(f"Found {len(recommendations)} recommendations for {target_date}")
        
        # 2. Get option executions on this day (and next day for delayed executions)
        executions = self._get_executions_for_date_range(
            target_date, 
            target_date + timedelta(days=1)
        )
        logger.info(f"Found {len(executions)} option executions")
        
        # 3. Match recommendations to executions
        matches = self._match_recommendations_to_executions(recommendations, executions)
        
        # 4. Find independent executions (no matching recommendation)
        matched_execution_ids = {m.execution.id for m in matches if m.execution}
        independent_executions = [e for e in executions if e.id not in matched_execution_ids]
        
        # 5. Save all matches to database
        saved_count = self._save_matches(matches, target_date)
        
        # 6. Save independent executions
        independent_count = self._save_independent_executions(independent_executions, target_date)
        
        # 7. Generate summary
        summary = {
            "date": target_date.isoformat(),
            "recommendations_count": len(recommendations),
            "executions_count": len(executions),
            "matches_saved": saved_count,
            "independent_actions": independent_count,
            "by_type": {
                "consent": sum(1 for m in matches if m.match_type == MatchType.CONSENT),
                "modify": sum(1 for m in matches if m.match_type == MatchType.MODIFY),
                "reject": sum(1 for m in matches if m.match_type == MatchType.REJECT),
                "no_action": sum(1 for m in matches if m.match_type == MatchType.NO_ACTION),
            }
        }
        
        logger.info(f"Reconciliation complete: {summary}")
        return summary
    
    def _get_recommendations_for_date(self, target_date: date) -> List[StrategyRecommendationRecord]:
        """
        Get all recommendations generated on a specific date.
        
        Note: We include ALL recommendations, not just those with notifications sent,
        because users can see recommendations in the dashboard even without push notifications.
        The RLHF system should learn from all visible recommendations.
        """
        return self.db.query(StrategyRecommendationRecord).filter(
            func.date(StrategyRecommendationRecord.created_at) == target_date,
        ).all()
    
    def _get_executions_for_date_range(
        self, 
        start_date: date, 
        end_date: date
    ) -> List[InvestmentTransaction]:
        """
        Get option transactions (STO, BTC, OEXP) for a date range.
        
        STO = Sell to Open (new position)
        BTC = Buy to Close (closing position)
        OEXP = Option Expiration
        """
        return self.db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_date >= start_date,
            InvestmentTransaction.transaction_date <= end_date,
            InvestmentTransaction.transaction_type.in_(['STO', 'BTC', 'OEXP'])
        ).all()
    
    def _match_recommendations_to_executions(
        self,
        recommendations: List[StrategyRecommendationRecord],
        executions: List[InvestmentTransaction]
    ) -> List[MatchResult]:
        """
        Match each recommendation to its best matching execution.
        
        Algorithm:
        1. For each recommendation, find candidate executions (same symbol)
        2. Score each candidate on strike, expiration, timing
        3. Pick best match if score above threshold
        4. Classify match type based on differences
        """
        matches = []
        used_executions = set()
        
        for rec in recommendations:
            # Extract symbol from recommendation
            rec_symbol = self._extract_symbol_from_recommendation(rec)
            if not rec_symbol:
                # Can't match without symbol - mark as no_action
                matches.append(MatchResult(
                    match_type=MatchType.NO_ACTION,
                    confidence=100.0,
                    recommendation=rec
                ))
                continue
            
            # Find candidate executions for this symbol
            candidates = [
                e for e in executions 
                if e.id not in used_executions 
                and self._symbols_match(e.symbol, rec_symbol)
            ]
            
            if not candidates:
                # No matching execution found - either reject or no_action
                match_type = self._determine_no_execution_type(rec)
                matches.append(MatchResult(
                    match_type=match_type,
                    confidence=100.0,
                    recommendation=rec
                ))
                continue
            
            # Score candidates and find best match
            best_match = None
            best_score = 0
            
            for exec in candidates:
                score, details = self._score_match(rec, exec)
                if score > best_score:
                    best_score = score
                    best_match = (exec, details)
            
            if best_match and best_score >= 50:  # Minimum 50% match score
                exec, details = best_match
                used_executions.add(exec.id)
                
                # Classify the match type
                match_type = self._classify_match(rec, exec, details)
                
                # Calculate time to execution
                hours_to_exec = self._calculate_hours_to_execution(rec, exec)
                
                matches.append(MatchResult(
                    match_type=match_type,
                    confidence=best_score,
                    recommendation=rec,
                    execution=exec,
                    modification_details=details if match_type == MatchType.MODIFY else {},
                    hours_to_execution=hours_to_exec
                ))
            else:
                # No good match - mark as reject
                matches.append(MatchResult(
                    match_type=MatchType.REJECT,
                    confidence=100.0,
                    recommendation=rec
                ))
        
        return matches
    
    def _extract_symbol_from_recommendation(self, rec: StrategyRecommendationRecord) -> Optional[str]:
        """Extract the underlying symbol from a recommendation."""
        # First try the symbol field directly
        if rec.symbol:
            return rec.symbol.upper()
        
        # Try context snapshot
        if rec.context_snapshot:
            context = rec.context_snapshot
            if isinstance(context, dict):
                for key in ['symbol', 'underlying', 'stock']:
                    if key in context:
                        return str(context[key]).upper()
        
        return None
    
    def _symbols_match(self, execution_symbol: str, rec_symbol: str) -> bool:
        """
        Check if execution symbol matches recommendation symbol.
        
        Execution symbols can be complex like "NVDA 01/10/2025 Put $130.00"
        while recommendation symbols are simple like "NVDA".
        """
        if not execution_symbol or not rec_symbol:
            return False
        
        # Extract underlying from execution symbol
        exec_underlying = execution_symbol.split()[0].upper()
        return exec_underlying == rec_symbol.upper()
    
    def _score_match(
        self, 
        rec: StrategyRecommendationRecord, 
        exec: InvestmentTransaction
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score how well an execution matches a recommendation.
        
        Returns (score 0-100, modification details dict).
        """
        score = 100.0
        details = {}
        
        # Extract recommendation details from context
        context = rec.context_snapshot or {}
        rec_strike = context.get('strike') or context.get('recommended_strike')
        rec_expiration = context.get('expiration') or context.get('recommended_expiration')
        rec_premium = context.get('premium') or context.get('expected_premium')
        
        # Parse execution details from description/symbol (description has full option details)
        exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
        exec_premium = float(exec.amount) / (float(exec.quantity or 1) * 100) if exec.quantity else None
        
        # Compare strike
        if rec_strike and exec_strike:
            strike_diff = abs(float(exec_strike) - float(rec_strike))
            strike_pct_diff = strike_diff / float(rec_strike) if float(rec_strike) > 0 else 0
            
            if strike_pct_diff > self.STRIKE_TOLERANCE_PCT:
                score -= min(30, strike_pct_diff * 100)  # Max 30 point penalty
                details['strike_diff'] = float(exec_strike) - float(rec_strike)
                details['strike_pct_diff'] = strike_pct_diff
        
        # Compare expiration
        if rec_expiration and exec_expiration:
            if isinstance(rec_expiration, str):
                try:
                    rec_exp_date = datetime.strptime(rec_expiration, '%Y-%m-%d').date()
                except ValueError:
                    rec_exp_date = None
            else:
                rec_exp_date = rec_expiration
            
            if rec_exp_date and exec_expiration:
                days_diff = (exec_expiration - rec_exp_date).days
                
                if abs(days_diff) > self.EXPIRATION_TOLERANCE_DAYS:
                    score -= min(30, abs(days_diff) * 2)  # 2 points per day, max 30
                    details['expiration_diff_days'] = days_diff
        
        # Compare premium (less important)
        if rec_premium and exec_premium:
            premium_diff = exec_premium - float(rec_premium)
            premium_pct_diff = abs(premium_diff) / float(rec_premium) if float(rec_premium) > 0 else 0
            
            if premium_pct_diff > self.PREMIUM_TOLERANCE_PCT:
                score -= min(20, premium_pct_diff * 50)  # Max 20 point penalty
                details['premium_diff'] = premium_diff
        
        # Action type match bonus
        rec_action = rec.action_type
        exec_action = exec.transaction_type
        if self._actions_align(rec_action, exec_action):
            score = min(100, score + 10)  # Bonus for aligned action
        
        return max(0, score), details
    
    def _parse_option_from_symbol(self, symbol: str, description: str = None) -> Tuple[Optional[Decimal], Optional[date]]:
        """
        Parse option details from symbol/description like "NVDA 01/10/2025 Put $130.00".
        
        The description field typically has the full option details, so we check that first.
        
        Returns (strike, expiration_date).
        """
        # Check description first (more detailed), then fall back to symbol
        text = description or symbol
        if not text:
            return None, None
        
        parts = text.split()
        strike = None
        expiration = None
        
        for part in parts:
            # Look for strike price
            if part.startswith('$'):
                try:
                    strike = Decimal(part.replace('$', '').replace(',', ''))
                except:
                    pass
            
            # Look for date - try multiple formats
            if '/' in part:
                for fmt in ['%m/%d/%Y', '%Y/%m/%d', '%m/%d/%y', '%d/%m/%Y']:
                    try:
                        expiration = datetime.strptime(part, fmt).date()
                        break
                    except:
                        pass
        
        return strike, expiration
    
    def _actions_align(self, rec_action: Optional[str], exec_action: Optional[str]) -> bool:
        """Check if recommendation action aligns with execution type."""
        if not rec_action or not exec_action:
            return True  # Unknown = assume aligned
        
        rec_action = rec_action.lower()
        exec_action = exec_action.upper()
        
        alignments = {
            'sell': ['STO'],
            'roll': ['STO', 'BTC'],
            'close': ['BTC'],
            'buy_to_close': ['BTC'],
        }
        
        return exec_action in alignments.get(rec_action, [exec_action])
    
    def _classify_match(
        self,
        rec: StrategyRecommendationRecord,
        exec: InvestmentTransaction,
        details: Dict[str, Any]
    ) -> MatchType:
        """
        Classify the match type based on differences.
        
        Consent: Close enough to recommendation
        Modify: Same symbol but different parameters
        """
        # If no significant modifications, it's consent
        if not details:
            return MatchType.CONSENT
        
        # Check if modifications are significant
        significant = False
        
        strike_diff = abs(details.get('strike_diff', 0))
        exp_diff = abs(details.get('expiration_diff_days', 0))
        
        # Strike diff > 3% or expiration diff > 2 days = modification
        if strike_diff > 0 or exp_diff > 2:
            significant = True
        
        return MatchType.MODIFY if significant else MatchType.CONSENT
    
    def _determine_no_execution_type(self, rec: StrategyRecommendationRecord) -> MatchType:
        """
        Determine if no execution means reject or no_action.
        
        No action: Position resolved itself (expired worthless, hit target, etc.)
        Reject: User chose not to act on recommendation
        """
        # Check if this was an informational recommendation
        if rec.recommendation_type in ['earnings_alert', 'dividend_alert', 'monitor']:
            return MatchType.NO_ACTION
        
        # Check if position status changed (would need to check sold_options table)
        # For now, default to reject if no execution found
        return MatchType.REJECT
    
    def _calculate_hours_to_execution(
        self,
        rec: StrategyRecommendationRecord,
        exec: InvestmentTransaction
    ) -> Optional[float]:
        """Calculate hours between recommendation and execution."""
        rec_time = rec.notification_sent_at or rec.created_at
        
        # Execution doesn't have exact time, so estimate
        exec_time = datetime.combine(exec.transaction_date, datetime.min.time())
        exec_time = exec_time.replace(hour=10)  # Assume 10 AM execution
        
        delta = exec_time - rec_time
        return delta.total_seconds() / 3600  # Convert to hours
    
    def _save_matches(self, matches: List[MatchResult], target_date: date) -> int:
        """Save match results to database."""
        saved = 0
        iso_cal = target_date.isocalendar()
        
        for match in matches:
            try:
                rec = match.recommendation
                exec = match.execution
                
                # Extract recommendation details from context or recommendation_id
                rec_strike = None
                rec_expiration = None
                rec_premium = None
                
                if rec:
                    context = rec.context_snapshot or {}
                    # Check multiple key names since different recommendation types use different keys
                    rec_strike = (
                        context.get('strike') or 
                        context.get('recommended_strike') or 
                        context.get('target_strike') or
                        context.get('new_strike')  # For roll recommendations
                    )
                    rec_expiration = (
                        context.get('expiration') or 
                        context.get('recommended_expiration') or 
                        context.get('target_expiration') or
                        context.get('expiration_date') or  # Common key in context
                        context.get('new_expiration')  # For roll recommendations
                    )
                    rec_premium = (
                        context.get('premium') or 
                        context.get('expected_premium') or 
                        context.get('target_premium') or
                        context.get('potential_premium') or
                        context.get('net_credit')  # For spread recommendations
                    )
                    
                    # Try to parse from recommendation_id if not in context
                    # Format: v3_roll_weekly_PLTR_207.5_Neels_Brokerage
                    if not rec_strike and rec.recommendation_id:
                        parts = rec.recommendation_id.split('_')
                        if len(parts) >= 5:
                            try:
                                rec_strike = Decimal(parts[4])  # Strike is typically 5th element
                            except (ValueError, InvalidOperation):
                                pass
                    
                    # Convert rec_expiration to date if it's a string
                    if rec_expiration and isinstance(rec_expiration, str):
                        try:
                            rec_expiration = datetime.strptime(rec_expiration, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                rec_expiration = datetime.strptime(rec_expiration, '%m/%d/%Y').date()
                            except ValueError:
                                rec_expiration = None
                
                # Parse execution details from symbol (e.g., "PLTR 01/09/2026 Call $182.50")
                exec_strike = None
                exec_expiration = None
                exec_account = None
                
                if exec:
                    exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
                    exec_account = exec.account_id  # Use account_id from transaction
                
                # Build the match record with all details
                db_match = RecommendationExecutionMatch(
                    # Recommendation side
                    recommendation_id=rec.recommendation_id if rec else None,
                    recommendation_record_id=rec.id if rec else None,
                    recommendation_date=target_date,
                    recommendation_time=rec.notification_sent_at if rec else None,
                    recommendation_type=rec.recommendation_type if rec else None,
                    recommended_action=rec.action_type if rec else None,
                    recommended_symbol=rec.symbol if rec else None,
                    recommended_strike=Decimal(str(rec_strike)) if rec_strike else None,
                    recommended_expiration=rec_expiration if isinstance(rec_expiration, date) else None,
                    recommended_premium=Decimal(str(rec_premium)) if rec_premium else None,
                    recommendation_priority=rec.priority if rec else None,
                    recommendation_context=rec.context_snapshot if rec else None,
                    
                    # Execution side
                    execution_id=exec.id if exec else None,
                    execution_date=exec.transaction_date if exec else None,
                    execution_action=exec.transaction_type if exec else None,
                    execution_symbol=exec.symbol if exec else None,
                    execution_strike=exec_strike if exec_strike else None,
                    execution_expiration=exec_expiration if exec_expiration else None,
                    execution_premium=Decimal(str(abs(float(exec.amount or 0)))) if exec else None,
                    execution_contracts=int(exec.quantity or 1) if exec else None,
                    execution_account=exec_account if exec_account else None,
                    
                    # Match analysis
                    match_type=match.match_type.value,
                    match_confidence=Decimal(str(match.confidence)),
                    modification_details=match.modification_details if match.modification_details else None,
                    hours_to_execution=Decimal(str(match.hours_to_execution)) if match.hours_to_execution else None,
                    
                    # Week tracking
                    year=iso_cal.year,
                    week_number=iso_cal.week,
                    reconciled_at=datetime.utcnow(),
                )
                
                self.db.add(db_match)
                saved += 1
                
            except Exception as e:
                logger.error(f"Error saving match: {e}")
                continue
        
        self.db.commit()
        return saved
    
    def _save_independent_executions(
        self, 
        executions: List[InvestmentTransaction],
        target_date: date
    ) -> int:
        """Save independent executions (no matching recommendation)."""
        saved = 0
        iso_cal = target_date.isocalendar()
        
        for exec in executions:
            try:
                # Parse execution details from description (has full option details)
                exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
                exec_account = exec.account_id
                
                db_match = RecommendationExecutionMatch(
                    recommendation_date=target_date,
                    
                    # Execution side with full details
                    execution_id=exec.id,
                    execution_date=exec.transaction_date,
                    execution_action=exec.transaction_type,
                    execution_symbol=exec.symbol,
                    execution_strike=exec_strike if exec_strike else None,
                    execution_expiration=exec_expiration if exec_expiration else None,
                    execution_premium=Decimal(str(abs(float(exec.amount or 0)))),
                    execution_contracts=int(exec.quantity or 1),
                    execution_account=exec_account if exec_account else None,
                    
                    # Mark as independent
                    match_type=MatchType.INDEPENDENT.value,
                    match_confidence=Decimal('100.0'),
                    
                    # Week tracking
                    year=iso_cal.year,
                    week_number=iso_cal.week,
                    reconciled_at=datetime.utcnow(),
                )
                
                self.db.add(db_match)
                saved += 1
                
            except Exception as e:
                logger.error(f"Error saving independent execution: {e}")
                continue
        
        self.db.commit()
        return saved
    
    # =========================================================================
    # OUTCOME TRACKING
    # =========================================================================
    
    def track_position_outcomes(self, as_of_date: date = None) -> Dict[str, Any]:
        """
        Track outcomes for positions that have completed.
        
        A position is complete when it:
        - Expired (past expiration date)
        - Was closed (BTC transaction found)
        - Was assigned (OASGN transaction found)
        
        Run daily to update outcomes.
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        # Find matches without outcomes where position should be complete
        pending_matches = self.db.query(RecommendationExecutionMatch).outerjoin(
            PositionOutcome
        ).filter(
            PositionOutcome.id == None,  # No outcome yet
            RecommendationExecutionMatch.execution_id != None,  # Has execution
        ).all()
        
        tracked = 0
        for match in pending_matches:
            outcome = self._determine_position_outcome(match, as_of_date)
            if outcome:
                self.db.add(outcome)
                tracked += 1
        
        self.db.commit()
        
        return {
            "date": as_of_date.isoformat(),
            "pending_checked": len(pending_matches),
            "outcomes_tracked": tracked
        }
    
    def _determine_position_outcome(
        self,
        match: RecommendationExecutionMatch,
        as_of_date: date
    ) -> Optional[PositionOutcome]:
        """Determine if a position has an outcome and what it was."""
        
        # Parse position details from execution
        if not match.execution_symbol:
            return None
        
        strike, expiration = self._parse_option_from_symbol(match.execution_symbol)
        
        if not expiration:
            return None
        
        # Check if position is past expiration
        if expiration > as_of_date:
            return None  # Still active
        
        # Look for closing transaction (BTC) for this position
        closing_txn = self._find_closing_transaction(match)
        
        # Determine status
        if closing_txn:
            if closing_txn.transaction_type == 'BTC':
                status = 'closed_profit' if float(closing_txn.amount) < float(match.execution_premium or 0) else 'closed_loss'
                premium_paid = Decimal(str(abs(float(closing_txn.amount))))
            elif closing_txn.transaction_type == 'OASGN':
                status = 'assigned'
                premium_paid = None
            else:
                status = 'closed_profit'
                premium_paid = None
        else:
            # No closing transaction = expired worthless
            status = 'expired_worthless'
            premium_paid = Decimal('0')
        
        # Calculate profit
        premium_received = match.execution_premium or Decimal('0')
        if status == 'expired_worthless':
            net_profit = premium_received
        elif premium_paid:
            net_profit = premium_received - premium_paid
        else:
            net_profit = None
        
        profit_pct = (net_profit / premium_received * 100) if premium_received and net_profit else None
        
        # Parse option type from symbol
        option_type = 'put' if 'Put' in (match.execution_symbol or '') else 'call'
        
        return PositionOutcome(
            match_id=match.id,
            symbol=match.execution_symbol.split()[0] if match.execution_symbol else 'UNKNOWN',
            strike=strike or Decimal('0'),
            expiration_date=expiration,
            option_type=option_type,
            contracts=match.execution_contracts or 1,
            account=match.execution_account,
            final_status=status,
            premium_received=premium_received,
            premium_paid_to_close=premium_paid,
            net_profit=net_profit,
            profit_percent=profit_pct,
            days_held=(expiration - match.execution_date).days if match.execution_date else None,
            tracked_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
    
    def _find_closing_transaction(
        self,
        match: RecommendationExecutionMatch
    ) -> Optional[InvestmentTransaction]:
        """Find the closing transaction for a position."""
        if not match.execution_symbol or not match.execution_date:
            return None
        
        # Look for BTC or OASGN transaction for same option
        # This is a simplified match - in practice you'd parse the option details
        symbol_prefix = match.execution_symbol.split()[0]
        
        closing = self.db.query(InvestmentTransaction).filter(
            InvestmentTransaction.transaction_type.in_(['BTC', 'OASGN', 'OEXP']),
            InvestmentTransaction.symbol.like(f'{symbol_prefix}%'),
            InvestmentTransaction.transaction_date > match.execution_date
        ).order_by(InvestmentTransaction.transaction_date.asc()).first()
        
        return closing
    
    # =========================================================================
    # WEEKLY LEARNING SUMMARY
    # =========================================================================
    
    def generate_weekly_summary(self, year: int, week_number: int) -> WeeklyLearningSummary:
        """
        Generate weekly learning summary.
        
        Run every Saturday morning to analyze the past week.
        """
        # Calculate week date range
        week_start = date.fromisocalendar(year, week_number, 1)  # Monday
        week_end = date.fromisocalendar(year, week_number, 7)    # Sunday
        
        # Check if summary already exists
        existing = self.db.query(WeeklyLearningSummary).filter(
            WeeklyLearningSummary.year == year,
            WeeklyLearningSummary.week_number == week_number
        ).first()
        
        if existing:
            logger.info(f"Weekly summary already exists for {year}-W{week_number}")
            return existing
        
        # Get all matches for the week
        matches = self.db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.year == year,
            RecommendationExecutionMatch.week_number == week_number
        ).all()
        
        # Get outcomes for these matches
        match_ids = [m.id for m in matches]
        outcomes = self.db.query(PositionOutcome).filter(
            PositionOutcome.match_id.in_(match_ids)
        ).all() if match_ids else []
        
        # Count by match type
        type_counts = {mt.value: 0 for mt in MatchType}
        for match in matches:
            type_counts[match.match_type] = type_counts.get(match.match_type, 0) + 1
        
        # Count by recommendation type
        rec_type_counts = {}
        for match in matches:
            if match.recommendation_type:
                rec_type_counts[match.recommendation_type] = rec_type_counts.get(match.recommendation_type, 0) + 1
        
        # Calculate P&L
        actual_pnl = sum(float(o.net_profit or 0) for o in outcomes)
        
        # Detect patterns
        patterns = self._detect_patterns(matches, outcomes)
        
        # Generate V4 candidates from patterns
        v4_candidates = self._generate_v4_candidates(patterns)
        
        # Create summary
        summary = WeeklyLearningSummary(
            year=year,
            week_number=week_number,
            week_start=week_start,
            week_end=week_end,
            
            total_recommendations=len([m for m in matches if m.recommendation_id]),
            total_executions=len([m for m in matches if m.execution_id]),
            
            consent_count=type_counts.get('consent', 0),
            modify_count=type_counts.get('modify', 0),
            reject_count=type_counts.get('reject', 0),
            independent_count=type_counts.get('independent', 0),
            no_action_count=type_counts.get('no_action', 0),
            
            recommendations_by_type=rec_type_counts if rec_type_counts else None,
            
            actual_pnl=Decimal(str(actual_pnl)),
            actual_trades=len(outcomes),
            
            patterns_observed=patterns if patterns else None,
            v4_candidates=v4_candidates if v4_candidates else None,
            
            generated_at=datetime.utcnow(),
        )
        
        self.db.add(summary)
        self.db.commit()
        
        logger.info(f"Generated weekly summary for {year}-W{week_number}")
        return summary
    
    def _detect_patterns(
        self,
        matches: List[RecommendationExecutionMatch],
        outcomes: List[PositionOutcome]
    ) -> List[Dict[str, Any]]:
        """
        Detect patterns in user behavior.
        
        Looks for:
        - Consistent modifications (DTE, strike, premium threshold)
        - Symbol preferences
        - Time-of-day patterns
        - Rejection patterns
        """
        patterns = []
        
        # Pattern 1: DTE modifications
        dte_mods = [
            m.modification_details.get('expiration_diff_days', 0)
            for m in matches 
            if m.match_type == 'modify' and m.modification_details
        ]
        
        if len(dte_mods) >= 3:
            avg_dte_diff = sum(dte_mods) / len(dte_mods)
            if abs(avg_dte_diff) > 3:  # Average of 3+ days difference
                patterns.append({
                    'pattern_id': 'prefer_longer_dte' if avg_dte_diff > 0 else 'prefer_shorter_dte',
                    'description': f'User {"adds" if avg_dte_diff > 0 else "reduces"} {abs(avg_dte_diff):.0f} days on average',
                    'occurrences': len(dte_mods),
                    'avg_modification': avg_dte_diff,
                    'confidence': 'high' if len(dte_mods) >= 5 else 'medium'
                })
        
        # Pattern 2: Strike modifications
        strike_mods = [
            m.modification_details.get('strike_diff', 0)
            for m in matches
            if m.match_type == 'modify' and m.modification_details
        ]
        
        if len(strike_mods) >= 3:
            avg_strike_diff = sum(strike_mods) / len(strike_mods)
            if abs(avg_strike_diff) > 2:  # $2+ average difference
                patterns.append({
                    'pattern_id': 'prefer_higher_strike' if avg_strike_diff > 0 else 'prefer_lower_strike',
                    'description': f'User chooses strike ${abs(avg_strike_diff):.0f} {"higher" if avg_strike_diff > 0 else "lower"}',
                    'occurrences': len(strike_mods),
                    'avg_modification': avg_strike_diff,
                    'confidence': 'high' if len(strike_mods) >= 5 else 'medium'
                })
        
        # Pattern 3: Rejection of low-premium recommendations
        rejected = [
            m for m in matches 
            if m.match_type == 'reject' and m.recommendation_context
        ]
        
        if rejected:
            # Check if rejections correlate with low premium
            rejected_premiums = [
                m.recommendation_context.get('premium', 0) 
                for m in rejected 
                if m.recommendation_context and m.recommendation_context.get('premium')
            ]
            if rejected_premiums and sum(rejected_premiums) / len(rejected_premiums) < 0.30:
                patterns.append({
                    'pattern_id': 'reject_low_premium',
                    'description': 'User tends to reject low-premium recommendations',
                    'occurrences': len(rejected),
                    'avg_rejected_premium': sum(rejected_premiums) / len(rejected_premiums),
                    'confidence': 'medium'
                })
        
        return patterns
    
    def _generate_v4_candidates(self, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate V4 algorithm change candidates from patterns."""
        candidates = []
        
        for pattern in patterns:
            pattern_id = pattern.get('pattern_id', '')
            
            if pattern_id == 'prefer_longer_dte':
                candidates.append({
                    'candidate_id': 'v4_adjust_default_dte',
                    'change_type': 'parameter',
                    'description': f'Increase default DTE by {pattern.get("avg_modification", 7):.0f} days',
                    'evidence': f'{pattern.get("occurrences", 0)} modifications observed',
                    'priority': 'high' if pattern.get('confidence') == 'high' else 'medium',
                    'risk': 'May reduce premium capture',
                    'decision': None
                })
            
            elif pattern_id == 'reject_low_premium':
                candidates.append({
                    'candidate_id': 'v4_min_premium_filter',
                    'change_type': 'filter',
                    'description': f'Add minimum premium filter (${pattern.get("avg_rejected_premium", 0.25):.2f})',
                    'evidence': f'{pattern.get("occurrences", 0)} rejections of low-premium recs',
                    'priority': 'medium',
                    'risk': 'May miss some opportunities',
                    'decision': None
                })
            
            elif pattern_id.startswith('prefer_') and 'strike' in pattern_id:
                candidates.append({
                    'candidate_id': 'v4_adjust_strike_selection',
                    'change_type': 'parameter',
                    'description': f'Adjust strike selection by ${abs(pattern.get("avg_modification", 0)):.0f}',
                    'evidence': f'{pattern.get("occurrences", 0)} strike modifications',
                    'priority': 'medium',
                    'risk': 'May affect risk/reward balance',
                    'decision': None
                })
        
        return candidates


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def get_reconciliation_service(db: Session) -> ReconciliationService:
    """Factory function to get ReconciliationService instance."""
    return ReconciliationService(db)

