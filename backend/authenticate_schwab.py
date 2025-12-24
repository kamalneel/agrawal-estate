#!/usr/bin/env python3
"""
One-time Schwab API Authentication Script

Run this script to authenticate with Schwab:
    cd backend
    ./venv/bin/python authenticate_schwab.py

A browser will open for Schwab login. After login, the token will be saved.
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
from dotenv import load_dotenv
load_dotenv()

from schwab import auth

# Configuration
APP_KEY = os.getenv("SCHWAB_APP_KEY")
APP_SECRET = os.getenv("SCHWAB_APP_SECRET")
CALLBACK_URL = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")
TOKEN_FILE = Path(__file__).parent / "schwab_token.json"

if not APP_KEY or not APP_SECRET:
    print("ERROR: Missing Schwab credentials in .env file")
    print("Required: SCHWAB_APP_KEY and SCHWAB_APP_SECRET")
    sys.exit(1)

print("=" * 60)
print("SCHWAB API AUTHENTICATION")
print("=" * 60)
print(f"App Key: {APP_KEY[:15]}...")
print(f"Callback URL: {CALLBACK_URL}")
print(f"Token will be saved to: {TOKEN_FILE}")
print()
print("A browser window will open for Schwab login...")
print("1. Log in with your Schwab credentials")
print("2. You may see an SSL warning - click 'Advanced' and 'Proceed'")
print("3. After login, the browser will redirect and this script will capture the token")
print("=" * 60)
print()

try:
    client = auth.easy_client(
        APP_KEY,
        APP_SECRET,
        CALLBACK_URL,
        str(TOKEN_FILE)
    )
    
    print()
    print("=" * 60)
    print("✅ AUTHENTICATION SUCCESSFUL!")
    print(f"Token saved to: {TOKEN_FILE}")
    print()
    print("You can now use Schwab API for options data.")
    print("Restart the backend server to apply changes.")
    print("=" * 60)
    
except Exception as e:
    print()
    print("=" * 60)
    print(f"❌ AUTHENTICATION FAILED: {e}")
    print()
    print("Troubleshooting:")
    print("1. Make sure you're logged into schwab.com in your default browser")
    print("2. Check that your App Key and Secret are correct")
    print("3. Try again - sometimes OAuth can be flaky")
    print("=" * 60)
    sys.exit(1)

