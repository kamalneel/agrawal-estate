"""
Telegram Webhook Handler for Recommendation Feedback

Handles incoming replies to recommendation notifications and processes
them as feedback through the feedback service.

Setup (one-time):
1. Your server must be accessible via HTTPS at a public URL
2. Set TELEGRAM_WEBHOOK_SECRET in your environment
3. Call the set_webhook endpoint or use:
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_URL>/api/v1/strategies/telegram/webhook&secret_token=<SECRET>"

Flow:
1. User receives recommendation notification on Telegram
2. User replies directly to the message with feedback
3. Telegram sends the reply to our webhook endpoint
4. We correlate the reply with the original recommendations
5. Feedback is processed through the AI feedback service
"""

import os
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def verify_telegram_webhook(
    secret_token: str,
    provided_token: Optional[str]
) -> bool:
    """
    Verify that the webhook request is from Telegram.
    
    Telegram sends the secret_token in the X-Telegram-Bot-Api-Secret-Token header.
    """
    if not secret_token:
        # If no secret configured, skip verification (not recommended for production)
        logger.warning("TELEGRAM_WEBHOOK_SECRET not set - skipping verification")
        return True
    
    if not provided_token:
        logger.warning("No secret token provided in webhook request")
        return False
    
    return hmac.compare_digest(secret_token, provided_token)


def extract_reply_info(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract relevant information from a Telegram update.
    
    We're looking for:
    - Messages that are replies to our bot's messages
    - The text content of the reply
    - The message_id of the original message being replied to
    
    Returns:
        Dict with reply info or None if not a relevant reply
    """
    message = update.get("message")
    if not message:
        return None
    
    # Check if this is a reply to another message
    reply_to = message.get("reply_to_message")
    if not reply_to:
        return None
    
    # Get the text of the reply
    text = message.get("text", "")
    if not text or not text.strip():
        return None
    
    # Get info about the original message being replied to
    original_message_id = reply_to.get("message_id")
    original_text = reply_to.get("text", "")
    
    # Get chat info
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    
    # Get sender info
    sender = message.get("from", {})
    sender_name = sender.get("first_name", "User")
    sender_username = sender.get("username", "")
    
    return {
        "reply_text": text.strip(),
        "original_message_id": original_message_id,
        "original_text": original_text,
        "chat_id": chat_id,
        "message_id": message.get("message_id"),
        "sender_name": sender_name,
        "sender_username": sender_username,
        "timestamp": message.get("date"),
    }


def find_recommendations_for_message(
    db_session,
    telegram_message_id: int,
    telegram_chat_id: str
) -> Optional[Dict[str, Any]]:
    """
    Find the recommendations that were sent in a specific Telegram message.
    
    Args:
        db_session: Database session
        telegram_message_id: The message_id from Telegram
        telegram_chat_id: The chat_id from Telegram
    
    Returns:
        Dict with recommendation info or None if not found
    """
    from app.modules.strategies.models import TelegramMessageTracking
    
    tracking = db_session.query(TelegramMessageTracking).filter(
        TelegramMessageTracking.telegram_message_id == telegram_message_id,
        TelegramMessageTracking.telegram_chat_id == telegram_chat_id
    ).first()
    
    if not tracking:
        return None
    
    return {
        "tracking_id": tracking.id,
        "recommendation_ids": tracking.recommendation_ids or [],
        "message_text": tracking.message_text,
        "sent_at": tracking.sent_at,
    }


async def process_telegram_reply(
    db_session,
    reply_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a Telegram reply as feedback on recommendations.
    
    Args:
        db_session: Database session
        reply_info: Extracted reply information
    
    Returns:
        Processing result
    """
    from app.modules.strategies.feedback_service import (
        parse_feedback_with_ai,
        save_feedback,
        get_recommendation_by_id
    )
    from app.modules.strategies.models import TelegramMessageTracking
    
    original_message_id = reply_info.get("original_message_id")
    chat_id = reply_info.get("chat_id")
    reply_text = reply_info.get("reply_text")
    
    if not original_message_id or not reply_text:
        return {
            "success": False,
            "error": "Missing message_id or reply text"
        }
    
    # Find the recommendations for this message
    recommendation_info = find_recommendations_for_message(
        db_session, 
        original_message_id, 
        chat_id
    )
    
    if not recommendation_info:
        logger.info(f"No tracked recommendations for message {original_message_id}")
        return {
            "success": False,
            "error": "Could not find recommendations for this message. Make sure you're replying to a recommendation notification."
        }
    
    recommendation_ids = recommendation_info.get("recommendation_ids", [])
    
    if not recommendation_ids:
        return {
            "success": False,
            "error": "No recommendation IDs found for this message"
        }
    
    # Update the tracking record
    tracking = db_session.query(TelegramMessageTracking).filter(
        TelegramMessageTracking.id == recommendation_info["tracking_id"]
    ).first()
    
    if tracking:
        tracking.reply_received = True
        tracking.reply_text = reply_text
        tracking.reply_received_at = datetime.utcnow()
    
    # Process feedback for each recommendation
    # (Usually the user is giving feedback on all recommendations in the batch)
    feedback_results = []
    
    for rec_id in recommendation_ids:
        try:
            # Get recommendation context
            recommendation_context = get_recommendation_by_id(db_session, rec_id)
            if not recommendation_context:
                recommendation_context = {"id": rec_id}
            
            # Parse feedback with AI
            try:
                parsed = await parse_feedback_with_ai(recommendation_context, reply_text)
            except Exception as e:
                logger.error(f"AI parsing failed for {rec_id}: {e}")
                parsed = None
            
            # Save feedback
            feedback_record = save_feedback(
                db=db_session,
                recommendation_id=rec_id,
                raw_feedback=reply_text,
                source="telegram",
                parsed_feedback=parsed,
                recommendation_context=recommendation_context
            )
            
            feedback_results.append({
                "recommendation_id": rec_id,
                "feedback_id": feedback_record.id,
                "reason_code": feedback_record.reason_code,
                "parsed": parsed is not None
            })
            
        except Exception as e:
            logger.error(f"Error processing feedback for {rec_id}: {e}")
            feedback_results.append({
                "recommendation_id": rec_id,
                "error": str(e)
            })
    
    # Mark tracking as processed
    if tracking:
        tracking.feedback_processed = True
        db_session.commit()
    
    logger.info(f"Processed Telegram feedback for {len(feedback_results)} recommendations")
    
    return {
        "success": True,
        "message": f"Feedback received for {len(feedback_results)} recommendation(s)",
        "feedback_results": feedback_results
    }


async def send_telegram_acknowledgment(
    chat_id: str,
    result: Dict[str, Any],
    reply_to_message_id: Optional[int] = None
) -> bool:
    """
    Send an acknowledgment message back to Telegram.
    
    Args:
        chat_id: Telegram chat ID
        result: Processing result
        reply_to_message_id: Message ID to reply to
    
    Returns:
        True if sent successfully
    """
    import requests
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return False
    
    # Format acknowledgment message
    if result.get("success"):
        feedback_count = len(result.get("feedback_results", []))
        reason_codes = [
            r.get("reason_code") 
            for r in result.get("feedback_results", []) 
            if r.get("reason_code")
        ]
        
        if reason_codes:
            unique_reasons = list(set(reason_codes))
            reason_str = ", ".join(unique_reasons[:3])
            message = f"✅ Got it! Feedback recorded ({reason_str}).\n\nI'll use this to improve future recommendations."
        else:
            message = f"✅ Thanks for your feedback! I've recorded it for {feedback_count} recommendation(s)."
    else:
        error = result.get("error", "Unknown error")
        message = f"⚠️ {error}\n\nTo give feedback, reply directly to a recommendation notification."
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
        
    except Exception as e:
        logger.error(f"Failed to send Telegram acknowledgment: {e}")
        return False


def get_telegram_webhook_info() -> Dict[str, Any]:
    """Get current webhook configuration from Telegram."""
    import requests
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN not set"}
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def set_telegram_webhook(webhook_url: str, secret_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Set the Telegram webhook URL.
    
    Args:
        webhook_url: Full HTTPS URL for the webhook endpoint
        secret_token: Optional secret token for verification
    
    Returns:
        Telegram API response
    """
    import requests
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN not set"}
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        data = {
            "url": webhook_url,
            "allowed_updates": ["message"],  # Only receive message updates
        }
        
        if secret_token:
            data["secret_token"] = secret_token
        
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        return {"error": str(e)}


def delete_telegram_webhook() -> Dict[str, Any]:
    """Delete the Telegram webhook (switch back to polling mode)."""
    import requests
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN not set"}
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        return {"error": str(e)}

