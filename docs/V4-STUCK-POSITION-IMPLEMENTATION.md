# V4 Algorithm Update: Stuck Position Handling

**Created:** February 3, 2026
**Status:** Proposal - Ready for Implementation

---

## Overview

This document outlines how to update the V4 notification algorithm to handle stuck positions using the new framework with **TIME TRAPPED** and **DEEP UNDERWATER** categories.

---

## Part 1: New Position Categories

### Add to `algorithm_config.py`

```python
# Position Categories
POSITION_CATEGORIES = {
    "SWIMMING": {
        "description": "Healthy weekly position, OTM or ATM",
        "criteria": {"expiry_days": "<=7", "itm_pct": "<=0"},
        "priority": "low",
    },
    "SHALLOW_UNDERWATER": {
        "description": "Weekly position, slightly ITM",
        "criteria": {"expiry_days": "<=7", "itm_pct": "0-10"},
        "priority": "medium",
    },
    "DEEP_UNDERWATER": {
        "description": "Weekly position, significantly ITM but weekly rolls still profitable",
        "criteria": {"expiry_days": "<=7", "itm_pct": "10-25", "weekly_roll": "> 0"},
        "priority": "high",
    },
    "LIFE_SUPPORT": {
        "description": "Weekly roll = $0, but bi-weekly roll still generates credit",
        "criteria": {"weekly_roll": "= 0", "biweekly_roll": "> 0"},
        "priority": "high",
    },
    "DROWNING": {
        "description": "ALL rolls (weekly, bi-weekly, monthly) require a debit",
        "criteria": {"weekly_roll": "< 0", "biweekly_roll": "<= 0"},
        "priority": "critical",
    },
    "TIME_TRAPPED": {
        "description": "Long-dated position, ITM, missing weekly income",
        "criteria": {"expiry_days": ">7", "itm_pct": ">0"},
        "priority": "high",
    },
}

# LIFE SUPPORT Thresholds by IV (Validated with Robinhood data Feb 3, 2026)
# These are ITM% where weekly rolls hit $0, but bi-weekly still works
LIFE_SUPPORT_THRESHOLDS = {
    "high_iv": {      # IV >= 60%
        "life_support_starts": 30,  # ITM% where weekly = $0
        "drowning_starts": 35,      # ITM% where bi-weekly = $0 (estimated)
        "example": "HOOD at $85.54, $111 strike = 30% ITM: weekly=$0, bi-weekly=$0.30 credit"
    },
    "medium_iv": {    # IV 35-60%
        "life_support_starts": 17,  # ITM% where weekly = $0
        "drowning_starts": 22,      # ITM% where bi-weekly = $0 (estimated)
        "example": "AVGO at $309.12, $360 strike = 16.5% ITM = $0.25 weekly credit"
    },
    "low_iv": {       # IV < 35%
        "life_support_starts": 10,  # Estimated
        "drowning_starts": 15,      # Estimated
        "example": "Estimated based on IV pattern"
    },
}

# Thresholds for decisions
STUCK_POSITION_CONFIG = {
    # DEEP UNDERWATER thresholds
    "take_loss_breakeven_weeks_threshold": 20,  # Take loss if breakeven < 20 weeks

    # TIME TRAPPED thresholds
    "compression_breakeven_attractive": 26,  # Compress if breakeven < 26 weeks
    "compression_breakeven_marginal": 52,    # Marginal zone: 26-52 weeks
    "take_loss_time_trapped_threshold": 12,  # Take loss if breakeven < 12 weeks

    # Minimum days before expiry to recommend waiting
    "min_days_for_wait_strategy": 45,

    # Alert trigger points (% from strike)
    "alert_levels": [0.10, 0.05, 0.02, 0.00],  # 10%, 5%, 2%, ATM
}
```

---

## Part 2: New Categorization Function

### Add to `v4_position_evaluator.py`

```python
def get_life_support_thresholds(self, symbol: str) -> tuple:
    """
    Get the ITM% thresholds for LIFE_SUPPORT and DROWNING.
    Based on IV (validated with Robinhood data Feb 3, 2026).

    Returns:
        (life_support_threshold, drowning_threshold)
    """
    iv = self._get_implied_volatility(symbol)

    if iv >= 60:      # High IV (HOOD-like)
        return (30.0, 35.0)  # Life support at 30%, drowning at 35%
    elif iv >= 35:    # Medium IV (AVGO-like)
        return (17.0, 22.0)  # Life support at 17%, drowning at 22%
    else:             # Low IV
        return (10.0, 15.0)  # Estimated


def categorize_position(
    self,
    position,
    stock_price: float,
    weekly_roll_credit: float = None,
    biweekly_roll_credit: float = None
) -> str:
    """
    Categorize position as SWIMMING, SHALLOW_UNDERWATER,
    DEEP_UNDERWATER, LIFE_SUPPORT, DROWNING, or TIME_TRAPPED.

    CRITICAL: DROWNING = ALL rolls are debits
              LIFE_SUPPORT = Weekly=$0, but bi-weekly still generates credit

    Returns:
        Category string
    """
    strike = float(position.strike_price)
    option_type = position.option_type
    days_to_exp = (position.expiration_date - date.today()).days

    # Calculate ITM %
    if option_type == 'call':
        itm_amount = max(0, stock_price - strike)
    else:  # put
        itm_amount = max(0, strike - stock_price)

    itm_pct = (itm_amount / stock_price * 100) if stock_price > 0 else 0
    is_itm = itm_pct > 0

    # Get thresholds for this stock's IV
    life_support_threshold, drowning_threshold = self.get_life_support_thresholds(position.symbol)

    # Categorize
    if days_to_exp <= 14:  # Weekly/Bi-weekly positions
        if not is_itm:
            return "SWIMMING"
        elif itm_pct <= 10:
            return "SHALLOW_UNDERWATER"
        elif itm_pct < life_support_threshold:
            return "DEEP_UNDERWATER"
        else:
            # Need to check actual roll credits to distinguish LIFE_SUPPORT vs DROWNING
            # If we have actual roll data, use it
            if weekly_roll_credit is not None and biweekly_roll_credit is not None:
                if weekly_roll_credit <= 0 and biweekly_roll_credit > 0:
                    return "LIFE_SUPPORT"  # Weekly=$0, bi-weekly=credit
                elif biweekly_roll_credit <= 0:
                    return "DROWNING"  # All rolls are debits
                else:
                    return "DEEP_UNDERWATER"  # Still getting weekly credits
            else:
                # Use ITM% as proxy
                if itm_pct < drowning_threshold:
                    return "LIFE_SUPPORT"
                else:
                    return "DROWNING"
    else:  # Long-dated (>14 days)
        if is_itm:
            return "TIME_TRAPPED"
        else:
            return "SWIMMING"  # Long-dated OTM is fine
```

---

## Part 3: Category-Specific Handlers

### DEEP UNDERWATER Handler

```python
def _handle_deep_underwater(
    self,
    position,
    stock_price: float,
    itm_pct: float,
    weekly_credit: float,
) -> V4EvaluationResult:
    """
    Handle DEEP UNDERWATER positions (weekly, >10% ITM).

    Strategy: Hold and wait for recovery, or take loss if breakeven is good.
    """
    # Get ATM income for comparison
    atm_income = self._estimate_atm_weekly_income(position.symbol, stock_price)

    # Calculate take-loss breakeven
    buyback_cost = self._get_current_premium(position) * 100
    original_premium = float(position.original_premium or 0) * 100
    loss = buyback_cost - original_premium

    income_improvement = atm_income - weekly_credit
    take_loss_breakeven = loss / income_improvement if income_improvement > 0 else float('inf')

    # Decision
    threshold = self.config.get('take_loss_breakeven_weeks_threshold', 20)

    if take_loss_breakeven < threshold:
        # Recommend taking loss
        reason = (
            f"**DEEP UNDERWATER - Consider Taking Loss**\n\n"
            f"Position: {position.symbol} ${position.strike_price} {position.option_type}\n"
            f"ITM: {itm_pct:.1f}%\n"
            f"Current weekly income: ${weekly_credit:.0f}/contract\n"
            f"ATM weekly income: ${atm_income:.0f}/contract\n\n"
            f"**Take Loss Analysis:**\n"
            f"- Loss to close: ${loss:.0f}\n"
            f"- Income improvement: ${income_improvement:.0f}/week\n"
            f"- Breakeven: {take_loss_breakeven:.0f} weeks\n\n"
            f"With breakeven under {threshold} weeks, taking the loss and "
            f"restarting at ATM may be worthwhile."
        )
        reason_short = f"Deep underwater, take-loss breakeven {take_loss_breakeven:.0f} weeks"

        return V4EvaluationResult(
            action='CONSIDER_TAKE_LOSS',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='optimize_income',
            details={
                'category': 'DEEP_UNDERWATER',
                'itm_pct': itm_pct,
                'weekly_credit': weekly_credit,
                'atm_income': atm_income,
                'take_loss_breakeven': take_loss_breakeven,
                'loss_amount': loss,
            }
        )
    else:
        # Recommend holding
        # Calculate price target for recovery
        if position.option_type == 'call':
            recovery_target = position.strike_price * 1.05
        else:
            recovery_target = position.strike_price * 0.95

        reason = (
            f"**DEEP UNDERWATER - Hold and Roll Weekly**\n\n"
            f"Position: {position.symbol} ${position.strike_price} {position.option_type}\n"
            f"ITM: {itm_pct:.1f}%\n"
            f"Weekly income: ${weekly_credit:.0f}/contract\n\n"
            f"Taking loss not recommended (breakeven {take_loss_breakeven:.0f} weeks > {threshold}).\n"
            f"Keep rolling weekly and wait for recovery.\n\n"
            f"**Price Alert:** Set alert at ${recovery_target:.2f}"
        )
        reason_short = f"Deep underwater, hold for ${weekly_credit:.0f}/week"

        return V4EvaluationResult(
            action='HOLD',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='mean_reversion',
            details={
                'category': 'DEEP_UNDERWATER',
                'itm_pct': itm_pct,
                'weekly_credit': weekly_credit,
                'recovery_target': recovery_target,
            },
            # Set follow-up for price alert
            has_follow_up=True,
            follow_up_condition='price_recovery',
            follow_up_threshold=recovery_target,
            follow_up_action='REASSESS',
        )
```

### LIFE SUPPORT Handler

```python
def _handle_life_support(
    self,
    position,
    stock_price: float,
    itm_pct: float,
    biweekly_roll_credit: float,
) -> V4EvaluationResult:
    """
    Handle LIFE SUPPORT positions (weekly=$0, but bi-weekly=credit).

    Strategy: Extend roll cadence to bi-weekly, wait for recovery.
    The user believes in the stock and can maintain without paying debits.
    """
    # Calculate annual income on bi-weekly cadence
    contracts = getattr(position, 'contracts_sold', 1) or 1
    annual_biweekly_income = biweekly_roll_credit * contracts * 26  # 26 bi-weekly periods

    # Calculate take-loss breakeven for comparison
    buyback_cost = self._get_current_premium(position) * 100 * contracts
    original_premium = float(position.original_premium or 0) * 100 * contracts
    loss = buyback_cost - original_premium
    atm_income = self._estimate_atm_weekly_income(position.symbol, stock_price) * contracts
    take_loss_breakeven = loss / atm_income if atm_income > 0 else float('inf')

    # Calculate recovery target
    if position.option_type == 'call':
        recovery_target = float(position.strike_price) * 0.90  # 10% ITM
    else:
        recovery_target = float(position.strike_price) * 1.10  # Stock rises to 10% below strike

    reason = (
        f"**LIFE SUPPORT - Switch to Bi-Weekly Rolls**\n\n"
        f"Position: {position.symbol} ${position.strike_price} {position.option_type}\n"
        f"ITM: {itm_pct:.1f}%\n"
        f"Weekly roll: $0 (breakeven)\n"
        f"Bi-weekly roll: **${biweekly_roll_credit:.2f}/contract** ✓\n\n"
        f"**You're NOT drowning!** Bi-weekly rolls still generate credit.\n\n"
        f"**Strategy:**\n"
        f"- Switch from weekly to bi-weekly rolls\n"
        f"- Annual income: ~${annual_biweekly_income:.0f} ({contracts} contracts)\n"
        f"- Wait for stock to recover\n\n"
        f"**Price Alert:** Set alert at ${recovery_target:.0f} (back to Deep Underwater)\n\n"
        f"**Alternative - Take Loss:**\n"
        f"- Loss: ${loss:.0f}\n"
        f"- New ATM income: ${atm_income:.0f}/week\n"
        f"- Breakeven: {take_loss_breakeven:.0f} weeks"
    )
    reason_short = f"Life support at {itm_pct:.0f}% ITM - roll bi-weekly for ${biweekly_roll_credit:.2f}"

    return V4EvaluationResult(
        action='ROLL_BIWEEKLY',
        position_id=str(position.id),
        symbol=position.symbol,
        reason=reason,
        reason_short=reason_short,
        philosophy_applied='survival',
        details={
            'category': 'LIFE_SUPPORT',
            'itm_pct': itm_pct,
            'weekly_roll_credit': 0,
            'biweekly_roll_credit': biweekly_roll_credit,
            'annual_income': annual_biweekly_income,
            'recovery_target': recovery_target,
            'take_loss_breakeven': take_loss_breakeven,
        },
        has_follow_up=True,
        follow_up_condition='price_recovery',
        follow_up_threshold=recovery_target,
        follow_up_action='REASSESS',
    )
```

### DROWNING Handler

```python
def _handle_drowning(
    self,
    position,
    stock_price: float,
    itm_pct: float,
) -> V4EvaluationResult:
    """
    Handle DROWNING positions (ALL rolls require a debit).

    Strategy: TAKE LOSS immediately - no other viable option.
    """
    contracts = getattr(position, 'contracts_sold', 1) or 1

    # Calculate take-loss breakeven
    buyback_cost = self._get_current_premium(position) * 100 * contracts
    original_premium = float(position.original_premium or 0) * 100 * contracts
    loss = buyback_cost - original_premium
    atm_income = self._estimate_atm_weekly_income(position.symbol, stock_price) * contracts
    take_loss_breakeven = loss / atm_income if atm_income > 0 else float('inf')

    reason = (
        f"**DROWNING - ALL Rolls Require Debit**\n\n"
        f"Position: {position.symbol} ${position.strike_price} {position.option_type}\n"
        f"ITM: {itm_pct:.1f}%\n"
        f"Weekly roll: DEBIT\n"
        f"Bi-weekly roll: DEBIT\n\n"
        f"**CRITICAL:** You cannot maintain this position without paying money.\n"
        f"Every roll costs you cash. This is a true crisis.\n\n"
        f"**Only Option - Take Loss:**\n"
        f"- Loss to close: ${loss:.0f}\n"
        f"- New ATM income: ${atm_income:.0f}/week\n"
        f"- Breakeven: {take_loss_breakeven:.0f} weeks\n\n"
        f"**Recommendation:** Take loss NOW and restart at ATM."
    )
    reason_short = f"DROWNING at {itm_pct:.0f}% ITM - ALL rolls are debits, TAKE LOSS"

    return V4EvaluationResult(
        action='TAKE_LOSS',
        position_id=str(position.id),
        symbol=position.symbol,
        reason=reason,
        reason_short=reason_short,
        philosophy_applied='cut_losses',
        urgency='critical',
        details={
            'category': 'DROWNING',
            'itm_pct': itm_pct,
            'weekly_roll_credit': -1,  # Negative = debit
            'biweekly_roll_credit': -1,
            'loss_amount': loss,
            'atm_income': atm_income,
            'take_loss_breakeven': take_loss_breakeven,
        }
    )
```

### TIME TRAPPED Handler

```python
def _handle_time_trapped(
    self,
    position,
    stock_price: float,
    itm_pct: float,
    days_to_exp: int,
) -> V4EvaluationResult:
    """
    Handle TIME TRAPPED positions (long-dated, ITM).

    Strategy: Wait, compress, or take loss based on breakeven analysis.
    """
    strike = float(position.strike_price)

    # Calculate compression cost
    compression_cost = self._calculate_compression_cost(position, stock_price)

    # Estimate weekly income if compressed
    weekly_income = self._estimate_weekly_income_at_strike(
        position.symbol, strike, stock_price, position.option_type
    )

    # Calculate compression breakeven
    compression_breakeven = compression_cost / weekly_income if weekly_income > 0 else float('inf')

    # Calculate take-loss breakeven
    buyback_cost = self._get_long_dated_premium(position) * 100
    original_premium = float(position.original_premium or 0) * 100
    loss = buyback_cost - original_premium
    atm_income = self._estimate_atm_weekly_income(position.symbol, stock_price)
    take_loss_breakeven = loss / atm_income if atm_income > 0 else float('inf')

    # Get thresholds
    attractive_threshold = self.config.get('compression_breakeven_attractive', 26)
    marginal_threshold = self.config.get('compression_breakeven_marginal', 52)
    take_loss_threshold = self.config.get('take_loss_time_trapped_threshold', 12)
    min_days_wait = self.config.get('min_days_for_wait_strategy', 45)

    # Decision tree
    if compression_breakeven < attractive_threshold:
        # COMPRESS
        reason = (
            f"**TIME TRAPPED - Compress to Weekly**\n\n"
            f"Position: {position.symbol} ${strike:.0f} {position.option_type} "
            f"(expires {position.expiration_date})\n"
            f"ITM: {itm_pct:.1f}%\n"
            f"Days to expiry: {days_to_exp}\n\n"
            f"**Compression Analysis:**\n"
            f"- Compression cost: ${compression_cost:.0f}\n"
            f"- Weekly income after: ${weekly_income:.0f}/contract\n"
            f"- Breakeven: {compression_breakeven:.0f} weeks ✓\n\n"
            f"Compression recommended - you'll recover the cost in {compression_breakeven:.0f} weeks "
            f"while earning income."
        )
        reason_short = f"Time trapped, compress (breakeven {compression_breakeven:.0f} weeks)"

        return V4EvaluationResult(
            action='COMPRESS',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='weekly_options_income',
            details={
                'category': 'TIME_TRAPPED',
                'compression_cost': compression_cost,
                'weekly_income': weekly_income,
                'compression_breakeven': compression_breakeven,
            },
            net_cost=compression_cost,
        )

    elif days_to_exp > min_days_wait:
        # WAIT - have time
        # Calculate price targets
        price_targets = self._calculate_price_targets(position, stock_price)

        reason = (
            f"**TIME TRAPPED - Wait for Stock Movement**\n\n"
            f"Position: {position.symbol} ${strike:.0f} {position.option_type} "
            f"(expires {position.expiration_date})\n"
            f"ITM: {itm_pct:.1f}%\n"
            f"Days to expiry: {days_to_exp}\n\n"
            f"**Why Wait:**\n"
            f"- Compression breakeven: {compression_breakeven:.0f} weeks (too long)\n"
            f"- You have {days_to_exp} days - time for stock to move\n"
            f"- Waiting costs ~$0 (minimal theta on long-dated)\n\n"
            f"**Set Price Alerts:**\n"
        )
        for target in price_targets:
            reason += f"- ${target['price']:.0f}: {target['action']}\n"

        reason_short = f"Time trapped, wait for movement ({days_to_exp}d left)"

        return V4EvaluationResult(
            action='WAIT',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='mean_reversion',
            details={
                'category': 'TIME_TRAPPED',
                'compression_breakeven': compression_breakeven,
                'price_targets': price_targets,
            },
            has_follow_up=True,
            follow_up_condition='price_movement',
            follow_up_threshold=price_targets[0]['price'] if price_targets else None,
            follow_up_action='REASSESS',
        )

    elif take_loss_breakeven < take_loss_threshold:
        # TAKE LOSS
        reason = (
            f"**TIME TRAPPED - Consider Taking Loss**\n\n"
            f"Position: {position.symbol} ${strike:.0f} {position.option_type}\n"
            f"ITM: {itm_pct:.1f}%\n"
            f"Days to expiry: {days_to_exp}\n\n"
            f"**Analysis:**\n"
            f"- Compression breakeven: {compression_breakeven:.0f} weeks (too long)\n"
            f"- Limited time remaining ({days_to_exp} days)\n\n"
            f"**Take Loss Option:**\n"
            f"- Loss to close: ${loss:.0f}\n"
            f"- New ATM income: ${atm_income:.0f}/week\n"
            f"- Breakeven: {take_loss_breakeven:.0f} weeks\n\n"
            f"Taking loss and restarting at ATM recovers quickly."
        )
        reason_short = f"Time trapped, take loss (recover in {take_loss_breakeven:.0f} weeks)"

        return V4EvaluationResult(
            action='TAKE_LOSS',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='cut_losses',
            details={
                'category': 'TIME_TRAPPED',
                'loss_amount': loss,
                'atm_income': atm_income,
                'take_loss_breakeven': take_loss_breakeven,
            },
        )

    else:
        # No good option - wait and reassess
        reason = (
            f"**TIME TRAPPED - No Clear Path**\n\n"
            f"Position: {position.symbol} ${strike:.0f} {position.option_type}\n"
            f"ITM: {itm_pct:.1f}%\n\n"
            f"**Analysis:**\n"
            f"- Compression breakeven: {compression_breakeven:.0f} weeks (too long)\n"
            f"- Take loss breakeven: {take_loss_breakeven:.0f} weeks (not attractive)\n"
            f"- Days remaining: {days_to_exp}\n\n"
            f"No optimal strategy. Wait and reassess weekly."
        )
        reason_short = f"Time trapped, no clear path - reassess weekly"

        return V4EvaluationResult(
            action='HOLD',
            position_id=str(position.id),
            symbol=position.symbol,
            reason=reason,
            reason_short=reason_short,
            philosophy_applied='patience',
            details={
                'category': 'TIME_TRAPPED',
                'compression_breakeven': compression_breakeven,
                'take_loss_breakeven': take_loss_breakeven,
            },
        )
```

---

## Part 4: Helper Functions Needed

```python
def _calculate_compression_cost(self, position, stock_price: float) -> float:
    """Calculate cost to compress from long-dated to weekly at same strike."""
    # Get long-dated premium (buyback cost)
    long_dated_premium = self._get_long_dated_premium(position)

    # Get weekly premium at same strike (sell price)
    weekly_premium = self._get_weekly_premium_at_strike(
        position.symbol,
        float(position.strike_price),
        position.option_type
    )

    # Compression cost = buy back - sell
    return (long_dated_premium - weekly_premium) * 100  # Per contract


def _estimate_weekly_income_at_strike(
    self,
    symbol: str,
    strike: float,
    stock_price: float,
    option_type: str
) -> float:
    """Estimate weekly roll credit at a given strike."""
    # This should use option chain data
    # For now, use IV-based estimation

    iv = self._get_implied_volatility(symbol)

    if option_type == 'call':
        itm_pct = max(0, (stock_price - strike) / stock_price * 100)
    else:
        itm_pct = max(0, (strike - stock_price) / stock_price * 100)

    # Base credit from IV
    if iv > 70:
        base_credit = 50
    elif iv > 50:
        base_credit = 35
    elif iv > 35:
        base_credit = 25
    else:
        base_credit = 15

    # Adjust for ITM depth
    if itm_pct > 25:
        multiplier = 0.4
    elif itm_pct > 15:
        multiplier = 0.6
    elif itm_pct > 10:
        multiplier = 0.8
    else:
        multiplier = 1.0

    return base_credit * multiplier


def _calculate_price_targets(self, position, stock_price: float) -> list:
    """Calculate price alert targets for TIME TRAPPED positions."""
    strike = float(position.strike_price)
    option_type = position.option_type

    targets = []

    if option_type == 'call':
        # For calls, want stock to DROP toward strike
        levels = [
            (strike * 1.10, "Reassess - 10% ITM"),
            (strike * 1.05, "Compress to weekly - 5% ITM"),
            (strike * 1.02, "Compress now - near ATM"),
            (strike, "Exit or roll for credit - ATM"),
        ]
        targets = [
            {"price": price, "action": action}
            for price, action in levels
            if price < stock_price
        ]
    else:
        # For puts, want stock to RISE toward strike
        levels = [
            (strike * 0.90, "Reassess - 10% ITM"),
            (strike * 0.95, "Compress to weekly - 5% ITM"),
            (strike * 0.98, "Compress now - near ATM"),
            (strike, "Exit or let expire - ATM"),
        ]
        targets = [
            {"price": price, "action": action}
            for price, action in levels
            if price > stock_price
        ]

    return targets


def _estimate_atm_weekly_income(self, symbol: str, stock_price: float) -> float:
    """Estimate weekly income if selling ATM options."""
    iv = self._get_implied_volatility(symbol)

    # ATM options have maximum time value
    if iv > 70:
        return 200  # High IV stocks
    elif iv > 50:
        return 150
    elif iv > 35:
        return 100
    else:
        return 60  # Low IV stocks
```

---

## Part 5: Updated Evaluate Method

Update the main `evaluate()` method in `v4_position_evaluator.py`:

```python
def evaluate(self, position, cost_basis=None, weekly_income=None):
    """Main V4 evaluation with stuck position handling."""

    # Get indicators
    indicators = self.ta_service.get_technical_indicators(position.symbol)
    if not indicators:
        return self._fallback_evaluation(position)

    stock_price = indicators.current_price

    # STEP 1: Categorize the position
    category = self.categorize_position(position, stock_price)

    # Calculate common metrics
    strike = float(position.strike_price)
    days_to_exp = (position.expiration_date - date.today()).days

    if position.option_type == 'call':
        itm_pct = max(0, (stock_price - strike) / stock_price * 100)
    else:
        itm_pct = max(0, (strike - stock_price) / stock_price * 100)

    # STEP 2: Route to appropriate handler
    if category == "SWIMMING":
        return self._handle_swimming(position, stock_price, days_to_exp)

    elif category == "SHALLOW_UNDERWATER":
        return self._handle_shallow_underwater(position, stock_price, itm_pct)

    elif category == "DEEP_UNDERWATER":
        weekly_credit = self._estimate_weekly_roll_credit(position, stock_price)
        return self._handle_deep_underwater(position, stock_price, itm_pct, weekly_credit)

    elif category == "LIFE_SUPPORT":
        # Weekly rolls = $0, but bi-weekly still generates credit
        biweekly_credit = self._estimate_biweekly_roll_credit(position, stock_price)
        return self._handle_life_support(position, stock_price, itm_pct, biweekly_credit)

    elif category == "DROWNING":
        # CRITICAL: ALL rolls are debits - must take loss
        return self._handle_drowning(position, stock_price, itm_pct)

    elif category == "TIME_TRAPPED":
        return self._handle_time_trapped(position, stock_price, itm_pct, days_to_exp)
```

---

## Part 6: New Notification Types

Add to notification service:

```python
# New action types for stuck positions
ACTION_DISPLAY_MAP = {
    'HOLD': 'Hold',
    'ROLL': 'Roll',
    'COMPRESS': 'Compress to Weekly',
    'CONSIDER_TAKE_LOSS': '⚠️ Consider Taking Loss',
    'TAKE_LOSS': '🛑 Take Loss',
    'WAIT': '⏳ Wait',
    'MIGRATE': 'Migrate Strike',
}

# New action types for stuck positions
ACTION_DISPLAY_MAP = {
    'HOLD': 'Hold',
    'ROLL': 'Roll Weekly',
    'ROLL_BIWEEKLY': 'Roll Bi-Weekly',
    'COMPRESS': 'Compress to Weekly',
    'CONSIDER_TAKE_LOSS': 'Consider Taking Loss',
    'TAKE_LOSS': 'Take Loss',
    'WAIT': 'Wait',
    'MIGRATE': 'Migrate Strike',
}

# Notification templates
STUCK_POSITION_TEMPLATES = {
    'DEEP_UNDERWATER': {
        'title': '{symbol} Deep Underwater ({itm_pct:.0f}% ITM)',
        'subtitle': 'Weekly roll: ${weekly_credit:.0f}/contract',
    },
    'LIFE_SUPPORT': {
        'title': '{symbol} Life Support ({itm_pct:.0f}% ITM)',
        'subtitle': 'Weekly=$0, bi-weekly=${biweekly_credit:.2f} - switch to bi-weekly rolls',
        'urgency': 'high',
    },
    'DROWNING': {
        'title': '🚨 {symbol} DROWNING ({itm_pct:.0f}% ITM)',
        'subtitle': 'ALL rolls = debit - TAKE LOSS to recover in {breakeven:.0f} weeks',
        'urgency': 'critical',
    },
    'TIME_TRAPPED': {
        'title': '{symbol} Time Trapped ({days_to_exp}d to expiry)',
        'subtitle': '{itm_pct:.0f}% ITM, compression breakeven {breakeven:.0f} weeks',
    },
}
```

---

## Part 7: Implementation Checklist

### Phase 1: Core Logic
- [ ] Add `POSITION_CATEGORIES` to `algorithm_config.py` (includes LIFE_SUPPORT)
- [ ] Add `STUCK_POSITION_CONFIG` thresholds
- [ ] Add `LIFE_SUPPORT_THRESHOLDS` by IV level
- [ ] Implement `get_life_support_thresholds()` function
- [ ] Implement `categorize_position()` function (with roll credit inputs)
- [ ] Implement `_handle_deep_underwater()` handler
- [ ] Implement `_handle_life_support()` handler (key insight!)
- [ ] Implement `_handle_drowning()` handler (all rolls = debit)
- [ ] Implement `_handle_time_trapped()` handler

### Phase 2: Helper Functions
- [ ] Implement `_calculate_compression_cost()`
- [ ] Implement `_estimate_weekly_roll_credit()`
- [ ] Implement `_estimate_biweekly_roll_credit()` (new!)
- [ ] Implement `_estimate_weekly_income_at_strike()`
- [ ] Implement `_calculate_price_targets()`
- [ ] Implement `_estimate_atm_weekly_income()`
- [ ] Implement `_get_implied_volatility()` (or use existing)

### Phase 3: Integration
- [ ] Update main `evaluate()` method to use categories
- [ ] Add LIFE_SUPPORT routing in evaluate method
- [ ] Add DROWNING routing in evaluate method
- [ ] Add new action types (`ROLL_BIWEEKLY`) to notification service
- [ ] Add LIFE_SUPPORT notification template
- [ ] Add DROWNING notification template (critical urgency)
- [ ] Update frontend to display new recommendation types
- [ ] Add price alert generation for WAIT/LIFE_SUPPORT recommendations

### Phase 4: Testing
- [ ] Test HOOD at 30% ITM (**LIFE SUPPORT** - weekly=$0, bi-weekly=$0.30)
- [ ] Test AVGO at 16.5% ITM (near-LIFE SUPPORT)
- [ ] Test HOOD at 26.8% ITM (DEEP UNDERWATER)
- [ ] Test AVGO at 15.8% ITM (DEEP UNDERWATER)
- [ ] Test with TSLA position (TIME TRAPPED)
- [ ] Test with MU position (TIME TRAPPED)
- [ ] Validate recommendations match framework
- [ ] Verify LIFE_SUPPORT vs DROWNING distinction works correctly

---

## Part 8: Future Enhancements

1. **Real-time option chain integration**: Get actual compression costs from API
2. **IV percentile tracking**: Store historical IV for better estimates
3. **Automated price alerts**: Create alerts when WAIT is recommended
4. **Migration analysis**: Add strike migration recommendations
5. **Portfolio-level view**: Show all stuck positions in one view
6. **Historical tracking**: Track escape outcomes for learning

---

**Document Status:** Ready for implementation review
