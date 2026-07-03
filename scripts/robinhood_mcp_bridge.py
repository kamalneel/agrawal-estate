#!/usr/bin/env python3
"""
Robinhood MCP → Estate Planner ingestion bridge.

Takes a JSON bundle of raw Robinhood MCP tool outputs (positions, portfolio,
orders, quotes) and feeds them through the app's EXISTING authoritative
ingestion paths — no direct DB writes:

  1. Holdings + options  → POST /ingestion/robinhood-paste/preview + /save
     (synthesizes the same text the Robinhood app copy-paste produces)
  2. Cash breakdown      → POST /ingestion/robinhood-cash/preview + /save
  3. Filled orders       → Robinhood-format activity CSV dropped in
     data/inbox/investments/robinhood/ + POST /ingestion/scan

The bundle is produced by a Claude Code session connected to the
robinhood-trading MCP server (see docs/ROBINHOOD_MCP_SYNC.md for the
tool-call recipe). This script is deterministic: all transformation logic
lives here, not in the LLM session.

Usage:
    python3 scripts/robinhood_mcp_bridge.py bundle.json            # preview only
    python3 scripts/robinhood_mcp_bridge.py bundle.json --save     # preview + save
    python3 scripts/robinhood_mcp_bridge.py bundle.json --save --api http://localhost:8000/api/v1

Known gaps vs the manual sources (still need monthly statement / activity CSV):
  - Dividends and interest (no MCP tool exposes them)
  - Option expirations & assignments (not orders, so not in order history)
  - Do NOT also import Robinhood's official activity CSV for a period synced
    here: synthesized Amounts are gross (no reg fees), so rows would not
    dedup against the official CSV's net amounts.
"""

import argparse
import csv
import io
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

DEFAULT_API = "http://localhost:8000/api/v1"
INBOX = Path(__file__).resolve().parent.parent / "data" / "inbox" / "investments" / "robinhood"

CSV_COLUMNS = ["Activity Date", "Process Date", "Settle Date", "Instrument",
               "Description", "Trans Code", "Quantity", "Price", "Amount"]

TRANS_CODE = {("sell", "open"): "STO", ("buy", "close"): "BTC",
              ("sell", "close"): "STC", ("buy", "open"): "BTO"}


# ---------------------------------------------------------------- formatting

def money(v: float) -> str:
    return f"${v:,.2f}"


def fmt_strike(v: float) -> str:
    # paste format shows strikes as-is; the parser accepts either
    return f"{v:g}" if float(v) == int(float(v)) else f"{v:.2f}"


def fmt_strike_csv(v: float) -> str:
    # activity CSV descriptions must match Robinhood's official format
    # exactly ("$215.00", two decimals) so fee-tolerant dedup can pair rows
    return f"{v:.2f}"


def fmt_shares(v: float) -> str:
    return f"{int(v):,}" if float(v) == int(float(v)) else f"{v:,g}"


def fmt_exp(iso_date: str) -> str:
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{d.month}/{d.day}/{d.year}"


# ---------------------------------------------------------- artifact builders

def build_paste_text(account: dict, instruments: dict, option_marks: dict,
                     equity_marks: dict) -> tuple[str, int, int]:
    """Synthesize the Robinhood app copy-paste (mixed format) for one account.

    Returns (text, expected_option_count, expected_stock_count).
    """
    lines = ["Options", "Positions Held"]
    n_options = 0
    for pos in account.get("option_positions", []):
        if pos.get("type") != "short":
            print(f"  ! skipping non-short option {pos.get('chain_symbol')} "
                  f"(app tracks sold options only)")
            continue
        inst = instruments[pos["option_id"]]
        original = abs(float(pos["average_price"])) / 100.0
        current = max(round(float(option_marks[pos["option_id"]]), 2), 0.01)
        # gain% chosen so the parser's original = current / (1 - g/100)
        # reconstructs the exact average credit from the broker
        gain = (1 - current / original) * 100.0
        qty = int(float(pos["quantity"]))
        lines += [
            f"{inst['chain_symbol']} ${fmt_strike(float(inst['strike_price']))} "
            f"{inst['type'].capitalize()}",
            f"{fmt_exp(inst['expiration_date'])} · {qty} sells",
            f"${current:.2f}",
            f"{gain:+.4f}%",
        ]
        n_options += 1

    lines.append("Stocks")
    n_stocks = 0
    for pos in account.get("equity_positions", []):
        price = float(equity_marks[pos["symbol"]])
        lines += [pos["symbol"], f"{fmt_shares(float(pos['quantity']))} Shares",
                  f"${price:,.2f}"]
        n_stocks += 1

    return "\n".join(lines), n_options, n_stocks


def build_cash_text(account: dict, instruments: dict) -> str:
    """Synthesize the Robinhood cash-section paste for one account."""
    p = account["portfolio"]
    cash = float(p["cash"])
    buying_power = float(p["buying_power"]["buying_power"])
    fmt = account["cash_format"]

    if fmt == "brokerage":
        free_cash, margin_used = (cash, 0.0) if cash >= 0 else (0.0, -cash)
        # cash-secured short puts; covered calls reserve shares, not cash
        collateral = sum(
            float(instruments[o["option_id"]]["strike_price"]) * 100
            * float(o["quantity"])
            for o in account.get("option_positions", [])
            if o.get("type") == "short"
            and instruments[o["option_id"]]["type"] == "put")
        return "\n".join([
            "Cash", money(free_cash),
            "Margin used", f"-{money(margin_used)}",
            "Options collateral", f"-{money(collateral)}",
            "Total", money(buying_power),
        ])

    label = "Roth IRA cash" if fmt == "roth_ira" else "Traditional IRA cash"
    collateral = max(cash - buying_power, 0.0)
    return "\n".join([
        label, money(cash),
        "Options collateral", f"-{money(collateral)}",
        "Buying power", money(buying_power),
    ])


def build_activity_csv(account: dict) -> tuple[str, int]:
    """Robinhood-format activity CSV from filled MCP orders (one row per fill).

    Only fills with trade_date >= account.activity_since are included, so a
    period already covered by an imported official activity CSV is never
    re-imported (synthesized amounts are gross of fees and would NOT dedup
    against the official CSV's net amounts).
    """
    since = account.get("activity_since", "1900-01-01")
    rows = []
    for order in account.get("option_orders", []):
        if order.get("state") != "filled":
            continue
        for leg in order.get("legs", []):
            code = TRANS_CODE[(leg["side"], leg["position_effect"])]
            desc = (f"{order['chain_symbol']} {fmt_exp(leg['expiration_date'])} "
                    f"{leg['option_type'].capitalize()} "
                    f"${fmt_strike_csv(float(leg['strike_price']))}")
            for ex in leg.get("executions", []):
                if ex["trade_date"] < since:
                    continue
                qty = float(ex["quantity"])
                price = float(ex["price"])
                total = qty * price * 100
                credit = code in ("STO", "STC")
                rows.append({
                    "Activity Date": fmt_exp(ex["trade_date"]),
                    "Process Date": fmt_exp(ex["trade_date"]),
                    "Settle Date": fmt_exp(ex["settlement_date"]),
                    "Instrument": order["chain_symbol"],
                    "Description": desc,
                    "Trans Code": code,
                    "Quantity": f"{qty:g}",
                    "Price": money(price),
                    "Amount": money(total) if credit else f"({money(total)})",
                })
    for order in account.get("equity_orders", []):
        if order.get("state") != "filled":
            continue
        code = order["side"].upper()  # BUY / SELL
        for ex in order.get("executions", []):
            # equity executions carry a timestamp, not trade/settle dates
            trade_date = ex.get("trade_date") or ex["timestamp"][:10]
            if trade_date < since:
                continue
            qty = float(ex["quantity"])
            price = float(ex["price"])
            total = qty * price
            rows.append({
                "Activity Date": fmt_exp(trade_date),
                "Process Date": fmt_exp(trade_date),
                "Settle Date": fmt_exp(ex.get("settlement_date") or trade_date),
                "Instrument": order["symbol"],
                "Description": order["symbol"],
                "Trans Code": code,
                "Quantity": f"{qty:g}",
                "Price": money(price),
                "Amount": money(total) if code == "SELL" else f"({money(total)})",
            })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue(), len(rows)


def csv_filename(account_name: str, as_of: str) -> str:
    # Must satisfy the CSV parser's filename→account inference patterns,
    # e.g. "Jaya Investment ..." → jaya_brokerage, "Jaya Roth IRA ..." → jaya_roth_ira
    base = account_name.replace("'s", "").replace("Brokerage", "Investment")
    return f"{base} MCP Activity {as_of}.csv"


# ------------------------------------------------------------------ API calls

def post(api: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{api}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ERROR {path}: {e.code} {e.read().decode()[:500]}")


# ----------------------------------------------------------------------- main

def sync_account(api: str, account: dict, bundle: dict, save: bool) -> None:
    name = account["account_name"]
    instruments = bundle["instruments"]
    print(f"\n=== {name} ===")

    # --- 1. holdings + options paste ---
    text, n_opt, n_stk = build_paste_text(
        account, instruments, bundle["option_marks"], bundle["equity_marks"])
    preview = post(api, "/ingestion/robinhood-paste/preview",
                   {"text": text, "account_name": name})
    print(f"  paste preview: format={preview['detected_format']} "
          f"stocks={preview['stocks_count']}/{n_stk} "
          f"options={preview['options_count']}/{n_opt}")
    if preview["stocks_count"] != n_stk or preview["options_count"] != n_opt:
        raise SystemExit("  parse-count mismatch — paste format drifted, aborting")
    # guard: parser must reconstruct the broker's exact average credit
    expected = {}
    for pos in account.get("option_positions", []):
        if pos.get("type") != "short":
            continue
        inst = instruments[pos["option_id"]]
        key = (inst["chain_symbol"], float(inst["strike_price"]), inst["type"])
        expected[key] = abs(float(pos["average_price"])) / 100.0
    for opt in preview["options"]:
        key = (opt["symbol"], float(opt["strike_price"]), opt["option_type"])
        want = expected.get(key)
        got = opt.get("original_premium")
        if want and got and abs(got - want) / want > 0.005:
            raise SystemExit(f"  original premium drift {key}: {got} vs {want}")
    if save:
        # confirm_empty_sections is safe here: the count guard above already
        # aborts if a section unexpectedly parsed empty, so a 0-count section
        # reaching this point is a genuine empty (e.g. an account with no
        # open options), not an accidental clear.
        result = post(api, "/ingestion/robinhood-paste/save",
                      {"text": text, "account_name": name, "confirm_empty_sections": True})
        print(f"  paste saved: {json.dumps({k: v for k, v in result.items() if isinstance(v, (int, str, bool))})}")

    # --- 2. cash breakdown ---
    cash_text = build_cash_text(account, instruments)
    cash_prev = post(api, "/ingestion/robinhood-cash/preview",
                     {"text": cash_text, "account_name": name})
    print(f"  cash preview: format={cash_prev['format']} "
          f"cash={cash_prev['cash']} collateral={cash_prev['options_collateral']} "
          f"true_cash={cash_prev['true_cash']}")
    if save:
        post(api, "/ingestion/robinhood-cash/save",
             {"text": cash_text, "account_name": name})
        print("  cash saved")

    # --- 3. activity CSV ---
    csv_text, n_rows = build_activity_csv(account)
    fname = csv_filename(name, bundle["as_of"])
    print(f"  activity: {n_rows} fills → {fname}")
    if save and n_rows:
        INBOX.mkdir(parents=True, exist_ok=True)
        (INBOX / fname).write_text(csv_text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--save", action="store_true",
                    help="actually save (default: preview only)")
    ap.add_argument("--api", default=DEFAULT_API)
    args = ap.parse_args()

    bundle = json.loads(args.bundle.read_text())
    for account in bundle["accounts"]:
        sync_account(args.api, account, bundle, args.save)

    if args.save:
        scan = post(args.api, "/ingestion/scan", {})
        print(f"\ninbox scan: found={scan.get('files_found')} "
              f"processed={scan.get('files_processed')} "
              f"failed={scan.get('files_failed')}")
    print("\ndone" + ("" if args.save else " (preview only — rerun with --save)"))


if __name__ == "__main__":
    main()
