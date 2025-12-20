#!/usr/bin/env python3
"""
Test Telegram notification setup.

This script tests if your Telegram bot is configured correctly.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from pydantic_settings import BaseSettings

class EnvSettings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = EnvSettings()

def test_telegram():
    """Test Telegram notification."""
    import requests
    
    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env file")
        return False
    
    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID not set in .env file")
        return False
    
    print(f"📱 Testing Telegram notification...")
    print(f"   Bot Token: {bot_token[:10]}...")
    print(f"   Chat ID: {chat_id}")
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": "🎉 Test notification from your Estate Planner!\n\nIf you received this, your Telegram setup is working correctly."
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            print("✅ Telegram notification sent successfully!")
            print(f"   Message ID: {result.get('result', {}).get('message_id')}")
            return True
        else:
            print(f"❌ Telegram API error: {result.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Telegram notification: {e}")
        return False

if __name__ == '__main__':
    success = test_telegram()
    sys.exit(0 if success else 1)



