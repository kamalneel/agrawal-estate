"""
Price Alert Manager

Stores condition-based price alerts (e.g., "alert me if TSLA drops below 420").
Alerts are persisted to data/price_alerts.json and checked on an interval.
"""

import json
import os
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

_ALERTS_FILE = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "price_alerts.json"


class AlertCondition(str, Enum):
    BELOW = "below"
    ABOVE = "above"


@dataclass
class PriceAlert:
    id: str
    symbol: str
    condition: str          # "below" or "above"
    target_price: float
    check_interval_minutes: int = 10
    note: str = ""
    created_at: str = ""
    triggered: bool = False
    triggered_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class PriceAlertManager:
    """Load, save, check, and manage price alerts."""

    def __init__(self, alerts_file: Path = _ALERTS_FILE):
        self._file = alerts_file
        self._alerts: List[PriceAlert] = []
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._alerts = [PriceAlert(**a) for a in data.get("alerts", [])]
            except Exception as e:
                logger.warning(f"Could not load price alerts: {e}")
                self._alerts = []

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"alerts": [asdict(a) for a in self._alerts]}
        self._file.write_text(json.dumps(payload, indent=2))

    def add_alert(
        self,
        symbol: str,
        condition: AlertCondition,
        target_price: float,
        check_interval_minutes: int = 10,
        note: str = "",
    ) -> PriceAlert:
        alert = PriceAlert(
            id=str(uuid.uuid4())[:8],
            symbol=symbol.upper(),
            condition=condition.value,
            target_price=target_price,
            check_interval_minutes=check_interval_minutes,
            note=note,
        )
        self._alerts.append(alert)
        self._save()
        logger.info(f"Price alert added: {symbol} {condition.value} ${target_price}")
        return alert

    def list_alerts(self) -> List[PriceAlert]:
        return [a for a in self._alerts if not a.triggered]

    def remove_alert(self, alert_id: str) -> bool:
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.id != alert_id]
        if len(self._alerts) < before:
            self._save()
            return True
        return False

    def cancel_by_symbol(self, symbol: str) -> int:
        """Cancel all active alerts for a symbol. Returns number removed."""
        sym = symbol.upper()
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.symbol != sym or a.triggered]
        removed = before - len(self._alerts)
        if removed:
            self._save()
        return removed

    def check_all(self) -> List[Dict[str, Any]]:
        """
        Check all active alerts against current prices.
        Returns list of triggered alert dicts (each includes 'alert' and 'current_price').
        Marks triggered alerts and saves.
        """
        active = [a for a in self._alerts if not a.triggered]
        if not active:
            return []

        # Fetch prices for all unique symbols
        symbols = list({a.symbol for a in active})
        prices = _fetch_current_prices(symbols)

        triggered = []
        for alert in active:
            price = prices.get(alert.symbol)
            if price is None:
                continue

            fired = (
                (alert.condition == AlertCondition.BELOW.value and price < alert.target_price) or
                (alert.condition == AlertCondition.ABOVE.value and price > alert.target_price)
            )
            if fired:
                alert.triggered = True
                alert.triggered_at = datetime.now().isoformat()
                triggered.append({"alert": alert, "current_price": price})
                logger.info(
                    f"Price alert triggered: {alert.symbol} is ${price:.2f} "
                    f"({alert.condition} ${alert.target_price:.2f})"
                )

        if triggered:
            self._save()

        return triggered


def _fetch_current_prices(symbols: List[str]) -> Dict[str, float]:
    """Fetch current prices for a list of symbols using the TA service."""
    try:
        from app.modules.strategies.technical_analysis import TechnicalAnalysisService
        svc = TechnicalAnalysisService()
        prices = {}
        for sym in symbols:
            try:
                ta = svc.get_technical_indicators(sym)
                if ta and ta.current_price:
                    prices[sym] = ta.current_price
            except Exception as e:
                logger.warning(f"Could not fetch price for {sym}: {e}")
        return prices
    except Exception as e:
        logger.warning(f"Price fetch failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# HTML notification builder (for price alert trigger emails)
# ---------------------------------------------------------------------------

def build_price_alert_email_html(alert: PriceAlert, current_price: float) -> str:
    """Build a rich HTML email for a triggered price alert."""
    cond = "dropped below" if alert.condition == "below" else "risen above"
    color = "#dc2626" if alert.condition == "below" else "#16a34a"
    icon = "↓" if alert.condition == "below" else "↑"
    now_str = datetime.now().strftime("%A, %B %-d · %-I:%M %p PT")

    pct_diff = abs(current_price - alert.target_price) / alert.target_price * 100

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
             font-size:15px; line-height:1.6; color:#111827; max-width:560px;
             margin:0 auto; padding:24px 20px; background:#ffffff;">
  <div style="border-bottom:2px solid {color}; padding-bottom:10px; margin-bottom:20px;">
    <div style="font-size:17px; font-weight:700; color:{color};">{icon} Price Alert — {alert.symbol}</div>
    <div style="font-size:12px; color:#6b7280; margin-top:2px;">{now_str}</div>
  </div>
  <div style="border:1px solid {color}40; border-radius:8px; overflow:hidden; margin-bottom:20px;">
    <div style="background:{color}; color:#fff; padding:12px 18px; font-size:18px; font-weight:700;">
      {alert.symbol} has {cond} ${alert.target_price:,.2f}
    </div>
    <div style="padding:16px 18px;">
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="color:#6b7280; padding:6px 0; width:160px;">Current Price</td>
          <td style="font-weight:700; font-size:18px; color:{color};">${current_price:,.2f}</td>
        </tr>
        <tr>
          <td style="color:#6b7280; padding:6px 0;">Alert Target</td>
          <td style="font-weight:600;">${alert.target_price:,.2f}</td>
        </tr>
        <tr>
          <td style="color:#6b7280; padding:6px 0;">Difference</td>
          <td style="color:{color};">{pct_diff:.1f}% past target</td>
        </tr>
        <tr>
          <td style="color:#6b7280; padding:6px 0;">Set on</td>
          <td style="color:#6b7280; font-size:13px;">{alert.created_at[:10]}</td>
        </tr>
      </table>
      {f'<p style="margin:12px 0 0; color:#6b7280; font-size:13px;">Note: {alert.note}</p>' if alert.note else ''}
    </div>
  </div>
  <div style="margin-top:16px; padding-top:14px; border-top:1px solid #e5e7eb;
              font-size:12px; color:#9ca3af;">
    Reply to this email to ask follow-up questions or set new price alerts.<br>
    — Your Estate Planner Assistant
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[PriceAlertManager] = None


def get_price_alert_manager() -> PriceAlertManager:
    global _manager
    if _manager is None:
        _manager = PriceAlertManager()
    return _manager
