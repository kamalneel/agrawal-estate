#!/usr/bin/env python3
"""
Test script to verify pending orders are properly skipped during parsing.
"""

import sys
sys.path.insert(0, '/Users/neelpersonal/agrawal-estate-planner/backend')

from app.ingestion.robinhood_unified_parser import parse_robinhood_data, parse_options_list_view

# User's test data with both pending orders and positions held
test_data = """
Options
Pending Orders
AVGO $315 Put
12/19 • 1 buy to close
$0.30 Limit
COIN $267.5 Call
12/19 • 2 buys to close
$0.03 Limit
IBIT $52 Call
12/19 • 2 buys to close
$0.02 Limit
Positions Held
AVGO $315 Put
12/19 • 1 sell
+$198.00
+87.22%
COIN $267.5 Call
12/19 • 2 sells
+$122.00
+96.83%
IBIT $52 Call
12/19 • 2 sells
+$28.00
+82.35%
NVDA $180 Call
12/19 • 6 sells
+$78.00
+65.00%
TSLA $490 Call
12/19 • 7 sells
-$1,098.02
-133.91%
AVGO $305 Put
12/26 • 1 sell
+$154.00
+58.56%
AVGO $360 Put
1/9/2026 • 2 sells
+$684.00
+9.12%
CRCL $90 Call
1/9/2026 • 2 sells
+$786.00
+60.28%
"""

def test_parsing():
    print("=" * 60)
    print("Testing Robinhood data parsing with pending orders")
    print("=" * 60)
    
    result = parse_robinhood_data(test_data)
    
    print(f"\nDetected format: {result.detected_format}")
    print(f"Has options section: {result.has_options_section}")
    print(f"Warnings: {result.warnings}")
    
    print(f"\n📊 Parsed {len(result.options)} options:")
    print("-" * 60)
    
    # Define expected positions (from Positions Held section only)
    expected_positions = [
        ("AVGO", 315, "put", "12/19", 1),
        ("COIN", 267.5, "call", "12/19", 2),
        ("IBIT", 52, "call", "12/19", 2),
        ("NVDA", 180, "call", "12/19", 6),
        ("TSLA", 490, "call", "12/19", 7),
        ("AVGO", 305, "put", "12/26", 1),
        ("AVGO", 360, "put", "1/9/2026", 2),
        ("CRCL", 90, "call", "1/9/2026", 2),
    ]
    
    for opt in result.options:
        print(f"  {opt.symbol} ${opt.strike_price} {opt.option_type}")
        print(f"    Expiration: {opt.expiration_date}")
        print(f"    Contracts: {opt.contracts}")
        print(f"    Current Premium: ${opt.current_premium:.4f}" if opt.current_premium else "    Current Premium: None")
        print(f"    Original Premium: ${opt.original_premium:.4f}" if opt.original_premium else "    Original Premium: None")
        print(f"    Gain/Loss: {opt.gain_loss_percent}%")
        print()
    
    # Verify we got the expected number of positions
    print("=" * 60)
    print("Verification")
    print("=" * 60)
    
    if len(result.options) == len(expected_positions):
        print(f"✅ Correct number of positions: {len(result.options)}")
    else:
        print(f"❌ Expected {len(expected_positions)} positions, got {len(result.options)}")
    
    # Check that no pending orders were included
    pending_symbols_strikes = [
        ("AVGO", 315, "put", "buy"),  # Pending: AVGO $315 Put buy to close
        ("COIN", 267.5, "call", "buy"),  # Pending: COIN $267.5 Call buy to close  
        ("IBIT", 52, "call", "buy"),  # Pending: IBIT $52 Call buy to close
    ]
    
    # These should NOT appear as duplicate entries
    # The positions held for same strikes should appear once
    
    symbol_counts = {}
    for opt in result.options:
        key = (opt.symbol, opt.strike_price, opt.option_type)
        symbol_counts[key] = symbol_counts.get(key, 0) + 1
    
    # Check for duplicates
    duplicates_found = False
    for key, count in symbol_counts.items():
        if count > 1:
            print(f"❌ Found duplicate: {key} appears {count} times")
            duplicates_found = True
    
    if not duplicates_found:
        print("✅ No duplicate entries found")
    
    # Verify each expected position is present
    all_present = True
    for sym, strike, opt_type, exp, contracts in expected_positions:
        found = any(
            opt.symbol == sym and 
            opt.strike_price == strike and 
            opt.option_type == opt_type and
            opt.contracts == contracts
            for opt in result.options
        )
        if not found:
            print(f"❌ Missing expected position: {sym} ${strike} {opt_type} (exp {exp}, {contracts} contracts)")
            all_present = False
    
    if all_present:
        print("✅ All expected positions found")
    
    print("\n" + "=" * 60)
    if len(result.options) == len(expected_positions) and not duplicates_found and all_present:
        print("✅ ALL TESTS PASSED - Pending orders correctly skipped!")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)

if __name__ == "__main__":
    test_parsing()

