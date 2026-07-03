"""
Email Inbound Webhook Router

Receives inbound email events from Resend and dispatches to the email assistant.

Resend sends a POST with JSON body when an email arrives at assistant@neellab.info.
We ack immediately (200) and do the work in a background task.
"""

import os
import logging
import hmac
import hashlib
from typing import Optional

import requests
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_resend_signature(raw_body: bytes, headers: dict) -> bool:
    """Verify the Resend webhook signature using svix."""
    secret = os.getenv("RESEND_WEBHOOK_SECRET", "").strip()
    if not secret:
        logger.warning("RESEND_WEBHOOK_SECRET not set — skipping signature verification")
        return True

    try:
        from svix.webhooks import Webhook, WebhookVerificationError
        wh = Webhook(secret)
        wh.verify(raw_body, {
            "svix-id": headers.get("svix-id", ""),
            "svix-timestamp": headers.get("svix-timestamp", ""),
            "svix-signature": headers.get("svix-signature", ""),
        })
        return True
    except Exception as e:
        logger.warning(f"Webhook signature verification failed: {e}")
        return False


def _fetch_email_body(email_id: str) -> Optional[dict]:
    """Fetch the full email (including body) from Resend's receiving API."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"https://api.resend.com/emails/receiving/{email_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.ok:
            return resp.json()
        logger.warning(f"Resend fetch failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Error fetching email body: {e}")
    return None


def _strip_html_tags(html: str) -> str:
    """Very simple HTML → plain text for when only HTML body is available."""
    import re
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return "\n".join(line for line in html.splitlines() if line.strip())


def _process_inbound(payload: dict):
    """Background task: fetch full email, call assistant, send reply."""
    db: Session = SessionLocal()
    try:
        data = payload.get("data", {})
        email_id = data.get("email_id") or data.get("id")
        from_addr = data.get("from", "")
        subject = data.get("subject", "(no subject)")

        if not email_id:
            logger.warning("Inbound webhook missing email_id — cannot fetch body")
            return

        full = _fetch_email_body(email_id)
        if not full:
            logger.warning(f"Could not fetch email body for id={email_id}")
            return

        from_addr = full.get("from") or from_addr
        subject = full.get("subject") or subject
        body = full.get("text") or ""
        if not body.strip() and full.get("html"):
            body = _strip_html_tags(full["html"])

        if not body.strip():
            logger.info(f"Empty body for email_id={email_id} — skipping")
            return

        from app.shared.services.email_assistant import handle_inbound_email
        handle_inbound_email(from_addr=from_addr, subject=subject, body=body, db=db)

    except Exception as e:
        logger.error(f"Error in inbound email processing: {e}", exc_info=True)
    finally:
        db.close()


@router.post("/inbound")
async def receive_inbound_email(request: Request, background_tasks: BackgroundTasks):
    """
    Resend webhook endpoint for received emails.

    Returns 200 immediately; processing happens in a background task
    so Resend doesn't time out and retry (which would cause duplicate replies).
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    if not _verify_resend_signature(raw_body, headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        import json
        payload = json.loads(raw_body)
    except Exception:
        return {"received": True}

    # Only handle email.received events
    event_type = payload.get("type", "")
    if event_type and event_type != "email.received":
        return {"received": True}

    # Ack immediately, process in background
    background_tasks.add_task(_process_inbound, payload)
    return {"received": True}


@router.get("/inbound")
async def webhook_health():
    """Health check — Resend pings GET to verify the endpoint exists."""
    return {"ok": True}
