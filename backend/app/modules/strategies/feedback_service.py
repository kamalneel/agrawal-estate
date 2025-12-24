"""
Feedback Service for Recommendation Learning (V4 Preparation)

Captures natural language feedback from users and uses AI to extract
structured insights for algorithm improvement.

Flow:
1. User provides natural language feedback on a recommendation
2. AI parses the feedback to extract structured insights
3. Insights are stored for pattern analysis
4. Periodic analysis generates V4 improvement suggestions
"""

import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.modules.strategies.models import (
    RecommendationFeedback,
    StrategyRecommendationRecord
)

logger = logging.getLogger(__name__)

# Predefined reason codes for categorization
REASON_CODES = {
    "premium_small": "Premium too small / not worth the effort",
    "premium_large": "Premium unexpectedly high (suspicious)",
    "timing_bad": "Wrong timing / market conditions",
    "stock_preference": "Don't want to sell/cap upside on this stock",
    "already_planned": "Already have a plan for this",
    "strike_aggressive": "Strike too aggressive / too close",
    "strike_conservative": "Strike too conservative / too far",
    "duration_long": "Roll duration too long",
    "duration_short": "Roll duration too short",
    "account_preference": "Account-specific preference",
    "liquidity_concern": "Liquidity or spread concerns",
    "earnings_risk": "Earnings or event risk",
    "other": "Other reason",
}


async def parse_feedback_with_ai(
    recommendation_context: Dict[str, Any],
    user_feedback: str
) -> Dict[str, Any]:
    """
    Use Claude/OpenAI to parse natural language feedback into structured insights.
    
    Args:
        recommendation_context: The original recommendation details
        user_feedback: User's natural language feedback
    
    Returns:
        Structured feedback dict with reason_code, threshold_hint, etc.
    """
    try:
        import anthropic
        
        client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        
        # Build context string from recommendation
        context_str = _format_recommendation_context(recommendation_context)
        
        prompt = f"""You are analyzing user feedback on a stock options trading notification.

ORIGINAL NOTIFICATION:
{context_str}

USER'S FEEDBACK:
"{user_feedback}"

Based on this feedback, extract structured insights. Return ONLY valid JSON (no markdown, no explanation):

{{
    "reason_code": "one of: premium_small, premium_large, timing_bad, stock_preference, already_planned, strike_aggressive, strike_conservative, duration_long, duration_short, account_preference, liquidity_concern, earnings_risk, other",
    "reason_detail": "brief 1-sentence explanation of what the user meant",
    "threshold_hint": number or null (if user mentioned a specific dollar amount or percentage as too small/large, extract it),
    "symbol_specific": true or false (is this feedback specific to this particular stock, or general?),
    "sentiment": "neutral, frustrated, or positive",
    "actionable_insight": "what should the trading algorithm learn from this feedback? Be specific about what parameter or behavior to adjust"
}}

Examples:
- "premium is only $8, not worth it" → threshold_hint: 8, reason_code: "premium_small"
- "I don't want to cap NVDA right now" → symbol_specific: true, reason_code: "stock_preference"
- "8 weeks is too long" → threshold_hint: 8, reason_code: "duration_long"
"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        response_text = message.content[0].text.strip()
        
        # Parse JSON response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        parsed = json.loads(response_text)
        
        # Validate reason_code
        if parsed.get("reason_code") not in REASON_CODES:
            parsed["reason_code"] = "other"
        
        return parsed
        
    except Exception as e:
        logger.error(f"AI feedback parsing failed: {e}")
        # Return basic parsing if AI fails
        return _fallback_parse(user_feedback)


def _format_recommendation_context(context: Dict[str, Any]) -> str:
    """Format recommendation context for the AI prompt."""
    parts = []
    
    if context.get("type"):
        parts.append(f"Type: {context['type']}")
    if context.get("symbol"):
        parts.append(f"Symbol: {context['symbol']}")
    if context.get("title"):
        parts.append(f"Title: {context['title']}")
    if context.get("description"):
        parts.append(f"Description: {context['description']}")
    if context.get("account_name"):
        parts.append(f"Account: {context['account_name']}")
    
    # Extract key context fields
    ctx = context.get("context", {})
    if ctx.get("strike_price"):
        parts.append(f"Strike: ${ctx['strike_price']}")
    if ctx.get("current_price"):
        parts.append(f"Stock Price: ${ctx['current_price']}")
    if ctx.get("premium_per_contract"):
        parts.append(f"Premium: ${ctx['premium_per_contract']}/contract")
    if ctx.get("total_premium"):
        parts.append(f"Total Premium: ${ctx['total_premium']}")
    if ctx.get("unsold_contracts"):
        parts.append(f"Contracts: {ctx['unsold_contracts']}")
    
    return "\n".join(parts) if parts else str(context)


def _fallback_parse(feedback: str) -> Dict[str, Any]:
    """Simple keyword-based parsing if AI fails."""
    feedback_lower = feedback.lower()
    
    result = {
        "reason_code": "other",
        "reason_detail": feedback[:200],
        "threshold_hint": None,
        "symbol_specific": False,
        "sentiment": "neutral",
        "actionable_insight": "User provided feedback - review manually"
    }
    
    # Simple keyword matching
    if any(word in feedback_lower for word in ["small", "low", "not worth", "too little"]):
        result["reason_code"] = "premium_small"
    elif any(word in feedback_lower for word in ["timing", "market", "volatile", "crazy"]):
        result["reason_code"] = "timing_bad"
    elif any(word in feedback_lower for word in ["cap", "upside", "bullish", "don't want to sell"]):
        result["reason_code"] = "stock_preference"
        result["symbol_specific"] = True
    elif any(word in feedback_lower for word in ["already", "planned", "later", "manually"]):
        result["reason_code"] = "already_planned"
    elif any(word in feedback_lower for word in ["strike", "close", "aggressive"]):
        result["reason_code"] = "strike_aggressive"
    elif any(word in feedback_lower for word in ["long", "weeks", "lock up"]):
        result["reason_code"] = "duration_long"
    
    # Try to extract numbers
    import re
    numbers = re.findall(r'\$?(\d+(?:\.\d{2})?)', feedback)
    if numbers:
        result["threshold_hint"] = float(numbers[0])
    
    return result


def save_feedback(
    db: Session,
    recommendation_id: str,
    raw_feedback: str,
    source: str,
    parsed_feedback: Optional[Dict[str, Any]] = None,
    recommendation_context: Optional[Dict[str, Any]] = None
) -> RecommendationFeedback:
    """
    Save user feedback to the database.
    
    Args:
        db: Database session
        recommendation_id: ID of the recommendation being commented on
        raw_feedback: User's natural language feedback
        source: 'web', 'telegram', or 'api'
        parsed_feedback: AI-parsed structured feedback (optional)
        recommendation_context: Context snapshot of the recommendation
    
    Returns:
        Created RecommendationFeedback record
    """
    feedback_record = RecommendationFeedback(
        recommendation_id=recommendation_id,
        source=source,
        raw_feedback=raw_feedback,
        context_snapshot=recommendation_context,
    )
    
    # Add recommendation metadata if available
    if recommendation_context:
        feedback_record.recommendation_type = recommendation_context.get("type")
        feedback_record.symbol = recommendation_context.get("symbol")
        feedback_record.account_name = recommendation_context.get("account_name")
    
    # Add parsed feedback if available
    if parsed_feedback:
        feedback_record.reason_code = parsed_feedback.get("reason_code")
        feedback_record.reason_detail = parsed_feedback.get("reason_detail")
        feedback_record.threshold_hint = parsed_feedback.get("threshold_hint")
        feedback_record.symbol_specific = parsed_feedback.get("symbol_specific")
        feedback_record.sentiment = parsed_feedback.get("sentiment")
        feedback_record.actionable_insight = parsed_feedback.get("actionable_insight")
        feedback_record.parsing_status = "parsed"
        feedback_record.parsed_at = datetime.utcnow()
    else:
        feedback_record.parsing_status = "pending"
    
    db.add(feedback_record)
    db.commit()
    db.refresh(feedback_record)
    
    logger.info(f"Saved feedback for recommendation {recommendation_id}: {raw_feedback[:50]}...")
    
    return feedback_record


def get_feedback_insights(
    db: Session,
    days_back: int = 30,
    min_occurrences: int = 3
) -> Dict[str, Any]:
    """
    Analyze feedback patterns to generate V4 insights.
    
    Args:
        db: Database session
        days_back: How many days of feedback to analyze
        min_occurrences: Minimum occurrences to report a pattern
    
    Returns:
        Dict with patterns and suggested algorithm improvements
    """
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    # Get all feedback in the period
    feedback_records = db.query(RecommendationFeedback).filter(
        RecommendationFeedback.created_at >= cutoff,
        RecommendationFeedback.parsing_status == "parsed"
    ).all()
    
    if not feedback_records:
        return {"message": "No feedback data available", "patterns": [], "suggestions": []}
    
    # Analyze patterns
    patterns = []
    suggestions = []
    
    # Pattern 1: Reason code frequency
    reason_counts = {}
    for fb in feedback_records:
        code = fb.reason_code or "unknown"
        reason_counts[code] = reason_counts.get(code, 0) + 1
    
    for reason, count in reason_counts.items():
        if count >= min_occurrences:
            patterns.append({
                "type": "reason_frequency",
                "reason_code": reason,
                "count": count,
                "percentage": round(count / len(feedback_records) * 100, 1),
                "description": REASON_CODES.get(reason, reason)
            })
    
    # Pattern 2: Premium thresholds
    premium_thresholds = [
        fb.threshold_hint for fb in feedback_records
        if fb.reason_code == "premium_small" and fb.threshold_hint
    ]
    if len(premium_thresholds) >= min_occurrences:
        avg_threshold = sum(premium_thresholds) / len(premium_thresholds)
        patterns.append({
            "type": "premium_threshold",
            "average_mentioned": round(avg_threshold, 2),
            "count": len(premium_thresholds),
            "values": premium_thresholds[:10]  # First 10 examples
        })
        suggestions.append({
            "finding": f"User mentions premium is 'too small' with average value ${avg_threshold:.0f}",
            "suggestion": f"Consider raising minimum premium threshold to ${avg_threshold:.0f}/contract",
            "config_key": "min_weekly_income",
            "suggested_value": avg_threshold
        })
    
    # Pattern 3: Symbol-specific preferences
    symbol_skips = {}
    for fb in feedback_records:
        if fb.symbol_specific and fb.symbol:
            symbol_skips[fb.symbol] = symbol_skips.get(fb.symbol, 0) + 1
    
    for symbol, count in symbol_skips.items():
        if count >= min_occurrences:
            patterns.append({
                "type": "symbol_preference",
                "symbol": symbol,
                "skip_count": count,
                "description": f"User frequently skips {symbol} recommendations"
            })
            suggestions.append({
                "finding": f"You skip {symbol} recommendations {count} times",
                "suggestion": f"Consider adding {symbol} to a 'reduced notification' list",
                "config_key": f"symbol_preferences.{symbol}",
                "suggested_value": "reduce_notifications"
            })
    
    # Pattern 4: Duration preferences
    duration_thresholds = [
        fb.threshold_hint for fb in feedback_records
        if fb.reason_code == "duration_long" and fb.threshold_hint
    ]
    if len(duration_thresholds) >= min_occurrences:
        avg_duration = sum(duration_thresholds) / len(duration_thresholds)
        patterns.append({
            "type": "duration_threshold",
            "average_mentioned": round(avg_duration, 1),
            "count": len(duration_thresholds),
            "description": f"User finds rolls > {avg_duration:.0f} weeks too long"
        })
        suggestions.append({
            "finding": f"You frequently skip rolls longer than {avg_duration:.0f} weeks",
            "suggestion": f"Consider capping max roll duration at {avg_duration:.0f} weeks",
            "config_key": "max_roll_weeks",
            "suggested_value": int(avg_duration)
        })
    
    return {
        "period_days": days_back,
        "total_feedback": len(feedback_records),
        "patterns": sorted(patterns, key=lambda x: x.get("count", 0), reverse=True),
        "suggestions": suggestions,
        "generated_at": datetime.utcnow().isoformat()
    }


def get_recommendation_by_id(db: Session, recommendation_id: str) -> Optional[Dict[str, Any]]:
    """Get recommendation details by ID for feedback context."""
    record = db.query(StrategyRecommendationRecord).filter(
        StrategyRecommendationRecord.recommendation_id == recommendation_id
    ).first()
    
    if not record:
        return None
    
    return {
        "id": record.recommendation_id,
        "type": record.recommendation_type,
        "title": record.title,
        "description": record.description,
        "symbol": record.symbol,
        "account_name": record.account_name,
        "context": record.context_snapshot,
        "created_at": record.created_at.isoformat() if record.created_at else None
    }

