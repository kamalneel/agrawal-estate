"""
Email Assistant — Rich HTML Response System

Handles inbound email replies. Fetches portfolio context + live technical data,
calls Claude for a brief interpretation, and replies with a formatted HTML email.
"""

import os
import re
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common English words / non-ticker uppercase words to exclude from extraction
# ---------------------------------------------------------------------------
_NON_TICKERS = {
    "A", "AN", "AM", "AND", "ARE", "AT", "ATM", "BE", "BB", "BUT", "BY",
    "BTC", "BUY", "CALL", "CAN", "DO", "DAY", "DATE", "DONE", "EACH",
    "EIN", "EPS", "ET", "ETF", "FOR", "FWD", "FW", "FIND", "FROM",
    "GET", "GIVE", "HE", "HER", "HIM", "HIS", "HIGH", "HAVE", "HAD",
    "HAS", "HOW", "I", "IF", "IN", "IS", "IT", "IRA", "ITM", "IV",
    "INTO", "ITS", "JUST", "K1", "LAST", "LIKE", "LIST", "LOOK",
    "LOSS", "LOW", "MA", "MAKE", "MY", "ME", "MORE", "NET", "NEW",
    "NEXT", "NO", "NOT", "NOW", "OF", "OFF", "OK", "ON", "ONE",
    "OR", "OTM", "OUT", "OPEN", "PM", "PT", "PST", "PUT", "RE",
    "RSI", "SELL", "SEND", "SET", "SHE", "SHOW", "SOME", "SO",
    "STO", "TELL", "THAN", "THE", "THEM", "THEY", "THAT", "THIS",
    "THEN", "TO", "TOO", "TOP", "TWO", "US", "UP", "USD",
    "V3", "V4", "V5", "V6", "WAS", "WE", "WEEK", "WILL",
    "WITH", "WHAT", "WHEN", "WHERE", "WHICH", "YOU", "YEAR",
    "EST", "PST", "PDT", "EDT",
}

_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")

# Known tickers that would otherwise match common words
_KNOWN_TICKERS = {"T", "F", "A", "M", "C", "U", "D", "E", "O", "W", "X", "Z"}


def _extract_symbols(text: str) -> List[str]:
    """Extract likely stock tickers from the user's question."""
    seen: Dict[str, int] = {}
    for m in _TICKER_RE.finditer(text.upper()):
        word = m.group(1)
        if word in _NON_TICKERS:
            continue
        seen[word] = seen.get(word, 0) + 1

    # Also check for single-letter known tickers explicitly mentioned
    for ticker in _KNOWN_TICKERS:
        if f" {ticker} " in f" {text.upper()} ":
            seen[ticker] = seen.get(ticker, 0) + 1

    return list(seen.keys())[:6]  # cap at 6 symbols per question


def _detect_intents(question: str) -> Dict[str, bool]:
    """Detect what types of analysis the user is asking for."""
    q = question.lower()
    return {
        "technical_analysis": any(w in q for w in [
            "technical", "rsi", "trend", "bollinger", "moving average", "ma50", "ma200",
            "iv", "volatility", "support", "resistance", "analysis", "where is",
            "close my", "closed my", "just closed",
        ]),
        "position_screening": any(w in q for w in [
            "should i open", "which account", "where should i", "uncovered",
            "new position", "sell a", "sell covered", "sell put", "which stocks",
            "open new", "how many", "unsold",
        ]),
        "at_risk": any(w in q for w in [
            "at risk", "in the money", "itm", "going to lose", "make a loss",
            "loss on", "assignment", "losing position", "trouble",
        ]),
        "algo_fit": any(w in q for w in [
            "algorithm", "v5", "v6", "fit my", "qualify", "criteria", "strategy",
            "does it fit", "should i add",
        ]),
        "price_alert": any(w in q for w in [
            "alert me", "notify me", "watch", "monitor", "keep checking",
            "if it goes", "if it drops", "if it falls", "if it rises",
            "if it hits", "price alert", "send me an alert",
            "cancel alert", "stop watching", "remove alert", "stop alert",
            "list alerts", "active alerts", "what alerts", "my alerts",
        ]),
        "portfolio_summary": any(w in q for w in [
            "portfolio", "balance", "total value", "p&l", "profit", "how am i doing",
            "net worth", "account balance", "holdings",
        ]),
    }


def _strip_quoted_reply(body: str) -> str:
    """Keep only the new part of an email reply — strip quoted history."""
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            break
        if stripped in ("--", "—", "___", "---"):
            break
        if re.match(r"^On .{5,80} wrote:$", stripped):
            break
        lines.append(line)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# HTML building helpers (all inline styles for email client compat)
# ---------------------------------------------------------------------------

_CARD_STYLE = (
    "border:1px solid #e2e8f0; border-radius:8px; margin-bottom:20px; "
    "overflow:hidden; font-size:14px;"
)
_HEADER_BLUE = (
    "background:#2563eb; color:#ffffff; padding:10px 16px; "
    "font-weight:700; font-size:14px;"
)
_HEADER_RED = (
    "background:#dc2626; color:#ffffff; padding:10px 16px; "
    "font-weight:700; font-size:14px;"
)
_HEADER_AMBER = (
    "background:#d97706; color:#ffffff; padding:10px 16px; "
    "font-weight:700; font-size:14px;"
)
_HEADER_GREEN = (
    "background:#16a34a; color:#ffffff; padding:10px 16px; "
    "font-weight:700; font-size:14px;"
)
_HEADER_PURPLE = (
    "background:#7c3aed; color:#ffffff; padding:10px 16px; "
    "font-weight:700; font-size:14px;"
)
_BODY_PAD = "padding:14px 16px;"
_TH = (
    "background:#f1f5f9; color:#374151; font-size:12px; font-weight:600; "
    "text-transform:uppercase; padding:6px 10px; text-align:left; "
    "border-bottom:1px solid #e2e8f0;"
)
_TD = "padding:6px 10px; border-bottom:1px solid #f1f5f9; color:#111827;"
_TD_MONO = "padding:6px 10px; border-bottom:1px solid #f1f5f9; font-family:monospace; color:#111827;"


def _badge(text: str, color: str = "#6b7280") -> str:
    return (
        f'<span style="display:inline-block; padding:2px 8px; border-radius:12px; '
        f'font-size:11px; font-weight:600; background:{color}20; color:{color};">{text}</span>'
    )


def _trend_badge(trend: str) -> str:
    colors = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#6b7280"}
    labels = {"bullish": "↑ Bullish", "bearish": "↓ Bearish", "neutral": "→ Neutral"}
    c = colors.get(trend, "#6b7280")
    return _badge(labels.get(trend, trend), c)


def _rsi_badge(rsi: float, status: str) -> str:
    if status == "overbought":
        return f'<span style="color:#dc2626; font-weight:600;">{rsi:.1f} — Overbought</span>'
    elif status == "oversold":
        return f'<span style="color:#16a34a; font-weight:600;">{rsi:.1f} — Oversold</span>'
    return f"{rsi:.1f} — Neutral"


def _row(label: str, value: str) -> str:
    return f"<tr><td style='{_TD} color:#6b7280; width:140px;'>{label}</td><td style='{_TD}'>{value}</td></tr>"


def _build_ta_card(symbol: str, ta) -> str:
    """Build a technical analysis card for one symbol."""
    price = f"${ta.current_price:,.2f}"
    iv_pct = f"{ta.annualized_volatility * 100:.0f}%" if ta.annualized_volatility else "—"
    ma50 = f"${ta.ma_50:,.2f}" if ta.ma_50 else "—"
    ma200 = f"${ta.ma_200:,.2f}" if ta.ma_200 else "—"

    year_range = f"${ta.year_low:,.2f} – ${ta.year_high:,.2f}"
    support = f"${ta.nearest_support:,.2f}" if ta.nearest_support else "—"
    resistance = f"${ta.nearest_resistance:,.2f}" if ta.nearest_resistance else "—"

    week_range = (
        f"${ta.prob_68_low:,.2f} – ${ta.prob_68_high:,.2f}"
        if ta.prob_68_low else "—"
    )

    bb_labels = {
        "above_upper": "Above upper band ⚠️",
        "near_upper": "Near upper band",
        "middle": "Middle band",
        "near_lower": "Near lower band",
        "below_lower": "Below lower band ⚠️",
    }
    bb_text = bb_labels.get(ta.bb_position, ta.bb_position)

    earnings_html = ""
    if ta.earnings_date:
        color = "#dc2626" if ta.earnings_within_week else "#d97706"
        earnings_html = f'<div style="margin-top:8px; color:{color}; font-size:13px;">⚠️ Earnings: {ta.earnings_date.strftime("%b %-d")}</div>'

    return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_BLUE}">📊 Technical Analysis — {symbol} &nbsp;<span style="font-weight:400; font-size:12px; opacity:.85">as of {date.today().strftime('%b %-d')}</span></div>
  <div style="{_BODY_PAD}">
    <table style="width:100%; border-collapse:collapse;">
      {_row("Price", f"<strong>{price}</strong> &nbsp; {_trend_badge(ta.trend)}")}
      {_row("RSI (14)", _rsi_badge(ta.rsi_14, ta.rsi_status))}
      {_row("MA 50 / 200", f"{ma50} &nbsp;/&nbsp; {ma200}")}
      {_row("Bollinger Band", bb_text)}
      {_row("IV (annual)", iv_pct)}
      {_row("52-week range", year_range)}
      {_row("Support / Resistance", f"{support} &nbsp;/&nbsp; {resistance}")}
      {_row("1-week range (68%)", week_range)}
    </table>
    {earnings_html}
  </div>
</div>"""


def _build_at_risk_html(positions_with_prices: List[Dict]) -> str:
    """Build an at-risk (ITM) positions table."""
    if not positions_with_prices:
        return ""

    rows = ""
    for p in positions_with_prices:
        itm_amt = p.get("itm_amount", 0)
        color = "#dc2626" if itm_amt > 0 else "#16a34a"
        sign = "+" if itm_amt > 0 else ""
        expiry = p.get("expiry", "?")
        rows += f"""<tr>
          <td style="{_TD}">{p['account']}</td>
          <td style="{_TD_MONO}">{p['symbol']}</td>
          <td style="{_TD}">{p['option_type'].upper()}</td>
          <td style="{_TD_MONO}">${p['strike']:,.2f}</td>
          <td style="{_TD_MONO}">${p['current_price']:,.2f}</td>
          <td style="{_TD} color:{color}; font-weight:600;">{sign}${abs(itm_amt):,.2f}</td>
          <td style="{_TD}">{expiry}</td>
        </tr>"""

    return f"""
<div style="{_CARD_STYLE} border-color:#fca5a5;">
  <div style="{_HEADER_RED}">⚠️ At-Risk Positions — Loss on Assignment</div>
  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="{_TH}">Account</th>
      <th style="{_TH}">Symbol</th>
      <th style="{_TH}">Type</th>
      <th style="{_TH}">Strike</th>
      <th style="{_TH}">Price</th>
      <th style="{_TH}">ITM Amount</th>
      <th style="{_TH}">Expiry</th>
    </tr>
    {rows}
  </table>
  <div style="{_BODY_PAD} color:#6b7280; font-size:12px;">
    ITM calls: stock price &gt; strike. ITM puts: stock price &lt; strike.
    Assignment would result in a net loss on the option.
  </div>
</div>"""


def _build_positions_html(positions: List) -> str:
    """Build an open positions summary table."""
    if not positions:
        return ""

    rows = ""
    for p in positions:
        pnl = ""
        if p.gain_loss_percent is not None:
            color = "#16a34a" if p.gain_loss_percent > 0 else "#dc2626"
            sign = "+" if p.gain_loss_percent > 0 else ""
            pnl = f'<span style="color:{color}; font-weight:600;">{sign}{p.gain_loss_percent:.1f}%</span>'

        from app.modules.strategies.models import SoldOptionsSnapshot
        from sqlalchemy import inspect
        # Get account name from snapshot relationship
        account = "—"
        try:
            account = p._sa_instance_state.session.query(
                SoldOptionsSnapshot
            ).filter(SoldOptionsSnapshot.id == p.snapshot_id).first()
            account = account.account_name if account else "—"
        except Exception:
            pass

        expiry = p.expiration_date.strftime("%b %-d") if p.expiration_date else "?"
        rows += f"""<tr>
          <td style="{_TD}">{account}</td>
          <td style="{_TD_MONO}">{p.symbol}</td>
          <td style="{_TD}">{p.option_type.upper() if p.option_type else '—'}</td>
          <td style="{_TD_MONO}">${float(p.strike_price):,.2f}</td>
          <td style="{_TD}">{p.contracts_sold}x</td>
          <td style="{_TD}">{expiry}</td>
          <td style="{_TD}">{pnl or '—'}</td>
        </tr>"""

    return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_BLUE}">📋 Open Options Positions ({len(positions)} total)</div>
  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="{_TH}">Account</th>
      <th style="{_TH}">Symbol</th>
      <th style="{_TH}">Type</th>
      <th style="{_TH}">Strike</th>
      <th style="{_TH}">Qty</th>
      <th style="{_TH}">Expiry</th>
      <th style="{_TH}">P&L</th>
    </tr>
    {rows}
  </table>
</div>"""


def _build_algo_fit_html(symbol: str, ta, v5_config: Dict) -> str:
    """Build a V5 algorithm fit assessment card."""
    if not ta:
        return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_PURPLE}">🔬 Algorithm Fit — {symbol}</div>
  <div style="{_BODY_PAD} color:#6b7280;">Could not fetch market data for {symbol}.</div>
</div>"""

    iv = ta.annualized_volatility * 100 if ta.annualized_volatility else 0

    high_iv_syms = v5_config.get("life_support", {}).get("high_iv_symbols", [])
    low_iv_syms = v5_config.get("life_support", {}).get("low_iv_symbols", [])

    if symbol in high_iv_syms or iv > 40:
        iv_cat = ("High IV (>40%)", "#dc2626")
    elif symbol in low_iv_syms or iv < 20:
        iv_cat = ("Low IV (<20%)", "#d97706")
    else:
        iv_cat = ("Medium IV (20–40%)", "#2563eb")

    # Criteria checks
    checks = [
        (
            "Price sellable strikes",
            ta.current_price >= 10,
            f"${ta.current_price:,.2f} — {'above $10 ✓' if ta.current_price >= 10 else 'too low for weekly income ✗'}",
        ),
        (
            "IV category",
            iv >= 15,
            f"{iv:.0f}% annual — {iv_cat[0]}",
            iv_cat[1],
        ),
        (
            "Trend",
            ta.trend in ("bullish", "neutral"),
            f"{ta.trend.capitalize()} — {'OK for covered calls ✓' if ta.trend != 'bearish' else 'bearish trend ⚠️'}",
        ),
        (
            "RSI not overbought",
            ta.rsi_status != "overbought",
            f"RSI {ta.rsi_14:.1f} — {ta.rsi_status}",
        ),
        (
            "Earnings clear",
            not ta.earnings_within_week,
            "Earnings within 1 week ⚠️" if ta.earnings_within_week else (
                f"Next: {ta.earnings_date.strftime('%b %-d')} ✓" if ta.earnings_date else "Not detected ✓"
            ),
        ),
    ]

    rows = ""
    for check in checks:
        name, passed, note = check[0], check[1], check[2]
        override_color = check[3] if len(check) > 3 else None
        icon = "✅" if passed else "⚠️"
        color = override_color or ("#16a34a" if passed else "#d97706")
        rows += f"""<tr>
          <td style="{_TD}">{name}</td>
          <td style="{_TD}"><span style="color:{color}; font-weight:600;">{icon}</span></td>
          <td style="{_TD} color:#6b7280;">{note}</td>
        </tr>"""

    passes = sum(1 for c in checks if c[1])
    verdict_color = "#16a34a" if passes >= 4 else "#d97706" if passes >= 3 else "#dc2626"
    verdict = "Strong fit" if passes >= 4 else "Marginal fit" if passes >= 3 else "Poor fit"

    return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_PURPLE}">🔬 V5 Algorithm Fit — {symbol} &nbsp;<span style="font-weight:400; font-size:12px;">${ta.current_price:,.2f}</span></div>
  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="{_TH}">Criterion</th>
      <th style="{_TH}">Status</th>
      <th style="{_TH}">Detail</th>
    </tr>
    {rows}
  </table>
  <div style="{_BODY_PAD}">
    <strong>Verdict:</strong> &nbsp;
    <span style="color:{verdict_color}; font-weight:700;">{verdict}</span>
    &nbsp;({passes}/{len(checks)} criteria met)
  </div>
</div>"""


def _build_price_alert_confirm_html(symbol: str, condition: str, target: float, interval: int) -> str:
    """Confirmation card for a newly created price alert."""
    cond_text = f"drops below ${target:,.2f}" if condition == "below" else f"rises above ${target:,.2f}"
    return f"""
<div style="{_CARD_STYLE} border-color:#a7f3d0;">
  <div style="{_HEADER_GREEN}">✅ Price Alert Set</div>
  <div style="{_BODY_PAD}">
    <p style="margin:0 0 8px;">I'll monitor <strong>{symbol}</strong> every <strong>{interval} minutes</strong>
    during market hours and alert you if the price <strong>{cond_text}</strong>.</p>
    <p style="margin:0; color:#6b7280; font-size:13px;">Reply "cancel {symbol} alert" to stop monitoring.</p>
  </div>
</div>"""


def _analysis_section(text: str) -> str:
    """Wrap Claude's plain-text analysis in a styled section."""
    paras = [f"<p style='margin:0 0 10px;'>{p.strip()}</p>" for p in text.split("\n\n") if p.strip()]
    return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_BLUE}" >💬 Analysis &amp; Recommendations</div>
  <div style="{_BODY_PAD} line-height:1.65;">
    {''.join(paras)}
  </div>
</div>"""


def _wrap_email_html(body_inner: str, question_preview: str) -> str:
    now_str = datetime.now().strftime("%A, %B %-d · %-I:%M %p PT")
    q_preview = question_preview[:120].replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
             font-size:15px; line-height:1.6; color:#111827; max-width:680px;
             margin:0 auto; padding:24px 20px; background:#ffffff;">
  <div style="border-bottom:2px solid #2563eb; padding-bottom:10px; margin-bottom:20px;">
    <div style="font-size:17px; font-weight:700; color:#2563eb;">🏦 Agrawal Estate Planner</div>
    <div style="font-size:12px; color:#6b7280; margin-top:2px;">{now_str}</div>
  </div>
  <div style="color:#6b7280; font-size:13px; margin-bottom:18px; font-style:italic;">
    Re: "{q_preview}{'…' if len(question_preview) > 120 else ''}"
  </div>
  {body_inner}
  <div style="margin-top:24px; padding-top:14px; border-top:1px solid #e5e7eb;
              font-size:12px; color:#9ca3af;">
    Reply to continue the conversation — your estate planner assistant will respond.<br>
    — Your Estate Planner Assistant
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------

def _gather_portfolio_context(db: Session) -> Tuple[List, List, List]:
    """Returns (open_positions, recommendations, holdings)."""
    positions, recs, holdings = [], [], []

    try:
        from app.modules.strategies.models import SoldOption, SoldOptionsSnapshot
        from sqlalchemy import func

        latest = (
            db.query(func.max(SoldOptionsSnapshot.id).label("max_id"))
            .group_by(SoldOptionsSnapshot.account_name)
            .subquery()
        )
        positions = (
            db.query(SoldOption)
            .filter(
                SoldOption.status == "open",
                SoldOption.snapshot_id.in_(db.query(latest.c.max_id)),
            )
            .all()
        )
    except Exception as e:
        logger.warning(f"Could not load open positions: {e}")

    try:
        from app.modules.strategies.recommendation_models import PositionRecommendation

        recs = (
            db.query(PositionRecommendation)
            .filter(PositionRecommendation.status == "active")
            .order_by(PositionRecommendation.updated_at.desc())
            .limit(20)
            .all()
        )
    except Exception as e:
        logger.warning(f"Could not load recommendations: {e}")

    try:
        from app.modules.investments.models import InvestmentHolding

        holdings = (
            db.query(InvestmentHolding)
            .filter(InvestmentHolding.market_value.isnot(None))
            .order_by(InvestmentHolding.market_value.desc())
            .limit(30)
            .all()
        )
    except Exception as e:
        logger.warning(f"Could not load holdings: {e}")

    return positions, recs, holdings


def _find_at_risk_positions(positions: List, ta_cache: Dict) -> List[Dict]:
    """Find ITM positions where assignment would cause a loss."""
    at_risk = []
    for p in positions:
        symbol = p.symbol
        if not symbol:
            continue

        # Try to get current price from TA cache or use snapshot price
        ta = ta_cache.get(symbol)
        current_price = ta.current_price if ta else None
        if current_price is None:
            continue

        strike = float(p.strike_price) if p.strike_price else None
        if strike is None:
            continue

        opt_type = (p.option_type or "").lower()
        itm_amount = None

        if opt_type == "call" and current_price > strike:
            itm_amount = current_price - strike  # loss = stock above strike
        elif opt_type == "put" and current_price < strike:
            itm_amount = strike - current_price  # loss = stock below strike

        if itm_amount is not None and itm_amount > 0:
            # Fetch account name
            account = "—"
            try:
                from app.modules.strategies.models import SoldOptionsSnapshot
                snap = db_session.query(SoldOptionsSnapshot).filter(
                    SoldOptionsSnapshot.id == p.snapshot_id
                ).first()
                account = snap.account_name if snap else "—"
            except Exception:
                pass

            expiry = p.expiration_date.strftime("%b %-d") if p.expiration_date else "?"
            at_risk.append({
                "account": account,
                "symbol": symbol,
                "option_type": opt_type,
                "strike": strike,
                "current_price": current_price,
                "itm_amount": itm_amount,
                "expiry": expiry,
            })

    return at_risk


def _fetch_ta_for_symbols(symbols: List[str]) -> Dict:
    """Fetch technical indicators for a list of symbols."""
    try:
        from app.modules.strategies.technical_analysis import TechnicalAnalysisService
        svc = TechnicalAnalysisService()
        result = {}
        for sym in symbols:
            try:
                ta = svc.get_technical_indicators(sym)
                if ta:
                    result[sym] = ta
            except Exception as e:
                logger.warning(f"TA fetch failed for {sym}: {e}")
        return result
    except Exception as e:
        logger.warning(f"Could not initialize TechnicalAnalysisService: {e}")
        return {}


# ---------------------------------------------------------------------------
# Price alert integration
# ---------------------------------------------------------------------------

def _handle_price_alert_request(question: str) -> Optional[str]:
    """
    If the question is a price alert or cancel-alert request, act on it and
    return a confirmation HTML card. Returns None if not applicable.
    """
    try:
        from app.shared.services.price_alerts import get_price_alert_manager, AlertCondition

        mgr = get_price_alert_manager()
        q_lower = question.lower()

        # Handle cancel: "cancel Tesla alert" / "stop watching TSLA"
        if any(w in q_lower for w in ["cancel", "stop watching", "remove alert", "stop alert"]):
            symbols = _extract_symbols(question)
            if symbols:
                removed = mgr.cancel_by_symbol(symbols[0])
                if removed:
                    return (
                        f'<div style="{_CARD_STYLE} border-color:#a7f3d0;">'
                        f'<div style="{_HEADER_GREEN}">✅ Alert Cancelled</div>'
                        f'<div style="{_BODY_PAD}">Removed {removed} active alert(s) for <strong>{symbols[0]}</strong>.</div>'
                        f'</div>'
                    )

        # Handle list alerts: "what alerts do I have active?"
        if any(w in q_lower for w in ["list alerts", "active alerts", "what alerts", "my alerts"]):
            active = mgr.list_alerts()
            if not active:
                return (
                    f'<div style="{_CARD_STYLE}">'
                    f'<div style="{_HEADER_BLUE}">📋 Active Price Alerts</div>'
                    f'<div style="{_BODY_PAD} color:#6b7280;">No active price alerts.</div>'
                    f'</div>'
                )
            rows = "".join(
                f'<tr><td style="{_TD_MONO}">{a.symbol}</td>'
                f'<td style="{_TD}">{a.condition} ${a.target_price:,.2f}</td>'
                f'<td style="{_TD} color:#6b7280; font-size:13px;">{a.created_at[:10]}</td></tr>'
                for a in active
            )
            return (
                f'<div style="{_CARD_STYLE}">'
                f'<div style="{_HEADER_BLUE}">📋 Active Price Alerts ({len(active)})</div>'
                f'<table style="width:100%; border-collapse:collapse;">'
                f'<tr><th style="{_TH}">Symbol</th><th style="{_TH}">Condition</th><th style="{_TH}">Set on</th></tr>'
                f'{rows}'
                f'</table></div>'
            )

        # Handle create alert: "monitor TSLA every 10 minutes if it goes below 420"
        price_match = re.search(r"\$?([\d,]+(?:\.\d+)?)", question)
        below = any(w in q_lower for w in ["below", "drops", "falls", "under"])
        above = any(w in q_lower for w in ["above", "rises", "hits", "over"])
        interval_match = re.search(r"(\d+)\s*(?:min|minute)", q_lower)
        interval = int(interval_match.group(1)) if interval_match else 10

        symbols = _extract_symbols(question)
        if symbols and price_match and (below or above):
            symbol = symbols[0]
            target = float(price_match.group(1).replace(",", ""))
            condition = AlertCondition.BELOW if below else AlertCondition.ABOVE
            mgr.add_alert(symbol, condition, target, interval)
            return _build_price_alert_confirm_html(symbol, condition.value, target, interval)

    except Exception as e:
        logger.warning(f"Could not process price alert: {e}")

    return None


# ---------------------------------------------------------------------------
# Claude call — text interpretation only (not HTML generation)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the Agrawal Family Estate Planner assistant — a direct, expert financial advisor.

The user's portfolio data is already displayed in formatted tables above your response.
Your job is to provide a SHORT, DIRECT INTERPRETATION — insights, recommendations, or answers \
that the data tables don't already show.

Rules:
- Maximum 200 words. Be concise.
- Do NOT re-describe what the tables already show.
- Focus on: what action to take, what to watch, what the data means.
- Use plain text only — NO markdown, NO asterisks, NO bullet symbols.
- If something is at-risk, be specific about the recommended action.
- Always end with: — Your Estate Planner
"""


def _call_claude(question: str, text_context: str) -> str:
    """Call Claude for a brief text interpretation. Returns plain text."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "The assistant is not configured (missing ANTHROPIC_API_KEY)."

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = f"Question: {question}\n\nPortfolio context:\n{text_context}"

    try:
        response = client.messages.create(
            model=os.getenv("AGENT_MODEL", "claude-sonnet-4-6"),
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text if response.content else "No response generated."
    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        return f"Could not generate analysis: {e}"


def _build_text_context(
    positions: List,
    recs: List,
    holdings: List,
    ta_cache: Dict,
    db: Session,
) -> str:
    """Build a compact text summary of portfolio data for Claude's context."""
    parts = [f"Today: {date.today().strftime('%A, %B %-d, %Y')}"]

    if positions:
        pos_lines = []
        for p in positions:
            from app.modules.strategies.models import SoldOptionsSnapshot
            snap = db.query(SoldOptionsSnapshot).filter(
                SoldOptionsSnapshot.id == p.snapshot_id
            ).first()
            account = snap.account_name if snap else "?"
            expiry = p.expiration_date.strftime("%b %-d") if p.expiration_date else "?"
            pnl = f" P&L:{p.gain_loss_percent:.1f}%" if p.gain_loss_percent is not None else ""
            pos_lines.append(
                f"  {account}: {p.contracts_sold}x {p.symbol} "
                f"${float(p.strike_price):,.0f} {p.option_type} exp {expiry}{pnl}"
            )
        parts.append("OPEN POSITIONS:\n" + "\n".join(pos_lines))

    if ta_cache:
        ta_lines = []
        for sym, ta in ta_cache.items():
            ta_lines.append(
                f"  {sym}: ${ta.current_price:.2f} | trend:{ta.trend} | "
                f"RSI:{ta.rsi_14:.1f}({ta.rsi_status}) | "
                f"IV:{ta.annualized_volatility*100:.0f}% | "
                f"MA50:{ta.ma_50:.2f if ta.ma_50 else 'N/A'}"
            )
        parts.append("TECHNICAL DATA:\n" + "\n".join(ta_lines))

    if holdings:
        top = holdings[:10]
        h_lines = [
            f"  {h.symbol}: {h.quantity}sh = ${float(h.market_value):,.0f}"
            for h in top
        ]
        parts.append("TOP HOLDINGS:\n" + "\n".join(h_lines))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main email sending
# ---------------------------------------------------------------------------

def _send_reply(to: str, subject: str, html: str, plain: str):
    """Send reply via Resend."""
    import resend as _resend

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.error("RESEND_API_KEY not set — cannot send reply")
        return

    _resend.api_key = api_key
    from_addr = os.getenv("AGENT_FROM", "Neel's Estate Planner <assistant@neellab.info>").strip()
    reply_to = os.getenv("AGENT_INBOX_ADDRESS", "assistant@neellab.info").strip()
    reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"

    try:
        resp = _resend.Emails.send({
            "from": from_addr,
            "to": [to],
            "reply_to": reply_to,
            "subject": reply_subject,
            "html": html,
            "text": plain,
        })
        msg_id = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
        logger.info(f"Reply sent (id={msg_id}) to {to}")
    except Exception as e:
        logger.error(f"Failed to send reply: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def handle_inbound_email(
    from_addr: str,
    subject: str,
    body: str,
    db: Session,
):
    """Process an inbound email and send a rich HTML reply."""
    user_email = os.getenv("AGENT_USER_EMAIL", "neelkamal@gmail.com").strip().lower()
    m = re.search(r"[\w.+\-]+@[\w.\-]+", from_addr)
    sender = m.group(0).lower() if m else from_addr.lower()

    if sender != user_email:
        logger.info(f"Ignoring email from non-owner {sender}")
        return

    question = _strip_quoted_reply(body)
    if not question:
        logger.info("Inbound email had no extractable question — skipping")
        return

    logger.info(f"Email assistant: {question[:80]}…")

    try:
        # 1. Detect intents and extract symbols
        intents = _detect_intents(question)
        symbols = _extract_symbols(question)
        logger.info(f"Intents: {intents} | Symbols: {symbols}")

        # 2. Fetch portfolio data
        positions, recs, holdings = _gather_portfolio_context(db)

        # 3. Fetch TA data for mentioned symbols
        #    Also fetch TA for all open positions if at-risk detection is needed
        ta_symbols = list(symbols)
        if intents["at_risk"] and positions:
            pos_syms = list({p.symbol for p in positions if p.symbol})
            ta_symbols = list(dict.fromkeys(ta_symbols + pos_syms))[:8]

        ta_cache = _fetch_ta_for_symbols(ta_symbols) if ta_symbols else {}

        # 4. Load V5 config for algo fit
        v5_config = {}
        if intents["algo_fit"]:
            try:
                from app.modules.strategies.algorithm_config import V5_CONFIG
                v5_config = V5_CONFIG
            except Exception:
                pass

        # 5. Build HTML sections
        html_sections = []

        # -- Price alert check (handle first, may short-circuit) --
        if intents["price_alert"]:
            alert_html = _handle_price_alert_request(question)
            if alert_html:
                html_sections.append(alert_html)

        # -- Technical analysis cards --
        if symbols and (intents["technical_analysis"] or intents["algo_fit"]):
            for sym in symbols:
                ta = ta_cache.get(sym)
                if ta:
                    html_sections.append(_build_ta_card(sym, ta))

        # -- Algorithm fit cards --
        if intents["algo_fit"] and symbols:
            for sym in symbols:
                ta = ta_cache.get(sym)
                html_sections.append(_build_algo_fit_html(sym, ta, v5_config))

        # -- At-risk positions --
        if intents["at_risk"] or positions:
            # Always show at-risk table if we have TA data for the positions
            at_risk = _find_at_risk_with_db(positions, ta_cache, db)
            if at_risk:
                html_sections.append(_build_at_risk_html(at_risk))

        # -- Open positions table (when screening or asked about positions) --
        if intents["position_screening"] or intents["portfolio_summary"]:
            html_sections.append(_build_positions_html_from_db(positions, db))

        # 6. Build text context for Claude
        text_ctx = _build_text_context(positions, recs, holdings, ta_cache, db)

        # 7. Get Claude's interpretation (short text, not HTML)
        analysis_text = _call_claude(question, text_ctx)

        # 8. Add analysis section
        html_sections.append(_analysis_section(analysis_text))

        # 9. Assemble final email
        inner_html = "\n".join(html_sections) if html_sections else _analysis_section(analysis_text)
        full_html = _wrap_email_html(inner_html, question)

        _send_reply(
            to=from_addr,
            subject=subject,
            html=full_html,
            plain=f"{question}\n\n---\n\n{analysis_text}",
        )

    except Exception as e:
        logger.error(f"Email assistant error: {e}", exc_info=True)
        # Fallback plain error reply
        _send_reply(
            to=from_addr,
            subject=subject,
            html=_wrap_email_html(
                _analysis_section(f"Sorry, I ran into an error: {e}"),
                question,
            ),
            plain=f"Error: {e}\n\n— Your Estate Planner Assistant",
        )


def _find_at_risk_with_db(positions: List, ta_cache: Dict, db: Session) -> List[Dict]:
    """Find ITM positions with DB access for account names."""
    from app.modules.strategies.models import SoldOptionsSnapshot

    at_risk = []
    for p in positions:
        symbol = p.symbol
        ta = ta_cache.get(symbol)
        if not ta:
            continue

        current_price = ta.current_price
        strike = float(p.strike_price) if p.strike_price else None
        if not strike:
            continue

        opt_type = (p.option_type or "").lower()
        itm_amount = None

        if opt_type == "call" and current_price > strike:
            itm_amount = current_price - strike
        elif opt_type == "put" and current_price < strike:
            itm_amount = strike - current_price

        if itm_amount and itm_amount > 0:
            snap = db.query(SoldOptionsSnapshot).filter(
                SoldOptionsSnapshot.id == p.snapshot_id
            ).first()
            account = snap.account_name if snap else "—"
            expiry = p.expiration_date.strftime("%b %-d") if p.expiration_date else "?"
            at_risk.append({
                "account": account,
                "symbol": symbol,
                "option_type": opt_type,
                "strike": strike,
                "current_price": current_price,
                "itm_amount": itm_amount,
                "expiry": expiry,
            })

    return at_risk


def _build_positions_html_from_db(positions: List, db: Session) -> str:
    """Build positions table with DB access for account names."""
    if not positions:
        return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_BLUE}">📋 Open Options Positions</div>
  <div style="{_BODY_PAD} color:#6b7280;">No open positions found.</div>
</div>"""

    from app.modules.strategies.models import SoldOptionsSnapshot

    rows = ""
    for p in positions:
        snap = db.query(SoldOptionsSnapshot).filter(
            SoldOptionsSnapshot.id == p.snapshot_id
        ).first()
        account = snap.account_name if snap else "—"

        pnl_html = "—"
        if p.gain_loss_percent is not None:
            color = "#16a34a" if p.gain_loss_percent > 0 else "#dc2626"
            sign = "+" if p.gain_loss_percent > 0 else ""
            pnl_html = f'<span style="color:{color}; font-weight:600;">{sign}{p.gain_loss_percent:.1f}%</span>'

        expiry = p.expiration_date.strftime("%b %-d") if p.expiration_date else "?"
        rows += f"""<tr>
          <td style="{_TD}">{account}</td>
          <td style="{_TD_MONO}">{p.symbol}</td>
          <td style="{_TD}">{(p.option_type or '').upper()}</td>
          <td style="{_TD_MONO}">${float(p.strike_price):,.2f}</td>
          <td style="{_TD}">{p.contracts_sold}x</td>
          <td style="{_TD}">{expiry}</td>
          <td style="{_TD}">{pnl_html}</td>
        </tr>"""

    return f"""
<div style="{_CARD_STYLE}">
  <div style="{_HEADER_BLUE}">📋 Open Options Positions ({len(positions)} total)</div>
  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="{_TH}">Account</th>
      <th style="{_TH}">Symbol</th>
      <th style="{_TH}">Type</th>
      <th style="{_TH}">Strike</th>
      <th style="{_TH}">Qty</th>
      <th style="{_TH}">Expiry</th>
      <th style="{_TH}">P&L</th>
    </tr>
    {rows}
  </table>
</div>"""
