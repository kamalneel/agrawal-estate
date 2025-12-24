"""
Telegram Polling Service for Reply Feedback

This service polls Telegram for new messages/replies and processes them as feedback.
Used when webhook setup isn't available (localhost development, no public URL).

Usage:
    # Run once manually:
    python -m app.shared.services.telegram_poller
    
    # Or import and call:
    from app.shared.services.telegram_poller import poll_and_process_replies
    await poll_and_process_replies()
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import requests

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.strategies.models import RecommendationFeedback, TelegramMessageTracking

logger = logging.getLogger(__name__)

# Store the last processed update_id to avoid reprocessing
OFFSET_FILE = "/tmp/telegram_poller_offset.txt"


def get_last_offset() -> Optional[int]:
    """Get the last processed update_id from file."""
    try:
        with open(OFFSET_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def save_offset(offset: int):
    """Save the last processed update_id to file."""
    with open(OFFSET_FILE, 'w') as f:
        f.write(str(offset))


def extract_symbols_from_text(text: str) -> List[str]:
    """Extract stock symbols mentioned in the feedback text."""
    # Common stock patterns
    symbols = []
    
    # Look for explicit symbol mentions
    symbol_patterns = [
        r'\b(NVDA|NVIDIA)\b',
        r'\b(AAPL|APPLE)\b',
        r'\b(MSFT|MICROSOFT)\b',
        r'\b(GOOGL?|GOOGLE)\b',
        r'\b(AMZN|AMAZON)\b',
        r'\b(META|FACEBOOK)\b',
        r'\b(TSLA|TESLA)\b',
        r'\b(AVGO|BROADCOM)\b',
        r'\b(NFLX|NETFLIX)\b',
        r'\b(IBIT)\b',
        r'\b(BABA|ALIBABA)\b',
        r'\b(AMD)\b',
        r'\b(QQQ)\b',
        r'\b(SPY)\b',
    ]
    
    text_upper = text.upper()
    for pattern in symbol_patterns:
        if re.search(pattern, text_upper):
            match = re.search(pattern, text_upper)
            if match:
                symbol = match.group(1)
                # Normalize to ticker
                symbol_map = {
                    'NVIDIA': 'NVDA', 'APPLE': 'AAPL', 'MICROSOFT': 'MSFT',
                    'GOOGLE': 'GOOGL', 'AMAZON': 'AMZN', 'FACEBOOK': 'META',
                    'TESLA': 'TSLA', 'BROADCOM': 'AVGO', 'NETFLIX': 'NFLX',
                    'ALIBABA': 'BABA'
                }
                symbols.append(symbol_map.get(symbol, symbol))
    
    return list(set(symbols))


def classify_feedback(text: str) -> Dict[str, Any]:
    """
    Simple keyword-based classification of feedback.
    Returns structured feedback data.
    """
    text_lower = text.lower()
    
    # Determine reason code
    reason_code = 'general_feedback'
    
    if any(word in text_lower for word in ['delta', 'delta 10', 'delta 2', 'delta 1', 'delta one', 'delta two']):
        reason_code = 'algorithm_issue'
    elif any(word in text_lower for word in ['premium', 'too small', 'too low', 'not worth']):
        reason_code = 'premium_small'
    elif any(word in text_lower for word in ['timing', 'market', 'volatile']):
        reason_code = 'timing_bad'
    elif any(word in text_lower for word in ['incorrect', 'wrong', 'mistake', 'error', 'bug']):
        reason_code = 'algorithm_issue'
    
    # Determine sentiment
    sentiment = 'neutral'
    if any(word in text_lower for word in ['way too', 'incorrect', 'wrong', 'problem', 'mistake']):
        sentiment = 'frustrated'
    
    # Extract any mentioned dollar amounts for threshold hints
    threshold_hint = None
    dollar_match = re.search(r'\$(\d+(?:\.\d+)?)', text)
    if dollar_match:
        threshold_hint = float(dollar_match.group(1))
    
    # Extract symbols
    symbols = extract_symbols_from_text(text)
    
    # Generate actionable insight
    if reason_code == 'algorithm_issue':
        actionable_insight = f"Check delta/strike calculation logic. User reports incorrect delta values."
    elif reason_code == 'premium_small':
        if threshold_hint:
            actionable_insight = f"Premium of ${threshold_hint} considered too small. Consider raising min_premium threshold."
        else:
            actionable_insight = "Premium considered too small. Consider raising min_premium threshold."
    else:
        actionable_insight = "User provided feedback - review manually"
    
    return {
        'reason_code': reason_code,
        'reason_detail': text[:200],  # First 200 chars as detail
        'threshold_hint': threshold_hint,
        'symbols': symbols,
        'sentiment': sentiment,
        'actionable_insight': actionable_insight
    }


def process_telegram_update(update: Dict[str, Any], db) -> bool:
    """
    Process a single Telegram update and save as feedback if it's a reply.
    Returns True if feedback was saved.
    """
    message = update.get('message', {})
    
    # Check if this is a reply to a bot message
    reply_to = message.get('reply_to_message')
    if not reply_to:
        logger.debug(f"Update {update.get('update_id')} is not a reply, skipping")
        return False
    
    # Verify it's a reply to our bot
    reply_from = reply_to.get('from', {})
    if not reply_from.get('is_bot'):
        logger.debug(f"Reply is not to a bot message, skipping")
        return False
    
    # Extract feedback text
    feedback_text = message.get('text', '')
    if not feedback_text:
        logger.debug(f"No text in reply, skipping")
        return False
    
    # Get user info
    from_user = message.get('from', {})
    user_name = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()
    chat_id = message.get('chat', {}).get('id')
    message_id = message.get('message_id')
    original_message_id = reply_to.get('message_id')
    
    logger.info(f"Processing Telegram reply from {user_name}: {feedback_text[:50]}...")
    
    # Classify the feedback
    parsed = classify_feedback(feedback_text)
    symbols = parsed.pop('symbols', [])
    
    # Create feedback record(s) - one per symbol mentioned, or one general if no symbols
    if not symbols:
        symbols = [None]  # Create at least one record
    
    for symbol in symbols:
        feedback = RecommendationFeedback(
            recommendation_id=None,  # Not linked to specific rec
            source='telegram',
            raw_feedback=feedback_text,
            reason_code=parsed['reason_code'],
            reason_detail=parsed['reason_detail'],
            threshold_hint=parsed['threshold_hint'],
            symbol=symbol,
            sentiment=parsed['sentiment'],
            actionable_insight=parsed['actionable_insight'],
            parsing_status='parsed',
            parsed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.add(feedback)
        logger.info(f"  Saved feedback for symbol: {symbol or 'general'}")
    
    db.commit()
    
    # Send acknowledgment to user
    try:
        send_acknowledgment(chat_id, message_id, parsed['reason_code'], symbols)
    except Exception as e:
        logger.warning(f"Failed to send acknowledgment: {e}")
    
    return True


def send_acknowledgment(chat_id: int, reply_to_message_id: int, reason_code: str, symbols: List[str]):
    """Send a thank-you message back to the user."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        return
    
    symbol_text = ", ".join(s for s in symbols if s) if any(symbols) else "your recommendations"
    
    message = (
        f"✅ *Feedback received!*\n\n"
        f"Thanks for your input on {symbol_text}.\n"
        f"Detected issue type: _{reason_code.replace('_', ' ')}_\n\n"
        f"This will help improve future recommendations."
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_to_message_id": reply_to_message_id
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        logger.info(f"Sent acknowledgment to chat {chat_id}")
    else:
        logger.warning(f"Failed to send acknowledgment: {response.text}")


def poll_telegram_updates() -> List[Dict[str, Any]]:
    """Poll Telegram for new updates."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return []
    
    offset = get_last_offset()
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset + 1  # Only get updates after the last processed one
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get('ok'):
            return data.get('result', [])
        else:
            logger.error(f"Telegram API error: {data}")
            return []
    except Exception as e:
        logger.error(f"Failed to poll Telegram: {e}")
        return []


async def poll_and_process_replies() -> Dict[str, Any]:
    """
    Main function to poll Telegram and process any reply feedback.
    Returns stats about what was processed.
    """
    updates = poll_telegram_updates()
    
    if not updates:
        return {"status": "no_updates", "processed": 0}
    
    db = SessionLocal()
    processed_count = 0
    last_update_id = None
    
    try:
        for update in updates:
            last_update_id = update.get('update_id')
            if process_telegram_update(update, db):
                processed_count += 1
        
        # Save the last processed update_id
        if last_update_id:
            save_offset(last_update_id)
        
        return {
            "status": "success",
            "updates_received": len(updates),
            "feedback_saved": processed_count,
            "last_update_id": last_update_id
        }
    
    except Exception as e:
        logger.exception(f"Error processing updates: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    
    finally:
        db.close()


def run_poller_once():
    """Synchronous wrapper to run the poller once."""
    return asyncio.run(poll_and_process_replies())


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🔍 Polling Telegram for replies...")
    result = run_poller_once()
    print(f"\n📊 Result: {result}")

