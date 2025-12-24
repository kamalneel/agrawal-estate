#!/usr/bin/env python3
"""Test the notification organizer"""
import sys
sys.path.insert(0, '/Users/neelpersonal/agrawal-estate-planner/backend')

from app.shared.services.notification_organizer import organize_and_format, estimate_premium

# Create sample recommendations
recommendations = [
    {
        'type': 'sell_unsold_contracts',
        'account_name': "Neel's Brokerage",
        'priority': 'high',
        'context': {
            'symbol': 'IBIT',
            'strike_price': 53,
            'current_price': 51,
            'unsold_contracts': 15,
            'weekly_income': 338,
            'option_type': 'call'
        }
    },
    {
        'type': 'sell_unsold_contracts',
        'account_name': "Neel's Brokerage",
        'priority': 'high',
        'context': {
            'symbol': 'NVDA',
            'strike_price': 195,
            'current_price': 183,
            'unsold_contracts': 1,
            'weekly_income': 220,
            'option_type': 'call'
        }
    },
    {
        'type': 'sell_unsold_contracts',
        'account_name': "Neel's Brokerage",
        'priority': 'high',
        'context': {
            'symbol': 'MSFT',
            'strike_price': 509,
            'current_price': 484,
            'unsold_contracts': 1,
            'weekly_income': 180,
            'option_type': 'call'
        }
    },
    {
        'type': 'sell_unsold_contracts',
        'account_name': "Jaya's Brokerage",
        'priority': 'high',
        'context': {
            'symbol': 'NVDA',
            'strike_price': 195,
            'current_price': 183,
            'unsold_contracts': 1,
            'weekly_income': 220,
            'option_type': 'call'
        }
    },
    {
        'type': 'roll_options',
        'account_name': "Jaya's Retirement",
        'priority': 'high',
        'context': {
            'symbol': 'AVGO',
            'old_strike': 362.5,
            'new_strike': 350,
            'current_price': 340,
            'current_expiration': '2024-12-26',
            'new_expiration': '2025-01-02',
            'contracts': 2,
            'option_type': 'put'
        }
    }
]

print('=== FORMATTED MESSAGE ===')
result = organize_and_format(recommendations)
print(result)
print()
print('=== TESTING PREMIUM ESTIMATION ===')
p1 = estimate_premium('NVDA', 195, 183, 1, None)  # OTM 6.5%
print(f'NVDA $195 (Stock $183): ${p1:.2f} estimated')
p2 = estimate_premium('NVDA', 195, 183, 1, 220)  # With known weekly income
print(f'NVDA with known income: ${p2:.2f}')
print()
print('=== TEST COMPLETE ===')

