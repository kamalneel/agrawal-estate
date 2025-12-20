#!/usr/bin/env python3
"""
Clarify what happens at expiration with the bull put spread.
"""

print(f"\n{'='*80}")
print(f"WHAT HAPPENS IF YOU LET IT EXPIRE - DETAILED EXPLANATION")
print(f"{'='*80}\n")

# Position details
sold_strike = 380  # Put you SOLD
bought_strike = 370  # Put you BOUGHT
current_stock_price = 356.70
net_credit = 3.59  # per share

print(f"Your Position:")
print(f"  ✅ SOLD: 1x AVGO ${sold_strike} Put")
print(f"     → This creates an OBLIGATION to BUY 100 shares at ${sold_strike}")
print(f"     → If stock closes below ${sold_strike}, you WILL be assigned\n")
print(f"  ✅ BOUGHT: 1x AVGO ${bought_strike} Put")
print(f"     → This gives you the RIGHT to SELL 100 shares at ${bought_strike}")
print(f"     → If stock closes below ${bought_strike}, it will auto-exercise\n")

print(f"Current Stock Price: ${current_stock_price}")
print(f"Both puts are IN THE MONEY\n")

print(f"{'='*80}")
print(f"AT EXPIRATION (Saturday Morning - Auto-Assignment/Exercise):")
print(f"{'='*80}\n")

print(f"1. Your SOLD ${sold_strike} Put:")
print(f"   → You WILL BE ASSIGNED")
print(f"   → You MUST BUY 100 shares of AVGO at ${sold_strike} per share")
print(f"   → Cost: ${sold_strike * 100:,}")
print(f"   → You now OWN 100 shares (bought at ${sold_strike})\n")

print(f"2. Your BOUGHT ${bought_strike} Put:")
print(f"   → It will AUTO-EXERCISE (because stock < ${bought_strike})")
print(f"   → You WILL SELL those 100 shares at ${bought_strike} per share")
print(f"   → Proceeds: ${bought_strike * 100:,}")
print(f"   → You NO LONGER own shares (sold at ${bought_strike})\n")

print(f"{'='*80}")
print(f"NET RESULT:")
print(f"{'='*80}\n")
print(f"Step-by-step:")
print(f"  1. Buy 100 shares at ${sold_strike}: -${sold_strike * 100:,}")
print(f"  2. Sell 100 shares at ${bought_strike}: +${bought_strike * 100:,}")
print(f"  3. Net cash flow: -${(sold_strike - bought_strike) * 100:,}")
print(f"  4. Plus net credit received: +${net_credit * 100:.2f}")
print(f"  5. FINAL LOSS: ${((sold_strike - bought_strike) * 100) - (net_credit * 100):.2f}\n")

print(f"ANSWER TO YOUR QUESTION:")
print(f"  ❓ At what price would you buy AVGO?")
print(f"  ✅ You would BUY at ${sold_strike} (your sold put strike)\n")
print(f"  ❓ Would you own AVGO after expiration?")
print(f"  ✅ NO - You buy at ${sold_strike}, then immediately sell at ${bought_strike}")
print(f"     You end up with NO SHARES, just a ${(sold_strike - bought_strike) * 100 - net_credit * 100:.2f} loss\n")

print(f"{'='*80}")
print(f"IMPORTANT DETAILS:")
print(f"{'='*80}\n")
print(f"⏰ Timing:")
print(f"  - Assignment/exercise happens Saturday morning (expiration day +1)")
print(f"  - You'll see shares in your account temporarily")
print(f"  - Then they'll be sold immediately via exercise\n")

print(f"💰 Cash Requirements:")
print(f"  - You NEED ${sold_strike * 100:,} available (to buy at ${sold_strike})")
print(f"  - This cash is needed from Friday night through Saturday morning")
print(f"  - If you don't have it, your broker may:")
print(f"    * Liquidate other positions")
print(f"    * Charge margin interest")
print(f"    * Reject the assignment (forced liquidation)\n")

print(f"💸 Fees:")
print(f"  - Assignment fee: ~$0-$25 per contract")
print(f"  - Exercise fee: ~$0-$25 per contract")
print(f"  - Total fees: ~$0-$50\n")

print(f"{'='*80}")
print(f"SUMMARY:")
print(f"{'='*80}\n")
print(f"  ✅ You would BUY AVGO at ${sold_strike} per share")
print(f"  ✅ But you would SELL it immediately at ${bought_strike} per share")
print(f"  ✅ Final result: NO SHARES, just a ${((sold_strike - bought_strike) * 100) - (net_credit * 100):.2f} cash loss")
print(f"  ✅ Effective cost: ${sold_strike - bought_strike:.2f} per share spread - ${net_credit:.2f} credit = ${(sold_strike - bought_strike) - net_credit:.2f} loss\n")


