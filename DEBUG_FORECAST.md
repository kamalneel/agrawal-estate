# Debugging 2025 Tax Forecast

## Steps to See the Forecast

1. **Restart the Backend Server**
   - The backend needs to be restarted to load the new forecast code
   - If using PM2: `pm2 restart estate-planner` or `pm2 restart all`
   - If running directly: Stop and restart the Python server

2. **Restart the Frontend (if needed)**
   - The frontend should hot-reload, but if changes don't appear, restart it
   - Usually: `npm run dev` in the frontend directory

3. **Check Backend Logs**
   - Look for any errors related to "Failed to generate 2025 forecast"
   - The forecast calculation might be failing silently

## Testing the Forecast Endpoint Directly

You can test the forecast API directly:

```bash
# Test the forecast endpoint
curl http://localhost:8000/api/v1/tax/forecast/2025?base_year=2024

# Or test the returns endpoint (which includes forecast)
curl http://localhost:8000/api/v1/tax/returns?include_forecast=true
```

## Common Issues

1. **Missing 2024 Tax Return**: The forecast needs 2024 tax data to use as a base for deductions
2. **Missing 2025 Income Data**: The forecast needs 2025 income data (W-2, rental, investment income)
3. **Silent Failures**: Check backend logs for error messages

## Manual Test

If the forecast isn't showing, you can manually test by:
1. Opening browser console on the Tax page
2. Check the network tab for the `/api/v1/tax/returns` request
3. Look for any errors in the response


