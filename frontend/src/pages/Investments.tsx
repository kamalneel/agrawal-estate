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

// Pure investment performance — value vs. cost basis, structurally
// independent of income. See docs/INVESTMENTS-PAGE-SPEC.md.
interface PurePosition {
  symbol: string
  status: 'open' | 'closed'
  shares?: number
  proceeds?: number
  cost_basis: number
  value?: number | null
  gain: number | null
  gain_pct: number | null
  weight_pct?: number | null
  closed_date?: string | null
}

interface PurePerformance {
  as_of: string
  current_value: number
  cost_basis: number
  gain: number
  gain_pct: number | null
  unpriced_count: number
  unpriced_cost_basis: number
  chart: { date: string; value: number; invested: number }[]
  open_positions: PurePosition[]
  closed_positions: PurePosition[]
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
interface CashAccountData {
  true_cash: number
  cash: number
  options_collateral: number
  margin_used: number
  pending_orders: number
}

interface AccountCardProps {
  account: Account
  onClick: () => void
  delay: number
  cashData?: CashAccountData
}

function AccountCard({ account, onClick, delay, cashData }: AccountCardProps) {
  const Icon = account.icon
  const isPositive = account.change >= 0
  const trueValue = cashData ? account.value + cashData.true_cash : null

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
      {trueValue !== null ? (
        <>
          <div className={styles.accountValue}>{formatCurrency(trueValue)}</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)', display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 2, marginBottom: 4 }}>
            <span>{formatCurrency(account.value)} stocks</span>
            <span style={{ color: 'var(--color-text-secondary)' }}>+{formatCurrency(cashData!.true_cash)} cash</span>
            {cashData!.margin_used > 0 && (
              <span style={{ color: 'var(--color-negative, #FF5A5A)' }}>−{formatCurrency(cashData!.margin_used)} margin</span>
            )}
          </div>
        </>
      ) : (
        <div className={styles.accountValue}>{formatCurrency(account.value)}</div>
      )}
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

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [growthSummary, setGrowthSummary] = useState<GrowthSummary | null>(null)
  const [chartPeriod, setChartPeriod] = useState<string | null>('ytd')

  const [stockGrowthData, setStockGrowthData] = useState<Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }> | null>(_stockGrowthCache?.data ?? null)
  const [capitalEvents, setCapitalEvents] = useState<CapitalEvent[]>([])
  const [capitalThreshold, setCapitalThreshold] = useState(5000)
  const [highlightedDate, setHighlightedDate] = useState<string | null>(null)
  const [cfSortKey, setCfSortKey] = useState<string>('date')
  const [cfSortDir, setCfSortDir] = useState<'asc' | 'desc'>('desc')
  const [optionChains, setOptionChains] = useState<Record<string, OptionChainInfo>>({})
  const [expandedChains, setExpandedChains] = useState<Set<string>>(new Set())
  const [cashBreakdown, setCashBreakdown] = useState<{ total_true_cash: number; total_margin_used: number; total_options_collateral: number; accounts: (CashAccountData & { account_name: string })[] } | null>(null)
  const [truePortfolioHistory, setTruePortfolioHistory] = useState<{ date: string; stock_value: number; true_cash: number; true_portfolio: number; is_real: boolean }[]>([])
  const [realDataStart, setRealDataStart] = useState<string | null>(null)
  const [acctTruePortHistory, setAcctTruePortHistory] = useState<{ date: string; stock_value: number; true_cash: number; true_portfolio: number; is_real: boolean }[]>([])
  const [acctRealDataStart, setAcctRealDataStart] = useState<string | null>(null)
  const [acctTruePortPeriod, setAcctTruePortPeriod] = useState<string | null>(null)
  const [purePerf, setPurePerf] = useState<PurePerformance | null>(null)
  const [showClosedBets, setShowClosedBets] = useState(false)
  const [pureChartPeriod, setPureChartPeriod] = useState<string | null>(null)

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

        if (!accountId) {
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
    setAcctTruePortHistory([])
    setAcctRealDataStart(null)
    setAcctTruePortPeriod(null)
    fetch(`${API_BASE}/ingestion/robinhood-cash/portfolio-history/by-account/${account.id}`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.history) setAcctTruePortHistory(d.history)
        if (d?.real_data_start) setAcctRealDataStart(d.real_data_start)
      })
      .catch(() => {})
  }

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
    fetch(`${API_BASE}/ingestion/robinhood-cash/balances`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setCashBreakdown(d))
      .catch(() => {})
    fetch(`${API_BASE}/ingestion/robinhood-cash/portfolio-history`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.history) setTruePortfolioHistory(d.history)
        if (d?.real_data_start) setRealDataStart(d.real_data_start)
      })
      .catch(() => {})
    fetchPurePerformance()
  }, [])

  const fetchPurePerformance = () => {
    fetch(`${API_BASE}/investments/pure-performance`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setPurePerf(d))
      .catch(() => {})
  }

  const totalEquity = accounts.reduce((sum, acc) => sum + acc.value, 0)
  const totalChange = accounts.reduce((sum, acc) => sum + acc.change, 0)
  const totalChangePercent = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : 0

  // Filter true portfolio history by selected chart period (client-side)
  const filteredTruePortfolioHistory = useMemo(() => {
    if (!truePortfolioHistory.length) return truePortfolioHistory
    if (!chartPeriod) return truePortfolioHistory
    const today = new Date()
    let cutoff: Date
    switch (chartPeriod) {
      case '1d': cutoff = new Date(today.getTime() - 1 * 24 * 60 * 60 * 1000); break
      case '1w': cutoff = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000); break
      case '30d': cutoff = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000); break
      case '90d': cutoff = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000); break
      case 'ytd': cutoff = new Date(today.getFullYear(), 0, 1); break
      case '1y': cutoff = new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000); break
      default: return truePortfolioHistory
    }
    const cutoffStr = cutoff.toISOString().split('T')[0]
    return truePortfolioHistory.filter(d => d.date >= cutoffStr)
  }, [truePortfolioHistory, chartPeriod])

  // Same period-filter pattern, applied to the pure-performance chart
  const filteredPureChart = useMemo(() => {
    const chart = purePerf?.chart ?? []
    if (!chart.length || !pureChartPeriod) return chart
    const today = new Date()
    let cutoff: Date
    switch (pureChartPeriod) {
      case '1d': cutoff = new Date(today.getTime() - 1 * 24 * 60 * 60 * 1000); break
      case '1w': cutoff = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000); break
      case '30d': cutoff = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000); break
      case '90d': cutoff = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000); break
      case 'ytd': cutoff = new Date(today.getFullYear(), 0, 1); break
      case '1y': cutoff = new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000); break
      default: return chart
    }
    const cutoffStr = cutoff.toISOString().split('T')[0]
    return chart.filter(d => d.date >= cutoffStr)
  }, [purePerf, pureChartPeriod])

  // Headline follows the chart's period selector: ALL shows the exact
  // since-inception figures from the API; any other window derives
  // "gain during this period" from (value − invested) at the window's
  // start vs. now — isolating price-driven return from any new capital
  // added during the window, not just re-showing the all-time number.
  const pureHeadline = useMemo(() => {
    if (!purePerf) return null
    if (!pureChartPeriod || filteredPureChart.length < 2) {
      return {
        gain: purePerf.gain, gain_pct: purePerf.gain_pct,
        value: purePerf.current_value, cost_basis: purePerf.cost_basis,
        scoped: false as const,
      }
    }
    const start = filteredPureChart[0]
    const end = filteredPureChart[filteredPureChart.length - 1]
    const gainStart = start.value - start.invested
    const gainEnd = end.value - end.invested
    const periodGain = gainEnd - gainStart
    return {
      gain: periodGain,
      gain_pct: start.invested ? (periodGain / start.invested) * 100 : null,
      value: end.value, cost_basis: end.invested,
      scoped: true as const, startDate: start.date, endDate: end.date,
    }
  }, [purePerf, pureChartPeriod, filteredPureChart])

  // Filter per-account True Portfolio history by period (client-side)
  const filteredAcctTruePortHistory = useMemo(() => {
    if (!acctTruePortHistory.length || !acctTruePortPeriod) return acctTruePortHistory
    const today = new Date()
    let cutoff: Date
    switch (acctTruePortPeriod) {
      case '30d':  cutoff = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000); break
      case '90d':  cutoff = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000); break
      case 'ytd':  cutoff = new Date(today.getFullYear(), 0, 1); break
      case '1y':   cutoff = new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000); break
      default: return acctTruePortHistory
    }
    const cutoffStr = cutoff.toISOString().split('T')[0]
    return acctTruePortHistory.filter(d => d.date >= cutoffStr)
  }, [acctTruePortHistory, acctTruePortPeriod])

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
    const selectedIndex = accounts.indexOf(selectedAccount)
    const prevAccount = selectedIndex > 0 ? accounts[selectedIndex - 1] : null
    const nextAccount = selectedIndex < accounts.length - 1 ? accounts[selectedIndex + 1] : null

    return (
      <div className={styles.page}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <button className={styles.backButton} onClick={() => setSelectedAccount(null)} style={{ margin: 0 }}>
            <ArrowLeft size={20} />
            Back to Stocks
          </button>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
            <button
              className={styles.backButton}
              style={{ margin: 0, opacity: prevAccount ? 1 : 0.3, pointerEvents: prevAccount ? 'auto' : 'none' }}
              onClick={() => prevAccount && handleAccountSelect(prevAccount)}
            >
              ← {prevAccount?.name ?? ''}
            </button>
            <button
              className={styles.backButton}
              style={{ margin: 0, opacity: nextAccount ? 1 : 0.3, pointerEvents: nextAccount ? 'auto' : 'none' }}
              onClick={() => nextAccount && handleAccountSelect(nextAccount)}
            >
              {nextAccount?.name ?? ''} →
            </button>
          </div>
        </div>

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

        {/* Per-account True Portfolio Chart */}
        {acctTruePortHistory.length > 1 && (() => {
          const HIST_COLOR = '#C49A3C'
          const hasHistorical = filteredAcctTruePortHistory.some(d => !d.is_real)
          const enrichedAcct = filteredAcctTruePortHistory.map(d => ({
            ...d,
            real_true_portfolio: d.is_real ? d.true_portfolio : null,
            real_stock_value:    d.is_real ? d.stock_value    : null,
            hist_stock_value:    !d.is_real ? d.stock_value   : null,
          }))
          return (
            <ChartWrapper
              title="True Portfolio"
              periodOptions={PERIOD_PRESETS.STANDARD}
              periodValue={acctTruePortPeriod}
              onPeriodChange={setAcctTruePortPeriod}
              isEmpty={filteredAcctTruePortHistory.length === 0}
              emptyMessage="Loading account history..."
            >
              <>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={enrichedAcct} margin={CHART_MARGINS}>
                  <defs>
                    <linearGradient id="acctTruePortGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="acctHistGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={HIST_COLOR} stopOpacity={0.18} />
                      <stop offset="100%" stopColor={HIST_COLOR} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis
                    dataKey="date"
                    {...X_AXIS_PROPS}
                    interval={Math.max(0, Math.floor(enrichedAcct.length / 8) - 1)}
                    tickFormatter={(v: string) => new Date(v + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis {...Y_AXIS_PROPS} tickFormatter={formatCurrencyShort} domain={['auto', 'auto']} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null
                      const pt = payload[0]?.payload as typeof enrichedAcct[0]
                      if (!pt) return null
                      const label = new Date(pt.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                      return (
                        <div className={styles.eventTooltip}>
                          <div className={styles.eventTooltipTitle}>{label}</div>
                          {pt.is_real ? (
                            <>
                              <div className={styles.eventTooltipRow}>
                                <span>True Portfolio</span>
                                <span style={{ color: CHART_GREEN, fontWeight: 600 }}>{formatCurrency(pt.true_portfolio)}</span>
                              </div>
                              <div className={styles.eventTooltipRow}>
                                <span>Equity</span>
                                <span>{formatCurrency(pt.stock_value)}</span>
                              </div>
                              <div className={styles.eventTooltipRow}>
                                <span>Cash</span>
                                <span>{formatCurrency(pt.true_cash)}</span>
                              </div>
                            </>
                          ) : (
                            <>
                              <div className={styles.eventTooltipRow}>
                                <span>Equity</span>
                                <span style={{ color: HIST_COLOR, fontWeight: 600 }}>{formatCurrency(pt.stock_value)}</span>
                              </div>
                              <div className={styles.eventTooltipRow}>
                                <span style={{ color: 'var(--color-text-tertiary)', fontSize: '11px' }}>Cash estimated — not shown</span>
                              </div>
                            </>
                          )}
                        </div>
                      )
                    }}
                  />
                  {hasHistorical && (
                    <Area type="monotone" dataKey="hist_stock_value" stroke={HIST_COLOR} strokeWidth={1.5} strokeDasharray="4 3"
                      fill="url(#acctHistGradient)" connectNulls={false} dot={false} activeDot={false} />
                  )}
                  <Area type="monotone" dataKey="real_true_portfolio" stroke={CHART_GREEN} strokeWidth={2.5}
                    fill="url(#acctTruePortGradient)" connectNulls={false}
                    activeDot={{ r: 5, fill: CHART_GREEN, stroke: '#fff', strokeWidth: 2 }} />
                  <Area type="monotone" dataKey="real_stock_value" stroke={CHART_GREEN} strokeWidth={1.5}
                    strokeOpacity={0.45} strokeDasharray="5 3" fill="none" connectNulls={false} dot={false} activeDot={false} />
                </AreaChart>
              </ResponsiveContainer>
              {hasHistorical && acctRealDataStart && (
                <div style={{ display: 'flex', gap: '20px', marginTop: '10px', fontSize: '12px', color: 'var(--color-text-tertiary)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ display: 'inline-block', width: '20px', borderTop: '2px dashed #C49A3C' }} />
                    Equity only (pre-{new Date(acctRealDataStart + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })})
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ display: 'inline-block', width: '20px', borderTop: '2px solid ' + CHART_GREEN }} />
                    True Portfolio (equity + cash)
                  </span>
                </div>
              )}
              </>
            </ChartWrapper>
          )
        })()}

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
      {/* L1 — pure investment performance: value vs. cost basis, structurally
          independent of income (premium/dividends never touch cost basis).
          See docs/INVESTMENTS-PAGE-SPEC.md. */}
      {purePerf && pureHeadline && (
        <section className={styles.pureHero}>
          <div className={styles.pureHeroContent}>
            <div className={styles.heroLabel}>
              Investment Performance
              {pureHeadline.scoped && (
                <span className={styles.pureHeroWindow}>
                  {' '}— {new Date(pureHeadline.startDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  {' '}to {new Date(pureHeadline.endDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
              )}
            </div>
            <div
              className={styles.pureHeroValue}
              style={{ color: pureHeadline.gain >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}
            >
              {pureHeadline.gain >= 0 ? '+' : '-'}{formatCurrency(Math.abs(pureHeadline.gain))}
              {pureHeadline.gain_pct != null && (
                <span className={styles.pureHeroPct}>
                  ({pureHeadline.gain_pct >= 0 ? '+' : ''}{pureHeadline.gain_pct.toFixed(1)}%)
                </span>
              )}
            </div>
            <div className={styles.pureHeroSub}>
              {pureHeadline.scoped ? (
                <>{formatCurrency(pureHeadline.value)} value now vs. {formatCurrency(pureHeadline.cost_basis)} invested as of the window end
                  — price movement only during this window, no options premium or dividends counted in.</>
              ) : (
                <>{formatCurrency(pureHeadline.value)} value vs. {formatCurrency(pureHeadline.cost_basis)} invested
                  — the stocks themselves, no options premium or dividends counted in.</>
              )}
              {purePerf.unpriced_count > 0 && (
                <span className={styles.pureHeroFlag}> ({purePerf.unpriced_count} position{purePerf.unpriced_count === 1 ? '' : 's'} unpriced, {formatCurrency(purePerf.unpriced_cost_basis)} cost basis excluded above)</span>
              )}
            </div>
          </div>
        </section>
      )}

      {purePerf && purePerf.chart.length > 1 && (
        <ChartWrapper
          title="Value vs. Capital Invested"
          periodOptions={PERIOD_PRESETS.EXTENDED}
          periodValue={pureChartPeriod}
          onPeriodChange={setPureChartPeriod}
          isEmpty={filteredPureChart.length === 0}
        >
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={filteredPureChart} margin={CHART_MARGINS}>
              <defs>
                <linearGradient id="pureValueGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="date" {...X_AXIS_PROPS}
                tickFormatter={(d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} />
              <YAxis {...Y_AXIS_PROPS} tickFormatter={(v) => formatCurrencyShort(v)} />
              <Tooltip
                labelFormatter={(d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                formatter={(v: number, name: string) => [formatCurrency(v), name === 'value' ? 'Value' : 'Invested']}
              />
              <Area type="monotone" dataKey="value" name="value" stroke={CHART_GREEN} strokeWidth={2} fill="url(#pureValueGradient)" />
              <Area type="monotone" dataKey="invested" name="invested" stroke="#C49A3C" strokeWidth={1.5} strokeDasharray="5 3" fill="none" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', gap: 20, marginTop: 10, fontSize: 12, color: 'var(--color-text-tertiary)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ display: 'inline-block', width: 20, borderTop: `2px solid ${CHART_GREEN}` }} />
              Value
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ display: 'inline-block', width: 20, borderTop: '2px dashed #C49A3C' }} />
              Capital Invested — the gap is the pure gain
            </span>
          </div>
        </ChartWrapper>
      )}

      {/* L2 — winners & losers: which bets are working, ranked by return */}
      {purePerf && purePerf.open_positions.length > 0 && (
        <section className={styles.betsSection}>
          <h2>Winners &amp; Losers</h2>
          <div className={styles.betsTableWrap}>
            <table className={styles.betsTable}>
              <thead>
                <tr>
                  <th>Symbol</th><th className={styles.num}>Weight</th>
                  <th className={styles.num}>Value</th><th className={styles.num}>Cost Basis</th>
                  <th className={styles.num}>Gain</th><th className={styles.num}>Return</th>
                </tr>
              </thead>
              <tbody>
                {purePerf.open_positions.map(p => (
                  <tr key={p.symbol}>
                    <td className={styles.betSym}>{p.symbol}</td>
                    <td className={styles.num}>{p.weight_pct != null ? `${p.weight_pct.toFixed(1)}%` : '—'}</td>
                    <td className={styles.num}>{p.value != null ? formatCurrency(p.value) : '—'}</td>
                    <td className={styles.num}>{formatCurrency(p.cost_basis)}</td>
                    <td className={styles.num} style={{ color: p.gain == null ? undefined : p.gain >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                      {p.gain != null ? `${p.gain >= 0 ? '+' : '-'}${formatCurrency(Math.abs(p.gain))}` : '—'}
                    </td>
                    <td className={styles.num} style={{ color: p.gain_pct == null ? undefined : p.gain_pct >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                      {p.gain_pct != null ? `${p.gain_pct >= 0 ? '+' : ''}${p.gain_pct.toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {purePerf.closed_positions.length > 0 && (
            <div className={styles.closedBetsToggle}>
              <button onClick={() => setShowClosedBets(v => !v)}>
                {showClosedBets ? 'hide' : 'show'} closed positions ({purePerf.closed_positions.length})
              </button>
              {showClosedBets && (
                <div className={styles.betsTableWrap}>
                  <table className={styles.betsTable}>
                    <thead>
                      <tr>
                        <th>Symbol</th><th>Closed</th>
                        <th className={styles.num}>Proceeds</th><th className={styles.num}>Cost Basis</th>
                        <th className={styles.num}>Gain</th><th className={styles.num}>Return</th>
                      </tr>
                    </thead>
                    <tbody>
                      {purePerf.closed_positions.map(p => (
                        <tr key={p.symbol}>
                          <td className={styles.betSym}>{p.symbol}</td>
                          <td>{p.closed_date ? new Date(p.closed_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</td>
                          <td className={styles.num}>{formatCurrency(p.proceeds || 0)}</td>
                          <td className={styles.num}>{formatCurrency(p.cost_basis)}</td>
                          <td className={styles.num} style={{ color: p.gain == null ? undefined : p.gain >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                            {p.gain != null ? `${p.gain >= 0 ? '+' : '-'}${formatCurrency(Math.abs(p.gain))}` : '—'}
                          </td>
                          <td className={styles.num} style={{ color: p.gain_pct == null ? undefined : p.gain_pct >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                            {p.gain_pct != null ? `${p.gain_pct >= 0 ? '+' : ''}${p.gain_pct.toFixed(1)}%` : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Total-wealth context strip — cash-inclusive True Portfolio, demoted
          to one line: the page's headline is pure performance above, and two
          stacked hero+chart blocks read as competing answers. Chart and
          capital flow live at the bottom as history. */}
      <section className={styles.trueStrip}>
        <div className={styles.trueStripBody}>
          {(() => {
            const trueCash = cashBreakdown?.total_true_cash ?? 0
            const truePortfolio = totalEquity + trueCash
            const dayPct = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : null
            return (
              <>
                <span className={styles.trueStripLabel}>True Portfolio (incl. cash)</span>
                <span className={styles.trueStripValue}>{formatCurrency(truePortfolio)}</span>
                <span className={styles.trueStripDetail}>{formatCurrency(totalEquity)} stocks</span>
                {trueCash !== 0 && <span className={styles.trueStripDetail}>+{formatCurrency(trueCash)} cash &amp; collateral</span>}
                {(cashBreakdown?.total_margin_used ?? 0) > 0 && (
                  <span className={styles.trueStripDetail} style={{ color: 'var(--color-negative, #FF5A5A)' }}>
                    −{formatCurrency(cashBreakdown!.total_margin_used)} margin
                  </span>
                )}
                {dayPct != null && (
                  <span className={styles.trueStripDetail} style={{ color: dayPct >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                    {dayPct >= 0 ? '+' : ''}{dayPct.toFixed(2)}% today
                  </span>
                )}
              </>
            )
          })()}
        </div>
        <button onClick={() => { fetchHoldings(); fetchGrowthSummary(); fetchStockGrowth(true); fetchPurePerformance(); }} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={18} />
        </button>
      </section>

      <section className={styles.accountsSection}>
        <h2>Brokerage Accounts ({accounts.length})</h2>
        <div className={styles.accountsGrid}>
          {accounts.map((account, index) => {
            const cashData = cashBreakdown?.accounts?.find(
              (a: any) => a.account_name.toLowerCase() === account.name.toLowerCase()
            )
            return (
            <AccountCard
              key={account.id}
              account={account}
              onClick={() => handleAccountSelect(account)}
              delay={index * 50}
              cashData={cashData ?? undefined}
            />
            )
          })}
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

        // Cost basis + return come from the lot engine (same source as
        // Winners & Losers above — one definition, no per-panel drift).
        // The synced investment_holdings.cost_basis field is NULL for some
        // accounts and silently understated returns' denominators (TSLA
        // showed +810% from exactly this). If the lot engine covers <98%
        // of the live shares (HSA not yet ingested, missing activity CSV
        // rows), show no number at all and flag it below the table rather
        // than fabricate one from partial basis.
        const lotBySymbol = new Map((purePerf?.open_positions ?? []).map(p => [p.symbol, p]))
        const flagged: { symbol: string; liveShares: number; lotShares: number }[] = []
        for (const h of holdingsMap.values()) {
          const lot = lotBySymbol.get(h.symbol)
          const coverage = lot?.shares ? lot.shares / h.shares : 0
          if (lot && coverage >= 0.98) {
            h.costBasis = lot.cost_basis
          } else {
            h.costBasis = null
            flagged.push({ symbol: h.symbol, liveShares: h.shares, lotShares: lot?.shares ?? 0 })
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
              <>
                <HoldingsTable rows={toHoldingsRows(aggregated, stockGrowthData ?? undefined)} columns={investmentColumns} />
                {flagged.length > 0 && (
                  <p className={styles.basisFootnote}>
                    Cost basis / return withheld where purchase records cover &lt;98% of live shares:{' '}
                    {flagged.map(f => `${f.symbol} (${Math.round(f.lotShares).toLocaleString()} of ${Math.round(f.liveShares).toLocaleString()} sh tracked)`).join(', ')}.
                    {' '}Untracked shares are in the HSA (Fidelity history pending) or awaiting fresh activity CSVs — see INVESTMENTS-PAGE-SPEC.
                  </p>
                )}
              </>
            ) : (
              <p className={styles.noHoldings}>No holdings across accounts.</p>
            )}
          </section>
        )
      })()}

      {/* History — total-wealth chart + capital flow (supporting detail) */}
      {/* True Portfolio Chart */}
      <ChartWrapper
        title="True Portfolio"
        periodOptions={PERIOD_PRESETS.EXTENDED}
        periodValue={chartPeriod}
        onPeriodChange={(key) => {
          setChartPeriod(key)
          fetchPortfolioHistory(undefined, key)
          fetchCapitalEvents(key)
        }}
        isEmpty={filteredTruePortfolioHistory.length === 0 && chartData.length === 0}
        emptyMessage="No historical data yet. Upload account statements to build your portfolio history."
      >
        {filteredTruePortfolioHistory.length > 1 ? (() => {
          // Map capital events by date for dot overlay on daily chart
          const eventsByDate = new Map<string, CapitalEvent[]>()
          for (const event of capitalEvents) {
            const key = event.date
            if (!eventsByDate.has(key)) eventsByDate.set(key, [])
            eventsByDate.get(key)!.push(event)
          }

          const enrichedData = filteredTruePortfolioHistory.map(d => {
            const evts = eventsByDate.get(d.date) || []
            const isReal = d.is_real
            return {
              ...d,
              hasBuy: evts.some(e => e.type === 'BUY'),
              hasSell: evts.some(e => e.type === 'SELL'),
              events: evts,
              // Real zone: full true portfolio + equity line
              real_true_portfolio: isReal ? d.true_portfolio : null,
              real_stock_value:    isReal ? d.stock_value : null,
              // Historical zone: equity only, in muted color
              hist_stock_value:    !isReal ? d.stock_value : null,
            }
          })

          const hasHistorical = enrichedData.some(d => d.hist_stock_value !== null)
          const HIST_COLOR = '#C49A3C'

          return (
          <>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={enrichedData} margin={CHART_MARGINS}>
              <defs>
                <linearGradient id="truePortGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="histEquityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={HIST_COLOR} stopOpacity={0.18} />
                  <stop offset="100%" stopColor={HIST_COLOR} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis
                dataKey="date"
                {...X_AXIS_PROPS}
                interval={Math.max(0, Math.floor(enrichedData.length / 10) - 1)}
                tickFormatter={(v: string) => {
                  const d = new Date(v + 'T00:00:00')
                  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                }}
              />
              <YAxis
                {...Y_AXIS_PROPS}
                tickFormatter={formatCurrencyShort}
                domain={['auto', 'auto']}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]?.payload as { date: string; stock_value: number; true_cash: number; true_portfolio: number; is_real: boolean; events: CapitalEvent[] }
                  if (!point) return null
                  const evts: CapitalEvent[] = point.events || []
                  const dateLabel = new Date(point.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                  return (
                    <div className={styles.eventTooltip}>
                      <div className={styles.eventTooltipTitle}>{dateLabel}</div>
                      {point.is_real ? (
                        <>
                          <div className={styles.eventTooltipRow}>
                            <span>True Portfolio</span>
                            <span style={{ color: CHART_GREEN, fontWeight: 600 }}>{formatCurrency(point.true_portfolio)}</span>
                          </div>
                          <div className={styles.eventTooltipRow}>
                            <span>Equity</span>
                            <span>{formatCurrency(point.stock_value)}</span>
                          </div>
                          <div className={styles.eventTooltipRow}>
                            <span>Cash &amp; Collateral</span>
                            <span>{formatCurrency(point.true_cash)}</span>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className={styles.eventTooltipRow}>
                            <span>Equity</span>
                            <span style={{ color: HIST_COLOR, fontWeight: 600 }}>{formatCurrency(point.stock_value)}</span>
                          </div>
                          <div className={styles.eventTooltipRow}>
                            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '11px' }}>Cash estimated — not shown</span>
                          </div>
                        </>
                      )}
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
              {/* Historical zone: equity only in amber (estimated cash excluded) */}
              {hasHistorical && (
                <Area
                  type="monotone"
                  dataKey="hist_stock_value"
                  stroke={HIST_COLOR}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  fill="url(#histEquityGradient)"
                  connectNulls={false}
                  dot={false}
                  activeDot={false}
                />
              )}
              {/* Real zone: true portfolio — primary filled area */}
              <Area
                type="monotone"
                dataKey="real_true_portfolio"
                stroke={CHART_GREEN}
                strokeWidth={2.5}
                fill="url(#truePortGradient)"
                connectNulls={false}
                animationDuration={1500}
                dot={(props: any) => {
                  const { cx, cy, payload } = props
                  if (cx == null || cy == null) return <g key={`dot-${props.index}`} />
                  if (!payload.hasBuy && !payload.hasSell) return <g key={`dot-${props.index}`} />
                  return (
                    <g key={`dot-${props.index}`} style={{ cursor: 'pointer' }}
                       onClick={() => setHighlightedDate(payload.date)}>
                      {payload.hasBuy && (
                        <>
                          <circle cx={cx} cy={cy} r={7} fill="#00D632" stroke="#fff" strokeWidth={2} opacity={0.9} />
                          <text x={cx} y={cy + 1} textAnchor="middle" fill="#fff" fontSize={9} fontWeight="bold">B</text>
                        </>
                      )}
                      {payload.hasSell && (
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
              {/* Real zone: equity dashed secondary line */}
              <Area
                type="monotone"
                dataKey="real_stock_value"
                stroke={CHART_GREEN}
                strokeWidth={1.5}
                strokeOpacity={0.45}
                strokeDasharray="5 3"
                fill="none"
                connectNulls={false}
                dot={false}
                activeDot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
          {hasHistorical && realDataStart && (
            <div style={{ display: 'flex', gap: '20px', marginTop: '10px', fontSize: '12px', color: 'var(--color-text-tertiary)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ display: 'inline-block', width: '20px', borderTop: '2px dashed #C49A3C' }} />
                Equity only (cash estimated, unreliable)
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ display: 'inline-block', width: '20px', borderTop: '2px solid ' + CHART_GREEN }} />
                True Portfolio — real data from {new Date(realDataStart + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
              </span>
            </div>
          )}
          </>
          )
        })() : chartData.length > 1 ? (() => {
          // Fallback: equity-only chart when true portfolio data is unavailable
          const isDaily = chartPeriod === '1d' || chartPeriod === '1w' || chartPeriod === '30d' || chartPeriod === '90d'
          const eventsByLabel = new Map<string, CapitalEvent[]>()
          for (const event of capitalEvents) {
            const key = isDaily ? event.formatted : event.month_key
            if (!eventsByLabel.has(key)) eventsByLabel.set(key, [])
            eventsByLabel.get(key)!.push(event)
          }
          const enrichedData = chartData.map(d => {
            const evts = eventsByLabel.get(d.month) || []
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
              <XAxis dataKey="month" {...X_AXIS_PROPS} interval={Math.max(0, Math.floor(enrichedData.length / 10) - 1)} />
              <YAxis {...Y_AXIS_PROPS} tickFormatter={formatCurrencyShort} domain={['dataMin - 50000', 'dataMax + 50000']} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]?.payload
                  if (!point) return null
                  const evts: CapitalEvent[] = point.events || []
                  return (
                    <div className={styles.eventTooltip}>
                      <div className={styles.eventTooltipTitle}>{point.month}</div>
                      <div className={styles.eventTooltipRow}><span>Portfolio</span><span>{formatCurrency(point.value)}</span></div>
                      {evts.map((e: CapitalEvent, i: number) => (
                        <div key={i} className={styles.eventTooltipRow}>
                          <span style={{ color: e.type === 'BUY' ? '#00D632' : '#FF5A5A' }}>{e.type} {e.symbol}</span>
                          <span>{formatCurrency(e.amount)}</span>
                        </div>
                      ))}
                    </div>
                  )
                }}
              />
              <Area type="monotone" dataKey="value" stroke={CHART_GREEN} strokeWidth={3} fill="url(#equityGradient)" animationDuration={1500}
                dot={(props: any) => {
                  const { cx, cy, payload } = props
                  if (cx == null || cy == null) return <g key={`dot-${props.index}`} />
                  if (!payload.hasBuy && !payload.hasSell) return <g key={`dot-${props.index}`} />
                  return (
                    <g key={`dot-${props.index}`} style={{ cursor: 'pointer' }} onClick={() => setHighlightedDate(payload.month)}>
                      {payload.hasBuy && (<><circle cx={cx} cy={cy} r={7} fill="#00D632" stroke="#fff" strokeWidth={2} opacity={0.9} /><text x={cx} y={cy + 1} textAnchor="middle" fill="#fff" fontSize={9} fontWeight="bold">B</text></>)}
                      {payload.hasSell && (<><circle cx={cx} cy={cy - 18} r={7} fill="#FF5A5A" stroke="#fff" strokeWidth={2} opacity={0.9} /><text x={cx} y={cy - 17} textAnchor="middle" fill="#fff" fontSize={9} fontWeight="bold">S</text></>)}
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
    </div>
  )
}
