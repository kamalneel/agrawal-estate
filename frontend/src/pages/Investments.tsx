import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, ArrowLeft, User, Heart, Briefcase, RefreshCw, AlertCircle } from 'lucide-react'
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
  change1d?: number | null
  change30d?: number | null
  change90d?: number | null
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

// Helper functions
const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

const formatCurrencyPrecise = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

const formatPercent = (value: number) => {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

const formatNumber = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

// Custom Tooltip for Chart
interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ value: number; payload: MonthlyData }>
}

function ChartTooltip({ active, payload }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div className={styles.chartTooltip}>
        <div className={styles.tooltipMonth}>{payload[0].payload.month}</div>
        <div className={styles.tooltipValue}>{formatCurrency(payload[0].value)}</div>
      </div>
    )
  }
  return null
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
      </div>
      <div className={styles.viewDetails}>
        View Holdings →
      </div>
    </button>
  )
}

// Holdings Table Component
interface HoldingsTableProps {
  holdings: Holding[]
}

function HoldingsTable({ holdings }: HoldingsTableProps) {
  const formatChange = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '—'
    const sign = value >= 0 ? '+' : ''
    return `${sign}${value.toFixed(2)}%`
  }
  
  // Filter out CASH (incorrectly calculated in backend) and calculate real values
  const stockHoldings = holdings.filter(h => h.symbol !== 'CASH')
  
  // Calculate total portfolio value from real prices (shares × currentPrice)
  const totalPortfolioValue = stockHoldings.reduce((sum, h) => sum + (h.shares * h.currentPrice), 0)
  
  return (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th className={styles.alignRight}>Shares</th>
            <th className={styles.alignRight}>Price</th>
            <th className={styles.alignRight}>Total Value</th>
            <th className={styles.alignRight}>% Portfolio</th>
            <th className={styles.alignRight}>Today</th>
            <th className={styles.alignRight}>30 Days</th>
            <th className={styles.alignRight}>90 Days</th>
          </tr>
        </thead>
        <tbody>
          {stockHoldings.map((holding) => {
            // Calculate total value as shares × price (more accurate than parsed value)
            const calculatedTotalValue = holding.shares * holding.currentPrice
            // Calculate percentage based on real total portfolio value
            const calculatedPercent = totalPortfolioValue > 0 ? (calculatedTotalValue / totalPortfolioValue * 100) : 0
            return (
            <tr key={holding.symbol} className={styles.tableRow}>
              <td className={styles.symbol}>{holding.symbol}</td>
              <td className={styles.name}>{holding.name}</td>
              <td className={styles.alignRight}>{formatNumber(holding.shares)}</td>
              <td className={styles.alignRight}>{formatCurrencyPrecise(holding.currentPrice)}</td>
              <td className={clsx(styles.alignRight, styles.totalValue)}>
                {formatCurrencyPrecise(calculatedTotalValue)}
              </td>
              <td className={styles.alignRight}>
                <div className={styles.percentBar}>
                  <div
                    className={styles.percentFill}
                    style={{ width: `${Math.min(calculatedPercent, 100)}%` }}
                  />
                  <span>{calculatedPercent.toFixed(1)}%</span>
                </div>
              </td>
              <td className={clsx(
                styles.alignRight,
                styles.changeCell,
                holding.change1d !== null && holding.change1d !== undefined
                  ? (holding.change1d >= 0 ? styles.positive : styles.negative)
                  : ''
              )}>
                {formatChange(holding.change1d)}
              </td>
              <td className={clsx(
                styles.alignRight,
                styles.changeCell,
                holding.change30d !== null && holding.change30d !== undefined
                  ? (holding.change30d >= 0 ? styles.positive : styles.negative)
                  : ''
              )}>
                {formatChange(holding.change30d)}
              </td>
              <td className={clsx(
                styles.alignRight,
                styles.changeCell,
                holding.change90d !== null && holding.change90d !== undefined
                  ? (holding.change90d >= 0 ? styles.positive : styles.negative)
                  : ''
              )}>
                {formatChange(holding.change90d)}
              </td>
            </tr>
          )})}
        </tbody>
      </table>
    </div>
  )
}

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

// Main Investments Component
export function Investments() {
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [chartData, setChartData] = useState<MonthlyData[]>([])
  const [accountChartData, setAccountChartData] = useState<MonthlyData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [growthSummary, setGrowthSummary] = useState<GrowthSummary | null>(null)
  

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
  const fetchPortfolioHistory = async (accountId?: string) => {
    try {
      const url = accountId 
        ? `${API_BASE}/investments/portfolio-history?account_id=${encodeURIComponent(accountId)}`
        : `${API_BASE}/investments/portfolio-history`
      
      const response = await fetch(url, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        // Transform API data to chart format
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
  const handleAccountSelect = async (account: Account) => {
    setSelectedAccount(account)
    setAccountChartData([]) // Clear previous data
    // Clear parse messages when switching accounts (they are account-specific)
    setParseSuccess(null)
    setParseError(null)
    setHoldingsText('') // Also clear the textarea
    await fetchPortfolioHistory(account.id)
  }

  // Fetch price changes for holdings
  const fetchPriceChanges = async (): Promise<Record<string, any>> => {
    try {
      const response = await fetch(`${API_BASE}/investments/price-changes`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        return data.price_data || {}
      }
    } catch (err) {
      console.error('Error fetching price changes:', err)
    }
    return {}
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
        change: 0,
        changePercent: 0,
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
          change: 0,
          changePercent: 0,
          change1d: null,
          change30d: null,
          change90d: null,
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
    fetchPortfolioHistory()
    fetchGrowthSummary()
  }, [])

  const totalEquity = accounts.reduce((sum, acc) => sum + acc.value, 0)
  const totalChange = accounts.reduce((sum, acc) => sum + acc.change, 0)
  const totalChangePercent = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : 0

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
            </div>
          </div>
        </div>

        {/* Account Growth Chart */}
        <section className={styles.chartSection}>
          <h2>Account Growth</h2>
          {accountChartData.length > 1 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={accountChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                  <defs>
                    <linearGradient id="accountGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={selectedAccount.color} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={selectedAccount.color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="month"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 12 }}
                    dy={10}
                    interval={Math.max(0, Math.floor(accountChartData.length / 8) - 1)}
                    tickFormatter={(value) => {
                      // Extract year from "Jan 2024" or "2024-01" format
                      const match = value.match(/(\d{4})/);
                      return match ? match[1] : value;
                    }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 12 }}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                    dx={-10}
                    width={70}
                  />
                  <Tooltip content={<ChartTooltip />} />
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
            </div>
          ) : accountChartData.length === 1 ? (
            <div className={styles.chartEmpty}>
              <div className={styles.singleDataPoint}>
                <span className={styles.dataPointLabel}>{accountChartData[0].month}</span>
                <span className={styles.dataPointValue}>{formatCurrency(accountChartData[0].value)}</span>
              </div>
              <p>Upload more statements to see account growth over time.</p>
            </div>
          ) : (
            <div className={styles.chartEmpty}>
              <p>Loading account history...</p>
            </div>
          )}
        </section>

        <section className={styles.holdingsSection}>
          <h2>Holdings ({selectedAccount.holdings.filter(h => h.symbol !== 'CASH').length})</h2>
          {selectedAccount.holdings.filter(h => h.symbol !== 'CASH').length > 0 ? (
          <HoldingsTable holdings={selectedAccount.holdings} />
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
          
          {/* Growth Periods */}
          {growthSummary?.periods && Object.keys(growthSummary.periods).length > 0 ? (
            <div className={styles.growthPeriods}>
              {(['30d', '90d', '1y'] as const).map((key) => {
                const period = growthSummary.periods[key]
                if (!period) return null
                const isPositive = period.change >= 0
                return (
                  <div 
                    key={key} 
                    className={clsx(
                      styles.growthPeriod,
                      isPositive ? styles.positive : styles.negative
                    )}
                  >
                    <span className={styles.periodLabel}>{period.label}</span>
                    <span className={styles.periodValue}>
                      {isPositive ? '+' : ''}{formatPercent(period.change_percent)}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className={clsx(
              styles.heroChange,
              totalChange >= 0 ? styles.positive : styles.negative
            )}>
              {totalChange >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
              <span>{formatCurrency(Math.abs(totalChange))}</span>
              <span className={styles.changePill}>{formatPercent(totalChangePercent)}</span>
              <span className={styles.changePeriod}>today</span>
            </div>
          )}
        </div>
        <button onClick={() => { fetchHoldings(); fetchGrowthSummary(); }} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={20} />
        </button>
      </section>

      {/* Growth Chart */}
      <section className={styles.chartSection}>
        <h2>Portfolio Growth</h2>
        {chartData.length > 1 ? (
        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00D632" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00D632" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#737373', fontSize: 12 }}
                dy={10}
                interval={Math.max(0, Math.floor(chartData.length / 10) - 1)}
                tickFormatter={(value) => {
                  // Extract year from "Jan 2024" or "2024-01" format
                  const match = value.match(/(\d{4})/);
                  return match ? match[1] : value;
                }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#737373', fontSize: 12 }}
                tickFormatter={(v) => `$${(v / 1000000).toFixed(1)}M`}
                dx={-10}
                width={70}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#00D632"
                strokeWidth={3}
                fill="url(#equityGradient)"
                animationDuration={1500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        ) : chartData.length === 1 ? (
          <div className={styles.chartEmpty}>
            <div className={styles.singleDataPoint}>
              <span className={styles.dataPointLabel}>{chartData[0].month}</span>
              <span className={styles.dataPointValue}>{formatCurrency(chartData[0].value)}</span>
            </div>
            <p>Upload statements from more months to see your portfolio growth over time.</p>
          </div>
        ) : (
          <div className={styles.chartEmpty}>
            <p>No historical data yet. Upload account statements to build your portfolio history.</p>
          </div>
        )}
      </section>

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
    </div>
  )
}
