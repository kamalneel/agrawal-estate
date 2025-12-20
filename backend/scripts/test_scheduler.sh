#!/bin/bash

# Test script for the recommendation scheduler
# This script tests the manual trigger endpoint

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Testing Recommendation Scheduler${NC}"
echo "=================================="
echo ""

# Configuration
API_URL="http://localhost:8000"
ENDPOINT="/api/v1/strategies/recommendations/check-now"

# Check if password is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Password required${NC}"
    echo "Usage: $0 <password> [send_notifications=true]"
    echo ""
    echo "Example:"
    echo "  $0 mypassword              # Test with notifications enabled"
    echo "  $0 mypassword false        # Test without sending notifications"
    exit 1
fi

PASSWORD="$1"
SEND_NOTIFICATIONS="${2:-true}"

echo "Step 1: Authenticating..."
LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"password\": \"${PASSWORD}\"}")

# Extract token
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}✗ Authentication failed${NC}"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Authentication successful${NC}"
echo ""

echo "Step 2: Triggering manual recommendation check..."
echo "  - Send notifications: $SEND_NOTIFICATIONS"
echo ""

CHECK_RESPONSE=$(curl -s -X POST "${API_URL}${ENDPOINT}?send_notifications=${SEND_NOTIFICATIONS}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json")

# Pretty print response
echo "Response:"
echo "$CHECK_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CHECK_RESPONSE"
echo ""

# Check if successful
if echo "$CHECK_RESPONSE" | grep -q '"success":\s*true'; then
    echo -e "${GREEN}✓ Recommendation check triggered successfully${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Check PM2 logs: pm2 logs agrawal-backend"
    echo "  2. Check Telegram for notifications (if enabled)"
    echo "  3. Check the UI Notification tab for recommendations"
else
    echo -e "${RED}✗ Recommendation check failed${NC}"
    exit 1
fi



