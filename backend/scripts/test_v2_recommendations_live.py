#!/usr/bin/env python3
"""
V2 Recommendation System - Live Test Script

This script allows you to test the V2 recommendation system end-to-end:
1. Triggers the recommendation engine
2. Shows V2 data captured (snapshots, changes)
3. Compares V1 vs V2 output
4. Optionally sends a test notification using V2 data

Usage:
    python scripts/test_v2_recommendations_live.py [options]

Options:
    --scan           Run a fresh recommendation scan
    --compare        Show V1 vs V2 comparison
    --show-snapshots Show recent V2 snapshots in detail
    --send-test      Send a TEST notification via Telegram using V2 data
    --symbol SYMBOL  Filter by symbol (e.g., PLTR)
"""

import sys
import os
import argparse
from datetime import datetime, date, timedelta
from decimal import Decimal
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import SessionLocal


def run_recommendation_scan(db: Session):
    """Trigger a fresh recommendation scan."""
    print("\n" + "=" * 70)
    print("🔄 RUNNING RECOMMENDATION SCAN")
    print("=" * 70)
    
    from app.modules.strategies.recommendations import OptionsStrategyRecommendationService
    
    service = OptionsStrategyRecommendationService(db)
    
    # Generate recommendations
    recommendations = service.generate_recommendations()
    print(f"\n📊 Generated {len(recommendations)} recommendations")
    
    # Save to both V1 and V2 (dual-write is automatic)
    saved = service.save_recommendations_to_history(
        recommendations, 
        scan_type="test_scan",
        enable_dual_write=True
    )
    print(f"💾 Saved {saved} recommendations (dual-write to V1 + V2)")
    
    return recommendations


def show_v1_vs_v2_comparison(db: Session, symbol: str = None, limit: int = 10):
    """Show side-by-side comparison of V1 vs V2 data."""
    print("\n" + "=" * 70)
    print("📊 V1 vs V2 COMPARISON")
    print("=" * 70)
    
    from app.modules.strategies.models import StrategyRecommendationRecord
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    
    # Get V1 data
    v1_query = db.query(StrategyRecommendationRecord).order_by(
        desc(StrategyRecommendationRecord.created_at)
    )
    if symbol:
        v1_query = v1_query.filter(StrategyRecommendationRecord.symbol == symbol.upper())
    v1_recs = v1_query.limit(limit).all()
    
    # Get V2 data
    v2_query = db.query(PositionRecommendation).filter(
        PositionRecommendation.status == 'active'
    ).order_by(desc(PositionRecommendation.last_snapshot_at))
    if symbol:
        v2_query = v2_query.filter(PositionRecommendation.symbol == symbol.upper())
    v2_recs = v2_query.limit(limit).all()
    
    print(f"\n{'─' * 70}")
    print(f"V1 (Legacy) - {len(v1_recs)} recent recommendations")
    print(f"{'─' * 70}")
    
    for rec in v1_recs[:5]:
        context = rec.context_snapshot or {}
        print(f"\n  📝 {rec.symbol or 'N/A'} | {rec.recommendation_type}")
        print(f"     Priority: {rec.priority} | Action: {rec.action_type}")
        print(f"     Created: {rec.created_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"     Notified: {'✅' if rec.notification_sent else '❌'}")
        if context.get('new_strike'):
            print(f"     Target: ${context.get('new_strike')} exp {context.get('new_expiration', 'N/A')}")
    
    print(f"\n{'─' * 70}")
    print(f"V2 (New) - {len(v2_recs)} active recommendations")
    print(f"{'─' * 70}")
    
    for rec in v2_recs[:5]:
        # Get latest snapshot
        latest = db.query(RecommendationSnapshot).filter(
            RecommendationSnapshot.recommendation_id == rec.id
        ).order_by(desc(RecommendationSnapshot.snapshot_number)).first()
        
        print(f"\n  📝 {rec.symbol} ${rec.source_strike} exp {rec.source_expiration}")
        print(f"     Account: {rec.account_name}")
        print(f"     Status: {rec.status} | Snapshots: {rec.total_snapshots}")
        print(f"     Notifications sent: {rec.total_notifications_sent}")
        
        if latest:
            print(f"     Latest snapshot #{latest.snapshot_number}:")
            print(f"       Action: {latest.recommended_action} | Priority: {latest.priority}")
            if latest.target_strike:
                print(f"       Target: ${latest.target_strike} exp {latest.target_expiration}")
            print(f"       Changes: action={latest.action_changed}, target={latest.target_changed}, priority={latest.priority_changed}")
            print(f"       Notified: {'✅' if latest.notification_sent else '❌'}")


def show_v2_snapshots_detail(db: Session, symbol: str = None, limit: int = 5):
    """Show detailed V2 snapshot data."""
    print("\n" + "=" * 70)
    print("📸 V2 SNAPSHOT DETAILS")
    print("=" * 70)
    
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    
    # Get recommendations with multiple snapshots
    query = db.query(PositionRecommendation).filter(
        PositionRecommendation.total_snapshots > 0
    ).order_by(desc(PositionRecommendation.last_snapshot_at))
    
    if symbol:
        query = query.filter(PositionRecommendation.symbol == symbol.upper())
    
    recommendations = query.limit(limit).all()
    
    for rec in recommendations:
        print(f"\n{'─' * 70}")
        print(f"🎯 {rec.recommendation_id}")
        print(f"{'─' * 70}")
        print(f"   Symbol: {rec.symbol} | Account: {rec.account_name}")
        print(f"   Source Position: ${rec.source_strike} {rec.option_type} exp {rec.source_expiration}")
        print(f"   Status: {rec.status}")
        print(f"   First detected: {rec.first_detected_at}")
        print(f"   Total snapshots: {rec.total_snapshots}")
        print(f"   Total notifications: {rec.total_notifications_sent}")
        
        # Get all snapshots
        snapshots = db.query(RecommendationSnapshot).filter(
            RecommendationSnapshot.recommendation_id == rec.id
        ).order_by(RecommendationSnapshot.snapshot_number).all()
        
        print(f"\n   📸 Snapshot History:")
        for s in snapshots:
            changes = []
            if s.action_changed:
                changes.append(f"action: {s.previous_action}→{s.recommended_action}")
            if s.target_changed:
                changes.append(f"target: ${s.previous_target_strike}→${s.target_strike}")
            if s.priority_changed:
                changes.append(f"priority: {s.previous_priority}→{s.priority}")
            
            change_str = " | ".join(changes) if changes else "no changes"
            notified = "📨" if s.notification_sent else "  "
            
            print(f"      #{s.snapshot_number} {notified} [{s.evaluated_at.strftime('%m/%d %H:%M')}] "
                  f"{s.recommended_action} {s.priority} | {change_str}")


def format_v2_notification_message(db: Session, limit: int = 5) -> str:
    """Format a notification message using V2 data."""
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    from collections import defaultdict
    
    # Get active recommendations with their latest snapshots
    recommendations = db.query(PositionRecommendation).filter(
        PositionRecommendation.status == 'active'
    ).order_by(desc(PositionRecommendation.last_snapshot_at)).limit(limit).all()
    
    if not recommendations:
        return "No active V2 recommendations found."
    
    # Group by account
    by_account = defaultdict(list)
    
    for rec in recommendations:
        latest = db.query(RecommendationSnapshot).filter(
            RecommendationSnapshot.recommendation_id == rec.id
        ).order_by(desc(RecommendationSnapshot.snapshot_number)).first()
        
        if latest:
            by_account[rec.account_name].append({
                'rec': rec,
                'snapshot': latest
            })
    
    # Format message
    lines = ["🧪 *V2 TEST NOTIFICATION*", ""]
    
    for account, items in by_account.items():
        lines.append(f"*{account}* - {len(items)} recommendation(s):")
        
        for item in items:
            rec = item['rec']
            s = item['snapshot']
            
            # Format action
            action_emoji = {
                'ROLL_WEEKLY': '🔄',
                'ROLL_ITM': '⚠️',
                'PULL_BACK': '↩️',
                'CLOSE': '❌',
                'SELL': '💰',
            }.get(s.recommended_action, '📝')
            
            # Build line
            line = f"  {action_emoji} {rec.symbol}"
            
            if s.recommended_action in ('ROLL_WEEKLY', 'ROLL_ITM', 'PULL_BACK'):
                line += f" ${rec.source_strike}→"
                if s.target_strike:
                    line += f"${s.target_strike}"
                if s.target_expiration:
                    line += f" {s.target_expiration.strftime('%m/%d')}"
            elif s.recommended_action == 'SELL':
                line += f" ${rec.source_strike}"
            
            # Add snapshot info
            line += f" (snap #{s.snapshot_number}"
            if s.action_changed:
                line += ", ACTION CHANGED"
            if s.priority_changed:
                line += ", PRIORITY↑"
            line += ")"
            
            lines.append(line)
        
        lines.append("")
    
    lines.append(f"_Generated from V2 model at {datetime.now().strftime('%H:%M:%S')}_")
    
    return "\n".join(lines)


def send_test_notification(db: Session):
    """Send a test notification using V2 data."""
    print("\n" + "=" * 70)
    print("📨 SENDING V2 TEST NOTIFICATION")
    print("=" * 70)
    
    message = format_v2_notification_message(db)
    
    print("\n📝 Message preview:")
    print("-" * 50)
    print(message)
    print("-" * 50)
    
    # Confirm before sending
    confirm = input("\n⚠️  Send this to Telegram? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    # Send via Telegram
    import requests
    
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not telegram_token or not telegram_chat_id:
        # Try loading from .env
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        value = value.strip('"\'')
                        if key == 'TELEGRAM_BOT_TOKEN':
                            telegram_token = value
                        elif key == 'TELEGRAM_CHAT_ID':
                            telegram_chat_id = value
    
    if not telegram_token or not telegram_chat_id:
        print("❌ Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return
    
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    response = requests.post(url, json={
        "chat_id": telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown"
    })
    
    if response.ok:
        result = response.json()
        message_id = result.get('result', {}).get('message_id')
        print(f"✅ Sent! Message ID: {message_id}")
    else:
        print(f"❌ Failed: {response.text}")


def show_notification_decision_log(db: Session, limit: int = 20):
    """Show the notification decision log from V2 snapshots."""
    print("\n" + "=" * 70)
    print("📋 V2 NOTIFICATION DECISION LOG")
    print("=" * 70)
    
    from app.modules.strategies.recommendation_models import (
        PositionRecommendation,
        RecommendationSnapshot
    )
    
    # Get recent snapshots
    snapshots = db.query(RecommendationSnapshot).order_by(
        desc(RecommendationSnapshot.evaluated_at)
    ).limit(limit).all()
    
    print(f"\n{'Timestamp':<18} {'Symbol':<8} {'#':<3} {'Action':<12} {'Priority':<8} {'Decision':<25} {'Sent'}")
    print("-" * 95)
    
    for s in snapshots:
        rec = db.query(PositionRecommendation).get(s.recommendation_id)
        
        sent_mark = "📨" if s.notification_sent else "  "
        decision = s.notification_decision or "pending"
        
        print(f"{s.evaluated_at.strftime('%m/%d %H:%M:%S'):<18} "
              f"{rec.symbol if rec else 'N/A':<8} "
              f"#{s.snapshot_number:<2} "
              f"{s.recommended_action:<12} "
              f"{s.priority:<8} "
              f"{decision:<25} "
              f"{sent_mark}")


def main():
    parser = argparse.ArgumentParser(
        description="Test V2 Recommendation System"
    )
    parser.add_argument("--scan", action="store_true", help="Run a fresh recommendation scan")
    parser.add_argument("--compare", action="store_true", help="Show V1 vs V2 comparison")
    parser.add_argument("--show-snapshots", action="store_true", help="Show V2 snapshot details")
    parser.add_argument("--show-decisions", action="store_true", help="Show notification decision log")
    parser.add_argument("--send-test", action="store_true", help="Send test notification via Telegram")
    parser.add_argument("--symbol", type=str, help="Filter by symbol")
    parser.add_argument("--all", action="store_true", help="Run all tests (except send)")
    
    args = parser.parse_args()
    
    # Default to showing comparison if no args
    if not any([args.scan, args.compare, args.show_snapshots, args.show_decisions, args.send_test, args.all]):
        args.compare = True
        args.show_decisions = True
    
    if args.all:
        args.scan = True
        args.compare = True
        args.show_snapshots = True
        args.show_decisions = True
    
    db = SessionLocal()
    try:
        print("\n" + "=" * 70)
        print("🧪 V2 RECOMMENDATION SYSTEM TEST")
        print("=" * 70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if args.symbol:
            print(f"Filter: {args.symbol.upper()}")
        
        if args.scan:
            run_recommendation_scan(db)
        
        if args.compare:
            show_v1_vs_v2_comparison(db, symbol=args.symbol)
        
        if args.show_snapshots:
            show_v2_snapshots_detail(db, symbol=args.symbol)
        
        if args.show_decisions:
            show_notification_decision_log(db)
        
        if args.send_test:
            send_test_notification(db)
        
        print("\n" + "=" * 70)
        print("✅ TEST COMPLETE")
        print("=" * 70)
        
    finally:
        db.close()


if __name__ == "__main__":
    main()


