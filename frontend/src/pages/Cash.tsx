import { useState, useEffect } from 'react'
import {
  Banknote,
  Building2,
  RefreshCw,
  TrendingUp,
  Clock,
  CheckCircle,
  Upload,
  User,
  CreditCard,
  Landmark,
  PiggyBank,
  ChartLine,
} from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import styles from './Cash.module.css'
import clsx from 'clsx'

const API_BASE = '/api/v1'

// Types
interface CashAccount {
  source: string
  source_display: string
  account_id: string
  account_name: string
  account_type: string
  owner: string
  balance: number
  as_of_date: string | null
}

interface BySource {
  display_name: string
  total: number
  accounts: CashAccount[]
}

interface ByOwner {
  total: number
  color: string
  accounts: CashAccount[]
}

interface CashSummary {
  total_cash: number
  account_count: number
  accounts: CashAccount[]
  by_source: Record<string, BySource>
  by_owner: Record<string, ByOwner>
}

interface CashHistoryItem {
  month: string
  formatted: string
  value: number
  bank: number
  robinhood: number
  year: number
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

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return 'N/A'
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// Custom Tooltip for Charts
interface ChartTooltipProps {
  active?: boolean
  payload?: Array<{ value: number; payload: CashHistoryItem }>
}

function ChartTooltip({ active, payload }: ChartTooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div className={styles.chartTooltip}>
        <div className={styles.tooltipMonth}>{payload[0].payload.formatted}</div>
        <div className={styles.tooltipValue}>{formatCurrency(payload[0].value)}</div>
      </div>
    )
  }
  return null
}

// Source icons
const getSourceIcon = (source: string) => {
  switch (source) {
    case 'bank_of_america':
      return Landmark
    case 'chase':
      return CreditCard
    case 'robinhood':
      return TrendingUp
    default:
      return Building2
  }
}

const getSourceColor = (source: string) => {
  // Use professional, non-alarming colors for financial data
  switch (source) {
    case 'bank_of_america':
      return '#012169' // Bank of America navy blue (their actual brand color)
    case 'chase':
      return '#0F62FE' // Chase blue (softer)
    case 'robinhood':
      return '#5AC53B' // Robinhood green (less fluorescent)
    default:
      return '#6B7280'
  }
}

// Source Card Component
interface SourceCardProps {
  source: string
  data: BySource
  isActive: boolean
}

function SourceCard({ source, data, isActive }: SourceCardProps) {
  const Icon = getSourceIcon(source)
  const color = getSourceColor(source)

  return (
    <div className={clsx(styles.sourceCard, isActive && styles.active)}>
      <div className={styles.sourceHeader}>
        <div
          className={styles.sourceIcon}
          style={{ background: `${color}20`, color: color }}
        >
          <Icon size={24} />
        </div>
        <div className={styles.sourceInfo}>
          <h3 className={styles.sourceName}>{data.display_name}</h3>
          <span className={styles.sourceType}>
            {data.accounts.length} account{data.accounts.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div className={styles.sourceValue}>
        {formatCurrency(data.total)}
      </div>

      <p className={styles.sourceDescription}>
        {source === 'robinhood' 
          ? 'Cash held in brokerage accounts (excludes 401k)'
          : source === 'bank_of_america'
          ? 'Checking and savings accounts'
          : source === 'chase'
          ? 'Checking and savings accounts'
          : 'Cash balance'
        }
      </p>

      <div className={clsx(styles.sourceBadge, isActive ? styles.active : styles.pending)}>
        {isActive ? (
          <>
            <CheckCircle size={12} />
            {data.accounts.length} Account{data.accounts.length !== 1 ? 's' : ''} Connected
          </>
        ) : (
          <>
            <Clock size={12} />
            Pending Upload
          </>
        )}
      </div>
    </div>
  )
}

// Account Card Component
interface AccountCardProps {
  account: CashAccount
}

function AccountCard({ account }: AccountCardProps) {
  const Icon = getSourceIcon(account.source)
  const color = getSourceColor(account.source)

  return (
    <div className={styles.accountCard}>
      <div className={styles.accountHeader}>
        <div
          className={styles.accountIcon}
          style={{ background: `${color}20`, color: color }}
        >
          <Icon size={20} />
        </div>
        <div>
          <h3 className={styles.accountName}>{account.account_name}</h3>
          <span className={styles.accountType}>{account.account_type}</span>
        </div>
      </div>
      <div className={styles.accountBalance}>
        {formatCurrency(account.balance)}
      </div>
      <div className={styles.accountDate}>
        As of {formatDate(account.as_of_date)}
      </div>
    </div>
  )
}

// Owner Card Component
interface OwnerCardProps {
  owner: string
  data: ByOwner
}

function OwnerCard({ owner, data }: OwnerCardProps) {
  return (
    <div className={clsx(styles.ownerCard, styles[owner.toLowerCase()])}>
      <div className={styles.ownerName}>{owner}</div>
      <div className={styles.ownerBalance} style={{ color: data.color }}>
        {formatCurrency(data.total)}
      </div>
      <div className={styles.ownerAccounts}>
        {data.accounts.length} account{data.accounts.length !== 1 ? 's' : ''}
      </div>
    </div>
  )
}

// Upload Card Component
interface UploadCardProps {
  title: string
  description: string
  path: string
  icon: typeof Landmark
  color: string
}

function UploadCard({ title, description, path, icon: Icon, color }: UploadCardProps) {
  return (
    <div className={styles.uploadCard}>
      <div className={styles.uploadIcon} style={{ background: `${color}20`, color: color }}>
        <Icon size={32} />
      </div>
      <div className={styles.uploadTitle}>{title}</div>
      <p className={styles.uploadDescription}>{description}</p>
      <div className={styles.uploadPath}>{path}</div>
    </div>
  )
}

// Main Cash Component
export function Cash() {
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<CashSummary | null>(null)
  const [history, setHistory] = useState<CashHistoryItem[]>([])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [summaryRes, historyRes] = await Promise.all([
        fetch(`${API_BASE}/cash/summary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/cash/history?months=12`, { headers: getAuthHeaders() }),
      ])

      if (summaryRes.ok) {
        const data = await summaryRes.json()
        setSummary(data)
      }
      if (historyRes.ok) {
        const data = await historyRes.json()
        setHistory(data.history || [])
      }
    } catch (err) {
      console.error('Error fetching cash data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Loading state
  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading cash balances...</p>
        </div>
      </div>
    )
  }

  // Define expected sources
  const expectedSources = ['robinhood', 'bank_of_america', 'chase']
  
  // Calculate totals by source
  const robinhoodTotal = summary?.by_source['robinhood']?.total || 0
  const boaTotal = summary?.by_source['bank_of_america']?.total || 0
  const chaseTotal = summary?.by_source['chase']?.total || 0

  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>Total Liquid Cash</div>
          <div className={styles.heroValue}>
            {formatCurrency(summary?.total_cash || 0)}
          </div>
          <div className={styles.heroSubtext}>
            Across {summary?.account_count || 0} account{(summary?.account_count || 0) !== 1 ? 's' : ''} from {Object.keys(summary?.by_source || {}).length} source{Object.keys(summary?.by_source || {}).length !== 1 ? 's' : ''}
          </div>

          <div className={styles.heroBreakdown}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel} style={{ color: getSourceColor('robinhood') }}>
                <span className={styles.sourceIndicator} style={{ background: getSourceColor('robinhood') }} />
                Robinhood
              </span>
              <span className={styles.heroStatValue}>
                {formatCurrency(robinhoodTotal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel} style={{ color: getSourceColor('bank_of_america') }}>
                <span className={styles.sourceIndicator} style={{ background: getSourceColor('bank_of_america') }} />
                Bank of America
              </span>
              <span className={styles.heroStatValue}>
                {formatCurrency(boaTotal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel} style={{ color: getSourceColor('chase') }}>
                <span className={styles.sourceIndicator} style={{ background: getSourceColor('chase') }} />
                Chase
              </span>
              <span className={styles.heroStatValue}>
                {formatCurrency(chaseTotal)}
              </span>
            </div>
          </div>
        </div>
        <button onClick={fetchData} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={20} />
        </button>
      </section>

      {/* Cash Sources */}
      <section className={styles.sourcesSection}>
        <h2>Cash Sources</h2>
        <div className={styles.sourcesGrid}>
          {expectedSources.map((source) => {
            const data = summary?.by_source[source]
            const hasData = data && data.accounts.length > 0
            
            return (
              <SourceCard
                key={source}
                source={source}
                data={data || {
                  display_name: source === 'bank_of_america' ? 'Bank of America' : 
                               source === 'chase' ? 'Chase' : 
                               source === 'robinhood' ? 'Robinhood' : source,
                  total: 0,
                  accounts: []
                }}
                isActive={hasData || false}
              />
            )
          })}
        </div>
      </section>

      {/* Cash History Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Cash Balance History</h2>
          <div className={styles.chartTotal}>
            {formatCurrency(summary?.total_cash || 0)}
          </div>
        </div>

        {history.length > 0 ? (
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height={350}>
              <AreaChart data={history} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                <defs>
                  <linearGradient id="cashGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00D632" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#00D632" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="formatted"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#737373', fontSize: 11 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#737373', fontSize: 11 }}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                  dx={-10}
                  width={60}
                />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#00D632"
                  strokeWidth={2}
                  fill="url(#cashGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className={styles.chartEmpty}>
            <ChartLine size={48} className={styles.chartEmptyIcon} />
            <p>No historical data available yet.<br />Upload bank statements to track cash over time.</p>
          </div>
        )}
      </section>

      {/* All Accounts */}
      {summary && summary.accounts.length > 0 && (
        <section className={styles.accountsSection}>
          <h2>All Cash Accounts</h2>
          <div className={styles.accountsGrid}>
            {summary.accounts.map((account, index) => (
              <AccountCard key={`${account.source}-${account.account_id}-${index}`} account={account} />
            ))}
          </div>
        </section>
      )}

      {/* By Owner */}
      {summary && Object.keys(summary.by_owner).length > 0 && (
        <section className={styles.ownerSection}>
          <h2>By Owner</h2>
          <div className={styles.ownerGrid}>
            {Object.entries(summary.by_owner).map(([owner, data]) => (
              <OwnerCard key={owner} owner={owner} data={data} />
            ))}
          </div>
        </section>
      )}

      {/* Upload Instructions */}
      <section className={styles.uploadSection}>
        <h2>Add Bank Statements</h2>
        <div className={styles.uploadGrid}>
          <UploadCard
            title="Bank of America"
            description="Upload your Bank of America statements to track checking and savings account balances"
            path="data/inbox/cash/bank_of_america/"
            icon={Landmark}
            color={getSourceColor('bank_of_america')}
          />
          <UploadCard
            title="Chase"
            description="Upload your Chase bank statements to track checking and savings account balances"
            path="data/inbox/cash/chase/"
            icon={CreditCard}
            color={getSourceColor('chase')}
          />
        </div>
      </section>

      {/* Empty State - Show if no data at all */}
      {summary && summary.accounts.length === 0 && (
        <div className={styles.emptyState}>
          <PiggyBank size={64} />
          <h3>No Cash Data Yet</h3>
          <p>
            Upload your bank statements from Bank of America and Chase to the folders above.
            Robinhood cash balances will be automatically pulled from your brokerage account data.
          </p>
        </div>
      )}
    </div>
  )
}

