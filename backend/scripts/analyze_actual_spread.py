#!/usr/bin/env python3
"""
Analyze actual bull put spread position from screenshots.
"""

print(f"\n{'='*80}")
print(f"URGENT: ACTUAL POSITION ANALYSIS - EXPIRING TODAY")
print(f"{'='*80}\n")

# From Image 1: SOLD PUT
sold_strike = 380
sold_credit = 5.60  # Average credit received
sold_breakeven = 374.40
sold_current_price = 23.53  # Current option price
sold_market_value = -2353.00  # Negative because you sold it
sold_total_return = -1793.00

# From Image 2: BOUGHT PUT  
bought_strike = 370  # Inferred from breakeven $367.99 + cost $2.01
bought_cost = 2.01  # Average cost paid
bought_breakeven = 367.99
bought_current_price = 13.03  # Current option price
bought_market_value = 1303.00  # Positive because you bought it
bought_total_return = 1102.00

# Current stock price (average from both screenshots)
current_stock_price = 356.70  # Average of $356.46 and $356.93

# Spread details
spread_width = sold_strike - bought_strike  # $380 - $370 = $10
net_credit = sold_credit - bought_cost  # $5.60 - $2.01 = $3.59

print(f"POSITION DETAILS:")
print(f"  SOLD: 1x AVGO ${sold_strike} Put")
print(f"    - Credit received: ${sold_credit:.2f} per share = ${sold_credit * 100:.2f} per contract")
print(f"    - Current option price: ${sold_current_price:.2f}")
print(f"    - Unrealized loss: ${abs(sold_total_return):.2f}")
print(f"    - Breakeven: ${sold_breakeven:.2f}")
print()
print(f"  BOUGHT: 1x AVGO ${bought_strike} Put")
print(f"    - Cost paid: ${bought_cost:.2f} per share = ${bought_cost * 100:.2f} per contract")
print(f"    - Current option price: ${bought_current_price:.2f}")
print(f"    - Unrealized gain: ${bought_total_return:.2f}")
print(f"    - Breakeven: ${bought_breakeven:.2f}")
print()
print(f"  NET POSITION:")
print(f"    - Net credit received: ${net_credit:.2f} per share = ${net_credit * 100:.2f}")
print(f"    - Spread width: ${spread_width:.2f}")
print(f"    - Current stock price: ${current_stock_price:.2f}")
print(f"    - Net unrealized P/L: ${bought_total_return + sold_total_return:.2f}")
print()

# What happens at expiration
print(f"{'='*80}")
print(f"WHAT HAPPENS AT EXPIRATION (Stock @ ${current_stock_price}):")
print(f"{'='*80}\n")

# Both puts are ITM
sold_put_intrinsic = max(0, sold_strike - current_stock_price)  # $380 - $356.70 = $23.30
bought_put_intrinsic = max(0, bought_strike - current_stock_price)  # $370 - $356.70 = $13.30

print(f"Both puts are IN THE MONEY!")
print(f"  ${sold_strike} Put intrinsic value: ${sold_put_intrinsic:.2f}")
print(f"  ${bought_strike} Put intrinsic value: ${bought_put_intrinsic:.2f}")
print()

# At expiration, if you let it expire:
print(f"If you LET BOTH EXPIRE:")
print(f"  1. Your SOLD ${sold_strike} Put will be assigned")
print(f"     → You MUST buy 100 shares at ${sold_strike} = ${sold_strike * 100:,}")
print()
print(f"  2. Your BOUGHT ${bought_strike} Put will be auto-exercised (if ITM)")
print(f"     → You CAN sell 100 shares at ${bought_strike} = ${bought_strike * 100:,}")
print()
print(f"  3. Net result:")
print(f"     → Buy at ${sold_strike}: ${sold_strike * 100:,}")
print(f"     → Sell at ${bought_strike}: ${bought_strike * 100:,}")
print(f"     → Gross cash flow: -${(sold_strike - bought_strike) * 100:.2f}")
print(f"     → Plus net credit received: +${net_credit * 100:.2f}")
print(f"     → NET LOSS: ${(spread_width * 100) - (net_credit * 100):.2f}")
print()

# Current value to close
close_cost_sold = sold_current_price * 100  # Cost to buy back
close_proceeds_bought = bought_current_price * 100  # Proceeds from selling
net_close_cost = close_cost_sold - close_proceeds_bought  # Net cost to close

print(f"{'='*80}")
print(f"CURRENT MARKET VALUE TO CLOSE:")
print(f"{'='*80}\n")
print(f"  Cost to buy back ${sold_strike} Put: ${close_cost_sold:.2f}")
print(f"  Proceeds from selling ${bought_strike} Put: ${close_proceeds_bought:.2f}")
print(f"  NET COST TO CLOSE: ${net_close_cost:.2f}")
print()

# Compare
max_loss_if_expire = (spread_width * 100) - (net_credit * 100)
current_realized_loss = net_close_cost - (net_credit * 100)

print(f"COMPARISON:")
print(f"  Max loss if you let expire: ${max_loss_if_expire:.2f}")
print(f"  Current loss if you close now: ${current_realized_loss:.2f}")
print(f"  Difference: ${max_loss_if_expire - current_realized_loss:.2f}")
print()

print(f"{'='*80}")
print(f"🚨 URGENT RECOMMENDATION:")
print(f"{'='*80}\n")

if current_realized_loss < max_loss_if_expire:
    print("✅ CLOSE THE SPREAD NOW!")
    print()
    print("Reasons:")
    print("  1. Current loss ($691) is LESS than max loss if you let expire")
    print("  2. Avoids assignment and need for cash")
    print("  3. Avoids exercise fees")
    print("  4. Clears position before market close")
    print()
    print("ACTION STEPS:")
    print("  1. Place a SPREAD ORDER to close:")
    print(f"     - Buy to Close: 1x AVGO ${sold_strike} Put @ limit ${sold_current_price:.2f}")
    print(f"     - Sell to Close: 1x AVGO ${bought_strike} Put @ limit ${bought_current_price:.2f}")
    print("  2. Use LIMIT orders (not market) to avoid slippage")
    print("  3. Execute as SPREAD (not leg-in) to minimize risk")
    print("  4. Set limit near current mid-prices")
else:
    print("⚠️  If closing cost > max loss, you might let expire, but this requires:")
    print("  1. Having ${sold_strike * 100:,} cash ready")
    print("  2. Ensuring your broker auto-exercises your ${bought_strike} put")
    print("  3. Understanding you'll realize the max loss anyway")

print()
print(f"{'='*80}")
print("FINAL ADVICE:")
print(f"{'='*80}\n")
print("Given you have 30 minutes:")
print("→ CLOSE THE SPREAD IMMEDIATELY")
print("→ Realize the $691 loss now (better than max loss)")
print("→ Free up capital and avoid weekend assignment risk")
print("→ Move on - this spread is not recoverable at current price\n")


