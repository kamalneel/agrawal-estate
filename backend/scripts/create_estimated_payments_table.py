"""
Script to create the estimated_tax_payments table and seed initial data.

Run this script to create the table for tracking estimated tax payments
and insert the initial payment data.

Usage: python scripts/create_estimated_payments_table.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def create_table_and_seed_data():
    """Create the estimated_tax_payments table and insert seed data."""

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS estimated_tax_payments (
        id SERIAL PRIMARY KEY,
        tax_year INTEGER NOT NULL,
        payment_date DATE NOT NULL,
        payment_type VARCHAR(20) NOT NULL,
        state_code VARCHAR(2),
        amount DECIMAL(18,2) NOT NULL,
        quarter INTEGER,
        payment_method VARCHAR(50),
        confirmation_number VARCHAR(100),
        notes TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """

    create_indexes_sql = """
    CREATE INDEX IF NOT EXISTS idx_estimated_tax_year ON estimated_tax_payments(tax_year);
    CREATE INDEX IF NOT EXISTS idx_estimated_payment_date ON estimated_tax_payments(payment_date);
    CREATE INDEX IF NOT EXISTS idx_estimated_payment_type ON estimated_tax_payments(payment_type);
    """

    # Check if we already have data
    check_data_sql = "SELECT COUNT(*) FROM estimated_tax_payments WHERE tax_year = 2025;"

    # Seed data - Tax payments for 2025
    seed_data_sql = """
    INSERT INTO estimated_tax_payments (tax_year, payment_date, payment_type, state_code, amount, quarter, payment_method, notes, created_at, updated_at)
    VALUES
    (2025, '2025-10-15', 'federal', NULL, 12000.00, 3, 'IRS Direct Pay', 'Q3 estimated payment', NOW(), NOW()),
    (2025, '2026-01-14', 'federal', NULL, 25000.00, 4, 'IRS Direct Pay', 'Q4 estimated payment', NOW(), NOW()),
    (2025, '2026-01-14', 'state', 'CA', 10000.00, 4, 'CA FTB Web Pay', 'Q4 estimated payment', NOW(), NOW());
    """

    with engine.connect() as conn:
        # Create table
        print("Creating estimated_tax_payments table...")
        conn.execute(text(create_table_sql))
        conn.commit()
        print("Table created successfully.")

        # Create indexes
        print("Creating indexes...")
        conn.execute(text(create_indexes_sql))
        conn.commit()
        print("Indexes created successfully.")

        # Check if data already exists
        result = conn.execute(text(check_data_sql))
        count = result.scalar()

        if count == 0:
            print("Inserting seed data...")
            conn.execute(text(seed_data_sql))
            conn.commit()
            print("Seed data inserted successfully.")
            print("\nPayments added:")
            print("  - Oct 15, 2025: $12,000 to IRS (Q3)")
            print("  - Jan 14, 2026: $25,000 to IRS (Q4)")
            print("  - Jan 14, 2026: $10,000 to CA FTB (Q4)")
        else:
            print(f"Data already exists ({count} records for 2025). Skipping seed data.")

        print("\nDone!")

if __name__ == "__main__":
    create_table_and_seed_data()
