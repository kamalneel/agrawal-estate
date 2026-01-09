# RLHF Daily Plan: "Human in the Loop" Responsibilities

## 🎯 **Your Role in the Learning Loop**

The RLHF system learns by **observing your decisions**, but you have specific responsibilities to make it work effectively. Think of yourself as the teacher - the algorithm is your student.

---

## 📅 **Daily Schedule**

### **6:00 AM - 6:30 AM PT (Algorithm Scan)**

**What Happens Automatically:**
- V3 scanner runs full technical analysis
- Generates recommendations for all positions
- Sends Telegram notifications (both verbose and smart modes)

**Your Responsibility:**
⏰ **NONE** - Just wake up to notifications waiting for you

---

### **6:30 AM - 9:00 AM PT (Morning Review)**

**What You Should Do:**

#### **Step 1: Read Telegram Notifications (5 minutes)**

Open Telegram and review notifications. You'll see messages like:

```
📊 MORNING SCAN (6:00 AM)

🔄 ROLL RECOMMENDATIONS (3)

1. PLTR $180 Jan 10 Call → $185 Jan 17
   Premium: $1.25 | Net: +$0.45 credit
   Reason: Weekly roll (63% profit)
   Priority: HIGH

2. NVDA $850 Jan 10 Call → $860 Jan 17
   Premium: $2.10 | Net: +$0.80 credit
   Reason: Weekly roll (71% profit)
   Priority: HIGH

3. AAPL $230 Jan 15 Put → $225 Jan 22
   Premium: $0.85 | Net: -$0.30 debit
   Reason: Escape ITM (2.1% ITM, 5 DTE)
   Priority: URGENT
```

#### **Step 2: Form Your Own Opinion (5 minutes)**

For each recommendation, ask yourself:
- ✅ Do I agree with this action?
- ✅ Do I want to modify it? (different strike, expiration, premium)
- ✅ Do I want to reject it? (do nothing or do something completely different)

**Important:** Don't force yourself to agree! The system learns from your natural decisions.

#### **Step 3: Note Mental Reasons (2 minutes)**

If you plan to diverge, mentally note why:
- "Premium too low for the risk"
- "Want to go further out for more premium"
- "Stock is oversold, expect bounce"
- "Don't like rolling on Mondays"
- "Earnings next week, too risky"

You'll log these later in the Learning Dashboard.

---

### **9:00 AM - 1:00 PM PT (Trading Window)**

**What You Should Do:**

#### **Execute Your Actual Trades**

Make your trading decisions based on:
- Algorithm recommendations (as a starting point)
- Your own analysis and judgment
- Current market conditions
- Your risk tolerance

**Examples of Typical Actions:**

**Scenario 1: Full Consent**
```
Algorithm says: Roll PLTR $180 → $185 Jan 17, $1.25 premium
You execute: EXACTLY that
Result: CONSENT (system learns this was a good recommendation)
```

**Scenario 2: Modification**
```
Algorithm says: Roll NVDA $850 → $860 Jan 17, $2.10 premium
You execute: Roll NVDA $850 → $860 Jan 24, $2.45 premium (7 days later)
Reason: "Want more premium, willing to hold longer"
Result: MODIFY (system learns you prefer longer DTE)
```

**Scenario 3: Rejection**
```
Algorithm says: Roll AAPL $230 → $225 Jan 22, $0.85 premium
You execute: NOTHING (you decide to wait)
Reason: "Premium too low, stock oversold, expecting bounce"
Result: REJECT (system learns about your premium thresholds)
```

**Scenario 4: Independent Action**
```
Algorithm says: NOTHING (no recommendation for TSLA)
You execute: Sell new TSLA $250 call for $3.50 (opportunity you spotted)
Result: INDEPENDENT (system learns you're proactive)
```

---

### **1:00 PM - 8:00 PM PT (Afternoon - No Action)**

**What Happens Automatically:**
- 8 AM scan (if urgent changes)
- 12 PM midday scan
- 12:45 PM pre-close scan

**Your Responsibility:**
⏰ **NONE** - System continues monitoring, you can ignore during work hours

---

### **8:00 PM - 9:00 PM PT (Evening - Optional Review)**

**What Happens Automatically:**
- Evening planning scan runs
- Sends informational notifications for tomorrow

**Your Responsibility (OPTIONAL):**

#### **Option A: Quick Check (2 minutes)**
Just read Telegram notification to know what's coming tomorrow:
```
📊 EVENING PLANNING (8:00 PM)

TOMORROW (Friday Jan 10):
├─ Earnings: PLTR (before market)
├─ Expiring: 3 positions
└─ Ex-Dividend: None
```

#### **Option B: Review in Dashboard (5 minutes)**
If you want more detail:
1. Go to `/notifications` or `/strategies/options-selling`
2. Review tomorrow's positions
3. Mental note of any positions to watch

---

### **9:00 PM - 9:30 PM PT (Daily Reconciliation - CRITICAL)**

**What Happens Automatically:**
- System matches today's recommendations to your actual executions
- Creates Match records (consent/modify/reject/independent)
- Calculates modification details (strike diff, DTE diff, premium diff)

**Your Responsibility: ADD REASONS FOR DIVERGENCE (10 minutes)**

This is the **most important** human-in-the-loop task!

#### **Step 1: Open Learning Dashboard**
```
http://localhost:3000/strategies/learning
```

#### **Step 2: Click "Matches" Tab**

You'll see today's matches:

```
TODAY'S MATCHES (3)

✏️ MODIFIED - NVDA $850 Call
   Recommended: Roll to $860 Jan 17, $2.10
   You executed: Roll to $860 Jan 24, $2.45
   Differences: +7 days, +$0.35 premium
   [Add Reason] [Mark Reviewed]

❌ REJECTED - AAPL $230 Put
   Recommended: Roll to $225 Jan 22, $0.85
   You executed: Nothing
   [Add Reason] [Mark Reviewed]

✅ CONSENT - PLTR $180 Call
   Recommended: Roll to $185 Jan 17, $1.25
   You executed: Exactly as recommended
   [Mark Reviewed]
```

#### **Step 3: Add Reasons for Each Divergence**

Click **"Add Reason"** on MODIFIED and REJECTED matches:

**For NVDA (Modified):**
```
Reason Code: [Select: premium_low]
Reason Text: "Wanted more premium ($2.45 vs $2.10). Willing to
              hold 7 extra days for additional $0.35. Stock is
              strong, expect it to stay OTM."
```

**For AAPL (Rejected):**
```
Reason Code: [Select: premium_low]
Reason Text: "Premium only $0.85 for a roll. Stock is oversold
              (RSI 28), expecting bounce next week. Better to wait
              and see if it bounces before rolling."
```

#### **Step 4: Mark All as Reviewed**

Click **"Mark Reviewed"** on each match, or **"Mark All as Reviewed"** button.

**Why This Matters:**
- ✅ Helps pattern detection find systematic preferences
- ✅ Creates rich context for future learning
- ✅ Helps you reflect on your decisions
- ✅ Builds a decision journal over time

---

## 📅 **Weekly Schedule (Saturday)**

### **9:00 AM PT - Weekly Learning Summary**

**What Happens Automatically:**
- System generates weekly summary
- Detects patterns in your behavior
- Generates V4 algorithm improvement candidates
- Sends Telegram notification

**Your Responsibility: REVIEW & DECIDE (20-30 minutes)**

#### **Step 1: Read Telegram Summary (2 minutes)**

```
📊 WEEKLY LEARNING SUMMARY (2026-W02)

RECOMMENDATIONS: 15
├─ ✅ Consent: 9 (60%)
├─ ✏️ Modified: 4 (27%)
├─ ❌ Rejected: 2 (13%)
└─ 🆕 Independent: 0 (0%)

DIVERGENCE RATE: 40% (down from 45% last week ✓)

P&L THIS WEEK: $450.00

PATTERNS DETECTED: 2
• User adds 7 days to DTE on average (5 occurrences)
• User rejects recommendations with premium <$0.30 (2 occurrences)

V4 CANDIDATES: 2
• Increase default DTE by 7 days (HIGH priority)
• Add minimum premium filter $0.30 (MEDIUM priority)

Review in Learning Dashboard for full details.
```

#### **Step 2: Open Learning Dashboard → Weekly Summaries Tab (5 minutes)**

Click on latest week (e.g., "2026-W02")

Review detailed breakdown:
- Total recommendations by type
- Match breakdown chart (pie chart showing consent/modify/reject)
- P&L comparison (you vs algorithm)
- Full pattern details

#### **Step 3: Review Patterns (5 minutes)**

For each pattern, ask:
- ✅ Is this actually my preference? (verify it's real)
- ✅ Do I want to keep doing this? (validate it's beneficial)
- ✅ Is this consistent across symbols? (check if it's universal or symbol-specific)

**Example Review:**

```
PATTERN: "User adds 7 days to DTE on average"

Your analysis:
✅ Yes, I do prefer longer DTE (gives more time for stock to move)
✅ I get better premiums with weekly rolls 7 days out
✅ This applies to all symbols except NVDA (I prefer 3 days for NVDA)

Decision: VALID - but need symbol-specific handling for NVDA
```

#### **Step 4: Review V4 Candidates (10 minutes)**

Click **"V4 Candidates"** tab

For each candidate:

**Candidate 1: Increase default DTE by 7 days**
```
Description: Adjust default DTE from 14 to 21 days
Evidence: User modified DTE in 5/8 recommendations this week
Priority: HIGH
Risk: May reduce premium capture per roll, but get better premiums overall

Your Decision Options:
[Implement] [Defer] [Reject]

Your Analysis:
✅ Evidence is strong (5 out of 8 times)
✅ I consciously prefer this
✅ Low risk (can always roll sooner if needed)

Decision: IMPLEMENT ✓
Reason: "This matches my preference for weekly rolls 7 days out.
         Better premiums and more flexibility."
```

**Candidate 2: Add minimum premium filter $0.30**
```
Description: Don't recommend rolls with premium <$0.30
Evidence: User rejected 2 low-premium recommendations
Priority: MEDIUM
Risk: May miss some opportunities, but avoids noise

Your Decision Options:
[Implement] [Defer] [Reject]

Your Analysis:
⚠️ Only 2 occurrences (small sample)
⚠️ Sometimes I do take low premium for risk reduction
✅ But generally prefer higher premiums

Decision: DEFER ✓
Reason: "Need more data. Want to see if this pattern holds over
         2-3 more weeks. Sometimes I take low premium if I'm
         worried about assignment risk."
```

#### **Step 5: Click "Implement" on Approved Candidates**

System will:
- Mark candidate as "implement"
- Notify you when it's deployed (manual code change needed currently)
- Track validation metrics (did it improve consent rate?)

#### **Step 6: Mark Summary as Reviewed**

Click **"Mark as Reviewed"** button

Add review notes:
```
"Week 2 - Good progress. Divergence down to 40% from 45%.
Implemented DTE adjustment. Deferred premium filter pending more data."
```

---

## 📊 **Monthly Review (First Saturday of Month)**

**What You Should Do: ANALYZE TRENDS (30 minutes)**

### **Step 1: Review Divergence Trend (5 minutes)**

Go to **Overview** tab → Look at "Divergence Rate Over Time" chart

Track month-over-month:
```
Month 1: 50% → 47% → 44% → 40% (declining ✓)
Month 2: 40% → 38% → 35% → 33% (declining ✓)
Month 3: 33% → 30% → 28% → 25% (declining ✓)
```

**Questions to ask:**
- ✅ Is divergence decreasing? (good!)
- ❌ Is divergence increasing? (investigate why)
- ⚠️ Is divergence flat? (may need more aggressive V4 implementations)

### **Step 2: Review Implemented V4 Candidates (10 minutes)**

Go to **V4 Candidates** tab → Filter by "implemented"

For each implemented candidate:
- ✅ Did consent rate improve after implementation?
- ✅ Did divergence rate decrease?
- ❌ Did it make things worse?

**Example Validation:**

```
V4 Candidate: "Increase default DTE by 7 days"
Implemented: Week 2 (Jan 11)

Results:
Before (Weeks 1-2):
  - DTE modifications: 10/15 (67%)
  - Divergence rate: 45%

After (Weeks 3-6):
  - DTE modifications: 3/25 (12%)
  - Divergence rate: 32%

Validation: SUCCESS ✓
Keep this change, it reduced DTE modifications by 55%
```

**If a candidate made things WORSE:**
```
V4 Candidate: "Add minimum premium filter $0.50"
Implemented: Week 5

Results:
Before: Divergence 32%
After: Divergence 38% (worse!)

Why? Algorithm started missing legitimate opportunities.
I was rejecting its "no recommendation" and trading independently.

Validation: FAILURE ✗
Action: ROLLBACK this change
```

### **Step 3: Set Goals for Next Month (5 minutes)**

```
Current State:
- Divergence: 33%
- Consent: 67%
- Top modification: Strike selection (still adjusting strikes)

Goals for Next Month:
1. Get divergence below 30%
2. Implement 2-3 more V4 candidates
3. Focus on strike selection pattern (need more data)

Action Items:
- Be more diligent about adding reasons for strike modifications
- Look for symbol-specific patterns (maybe NVDA vs AAPL different)
- Consider implementing strike adjustment if pattern emerges
```

---

## 📋 **Quick Reference: Daily Checklist**

### **Every Day**
- [ ] 6:30 AM: Read Telegram notifications (5 min)
- [ ] 9 AM - 1 PM: Execute trades based on your judgment (30-60 min)
- [ ] 9:00 PM: Add reasons for divergences in Learning Dashboard (10 min)
- [ ] 9:05 PM: Mark matches as reviewed (1 min)

**Total daily time: ~15-20 minutes** (excluding actual trading)

### **Every Saturday**
- [ ] 9:00 AM: Read weekly Telegram summary (2 min)
- [ ] 9:05 AM: Review detailed summary in dashboard (5 min)
- [ ] 9:10 AM: Review patterns (5 min)
- [ ] 9:15 AM: Review and decide on V4 candidates (10 min)
- [ ] 9:25 AM: Mark summary as reviewed (2 min)

**Total weekly time: ~25-30 minutes**

### **First Saturday of Month**
- [ ] Do all weekly tasks above
- [ ] Review divergence trend (5 min)
- [ ] Validate implemented V4 candidates (10 min)
- [ ] Set goals for next month (5 min)

**Total monthly time: ~45-50 minutes**

---

## 🎯 **Key Principles for Human-in-the-Loop**

### **1. Trade Naturally**
❌ DON'T: Force yourself to agree with algorithm
❌ DON'T: Override your judgment to "help" the system learn
✅ DO: Make the decision you would normally make
✅ DO: Trust your instincts and experience

**Why:** System learns from your ACTUAL preferences, not what you think it wants to hear.

### **2. Provide Rich Context**
❌ DON'T: Just click "reject" without explanation
❌ DON'T: Use generic reasons like "didn't like it"
✅ DO: Add specific reasons: "Premium too low", "Stock oversold", "Earnings risk"
✅ DO: Add numerical context: "Wanted $2.50+, only got $2.10 offer"

**Why:** Better context → Better pattern detection → Faster convergence

### **3. Be Consistent**
❌ DON'T: Modify DTE randomly (sometimes +3 days, sometimes +14 days)
❌ DON'T: Change your strategy week-to-week
✅ DO: Apply consistent rules: "I always prefer 7 days for weekly rolls"
✅ DO: Have consistent thresholds: "I never roll for <$0.30 premium"

**Why:** Consistent behavior → Clear patterns → Easier for algorithm to learn

### **4. Review Regularly**
❌ DON'T: Skip weekly summaries
❌ DON'NOT: Batch review matches monthly
✅ DO: Add reasons daily (while trades are fresh in memory)
✅ DO: Review summaries every Saturday morning

**Why:** Regular feedback → Faster learning → Better convergence

### **5. Make Decisions Thoughtfully**
❌ DON'T: Auto-approve all V4 candidates
❌ DON'T: Reject candidates without understanding them
✅ DO: Analyze evidence carefully
✅ DO: Defer if uncertain (need more data)
✅ DO: Validate after implementation

**Why:** Quality decisions → Better algorithm → Higher consent rate

---

## 🧪 **Testing Plan: First 2 Weeks**

### **Week 0: Setup & Initialization (Pre-Testing)**

**Monday:**
1. Start your backend server
2. Start your frontend server
3. Visit `/strategies/learning` - verify it loads
4. Run test script: `python3 test_rlhf_system.py`
5. Click "Reconcile" → 7 days (populate historical data)

**Tuesday-Friday:**
Just trade normally, don't worry about RLHF

**Saturday:**
Check if weekly summary was generated
- If yes: Great! System is working
- If no: Check scheduler logs, may need to manually trigger

### **Week 1: Active Learning Phase**

**Daily (Monday-Friday):**
1. Read morning Telegram notifications
2. Execute trades as you normally would
3. **9:00 PM: Log into Learning Dashboard**
   - Go to Matches tab
   - Add reasons for ANY divergences
   - Mark all as reviewed
4. Track time spent: Should be ~10 minutes

**Saturday:**
1. **9:00 AM: Review weekly summary**
   - Read Telegram notification
   - Open Learning Dashboard → Weekly Summaries tab
   - Click latest week
2. **Review patterns** (even if only 1-2 patterns)
3. **Review V4 candidates** (may not have any yet - need more data)
4. **Mark summary as reviewed**
5. **Add notes**: "Week 1 - baseline data collection"

**Expected Results After Week 1:**
- 5-10 matches collected
- 1-2 patterns detected (if any clear preferences)
- 0-1 V4 candidates (probably too early)
- Divergence rate: 40-60% (baseline)

### **Week 2: Refinement Phase**

**Daily (Monday-Friday):**
Same as Week 1, but:
1. **Be more detailed in reasons**
   - Add specific numbers: "Wanted $2.50, only $2.10 offered"
   - Add context: "Stock RSI 28, expecting bounce"
2. **Note if you're being consistent**
   - "This is the 3rd time I've added 7 days"
   - "Again rejected low premium (<$0.30)"

**Saturday:**
1. Review weekly summary (should have more patterns now)
2. **Compare Week 1 vs Week 2:**
   - Is divergence rate changing?
   - Are same patterns appearing?
   - Any new patterns?
3. **Decide on first V4 candidate** (if any)
   - If pattern is strong (3+ occurrences), consider implementing
   - If pattern is weak (1-2 occurrences), defer
4. **Add notes**: "Week 2 - pattern X confirmed, considering V4 candidate Y"

**Expected Results After Week 2:**
- 10-20 total matches
- 2-4 clear patterns
- 1-2 V4 candidates ready for decision
- Divergence rate: Should be similar to Week 1 (system hasn't adapted yet)

---

## 📈 **Success Criteria**

### **After Week 2 (Baseline Established)**
✅ At least 10 matches collected
✅ At least 2 patterns detected
✅ You've added reasons for 80%+ of divergences
✅ Weekly summary generated successfully
✅ You understand the workflow

### **After Month 1 (Early Learning)**
✅ At least 40 matches collected
✅ 3-5 clear patterns emerged
✅ 1-2 V4 candidates implemented
✅ Divergence rate measured (baseline)
✅ You're comfortable with daily workflow (<10 min/day)

### **After Month 3 (Convergence Starting)**
✅ At least 120 matches collected
✅ 10-15 patterns tracked
✅ 5-8 V4 candidates implemented
✅ Divergence rate decreased by 10-15% from baseline
✅ Consent rate increased
✅ You're seeing fewer modifications needed

### **After Month 6 (System Converged)**
✅ At least 240 matches collected
✅ 15-20 patterns tracked
✅ 10-15 V4 candidates implemented
✅ Divergence rate <20% (target achieved)
✅ Consent rate >80%
✅ Weekly review time <10 minutes

---

## ⚠️ **Common Mistakes to Avoid**

### **1. Forcing Agreement**
❌ **Wrong:** "Algorithm says roll, so I'll roll even though I don't want to"
✅ **Right:** "Algorithm says roll, but I think premium is too low. I'll wait and mark it as rejected with reason."

### **2. Ignoring Reasons**
❌ **Wrong:** Just clicking "reject" without adding reason
✅ **Right:** "Rejected because premium $0.25 < my $0.30 threshold"

### **3. Inconsistent Behavior**
❌ **Wrong:** Monday you add 7 days, Tuesday you subtract 3 days, Wednesday you add 14 days
✅ **Right:** Consistently add 7 days for weekly rolls (system can learn this pattern)

### **4. Skipping Weekly Reviews**
❌ **Wrong:** "I'll catch up on summaries next month"
✅ **Right:** Review every Saturday while it's fresh

### **5. Auto-Approving V4 Candidates**
❌ **Wrong:** "Approve all" without reading
✅ **Right:** Analyze each candidate, defer if uncertain

### **6. Not Validating Changes**
❌ **Wrong:** Implement V4 candidate and forget about it
✅ **Right:** Check next month if it actually improved consent rate

### **7. Giving Up Too Early**
❌ **Wrong:** "Week 3 and still 45% divergence, system doesn't work"
✅ **Right:** "Week 3, divergence is 45%, need 3-6 months to converge, staying patient"

---

## 🎓 **Learning Mindset**

Think of this as **teaching a new trader** your strategy:

**Week 1-2:** Student shadows you, takes notes
**Week 3-4:** Student starts asking "why did you do that?"
**Month 2:** Student proposes improvements: "You always do X, should I make that a rule?"
**Month 3:** Student starts getting it right more often
**Month 6:** Student trades like you 80% of the time

**Your role:** Patient teacher who provides clear, consistent feedback

---

## 📞 **When to Escalate to LLMs**

Only consider LLM integration if after **6 months**:

❌ Divergence still >30%
❌ Patterns are highly context-dependent:
   - "I roll when VIX > 20 but not when VIX < 15"
   - "I adjust based on whether Fed meeting is this week"
   - "I modify based on overall market sentiment"
❌ You have 500+ labeled examples
❌ Rule-based patterns aren't capturing your logic

If most divergences are simple (DTE, strike, premium thresholds), **rule-based RLHF is sufficient**.

---

## 🎯 **Your Commitment**

To make RLHF work, commit to:

✅ **Daily:** 10-15 minutes adding reasons and marking reviewed
✅ **Weekly:** 20-30 minutes reviewing summary and deciding on V4 candidates
✅ **Monthly:** 30 minutes validating changes and setting goals
✅ **Total:** ~2-3 hours per month for 6 months

**Return on Investment:**
- Month 1-3: Time investment > time saved (you're training)
- Month 4-6: Time investment ≈ time saved (breaking even)
- Month 7+: Time investment < time saved (algorithm does 80% of your thinking)

**Final goal:** Algorithm makes recommendations you agree with 80%+ of the time, saving you decision fatigue and mental energy while maintaining your strategy's performance.

---

Ready to start testing? Let's begin with Week 0 setup! 🚀
