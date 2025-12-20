#!/usr/bin/env python3
"""
Direct fetch of AVGO options using yfinance (bypasses cache issues).
"""

import yfinance as yf
from datetime import datetime, date
import pandas as pd
import time

symbol = "AVGO"

print(f"\n{'='*80}")
print(f"AVGO DIRECT OPTION FETCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*80}\n")

# Get ticker
print("1. Fetching ticker info...")
ticker = yf.Ticker(symbol)
info = ticker.info
current_price = info.get('currentPrice') or info.get('regularMarketPrice')
print(f"✅ Current Price: ${current_price:.2f}\n")

# Get expirations
print("2. Fetching option expirations...")
time.sleep(1)
try:
    expirations = list(ticker.options)
    print(f"✅ Found {len(expirations)} expirations")
    
    # Filter for 1-4 weeks
    today = date.today()
    target_exps = []
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days = (exp_date - today).days
            if 1 <= days <= 28:
                target_exps.append((exp_str, days))
        except:
            pass
    
    target_exps.sort(key=lambda x: x[1])
    print(f"✅ Found {len(target_exps)} expirations in 1-4 week range:\n")
    for exp_str, days in target_exps[:5]:
        print(f"   - {exp_str} ({days} days)")
    
    # Analyze first 3 expirations
    print(f"\n{'='*80}")
    print("3. OPTION CHAIN ANALYSIS")
    print(f"{'='*80}\n")
    
    for exp_str, days in target_exps[:3]:
        print(f"\n📅 Expiration: {exp_str} ({days} days)")
        print("-" * 80)
        
        time.sleep(2)  # Rate limiting protection
        try:
            chain = ticker.option_chain(exp_str)
            calls = chain.calls
            puts = chain.puts
            
            # Filter strikes around current price
            strikes_to_check = [340, 350, 355, 360, 365, 370, 375]
            strikes_to_check = [s for s in strikes_to_check if 300 <= s <= 400]
            
            print(f"\n   💰 CALL OPTIONS:")
            print(f"   {'Strike':<8} {'Bid':<8} {'Ask':<8} {'Mid':<8} {'IV':<8} {'Break-Even':<12}")
            print(f"   {'-'*60}")
            
            for strike in strikes_to_check:
                call = calls[abs(calls['strike'] - strike) < 1]
                if not call.empty:
                    row = call.iloc[0]
                    bid = float(row['bid']) if pd.notna(row['bid']) else 0
                    ask = float(row['ask']) if pd.notna(row['ask']) else 0
                    mid = (bid + ask) / 2 if (bid > 0 or ask > 0) else ask if ask > 0 else bid
                    iv = float(row['impliedVolatility']) * 100 if pd.notna(row['impliedVolatility']) else 0
                    breakeven = strike + mid if mid > 0 else 0
                    
                    if mid > 0:
                        print(f"   ${strike:<7.0f} ${bid:<7.2f} ${ask:<7.2f} ${mid:<7.2f} {iv:<7.1f}% ${breakeven:<11.2f}")
            
            print(f"\n   💰 PUT OPTIONS (SELLING):")
            print(f"   {'Strike':<8} {'Bid':<8} {'Ask':<8} {'Mid':<8} {'IV':<8} {'Premium':<10}")
            print(f"   {'-'*60}")
            
            for strike in strikes_to_check:
                if strike < current_price:  # Only show puts below current price for selling
                    put = puts[abs(puts['strike'] - strike) < 1]
                    if not put.empty:
                        row = put.iloc[0]
                        bid = float(row['bid']) if pd.notna(row['bid']) else 0
                        ask = float(row['ask']) if pd.notna(row['ask']) else 0
                        mid = (bid + ask) / 2 if (bid > 0 or ask > 0) else ask if ask > 0 else bid
                        iv = float(row['impliedVolatility']) * 100 if pd.notna(row['impliedVolatility']) else 0
                        premium = mid * 100
                        
                        if mid > 0:
                            print(f"   ${strike:<7.0f} ${bid:<7.2f} ${ask:<7.2f} ${mid:<7.2f} {iv:<7.1f}% ${premium:<9.2f}")
        
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
            continue
    
    print(f"\n{'='*80}\n")
    
except Exception as e:
    print(f"❌ Error fetching expirations: {e}")
    import traceback
    traceback.print_exc()


