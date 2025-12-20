#!/bin/bash
# Test script for recommendations API endpoint

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Testing Recommendations API..."

# Step 1: Get auth token
echo -e "\n${YELLOW}Step 1: Authenticating...${NC}"
TOKEN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"password":"Alishade@r"}')

TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}❌ Failed to get authentication token${NC}"
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✅ Authentication successful${NC}"

# Step 2: Test recommendations endpoint
echo -e "\n${YELLOW}Step 2: Testing recommendations endpoint...${NC}"
RESPONSE=$(curl -s "http://localhost:8000/api/v1/strategies/options-selling/recommendations?send_notification=true&notification_priority=high" \
  -H "Authorization: Bearer $TOKEN")

# Check if we got a valid response
if echo "$RESPONSE" | grep -q '"recommendations"'; then
  echo -e "${GREEN}✅ Recommendations endpoint working!${NC}"
  echo -e "\nResponse summary:"
  echo "$RESPONSE" | python3 -m json.tool | head -20
elif echo "$RESPONSE" | grep -q '"detail"'; then
  echo -e "${RED}❌ Error:${NC}"
  echo "$RESPONSE" | python3 -m json.tool
  echo -e "\n${YELLOW}💡 Tip: Make sure the server has been restarted to load the new route${NC}"
else
  echo -e "${RED}❌ Unexpected response:${NC}"
  echo "$RESPONSE"
fi



