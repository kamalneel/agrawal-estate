import React, { useState, useEffect, useMemo } from 'react'
import { TrendingUp, TrendingDown, ArrowLeft, User, Heart, Briefcase, RefreshCw, AlertCircle, ChevronRight } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import styles from './Investments.module.css'
import clsx from 'clsx'
import {
  HoldingsTable,
  symbolColumn,
  sharesColumn,
  priceColumn,
  valueColumn,
  percentPortfolioColumn,
  costBasisColumn,
  totalReturnColumn,
  stockGrowthColumn,
  holdingPeriodColumn,
} from '../components/HoldingsTable'
import type { HoldingsRow, ColumnDef } from '../components/HoldingsTable'
import {
  formatCurrency,
  formatCurrencyShort,
  formatPercent,
  ChartTooltip,
  ChartWrapper,
  PERIOD_PRESETS,
  GRID_PROPS,
  X_AXIS_PROPS,
  Y_AXIS_PROPS,
  CHART_MARGINS,
  CHART_GREEN,
} from '../components/charts'

const API_BASE = '/api/v1'

// Types
interface Holding {
  symbol: string
  name: string
  shares: number
  currentPrice: number
  totalValue: number
  percentOfPortfolio: number
  priceSource?: 'live' | 'cached' | 'statement'
  change: number
  changePercent: number
  costBasis?: number | null
}

interface Account {
  id: string
  name: string
  owner: string
  type: 'brokerage' | 'retirement' | 'ira' | 'hsa' | string
  value: number
  securitiesValue?: number
  cashBalance?: number
  change: number
  changePercent: number
  holdings: Holding[]
  icon: typeof User
  color: string
  pricesUpdatedAt?: string
}

interface MonthlyData {
  month: string
  value: number
}

interface GrowthPeriod {
  label: string
  past_value: number
  current_value: number
  change: number
  change_percent: number
  snapshot_date: string
}

interface GrowthSummary {
  current_value: number
  periods: {
    "30d"?: GrowthPeriod
    "90d"?: GrowthPeriod
    "1y"?: GrowthPeriod
  }
}

interface CapitalEvent {
  date: string
  formatted: string
  month_key: string
  date_key: string
  type: 'BUY' | 'SELL'
  symbol: string
  quantity: number | null
  amount: number
  price_per_share: number | null
  account_id: string
  account_name: string
  description: string
}

interface OptionChainTrade {
  date: string; formatted: string; type: 'STO' | 'BTC'
  strike: number; expiry: string; amount: number; contracts: number
}

interface OptionChainInfo {
  is_forced: boolean; option_type: 'put' | 'call'
  net_premium: number; rolls: number
  chain_start_date: string; starting_strike: number; final_strike: number
  duration_days: number; contracts: number; trades: OptionChainTrade[]
}


// Account type to icon mapping
const getAccountIcon = (type: string) => {
  switch (type) {
    case 'retirement':
    case '401k':
      return Briefcase
    case 'hsa':
      return Heart
    default:
      return User
  }
}

// Account type display names
const getAccountTypeDisplay = (type: string) => {
  switch (type) {
    case 'brokerage':
    case 'individual':
      return 'Brokerage Account'
    case 'retirement':
    case '401k':
      return 'Retirement Account'
    case 'ira':
      return 'IRA Account'
    case 'roth_ira':
      return 'Roth IRA Account'
    case 'hsa':
      return 'Health Savings Account'
    default:
      return 'Brokerage Account'
  }
}


// Account Card Component
interface AccountCardProps {
  account: Account
  onClick: () => void
  delay: number
}

function AccountCard({ account, onClick, delay }: AccountCardProps) {
  const Icon = account.icon
  const isPositive = account.change >= 0

  return (
    <button
      className={styles.accountCard}
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={styles.accountHeader}>
        <div
          className={styles.accountIcon}
          style={{ background: `${account.color}20`, color: account.color }}
        >
          <Icon size={24} />
        </div>
        <div className={styles.accountInfo}>
          <h3 className={styles.accountName}>{account.name}</h3>
          <span className={styles.accountType}>
            {getAccountTypeDisplay(account.type)}
          </span>
        </div>
      </div>
      <div className={styles.accountValue}>{formatCurrency(account.value)}</div>
      <div className={clsx(styles.accountChange, isPositive ? styles.positive : styles.negative)}>
        {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
        <span>{formatCurrency(Math.abs(account.change))}</span>
        <span className={styles.changePercent}>{formatPercent(account.changePercent)}</span>
        <span style={{ opacity: 0.6, fontSize: '0.8em', marginLeft: 4 }}>Today</span>
      </div>
      <div className={styles.viewDetails}>
        View Holdings →
      </div>
    </button>
  )
}

// Mapper: convert Holding[] to HoldingsRow[], merging growth data
function toHoldingsRows(holdings: Holding[], growthData?: Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }>): HoldingsRow[] {
  return holdings.map((h) => {
    const value = h.symbol === 'CASH' ? h.totalValue : h.shares * h.currentPrice
    const costBasis = h.costBasis ?? null
    const totalReturnPct = costBasis && costBasis > 0 ? ((value - costBasis) / costBasis) * 100 : null
    const growth = growthData?.[h.symbol]
    return {
      symbol: h.symbol,
      shares: h.shares,
      currentPrice: h.currentPrice,
      value: h.totalValue,
      isCash: h.symbol === 'CASH',
      costBasis,
      totalReturnPct: totalReturnPct != null ? Math.round(totalReturnPct * 10) / 10 : null,
      growthYTD: growth?.growth_ytd ?? null,
      growth1Y: growth?.growth_1y ?? null,
      growth5Y: growth?.growth_5y ?? null,
      holdingPeriodDays: growth?.holding_period_days ?? null,
    }
  })
}

// Column configuration for Investments page
const investmentColumns: ColumnDef[] = [
  symbolColumn(),
  sharesColumn(),
  priceColumn('Price (Live)'),
  valueColumn(),
  percentPortfolioColumn(),
  costBasisColumn(),
  totalReturnColumn(),
  stockGrowthColumn('growthYTD', 'YTD', 'growthYTD'),
  stockGrowthColumn('growth1Y', '1Y Growth', 'growth1Y'),
  stockGrowthColumn('growth5Y', '5Y Growth', 'growth5Y'),
  holdingPeriodColumn(),
]

// Empty State Component
function EmptyState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={styles.emptyState}>
      <AlertCircle size={48} />
      <h3>No Holdings Data</h3>
      <p>No stock holdings found in the database. Add your holdings to get started.</p>
      <button onClick={onRefresh} className={styles.refreshButton}>
        <RefreshCw size={18} />
        Refresh Data
      </button>
    </div>
  )
}

// Module-level cache for stock growth data (survives re-mounts across page navigations)
let _stockGrowthCache: { data: Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }>; ts: number } | null = null
const STOCK_GROWTH_CACHE_TTL = 60 * 60 * 1000 // 1 hour in ms

// Main Investments Component
export function Investments() {
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [chartData, setChartData] = useState<MonthlyData[]>([])
  const [accountChartData, setAccountChartData] = useState<MonthlyData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [growthSummary, setGrowthSummary] = useState<GrowthSummary | null>(null)
  const [chartPeriod, setChartPeriod] = useState<string | null>('ytd')
  const [accountChartPeriod, setAccountChartPeriod] = useState<string | null>(null)
  const [stockGrowthData, setStockGrowthData] = useState<Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }> | null>(_stockGrowthCache?.data ?? null)
  const [capitalEvents, setCapitalEvents] = useState<CapitalEvent[]>([])
  const [capitalThreshold, setCapitalThreshold] = useState(5000)
  const [highlightedDate, setHighlightedDate] = useState<string | null>(null)
  const [cfSortKey, setCfSortKey] = useState<string>('date')
  const [cfSortDir, setCfSortDir] = useState<'asc' | 'desc'>('desc')
  const [optionChains, setOptionChains] = useState<Record<string, OptionChainInfo>>({})
  const [expandedChains, setExpandedChains] = useState<Set<string>>(new Set())

  // Fetch stock growth data (with frontend cache to avoid re-fetching on page navigation)
  const fetchStockGrowth = async (force = false) => {
    // Use cached data if still fresh
    if (!force && _stockGrowthCache && Date.now() - _stockGrowthCache.ts < STOCK_GROWTH_CACHE_TTL) {
      setStockGrowthData(_stockGrowthCache.data)
      return
    }
    try {
      const response = await fetch(`${API_BASE}/investments/stock-growth`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        _stockGrowthCache = { data, ts: Date.now() }
        setStockGrowthData(data)
      }
    } catch (err) {
      console.error('Error fetching stock growth:', err)
    }
  }

  // Fetch capital events (BUY/SELL) for chart overlay and table
  const fetchCapitalEvents = async (period?: string | null, minAmount?: number) => {
    try {
      const params = new URLSearchParams()
      if (period) params.set('period', period)
      params.set('min_amount', String(minAmount ?? capitalThreshold))
      const qs = params.toString()

      const [eventsRes, chainsRes] = await Promise.all([
        fetch(`${API_BASE}/investments/capital-events${qs ? `?${qs}` : ''}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/capital-events/option-chains${qs ? `?${qs}` : ''}`, { headers: getAuthHeaders() }),
      ])

      if (eventsRes.ok) {
        const data = await eventsRes.json()
        setCapitalEvents(data.events || [])
      }
      if (chainsRes.ok) {
        const data = await chainsRes.json()
        setOptionChains(data.option_chains || {})
      }
    } catch (err) {
      console.error('Error fetching capital events:', err)
    }
  }

  const getEventKey = (e: CapitalEvent) => `${e.date}|${e.symbol}|${e.account_id}|${e.type}`

  const toggleChainExpand = (key: string) => {
    setExpandedChains(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Fetch growth summary from snapshots
  const fetchGrowthSummary = async () => {
    try {
      const response = await fetch(`${API_BASE}/investments/growth-summary`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        setGrowthSummary(data)
      } else {
        console.error('Growth summary API error:', response.status)
      }
    } catch (err) {
      console.error('Error fetching growth summary:', err)
    }
  }

  // Fetch portfolio history for chart
  const fetchPortfolioHistory = async (accountId?: string, period?: string | null) => {
    try {
      const params = new URLSearchParams()
      if (accountId) params.set('account_id', accountId)
      if (period) params.set('period', period)
      const qs = params.toString()
      const url = `${API_BASE}/investments/portfolio-history${qs ? `?${qs}` : ''}`

      const response = await fetch(url, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        const history: MonthlyData[] = (data.history || []).map((h: any) => ({
          month: h.formatted || h.month,
          value: h.value,
        }))

        if (accountId) {
          setAccountChartData(history)
        } else {
          setChartData(history)
        }
      } else {
        console.error('Portfolio history API error:', response.status, await response.text())
      }
    } catch (err) {
      console.error('Error fetching portfolio history:', err)
    }
  }
  
  // Fetch account-specific history when account is selected
  const handleAccountSelect = (account: Account) => {
    setSelectedAccount(account)
    setAccountChartData([]) // Clear previous data
    setAccountChartPeriod(null) // Reset to "All" period
  }

  // Fetch chart data when selected account or period changes
  useEffect(() => {
    if (selectedAccount) {
      fetchPortfolioHistory(selectedAccount.id, accountChartPeriod)
    }
  }, [selectedAccount?.id, accountChartPeriod])

  // Fetch holdings with LIVE prices from Yahoo Finance
  const fetchHoldings = async () => {
    setLoading(true)
    setError(null)
    
    try {
      // Use /holdings/live endpoint for real-time Yahoo Finance prices
      const holdingsResponse = await fetch(`${API_BASE}/investments/holdings/live`, { 
        headers: getAuthHeaders() 
      })
      
      if (!holdingsResponse.ok) {
        throw new Error('Failed to fetch holdings')
      }
      
      const data = await holdingsResponse.json()
      
      // Transform API data to our Account format
      // The /holdings/live endpoint already includes:
      // - Live prices from Yahoo Finance
      // - Calculated market values (shares × live price)
      // - Cash balances from statements
      const transformedAccounts: Account[] = (data.accounts || []).map((acc: any) => ({
        id: acc.id,
        name: acc.name,
        owner: acc.owner,
        type: acc.type,
        value: acc.value || 0,
        securitiesValue: acc.securitiesValue || 0,
        cashBalance: acc.cashBalance || 0,
        change: acc.change || 0,
        changePercent: acc.changePercent || 0,
        icon: getAccountIcon(acc.type),
        color: acc.color || '#00D632',
        pricesUpdatedAt: acc.pricesUpdatedAt,
        holdings: (acc.holdings || []).map((h: any) => ({
          symbol: h.symbol,
          name: h.name || h.symbol,
          shares: h.shares || 0,
          currentPrice: h.currentPrice || 0,
          totalValue: h.totalValue || 0,
          percentOfPortfolio: h.percentOfPortfolio || 0,
          priceSource: h.priceSource || 'cached',
          change: h.change || 0,
          changePercent: h.changePercent || 0,
          costBasis: h.costBasis ?? null,
        })),
      }))
      
      setAccounts(transformedAccounts)
    } catch (err) {
      console.error('Error fetching holdings:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHoldings()
    fetchPortfolioHistory(undefined, 'ytd')
    fetchGrowthSummary()
    fetchStockGrowth()
    fetchCapitalEvents('ytd')
  }, [])

  const totalEquity = accounts.reduce((sum, acc) => sum + acc.value, 0)
  const totalChange = accounts.reduce((sum, acc) => sum + acc.change, 0)
  const totalChangePercent = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : 0

  // Build current price lookup from holdings for Capital Flow table
  const currentPriceMap = useMemo(() => {
    const map: Record<string, number> = {}
    for (const acc of accounts) {
      for (const h of acc.holdings) {
        if (h.symbol !== 'CASH' && h.currentPrice > 0) {
          map[h.symbol] = h.currentPrice
        }
      }
    }
    return map
  }, [accounts])

  // Loading state
  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading stocks...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <h3>Error Loading Data</h3>
          <p>{error}</p>
          <button onClick={fetchHoldings} className={styles.refreshButton}>
            <RefreshCw size={18} />
            Try Again
          </button>
        </div>
      </div>
    )
  }

  // Detail View
  if (selectedAccount) {
    return (
      <div className={styles.page}>
        <button
          className={styles.backButton}
          onClick={() => setSelectedAccount(null)}
        >
          <ArrowLeft size={20} />
          Back to Stocks
        </button>

        <div className={styles.detailHeader}>
          <div
            className={styles.detailIcon}
            style={{ background: `${selectedAccount.color}20`, color: selectedAccount.color }}
          >
            <selectedAccount.icon size={32} />
          </div>
          <div className={styles.detailInfo}>
            <h1>{selectedAccount.name}</h1>
            <span className={styles.detailType}>
              {getAccountTypeDisplay(selectedAccount.type)}
            </span>
          </div>
          <div className={styles.detailValue}>
            <div className={styles.detailAmount}>{formatCurrency(selectedAccount.value)}</div>
            <div className={clsx(
              styles.detailChange,
              selectedAccount.change >= 0 ? styles.positive : styles.negative
            )}>
              {selectedAccount.change >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              {formatCurrency(Math.abs(selectedAccount.change))}
              <span className={styles.changePill}>
                {formatPercent(selectedAccount.changePercent)}
              </span>
              <span style={{ opacity: 0.6, fontSize: '0.8em', marginLeft: 4 }}>Today</span>
            </div>
          </div>
        </div>

        {/* Account Growth Chart */}
        <ChartWrapper
          title="Account Growth"
          periodOptions={PERIOD_PRESETS.STANDARD}
          periodValue={accountChartPeriod}
          onPeriodChange={setAccountChartPeriod}
          isEmpty={accountChartData.length === 0}
          emptyMessage="Loading account history..."
        >
          {accountChartData.length > 1 ? (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={accountChartData} margin={CHART_MARGINS}>
                <defs>
                  <linearGradient id="accountGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={selectedAccount.color} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={selectedAccount.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis
                  dataKey="month"
                  {...X_AXIS_PROPS}
                  interval={Math.max(0, Math.floor(accountChartData.length / 8) - 1)}
                  tickFormatter={(value) => {
                    const match = value.match(/(\d{4})/);
                    return match ? match[1] : value;
                  }}
                />
                <YAxis {...Y_AXIS_PROPS} tickFormatter={formatCurrencyShort} />
                <Tooltip content={<ChartTooltip labelKey="month" />} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={selectedAccount.color}
                  strokeWidth={3}
                  fill="url(#accountGradient)"
                  animationDuration={1000}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : accountChartData.length === 1 ? (
            <div className={styles.chartEmpty}>
              <div className={styles.singleDataPoint}>
                <span className={styles.dataPointLabel}>{accountChartData[0].month}</span>
                <span className={styles.dataPointValue}>{formatCurrency(accountChartData[0].value)}</span>
              </div>
              <p>Upload more statements to see account growth over time.</p>
            </div>
          ) : null}
        </ChartWrapper>

        <section className={styles.holdingsSection}>
          <h2>Holdings ({selectedAccount.holdings.filter(h => h.symbol !== 'CASH').length})</h2>
          {selectedAccount.holdings.filter(h => h.symbol !== 'CASH').length > 0 ? (
          <HoldingsTable
            rows={toHoldingsRows(selectedAccount.holdings, stockGrowthData ?? undefined)}
            columns={investmentColumns}
          />
          ) : (
            <p className={styles.noHoldings}>No holdings in this account.</p>
          )}
        </section>
      </div>
    )
  }

  // Empty state
  if (accounts.length === 0) {
    return (
      <div className={styles.page}>
        <EmptyState onRefresh={fetchHoldings} />
      </div>
    )
  }

  // Main View
  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>Total Stock Holdings</div>
          <div className={styles.heroValue}>{formatCurrency(totalEquity)}</div>
          
          {/* Growth Periods — portfolio-weighted average of individual stock returns */}
          {(() => {
            // Build weighted growth from individual stock data + daily change from live prices
            const allHoldings = accounts.flatMap(a => a.holdings.filter(h => h.symbol !== 'CASH'))
            const growthCards: { key: string; label: string; pct: number | null }[] = []

            // 1D: use daily change from live prices (already available)
            const dayPct = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : null
            growthCards.push({ key: '1d', label: '1 Day', pct: dayPct })

            // YTD and 1Y: portfolio-weighted average of per-stock growth
            if (stockGrowthData) {
              for (const [key, label, field] of [
                ['ytd', 'YTD', 'growth_ytd'],
                ['1y', '1 Year', 'growth_1y'],
              ] as const) {
                let weightedSum = 0
                let totalVal = 0
                for (const h of allHoldings) {
                  const g = stockGrowthData[h.symbol]
                  const growthVal = g?.[field]
                  if (growthVal == null) continue
                  const val = h.shares * h.currentPrice
                  weightedSum += growthVal * val
                  totalVal += val
                }
                growthCards.push({ key, label, pct: totalVal > 0 ? weightedSum / totalVal : null })
              }
            }

            return (
              <div className={styles.growthPeriods}>
                {growthCards.map(({ key, label, pct }) => {
                  if (pct == null) return null
                  const isPositive = pct >= 0
                  return (
                    <div
                      key={key}
                      className={clsx(
                        styles.growthPeriod,
                        isPositive ? styles.positive : styles.negative
                      )}
                    >
                      <span className={styles.periodLabel}>{label}</span>
                      <span className={styles.periodValue}>
                        {isPositive ? '+' : ''}{pct.toFixed(2)}%
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
        <button onClick={() => { fetchHoldings(); fetchGrowthSummary(); fetchStockGrowth(true); }} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={20} />
        </button>
      </section>

      {/* Growth Chart */}
      <ChartWrapper
        title="Portfolio Growth"
        periodOptions={PERIOD_PRESETS.EXTENDED}
        periodValue={chartPeriod}
        onPeriodChange={(key) => {
          setChartPeriod(key)
          fetchPortfolioHistory(undefined, key)
          fetchCapitalEvents(key)
        }}
        isEmpty={chartData.length === 0}
        emptyMessage="No historical data yet. Upload account statements to build your portfolio history."
      >
        {chartData.length > 1 ? (() => {
          // Merge capital events onto chart data points for dot overlay
          const isDaily = chartPeriod === '1d' || chartPeriod === '1w' || chartPeriod === '30d' || chartPeriod === '90d'
          const eventsByLabel = new Map<string, CapitalEvent[]>()
          for (const event of capitalEvents) {
            const key = isDaily ? event.formatted : event.month_key
            if (!eventsByLabel.has(key)) eventsByLabel.set(key, [])
            eventsByLabel.get(key)!.push(event)
          }

          const enrichedData = chartData.map(d => {
            const evts = eventsByLabel.get(d.month)
            if (!evts || evts.length === 0) return { ...d, events: [] as CapitalEvent[] }
            return { ...d, hasBuy: evts.some(e => e.type === 'BUY'), hasSell: evts.some(e => e.type === 'SELL'), events: evts }
          })

          return (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={enrichedData} margin={CHART_MARGINS}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis
                dataKey="month"
                {...X_AXIS_PROPS}
                interval={Math.max(0, Math.floor(enrichedData.length / 10) - 1)}
              />
              <YAxis
                {...Y_AXIS_PROPS}
                tickFormatter={formatCurrencyShort}
                domain={['dataMin - 50000', 'dataMax + 50000']}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload || !payload.length) return null
                  const point = payload[0]?.payload
                  if (!point) return null
                  const evts: CapitalEvent[] = point.events || []
                  return (
                    <div className={styles.eventTooltip}>
                      <div className={styles.eventTooltipTitle}>{point.month}</div>
                      <div className={styles.eventTooltipRow}>
                        <span>Portfolio</span>
                        <span>{formatCurrency(point.value)}</span>
                      </div>
                      {evts.map((e: CapitalEvent, i: number) => (
                        <div key={i} className={styles.eventTooltipRow}>
                          <span style={{ color: e.type === 'BUY' ? '#00D632' : '#FF5A5A' }}>
                            {e.type} {e.symbol}
                          </span>
                          <span>{formatCurrency(e.amount)}</span>
                        </div>
                      ))}
                    </div>
                  )
                }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={CHART_GREEN}
                strokeWidth={3}
                fill="url(#equityGradient)"
                animationDuration={1500}
                dot={(props: any) => {
                  const { cx, cy, payload } = props
                  if (cx == null || cy == null) return <g key={`dot-${props.index}`} />
                  const hasBuy = payload.hasBuy
                  const hasSell = payload.hasSell
                  if (!hasBuy && !hasSell) return <g key={`dot-${props.index}`} />
                  return (
                    <g key={`dot-${props.index}`} style={{ cursor: 'pointer' }}
                       onClick={() => setHighlightedDate(payload.month)}>
                      {hasBuy && (
                        <>
                          <circle cx={cx} cy={cy} r={7} fill="#00D632" stroke="#fff" strokeWidth={2} opacity={0.9} />
                          <text x={cx} y={cy + 1} textAnchor="middle" fill="#fff" fontSize={9} fontWeight="bold">B</text>
                        </>
                      )}
                      {hasSell && (
                        <>
                          <circle cx={cx} cy={cy - 18} r={7} fill="#FF5A5A" stroke="#fff" strokeWidth={2} opacity={0.9} />
                          <text x={cx} y={cy - 17} textAnchor="middle" fill="#fff" fontSize={9} fontWeight="bold">S</text>
                        </>
                      )}
                    </g>
                  )
                }}
                activeDot={{ r: 5, fill: CHART_GREEN, stroke: '#fff', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
          )
        })() : chartData.length === 1 ? (
          <div className={styles.chartEmpty}>
            <div className={styles.singleDataPoint}>
              <span className={styles.dataPointLabel}>{chartData[0].month}</span>
              <span className={styles.dataPointValue}>{formatCurrency(chartData[0].value)}</span>
            </div>
            <p>Upload statements from more months to see your portfolio growth over time.</p>
          </div>
        ) : null}
      </ChartWrapper>

      {/* Capital Flow Table */}
      {capitalEvents.length > 0 && (
        <section className={styles.capitalFlowSection}>
          <div className={styles.capitalFlowHeader}>
            <h2>Capital Flow ({capitalEvents.length} transactions)</h2>
            <select
              className={styles.thresholdSelect}
              value={capitalThreshold}
              onChange={(e) => {
                const val = Number(e.target.value)
                setCapitalThreshold(val)
                fetchCapitalEvents(chartPeriod, val)
              }}
            >
              <option value={1000}>{"Show \u2265 $1K"}</option>
              <option value={5000}>{"Show \u2265 $5K"}</option>
              <option value={10000}>{"Show \u2265 $10K"}</option>
              <option value={25000}>{"Show \u2265 $25K"}</option>
            </select>
          </div>
          <table className={styles.capitalFlowTable}>
            <thead>
              <tr>
                {([
                  ['date', 'Date'],
                  ['type', 'Type'],
                  ['symbol', 'Symbol'],
                  ['quantity', 'Shares'],
                  ['price_per_share', 'Price/Share'],
                  ['current_price', 'Current Price'],
                  ['account_name', 'Account'],
                  ['option_premium', 'Option Premium'],
                  ['amount', 'Amount'],
                ] as [string, string][]).map(([key, label]) => (
                  <th
                    key={key}
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => {
                      if (cfSortKey === key) {
                        setCfSortDir(d => d === 'desc' ? 'asc' : 'desc')
                      } else {
                        setCfSortKey(key)
                        setCfSortDir(key === 'symbol' || key === 'account_name' || key === 'type' ? 'asc' : 'desc')
                      }
                    }}
                  >
                    {label} {cfSortKey === key ? (cfSortDir === 'asc' ? '↑' : '↓') : <span style={{ opacity: 0.3 }}>⇅</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...capitalEvents].sort((a, b) => {
                let cmp = 0
                if (cfSortKey === 'current_price') {
                  cmp = (currentPriceMap[a.symbol] ?? 0) - (currentPriceMap[b.symbol] ?? 0)
                } else if (cfSortKey === 'option_premium') {
                  cmp = (optionChains[getEventKey(a)]?.net_premium ?? 0) - (optionChains[getEventKey(b)]?.net_premium ?? 0)
                } else {
                  const key = cfSortKey as keyof CapitalEvent
                  const va = a[key]
                  const vb = b[key]
                  if (typeof va === 'string' && typeof vb === 'string') cmp = va.localeCompare(vb)
                  else cmp = ((va as number) ?? 0) - ((vb as number) ?? 0)
                }
                return cfSortDir === 'asc' ? cmp : -cmp
              }).map((event, i) => {
                const isDaily = chartPeriod === '1d' || chartPeriod === '1w' || chartPeriod === '30d' || chartPeriod === '90d'
                const matchLabel = isDaily ? event.formatted : event.month_key
                const isHighlighted = highlightedDate === matchLabel
                const eventKey = getEventKey(event)
                const chain = optionChains[eventKey]
                const isExpanded = expandedChains.has(eventKey)
                return (
                  <React.Fragment key={i}>
                  <tr className={isHighlighted ? styles.highlighted : undefined}>
                    <td>{event.formatted}</td>
                    <td>
                      <span className={`${styles.typeBadge} ${event.type === 'BUY' ? styles.typeBuy : styles.typeSell}`}>
                        {event.type}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{event.symbol}</td>
                    <td className={styles.monoCell}>{event.quantity != null ? event.quantity.toLocaleString() : '-'}</td>
                    <td className={styles.monoCell}>{event.price_per_share != null ? formatCurrency(event.price_per_share) : '-'}</td>
                    <td className={styles.monoCell}>{currentPriceMap[event.symbol] ? formatCurrency(currentPriceMap[event.symbol]) : '-'}</td>
                    <td className={styles.accountCell}>{event.account_name}</td>
                    <td>
                      {chain ? (
                        <span
                          className={styles.premiumClickable}
                          onClick={() => toggleChainExpand(eventKey)}
                        >
                          <ChevronRight
                            size={14}
                            className={`${styles.expandIcon} ${isExpanded ? styles.rotated : ''}`}
                          />
                          <span className={chain.net_premium >= 0 ? styles.premiumPositive : styles.premiumNegative}>
                            {chain.net_premium >= 0 ? '+' : ''}{formatCurrency(chain.net_premium)}
                          </span>
                        </span>
                      ) : (
                        <span className={styles.premiumDash}>&mdash;</span>
                      )}
                    </td>
                    <td className={event.type === 'BUY' ? styles.amountBuy : styles.amountSell}>
                      {event.type === 'BUY' ? '-' : '+'}{formatCurrency(event.amount)}
                    </td>
                  </tr>
                  {chain && isExpanded && (
                    <tr className={styles.chainExpandedRow}>
                      <td colSpan={9}>
                        <div className={styles.chainDetails}>
                          <div className={styles.chainSummary}>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Type</span>
                              <span className={styles.chainStatValue}>{chain.option_type === 'put' ? 'Put Assignment' : 'Call Assignment'}</span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Contracts</span>
                              <span className={styles.chainStatValue}>{chain.contracts}</span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Started</span>
                              <span className={styles.chainStatValue}>
                                {chain.chain_start_date ? new Date(chain.chain_start_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '-'}
                              </span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Strike Range</span>
                              <span className={styles.chainStatValue}>${chain.starting_strike} → ${chain.final_strike}</span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Rolls</span>
                              <span className={styles.chainStatValue}>{chain.rolls}</span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Duration</span>
                              <span className={styles.chainStatValue}>{chain.duration_days} days</span>
                            </div>
                            <div className={styles.chainStat}>
                              <span className={styles.chainStatLabel}>Net Premium</span>
                              <span className={`${styles.chainStatValue} ${chain.net_premium >= 0 ? styles.premiumPositive : styles.premiumNegative}`}>
                                {chain.net_premium >= 0 ? '+' : ''}{formatCurrency(chain.net_premium)}
                              </span>
                            </div>
                          </div>
                          <table className={styles.chainTable}>
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Action</th>
                                <th>Strike</th>
                                <th>Expiry</th>
                                <th>Contracts</th>
                                <th>Amount</th>
                              </tr>
                            </thead>
                            <tbody>
                              {chain.trades.map((trade, ti) => (
                                <tr key={ti}>
                                  <td>{trade.formatted}</td>
                                  <td className={trade.type === 'STO' ? styles.tradeOpen : styles.tradeClose}>
                                    {trade.type}
                                  </td>
                                  <td>${trade.strike}</td>
                                  <td>{trade.expiry}</td>
                                  <td>{trade.contracts}</td>
                                  <td className={trade.amount >= 0 ? styles.premiumPositive : styles.premiumNegative}>
                                    {trade.amount >= 0 ? '+' : ''}{formatCurrency(trade.amount)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={7} className={styles.footerLabel}>Totals</td>
                <td>
                  <div className={styles.footerStats}>
                    <span className={styles.footerBuys}>
                      Buy: {formatCurrency(capitalEvents.filter(e => e.type === 'BUY').reduce((s, e) => s + e.amount, 0))}
                    </span>
                    <span className={styles.footerSells}>
                      Sell: {formatCurrency(capitalEvents.filter(e => e.type === 'SELL').reduce((s, e) => s + e.amount, 0))}
                    </span>
                    <span className={styles.footerNet}>
                      Net: {formatCurrency(
                        capitalEvents.filter(e => e.type === 'SELL').reduce((s, e) => s + e.amount, 0)
                        - capitalEvents.filter(e => e.type === 'BUY').reduce((s, e) => s + e.amount, 0)
                      )}
                    </span>
                  </div>
                </td>
              </tr>
            </tfoot>
          </table>
        </section>
      )}

      {/* Account Cards */}
      <section className={styles.accountsSection}>
        <h2>Brokerage Accounts ({accounts.length})</h2>
        <div className={styles.accountsGrid}>
          {accounts.map((account, index) => (
            <AccountCard
              key={account.id}
              account={account}
              onClick={() => handleAccountSelect(account)}
              delay={index * 50}
            />
          ))}
        </div>
      </section>

      {/* Total Portfolio Holdings */}
      {accounts.length > 0 && (() => {
        // Aggregate holdings across all accounts by symbol
        const holdingsMap = new Map<string, Holding>()
        for (const account of accounts) {
          for (const h of account.holdings) {
            if (h.symbol === 'CASH') continue
            const existing = holdingsMap.get(h.symbol)
            if (existing) {
              // Sum cost basis across accounts for weighted average
              if (h.costBasis && existing.costBasis) {
                existing.costBasis = existing.costBasis + h.costBasis
              } else if (h.costBasis) {
                existing.costBasis = h.costBasis
              }
              existing.shares += h.shares
              existing.totalValue = existing.shares * existing.currentPrice
            } else {
              holdingsMap.set(h.symbol, {
                ...h,
                totalValue: h.shares * h.currentPrice,
              })
            }
          }
        }

        const aggregated = Array.from(holdingsMap.values())
          .sort((a, b) => (b.shares * b.currentPrice) - (a.shares * a.currentPrice))

        const totalValue = aggregated.reduce((sum, h) => sum + (h.shares * h.currentPrice), 0)
        // Recalculate percentOfPortfolio against entire portfolio
        for (const h of aggregated) {
          const hValue = h.shares * h.currentPrice
          h.percentOfPortfolio = totalValue > 0 ? (hValue / totalValue) * 100 : 0
        }

        return (
          <section className={styles.holdingsSection}>
            <h2>Total Portfolio Holdings ({aggregated.length})</h2>
            {aggregated.length > 0 ? (
              <HoldingsTable rows={toHoldingsRows(aggregated, stockGrowthData ?? undefined)} columns={investmentColumns} />
            ) : (
              <p className={styles.noHoldings}>No holdings across accounts.</p>
            )}
          </section>
        )
      })()}
    </div>
  )
}
