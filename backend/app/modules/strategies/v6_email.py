"""
HTML/plain-text email rendering for the V6 action queue.

Built 2026-07-22 to point Neel's actual email notifications at the same
engine that powers the Options Execution page. Before this, emails ran
on the older, separately-maintained v5 engine (ALGORITHM_VERSION in
.env) while the page ran on v6 — meaning every v6 improvement (real
RSI/entry-timing check, roll-streak cyclical-vs-runaway detector,
earnings badges, clearer strike/premium wording) was invisible in the
inbox. "One feed, two renderers" (the design intent documented in
OPTIONS-EXECUTION-PAGE-SPEC.md) is now actually true: build_action_queue()
is the single source for both surfaces.

Scope note: does NOT replicate v5's save_v5_to_history (V2 snapshot
tables) — nothing in the frontend reads that history, so it was dead
weight, not functionality worth preserving.
"""

from typing import Dict, List

from app.modules.strategies.v6_engine import CANONICAL_ORDER

_PRIORITY_STYLES = {
    "urgent": ("#dc2626", "#fee2e2"),
    "high":   ("#d97706", "#fef3c7"),
    "medium": ("#2563eb", "#dbeafe"),
    "low":    ("#6b7280", "#f3f4f6"),
}
_ACTION_STYLES = {
    "SELL":  ("#2563eb", "#dbeafe"),
    "ROLL":  ("#d97706", "#fef3c7"),
    "BUY":   ("#2563eb", "#dbeafe"),
    "ALERT": ("#dc2626", "#fee2e2"),
}


def _badge(text: str, fg: str, bg: str) -> str:
    return (f'<span style="display:inline-block; padding:2px 7px; border-radius:4px; '
            f'font-size:10px; font-weight:700; background:{bg}; color:{fg}; '
            f'letter-spacing:.4px;">{text}</span>')


def _context_badges(ctx: Dict) -> str:
    """Same three badges the page shows: earnings, entry-timing wait,
    roll-streak trend — so the email carries the same signal, not a
    stripped-down summary."""
    parts = []
    er = ctx.get("next_earnings")
    if er and er.get("date"):
        parts.append(
            '<span style="font-size:10px; color:#92400e; background:#fef3c7; '
            f'padding:1px 6px; border-radius:8px; margin-left:4px;">📅 ER {er["date"][5:]}</span>')
    et = ctx.get("entry_timing")
    if et and et.get("wait"):
        rsi_txt = f' (RSI {round(et["rsi"])})' if et.get("rsi") is not None else ""
        parts.append(
            '<span style="font-size:10px; color:#dc2626; background:#fee2e2; '
            f'padding:1px 6px; border-radius:8px; margin-left:4px;">⏸ WAIT{rsi_txt}</span>')
    rs = ctx.get("roll_streak")
    if rs and rs.get("weeks_rolled", 0) >= 2:
        worsening = rs.get("trend") == "worsening"
        icon, color, bg = ("⚠", "#dc2626", "#fee2e2") if worsening else ("↻", "#6b7280", "#f3f4f6")
        parts.append(
            f'<span style="font-size:10px; color:{color}; background:{bg}; '
            f'padding:1px 6px; border-radius:8px; margin-left:4px;">{icon} {rs["weeks_rolled"]}wk</span>')
    return "".join(parts)


def _display_action(item: Dict) -> str:
    """SELL reads as HOLD (yellow) when the real entry-timing check says
    wait — a green SELL badge next to a red WAIT flag read as
    contradictory (Neel, 2026-07-22). Mirrors the same override in
    OptionsExecution.tsx (displayAction) so page and email agree."""
    ctx = item.get("context") or {}
    if item.get("action") == "SELL" and (ctx.get("entry_timing") or {}).get("wait"):
        return "HOLD"
    return item.get("action", "")


def _item_row(item: Dict) -> str:
    action = _display_action(item)
    afg, abg = ("#a16207", "#fef9c3") if action == "HOLD" else _ACTION_STYLES.get(action, ("#6b7280", "#f3f4f6"))
    priority = item.get("priority", "low")
    pfg, pbg = _PRIORITY_STYLES.get(priority, _PRIORITY_STYLES["low"])
    ctx = item.get("context") or {}
    earn = item.get("earn")
    earn_html = (f'&nbsp; <span style="color:#16a34a; font-weight:600;">Earn ~${earn:,.0f}</span>'
                 if earn else "")
    return (
        "<tr>"
        f'<td style="padding:6px 8px; border-bottom:1px solid #f1f5f9; white-space:nowrap;">{_badge(priority.upper(), pfg, pbg)}</td>'
        f'<td style="padding:6px 8px; border-bottom:1px solid #f1f5f9; white-space:nowrap;">{_badge(action, afg, abg)}</td>'
        f'<td style="padding:6px 8px; border-bottom:1px solid #f1f5f9; font-family:monospace; '
        f'font-weight:700; white-space:nowrap;">{item.get("symbol", "")}</td>'
        f'<td style="padding:6px 8px; border-bottom:1px solid #f1f5f9; font-size:13px; color:#111827;">'
        f'{item.get("detail", "")}{_context_badges(ctx)}{earn_html}</td>'
        "</tr>"
    )


def format_html_email(queue: Dict, scan_label: str = "") -> str:
    items = queue.get("items", [])
    if not items:
        return "<p style='color:#6b7280;'>No recommendations at this time.</p>"

    by_account: Dict[str, List[Dict]] = {}
    for i in items:
        by_account.setdefault(i["account"], []).append(i)

    summary = queue.get("summary", {})
    urgent, high = summary.get("urgent", 0), summary.get("high", 0)

    header = (
        '<div style="margin-bottom:14px; font-size:14px; color:#374151;">'
        f'<strong>{len(items)} recommendations</strong> across {len(by_account)} accounts'
        + (f' &nbsp; <span style="color:#dc2626; font-weight:700;">{urgent} URGENT</span>' if urgent else "")
        + (f' &nbsp; <span style="color:#d97706; font-weight:700;">{high} HIGH</span>' if high else "")
        + f'<br><span style="color:#6b7280; font-size:12px;">{scan_label} · V6.1</span>'
        "</div>"
    )

    sections = []
    for acct in CANONICAL_ORDER:
        rows = by_account.get(acct)
        if not rows:
            continue
        rows_html = "".join(_item_row(i) for i in rows)
        sections.append(
            '<div style="margin-bottom:18px;">'
            f'<div style="background:#1e293b; color:#fff; padding:8px 12px; font-weight:700; '
            f'font-size:13px;">{acct} — {len(rows)} recs</div>'
            f'<table style="width:100%; border-collapse:collapse;">{rows_html}</table>'
            "</div>"
        )
    return header + "".join(sections)


def format_plain_text(queue: Dict, scan_label: str = "") -> str:
    items = queue.get("items", [])
    if not items:
        return "No recommendations at this time."

    by_account: Dict[str, List[Dict]] = {}
    for i in items:
        by_account.setdefault(i["account"], []).append(i)

    lines = [f"{scan_label} — {len(items)} recommendations\n"]
    for acct in CANONICAL_ORDER:
        rows = by_account.get(acct)
        if not rows:
            continue
        lines.append(f"\n{acct}:")
        for i in rows:
            lines.append(f"  [{i.get('priority', 'low').upper()}] [{i['action']}] {i['symbol']}: {i['detail']}")
    return "\n".join(lines)
