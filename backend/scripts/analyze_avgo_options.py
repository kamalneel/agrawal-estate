#!/usr/bin/env python3
"""
Analyze AVGO options after earnings drop to provide specific recommendations.
"""

import sys
import os
from datetime import date, datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.modules.strategies.yahoo_cache import (
    get_ticker_info,
    get_option_expirations,
    get_option_chain
)
from app.modules.strategies.option_monitor import OptionChainFetcher
import pandas as pd

def analyze_avgo_options():
    """Fetch and analyze AVGO option chain for recommendations."""
    
    symbol = "AVGO"
    
    print(f"\n{'='*80}")
    print(f"AVGO OPTIONS ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    # 1. Get current stock price
    print("1. Fetching current stock price...")
    ticker_info = get_ticker_info(symbol)
    if not ticker_info:
        print(f"❌ Failed to fetch stock info for {symbol}")
        return
    
    current_price = ticker_info.get('currentPrice') or ticker_info.get('regularMarketPrice')
    previous_close = ticker_info.get('previousClose')
    
    if not current_price:
        print(f"❌ Could not determine current price")
        return
    
    change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close else 0
    
    print(f"✅ Current Price: ${current_price:.2f}")
    print(f"   Previous Close: ${previous_close:.2f}" if previous_close else "")
    print(f"   Change: {change_pct:+.2f}%\n")
    
    # 2. Get available expirations (with force refresh to bypass cache if needed)
    print("2. Fetching available option expirations...")
    import time
    time.sleep(2)  # Small delay to avoid rate limiting
    expirations = get_option_expirations(symbol, force_refresh=True)
    if not expirations:
        print(f"❌ No option expirations found for {symbol}")
        return
    
    print(f"✅ Found {len(expirations)} expiration dates")
    
    # Filter for 1-3 weeks out (7-21 days), but also include up to 4 weeks if needed
    today = date.today()
    target_expirations = []
    
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days_to_exp = (exp_date - today).days
            if 1 <= days_to_exp <= 28:  # Include 1-28 days
                target_expirations.append((exp_str, exp_date, days_to_exp))
        except:
            continue
    
    # Sort by days to expiration
    target_expirations.sort(key=lambda x: x[2])
    
    if not target_expirations:
        print(f"⚠️  No expirations in range. Available expirations:")
        for exp_str in expirations[:10]:
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                days = (exp_date - today).days
                print(f"   - {exp_str} ({days} days)")
            except:
                pass
        
        # Try to use the first available expiration anyway
        if expirations:
            exp_str = expirations[0]
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                days = (exp_date - today).days
                if days >= 0:
                    target_expirations = [(exp_str, exp_date, days)]
                    print(f"\n⚠️  Using {exp_str} ({days} days) for analysis...")
            except:
                pass
    
    if not target_expirations:
        print("❌ No usable expirations found")
        return
    
    print(f"\n✅ Found {len(target_expirations)} expirations in 1-3 week range:\n")
    for exp_str, exp_date, days in target_expirations:
        print(f"   - {exp_str} ({days} days to expiration)")
    
    # 3. Analyze options for each expiration
    print(f"\n{'='*80}")
    print("3. OPTION CHAIN ANALYSIS")
    print(f"{'='*80}\n")
    
    recommendations = []
    
    for exp_str, exp_date, days_to_exp in target_expirations:
        print(f"\n📅 Expiration: {exp_str} ({days_to_exp} days)")
        print("-" * 80)
        
        chain = get_option_chain(symbol, exp_str)
        if not chain or (chain.calls.empty and chain.puts.empty):
            print("   ⚠️  No option data available")
            continue
        
        calls_df = chain.calls
        puts_df = chain.puts
        
        # Filter relevant strikes (around current price ± 10%)
        price_range_min = current_price * 0.90
        price_range_max = current_price * 1.10
        
        relevant_calls = calls_df[
            (calls_df['strike'] >= price_range_min) & 
            (calls_df['strike'] <= price_range_max)
        ].copy()
        
        relevant_puts = puts_df[
            (puts_df['strike'] >= price_range_min) & 
            (puts_df['strike'] <= price_range_max)
        ].copy()
        
        # Calculate mid prices (bid/ask average)
        relevant_calls['mid'] = (relevant_calls['bid'] + relevant_calls['ask']) / 2
        relevant_puts['mid'] = (relevant_puts['bid'] + relevant_puts['ask']) / 2
        
        # Key strikes to analyze
        strikes_to_check = [340, 350, 355, 360, 365, 370]
        strikes_to_check = [s for s in strikes_to_check if price_range_min <= s <= price_range_max]
        
        print(f"\n   💰 CALL OPTIONS (Buying Calls - Bullish):")
        print(f"   {'Strike':<8} {'Bid':<8} {'Ask':<8} {'Mid':<8} {'IV':<8} {'ITM':<5} {'Break-Even':<12}")
        print(f"   {'-'*65}")
        
        call_data = []
        for strike in strikes_to_check:
            call = relevant_calls[abs(relevant_calls['strike'] - strike) < 1]
            if not call.empty:
                row = call.iloc[0]
                strike_val = float(row['strike'])
                bid = float(row['bid']) if pd.notna(row['bid']) else 0
                ask = float(row['ask']) if pd.notna(row['ask']) else 0
                mid = (bid + ask) / 2 if (bid > 0 or ask > 0) else 0
                iv = float(row['impliedVolatility']) * 100 if pd.notna(row['impliedVolatility']) else 0
                itm = "Yes" if strike_val < current_price else "No"
                breakeven = strike_val + mid if mid > 0 else 0
                
                # Calculate potential profit if stock recovers
                target_price = current_price * 1.05  # 5% recovery
                intrinsic_at_target = max(0, target_price - strike_val)
                profit_at_target = intrinsic_at_target - mid if mid > 0 else 0
                roi = (profit_at_target / mid * 100) if mid > 0 else 0
                
                call_data.append({
                    'strike': strike_val,
                    'bid': bid,
                    'ask': ask,
                    'mid': mid,
                    'iv': iv,
                    'itm': itm,
                    'breakeven': breakeven,
                    'days': days_to_exp,
                    'profit_5pct': profit_at_target,
                    'roi_5pct': roi
                })
                
                print(f"   ${strike_val:<7.0f} ${bid:<7.2f} ${ask:<7.2f} ${mid:<7.2f} {iv:<7.1f}% {itm:<5} ${breakeven:<11.2f}")
        
        print(f"\n   💰 PUT OPTIONS (Selling Puts - Bullish/Neutral):")
        print(f"   {'Strike':<8} {'Bid':<8} {'Ask':<8} {'Mid':<8} {'IV':<8} {'ITM':<5} {'Premium':<10}")
        print(f"   {'-'*65}")
        
        put_data = []
        for strike in strikes_to_check:
            put = relevant_puts[abs(relevant_puts['strike'] - strike) < 1]
            if not put.empty:
                row = put.iloc[0]
                strike_val = float(row['strike'])
                bid = float(row['bid']) if pd.notna(row['bid']) else 0
                ask = float(row['ask']) if pd.notna(row['ask']) else 0
                mid = (bid + ask) / 2 if (bid > 0 or ask > 0) else 0
                iv = float(row['impliedVolatility']) * 100 if pd.notna(row['impliedVolatility']) else 0
                itm = "Yes" if strike_val > current_price else "No"
                
                # Calculate premium and capital required
                premium_per_contract = mid * 100
                capital_required = strike_val * 100  # Cash-secured
                
                put_data.append({
                    'strike': strike_val,
                    'bid': bid,
                    'ask': ask,
                    'mid': mid,
                    'iv': iv,
                    'itm': itm,
                    'premium': premium_per_contract,
                    'capital': capital_required,
                    'days': days_to_exp
                })
                
                print(f"   ${strike_val:<7.0f} ${bid:<7.2f} ${ask:<7.2f} ${mid:<7.2f} {iv:<7.1f}% {itm:<5} ${premium_per_contract:<9.2f}")
        
        # Store recommendations
        if call_data:
            recommendations.append({
                'expiration': exp_str,
                'days': days_to_exp,
                'type': 'calls',
                'data': call_data
            })
        if put_data:
            recommendations.append({
                'expiration': exp_str,
                'days': days_to_exp,
                'type': 'puts',
                'data': put_data
            })
    
    # 4. Generate recommendations
    print(f"\n{'='*80}")
    print("4. RECOMMENDATIONS")
    print(f"{'='*80}\n")
    
    print("🎯 BUYING CALLS (If you expect recovery within 1-2 weeks):\n")
    best_calls = []
    for rec in recommendations:
        if rec['type'] == 'calls' and rec['days'] <= 14:
            for opt in rec['data']:
                if opt['mid'] > 0:
                    best_calls.append({
                        **opt,
                        'expiration': rec['expiration'],
                        'days': rec['days']
                    })
    
    if best_calls:
        # Sort by ROI if stock recovers 5%
        best_calls.sort(key=lambda x: x.get('roi_5pct', 0), reverse=True)
        
        print("   Top Call Options (assuming 5% stock recovery):")
        print(f"   {'Strike':<8} {'Exp':<12} {'Days':<6} {'Premium':<10} {'5% ROI':<8} {'Break-Even':<12}")
        print(f"   {'-'*70}")
        
        for opt in best_calls[:5]:
            print(f"   ${opt['strike']:<7.0f} {opt['expiration']:<12} {opt['days']:<6} "
                  f"${opt['mid']*100:<9.2f} {opt.get('roi_5pct', 0):>6.1f}%  ${opt.get('breakeven', 0):<11.2f}")
    
    print(f"\n🎯 SELLING PUTS (If you're willing to own stock at lower price):\n")
    best_puts = []
    for rec in recommendations:
        if rec['type'] == 'puts' and rec['days'] <= 21:
            for opt in rec['data']:
                if opt['mid'] > 0 and opt['strike'] < current_price * 0.95:  # Below current price
                    # Calculate return on risk
                    capital = opt['capital']
                    premium = opt['premium']
                    return_pct = (premium / capital) * 100
                    best_puts.append({
                        **opt,
                        'expiration': rec['expiration'],
                        'days': rec['days'],
                        'return_pct': return_pct
                    })
    
    if best_puts:
        # Sort by return percentage
        best_puts.sort(key=lambda x: x['return_pct'], reverse=True)
        
        print("   Top Put Selling Opportunities (below current price):")
        print(f"   {'Strike':<8} {'Exp':<12} {'Days':<6} {'Premium':<10} {'Capital':<10} {'Return':<8}")
        print(f"   {'-'*70}")
        
        for opt in best_puts[:5]:
            print(f"   ${opt['strike']:<7.0f} {opt['expiration']:<12} {opt['days']:<6} "
                  f"${opt['premium']:<9.2f} ${opt['capital']:<9.0f} {opt['return_pct']:>5.2f}%")
    
    print(f"\n{'='*80}\n")
    
    return {
        'current_price': current_price,
        'change_pct': change_pct,
        'recommendations': recommendations,
        'best_calls': best_calls[:5] if best_calls else [],
        'best_puts': best_puts[:5] if best_puts else []
    }

if __name__ == "__main__":
    try:
        result = analyze_avgo_options()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

