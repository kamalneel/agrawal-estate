import { useState, useEffect } from 'react'
import {
  TrendingUp,
  RefreshCw,
  ArrowLeft,
  DollarSign,
  Home,
  Briefcase,
  User,
  Clock,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
  PiggyBank,
} from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import styles from './Income.module.css'
import clsx from 'clsx'

const API_BASE = '/api/v1'

// Types
interface IncomeSource {
  id: string
  name: string
  type: 'salary' | 'rental' | 'investment'
  status: 'active' | 'pending_upload'
  value?: number
  description: string
  icon: typeof TrendingUp
  color: string
}

interface AccountIncome {
  name: string
  owner: string
  type: string
  options_income: number
  dividend_income: number
  interest_income: number
  stock_lending: number
  total: number
}

interface MonthlyData {
  month: string
  formatted: string
  value: number
  year: number
}

interface OptionsData {
  total_income: number
  by_account: Record<string, {
    owner: string
    account_type: string
    total: number
    transaction_count: number
    monthly: Record<string, number>
  }>
  transactions: Array<{
    date: string
    symbol: string
    description: string
    trans_code: string
    quantity: number
    amount: number
    account: string
    option_type: string
  }>
  transaction_count: number
}

interface DividendData {
  total_income: number
  by_account: Record<string, {
    owner: string
    account_type: string
    total: number
    transaction_count: number
    monthly?: Record<string, number>
  }>
  by_symbol: Record<string, number>
  transactions: Array<{
    date: string
    symbol: string
    amount: number
    account: string
  }>
  transaction_count: number
}

interface InterestData {
  total_income: number
  by_account: Record<string, {
    owner: string
    account_type: string
    total: number
    transaction_count: number
    monthly?: Record<string, number>
  }>
  transactions: Array<{
    date: string
    description: string
    amount: number
    account: string
    source: string
  }>
  transaction_count: number
}

interface RentalExpense {
  category: string
  amount: number
}

interface RentalProperty {
  address: string
  year: number
  gross_income: number
  total_expenses: number
  net_income: number
  property_tax: number
  hoa: number
  maintenance: number
  other_expenses: number
  cost_basis: number
  expenses: RentalExpense[]
  monthly_income: Array<{
    month: string
    month_name: string
    amount: number
    year: number
  }>
}

interface RentalData {
  total_gross_income: number
  total_expenses: number
  total_net_income: number
  total_property_tax: number
  total_hoa: number
  total_maintenance: number
  property_count: number
  properties: RentalProperty[]
}

interface SalaryYearData {
  year: number
  gross: number
  net: number
  federal_tax: number
  state_tax: number
}

interface SalaryEmployee {
  name: string
  employer: string
  yearly_data: SalaryYearData[]
  total_gross: number
  total_net: number
}

interface SalaryData {
  employees: SalaryEmployee[]
  total_gross_income: number
  total_net_income: number
  employee_count: number
}

interface WeeklyData {
  count: number
  amount: number
}

interface SymbolWeeklyData {
  week1: WeeklyData
  week2: WeeklyData
  week3: WeeklyData
  week4: WeeklyData
  week5: WeeklyData
  total_count: number
  total_amount: number
}

interface WeeklyBreakdownData {
  account_name: string
  month: string
  month_formatted: string
  month_total: number
  weekly_data: Record<string, SymbolWeeklyData>
  symbols: string[]
  weekly_totals: {
    week1: number
    week2: number
    week3: number
    week4: number
    week5: number
  }
  weekly_counts: {
    week1: number
    week2: number
    week3: number
    week4: number
    week5: number
  }
  transaction_count: number
}

interface AccountOptionsDetailData {
  account_name: string
  owner: string
  account_type: string
  total_income: number
  monthly: Record<string, number>
  available_months: string[]
  transactions: Array<{
    date: string
    symbol: string
    description: string
    trans_code: string
    quantity: number
    price: number
    amount: number
    option_type: string
    strike: number | null
    expiry: string | null
  }>
  transaction_count: number
}

// Helper functions
const formatCurrency = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '$0'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

const formatCurrencyPrecise = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// Format month key (e.g., "2025-11") to display format (e.g., "Nov 2025")
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const formatMonthKey = (monthKey: string) => {
  const [yearStr, monthStr] = monthKey.split('-')
  const monthNum = parseInt(monthStr)
  return `${MONTH_NAMES[monthNum - 1]} ${yearStr}`
}

// Sort and filter accounts in the proper order
// Order: Neel's Brokerage → Neel's Retirement → Neel's Roth IRA → Jaya's Brokerage → Jaya's Retirement → Jaya's Roth IRA → Alisha's Brokerage → Agrawal Family HSA
const ACCOUNT_ORDER: Record<string, number> = {
  "Neel's Brokerage": 1,
  "Neel's Retirement": 2,
  "Neel's Roth IRA": 3,
  "Jaya's Brokerage": 4,
  "Jaya's Retirement": 5,
  "Jaya's IRA": 6,
  "Jaya's Roth IRA": 7,
  "Alisha's Brokerage": 8,
  "Agrawal Family HSA": 9,
}

const HIDDEN_ACCOUNTS = ['robinhood_default']

function sortAndFilterAccounts<T>(accounts: Record<string, T>): Array<[string, T]> {
  return Object.entries(accounts)
    .filter(([name]) => !HIDDEN_ACCOUNTS.includes(name))
    .sort(([a], [b]) => {
      const orderA = ACCOUNT_ORDER[a] ?? 100
      const orderB = ACCOUNT_ORDER[b] ?? 100
      return orderA - orderB
    })
}

// Custom Tooltip for Charts
interface ChartTooltipProps {
  active?: boolean
  payload?: Array<{ value: number; payload: MonthlyData }>
  label?: string
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

// Income Source Card Component
interface SourceCardProps {
  source: IncomeSource
  onClick: () => void
}

function SourceCard({ source, onClick }: SourceCardProps) {
  const Icon = source.icon
  const isActive = source.status === 'active'
  const hasValue = source.value !== undefined && source.value > 0

  return (
    <button
      className={clsx(styles.sourceCard, isActive ? styles.active : styles.pending)}
      onClick={onClick}
    >
      <div className={styles.sourceHeader}>
        <div
          className={styles.sourceIcon}
          style={{ background: `${source.color}20`, color: source.color }}
        >
          <Icon size={24} />
        </div>
        <div className={styles.sourceInfo}>
          <h3 className={styles.sourceName}>{source.name}</h3>
          <span className={styles.sourceType}>{source.type}</span>
        </div>
      </div>

      {hasValue ? (
        <div className={clsx(styles.sourceValue, styles.positive)}>
          {formatCurrency(source.value!)}
        </div>
      ) : (
        <div className={styles.sourceValue}>—</div>
      )}

      <p className={styles.sourceDescription}>{source.description}</p>

      <div className={clsx(styles.sourceBadge, isActive ? styles.active : styles.pending)}>
        {isActive ? (
          <>
            <CheckCircle size={12} />
            Active
          </>
        ) : (
          <>
            <Clock size={12} />
            Pending Upload
          </>
        )}
      </div>
    </button>
  )
}

// Account Card Component
interface AccountCardProps {
  account: AccountIncome
  onClick: () => void
  color: string
}

function AccountCard({ account, onClick, color }: AccountCardProps) {
  return (
    <button className={styles.accountCard} onClick={onClick}>
      <div className={styles.accountHeader}>
        <div
          className={styles.accountIcon}
          style={{ background: `${color}20`, color: color }}
        >
          <User size={20} />
        </div>
        <div>
          <h3 className={styles.accountName}>{account.name}</h3>
          <span className={styles.accountType}>
            {account.type === 'retirement' ? 'Retirement' : 'Individual'}
          </span>
        </div>
      </div>

      <div className={styles.accountStats}>
        <div className={styles.accountStat}>
          <span className={styles.accountStatLabel}>Options</span>
          <span className={styles.accountStatValue}>
            {formatCurrency(account.options_income)}
          </span>
        </div>
        <div className={styles.accountStat}>
          <span className={styles.accountStatLabel}>Dividends</span>
          <span className={styles.accountStatValue} style={{ color: '#00A3FF' }}>
            {formatCurrency(account.dividend_income)}
          </span>
        </div>
        <div className={styles.accountStat}>
          <span className={styles.accountStatLabel}>Interest</span>
          <span className={styles.accountStatValue} style={{ color: '#FFB800' }}>
            {formatCurrency(account.interest_income)}
          </span>
        </div>
        <div className={styles.accountStat}>
          <span className={styles.accountStatLabel}>Total</span>
          <span className={styles.accountStatValue} style={{ color: color }}>
            {formatCurrency(account.total)}
          </span>
        </div>
      </div>
      
      <div className={styles.viewDetails}>
        View Charts →
      </div>
    </button>
  )
}

// Options Detail View
interface OptionsDetailProps {
  data: OptionsData
  chartData: MonthlyData[]
  onBack: () => void
}

function OptionsDetail({ data, chartData, onBack }: OptionsDetailProps) {
  const [selectedYear, setSelectedYear] = useState(2025)
  
  const filteredChartData = chartData.filter(d => d.year === selectedYear)
  const years = [...new Set(chartData.map(d => d.year))].sort((a, b) => b - a)
  
  // Calculate year-filtered total from chart data
  const yearFilteredTotal = filteredChartData.reduce((sum, d) => sum + d.value, 0)
  
  // Calculate year-filtered account totals from monthly data
  const getAccountYearTotal = (account: { monthly?: Record<string, number> }) => {
    if (!account.monthly) return 0
    return Object.entries(account.monthly)
      .filter(([month]) => month.startsWith(`${selectedYear}-`))
      .reduce((sum, [, value]) => sum + value, 0)
  }
  
  // Filter transactions by year
  const filteredTransactions = data.transactions.filter(txn => 
    txn.date.startsWith(`${selectedYear}`)
  )

  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Income
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ background: 'rgba(0, 214, 50, 0.15)', color: '#00D632' }}
        >
          <TrendingUp size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>Options Income</h1>
          <span className={styles.detailType}>
            Premium income from selling calls and puts across all accounts
          </span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount}>{formatCurrency(yearFilteredTotal)}</div>
          <span className={styles.detailType}>{selectedYear}</span>
        </div>
      </div>

      {/* Options Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Options Income</h2>
        </div>

        <div className={styles.yearSelector}>
          {years.map(year => (
            <button
              key={year}
              className={clsx(styles.yearButton, selectedYear === year && styles.active)}
              onClick={() => setSelectedYear(year)}
            >
              {year}
            </button>
          ))}
        </div>

        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={filteredChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
              <Bar
                dataKey="value"
                fill="#00D632"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Account Breakdown */}
      <section className={styles.accountsSection}>
        <h2>By Account ({selectedYear})</h2>
        <div className={styles.accountsGrid}>
          {sortAndFilterAccounts(data.by_account)
            .map(([name, account]) => {
              const yearTotal = getAccountYearTotal(account)
              if (yearTotal === 0) return null // Hide accounts with no income for selected year
              return (
                <div key={name} className={styles.accountCard} style={{ cursor: 'default' }}>
                  <div className={styles.accountHeader}>
                    <div
                      className={styles.accountIcon}
                      style={{
                        background: account.owner === 'Neel' ? 'rgba(0, 163, 255, 0.15)' : 'rgba(168, 85, 247, 0.15)',
                        color: account.owner === 'Neel' ? '#00A3FF' : '#A855F7'
                      }}
                    >
                      <User size={20} />
                    </div>
                    <div>
                      <h3 className={styles.accountName}>{name}</h3>
                      <span className={styles.accountType}>
                        {selectedYear}
                      </span>
                    </div>
                  </div>
                  <div className={styles.accountStats}>
                    <div className={styles.accountStat}>
                      <span className={styles.accountStatLabel}>Total</span>
                      <span className={styles.accountStatValue}>
                        {formatCurrency(yearTotal)}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })
            .filter(Boolean)}
        </div>
      </section>

      {/* Recent Transactions */}
      <section className={styles.transactionsSection}>
        <h2>Transactions ({filteredTransactions.length})</h2>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Description</th>
                <th>Account</th>
                <th className={styles.alignRight}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.slice(0, 50).map((txn, i) => (
                <tr key={i}>
                  <td>{formatDate(txn.date)}</td>
                  <td className={styles.symbolCell}>{txn.symbol}</td>
                  <td>
                    <span className={clsx(
                      styles.transCodeBadge,
                      txn.trans_code === 'STO' && styles.sto,
                      txn.trans_code === 'BTC' && styles.btc,
                      txn.trans_code === 'OEXP' && styles.oexp,
                    )}>
                      {txn.trans_code}
                    </span>
                  </td>
                  <td>{txn.description.slice(0, 40)}...</td>
                  <td>{txn.account}</td>
                  <td className={clsx(
                    styles.alignRight,
                    styles.amountCell,
                    txn.amount >= 0 ? styles.positive : styles.negative
                  )}>
                    {formatCurrencyPrecise(txn.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

// Dividends Detail View
interface DividendsDetailProps {
  data: DividendData
  chartData: MonthlyData[]
  onBack: () => void
}

function DividendsDetail({ data, chartData, onBack }: DividendsDetailProps) {
  const [selectedYear, setSelectedYear] = useState(2025)
  
  const filteredChartData = chartData.filter(d => d.year === selectedYear)
  const years = [...new Set(chartData.map(d => d.year))].sort((a, b) => b - a)
  
  // Calculate year-filtered total from chart data
  const yearFilteredTotal = filteredChartData.reduce((sum, d) => sum + d.value, 0)
  
  // Calculate year-filtered account totals from monthly data
  const getAccountYearTotal = (account: { monthly?: Record<string, number> }) => {
    if (!account.monthly) return 0
    return Object.entries(account.monthly)
      .filter(([month]) => month.startsWith(`${selectedYear}-`))
      .reduce((sum, [, value]) => sum + value, 0)
  }
  
  // Filter transactions by year
  const filteredTransactions = data.transactions.filter(txn => 
    txn.date.startsWith(`${selectedYear}`)
  )

  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Income
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ background: 'rgba(0, 163, 255, 0.15)', color: '#00A3FF' }}
        >
          <DollarSign size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>Dividend Income</h1>
          <span className={styles.detailType}>
            Quarterly dividend payments from stocks across all accounts
          </span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount}>{formatCurrency(yearFilteredTotal)}</div>
          <span className={styles.detailType}>{selectedYear}</span>
        </div>
      </div>

      {/* Dividend Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Dividend Income</h2>
        </div>

        <div className={styles.yearSelector}>
          {years.map(year => (
            <button
              key={year}
              className={clsx(styles.yearButton, selectedYear === year && styles.active)}
              onClick={() => setSelectedYear(year)}
            >
              {year}
            </button>
          ))}
        </div>

        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={filteredChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                dx={-10}
                width={60}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="value"
                fill="#00A3FF"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* By Symbol - calculated from filtered transactions */}
      <section className={styles.bySymbolSection}>
        <h2>Dividends by Stock ({selectedYear})</h2>
        <div className={styles.symbolGrid}>
          {(() => {
            // Calculate by-symbol totals from filtered transactions
            const symbolTotals: Record<string, number> = {}
            filteredTransactions.forEach(txn => {
              if (txn.symbol) {
                symbolTotals[txn.symbol] = (symbolTotals[txn.symbol] || 0) + txn.amount
              }
            })
            return Object.entries(symbolTotals)
              .sort(([, a], [, b]) => b - a) // Sort by amount descending
              .slice(0, 12)
              .map(([symbol, amount]) => (
                <div key={symbol} className={styles.symbolCard}>
                  <span className={styles.symbolName}>{symbol}</span>
                  <span className={styles.symbolAmount}>{formatCurrencyPrecise(amount)}</span>
                </div>
              ))
          })()}
        </div>
      </section>

      {/* Recent Transactions */}
      <section className={styles.transactionsSection}>
        <h2>Dividend Payments ({filteredTransactions.length})</h2>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Symbol</th>
                <th>Account</th>
                <th className={styles.alignRight}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.slice(0, 30).map((txn, i) => (
                <tr key={i}>
                  <td>{formatDate(txn.date)}</td>
                  <td className={styles.symbolCell}>{txn.symbol}</td>
                  <td>{txn.account}</td>
                  <td className={clsx(styles.alignRight, styles.amountCell, styles.positive)}>
                    {formatCurrencyPrecise(txn.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

// Interest Detail View
interface InterestDetailProps {
  data: InterestData
  chartData: MonthlyData[]
  onBack: () => void
}

function InterestDetail({ data, chartData, onBack }: InterestDetailProps) {
  const [selectedYear, setSelectedYear] = useState(2025)
  
  const filteredChartData = chartData.filter(d => d.year === selectedYear)
  const years = [...new Set(chartData.map(d => d.year))].sort((a, b) => b - a)
  
  // Calculate year-filtered total from chart data
  const yearFilteredTotal = filteredChartData.reduce((sum, d) => sum + d.value, 0)
  
  // Calculate year-filtered account totals from monthly data
  const getAccountYearTotal = (account: { monthly?: Record<string, number> }) => {
    if (!account.monthly) return 0
    return Object.entries(account.monthly)
      .filter(([month]) => month.startsWith(`${selectedYear}-`))
      .reduce((sum, [, value]) => sum + value, 0)
  }
  
  // Filter transactions by year
  const filteredTransactions = data.transactions.filter(txn => 
    txn.date.startsWith(`${selectedYear}`)
  )

  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Income
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ background: 'rgba(255, 184, 0, 0.15)', color: '#FFB800' }}
        >
          <PiggyBank size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>Interest Income</h1>
          <span className={styles.detailType}>
            Interest earned on cash balances and bank accounts
          </span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount} style={{ color: '#FFB800' }}>
            {formatCurrency(yearFilteredTotal)}
          </div>
          <span className={styles.detailType}>{selectedYear}</span>
        </div>
      </div>

      {/* Interest Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Interest Income</h2>
        </div>

        <div className={styles.yearSelector}>
          {years.map(year => (
            <button
              key={year}
              className={clsx(styles.yearButton, selectedYear === year && styles.active)}
              onClick={() => setSelectedYear(year)}
            >
              {year}
            </button>
          ))}
        </div>

        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={filteredChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                dx={-10}
                width={60}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar
                dataKey="value"
                fill="#FFB800"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Account Breakdown */}
      <section className={styles.accountsSection}>
        <h2>By Account ({selectedYear})</h2>
        <div className={styles.accountsGrid}>
          {sortAndFilterAccounts(data.by_account)
            .map(([name, account]) => {
              const yearTotal = getAccountYearTotal(account)
              if (yearTotal === 0) return null // Hide accounts with no income for selected year
              return (
                <div key={name} className={styles.accountCard} style={{ cursor: 'default' }}>
                  <div className={styles.accountHeader}>
                    <div
                      className={styles.accountIcon}
                      style={{
                        background: account.owner === 'Neel' ? 'rgba(0, 163, 255, 0.15)' : 'rgba(168, 85, 247, 0.15)',
                        color: account.owner === 'Neel' ? '#00A3FF' : '#A855F7'
                      }}
                    >
                      <User size={20} />
                    </div>
                    <div>
                      <h3 className={styles.accountName}>{name}</h3>
                      <span className={styles.accountType}>
                        {selectedYear}
                      </span>
                    </div>
                  </div>
                  <div className={styles.accountStats}>
                    <div className={styles.accountStat}>
                      <span className={styles.accountStatLabel}>Total</span>
                      <span className={styles.accountStatValue} style={{ color: '#FFB800' }}>
                        {formatCurrency(yearTotal)}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })
            .filter(Boolean)}
        </div>
      </section>

      {/* Recent Transactions */}
      <section className={styles.transactionsSection}>
        <h2>Interest Payments ({filteredTransactions.length})</h2>
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Account</th>
                <th>Source</th>
                <th className={styles.alignRight}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.slice(0, 50).map((txn, i) => (
                <tr key={i}>
                  <td>{formatDate(txn.date)}</td>
                  <td>{txn.description}</td>
                  <td>{txn.account}</td>
                  <td style={{ textTransform: 'capitalize' }}>{txn.source}</td>
                  <td className={clsx(styles.alignRight, styles.amountCell, styles.positive)}>
                    {formatCurrencyPrecise(txn.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

// Account Options Detail View - Shows monthly chart and weekly breakdown
interface AccountOptionsDetailProps {
  accountName: string
  onBack: () => void
}

function AccountOptionsDetail({ accountName, onBack }: AccountOptionsDetailProps) {
  const [loading, setLoading] = useState(true)
  const [optionsDetail, setOptionsDetail] = useState<AccountOptionsDetailData | null>(null)
  const [weeklyData, setWeeklyData] = useState<WeeklyBreakdownData | null>(null)
  const [selectedMonth, setSelectedMonth] = useState<string>('')
  const [selectedYear, setSelectedYear] = useState(2025)

  // Fetch options detail for this account
  useEffect(() => {
    const fetchOptionsDetail = async () => {
      setLoading(true)
      try {
        const res = await fetch(
          `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/options`,
          { headers: getAuthHeaders() }
        )
        if (res.ok) {
          const data = await res.json()
          setOptionsDetail(data)
          // Set default selected month to most recent
          if (data.available_months && data.available_months.length > 0) {
            setSelectedMonth(data.available_months[0])
          }
        }
      } catch (err) {
        console.error('Error fetching options detail:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchOptionsDetail()
  }, [accountName])

  // Fetch weekly breakdown when month changes
  useEffect(() => {
    if (!selectedMonth) return
    
    const fetchWeeklyData = async () => {
      const [year, month] = selectedMonth.split('-').map(Number)
      try {
        const res = await fetch(
          `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/options/weekly?year=${year}&month=${month}`,
          { headers: getAuthHeaders() }
        )
        if (res.ok) {
          const data = await res.json()
          setWeeklyData(data)
        }
      } catch (err) {
        console.error('Error fetching weekly data:', err)
      }
    }
    fetchWeeklyData()
  }, [accountName, selectedMonth])

  if (loading) {
    return (
      <>
        <button className={styles.backButton} onClick={onBack}>
          <ArrowLeft size={18} />
          Back to Account
        </button>
        <div className={styles.loading}>Loading options data...</div>
      </>
    )
  }

  if (!optionsDetail) {
    return (
      <>
        <button className={styles.backButton} onClick={onBack}>
          <ArrowLeft size={18} />
          Back to Account
        </button>
        <div className={styles.error}>No options data available</div>
      </>
    )
  }

  // Convert monthly data to chart format
  const chartData: MonthlyData[] = optionsDetail.monthly
    ? Object.entries(optionsDetail.monthly)
        .map(([month, value]) => ({
          month,
          formatted: formatMonthKey(month),
          value: value as number,
          year: parseInt(month.split('-')[0]),
        }))
        .sort((a, b) => a.month.localeCompare(b.month))
    : []

  // Get available years from chart data
  const years = [...new Set(chartData.map(d => d.year))].sort((a, b) => b - a)
  const filteredChartData = chartData.filter(d => d.year === selectedYear)

  // Group available months by year for the selector
  const monthsByYear: Record<number, string[]> = {}
  ;(optionsDetail.available_months || []).forEach(month => {
    const year = parseInt(month.split('-')[0])
    if (!monthsByYear[year]) monthsByYear[year] = []
    monthsByYear[year].push(month)
  })

  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Account
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ background: 'rgba(0, 214, 50, 0.15)', color: '#00D632' }}
        >
          <TrendingUp size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>Options Income</h1>
          <span className={styles.detailType}>{accountName}</span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount}>{formatCurrency(optionsDetail.total_income)}</div>
          <span className={styles.detailType}>All Time</span>
        </div>
      </div>

      {/* Monthly Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Options Income</h2>
        </div>

        {years.length > 0 && (
          <div className={styles.yearSelector}>
            {years.map(year => (
              <button
                key={year}
                className={clsx(styles.yearButton, selectedYear === year && styles.active)}
                onClick={() => setSelectedYear(year)}
              >
                {year}
              </button>
            ))}
          </div>
        )}

        {filteredChartData.length > 0 ? (
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={filteredChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
                <Bar dataKey="value" fill="#00D632" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className={styles.chartEmpty}>No options data for {selectedYear}</div>
        )}
      </section>

      {/* Month Selector for Weekly Breakdown */}
      <section className={styles.accountsSection}>
        <h2>Weekly Breakdown</h2>
        <p style={{ color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>
          Select a month to see weekly options income by stock symbol
        </p>
        
        <div className={styles.monthSelector}>
          {Object.entries(monthsByYear)
            .sort(([a], [b]) => parseInt(b) - parseInt(a))
            .map(([year, months]) => (
              <div key={year} className={styles.monthYearGroup}>
                <span className={styles.monthYearLabel}>{year}</span>
                <div className={styles.monthButtons}>
                  {months.map(month => {
                    const monthNum = parseInt(month.split('-')[1])
                    const monthName = new Date(2000, monthNum - 1, 1).toLocaleDateString('en-US', { month: 'short' })
                    return (
                      <button
                        key={month}
                        className={clsx(styles.monthButton, selectedMonth === month && styles.active)}
                        onClick={() => setSelectedMonth(month)}
                      >
                        {monthName}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
        </div>
      </section>

      {/* Weekly Breakdown Table */}
      {weeklyData && (
        <section className={styles.transactionsSection}>
          <div className={styles.weeklyHeader}>
            <h2>{weeklyData.month_formatted}</h2>
            <div className={styles.weeklyTotal}>
              Total: <span style={{ color: '#00D632' }}>{formatCurrency(weeklyData.month_total)}</span>
            </div>
          </div>

          {/* Weekly Summary Row */}
          <div className={styles.weeklySummary}>
            <div className={styles.weekCell}>
              <span className={styles.weekLabel}>Week 1</span>
              <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals.week1)}</span>
              <span className={styles.weekCount}>{weeklyData.weekly_counts.week1} contracts</span>
            </div>
            <div className={styles.weekCell}>
              <span className={styles.weekLabel}>Week 2</span>
              <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals.week2)}</span>
              <span className={styles.weekCount}>{weeklyData.weekly_counts.week2} contracts</span>
            </div>
            <div className={styles.weekCell}>
              <span className={styles.weekLabel}>Week 3</span>
              <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals.week3)}</span>
              <span className={styles.weekCount}>{weeklyData.weekly_counts.week3} contracts</span>
            </div>
            <div className={styles.weekCell}>
              <span className={styles.weekLabel}>Week 4</span>
              <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals.week4)}</span>
              <span className={styles.weekCount}>{weeklyData.weekly_counts.week4} contracts</span>
            </div>
            {weeklyData.weekly_totals.week5 > 0 && (
              <div className={styles.weekCell}>
                <span className={styles.weekLabel}>Week 5</span>
                <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals.week5)}</span>
                <span className={styles.weekCount}>{weeklyData.weekly_counts.week5} contracts</span>
              </div>
            )}
          </div>

          {/* Symbol-by-Week Table */}
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className={styles.alignCenter}>Week 1<br/><span style={{ fontWeight: 400, fontSize: '10px' }}>(1-7)</span></th>
                  <th className={styles.alignCenter}>Week 2<br/><span style={{ fontWeight: 400, fontSize: '10px' }}>(8-14)</span></th>
                  <th className={styles.alignCenter}>Week 3<br/><span style={{ fontWeight: 400, fontSize: '10px' }}>(15-21)</span></th>
                  <th className={styles.alignCenter}>Week 4<br/><span style={{ fontWeight: 400, fontSize: '10px' }}>(22-28)</span></th>
                  {weeklyData.weekly_totals.week5 > 0 && (
                    <th className={styles.alignCenter}>Week 5<br/><span style={{ fontWeight: 400, fontSize: '10px' }}>(29-31)</span></th>
                  )}
                  <th className={styles.alignRight}>Total</th>
                </tr>
              </thead>
              <tbody>
                {weeklyData.symbols.map(symbol => {
                  const data = weeklyData.weekly_data[symbol]
                  return (
                    <tr key={symbol}>
                      <td className={styles.symbolCell}>{symbol}</td>
                      <td className={styles.alignCenter}>
                        {data.week1.count > 0 ? (
                          <div className={styles.weekCellData}>
                            <span className={styles.contractCount}>{data.week1.count}</span>
                            <span className={clsx(styles.cellAmount, data.week1.amount >= 0 ? styles.positive : styles.negative)}>
                              {formatCurrencyPrecise(data.week1.amount)}
                            </span>
                          </div>
                        ) : '-'}
                      </td>
                      <td className={styles.alignCenter}>
                        {data.week2.count > 0 ? (
                          <div className={styles.weekCellData}>
                            <span className={styles.contractCount}>{data.week2.count}</span>
                            <span className={clsx(styles.cellAmount, data.week2.amount >= 0 ? styles.positive : styles.negative)}>
                              {formatCurrencyPrecise(data.week2.amount)}
                            </span>
                          </div>
                        ) : '-'}
                      </td>
                      <td className={styles.alignCenter}>
                        {data.week3.count > 0 ? (
                          <div className={styles.weekCellData}>
                            <span className={styles.contractCount}>{data.week3.count}</span>
                            <span className={clsx(styles.cellAmount, data.week3.amount >= 0 ? styles.positive : styles.negative)}>
                              {formatCurrencyPrecise(data.week3.amount)}
                            </span>
                          </div>
                        ) : '-'}
                      </td>
                      <td className={styles.alignCenter}>
                        {data.week4.count > 0 ? (
                          <div className={styles.weekCellData}>
                            <span className={styles.contractCount}>{data.week4.count}</span>
                            <span className={clsx(styles.cellAmount, data.week4.amount >= 0 ? styles.positive : styles.negative)}>
                              {formatCurrencyPrecise(data.week4.amount)}
                            </span>
                          </div>
                        ) : '-'}
                      </td>
                      {weeklyData.weekly_totals.week5 > 0 && (
                        <td className={styles.alignCenter}>
                          {data.week5.count > 0 ? (
                            <div className={styles.weekCellData}>
                              <span className={styles.contractCount}>{data.week5.count}</span>
                              <span className={clsx(styles.cellAmount, data.week5.amount >= 0 ? styles.positive : styles.negative)}>
                                {formatCurrencyPrecise(data.week5.amount)}
                              </span>
                            </div>
                          ) : '-'}
                        </td>
                      )}
                      <td className={styles.alignRight}>
                        <div className={styles.weekCellData}>
                          <span className={styles.contractCount}>{data.total_count} contracts</span>
                          <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                            {formatCurrency(data.total_amount)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: '2px solid var(--color-border)' }}>
                  <td style={{ fontWeight: 600 }}>TOTAL</td>
                  <td className={styles.alignCenter}>
                    <div className={styles.weekCellData}>
                      <span className={styles.contractCount}>{weeklyData.weekly_counts.week1}</span>
                      <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                        {formatCurrency(weeklyData.weekly_totals.week1)}
                      </span>
                    </div>
                  </td>
                  <td className={styles.alignCenter}>
                    <div className={styles.weekCellData}>
                      <span className={styles.contractCount}>{weeklyData.weekly_counts.week2}</span>
                      <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                        {formatCurrency(weeklyData.weekly_totals.week2)}
                      </span>
                    </div>
                  </td>
                  <td className={styles.alignCenter}>
                    <div className={styles.weekCellData}>
                      <span className={styles.contractCount}>{weeklyData.weekly_counts.week3}</span>
                      <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                        {formatCurrency(weeklyData.weekly_totals.week3)}
                      </span>
                    </div>
                  </td>
                  <td className={styles.alignCenter}>
                    <div className={styles.weekCellData}>
                      <span className={styles.contractCount}>{weeklyData.weekly_counts.week4}</span>
                      <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                        {formatCurrency(weeklyData.weekly_totals.week4)}
                      </span>
                    </div>
                  </td>
                  {weeklyData.weekly_totals.week5 > 0 && (
                    <td className={styles.alignCenter}>
                      <div className={styles.weekCellData}>
                        <span className={styles.contractCount}>{weeklyData.weekly_counts.week5}</span>
                        <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 600 }}>
                          {formatCurrency(weeklyData.weekly_totals.week5)}
                        </span>
                      </div>
                    </td>
                  )}
                  <td className={styles.alignRight}>
                    <span className={clsx(styles.cellAmount, styles.positive)} style={{ fontWeight: 700, fontSize: '16px' }}>
                      {formatCurrency(weeklyData.month_total)}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      )}
    </>
  )
}

// Rental Detail View
interface RentalDetailProps {
  data: RentalData
  chartData: MonthlyData[]
  onBack: () => void
}

function RentalDetail({ data, chartData, onBack }: RentalDetailProps) {
  const property = data.properties[0] // For now, show first property
  
  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Income
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#EC4899' }}
        >
          <Home size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>Rental Income</h1>
          <span className={styles.detailType}>
            {property?.address || 'Property'}
          </span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount} style={{ color: '#EC4899' }}>
            {formatCurrency(data.total_net_income)}
          </div>
          <span className={styles.detailType}>Net Income ({property?.year})</span>
        </div>
      </div>

      {/* Summary Cards */}
      <section className={styles.accountsSection}>
        <h2>Income & Expenses Summary</h2>
        <div className={styles.accountsGrid} style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(0, 214, 50, 0.15)', color: '#00D632' }}>
                <DollarSign size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Gross Income</h3>
                <span className={styles.accountType}>Total rent collected</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatValue}>{formatCurrency(data.total_gross_income)}</span>
              </div>
            </div>
          </div>

          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(255, 90, 90, 0.15)', color: '#FF5A5A' }}>
                <Home size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Property Tax</h3>
                <span className={styles.accountType}>Annual tax</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatValue} style={{ color: '#FF5A5A' }}>
                  -{formatCurrency(data.total_property_tax)}
                </span>
              </div>
            </div>
          </div>

          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(255, 184, 0, 0.15)', color: '#FFB800' }}>
                <Briefcase size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>HOA</h3>
                <span className={styles.accountType}>Annual HOA dues</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatValue} style={{ color: '#FFB800' }}>
                  -{formatCurrency(data.total_hoa)}
                </span>
              </div>
            </div>
          </div>

          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#A855F7' }}>
                <TrendingUp size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Maintenance</h3>
                <span className={styles.accountType}>Repairs & upkeep</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatValue} style={{ color: '#A855F7' }}>
                  -{formatCurrency(data.total_maintenance)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Monthly Rental Income Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Rental Income</h2>
          <div className={styles.chartTotal}>
            Avg: {formatCurrency(data.total_gross_income / 12)}/mo
          </div>
        </div>

        {chartData.length > 0 ? (
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
                <Bar dataKey="value" fill="#EC4899" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className={styles.chartEmpty}>No monthly data available</div>
        )}
      </section>

      {/* Expenses Breakdown */}
      {property && property.expenses.length > 0 && (
        <section className={styles.transactionsSection}>
          <h2>All Expenses ({property.year})</h2>
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Category</th>
                  <th className={styles.alignRight}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {property.expenses.map((expense, i) => (
                  <tr key={i}>
                    <td>{expense.category}</td>
                    <td className={clsx(styles.alignRight, styles.amountCell)} style={{ color: '#FF5A5A' }}>
                      -{formatCurrencyPrecise(expense.amount)}
                    </td>
                  </tr>
                ))}
                <tr style={{ borderTop: '2px solid var(--color-border)', fontWeight: 600 }}>
                  <td>Total Expenses</td>
                  <td className={clsx(styles.alignRight, styles.amountCell)} style={{ color: '#FF5A5A' }}>
                    -{formatCurrencyPrecise(data.total_expenses)}
                  </td>
                </tr>
                <tr style={{ fontWeight: 600 }}>
                  <td style={{ color: '#00D632' }}>Net Income</td>
                  <td className={clsx(styles.alignRight, styles.amountCell)} style={{ color: '#00D632' }}>
                    {formatCurrencyPrecise(data.total_net_income)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Property Details */}
      {property && (
        <section className={styles.accountsSection}>
          <h2>Property Details</h2>
          <div className={styles.accountsGrid} style={{ gridTemplateColumns: '1fr' }}>
            <div className={styles.accountCard} style={{ cursor: 'default' }}>
              <div className={styles.accountHeader}>
                <div className={styles.accountIcon} style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#EC4899' }}>
                  <Home size={20} />
                </div>
                <div>
                  <h3 className={styles.accountName}>{property.address}</h3>
                  <span className={styles.accountType}>Rental Property • Tax Year {property.year}</span>
                </div>
              </div>
              <div className={styles.accountStats} style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <div className={styles.accountStat}>
                  <span className={styles.accountStatLabel}>Cost Basis</span>
                  <span className={styles.accountStatValue}>{formatCurrency(property.cost_basis)}</span>
                </div>
                <div className={styles.accountStat}>
                  <span className={styles.accountStatLabel}>Gross Income</span>
                  <span className={styles.accountStatValue} style={{ color: '#00D632' }}>{formatCurrency(property.gross_income)}</span>
                </div>
                <div className={styles.accountStat}>
                  <span className={styles.accountStatLabel}>Total Expenses</span>
                  <span className={styles.accountStatValue} style={{ color: '#FF5A5A' }}>{formatCurrency(property.total_expenses)}</span>
                </div>
                <div className={styles.accountStat}>
                  <span className={styles.accountStatLabel}>Net Income</span>
                  <span className={styles.accountStatValue} style={{ color: '#EC4899' }}>{formatCurrency(property.net_income)}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}
    </>
  )
}

// Account Detail View
interface AccountDetailProps {
  accountName: string
  optionsData: OptionsData | null
  dividendData: DividendData | null
  interestData: InterestData | null
  onBack: () => void
  onOptionsClick?: () => void
}

function AccountDetail({ accountName, optionsData, dividendData, interestData, onBack, onOptionsClick }: AccountDetailProps) {
  const [selectedYear, setSelectedYear] = useState(2025)
  
  // Get account-specific data
  const accountOptions = optionsData?.by_account[accountName]
  const accountDividends = dividendData?.by_account[accountName]
  const accountInterest = interestData?.by_account[accountName]
  
  // Convert monthly data to chart format
  const optionsChartData: MonthlyData[] = accountOptions?.monthly 
    ? Object.entries(accountOptions.monthly).map(([month, value]) => ({
        month,
        formatted: formatMonthKey(month),
        value: value as number,
        year: parseInt(month.split('-')[0]),
      })).sort((a, b) => a.month.localeCompare(b.month))
    : []
  
  const dividendChartData: MonthlyData[] = accountDividends?.monthly
    ? Object.entries(accountDividends.monthly).map(([month, value]) => ({
        month,
        formatted: formatMonthKey(month),
        value: value as number,
        year: parseInt(month.split('-')[0]),
      })).sort((a, b) => a.month.localeCompare(b.month))
    : []
  
  const interestChartData: MonthlyData[] = accountInterest?.monthly
    ? Object.entries(accountInterest.monthly).map(([month, value]) => ({
        month,
        formatted: formatMonthKey(month),
        value: value as number,
        year: parseInt(month.split('-')[0]),
      })).sort((a, b) => a.month.localeCompare(b.month))
    : []
  
  // Get all available years from all three data sets
  const allYears = new Set([
    ...optionsChartData.map(d => d.year),
    ...dividendChartData.map(d => d.year),
    ...interestChartData.map(d => d.year),
  ])
  const years = [...allYears].sort((a, b) => b - a)
  
  // Filter by selected year
  const filteredOptions = optionsChartData.filter(d => d.year === selectedYear)
  const filteredDividends = dividendChartData.filter(d => d.year === selectedYear)
  const filteredInterest = interestChartData.filter(d => d.year === selectedYear)
  
  // Calculate year-specific totals
  const yearOptionsTotal = filteredOptions.reduce((sum, d) => sum + d.value, 0)
  const yearDividendsTotal = filteredDividends.reduce((sum, d) => sum + d.value, 0)
  const yearInterestTotal = filteredInterest.reduce((sum, d) => sum + d.value, 0)
  const yearTotalIncome = yearOptionsTotal + yearDividendsTotal + yearInterestTotal
  
  // Count transactions for selected year (approximate from monthly data)
  const yearOptionsMonths = filteredOptions.filter(d => d.value !== 0).length
  const yearDividendsMonths = filteredDividends.filter(d => d.value !== 0).length
  const yearInterestMonths = filteredInterest.filter(d => d.value !== 0).length
  
  const owner = accountOptions?.owner || accountDividends?.owner || accountInterest?.owner || 'Unknown'
  const accountType = accountOptions?.account_type || accountDividends?.account_type || accountInterest?.account_type || 'individual'

  return (
    <>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={18} />
        Back to Income
      </button>

      <div className={styles.detailHeader}>
        <div
          className={styles.detailIcon}
          style={{ 
            background: owner === 'Neel' ? 'rgba(0, 163, 255, 0.15)' : 'rgba(168, 85, 247, 0.15)', 
            color: owner === 'Neel' ? '#00A3FF' : '#A855F7' 
          }}
        >
          <User size={32} />
        </div>
        <div className={styles.detailInfo}>
          <h1>{accountName}</h1>
          <span className={styles.detailType}>
            {accountType === 'retirement' ? 'Retirement Account' : 'Individual Brokerage Account'}
          </span>
        </div>
        <div className={styles.detailValue}>
          <div className={styles.detailAmount}>{formatCurrency(yearTotalIncome)}</div>
          <span className={styles.detailType}>{selectedYear} Total</span>
        </div>
      </div>

      {/* Year Selector */}
      {years.length > 0 && (
        <div className={styles.yearSelector} style={{ marginBottom: 'var(--space-6)' }}>
          {years.map(year => (
            <button
              key={year}
              className={clsx(styles.yearButton, selectedYear === year && styles.active)}
              onClick={() => setSelectedYear(year)}
            >
              {year}
            </button>
          ))}
        </div>
      )}

      {/* Three Charts Grid */}
      <div className={styles.chartsGrid}>
        {/* Options Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Options Income</h2>
            <div className={styles.chartTotal}>
              {formatCurrency(yearOptionsTotal)}
            </div>
          </div>

          {filteredOptions.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={filteredOptions} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#00D632" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No options data for {selectedYear}</div>
          )}
        </section>

        {/* Dividends Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Dividend Income</h2>
            <div className={styles.chartTotal} style={{ color: '#00A3FF' }}>
              {formatCurrency(yearDividendsTotal)}
            </div>
          </div>

          {filteredDividends.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={filteredDividends} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${v.toFixed(0)}`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#00A3FF" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No dividend data for {selectedYear}</div>
          )}
        </section>

        {/* Interest Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Interest Income</h2>
            <div className={styles.chartTotal} style={{ color: '#FFB800' }}>
              {formatCurrency(yearInterestTotal)}
            </div>
          </div>

          {filteredInterest.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={filteredInterest} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${v.toFixed(0)}`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#FFB800" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No interest data for {selectedYear}</div>
          )}
        </section>
      </div>

      {/* Income Summary Cards */}
      <section className={styles.accountsSection}>
        <h2>{selectedYear} Income Breakdown</h2>
        <div className={styles.accountsGrid} style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <button 
            className={styles.accountCard} 
            onClick={onOptionsClick}
            style={{ cursor: onOptionsClick ? 'pointer' : 'default' }}
          >
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(0, 214, 50, 0.15)', color: '#00D632' }}>
                <TrendingUp size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Options</h3>
                <span className={styles.accountType}>{yearOptionsMonths} months with income</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatLabel}>{selectedYear} Total</span>
                <span className={styles.accountStatValue}>{formatCurrency(yearOptionsTotal)}</span>
              </div>
            </div>
            {onOptionsClick && (
              <div className={styles.viewDetails}>
                View Weekly Breakdown →
              </div>
            )}
          </button>

          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(0, 163, 255, 0.15)', color: '#00A3FF' }}>
                <DollarSign size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Dividends</h3>
                <span className={styles.accountType}>{yearDividendsMonths} months with income</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatLabel}>{selectedYear} Total</span>
                <span className={styles.accountStatValue} style={{ color: '#00A3FF' }}>{formatCurrency(yearDividendsTotal)}</span>
              </div>
            </div>
          </div>

          <div className={styles.accountCard} style={{ cursor: 'default' }}>
            <div className={styles.accountHeader}>
              <div className={styles.accountIcon} style={{ background: 'rgba(255, 184, 0, 0.15)', color: '#FFB800' }}>
                <PiggyBank size={20} />
              </div>
              <div>
                <h3 className={styles.accountName}>Interest</h3>
                <span className={styles.accountType}>{yearInterestMonths} months with income</span>
              </div>
            </div>
            <div className={styles.accountStats}>
              <div className={styles.accountStat}>
                <span className={styles.accountStatLabel}>{selectedYear} Total</span>
                <span className={styles.accountStatValue} style={{ color: '#FFB800' }}>{formatCurrency(yearInterestTotal)}</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}

// Salary Detail Component
interface SalaryDetailProps {
  employeeName: string
  onBack: () => void
}

function SalaryDetail({ employeeName, onBack }: SalaryDetailProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<any>(null)
  const [selectedYear, setSelectedYear] = useState<number | 'all'>('all')

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await fetch(
          `${API_BASE}/income/salary/employee/${employeeName.toLowerCase().replace(/['\s]/g, '_')}`,
          { headers: getAuthHeaders() }
        )
        if (res.ok) {
          const result = await res.json()
          setData(result)
        }
      } catch (err) {
        console.error('Error fetching salary detail:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [employeeName])

  if (loading) {
    return (
      <div className={styles.detailView}>
        <button className={styles.backButton} onClick={onBack}>
          <ChevronLeft size={20} /> Back to Income
        </button>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading salary data...</p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className={styles.detailView}>
        <button className={styles.backButton} onClick={onBack}>
          <ChevronLeft size={20} /> Back to Income
        </button>
        <div className={styles.chartEmpty}>No salary data found</div>
      </div>
    )
  }

  // Get available years
  const years = data.yearly_summary?.map((y: any) => y.year) || []
  
  // Filter records by selected year
  const filteredRecords = selectedYear === 'all' 
    ? data.records 
    : data.records?.filter((r: any) => r.year === selectedYear) || []

  // Calculate totals for filtered data
  const filteredTotal = filteredRecords.reduce((sum: number, r: any) => sum + r.wages, 0)
  const filteredFederalTax = filteredRecords.reduce((sum: number, r: any) => sum + r.federal_tax, 0)
  const filteredStateTax = filteredRecords.reduce((sum: number, r: any) => sum + r.state_tax, 0)

  return (
    <div className={styles.detailView}>
      <button className={styles.backButton} onClick={onBack}>
        <ChevronLeft size={20} /> Back to Income
      </button>

      <header className={styles.detailHeader}>
        <div className={styles.detailIcon} style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#A855F7' }}>
          <Briefcase size={32} />
        </div>
        <div>
          <h1 className={styles.detailTitle}>{data.employee_name}'s Salary</h1>
          <p className={styles.detailSubtitle}>
            W-2 Income History • {data.years_count} years of records
          </p>
        </div>
      </header>

      {/* Year Filter */}
      <div className={styles.yearFilter}>
        <button
          className={`${styles.yearButton} ${selectedYear === 'all' ? styles.active : ''}`}
          onClick={() => setSelectedYear('all')}
        >
          All Time
        </button>
        {years.map((year: number) => (
          <button
            key={year}
            className={`${styles.yearButton} ${selectedYear === year ? styles.active : ''}`}
            onClick={() => setSelectedYear(year)}
          >
            {year}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Total Wages</span>
          <span className={styles.summaryValue} style={{ color: '#A855F7' }}>
            {formatCurrency(filteredTotal)}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Federal Tax</span>
          <span className={styles.summaryValue} style={{ color: '#FF5A5A' }}>
            {formatCurrency(filteredFederalTax)}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>State Tax</span>
          <span className={styles.summaryValue} style={{ color: '#FFB800' }}>
            {formatCurrency(filteredStateTax)}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Net (Est.)</span>
          <span className={styles.summaryValue} style={{ color: '#00D632' }}>
            {formatCurrency(filteredTotal - filteredFederalTax - filteredStateTax)}
          </span>
        </div>
      </div>

      {/* W-2 Records Table */}
      <section className={styles.accountsSection}>
        <h2>W-2 Records {selectedYear !== 'all' ? `(${selectedYear})` : '(All Years)'}</h2>
        <div className={styles.w2Table}>
          <div className={styles.w2Header}>
            <span>Year</span>
            <span>Employer</span>
            <span>Wages</span>
            <span>Federal Tax</span>
            <span>State Tax</span>
            <span>401(k)</span>
          </div>
          {filteredRecords.map((record: any, idx: number) => (
            <div key={idx} className={styles.w2Row}>
              <span className={styles.w2Year}>{record.year}</span>
              <span className={styles.w2Employer}>
                {record.employer}
                {record.source && record.source.includes('Severance') && (
                  <span className={styles.w2Note}> (includes severance)</span>
                )}
              </span>
              <span className={styles.w2Wages}>{formatCurrency(record.wages)}</span>
              <span className={styles.w2Tax}>{formatCurrency(record.federal_tax)}</span>
              <span className={styles.w2Tax}>{formatCurrency(record.state_tax)}</span>
              <span className={styles.w2Tax}>{formatCurrency(record.retirement_401k)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Yearly Summary Chart */}
      {selectedYear === 'all' && data.yearly_summary && (
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Yearly Wages Trend</h2>
          </div>
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={[...data.yearly_summary].reverse()}
                margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="year"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#737373', fontSize: 12 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#737373', fontSize: 10 }}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(value: number) => [formatCurrency(value), 'Total Wages']}
                  contentStyle={{
                    background: '#1a1a1a',
                    border: '1px solid #333',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="total_wages" fill="#A855F7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  )
}


// Main Income Component
export function Income() {
  const [view, setView] = useState<'main' | 'options' | 'dividends' | 'interest' | 'rental' | 'account' | 'account_options' | 'salary_detail'>('main')
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [selectedEmployee, setSelectedEmployee] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<{
    total_investment_income: number
    options_income: number
    dividend_income: number
    interest_income: number
    stock_lending: number
    accounts: AccountIncome[]
  } | null>(null)
  const [optionsData, setOptionsData] = useState<OptionsData | null>(null)
  const [dividendData, setDividendData] = useState<DividendData | null>(null)
  const [interestData, setInterestData] = useState<InterestData | null>(null)
  const [optionsChartData, setOptionsChartData] = useState<MonthlyData[]>([])
  const [dividendChartData, setDividendChartData] = useState<MonthlyData[]>([])
  const [interestChartData, setInterestChartData] = useState<MonthlyData[]>([])
  const [rentalData, setRentalData] = useState<RentalData | null>(null)
  const [rentalChartData, setRentalChartData] = useState<MonthlyData[]>([])
  const [salaryData, setSalaryData] = useState<SalaryData | null>(null)
  const [mainSelectedYear, setMainSelectedYear] = useState<number | 'all'>(2025)
  const [mainSelectedMonth, setMainSelectedMonth] = useState<number | null>(null) // null = Full Year, 1-12 = specific month

  // Current year for showing month selector
  const currentYear = new Date().getFullYear()

  // Reset month when year changes (unless selecting current year)
  const handleYearChange = (year: number | 'all') => {
    setMainSelectedYear(year)
    if (year !== currentYear) {
      setMainSelectedMonth(null)
    }
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const [summaryRes, optionsRes, dividendsRes, interestRes, optionsChartRes, dividendChartRes, interestChartRes, rentalRes, rentalChartRes, salaryRes] = await Promise.all([
        fetch(`${API_BASE}/income/summary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/dividends`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/interest`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/chart`, { headers: getAuthHeaders() }),  // No start_year - get ALL data
        fetch(`${API_BASE}/income/dividends/chart`, { headers: getAuthHeaders() }),  // No start_year - get ALL data
        fetch(`${API_BASE}/income/interest/chart`, { headers: getAuthHeaders() }),  // No start_year - get ALL data
        fetch(`${API_BASE}/income/rental`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/rental/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/salary`, { headers: getAuthHeaders() }),
      ])

      if (summaryRes.ok) {
        const data = await summaryRes.json()
        setSummary(data)
      }
      if (optionsRes.ok) {
        const data = await optionsRes.json()
        setOptionsData(data)
      }
      if (dividendsRes.ok) {
        const data = await dividendsRes.json()
        setDividendData(data)
      }
      if (interestRes.ok) {
        const data = await interestRes.json()
        setInterestData(data)
      }
      if (optionsChartRes.ok) {
        const data = await optionsChartRes.json()
        setOptionsChartData(data.data || [])
      }
      if (dividendChartRes.ok) {
        const data = await dividendChartRes.json()
        setDividendChartData(data.data || [])
      }
      if (interestChartRes.ok) {
        const data = await interestChartRes.json()
        setInterestChartData(data.data || [])
      }
      if (rentalRes.ok) {
        const data = await rentalRes.json()
        setRentalData(data)
      }
      if (rentalChartRes.ok) {
        const data = await rentalChartRes.json()
        setRentalChartData(data.data || [])
      }
      if (salaryRes.ok) {
        const data = await salaryRes.json()
        setSalaryData(data)
      }
    } catch (err) {
      console.error('Error fetching income data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Calculate available years from all data sources
  const salaryYears = salaryData?.employees?.flatMap(emp => 
    emp.yearly_data?.map(y => y.year) || []
  ) || []
  const rentalYears = rentalData?.properties?.map(p => p.year) || []
  
  const availableYears = [...new Set([
    ...optionsChartData.map(d => d.year),
    ...dividendChartData.map(d => d.year),
    ...interestChartData.map(d => d.year),
    ...salaryYears,
    ...rentalYears,
  ])].sort((a, b) => b - a)

  // Helper to filter chart data by year and optionally month
  const filterChartData = (data: MonthlyData[]) => {
    let filtered = data
    if (mainSelectedYear !== 'all') {
      filtered = filtered.filter(d => d.year === mainSelectedYear)
    }
    if (mainSelectedMonth !== null && mainSelectedYear === currentYear) {
      // d.month is a string like "2025-12", extract the month number
      filtered = filtered.filter(d => {
        const monthNum = parseInt(d.month.split('-')[1], 10)
        return monthNum === mainSelectedMonth
      })
    }
    return filtered
  }

  // Calculate year/month-filtered totals
  const filteredOptionsTotal = filterChartData(optionsChartData).reduce((sum, d) => sum + d.value, 0)
  const filteredDividendTotal = filterChartData(dividendChartData).reduce((sum, d) => sum + d.value, 0)
  const filteredInterestTotal = filterChartData(interestChartData).reduce((sum, d) => sum + d.value, 0)

  // Note: filteredRentalData is calculated later, so we compute rental separately here
  // Rental data doesn't have monthly breakdown, so we can only filter by year
  const filteredRentalTotal = (() => {
    if (!rentalData?.properties) return 0
    let filteredProperties = mainSelectedYear === 'all'
      ? rentalData.properties
      : rentalData.properties.filter(p => p.year === mainSelectedYear)
    // If filtering by month, we need to prorate the rental income (rental is typically yearly)
    // For simplicity, show the full year amount when a specific month is selected
    // (rental income doesn't have monthly granularity in the current data structure)
    return filteredProperties.reduce((sum, p) => sum + p.net_income, 0)
  })()

  // Compute salary total separately as well
  // Use GROSS income to match what the salary source cards display
  // Salary data doesn't have monthly breakdown, so we can only filter by year
  const computedSalaryTotal = (() => {
    if (!salaryData?.employees) return 0
    return salaryData.employees.reduce((total, emp) => {
      if (mainSelectedYear === 'all') {
        return total + emp.total_gross
      }
      const yearData = emp.yearly_data.find(y => y.year === mainSelectedYear)
      // Salary doesn't have monthly granularity - show full year amount
      return total + (yearData?.gross || 0)
    }, 0)
  })()

  const filteredTotalIncome = filteredOptionsTotal + filteredDividendTotal + filteredInterestTotal + filteredRentalTotal + computedSalaryTotal

  // Filter chart data by selected year and month
  const mainFilteredOptionsChart = filterChartData(optionsChartData)
  const mainFilteredDividendChart = filterChartData(dividendChartData)
  const mainFilteredInterestChart = filterChartData(interestChartData)

  // Calculate year/month-filtered account totals
  const getYearFilteredAccountData = () => {
    if (!summary?.accounts) return []
    
    return summary.accounts
      .filter(account => !HIDDEN_ACCOUNTS.includes(account.name))
      .map(account => {
        // Get monthly data for this account from each income type
        const optionsMonthly = optionsData?.by_account[account.name]?.monthly || {}
        const dividendMonthly = dividendData?.by_account[account.name]?.monthly || {}
        const interestMonthly = interestData?.by_account[account.name]?.monthly || {}
        
        // Filter by year and optionally by month, then sum
        const filterAndSum = (monthly: Record<string, number>) => {
          return Object.entries(monthly)
            .filter(([monthKey]) => {
              // monthKey format is "YYYY-MM" e.g. "2025-12"
              if (mainSelectedYear === 'all') return true
              if (!monthKey.startsWith(String(mainSelectedYear))) return false
              // If filtering by specific month
              if (mainSelectedMonth !== null && mainSelectedYear === currentYear) {
                const monthNum = parseInt(monthKey.split('-')[1], 10)
                return monthNum === mainSelectedMonth
              }
              return true
            })
            .reduce((sum, [, value]) => sum + value, 0)
        }
        
        const filteredOptions = filterAndSum(optionsMonthly)
        const filteredDividends = filterAndSum(dividendMonthly)
        const filteredInterest = filterAndSum(interestMonthly)
        
        return {
          ...account,
          options_income: filteredOptions,
          dividend_income: filteredDividends,
          interest_income: filteredInterest,
          total: filteredOptions + filteredDividends + filteredInterest,
        }
      })
      .sort((a, b) => {
        // Sort by defined account order
        const orderA = ACCOUNT_ORDER[a.name] ?? 100
        const orderB = ACCOUNT_ORDER[b.name] ?? 100
        return orderA - orderB
      })
  }
  
  const filteredAccounts = getYearFilteredAccountData()

  // Calculate year-filtered rental data
  const getYearFilteredRentalData = () => {
    if (!rentalData?.properties) return null
    
    // Filter properties by year
    const filteredProperties = mainSelectedYear === 'all'
      ? rentalData.properties
      : rentalData.properties.filter(p => p.year === mainSelectedYear)
    
    if (filteredProperties.length === 0) return null
    
    // Get unique property addresses
    const uniqueAddresses = new Set(filteredProperties.map(p => p.address))
    
    return {
      ...rentalData,
      properties: filteredProperties,
      property_count: uniqueAddresses.size,
      total_gross_income: filteredProperties.reduce((sum, p) => sum + p.gross_income, 0),
      total_expenses: filteredProperties.reduce((sum, p) => sum + p.total_expenses, 0),
      total_net_income: filteredProperties.reduce((sum, p) => sum + p.net_income, 0),
      total_property_tax: filteredProperties.reduce((sum, p) => sum + p.property_tax, 0),
      total_hoa: filteredProperties.reduce((sum, p) => sum + p.hoa, 0),
      total_maintenance: filteredProperties.reduce((sum, p) => sum + p.maintenance, 0),
    }
  }
  
  const filteredRentalData = getYearFilteredRentalData()

  // Calculate year-filtered salary data
  const getYearFilteredSalaryTotal = () => {
    if (!salaryData?.employees) return 0
    
    return salaryData.employees.reduce((total, emp) => {
      if (mainSelectedYear === 'all') {
        return total + emp.total_net
      }
      const yearData = emp.yearly_data.find(y => y.year === mainSelectedYear)
      return total + (yearData?.net || 0)
    }, 0)
  }
  
  const filteredSalaryTotal = getYearFilteredSalaryTotal()

  // Get Jaya's salary data for specific year
  const getJayaSalary = () => {
    const jaya = salaryData?.employees.find(e => e.name.toLowerCase().includes('jaya'))
    if (!jaya) return null
    
    if (mainSelectedYear === 'all') {
      return { net: jaya.total_net, gross: jaya.total_gross, employer: jaya.employer }
    }
    const yearData = jaya.yearly_data.find(y => y.year === mainSelectedYear)
    return yearData ? { net: yearData.net, gross: yearData.gross, employer: jaya.employer } : null
  }
  
  const jayaSalary = getJayaSalary()

  // Get Neel's salary data for specific year
  const getNeelSalary = () => {
    const neel = salaryData?.employees.find(e => e.name.toLowerCase().includes('neel'))
    if (!neel) return null
    
    if (mainSelectedYear === 'all') {
      return { net: neel.total_net, gross: neel.total_gross, employer: neel.employer }
    }
    const yearData = neel.yearly_data.find(y => y.year === mainSelectedYear)
    return yearData ? { net: yearData.net, gross: yearData.gross, employer: neel.employer } : null
  }
  
  const neelSalary = getNeelSalary()

  // Build income sources list
  const incomeSources: IncomeSource[] = [
    {
      id: 'salary_jaya',
      name: "Jaya's Salary",
      type: 'salary',
      status: jayaSalary && jayaSalary.gross > 0 ? 'active' : 'pending_upload',
      value: jayaSalary?.gross || 0,
      description: jayaSalary 
        ? `${jayaSalary.employer} • Gross W-2 wages`
        : 'W2 income - awaiting file upload',
      icon: Briefcase,
      color: '#A855F7',
    },
    {
      id: 'salary_neel',
      name: "Neel's Salary",
      type: 'salary',
      status: neelSalary && neelSalary.gross > 0 ? 'active' : 'pending_upload',
      value: neelSalary?.gross || 0,
      description: neelSalary 
        ? `${neelSalary.employer} • Gross W-2 wages`
        : 'W2 income - awaiting file upload',
      icon: Briefcase,
      color: '#00A3FF',
    },
    {
      id: 'rental_income',
      name: 'Rental Income',
      type: 'rental',
      status: filteredRentalData && filteredRentalData.property_count > 0 ? 'active' : 'pending_upload',
      value: filteredRentalData?.total_net_income || 0,
      description: filteredRentalData 
        ? `${filteredRentalData.property_count} property • Net of taxes, HOA, maintenance`
        : 'Property rental income (net of taxes, HOA, maintenance)',
      icon: Home,
      color: '#EC4899',
    },
    {
      id: 'options_income',
      name: 'Options Income',
      type: 'investment',
      status: 'active',
      value: filteredOptionsTotal,
      description: 'Premium from selling covered calls and cash-secured puts',
      icon: TrendingUp,
      color: '#00D632',
    },
    {
      id: 'dividend_income',
      name: 'Dividend Income',
      type: 'investment',
      status: 'active',
      value: filteredDividendTotal,
      description: 'Quarterly dividend payments from stocks',
      icon: DollarSign,
      color: '#00A3FF',
    },
    {
      id: 'interest_income',
      name: 'Interest Income',
      type: 'investment',
      status: 'active',
      value: filteredInterestTotal,
      description: 'Interest earned on cash balances and bank accounts',
      icon: PiggyBank,
      color: '#FFB800',
    },
  ]

  // Loading state
  if (loading) {
  return (
    <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading income data...</p>
      </div>
    </div>
  )
}

  // Options detail view
  if (view === 'options' && optionsData) {
    return (
      <div className={styles.page}>
        <OptionsDetail
          data={optionsData}
          chartData={optionsChartData}
          onBack={() => setView('main')}
        />
      </div>
    )
  }

  // Dividends detail view
  if (view === 'dividends' && dividendData) {
    return (
      <div className={styles.page}>
        <DividendsDetail
          data={dividendData}
          chartData={dividendChartData}
          onBack={() => setView('main')}
        />
      </div>
    )
  }

  // Interest detail view
  if (view === 'interest' && interestData) {
    return (
      <div className={styles.page}>
        <InterestDetail
          data={interestData}
          chartData={interestChartData}
          onBack={() => setView('main')}
        />
      </div>
    )
  }

  // Rental detail view
  if (view === 'rental' && rentalData) {
    // Filter rental chart data by selected year
    const filteredRentalChart = mainSelectedYear === 'all'
      ? rentalChartData
      : rentalChartData.filter(d => d.year === mainSelectedYear)
    
    return (
      <div className={styles.page}>
        <RentalDetail
          data={filteredRentalData!}
          chartData={filteredRentalChart}
          onBack={() => setView('main')}
        />
      </div>
    )
  }

  // Account detail view
  if (view === 'account' && selectedAccount) {
    return (
      <div className={styles.page}>
        <AccountDetail
          accountName={selectedAccount}
          optionsData={optionsData}
          dividendData={dividendData}
          interestData={interestData}
          onBack={() => {
            setView('main')
            setSelectedAccount(null)
          }}
          onOptionsClick={() => setView('account_options')}
        />
      </div>
    )
  }

  // Account Options detail view
  if (view === 'account_options' && selectedAccount) {
    return (
      <div className={styles.page}>
        <AccountOptionsDetail
          accountName={selectedAccount}
          onBack={() => setView('account')}
        />
      </div>
    )
  }

  // Salary detail view
  if (view === 'salary_detail' && selectedEmployee) {
    return (
      <div className={styles.page}>
        <SalaryDetail
          employeeName={selectedEmployee}
          onBack={() => {
            setView('main')
            setSelectedEmployee(null)
          }}
        />
      </div>
    )
  }

  // Main view
  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>
            Total Income {mainSelectedYear === 'all' 
              ? '(All Time)' 
              : mainSelectedMonth !== null && mainSelectedYear === currentYear
                ? `(${new Date(currentYear, mainSelectedMonth - 1).toLocaleString('default', { month: 'long' })} ${mainSelectedYear})`
                : `(${mainSelectedYear})`}
          </div>
          <div className={styles.heroValue}>
            {formatCurrency(filteredTotalIncome)}
          </div>
          <div className={styles.heroSubtext}>
            Across {summary?.accounts.length || 0} investment accounts
          </div>

          <div className={styles.heroBreakdown}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Options</span>
              <span className={styles.heroStatValue}>
                {formatCurrency(filteredOptionsTotal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Dividends</span>
              <span className={styles.heroStatValue}>
                {formatCurrency(filteredDividendTotal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Interest</span>
              <span className={styles.heroStatValue}>
                {formatCurrency(filteredInterestTotal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Rental</span>
              <span className={styles.heroStatValue}>
                {formatCurrency(filteredRentalTotal)}
              </span>
            </div>
            {computedSalaryTotal > 0 && (
              <div className={styles.heroStat}>
                <span className={styles.heroStatLabel}>Salary</span>
                <span className={styles.heroStatValue}>
                  {formatCurrency(computedSalaryTotal)}
                </span>
              </div>
            )}
          </div>

          {/* Year Selector */}
          <div className={styles.yearSelector} style={{ marginTop: 'var(--space-4)' }}>
            <button
              className={clsx(styles.yearButton, mainSelectedYear === 'all' && styles.active)}
              onClick={() => handleYearChange('all')}
            >
              All Time
            </button>
            {availableYears.map(year => (
              <button
                key={year}
                className={clsx(styles.yearButton, mainSelectedYear === year && styles.active)}
                onClick={() => handleYearChange(year)}
              >
                {year}
              </button>
            ))}
          </div>

          {/* Month Selector - only show for current year */}
          {mainSelectedYear === currentYear && (
            <div className={styles.monthSelectorRow}>
              <button
                className={clsx(styles.monthPill, mainSelectedMonth === null && styles.active)}
                onClick={() => setMainSelectedMonth(null)}
              >
                Full Year
              </button>
              {[12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map(month => (
                <button
                  key={month}
                  className={clsx(styles.monthPill, mainSelectedMonth === month && styles.active)}
                  onClick={() => setMainSelectedMonth(month)}
                >
                  {new Date(currentYear, month - 1).toLocaleString('default', { month: 'short' })}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={fetchData} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={20} />
        </button>
      </section>

      {/* Income Sources */}
      <section className={styles.sourcesSection}>
        <h2>Income Sources</h2>
        <div className={styles.sourcesGrid}>
          {incomeSources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              onClick={() => {
                if (source.id === 'options_income') {
                  setView('options')
                } else if (source.id === 'dividend_income') {
                  setView('dividends')
                } else if (source.id === 'interest_income') {
                  setView('interest')
                } else if (source.id === 'rental_income' && filteredRentalData) {
                  setView('rental')
                } else if (source.id === 'salary_jaya') {
                  setSelectedEmployee('Jaya')
                  setView('salary_detail')
                } else if (source.id === 'salary_neel') {
                  setSelectedEmployee('Neel')
                  setView('salary_detail')
                }
              }}
            />
          ))}
        </div>
      </section>

      {/* Charts Side by Side */}
      <div className={styles.chartsGrid}>
        {/* Options Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Options Income</h2>
            <div className={styles.chartTotal}>
              {formatCurrency(filteredOptionsTotal)}
            </div>
          </div>

          {mainFilteredOptionsChart.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={mainFilteredOptionsChart}
                  margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#00D632" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No options data available</div>
          )}

          <button
            className={styles.backButton}
            style={{ marginTop: 'var(--space-4)', marginBottom: 0 }}
            onClick={() => setView('options')}
          >
            View Details <ChevronRight size={16} />
          </button>
        </section>

        {/* Dividends Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Dividend Income</h2>
            <div className={styles.chartTotal} style={{ color: '#00A3FF' }}>
              {formatCurrency(filteredDividendTotal)}
            </div>
          </div>

          {mainFilteredDividendChart.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={mainFilteredDividendChart}
                  margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${v.toFixed(0)}`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#00A3FF" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No dividend data available</div>
          )}

          <button
            className={styles.backButton}
            style={{ marginTop: 'var(--space-4)', marginBottom: 0 }}
            onClick={() => setView('dividends')}
          >
            View Details <ChevronRight size={16} />
          </button>
        </section>

        {/* Interest Chart */}
        <section className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <h2>Interest Income</h2>
            <div className={styles.chartTotal} style={{ color: '#FFB800' }}>
              {formatCurrency(filteredInterestTotal)}
            </div>
          </div>

          {mainFilteredInterestChart.length > 0 ? (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={mainFilteredInterestChart}
                  margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="formatted"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    dy={10}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#737373', fontSize: 10 }}
                    tickFormatter={(v) => `$${v.toFixed(0)}`}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="value" fill="#FFB800" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className={styles.chartEmpty}>No interest data available</div>
          )}

          <button
            className={styles.backButton}
            style={{ marginTop: 'var(--space-4)', marginBottom: 0 }}
            onClick={() => setView('interest')}
          >
            View Details <ChevronRight size={16} />
          </button>
        </section>
      </div>

      {/* Account Breakdown */}
      {filteredAccounts.length > 0 && (
        <section className={styles.accountsSection}>
          <h2>By Account {mainSelectedYear === 'all' 
            ? '(All Time)' 
            : mainSelectedMonth !== null && mainSelectedYear === currentYear
              ? `(${new Date(currentYear, mainSelectedMonth - 1).toLocaleString('default', { month: 'long' })} ${mainSelectedYear})`
              : `(${mainSelectedYear})`}</h2>
          <div className={styles.accountsGrid}>
            {filteredAccounts.map((account, index) => {
              const colors = ['#00D632', '#00A3FF', '#A855F7', '#FFB800']
              return (
                <AccountCard
                  key={account.name}
                  account={account}
                  onClick={() => {
                    setSelectedAccount(account.name)
                    setView('account')
                  }}
                  color={colors[index % colors.length]}
                />
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
