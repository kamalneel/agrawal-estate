#!/usr/bin/env python3
"""
Explain exactly how to close both legs of the bull put spread.
"""

print(f"\n{'='*80}")
print(f"HOW TO CLOSE YOUR BULL PUT SPREAD - STEP BY STEP")
print(f"{'='*80}\n")

print(f"YOUR CURRENT POSITIONS:")
print(f"  ✅ SOLD: 1x AVGO $380 Put")
print(f"     → You opened by SELLING")
print(f"     → To CLOSE: You need to BUY it back\n")
print(f"  ✅ BOUGHT: 1x AVGO $370 Put")
print(f"     → You opened by BUYING")
print(f"     → To CLOSE: You need to SELL it\n")

print(f"{'='*80}")
print(f"WHAT YOUR BROKER IS SHOWING:")
print(f"{'='*80}\n")
print(f"1. AVGO $380 Put - '$2,300 to close':")
print(f"   ✅ CORRECT - This is to BUY BACK what you sold")
print(f"   → Action: BUY TO CLOSE (not buy to open)")
print(f"   → Cost: ~$2,300\n")
print(f"2. AVGO $370 Put - '$1,280 to open':")
print(f"   ❌ CONFUSING - This says 'to open' but you need 'to close'")
print(f"   → You BOUGHT this put, so to close you need to SELL it")
print(f"   → Look for 'SELL TO CLOSE' option (not 'buy to open')")
print(f"   → Proceeds: ~$1,280 (money comes TO you)\n")

print(f"{'='*80}")
print(f"EXACT ACTIONS YOU NEED TO TAKE:")
print(f"{'='*80}\n")

print(f"STEP 1: Close the $380 Put (the one you SOLD)")
print(f"  📍 Find: AVGO $380 Put Dec 12 expiration")
print(f"  📍 Action: BUY TO CLOSE (or 'Close Position' or 'Buy Back')")
print(f"  📍 Quantity: 1 contract")
print(f"  📍 Cost: ~$2,300 (this is what you'll pay)")
print(f"  📍 Order Type: LIMIT order at current mid-price\n")

print(f"STEP 2: Close the $370 Put (the one you BOUGHT)")
print(f"  📍 Find: AVGO $370 Put Dec 12 expiration")
print(f"  📍 Action: SELL TO CLOSE (or 'Close Position' or 'Sell')")
print(f"  📍 Quantity: 1 contract")
print(f"  📍 Proceeds: ~$1,280 (this is what you'll receive)")
print(f"  📍 Order Type: LIMIT order at current mid-price\n")

print(f"⚠️  IMPORTANT: The $1,280 shown might be:")
print(f"   Option A: Cost to BUY another one (wrong - don't do this)")
print(f"   Option B: Proceeds from SELLING the one you own (correct!)")
print(f"   → Make sure you're SELLING, not buying more!\n")

print(f"{'='*80}")
print(f"BEST METHOD: CLOSE AS A SPREAD")
print(f"{'='*80}\n")
print(f"Many brokers let you close both legs together:")
print(f"  1. Look for 'Close Spread' or 'Close Position'")
print(f"  2. Select both options ($380 and $370 puts)")
print(f"  3. Choose 'Close Spread' or 'Leg Out'")
print(f"  4. This executes both simultaneously")
print(f"  5. Net cost: ~$2,300 - $1,280 = ~$1,020\n")
print(f"Benefits:")
print(f"  ✅ Both legs execute together (no leg-in risk)")
print(f"  ✅ Better pricing (spread pricing)")
print(f"  ✅ Single transaction\n")

print(f"{'='*80}")
print(f"WHAT TO DO RIGHT NOW:")
print(f"{'='*80}\n")
print(f"1. Check your $370 Put position:")
print(f"   → Does it show 'SELL TO CLOSE' option?")
print(f"   → If it only shows 'BUY TO OPEN', look for a different button")
print(f"   → Try: 'Close Position', 'Sell', or 'Exit Position'\n")
print(f"2. If you can't find 'SELL TO CLOSE':")
print(f"   → Click on your open $370 Put position")
print(f"   → Look for 'Close' or 'Exit' buttons")
print(f"   → Your broker should show your LONG position and how to close it\n")
print(f"3. Execute both orders:")
print(f"   → Option A: Close as spread (if available)")
print(f"   → Option B: Execute both separately (but do them quickly!)\n")

print(f"{'='*80}")
print(f"NET RESULT AFTER CLOSING BOTH:")
print(f"{'='*80}\n")
cost_to_close_380 = 2300
proceeds_from_370 = 1280
net_credit_original = 359  # Original credit received

net_cost = cost_to_close_380 - proceeds_from_370
net_loss = net_cost - net_credit_original

print(f"  Cost to buy back $380 Put: -${cost_to_close_380:,}")
print(f"  Proceeds from selling $370 Put: +${proceeds_from_370:,}")
print(f"  Net cost to close: -${net_cost:,}")
print(f"  Less original credit received: +${net_credit_original:.2f}")
print(f"  TOTAL REALIZED LOSS: -${net_loss:.2f}\n")

print(f"{'='*80}")
print(f"IF YOU'RE STUCK:")
print(f"{'='*80}\n")
print(f"  → Call your broker's options desk")
print(f"  → Say: 'I need to close a bull put spread - buy back my $380 put")
print(f"    and sell my $370 put before expiration'")
print(f"  → They can help you execute both legs\n")


