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
from datetime import datetime, date, timedelta, time
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
from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    RecommendationExecution,
    generate_recommendation_id,
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
class V2SnapshotAdapter:
    """
    Adapter that wraps V2 RecommendationSnapshot to provide 
    a V1-compatible interface for the reconciliation logic.
    """
    snapshot: 'RecommendationSnapshot'
    position: 'PositionRecommendation'
    
    @property
    def id(self) -> int:
        return self.snapshot.id
    
    @property
    def recommendation_id(self) -> str:
        return self.position.recommendation_id
    
    @property
    def symbol(self) -> str:
        return self.position.symbol
    
    @property
    def account_name(self) -> str:
        return self.position.account_name
    
    @property
    def action_type(self) -> str:
        return self.snapshot.recommended_action
    
    @property
    def recommendation_type(self) -> str:
        # Map V2 actions to V1-style types
        action = self.snapshot.recommended_action or ''
        if action.upper() in ['ROLL', 'ROLL_OUT', 'ROLL_UP']:
            return 'roll'
        elif action.upper() in ['CLOSE', 'CLOSE_DONT_ROLL', 'BUY_TO_CLOSE']:
            return 'close'
        elif action.upper() in ['HOLD', 'WAIT']:
            return 'hold'
        elif action.upper() in ['MONITOR', 'WATCH']:
            return 'monitor'
        elif action.upper() in ['SELL', 'STO', 'SELL_TO_OPEN']:
            return 'sell'
        return action.lower() if action else 'unknown'
    
    @property
    def priority(self) -> str:
        return self.snapshot.priority
    
    @property
    def notification_sent_at(self) -> Optional[datetime]:
        return self.snapshot.notification_sent_at
    
    @property
    def created_at(self) -> datetime:
        return self.snapshot.created_at
    
    @property
    def context_snapshot(self) -> Dict[str, Any]:
        """Build V1-compatible context from V2 snapshot fields."""
        context = self.snapshot.full_context or {}
        
        # Ensure key fields are present from snapshot fields
        if self.snapshot.target_strike:
            context['target_strike'] = float(self.snapshot.target_strike)
            context['strike_price'] = float(self.snapshot.target_strike)
        if self.snapshot.target_expiration:
            context['target_expiration'] = str(self.snapshot.target_expiration)
        if self.snapshot.target_premium:
            context['target_premium'] = float(self.snapshot.target_premium)
            context['new_premium'] = float(self.snapshot.target_premium)
        if self.snapshot.net_cost:
            context['net_cost'] = float(self.snapshot.net_cost)
        if self.snapshot.estimated_cost_to_close:
            context['close_cost'] = float(self.snapshot.estimated_cost_to_close)
        if self.position.source_strike:
            context['current_strike'] = float(self.position.source_strike)
        if self.position.source_expiration:
            context['current_expiration'] = str(self.position.source_expiration)
        if self.position.source_contracts:
            context['contracts'] = self.position.source_contracts
        
        context['account_name'] = self.position.account_name
        context['symbol'] = self.position.symbol
        
        return context


@dataclass
class MatchResult:
    """Result of matching a recommendation to an execution."""
    match_type: MatchType
    confidence: float  # 0-100
    recommendation: Optional[Any] = None  # Can be StrategyRecommendationRecord or V2SnapshotAdapter
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
    
    def _get_recommendations_for_date(self, target_date: date) -> List[V2SnapshotAdapter]:
        """
        Get all V2 recommendations (snapshots) that were sent to the user on a specific date.
        
        Only includes snapshots where notification_sent_at is set, meaning the user
        actually received this notification. This is key for accurate RLHF learning.
        """
        # Query V2 snapshots where notifications were actually sent
        snapshots = self.db.query(RecommendationSnapshot).join(
            PositionRecommendation,
            RecommendationSnapshot.recommendation_id == PositionRecommendation.id
        ).filter(
            RecommendationSnapshot.notification_sent_at.isnot(None),
            func.date(RecommendationSnapshot.notification_sent_at) == target_date,
        ).all()
        
        # Wrap in adapters for V1-compatible interface
        result = []
        for snapshot in snapshots:
            position = snapshot.recommendation  # Use the relationship
            if position:
                result.append(V2SnapshotAdapter(snapshot=snapshot, position=position))
            else:
                logger.warning(f"Snapshot {snapshot.id} has no parent PositionRecommendation")
        
        return result
    
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
        recommendations: List[V2SnapshotAdapter],
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
    
    def _extract_symbol_from_recommendation(self, rec: Any) -> Optional[str]:
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
        rec: Any, 
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
        rec_strike = (
            context.get('strike') or 
            context.get('recommended_strike') or 
            context.get('strike_price') or  # Used in sell_unsold_contracts and new_covered_call
            context.get('target_strike') or
            context.get('new_strike')  # For roll recommendations
        )
        rec_expiration = (
            context.get('expiration') or 
            context.get('recommended_expiration') or
            context.get('expiration_date') or  # Common key in context
            context.get('target_expiration') or
            context.get('new_expiration')  # For roll recommendations
        )
        # Try premium_per_contract first (per-contract value)
        rec_premium = (
            context.get('premium') or 
            context.get('expected_premium') or
            context.get('premium_per_contract') or  # Used in sell_unsold_contracts and new_covered_call
            context.get('target_premium') or
            context.get('potential_premium') or
            context.get('net_credit')  # For spread recommendations
        )
        
        # If we didn't find per-contract premium, try total_premium and divide by contracts
        if not rec_premium and context.get('total_premium'):
            contracts = context.get('contracts') or context.get('unsold_contracts') or 1
            if contracts > 0:
                rec_premium = float(context.get('total_premium')) / contracts
        
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
        rec: Any,
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
    
    def _determine_no_execution_type(self, rec: Any) -> MatchType:
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
        rec: Any,
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
                        context.get('strike_price') or  # Used in sell_unsold_contracts and new_covered_call
                        context.get('target_strike') or
                        context.get('new_strike')  # For roll recommendations
                    )
                    rec_expiration = (
                        context.get('expiration') or 
                        context.get('recommended_expiration') or 
                        context.get('expiration_date') or  # Common key in context
                        context.get('target_expiration') or
                        context.get('new_expiration')  # For roll recommendations
                    )
                    # Try premium_per_contract first (per-contract value)
                    # For roll recommendations, prioritize new_premium (premium for the new position)
                    rec_premium = (
                        context.get('new_premium') or  # Premium for new position in roll
                        context.get('estimated_new_premium') or  # Alternative key for new premium
                        context.get('new_premium_income') or  # Income from new position
                        # Standard premium keys
                        context.get('premium') or 
                        context.get('expected_premium') or 
                        context.get('premium_per_contract') or  # Used in sell_unsold_contracts and new_covered_call
                        context.get('target_premium') or
                        context.get('potential_premium') or
                        context.get('net_credit')  # For spread recommendations
                    )
                    
                    # If we didn't find per-contract premium, try total_premium and divide by contracts
                    # Note: We store per-contract premium in recommended_premium field
                    if not rec_premium and context.get('total_premium'):
                        contracts = context.get('contracts') or context.get('unsold_contracts') or 1
                        if contracts > 0:
                            rec_premium = float(context.get('total_premium')) / contracts
                    
                    # Also extract contracts for the match record
                    rec_contracts = context.get('contracts') or context.get('unsold_contracts')
                    
                    # Extract account name - try context first, then direct field
                    rec_account = (
                        context.get('account_name') or 
                        context.get('account') or
                        getattr(rec, 'account_name', None)  # V2SnapshotAdapter provides this
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
                
                # Check if match already exists to avoid duplicates
                existing_match = None
                if rec and exec:
                    # Try to find existing match by recommendation_record_id + execution_id
                    existing_match = self.db.query(RecommendationExecutionMatch).filter(
                        RecommendationExecutionMatch.recommendation_record_id == rec.id,
                        RecommendationExecutionMatch.execution_id == exec.id,
                        RecommendationExecutionMatch.recommendation_date == target_date
                    ).first()
                elif rec:
                    # For reject/no_action matches, check by recommendation_record_id + date
                    existing_match = self.db.query(RecommendationExecutionMatch).filter(
                        RecommendationExecutionMatch.recommendation_record_id == rec.id,
                        RecommendationExecutionMatch.recommendation_date == target_date,
                        RecommendationExecutionMatch.execution_id.is_(None)
                    ).first()
                
                if existing_match:
                    # Update existing match with latest data
                    # Use notification_sent_at if available, otherwise fall back to created_at
                    existing_match.recommendation_time = rec.notification_sent_at if rec and rec.notification_sent_at else (rec.created_at if rec else None)
                    existing_match.recommendation_type = rec.recommendation_type if rec else None
                    existing_match.recommended_action = rec.action_type if rec else None
                    existing_match.recommended_symbol = rec.symbol if rec else None
                    existing_match.recommended_strike = Decimal(str(rec_strike)) if rec_strike else None
                    existing_match.recommended_expiration = rec_expiration if isinstance(rec_expiration, date) else None
                    existing_match.recommended_premium = Decimal(str(rec_premium)) if rec_premium else None
                    existing_match.recommended_contracts = int(rec_contracts) if rec_contracts else None
                    existing_match.recommendation_priority = rec.priority if rec else None
                    existing_match.recommendation_context = rec.context_snapshot if rec else None
                    
                    if exec:
                        existing_match.execution_date = exec.transaction_date
                        # Convert transaction_date (Date) to DateTime for execution_time
                        # Use 9:30 AM as default time (market open) if we only have date
                        if exec.transaction_date:
                            existing_match.execution_time = datetime.combine(exec.transaction_date, time(9, 30))
                        existing_match.execution_action = exec.transaction_type
                        existing_match.execution_symbol = exec.symbol
                        existing_match.execution_strike = exec_strike if exec_strike else None
                        existing_match.execution_expiration = exec_expiration if exec_expiration else None
                        existing_match.execution_premium = Decimal(str(abs(float(exec.amount or 0))))
                        existing_match.execution_contracts = int(exec.quantity or 1)
                        existing_match.execution_account = exec_account if exec_account else None
                    
                    existing_match.match_type = match.match_type.value
                    existing_match.match_confidence = Decimal(str(match.confidence))
                    existing_match.modification_details = match.modification_details if match.modification_details else None
                    existing_match.hours_to_execution = Decimal(str(match.hours_to_execution)) if match.hours_to_execution else None
                    existing_match.reconciled_at = datetime.utcnow()
                    existing_match.updated_at = datetime.utcnow()
                    
                    # Week tracking
                    existing_match.year = iso_cal.year
                    existing_match.week_number = iso_cal.week
                else:
                    # Create new match record
                    db_match = RecommendationExecutionMatch(
                        # Recommendation side
                        recommendation_id=rec.recommendation_id if rec else None,
                        recommendation_record_id=rec.id if rec else None,
                        recommendation_date=target_date,
                        # Use notification_sent_at if available, otherwise fall back to created_at
                        recommendation_time=rec.notification_sent_at if rec and rec.notification_sent_at else (rec.created_at if rec else None),
                        recommendation_type=rec.recommendation_type if rec else None,
                        recommended_action=rec.action_type if rec else None,
                        recommended_symbol=rec.symbol if rec else None,
                        recommended_strike=Decimal(str(rec_strike)) if rec_strike else None,
                        recommended_expiration=rec_expiration if isinstance(rec_expiration, date) else None,
                        recommended_premium=Decimal(str(rec_premium)) if rec_premium else None,
                        recommended_contracts=int(rec_contracts) if rec_contracts else None,
                        recommendation_priority=rec.priority if rec else None,
                        recommendation_context=rec.context_snapshot if rec else None,
                        
                        # Execution side
                        execution_id=exec.id if exec else None,
                        execution_date=exec.transaction_date if exec else None,
                        # Convert transaction_date (Date) to DateTime for execution_time
                        # Use 9:30 AM as default time (market open) if we only have date
                        execution_time=datetime.combine(exec.transaction_date, time(9, 30)) if exec and exec.transaction_date else None,
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
                # Check if this independent execution already exists
                existing_match = self.db.query(RecommendationExecutionMatch).filter(
                    RecommendationExecutionMatch.execution_id == exec.id,
                    RecommendationExecutionMatch.recommendation_date == target_date,
                    RecommendationExecutionMatch.match_type == MatchType.INDEPENDENT.value
                ).first()
                
                if existing_match:
                    # Update existing match with latest data
                    exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
                    exec_account = exec.account_id
                    
                    existing_match.execution_date = exec.transaction_date
                    # Convert transaction_date (Date) to DateTime for execution_time
                    if exec.transaction_date:
                        existing_match.execution_time = datetime.combine(exec.transaction_date, time(9, 30))
                    existing_match.execution_action = exec.transaction_type
                    existing_match.execution_symbol = exec.symbol
                    existing_match.execution_strike = exec_strike if exec_strike else None
                    existing_match.execution_expiration = exec_expiration if exec_expiration else None
                    existing_match.execution_premium = Decimal(str(abs(float(exec.amount or 0))))
                    existing_match.execution_contracts = int(exec.quantity or 1)
                    existing_match.execution_account = exec_account if exec_account else None
                    existing_match.reconciled_at = datetime.utcnow()
                    existing_match.updated_at = datetime.utcnow()
                    existing_match.year = iso_cal.year
                    existing_match.week_number = iso_cal.week
                else:
                    # Parse execution details from description (has full option details)
                    exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
                    exec_account = exec.account_id
                    
                    db_match = RecommendationExecutionMatch(
                        recommendation_date=target_date,
                        
                        # Execution side with full details
                        execution_id=exec.id,
                        execution_date=exec.transaction_date,
                        # Convert transaction_date (Date) to DateTime for execution_time
                        execution_time=datetime.combine(exec.transaction_date, time(9, 30)) if exec.transaction_date else None,
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
# V2 RECONCILIATION (Snapshot-based model)
# =========================================================================

    def reconcile_to_v2_model(self, match: MatchResult) -> Optional[int]:
        """
        Link a match result to the V2 recommendation model.
        
        This creates a RecommendationExecution record and resolves
        the corresponding PositionRecommendation.
        
        Returns the execution ID if created, None otherwise.
        """
        try:
            rec = match.recommendation
            exec = match.execution
            
            if not rec or not rec.context_snapshot:
                return None
            
            context = rec.context_snapshot
            
            # Extract position identity to find V2 recommendation
            symbol = context.get('symbol')
            account_name = context.get('account_name') or context.get('account', 'Unknown')
            source_strike = context.get('current_strike') or context.get('strike_price')
            source_expiration_str = context.get('current_expiration') or context.get('expiration_date')
            option_type = context.get('option_type', 'call')
            
            if not symbol or not source_strike or not source_expiration_str:
                return None
            
            # Parse expiration
            if isinstance(source_expiration_str, str):
                source_expiration = date.fromisoformat(source_expiration_str)
            else:
                source_expiration = source_expiration_str
            
            # Generate recommendation ID and find it
            rec_id = generate_recommendation_id(
                symbol, float(source_strike), source_expiration, option_type, account_name
            )
            
            v2_rec = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == rec_id
            ).first()
            
            if not v2_rec:
                logger.debug(f"[V2_RECONCILE] No V2 recommendation found for {rec_id}")
                return None
            
            # Get the latest snapshot
            latest_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == v2_rec.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
            
            # Parse execution details
            exec_strike = None
            exec_expiration = None
            if exec:
                exec_strike, exec_expiration = self._parse_option_from_symbol(exec.symbol, exec.description)
            
            # Create execution record
            v2_execution = RecommendationExecution(
                recommendation_id=v2_rec.id,
                snapshot_id=latest_snapshot.id if latest_snapshot else None,
                
                execution_action=exec.transaction_type if exec else None,
                execution_strike=Decimal(str(exec_strike)) if exec_strike else None,
                execution_expiration=exec_expiration,
                execution_premium=Decimal(str(abs(float(exec.amount or 0)))) if exec else None,
                execution_contracts=int(exec.quantity or 1) if exec else None,
                
                match_type=match.match_type.value,
                match_confidence=Decimal(str(match.confidence)),
                modification_details=match.modification_details if match.modification_details else None,
                
                executed_at=datetime.combine(exec.transaction_date, time(9, 30)) if exec and exec.transaction_date else None,
                hours_after_snapshot=Decimal(str(match.hours_to_execution)) if match.hours_to_execution else None,
                notification_count_before_action=v2_rec.total_notifications_sent,
                
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(v2_execution)
            
            # Resolve the recommendation
            resolution_type = f'user_acted_{match.match_type.value}'
            v2_rec.status = 'resolved'
            v2_rec.resolution_type = resolution_type
            v2_rec.resolved_at = datetime.utcnow()
            
            if v2_rec.first_detected_at:
                v2_rec.days_active = (datetime.utcnow() - v2_rec.first_detected_at).days
            
            v2_rec.updated_at = datetime.utcnow()
            
            self.db.flush()
            
            logger.info(f"[V2_RECONCILE] Created execution for {rec_id} (match_type={match.match_type.value})")
            
            # Auto-create new recommendation if this was a roll
            new_rec_id = self._auto_create_new_recommendation_if_rolled(
                v2_rec, v2_execution, exec, exec_strike, exec_expiration
            )
            
            if new_rec_id:
                logger.info(f"[V2_RECONCILE] Created new recommendation for rolled position: {new_rec_id}")
            
            return v2_execution.id
            
        except Exception as e:
            logger.error(f"[V2_RECONCILE] Error: {e}", exc_info=True)
            return None
    
    def _auto_create_new_recommendation_if_rolled(
        self,
        old_rec: PositionRecommendation,
        execution: RecommendationExecution,
        exec_txn,
        exec_strike: float,
        exec_expiration: date
    ) -> Optional[int]:
        """
        Auto-create a new recommendation when a position is rolled.
        
        This is called after an execution is linked to a recommendation.
        If the execution appears to be a roll (new strike or expiration),
        create a new recommendation for the new position.
        """
        try:
            # Skip if not a roll action
            exec_action = execution.execution_action if execution else None
            if not exec_action:
                return None
            
            # Check if this looks like a roll (STO = Sell to Open for new position)
            # or if the recommended action was a roll
            latest_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == old_rec.id
            ).order_by(RecommendationSnapshot.snapshot_number.desc()).first()
            
            was_roll_recommended = False
            if latest_snapshot and latest_snapshot.recommended_action:
                was_roll_recommended = 'ROLL' in latest_snapshot.recommended_action.upper()
            
            # Skip if no new strike/expiration (not a roll)
            if not exec_strike or not exec_expiration:
                return None
            
            # Skip if same as old position (not a roll)
            if (float(old_rec.source_strike) == exec_strike and 
                old_rec.source_expiration == exec_expiration):
                return None
            
            # Check if a recommendation already exists for the new position
            new_rec_id = generate_recommendation_id(
                symbol=old_rec.symbol,
                account_name=old_rec.account_name,
                source_strike=Decimal(str(exec_strike)),
                source_expiration=exec_expiration,
                option_type=old_rec.option_type
            )
            
            existing = self.db.query(PositionRecommendation).filter(
                PositionRecommendation.recommendation_id == new_rec_id
            ).first()
            
            if existing:
                logger.debug(f"[V2_RECONCILE] New position recommendation already exists: {new_rec_id}")
                return existing.id
            
            # Create new recommendation
            new_rec = PositionRecommendation(
                recommendation_id=new_rec_id,
                symbol=old_rec.symbol,
                account_name=old_rec.account_name,
                source_strike=Decimal(str(exec_strike)),
                source_expiration=exec_expiration,
                option_type=old_rec.option_type,
                source_contracts=old_rec.source_contracts,
                status='active',
                first_detected_at=datetime.utcnow(),
            )
            
            self.db.add(new_rec)
            self.db.flush()
            
            # Mark old recommendation as superseded
            old_rec.status = 'superseded'
            old_rec.resolution_type = 'rolled_to_new'
            old_rec.resolution_notes = f'Rolled to {exec_strike} {exec_expiration}'
            
            logger.info(
                f"[V2_RECONCILE] Created new recommendation {new_rec_id} for rolled position "
                f"({old_rec.source_strike}→{exec_strike}, {old_rec.source_expiration}→{exec_expiration})"
            )
            
            return new_rec.id
            
        except Exception as e:
            logger.error(f"[V2_RECONCILE] Error creating new recommendation: {e}", exc_info=True)
            return None
    
    def reconcile_day_v2(self, target_date: date) -> Dict[str, Any]:
        """
        Reconcile recommendations to V2 model for a specific day.
        
        This should be called after reconcile_day() to also update
        the new snapshot-based tables.
        """
        logger.info(f"[V2_RECONCILE] Starting V2 reconciliation for {target_date}")
        
        # Get all matches from the legacy table for this date
        matches_today = self.db.query(RecommendationExecutionMatch).filter(
            RecommendationExecutionMatch.recommendation_date == target_date
        ).all()
        
        v2_created = 0
        
        for legacy_match in matches_today:
            if legacy_match.recommendation_record_id:
                # Get the recommendation
                rec = self.db.query(StrategyRecommendationRecord).get(
                    legacy_match.recommendation_record_id
                )
                
                if rec:
                    # Build a MatchResult from the legacy match
                    exec_obj = None
                    if legacy_match.execution_id:
                        exec_obj = self.db.query(InvestmentTransaction).get(legacy_match.execution_id)
                    
                    match_result = MatchResult(
                        match_type=MatchType(legacy_match.match_type),
                        confidence=float(legacy_match.match_confidence or 100),
                        recommendation=rec,
                        execution=exec_obj,
                        modification_details=legacy_match.modification_details or {},
                        hours_to_execution=float(legacy_match.hours_to_execution) if legacy_match.hours_to_execution else None
                    )
                    
                    result = self.reconcile_to_v2_model(match_result)
                    if result:
                        v2_created += 1
        
        self.db.commit()
        
        summary = {
            "date": target_date.isoformat(),
            "legacy_matches_processed": len(matches_today),
            "v2_executions_created": v2_created
        }
        
        logger.info(f"[V2_RECONCILE] Complete: {summary}")
        return summary


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def get_reconciliation_service(db: Session) -> ReconciliationService:
    """Factory function to get ReconciliationService instance."""
    return ReconciliationService(db)

