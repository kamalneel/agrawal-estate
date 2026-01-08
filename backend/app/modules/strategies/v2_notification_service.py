"""
V2 Notification Service

This service handles notifications natively from the V2 recommendation/snapshot model.
Each notification references a specific snapshot, enabling:
- Clear audit trail (which snapshot triggered which notification)
- Smart vs Verbose mode support
- Proper lifecycle tracking

Key concepts:
- Recommendation: The identity (AAPL $285 call in Jaya's account)
- Snapshot: Point-in-time evaluation (Snap #3: ROLL → $270 at 12 PM)
- Notification: A message sent to user referencing a specific snapshot
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from decimal import Decimal
from collections import defaultdict
import logging

from app.modules.strategies.recommendation_models import (
    PositionRecommendation,
    RecommendationSnapshot,
    generate_recommendation_id
)
from app.core.timezone import format_datetime_for_api, now_utc_iso

logger = logging.getLogger(__name__)

# Account ordering - consistent with frontend (Income, Investments, Notifications pages)
# Order: Neel's accounts first, then Jaya's, then others
ACCOUNT_ORDER = {
    "Neel's Brokerage": 1,
    "Neel's Retirement": 2,
    "Neel's Roth IRA": 3,
    "Jaya's Brokerage": 4,
    "Jaya's IRA": 5,
    "Jaya's Roth IRA": 6,
    "Alisha's Brokerage": 7,
    "Agrawal Family HSA": 8,
    "Other": 99,
}

def get_account_sort_order(account_name: str) -> int:
    """Get sort order for account name. Lower = earlier in list."""
    return ACCOUNT_ORDER.get(account_name, 50)  # Unknown accounts go in the middle


class V2NotificationService:
    """
    Notification service that works natively with V2 recommendations and snapshots.
    
    Features:
    - Reads directly from V2 snapshots
    - Supports verbose (every snapshot) and smart (changes only) modes
    - Includes snapshot number in notifications for traceability
    - Handles new sell opportunities
    """
    
    PRIORITY_ORDER = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_notifications_to_send(
        self,
        mode: str = 'both',
        scan_type: str = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all notifications that should be sent based on current V2 state.
        
        Args:
            mode: 'verbose' (all snapshots), 'smart' (changes only), or 'both'
            scan_type: Optional scan identifier (e.g., '6am', '12pm')
        
        Returns:
            Dict with 'verbose' and 'smart' lists of notification items
        """
        result = {
            'verbose': [],
            'smart': []
        }
        
        # Get all active recommendations with their latest snapshots
        active_recs = self.db.query(PositionRecommendation).filter(
            PositionRecommendation.status == 'active'
        ).all()
        
        for rec in active_recs:
            # Get the latest snapshot
            latest_snapshot = self.db.query(RecommendationSnapshot).filter(
                RecommendationSnapshot.recommendation_id == rec.id
            ).order_by(desc(RecommendationSnapshot.snapshot_number)).first()
            
            if not latest_snapshot:
                continue
            
            # Skip if action is NO_ACTION or HOLD
            if latest_snapshot.recommended_action in ('NO_ACTION', 'HOLD', 'no_action', 'hold'):
                continue
            
            # Build notification item
            notif_item = self._build_notification_item(rec, latest_snapshot)
            
            # Verbose mode: include all active recommendations
            if mode in ('verbose', 'both'):
                result['verbose'].append(notif_item)
            
            # Smart mode: only include if this snapshot warrants notification
            if mode in ('smart', 'both'):
                if self._should_notify_smart(rec, latest_snapshot):
                    result['smart'].append(notif_item)
        
        # Sort by priority within each list
        for key in result:
            result[key].sort(key=lambda x: self.PRIORITY_ORDER.get(x['priority'], 99))
        
        return result
    
    def _build_notification_item(
        self,
        rec: PositionRecommendation,
        snapshot: RecommendationSnapshot
    ) -> Dict[str, Any]:
        """Build a notification item from a recommendation and its snapshot."""
        
        # Determine action type for display
        action = snapshot.recommended_action
        action_display = self._format_action(action)
        
        # Build title based on action and position type
        is_uncovered = rec.position_type == 'uncovered' or rec.source_strike is None
        
        if action.upper().startswith('ROLL'):
            if snapshot.target_strike:
                title = f"{action_display}: {rec.symbol} ${rec.source_strike}→${snapshot.target_strike}"
                if snapshot.target_expiration:
                    title += f" {snapshot.target_expiration.strftime('%m/%d')}"
            else:
                title = f"{action_display}: {rec.symbol} ${rec.source_strike}"
            
            # Add net cost/credit for ROLL
            if snapshot.net_cost:
                net_cost = float(snapshot.net_cost)
                if net_cost > 0:
                    title += f" · ${net_cost:.2f} debit"
                elif net_cost < 0:
                    title += f" · ${abs(net_cost):.2f} credit"
                # If zero, it's a zero-cost roll - don't add anything
                
        elif action.upper() == 'CLOSE':
            title = f"CLOSE: {rec.symbol} ${rec.source_strike} - Cannot escape"
            # Add estimated close cost if available
            if snapshot.estimated_cost_to_close:
                title += f" · ~${float(snapshot.estimated_cost_to_close):.0f} to close"
                
        elif action.upper() == 'SELL':
            if is_uncovered:
                # Uncovered position - show contracts and target
                contracts = rec.source_contracts or 1
                if snapshot.target_strike:
                    title = f"SELL: {contracts} {rec.symbol} ${snapshot.target_strike:.0f} calls"
                else:
                    title = f"SELL: {rec.symbol} calls"
                if snapshot.stock_price:
                    title += f" · Stock ${snapshot.stock_price:.0f}"
                # Add premium for SELL
                if snapshot.target_premium:
                    total_premium = float(snapshot.target_premium) * contracts
                    title += f" · Earn ${total_premium:.0f}"
            else:
                if snapshot.target_strike:
                    title = f"SELL: {rec.symbol} ${snapshot.target_strike} calls"
                else:
                    title = f"SELL: {rec.symbol} calls · Stock ${snapshot.stock_price:.0f}" if snapshot.stock_price else f"SELL: {rec.symbol} calls"
        elif action.upper() == 'WAIT':
            # WAIT recommendation for uncovered position
            contracts = rec.source_contracts or 1
            title = f"⏸️ WAIT: {rec.symbol} ({contracts} uncovered)"
            if snapshot.stock_price:
                title += f" · Stock ${snapshot.stock_price:.0f}"
        else:
            if rec.source_strike:
                title = f"{action_display}: {rec.symbol} ${rec.source_strike}"
            else:
                title = f"{action_display}: {rec.symbol}"
        
        # Build description - simplify long detailed analysis
        raw_reason = snapshot.reason or f"{action_display} recommended"
        import re
        
        # Try to extract key summary from detailed analysis
        description = raw_reason
        
        # Look for **Recommendation** section
        if '**Recommendation**' in raw_reason:
            rec_match = re.search(r'\*\*Recommendation\*\*:?\s*(.+?)(?:\n\n|$)', raw_reason, re.DOTALL)
            if rec_match:
                description = rec_match.group(1).strip()
        # Look for **Roll Now** or **Alternative Scenarios** section  
        elif '**Roll Now**' in raw_reason:
            roll_match = re.search(r'\*\*Roll Now\*\*:?\s*(.+?)(?:\n|$)', raw_reason)
            if roll_match:
                description = roll_match.group(1).strip()
        # Look for first line if it's a summary (starts with "Position is")
        elif raw_reason.startswith('Position is'):
            first_line = raw_reason.split('\n')[0]
            description = first_line
        
        # Clean up markdown formatting for display
        description = re.sub(r'\*\*([^*]+)\*\*', r'\1', description)  # Remove **bold**
        description = description.replace('**', '').replace('*', '')
        
        # Final truncation if still too long
        if len(description) > 200:
            description = description[:200] + "..."
        
        # Add snapshot context
        snapshot_info = f"Snap #{snapshot.snapshot_number}"
        if snapshot.action_changed:
            snapshot_info += " ⚡ACTION CHANGED"
        if snapshot.target_changed:
            snapshot_info += " 🎯TARGET CHANGED"
        if snapshot.priority_changed:
            snapshot_info += " ⬆️PRIORITY UP"
        
        return {
            # Identity
            'id': f"v2_{rec.recommendation_id}_snap{snapshot.snapshot_number}",
            'recommendation_id': rec.recommendation_id,
            'v2_recommendation_id': rec.id,
            'snapshot_id': snapshot.id,
            'snapshot_number': snapshot.snapshot_number,
            
            # Display
            'type': self._get_recommendation_type(action),
            'category': 'position_management',
            'priority': snapshot.priority,
            'title': title,
            'description': description,
            'rationale': snapshot.reason,
            'action': action_display,
            'action_type': action.lower(),
            
            # Position info
            'symbol': rec.symbol,
            'account_name': rec.account_name,
            'source_strike': float(rec.source_strike) if rec.source_strike else None,
            'source_expiration': rec.source_expiration.isoformat() if rec.source_expiration else None,
            'option_type': rec.option_type,
            'contracts': rec.source_contracts,
            
            # Target info
            'target_strike': float(snapshot.target_strike) if snapshot.target_strike else None,
            'target_expiration': snapshot.target_expiration.isoformat() if snapshot.target_expiration else None,
            'target_premium': float(snapshot.target_premium) if snapshot.target_premium else None,
            'net_cost': float(snapshot.net_cost) if snapshot.net_cost else None,
            
            # Market state
            'stock_price': float(snapshot.stock_price) if snapshot.stock_price else None,
            'profit_pct': float(snapshot.profit_pct) if snapshot.profit_pct else None,
            'is_itm': snapshot.is_itm,
            'itm_pct': float(snapshot.itm_pct) if snapshot.itm_pct else None,
            
            # Change tracking
            'action_changed': snapshot.action_changed,
            'target_changed': snapshot.target_changed,
            'priority_changed': snapshot.priority_changed,
            'previous_action': snapshot.previous_action,
            'previous_target_strike': float(snapshot.previous_target_strike) if snapshot.previous_target_strike else None,
            
            # Snapshot metadata
            'snapshot_info': snapshot_info,
            'evaluated_at': format_datetime_for_api(snapshot.evaluated_at),
            'total_snapshots': rec.total_snapshots,
            'days_active': rec.days_active,
            
            # For notification tracking - use centralized UTC timestamp
            'created_at': now_utc_iso(),
            
            # Full context for compatibility
            'context': {
                'symbol': rec.symbol,
                'account_name': rec.account_name,
                'current_strike': float(rec.source_strike) if rec.source_strike else None,
                'current_expiration': rec.source_expiration.isoformat() if rec.source_expiration else None,
                'option_type': rec.option_type,
                'target_strike': float(snapshot.target_strike) if snapshot.target_strike else None,
                'target_expiration': snapshot.target_expiration.isoformat() if snapshot.target_expiration else None,
                'stock_price': float(snapshot.stock_price) if snapshot.stock_price else None,
                'profit_pct': float(snapshot.profit_pct) if snapshot.profit_pct else None,
                'snapshot_number': snapshot.snapshot_number,
                'total_snapshots': rec.total_snapshots,
            }
        }
    
    def _should_notify_smart(
        self,
        rec: PositionRecommendation,
        snapshot: RecommendationSnapshot
    ) -> bool:
        """
        Determine if this snapshot warrants a smart-mode notification.
        
        Smart mode sends notification if:
        1. First snapshot (new recommendation)
        2. Action changed
        3. Target changed significantly
        4. Priority escalated
        5. Cooldown period passed (daily reminder)
        """
        # First snapshot: always notify
        if snapshot.snapshot_number == 1:
            return True
        
        # Action changed: always notify
        if snapshot.action_changed:
            return True
        
        # Target changed: notify if significant
        if snapshot.target_changed:
            # Check if strike changed by more than $1
            if snapshot.previous_target_strike and snapshot.target_strike:
                strike_diff = abs(float(snapshot.target_strike) - float(snapshot.previous_target_strike))
                if strike_diff > 1.0:
                    return True
            # Check if expiration changed
            if snapshot.previous_target_expiration != snapshot.target_expiration:
                return True
        
        # Priority escalated: notify
        if snapshot.priority_changed:
            current = self.PRIORITY_ORDER.get(snapshot.priority, 99)
            previous = self.PRIORITY_ORDER.get(snapshot.previous_priority, 99)
            if current < previous:  # Lower number = higher priority
                return True
        
        # Check if we've already notified on a recent snapshot
        last_notified = self.db.query(RecommendationSnapshot).filter(
            and_(
                RecommendationSnapshot.recommendation_id == rec.id,
                RecommendationSnapshot.smart_notification_sent == True
            )
        ).order_by(desc(RecommendationSnapshot.snapshot_number)).first()
        
        if not last_notified:
            # Never notified: send
            return True
        
        # Check cooldown (4 hours)
        if last_notified.smart_notification_at:
            hours_since = (datetime.utcnow() - last_notified.smart_notification_at).total_seconds() / 3600
            if hours_since >= 4:
                return True
        
        # Otherwise, don't notify
        return False
    
    def _format_action(self, action: str) -> str:
        """Format action for display."""
        action_map = {
            'ROLL_WEEKLY': 'ROLL',
            'ROLL_ITM': 'ROLL (ITM)',
            'PULL_BACK': 'PULL BACK',
            'CLOSE_CATASTROPHIC': 'CLOSE',
            'CLOSE': 'CLOSE',
            'SELL': 'SELL',
            'HOLD': 'HOLD',
            'NO_ACTION': 'HOLD',
        }
        return action_map.get(action.upper(), action.upper())
    
    def _get_recommendation_type(self, action: str) -> str:
        """Get recommendation type from action."""
        type_map = {
            'ROLL_WEEKLY': 'roll_options',
            'ROLL_ITM': 'roll_itm',
            'PULL_BACK': 'pull_back',
            'CLOSE_CATASTROPHIC': 'close_position',
            'CLOSE': 'close_position',
            'SELL': 'sell_unsold_contracts',
        }
        return type_map.get(action.upper(), 'position_management')
    
    def mark_snapshot_notified(
        self,
        snapshot_id: int,
        mode: str,
        channel: str = 'telegram',
        message_id: int = None
    ):
        """Mark a snapshot as having been notified."""
        # Skip if no snapshot_id (e.g., V1 sell opportunities)
        if not snapshot_id:
            return
            
        snapshot = self.db.query(RecommendationSnapshot).filter(
            RecommendationSnapshot.id == snapshot_id
        ).first()
        if not snapshot:
            return
        
        now = datetime.utcnow()
        
        if mode == 'verbose':
            snapshot.verbose_notification_sent = True
            snapshot.verbose_notification_at = now
        elif mode == 'smart':
            snapshot.smart_notification_sent = True
            snapshot.smart_notification_at = now
        else:  # both
            snapshot.verbose_notification_sent = True
            snapshot.verbose_notification_at = now
            snapshot.smart_notification_sent = True
            snapshot.smart_notification_at = now
        
        # Update general fields
        if not snapshot.notification_sent:
            snapshot.notification_sent = True
            snapshot.notification_sent_at = now
            snapshot.notification_channel = channel
            snapshot.notification_mode = mode
            if message_id:
                snapshot.telegram_message_id = message_id
        
        # Update recommendation stats
        rec = snapshot.recommendation
        if rec:
            rec.total_notifications_sent = (rec.total_notifications_sent or 0) + 1
            rec.updated_at = now
        
        self.db.commit()
    
    def format_telegram_message(
        self,
        notifications: List[Dict[str, Any]],
        mode: str
    ) -> str:
        """
        Format notifications for Telegram, grouped by account.
        Matches the organization of the existing notification system.
        """
        if not notifications:
            return ""
        
        # Add mode header
        if mode == 'verbose':
            lines = ["📢 *VERBOSE MODE* - All Snapshots", "─────────────────────", ""]
        else:
            lines = ["🧠 *SMART MODE* - Changes Only", "─────────────────────", ""]
        
        # Group by account
        by_account = defaultdict(list)
        for notif in notifications:
            account = notif.get('account_name') or 'Other'
            by_account[account].append(notif)
        
        # Format each account group using NEO order (Neel's first, then Jaya's, then others)
        for account in sorted(by_account.keys(), key=lambda x: get_account_sort_order(x or 'Other')):
            items = by_account[account]
            lines.append(f"*{account} - {len(items)} Recommendation{'s' if len(items) > 1 else ''}:*")
            
            for item in items:
                action = item.get('action', '')
                symbol = item.get('symbol', '')
                source_strike = item.get('source_strike')
                target_strike = item.get('target_strike')
                target_exp = item.get('target_expiration')
                stock_price = item.get('stock_price')
                snap_num = item.get('snapshot_number', 1)
                
                # Get premium/cost data
                net_cost = item.get('net_cost')
                target_premium = item.get('target_premium')
                contracts = item.get('contracts') or 1
                
                # Format line based on action type
                if action.upper().startswith('ROLL'):
                    if target_strike and target_exp:
                        exp_display = datetime.fromisoformat(target_exp).strftime('%b %d') if target_exp else ''
                        line = f"• {action}: {symbol} ${source_strike}→${target_strike} {exp_display}"
                    elif target_strike:
                        line = f"• {action}: {symbol} ${source_strike}→${target_strike}"
                    else:
                        line = f"• {action}: {symbol} ${source_strike}"
                    # Add net cost/credit
                    if net_cost:
                        if net_cost > 0:
                            line += f" (${net_cost:.2f} debit)"
                        elif net_cost < 0:
                            line += f" (${abs(net_cost):.2f} credit)"
                elif action.upper() == 'CLOSE':
                    line = f"• CLOSE: {symbol} ${source_strike}"
                elif action.upper() == 'SELL':
                    if target_strike:
                        line = f"• SELL: {symbol} ${target_strike} calls"
                    else:
                        line = f"• SELL: {symbol} calls"
                    # Add premium estimate
                    if target_premium and contracts:
                        total_premium = target_premium * contracts
                        line += f" (earn ${total_premium:.0f})"
                elif action.upper() == 'WAIT':
                    # WAIT recommendations - show with distinct indicator
                    uncovered = item.get('contracts', 0) or (item.get('context') or {}).get('uncovered_shares', 0) // 100
                    reason_short = (item.get('rationale') or 'likely bounce')[:30]
                    if uncovered:
                        line = f"• ⏸️ WAIT: {symbol} ({uncovered} uncovered) - {reason_short}"
                    else:
                        line = f"• ⏸️ WAIT: {symbol} - {reason_short}"
                else:
                    line = f"• {action}: {symbol}"
                
                # Add stock price if available
                if stock_price:
                    line += f" · Stock ${stock_price:.0f}"
                
                # Add snapshot info
                line += f" _(snap #{snap_num})_"
                
                # Add change indicators
                if item.get('action_changed'):
                    line += " ⚡"
                if item.get('target_changed'):
                    line += " 🎯"
                if item.get('priority_changed'):
                    line += " ⬆️"
                
                lines.append(line)
            
            lines.append("")  # Blank line between accounts
        
        # Add timestamp
        now = datetime.now()
        lines.append(f"_{now.strftime('%I:%M %p')}_")
        
        return "\n".join(lines)
    
    def get_new_sell_opportunities(self) -> List[Dict[str, Any]]:
        """
        Get opportunities to sell new calls on positions without sold options.
        
        NOTE: As of V2 architecture update, uncovered positions are now stored
        in the V2 model (PositionRecommendation with position_type='uncovered').
        
        This method is now DEPRECATED - uncovered positions are returned by
        get_notifications_to_send() along with sold option recommendations.
        
        Returns empty list for backward compatibility.
        """
        # V2 now handles uncovered positions directly
        # They have position_type='uncovered' and source_strike=NULL
        # Returning empty to avoid duplicates
        return []
        
        # LEGACY CODE (commented out for reference):
        # from app.modules.strategies.models import StrategyRecommendationRecord
        # from datetime import timedelta
        # cutoff = datetime.utcnow() - timedelta(hours=24)
        # sell_recs = self.db.query(StrategyRecommendationRecord).filter(...)
        
        result = []
        for rec in sell_recs:
            context = rec.context_snapshot or {}
            
            # Detect WAIT vs SELL based on title or context
            # WAIT recommendations have title starting with "WAIT" and action_type="monitor"
            is_wait = (
                (rec.title and rec.title.upper().startswith('WAIT')) or
                context.get('action_type') == 'monitor' or
                context.get('should_wait', False)
            )
            
            if is_wait:
                action = 'WAIT'
                action_type = 'monitor'
                rec_id_prefix = 'v1_wait'
            else:
                action = 'SELL'
                action_type = 'sell'
                rec_id_prefix = 'v1_sell'
            
            notif_item = {
                # Identity
                'id': f"{rec_id_prefix}_{rec.id}",
                'recommendation_id': rec.recommendation_id,
                'v2_recommendation_id': None,  # Not in V2 yet
                'snapshot_id': None,
                'snapshot_number': 1,  # These are one-time, no snapshots
                
                # Display
                'type': rec.recommendation_type,
                'category': rec.category,
                'priority': 'low' if is_wait else rec.priority,  # WAIT is lower priority
                'title': rec.title,
                'description': rec.description,
                'rationale': rec.rationale,
                'action': action,
                'action_type': action_type,
                
                # Position info (no source position)
                'symbol': rec.symbol,
                'account_name': rec.account_name,
                'source_strike': None,  # No source - this is new
                'source_expiration': None,
                'option_type': context.get('option_type', 'call'),
                'contracts': context.get('quantity', 1),
                
                # Target info
                'target_strike': context.get('strike_price') or context.get('recommended_strike'),
                'target_expiration': context.get('recommended_expiration'),
                'target_premium': context.get('premium_per_contract') or context.get('expected_premium'),
                'net_cost': None,
                
                # Market state
                'stock_price': context.get('stock_price'),
                'profit_pct': None,
                'is_itm': False,
                'itm_pct': None,
                
                # Change tracking (not applicable for one-time recs)
                'action_changed': False,
                'target_changed': False,
                'priority_changed': False,
                'previous_action': None,
                'previous_target_strike': None,
                
                # Metadata
                'snapshot_info': "New opportunity",
                'evaluated_at': format_datetime_for_api(rec.created_at),
                'total_snapshots': 1,
                'days_active': 0,
                
                'created_at': format_datetime_for_api(rec.created_at) or now_utc_iso(),
                
                'context': context,
            }
            
            result.append(notif_item)
        
        # Deduplicate by symbol + account (keep most recent)
        # This handles cases where multiple recommendations were generated for same position
        seen = {}
        deduplicated = []
        
        # Sort by created_at descending so we keep the newest
        result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        for item in result:
            key = f"{item.get('symbol', '')}_{item.get('account_name', '')}"
            if key not in seen:
                seen[key] = True
                deduplicated.append(item)
        
        return deduplicated
    
    def get_all_notifications_to_send(
        self,
        mode: str = 'both',
        scan_type: str = None,
        include_sell_opportunities: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all notifications including both V2 snapshots and V1 sell opportunities.
        
        This is the comprehensive method that combines:
        - V2 position-based recommendations (with snapshots)
        - V1 sell opportunities (one-time, no snapshots)
        """
        # Get V2 notifications
        result = self.get_notifications_to_send(mode=mode, scan_type=scan_type)
        
        # Add sell opportunities if requested
        if include_sell_opportunities:
            sell_opps = self.get_new_sell_opportunities()
            
            # Sell opportunities go to both verbose and smart (they're always "new")
            result['verbose'].extend(sell_opps)
            result['smart'].extend(sell_opps)
            
            # Re-sort by priority
            for key in result:
                result[key].sort(key=lambda x: self.PRIORITY_ORDER.get(x['priority'], 99))
        
        return result


def get_v2_notification_service(db: Session) -> V2NotificationService:
    """Factory function to get a V2NotificationService instance."""
    return V2NotificationService(db)

