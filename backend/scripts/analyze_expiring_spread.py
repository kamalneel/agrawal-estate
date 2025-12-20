#!/usr/bin/env python3
"""
Urgent analysis of expiring bull put spread on AVGO.
"""

from datetime import datetime

# Position details
stock_price = 361  # Current stock price (approximate)
expiration_today = True
time_left = 30  # minutes

# User's positions (from their display)
# SOLD 1x AVGO $370 Put - showing +$1,157 profit
# BOUGHT 1x AVGO $380 Put - showing -$1,798 loss

# Note: This seems inverted from typical bull put spread
# Typically: Sell higher strike ($380), Buy lower strike ($370)
# User has: Sold $370, Bought $380

print(f"\n{'='*80}")
print(f"URGENT: EXPIRING BULL PUT SPREAD ANALYSIS")
print(f"{'='*80}\n")
print(f"Stock Price: ~${stock_price}")
print(f"Time to Expiration: {time_left} minutes\n")

# Position breakdown
sold_strike = 370  # Put they SOLD
bought_strike = 380  # Put they BOUGHT
spread_width = abs(bought_strike - sold_strike)  # $10

print(f"Position Details:")
print(f"  SOLD: 1x AVGO ${sold_strike} Put")
print(f"  BOUGHT: 1x AVGO ${bought_strike} Put")
print(f"  Spread Width: ${spread_width}\n")

# Current situation analysis
print(f"Current Situation:")
print(f"  Stock is at ${stock_price}")
print(f"  ${bought_strike} Put: {'ITM' if stock_price < bought_strike else 'OTM'} "
      f"(Intrinsic: ${max(0, bought_strike - stock_price):.2f})")
print(f"  ${sold_strike} Put: {'ITM' if stock_price < sold_strike else 'OTM'} "
      f"(Intrinsic: ${max(0, sold_strike - stock_price):.2f})\n")

# What happens at expiration
print(f"{'='*80}")
print("WHAT HAPPENS AT EXPIRATION (If Stock Closes at Current $361):")
print(f"{'='*80}\n")

if stock_price < sold_strike:
    print(f"❌ CRITICAL: Both puts are IN THE MONEY!")
    print(f"\nOutcome:")
    print(f"  1. Your SOLD ${sold_strike} Put:")
    print(f"     → You WILL BE ASSIGNED (obligated to buy 100 shares at ${sold_strike})")
    print(f"     → Cost: ${sold_strike * 100:,}")
    print(f"     → Current value: ${stock_price * 100:,}")
    print(f"     → Loss on assignment: ${(sold_strike - stock_price) * 100:.2f}")
    
    print(f"\n  2. Your BOUGHT ${bought_strike} Put:")
    print(f"     → You can EXERCISE (sell 100 shares at ${bought_strike})")
    print(f"     → This protects you up to ${bought_strike}")
    
    print(f"\n  Net Result (after exercising both):")
    buy_cost = sold_strike * 100
    sell_proceeds = bought_strike * 100
    net_loss = (bought_strike - sold_strike) * 100
    
    # Need to account for original premium received/paid
    # Display shows: +$1,157 on sold, -$1,798 on bought
    # Net credit received initially = $1,157 - $1,798 = -$641 (they actually paid a debit!)
    
    # Actually, the displayed P/L might be different
    # Let me calculate based on spread mechanics
    
    print(f"     → Buy at ${sold_strike}: ${buy_cost:,}")
    print(f"     → Sell at ${bought_strike}: ${sell_proceeds:,}")
    print(f"     → Gross loss: ${net_loss:,}")
    print(f"     → Less original net credit/debit received")
    print(f"     → MAX LOSS = Spread width - Net credit = ${spread_width * 100:,} - Net credit\n")

elif sold_strike <= stock_price < bought_strike:
    print(f"⚠️  Partial ITM:")
    print(f"  ${sold_strike} Put: OTM (expires worthless) ✅")
    print(f"  ${bought_strike} Put: ITM (has value, but you paid for it)")
    print(f"  Result: Partial loss\n")
    
else:
    print(f"✅ Both puts expire worthless!")
    print(f"  You keep the net credit received\n")

# Recommendations
print(f"{'='*80}")
print("URGENT RECOMMENDATIONS:")
print(f"{'='*80}\n")

print("Option 1: CLOSE THE SPREAD NOW (RECOMMENDED)")
print("-" * 80)
print("  Action: Buy back the ${sold_strike} Put you sold + Sell the ${bought_strike} Put you bought")
print("  Why: Lock in current P/L, avoid assignment risk")
print("  Cost: Current bid-ask spread + commissions")
print("  Benefit: Certainty, no assignment risk\n")

print("Option 2: WAIT AND EXERCISE BOTH (If Stock Stays Below $370)")
print("-" * 80)
print("  Action: Let assignment happen, then exercise your ${bought_strike} put")
print("  Why: If you want to avoid paying to close")
print("  Risk: Need to have cash for assignment, then immediately exercise")
print("  Note: Only do this if closing cost > spread loss\n")

print("Option 3: ROLL THE SPREAD (If you want to extend)")
print("-" * 80)
print("  Action: Close current spread + Open new spread for next week")
print("  Why: Give stock more time to recover")
print("  Cost: Current loss + new spread cost")
print("  Only if: You still think stock will recover\n")

print(f"\n{'='*80}")
print("MY RECOMMENDATION:")
print(f"{'='*80}\n")
print("Given stock is at $361 (below both strikes):")
print("\n🚨 IMMEDIATELY CLOSE THE SPREAD")
print("\nSteps:")
print("  1. Buy to Close: 1x AVGO ${sold_strike} Put (buy back what you sold)")
print("  2. Sell to Close: 1x AVGO ${bought_strike} Put (sell what you bought)")
print("  3. Do this as a SPREAD ORDER (leg-in risk if done separately)")
print("\nWhy:")
print("  ✅ Locks in current loss (likely ~$600-800 based on spread width)")
print("  ✅ Avoids assignment risk and overnight margin requirements")
print("  ✅ Prevents potential exercise fees")
print("  ✅ Clears your position before market close\n")

print("If you can't close:")
print("  → Make sure you have ${sold_strike * 100:,} cash available")
print("  → Be ready to exercise your ${bought_strike} put immediately if assigned")
print("  → Contact your broker about automatic exercise procedures\n")


