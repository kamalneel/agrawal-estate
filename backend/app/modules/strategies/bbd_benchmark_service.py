"""
BBD Benchmark — the taxable brokerages against a buy-and-hold twin.

docs/BBD-BENCHMARK-SPEC.md. Question (Neel, 2026-09-27): is all the option
selling producing better returns than just buying QQQ and holding it?

A twin portfolio starts with the accounts' combined net liquidation value on
the first month-end both accounts have a statement, buys the index ETF with
it, and then receives every external cash flow the real accounts had, on the
same day, at that day's close. Two twins: one sells shares to fund
withdrawals (a passive investor), one borrows on margin like the real
accounts do. Everything else the strategy does — premium, dividends,
interest, margin cost, stock picking — stays inside the real value.
Pre-tax; QQQ dividends not modelled (spec, "left out of v1").
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.strategies.bbd_performance_service import BbdPerformanceService


def _month_end(year: int, month: int) -> date:
    return (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1))


class _Prices:
    def __init__(self, db: Session, symbol: str):
        rows = db.execute(text(
            "SELECT price_date, close_price FROM symbol_price_history WHERE symbol = :s ORDER BY price_date"
        ), {"s": symbol}).fetchall()
        self.dates = [r.price_date for r in rows]
        self.closes = [float(r.close_price) for r in rows]

    def on(self, d: date) -> Optional[float]:
        """Last close on or before d."""
        lo, hi = 0, len(self.dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.dates[mid] <= d:
                lo = mid + 1
            else:
                hi = mid
        return self.closes[lo - 1] if lo > 0 else None

    @property
    def last_date(self) -> Optional[date]:
        return self.dates[-1] if self.dates else None


def get_benchmark(db: Session, symbol: str = "QQQ") -> Dict[str, Any]:
    svc = BbdPerformanceService(db)
    prices = _Prices(db, symbol)
    if not prices.dates:
        return {"error": f"no price history for {symbol}; run the refresh or backfill symbol_price_history"}

    # ── Real accounts: month-end net liquidation value, both brokerages ──
    account_months = {
        k: v for k, v in svc._get_account_month_values().items()
        if any(k.startswith(a) for a in svc.BROKERAGE_ACCOUNTS)
    }
    months = sorted(m for m in set().union(*[set(v) for v in account_months.values()])
                    if all(m in v for v in account_months.values()))
    if len(months) < 2:
        return {"error": "need at least two month-ends with both brokerage accounts"}

    actual_by_month = {m: sum(v[m] for v in account_months.values()) for m in months}
    start_month, end_month = months[0], months[-1]
    start_date = _month_end(int(start_month[:4]), int(start_month[5:7]))
    today = date.today()
    # The last month is in progress: its "actual" is the latest snapshot; date it at the latest price we have.
    end_date = min(prices.last_date or today, today)
    if end_month != f"{end_date.year}-{end_date.month:02d}":
        end_date = _month_end(int(end_month[:4]), int(end_month[5:7]))

    start_value = actual_by_month[start_month]
    start_price = prices.on(start_date)
    if not start_price:
        return {"error": f"no {symbol} price on or before {start_date}"}

    # ── External cash flows after the start, paired accounts only ──
    flows = [f for f in svc._get_external_cash_flows_for_period(start_date + timedelta(days=1), end_date)
             if f["account_id"] in svc.BROKERAGE_ACCOUNTS]
    flows.sort(key=lambda f: f["date"])

    # ── Replay the twins month by month ──
    monthly_rate = float(svc.ASSUMED_ANNUAL_MARGIN_RATE) / 12
    shares_sell = start_value / start_price
    shares_borrow = start_value / start_price
    loan = 0.0
    series: List[Dict[str, Any]] = [{
        "date": start_date.isoformat(), "label": start_date.strftime("%b %Y"),
        "actual": round(start_value, 2), "twin_sell": round(start_value, 2), "twin_borrow": round(start_value, 2),
        "twin_loan": 0.0, "price": start_price, "flows": 0.0,
    }]
    fi = 0
    for m in months[1:]:
        m_end = _month_end(int(m[:4]), int(m[5:7]))
        if m == end_month:
            m_end = end_date
        month_flows = 0.0
        while fi < len(flows) and flows[fi]["date"] <= m_end:
            f = flows[fi]
            p = prices.on(f["date"]) or start_price
            amt = f["amount"]
            month_flows += amt
            shares_sell += amt / p                      # deposit buys, withdrawal sells
            if amt >= 0:
                shares_borrow += amt / p                # deposits buy shares in both twins
            else:
                loan += -amt                            # withdrawals are borrowed, not sold
            fi += 1
        loan *= (1 + monthly_rate)
        p_end = prices.on(m_end) or start_price
        series.append({
            "date": m_end.isoformat(), "label": m_end.strftime("%b %Y"),
            "actual": round(actual_by_month[m], 2),
            "twin_sell": round(shares_sell * p_end, 2),
            "twin_borrow": round(shares_borrow * p_end - loan, 2),
            "twin_loan": round(loan, 2), "price": p_end, "flows": round(month_flows, 2),
        })

    final = series[-1]
    total_flows = sum(f["amount"] for f in flows)

    # ── Per-year: real TWR (page metric) vs index price return over the same month-ends ──
    growth_rows = {m["period_label"]: m for m in svc.get_metrics("portfolio_growth", "year")}
    pure_rows = {m["period_label"]: m for m in svc.get_metrics("pure_growth", "year")}
    income_rows = {m["period_label"]: m for m in svc.get_metrics("options_yield", "year")}
    years: List[Dict[str, Any]] = []
    for yr in sorted({m[:4] for m in months}):
        yms = [m for m in months if m.startswith(yr)]
        if len(yms) < 2:
            continue
        base_m, last_m = yms[0], yms[-1]
        base_d = _month_end(int(base_m[:4]), int(base_m[5:7]))
        last_d = end_date if last_m == end_month else _month_end(int(last_m[:4]), int(last_m[5:7]))
        p0, p1 = prices.on(base_d), prices.on(last_d)
        pt_sell = next((s for s in series if s["date"] == last_d.isoformat()), None)
        g, pu, inc = growth_rows.get(yr), pure_rows.get(yr), income_rows.get(yr)
        years.append({
            "year": yr, "from": base_d.isoformat(), "to": last_d.isoformat(),
            "actual_twr_pct": g and g.get("actual_percent"),
            "index_twr_pct": round((p1 / p0 - 1) * 100, 2) if p0 and p1 else None,
            "growth_pct": pu and pu.get("actual_percent"),
            "income_pct": inc and inc.get("actual_percent"),
            "actual_end": round(actual_by_month[last_m], 2),
            "twin_sell_end": pt_sell and pt_sell["twin_sell"],
            "twin_borrow_end": pt_sell and pt_sell["twin_borrow"],
        })

    return {
        "symbol": symbol,
        "accounts": list(svc.BROKERAGE_ACCOUNTS),
        "start": {"date": start_date.isoformat(), "value": round(start_value, 2), "price": start_price},
        "end": {"date": end_date.isoformat(), "actual": final["actual"],
                "twin_sell": final["twin_sell"], "twin_borrow": final["twin_borrow"],
                "twin_loan": final["twin_loan"], "price": final["price"]},
        "gap_vs_sell": round(final["actual"] - final["twin_sell"], 2),
        "gap_vs_sell_pct_of_start": round((final["actual"] - final["twin_sell"]) / start_value * 100, 2),
        "gap_vs_borrow": round(final["actual"] - final["twin_borrow"], 2),
        "gap_vs_borrow_pct_of_start": round((final["actual"] - final["twin_borrow"]) / start_value * 100, 2),
        "index_return_pct": round((final["price"] / start_price - 1) * 100, 2),
        "flows": {"count": len(flows), "net": round(total_flows, 2),
                  "deposits": round(sum(f["amount"] for f in flows if f["amount"] > 0), 2),
                  "withdrawals": round(sum(f["amount"] for f in flows if f["amount"] < 0), 2)},
        "series": series,
        "years": years,
        "assumptions": {
            "margin_rate_pct": float(svc.ASSUMED_ANNUAL_MARGIN_RATE) * 100,
            "pre_tax": True, "index_dividends": "excluded",
            "price_source": "symbol_price_history (Robinhood MCP daily closes)",
            "note": "Twin-sell funds withdrawals by selling shares; twin-borrow borrows them at the margin rate, compounding monthly.",
        },
    }
