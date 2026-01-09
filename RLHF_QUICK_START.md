# RLHF Quick Start: Test in 15 Minutes

## 🚀 **Fast Track to Testing Your RLHF System**

Skip the reading, just follow these steps to see your RLHF system in action.

---

## ✅ **Prerequisites**

- [ ] Backend server running
- [ ] Frontend server running
- [ ] You have at least 3-5 days of trading history (recommendations + executions)

---

## 📋 **15-Minute Test Plan**

### **Minute 1-2: Access the Dashboard**

1. Open browser: `http://localhost:3000/strategies/learning`
2. You should see the Learning Dashboard with 4 tabs
3. Verify it loads without errors

✅ **Success:** Dashboard appears with Overview, Matches, Weekly Summaries, V4 Candidates tabs

---

### **Minute 3-5: Run Initial Reconciliation**

1. Click **"Reconcile"** button (top right of Overview tab)
2. Select **"7 days"** from dropdown
3. Click **"Run Reconciliation"**
4. Wait ~10 seconds
5. Click **"Refresh"** icon

✅ **Success:** You see a loading spinner, then success message

---

### **Minute 6-8: View Your Matches**

1. Click **"Matches"** tab
2. You should see a list of recent recommendation-execution pairs
3. Look for these match types:
   - ✅ **CONSENT** (green) - You followed algorithm
   - ✏️ **MODIFY** (yellow) - You changed something
   - ❌ **REJECT** (red) - You ignored it
   - ⚡ **INDEPENDENT** (purple) - You traded without recommendation

✅ **Success:** You see at least 5-10 matches from past week

**Example match:**
```
✏️ MODIFIED - PLTR $180 Call
   Algorithm recommended: Roll to $185 Jan 17, $1.25
   You executed: Roll to $185 Jan 24, $1.50
   Differences: +7 days DTE, +$0.25 premium
```

---

### **Minute 9-11: Add Reasons for Divergence**

1. Find a **MODIFY** or **REJECT** match
2. Click **"Add Reason"** button
3. Select reason code from dropdown:
   - **premium_low** - Premium was too low
   - **timing** - Timing-related decision
   - **gut_feeling** - Intuition-based
   - **other** - Other reason
4. Add text explanation: "Wanted more premium for the risk"
5. Click **"Save"**
6. Click **"Mark Reviewed"**

✅ **Success:** Match shows your reason, "Reviewed" checkmark appears

---

### **Minute 12-13: Check Divergence Analytics**

1. Click **"Overview"** tab
2. Look at top statistics:
   - **Total Matches**: Should be 5-20
   - **Consent Rate**: 40-60% is normal for start
   - **Divergence Rate**: 40-60% is normal for start
3. Scroll down to see trend chart (if enough data)

✅ **Success:** You see your baseline divergence rate

**What the numbers mean:**
- **60% consent** = You agreed with algorithm 6/10 times (good start!)
- **40% divergence** = You modified or rejected 4/10 times (normal, will improve)

---

### **Minute 14: Generate Weekly Summary**

1. Click **"Weekly Summaries"** tab
2. Click **"Generate Summary"** button
3. Enter current year and week number (e.g., 2026, week 2)
4. Click **"Generate"**
5. Wait ~5 seconds

✅ **Success:** Weekly summary appears with:
- Match breakdown
- Patterns detected (maybe 1-2)
- V4 candidates (maybe 0-1)

---

### **Minute 15: Review V4 Candidates**

1. Click **"V4 Candidates"** tab
2. If you see any candidates:
   - Read the description
   - Check the evidence
   - For testing, just click **"Defer"** (need more data)
3. If no candidates: Normal! Need more data (2-3 weeks)

✅ **Success:** Tab loads, shows candidates or empty state

---

## 🎉 **Congratulations!**

If you completed all steps, your RLHF system is **working perfectly**!

---

## 📊 **What You Just Tested**

✅ **Frontend:** Learning Dashboard loads and displays data
✅ **Backend:** Reconciliation service matches recommendations → executions
✅ **Database:** Match records created and retrievable
✅ **Pattern Detection:** System analyzing your preferences
✅ **V4 Candidates:** Algorithm improvement proposals generated
✅ **User Workflow:** Adding reasons and marking reviewed

---

## 🎯 **Next Steps**

### **Option 1: Start Using Daily (Recommended)**

Follow the full daily plan:
1. Read `RLHF_DAILY_PLAN.md`
2. Start tomorrow morning:
   - Read Telegram notifications (6:30 AM)
   - Trade as normal (9 AM - 1 PM)
   - Add reasons for divergences (9:00 PM)
3. Review weekly summary next Saturday (9:00 AM)

### **Option 2: Test with Historical Data**

Run reconciliation for more days:
1. Click **"Reconcile"** → **"14 days"**
2. Wait for completion
3. Review matches and patterns
4. Generate weekly summaries for past weeks

### **Option 3: Simulate a Week**

Manually create some test scenarios:
1. Make a trade tomorrow
2. Wait for evening reconciliation (9 PM)
3. Add reasons in dashboard
4. See how system learns

---

## 🐛 **Troubleshooting**

### **Problem: "No matches found"**

**Possible causes:**
1. Reconciliation hasn't run yet
2. No recommendations in past 7 days
3. No executions in past 7 days

**Solutions:**
1. Check if you have data in both:
   - Recommendations: `/api/v1/strategies/recommendations`
   - Executions: `/api/v1/investments/transactions`
2. Try reconciling longer period: 14 or 30 days
3. Check scheduler logs to verify reconciliation ran

### **Problem: "All matches are 'reject'"**

**Possible causes:**
1. Matching algorithm too strict
2. Option symbols don't match exactly
3. Execution dates don't align

**Solutions:**
1. Check a few matches manually:
   - Did you actually execute something different?
   - Or is this a matching bug?
2. Look at modification details (should show differences)
3. If all are false rejections, may need to adjust matching thresholds

### **Problem: "No patterns detected"**

**This is normal!**
- Need at least 3-5 similar modifications to detect pattern
- Takes 2-3 weeks minimum
- Be patient, keep adding reasons

### **Problem: "Dashboard won't load"**

**Check:**
1. Is backend server running? `http://localhost:8000/docs`
2. Is frontend server running? `http://localhost:3000`
3. Are you logged in?
4. Check browser console for errors (F12)

---

## 📞 **Need Help?**

If stuck:
1. Check `RLHF_SYSTEM_GUIDE.md` for detailed documentation
2. Check `RLHF_DAILY_PLAN.md` for daily workflow
3. Run test script: `python3 backend/test_rlhf_system.py`
4. Check backend logs for errors

---

## 🎓 **Key Concepts**

### **Match Types:**
- **CONSENT:** You followed algorithm → System learns this was good
- **MODIFY:** You changed strike/DTE/premium → System learns your preferences
- **REJECT:** You ignored recommendation → System learns this was bad or poorly timed
- **INDEPENDENT:** You acted without recommendation → System learns about gaps

### **Divergence Rate:**
```
Divergence = (Modifications + Rejections) / Total Recommendations

Examples:
- 10 recommendations, 7 consent, 2 modify, 1 reject = 30% divergence (good!)
- 10 recommendations, 4 consent, 6 modify, 0 reject = 60% divergence (normal for start)
```

**Target:** <20% divergence after 6 months

### **Learning Cycle:**
```
Week 1: Collect data (just observe)
Week 2: Collect data (observe patterns)
Week 3: First patterns emerge
Week 4: First V4 candidates proposed
Week 5: Implement first candidate
Week 6+: Monitor if change improved consent rate
```

---

## 📈 **Expected Timeline**

| When | Divergence | What to Expect |
|------|------------|----------------|
| **Day 1** | 50-60% | Baseline established |
| **Week 2** | 45-55% | First patterns detected |
| **Month 1** | 40-50% | 1-2 V4 candidates implemented |
| **Month 3** | 30-40% | 5-8 V4 candidates implemented |
| **Month 6** | <20% | System mimics you successfully |

---

## ✅ **You're Ready!**

Your RLHF system is fully functional. Start using it daily and watch it learn your trading style over the next 3-6 months.

**Remember:** This is a marathon, not a sprint. The system needs time to collect data, detect patterns, and converge to your preferences. Be patient, be consistent, and provide rich feedback.

Happy trading! 🚀📈
