import { useState, useEffect, Component, ErrorInfo, ReactNode } from 'react'
import { TrendingUp, TrendingDown, Building2, Briefcase, Landmark, CreditCard, Loader2, Rocket, Wallet } from 'lucide-react'
import { WealthChart } from '../components/dashboard/WealthChart'
import { AssetCard } from '../components/dashboard/AssetCard'
import { InsightsPanel } from '../components/dashboard/InsightsPanel'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './Dashboard.module.css'
import clsx from 'clsx'

// Error boundary to catch render errors
interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class DashboardErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Dashboard error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '40px', textAlign: 'center', color: '#fff' }}>
          <h2 style={{ color: '#FF5A5A' }}>Dashboard Error</h2>
          <p style={{ color: '#A3A3A3' }}>{this.state.error?.message}</p>
          <button 
            onClick={() => window.location.reload()}
            style={{ marginTop: '20px', padding: '10px 20px', background: '#00D632', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
          >
            Reload Page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// Types for API responses
interface AssetData {
  label: string
  description: string
  value: number
  change?: number
  changePercent?: number
}

interface DashboardSummary {
  total_net_worth: number
  total_assets: number
  total_liabilities: number
  assets: {
    public_equity: AssetData & { by_owner?: Record<string, { value: number }> }
    real_estate: AssetData
    startup_equity: AssetData & { companies?: Array<{ name: string; estimated_value: number }> }
    cash: AssetData & { accounts?: Array<{ account_name: string; balance: number }> }
  }
  liabilities: {
    mortgages: AssetData
    other_loans: AssetData
  }
  income: {
    total_investment_income: number
    options_income: number
    dividend_income: number
  }
  last_updated: string
}

interface WealthHistoryItem {
  year: number
  age: number
  netWorth: number
  realEstate?: number
  investments?: number
}

interface WealthHistoryResponse {
  history: WealthHistoryItem[]
  current_age: number
}

type TabType = 'assets' | 'liabilities'

// Icon mapping for asset types
const ASSET_ICONS = {
  public_equity: TrendingUp,
  real_estate: Building2,
  startup_equity: Rocket,
  cash: Wallet,
  mortgages: Landmark,
  other_loans: CreditCard,
}

function DashboardContent() {
  const [activeTab, setActiveTab] = useState<TabType>('assets')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [wealthHistory, setWealthHistory] = useState<WealthHistoryItem[]>([])
  const [currentAge, setCurrentAge] = useState(45)
  const [liveEquityValue, setLiveEquityValue] = useState<number | null>(null)

  useEffect(() => {
    async function fetchDashboardData() {
      setLoading(true)
      setError(null)

      try {
        const headers = getAuthHeaders()
        
        // Fetch summary, history, and holdings with live prices in parallel
        const [summaryRes, historyRes, holdingsRes] = await Promise.all([
          fetch('/api/v1/dashboard/summary', { headers }),
          fetch('/api/v1/dashboard/wealth-history', { headers }),
          fetch('/api/v1/investments/holdings/live', { headers }),
        ])

        if (summaryRes.ok) {
          const summaryData: DashboardSummary = await summaryRes.json()
          setSummary(summaryData)
        } else {
          throw new Error(`Failed to load summary: ${summaryRes.status}`)
        }

        if (historyRes.ok) {
          const historyData: WealthHistoryResponse = await historyRes.json()
          setWealthHistory(historyData.history)
          setCurrentAge(historyData.current_age)
        }

        // Get live equity value from holdings API with Yahoo Finance prices
        if (holdingsRes.ok) {
          const holdingsData = await holdingsRes.json()
          // Use totalValue from live API (includes Yahoo Finance prices)
          setLiveEquityValue(holdingsData.totalValue || holdingsData.total_value || 0)
        }

      } catch (err) {
        console.error('Dashboard fetch error:', err)
        setError(err instanceof Error ? err.message : 'Failed to load dashboard')
      } finally {
        setLoading(false)
      }
    }

    fetchDashboardData()
  }, [])

  const formatCurrency = (value: number | undefined) => {
    if (value === undefined || value === null || isNaN(value)) return '$0'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value)
  }

  const formatPercent = (value: number | undefined) => {
    if (value === undefined || value === null || isNaN(value)) return '+0.00%'
    const sign = value >= 0 ? '+' : ''
    return `${sign}${value.toFixed(2)}%`
  }

  // Loading state
  if (loading) {
    return (
      <div className={styles.dashboard}>
        <div className={styles.loadingState}>
          <Loader2 className={styles.spinner} size={48} />
          <p>Loading dashboard data...</p>
          <p style={{ fontSize: '12px', color: '#666' }}>Fetching from API...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error || !summary) {
    const isAuthError = error?.includes('token') || error?.includes('log in') || error?.includes('Session')
    return (
      <div className={styles.dashboard}>
        <div className={styles.errorState}>
          <p>Failed to load dashboard data</p>
          <p className={styles.errorDetail}>{error || 'No data received'}</p>
          <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
            <button onClick={() => window.location.reload()}>Retry</button>
            {isAuthError && (
              <button 
                onClick={() => {
                  localStorage.clear()
                  window.location.href = '/login'
                }}
                style={{ background: '#FF5A5A' }}
              >
                Log In Again
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Calculate totals using live equity value from Yahoo Finance
  // If we have live prices, use them; otherwise fall back to database values
  const storedEquityValue = summary.assets.public_equity.value
  const actualEquityValue = liveEquityValue !== null ? liveEquityValue : storedEquityValue
  const equityDifference = actualEquityValue - storedEquityValue
  
  // Recalculate total assets and net worth with live equity
  const totalAssets = summary.total_assets + equityDifference
  const totalLiabilities = summary.total_liabilities
  const netWorth = summary.total_net_worth + equityDifference

  // Calculate year-over-year change from wealth history
  // Only show YoY change if we have comparable data (both years have investments tracked)
  const currentYearData = wealthHistory.length > 0 ? wealthHistory[wealthHistory.length - 1] : null
  const lastYearData = wealthHistory.length > 1 ? wealthHistory[wealthHistory.length - 2] : null
  
  // Check if both years have comparable data (investments > 0 means we're tracking investments)
  const hasComparableData = currentYearData?.investments && currentYearData.investments > 0 &&
                            lastYearData?.investments && lastYearData.investments > 0
  
  // Only calculate meaningful YoY change when data is comparable
  // Otherwise the comparison would be misleading (e.g., comparing real estate only vs full portfolio)
  const totalChange = hasComparableData && currentYearData?.netWorth && lastYearData?.netWorth
    ? currentYearData.netWorth - lastYearData.netWorth 
    : 0
  const totalChangePercent = hasComparableData && lastYearData?.netWorth && lastYearData.netWorth > 0 && totalChange
    ? (totalChange / lastYearData.netWorth) * 100
    : 0

  // Build asset cards data - use live equity value for public equity
  const assetCards = [
    {
      key: 'public_equity',
      ...summary.assets.public_equity,
      value: actualEquityValue,  // Override with live Yahoo Finance value
      icon: ASSET_ICONS.public_equity,
    },
    {
      key: 'real_estate',
      ...summary.assets.real_estate,
      icon: ASSET_ICONS.real_estate,
    },
    {
      key: 'startup_equity',
      ...summary.assets.startup_equity,
      icon: ASSET_ICONS.startup_equity,
    },
    {
      key: 'cash',
      ...summary.assets.cash,
      icon: ASSET_ICONS.cash,
    },
  ].filter(asset => asset.value > 0) // Only show assets with value

  const liabilityCards = [
    {
      key: 'mortgages',
      ...summary.liabilities.mortgages,
      icon: ASSET_ICONS.mortgages,
    },
    {
      key: 'other_loans',
      ...summary.liabilities.other_loans,
      icon: ASSET_ICONS.other_loans,
    },
  ]

  return (
    <div className={styles.dashboard}>
      {/* Hero Section - Net Worth */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>
            Total Net Worth
            <span className={styles.ageTag}>Age {currentAge}</span>
          </div>
          <div className={styles.heroValue}>
            {formatCurrency(netWorth)}
          </div>
          {totalChange !== 0 && (
            <div className={clsx(
              styles.heroChange,
              totalChange >= 0 ? styles.positive : styles.negative
            )}>
              {totalChange >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
              <span>{formatCurrency(Math.abs(totalChange))}</span>
              <span className={styles.changePill}>
                {formatPercent(totalChangePercent)}
              </span>
              <span className={styles.changePeriod}>this year</span>
            </div>
          )}
        </div>

        <div className={styles.heroSummary}>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Total Assets</span>
            <span className={styles.summaryValue}>{formatCurrency(totalAssets)}</span>
          </div>
          <div className={styles.summaryDivider} />
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Total Liabilities</span>
            <span className={clsx(styles.summaryValue, totalLiabilities > 0 && styles.negative)}>
              {formatCurrency(totalLiabilities)}
            </span>
          </div>
        </div>
      </section>

      {/* Tabs - Assets / Liabilities */}
      <div className={styles.tabs}>
        <button
          className={clsx(styles.tab, activeTab === 'assets' && styles.active)}
          onClick={() => setActiveTab('assets')}
        >
          Assets
          <span className={styles.tabValue}>{formatCurrency(totalAssets)}</span>
        </button>
        <button
          className={clsx(styles.tab, activeTab === 'liabilities' && styles.active)}
          onClick={() => setActiveTab('liabilities')}
        >
          Liabilities
          <span className={clsx(styles.tabValue, totalLiabilities > 0 && styles.negative)}>
            {formatCurrency(totalLiabilities)}
          </span>
        </button>
      </div>

      {/* Asset/Liability Cards */}
      <section className={styles.cards}>
        {activeTab === 'assets' ? (
          assetCards.length > 0 ? (
            assetCards.map((asset, index) => (
              <AssetCard
                key={asset.key}
                label={asset.label}
                description={asset.description}
                value={asset.value}
                change={asset.change}
                changePercent={asset.changePercent}
                icon={asset.icon}
                delay={index * 50}
              />
            ))
          ) : (
            <div className={styles.emptyState}>
              <p>No assets recorded yet.</p>
              <p>Import brokerage statements to get started.</p>
            </div>
          )
        ) : (
          liabilityCards.filter(l => l.value > 0).length > 0 ? (
            liabilityCards.filter(l => l.value > 0).map((liability, index) => (
              <AssetCard
                key={liability.key}
                label={liability.label}
                description={liability.description}
                value={liability.value}
                change={liability.change}
                changePercent={liability.changePercent}
                icon={liability.icon}
                isLiability
                delay={index * 50}
              />
            ))
          ) : (
            <div className={styles.emptyState}>
              <p>No outstanding liabilities!</p>
              <p>All loans have been paid off.</p>
            </div>
          )
        )}
      </section>

      {/* Wealth Timeline Chart */}
      {wealthHistory.length > 0 && (
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Wealth Journey</h2>
            <p className={styles.chartSubtitle}>
              Net worth progression from age {wealthHistory[0]?.age || 30} to {currentAge}
            </p>
          </div>
          <WealthChart data={wealthHistory} />
        </section>
      )}

      {/* Daily Insights Section */}
      <InsightsPanel />

    </div>
  )
}

// Export wrapped component with error boundary
export function Dashboard() {
  return (
    <DashboardErrorBoundary>
      <DashboardContent />
    </DashboardErrorBoundary>
  )
}
