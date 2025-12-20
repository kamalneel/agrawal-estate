"""
Analyze dividend data discrepancy between Neel's Brokerage and Jaya's Brokerage.

This script examines the dividend transactions to identify why Jaya's smaller
brokerage account might have more dividend income than expected compared to Neel's larger account.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

# Connect to database
conn = psycopg2.connect(
    host="localhost",
    database="agrawal_estate",
    user="agrawal_user",
    password="agrawal_secure_2024",
    port=5432
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

def to_float(val):
    """Convert Decimal to float, handling None."""
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return val

print("=" * 80)
print("DIVIDEND DATA ANALYSIS: Neel's Brokerage vs Jaya's Brokerage")
print("=" * 80)

# 1. Get all investment accounts
print("\n1. ALL INVESTMENT ACCOUNTS")
print("-" * 60)
cursor.execute("""
    SELECT account_id, account_name, account_type, source, is_active
    FROM investment_accounts
    ORDER BY account_name
""")
accounts = cursor.fetchall()
for acc in accounts:
    print(f"  {acc['account_name']} ({acc['account_id']}) - Type: {acc['account_type']}, Source: {acc['source']}, Active: {acc['is_active']}")

# 2. Get dividend summary by account for 2025
print("\n2. DIVIDEND INCOME BY ACCOUNT - 2025")
print("-" * 60)
cursor.execute("""
    SELECT 
        ia.account_name,
        ia.account_id,
        COUNT(it.id) as transaction_count,
        SUM(it.amount) as total_dividends
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND EXTRACT(YEAR FROM it.transaction_date) = 2025
    GROUP BY ia.account_name, ia.account_id
    ORDER BY total_dividends DESC
""")
results = cursor.fetchall()
for row in results:
    total = to_float(row['total_dividends'])
    print(f"  {row['account_name']}: ${total:,.2f} ({row['transaction_count']} transactions)")

# 3. Get all dividends by year for brokerage accounts only
print("\n3. DIVIDEND INCOME BY YEAR (BROKERAGE ACCOUNTS ONLY)")
print("-" * 60)
cursor.execute("""
    SELECT 
        EXTRACT(YEAR FROM it.transaction_date)::int as year,
        ia.account_name,
        SUM(it.amount) as total_dividends
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND ia.account_type IN ('brokerage', 'individual')
    GROUP BY year, ia.account_name
    ORDER BY year DESC, ia.account_name
""")
results = cursor.fetchall()
year_totals = defaultdict(lambda: defaultdict(float))
for row in results:
    year_totals[row['year']][row['account_name']] = to_float(row['total_dividends'])

for year in sorted(year_totals.keys(), reverse=True):
    print(f"\n  {year}:")
    for account, total in sorted(year_totals[year].items(), key=lambda x: -x[1]):
        print(f"    {account}: ${total:,.2f}")

# 4. Compare holdings/portfolio values for context
print("\n4. CURRENT HOLDINGS BY ACCOUNT (Market Value)")
print("-" * 60)
cursor.execute("""
    SELECT 
        ia.account_name,
        ia.account_id,
        SUM(ih.market_value) as total_market_value,
        COUNT(ih.symbol) as num_positions
    FROM investment_holdings ih
    JOIN investment_accounts ia 
        ON ih.account_id = ia.account_id AND ih.source = ia.source
    WHERE ia.account_type IN ('brokerage', 'individual')
    GROUP BY ia.account_name, ia.account_id
    ORDER BY total_market_value DESC
""")
results = cursor.fetchall()
for row in results:
    mv = to_float(row['total_market_value'])
    print(f"  {row['account_name']}: ${mv:,.2f} ({row['num_positions']} positions)")

# 5. Dividend breakdown by symbol for 2025 - COMPARE BOTH ACCOUNTS
print("\n5. 2025 DIVIDENDS BY SYMBOL - COMPARISON")
print("-" * 60)

# Get Neel's dividends by symbol
cursor.execute("""
    SELECT 
        it.symbol,
        SUM(it.amount) as total_dividends,
        COUNT(*) as num_transactions
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND EXTRACT(YEAR FROM it.transaction_date) = 2025
        AND ia.account_name = 'Neel''s Brokerage'
    GROUP BY it.symbol
    ORDER BY total_dividends DESC
""")
neel_dividends = {row['symbol']: (to_float(row['total_dividends']), row['num_transactions']) for row in cursor.fetchall()}

# Get Jaya's dividends by symbol
cursor.execute("""
    SELECT 
        it.symbol,
        SUM(it.amount) as total_dividends,
        COUNT(*) as num_transactions
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND EXTRACT(YEAR FROM it.transaction_date) = 2025
        AND ia.account_name = 'Jaya''s Brokerage'
    GROUP BY it.symbol
    ORDER BY total_dividends DESC
""")
jaya_dividends = {row['symbol']: (to_float(row['total_dividends']), row['num_transactions']) for row in cursor.fetchall()}

all_symbols = set(neel_dividends.keys()) | set(jaya_dividends.keys())

print(f"\n  {'Symbol':<10} {'Neel Div':>12} {'Neel #':>8} {'Jaya Div':>12} {'Jaya #':>8}")
print(f"  {'-'*10} {'-'*12} {'-'*8} {'-'*12} {'-'*8}")

neel_total = 0
jaya_total = 0
for symbol in sorted(all_symbols, key=lambda s: -(neel_dividends.get(s, (0, 0))[0] + jaya_dividends.get(s, (0, 0))[0])):
    neel_div, neel_num = neel_dividends.get(symbol, (0, 0))
    jaya_div, jaya_num = jaya_dividends.get(symbol, (0, 0))
    neel_total += neel_div
    jaya_total += jaya_div
    print(f"  {symbol:<10} ${neel_div:>10,.2f} {neel_num:>8} ${jaya_div:>10,.2f} {jaya_num:>8}")

print(f"  {'-'*10} {'-'*12} {'-'*8} {'-'*12} {'-'*8}")
print(f"  {'TOTAL':<10} ${neel_total:>10,.2f} {'':<8} ${jaya_total:>10,.2f}")

# 6. Look at recent dividend transactions for both accounts
print("\n6. RECENT DIVIDEND TRANSACTIONS (2025)")
print("-" * 60)

cursor.execute("""
    SELECT 
        it.transaction_date,
        it.symbol,
        it.amount,
        ia.account_name,
        it.description
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND EXTRACT(YEAR FROM it.transaction_date) = 2025
        AND ia.account_name IN ('Neel''s Brokerage', 'Jaya''s Brokerage')
    ORDER BY it.transaction_date DESC, ia.account_name
    LIMIT 50
""")

print(f"  {'Date':<12} {'Account':<18} {'Symbol':<8} {'Amount':>10} Description")
print(f"  {'-'*12} {'-'*18} {'-'*8} {'-'*10} {'-'*30}")
for row in cursor.fetchall():
    desc = row['description'][:30] if row['description'] else ''
    amt = to_float(row['amount'])
    date_str = str(row['transaction_date'])
    print(f"  {date_str:<12} {row['account_name']:<18} {row['symbol']:<8} ${amt:>9,.2f} {desc}")

# 7. Check for potential data issues - duplicates or missing data
print("\n7. CHECKING FOR POTENTIAL DATA ISSUES")
print("-" * 60)

# Check for duplicates
cursor.execute("""
    SELECT 
        it.transaction_date,
        it.symbol,
        it.amount,
        ia.account_name,
        COUNT(*) as duplicate_count
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND EXTRACT(YEAR FROM it.transaction_date) = 2025
        AND ia.account_name IN ('Neel''s Brokerage', 'Jaya''s Brokerage')
    GROUP BY it.transaction_date, it.symbol, it.amount, ia.account_name
    HAVING COUNT(*) > 1
""")
duplicates = cursor.fetchall()
if duplicates:
    print("  DUPLICATE ENTRIES FOUND:")
    for row in duplicates:
        amt = to_float(row['amount'])
        print(f"    {row['transaction_date']} {row['account_name']} {row['symbol']} ${amt:.2f} x{row['duplicate_count']}")
else:
    print("  No duplicate dividend entries found.")

# 8. Holdings that pay dividends - check holdings vs dividend-paying stocks
print("\n8. CURRENT DIVIDEND-PAYING HOLDINGS VS ACTUAL DIVIDENDS RECEIVED")
print("-" * 60)

# Get current holdings for both accounts
cursor.execute("""
    SELECT 
        ia.account_name,
        ih.symbol,
        ih.quantity,
        ih.market_value,
        ih.description
    FROM investment_holdings ih
    JOIN investment_accounts ia 
        ON ih.account_id = ia.account_id AND ih.source = ia.source
    WHERE ia.account_name IN ('Neel''s Brokerage', 'Jaya''s Brokerage')
    ORDER BY ia.account_name, ih.market_value DESC
""")

holdings = defaultdict(list)
for row in cursor.fetchall():
    holdings[row['account_name']].append({
        'symbol': row['symbol'],
        'quantity': to_float(row['quantity']),
        'market_value': to_float(row['market_value']),
        'description': row['description']
    })

for account_name, account_holdings in holdings.items():
    print(f"\n  {account_name}:")
    total_mv = sum(h['market_value'] for h in account_holdings)
    print(f"    Total Market Value: ${total_mv:,.2f}")
    print(f"\n    {'Symbol':<8} {'Qty':>8} {'Mkt Value':>12} {'2025 Divs':>12}")
    print(f"    {'-'*8} {'-'*8} {'-'*12} {'-'*12}")
    
    divs = neel_dividends if "Neel" in account_name else jaya_dividends
    for h in account_holdings[:15]:  # Top 15 positions
        div_amt = divs.get(h['symbol'], (0, 0))[0]
        print(f"    {h['symbol']:<8} {h['quantity']:>8,.0f} ${h['market_value']:>10,.2f} ${div_amt:>10,.2f}")

# 9. Historical comparison
print("\n9. HISTORICAL DIVIDEND COMPARISON (ALL YEARS)")
print("-" * 60)

cursor.execute("""
    SELECT 
        EXTRACT(YEAR FROM it.transaction_date)::int as year,
        SUM(CASE WHEN ia.account_name = 'Neel''s Brokerage' THEN it.amount ELSE 0 END) as neel_dividends,
        SUM(CASE WHEN ia.account_name = 'Jaya''s Brokerage' THEN it.amount ELSE 0 END) as jaya_dividends
    FROM investment_transactions it
    JOIN investment_accounts ia 
        ON it.account_id = ia.account_id AND it.source = ia.source
    WHERE it.transaction_type IN ('DIVIDEND', 'CDIV', 'QUAL DIV REINVEST', 'REINVEST DIVIDEND', 'CASH DIVIDEND', 'QUALIFIED DIVIDEND')
        AND ia.account_name IN ('Neel''s Brokerage', 'Jaya''s Brokerage')
    GROUP BY year
    ORDER BY year
""")

print(f"  {'Year':<8} {'Neel Dividends':>15} {'Jaya Dividends':>15} {'Ratio (N/J)':>12}")
print(f"  {'-'*8} {'-'*15} {'-'*15} {'-'*12}")
for row in cursor.fetchall():
    neel = to_float(row['neel_dividends'])
    jaya = to_float(row['jaya_dividends'])
    ratio = neel / jaya if jaya > 0 else float('inf')
    print(f"  {row['year']:<8} ${neel:>13,.2f} ${jaya:>13,.2f} {ratio:>11.2f}x")

# 10. Check transaction types that might be dividends but not captured
print("\n10. ALL TRANSACTION TYPES IN THE DATABASE")
print("-" * 60)
cursor.execute("""
    SELECT 
        transaction_type,
        COUNT(*) as count,
        SUM(amount) as total
    FROM investment_transactions
    GROUP BY transaction_type
    ORDER BY count DESC
""")
for row in cursor.fetchall():
    total = to_float(row['total'])
    print(f"  {row['transaction_type']:<20} Count: {row['count']:>6}  Total: ${total:>12,.2f}")

conn.close()

print("\n" + "=" * 80)
print("END OF ANALYSIS")
print("=" * 80)
