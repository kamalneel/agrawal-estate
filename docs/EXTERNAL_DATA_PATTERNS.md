# External Data & Caching Patterns

## Overview

This document covers external data sources, polling schedules, caching strategies, and frontend patterns for fetching external data.

---

## External Data Sources

### 1. Yahoo Finance (Primary)

**Library:** `yfinance` (Python)  
**Direct API:** `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`

**Data Provided:**
- Stock prices (current, historical)
- Options chains (calls, puts)
- Option expiration dates
- Technical indicators (RSI, moving averages, volatility)

**Rate Limiting:**
- Undocumented rate limits
- System uses intelligent caching to avoid 429 errors
- Falls back to NASDAQ API when rate-limited

### 2. NASDAQ API (Fallback)

**Endpoint:** `https://api.nasdaq.com/api/quote/{symbol}/option-chain`

**Usage:**
- Only used when Yahoo Finance is rate-limited
- Provides options chain data as fallback
- No authentication required

---

## Cache Architecture

### Yahoo Finance Cache (`yahoo_cache.py`)

**Cache TTL (Time To Live):**

| Market Status | Cache TTL | Rationale |
|--------------|-----------|-----------|
| Market Hours (6:30 AM - 1:00 PM PT) | 5 minutes | Prices change frequently |
| Extended Hours (4:00 AM - 6:30 AM, 1:00 PM - 5:00 PM PT) | 10 minutes | Some price movement |
| Outside Market Hours | 30 minutes | Prices static |
| Weekends | 60 minutes | Markets closed |

**Cache Types:**
- Ticker Info Cache: Stock information
- Option Chain Cache: Options data for specific symbol/expiration
- Expirations Cache: Available expiration dates

### Stock Price Cache (`price_service.py`)

| Market Status | Cache TTL |
|--------------|-----------|
| Market Hours | 60 seconds |
| Outside Market Hours | 30 minutes |
| Weekends | 30 minutes |

---

## Page Dependencies & Data Fetching

### Summary Table

| Page | External Data? | Data Source | Polling Type | Cache TTL | Refresh Method |
|------|---------------|-------------|--------------|-----------|----------------|
| **Dashboard** | ✅ Yes | Yahoo Finance | On-demand | 60s / 30min | Page load, manual |
| **Options Selling** | ✅ Yes | Yahoo Finance | On-demand | 5min / 30min | Tab open, manual |
| **Options Monitor** | ✅ Yes | Yahoo Finance | On-demand | 5min / 30min | "Check Now" button |
| **Notifications** | ✅ Indirect | Yahoo Finance (via recommendations) | On-demand | N/A | Page load |
| **Investments** | ✅ Yes | Yahoo Finance | On-demand | 60s / 30min | Page load, manual |
| **Real Estate** | ❌ No | Database only | N/A | N/A | N/A |
| **Income** | ❌ No | Database only | N/A | N/A | N/A |
| **Cash** | ❌ No | Database only | N/A | N/A | N/A |

---

## Automated Polling (APScheduler)

**Important:** The scheduler is for **generating recommendations** and **sending notifications**, NOT for polling external data.

| Time Period | Frequency | Description |
|------------|-----------|-------------|
| 5:30 AM PT (Mon-Fri) | Daily | Pre-computes technical indicators |
| 8 AM - 2 PM PT (Mon-Fri) | Every 15 min | Active hours checks |
| Midnight - 8 AM PT | Every 30 min | Pre-market checks |
| 2 PM - Midnight PT | Every 60 min | After-hours checks |
| Weekends | Every 6 hours | Weekend checks |

---

## Frontend External Data Patterns

### Core Principles

1. **Show Cached Data Immediately** - Never show blank screen while waiting
2. **Manual Refresh by Default** - Don't auto-refresh on mount for external data
3. **Progressive Enhancement** - Load cached data first, then refresh in background
4. **Graceful Degradation** - Continue working even if API calls fail
5. **Clear Data Freshness Indicators** - Always show when data was last updated

### Pattern Implementation

#### 1. Load Cached Data on Mount

```typescript
useEffect(() => {
  try {
    const cached = localStorage.getItem('data_cache');
    if (cached) {
      const parsed = JSON.parse(cached);
      setData(parsed.data || []);
      if (parsed.generated_at) {
        setGeneratedAt(new Date(parsed.generated_at));
      }
    }
  } catch (e) {
    console.error('Error loading cached data:', e);
  }
}, []);
```

#### 2. Manual Refresh Pattern

```typescript
const fetchData = async () => {
  setRefreshing(true);
  setError(null);
  
  try {
    // Step 1: Refresh external data (with timeout)
    const refreshController = new AbortController();
    const refreshTimeout = setTimeout(() => refreshController.abort(), 30000);
    
    try {
      await fetch('/api/v1/external/refresh', {
        method: 'POST',
        signal: refreshController.signal
      });
      clearTimeout(refreshTimeout);
    } catch (refreshErr) {
      clearTimeout(refreshTimeout);
      // Continue even if refresh fails - use cached data
    }
    
    // Step 2: Fetch fresh data (with separate timeout)
    const response = await fetch('/api/v1/data', {
      cache: 'no-store'
    });
    
    if (response.ok) {
      const result = await response.json();
      setData(result.data || []);
      
      // Cache the results
      localStorage.setItem('data_cache', JSON.stringify({
        data: result.data,
        generated_at: new Date().toISOString()
      }));
    }
  } catch (err) {
    setError(`Failed to load: ${err.message}`);
  } finally {
    setRefreshing(false);
  }
};
```

#### 3. Data Freshness Indicators

```typescript
{generatedAt ? (
  <span className={lastUpdated > 1Hour ? styles.stale : ''}>
    Last refreshed: {formatTimeAgo(generatedAt)}
  </span>
) : (
  <span className={styles.stale}>
    Never refreshed - click Refresh to load
  </span>
)}
```

#### 4. Refresh Button

```typescript
<button 
  onClick={fetchData}
  disabled={refreshing}
>
  {refreshing ? 'Refreshing...' : 'Refresh'}
</button>
```

---

## When to Use This Pattern

**Use for:**
- ✅ Data from external APIs (Yahoo Finance, MFapi.in)
- ✅ API calls that can be slow (> 1 second)
- ✅ API calls that can fail or timeout
- ✅ Data that doesn't need to be real-time

**Don't use for:**
- ❌ Data only from your own database (use standard fetch)
- ❌ Data that must be real-time (use WebSockets)
- ❌ Critical data that must be fresh (show loading state)

---

## API Endpoints

### Data Freshness Info

```
GET /api/v1/strategies/data-freshness
```

Returns:
- `last_options_fetch`: When options data was last fetched
- `last_prices_fetch`: When prices were last fetched
- `cache_ttl_seconds`: Current cache TTL
- `is_market_hours`: Whether market is currently open
- `data_sources`: Which API provided data

### Clear Cache

```
POST /api/v1/strategies/clear-cache?symbol=AAPL
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/modules/strategies/yahoo_cache.py` | Options and ticker data cache |
| `backend/app/modules/investments/price_service.py` | Stock prices cache |
| `backend/app/core/cache.py` | General caching utilities |
| `backend/app/core/scheduler.py` | APScheduler configuration |

---

## Key Insights

1. **No Background Data Polling** - Most pages fetch on-demand to prevent rate limiting
2. **Intelligent Caching** - Cache TTL adapts to market hours
3. **Manual Refresh Options** - Most pages have "Refresh" buttons for user control
4. **Rate Limiting Protection** - Multiple cache layers + NASDAQ fallback

---

*Last Updated: December 2025*

