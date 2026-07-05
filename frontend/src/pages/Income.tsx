import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
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
  Trash2,
  Plus,
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
  ComposedChart,
  Area,
  Line,
  Legend,
  ReferenceLine,
  Cell,
} from 'recharts'
import styles from './Income.module.css'
import clsx from 'clsx'
import { UnifiedIncomeBand } from '../components/UnifiedIncomeBand/UnifiedIncomeBand'
import { EquitySalesDetail, DrillRange } from '../components/EquitySalesDetail/EquitySalesDetail'
import { GoalsStrip } from '../components/GoalsStrip/GoalsStrip'
import {
  formatCurrency as sharedFormatCurrency,
  formatCurrencyShort,
  ChartTooltip as SharedChartTooltip,
  GRID_PROPS,
} from '../components/charts'
import {
  HoldingsTable,
  symbolColumn,
  sharesColumn,
  priceColumn,
  valueColumn,
  dividendIncomeColumn,
  optionsIncomeColumn,
  totalIncomeColumn,
  totalYieldColumn,
} from '../components/HoldingsTable'
import type { HoldingsRow, ColumnDef } from '../components/HoldingsTable'

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

interface WeekMeta {
  key: string
  label: string
  range: string
}

interface SymbolWeeklyData {
  [weekKey: string]: WeeklyData | number
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
  weeks: WeekMeta[]
  weekly_totals: Record<string, number>
  weekly_counts: Record<string, number>
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

// Helper functions — delegate to shared formatters with NaN guard
const formatCurrency = (value: number) => {
  if (value === undefined || value === null || isNaN(value)) return '$0'
  return sharedFormatCurrency(value)
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

const formatFullCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

const formatYAxis = formatCurrencyShort

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

// Chart tooltip — delegates to shared component
const ChartTooltip = () => <SharedChartTooltip labelKey="formatted" />

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
  initialYear?: number
}

function OptionsDetail({ data, chartData, onBack, initialYear }: OptionsDetailProps) {
  const [selectedYear, setSelectedYear] = useState(initialYear ?? new Date().getFullYear())
  
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
              <CartesianGrid {...GRID_PROPS} />
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
  initialYear?: number
}

function DividendsDetail({ data, chartData, onBack, initialYear }: DividendsDetailProps) {
  const [selectedYear, setSelectedYear] = useState(initialYear ?? new Date().getFullYear())
  
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
              <CartesianGrid {...GRID_PROPS} />
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
  initialYear?: number
}

function InterestDetail({ data, chartData, onBack, initialYear }: InterestDetailProps) {
  const [selectedYear, setSelectedYear] = useState(initialYear ?? new Date().getFullYear())
  
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
              <CartesianGrid {...GRID_PROPS} />
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

// Income holdings table columns - factory to allow dynamic headers
function makeIncomeColumns(periodLabel?: string): ColumnDef[] {
  const suffix = periodLabel ? ` (${periodLabel})` : ''
  return [
    symbolColumn(),
    sharesColumn(),
    priceColumn('Price (Live)'),
    valueColumn(),
    { ...dividendIncomeColumn(), header: `Dividends${suffix}` },
    { ...optionsIncomeColumn(), header: `Options${suffix}` },
    { ...totalIncomeColumn(), header: `Total Income${suffix}` },
    totalYieldColumn(),
  ]
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
  const [holdingsRows, setHoldingsRows] = useState<HoldingsRow[]>([])
  const [holdingsData, setHoldingsData] = useState<any>(null)

  // Single unified time picker state — defaults to current month
  const now = new Date()
  const [filterYear, setFilterYear] = useState<number>(now.getFullYear())
  const [filterMonth, setFilterMonth] = useState<number | null>(now.getMonth() + 1)
  const [allTime, setAllTime] = useState(false)
  const [incomeColumns, setIncomeColumns] = useState<ColumnDef[]>(() => {
    const monthName = now.toLocaleString('default', { month: 'short' })
    return makeIncomeColumns(`${monthName} ${now.getFullYear()}`)
  })
  // Computed: total income for the selected period (sum of holdingsRows)
  const periodTotal = holdingsRows.reduce((sum, r) => sum + (r.totalIncome ?? 0), 0)

  // Computed period label
  const periodLabel = allTime
    ? 'All Time'
    : filterMonth
      ? `${new Date(filterYear, filterMonth - 1).toLocaleString('default', { month: 'long' })} ${filterYear}`
      : `${filterYear}`

  // Fetch options detail and holdings for this account
  useEffect(() => {
    const fetchOptionsDetail = async () => {
      setLoading(true)
      try {
        const [optRes, holdRes] = await Promise.all([
          fetch(`${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/options`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/investments/holdings/live`, { headers: getAuthHeaders() }),
        ])
        if (optRes.ok) {
          const data = await optRes.json()
          setOptionsDetail(data)
        }
        if (holdRes.ok) {
          const holdData = await holdRes.json()
          setHoldingsData(holdData)
        }
      } catch (err) {
        console.error('Error fetching options detail:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchOptionsDetail()
  }, [accountName])

  // Fetch filtered income data + weekly breakdown when time period changes
  useEffect(() => {
    if (!holdingsData) return

    const fetchFilteredIncome = async () => {
      try {
        const params = new URLSearchParams()
        if (!allTime && filterYear) params.set('year', String(filterYear))
        if (!allTime && filterMonth) params.set('month', String(filterMonth))

        const res = await fetch(
          `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/income-by-symbol?${params}`,
          { headers: getAuthHeaders() }
        )
        if (!res.ok) return
        const data = await res.json()
        const optBySymbol: Record<string, number> = data.options_by_symbol || {}
        const divBySymbol: Record<string, number> = data.dividends_by_symbol || {}

        // Build period label for column headers
        let colLabel = 'All Time'
        if (!allTime) {
          if (filterMonth) {
            const monthName = new Date(filterYear, filterMonth - 1).toLocaleString('default', { month: 'short' })
            colLabel = `${monthName} ${filterYear}`
          } else {
            colLabel = String(filterYear)
          }
        }
        setIncomeColumns(makeIncomeColumns(colLabel))

        // Find the matching account
        const acct = (holdingsData.accounts || []).find((a: any) => a.name === accountName)
        if (acct) {
          const rows: HoldingsRow[] = (acct.holdings || [])
            .filter((h: any) => h.symbol !== 'CASH')
            .map((h: any) => {
              const div = divBySymbol[h.symbol] ?? 0
              const opt = optBySymbol[h.symbol] ?? 0
              return {
                symbol: h.symbol,
                shares: h.shares || 0,
                currentPrice: h.currentPrice || 0,
                value: (h.shares || 0) * (h.currentPrice || 0),
                isCash: false,
                dividendIncome: div,
                optionsIncome: opt,
                totalIncome: div + opt,
              }
            })
          setHoldingsRows(rows)
        }
      } catch (err) {
        console.error('Error fetching filtered income:', err)
      }
    }
    fetchFilteredIncome()

    // Also fetch weekly breakdown if a specific month is selected
    if (!allTime && filterMonth) {
      const fetchWeeklyData = async () => {
        try {
          const res = await fetch(
            `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/options/weekly?year=${filterYear}&month=${filterMonth}`,
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
    } else {
      setWeeklyData(null)
    }
  }, [accountName, holdingsData, filterYear, filterMonth, allTime])

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
  const filteredChartData = chartData.filter(d => d.year === filterYear)

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
          <div className={styles.detailAmount}>{formatCurrency(periodTotal)}</div>
          <span className={styles.detailType}>{periodLabel}</span>
        </div>
      </div>

      {/* Unified Time Picker — controls everything on the page */}
      {years.length > 0 && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <div className={styles.yearSelector} style={{ marginBottom: 'var(--space-3)' }}>
            {years.map(y => (
              <button
                key={y}
                className={clsx(styles.yearButton, !allTime && filterYear === y && styles.active)}
                onClick={() => { setAllTime(false); setFilterYear(y); setFilterMonth(null) }}
              >
                {y}
              </button>
            ))}
          </div>
          <div className={styles.monthSelectorRow}>
            <button
              className={clsx(styles.monthPill, allTime && styles.active)}
              onClick={() => { setAllTime(true); setFilterMonth(null) }}
            >
              All Time
            </button>
            <button
              className={clsx(styles.monthPill, !allTime && filterMonth === null && styles.active)}
              onClick={() => { setAllTime(false); setFilterMonth(null) }}
            >
              Full Year
            </button>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(m => (
              <button
                key={m}
                className={clsx(styles.monthPill, !allTime && filterMonth === m && styles.active)}
                onClick={() => { setAllTime(false); setFilterMonth(m) }}
              >
                {new Date(filterYear, m - 1).toLocaleString('default', { month: 'short' })}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Monthly Chart */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Options Income</h2>
        </div>

        {filteredChartData.length > 0 ? (
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={filteredChartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid {...GRID_PROPS} />
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
          <div className={styles.chartEmpty}>No options data for {filterYear}</div>
        )}
      </section>

      {/* Holdings Income Table */}
      {holdingsRows.length > 0 && (
        <section className={styles.transactionsSection}>
          <h2>Income by Holding</h2>
          <HoldingsTable
            rows={holdingsRows}
            columns={incomeColumns}
            defaultSortKey="totalIncome"
          />
        </section>
      )}

      {/* Weekly Breakdown Table — only shown when a specific month is selected */}
      {weeklyData && filterMonth && !allTime && (
        <section className={styles.transactionsSection}>
          <div className={styles.weeklyHeader}>
            <h2>{weeklyData.month_formatted}</h2>
            <div className={styles.weeklyTotal}>
              Total: <span style={{ color: '#00D632' }}>{formatCurrency(weeklyData.month_total)}</span>
            </div>
          </div>

          {/* Weekly Summary Row */}
          <div className={styles.weeklySummary}>
            {weeklyData.weeks.map((week, i) => (
              <div key={week.key} className={styles.weekCell}>
                <span className={styles.weekLabel}>Week {i + 1}</span>
                <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals[week.key] || 0)}</span>
                <span className={styles.weekCount}>{weeklyData.weekly_counts[week.key] || 0} contracts</span>
              </div>
            ))}
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
                <CartesianGrid {...GRID_PROPS} />
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
}

function AccountDetail({ accountName, optionsData, dividendData, interestData, onBack }: AccountDetailProps) {
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear())
  const [selectedMonth, setSelectedMonth] = useState<number | null>(new Date().getMonth() + 1)

  // Holdings table state
  const [holdingsRows, setHoldingsRows] = useState<HoldingsRow[]>([])
  const [holdingsData, setHoldingsData] = useState<any>(null)
  const [weeklyData, setWeeklyData] = useState<WeeklyBreakdownData | null>(null)
  const [incomeColumns, setIncomeColumns] = useState<ColumnDef[]>(() => {
    const now = new Date()
    const monthName = now.toLocaleString('default', { month: 'short' })
    return makeIncomeColumns(`${monthName} ${now.getFullYear()}`)
  })
  
  // Realized equity sales for this account (per-sale, from the lot engine)
  const [acctSales, setAcctSales] = useState<any[]>([])
  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/investments/realized-pnl/sales?year=${selectedYear}`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : { sales: [] }))
      .then(d => { if (!cancelled) setAcctSales((d.sales || []).filter((s: any) => s.account === accountName)) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedYear, accountName])

  // Handle year change - month selection is preserved across year changes
  const handleYearChange = (year: number) => {
    setSelectedYear(year)
  }

  // Fetch holdings data once
  useEffect(() => {
    const fetchHoldings = async () => {
      try {
        const res = await fetch(`${API_BASE}/investments/holdings/live`, { headers: getAuthHeaders() })
        if (res.ok) {
          setHoldingsData(await res.json())
        }
      } catch (err) {
        console.error('Error fetching holdings:', err)
      }
    }
    fetchHoldings()
  }, [accountName])

  // Fetch income-by-symbol + weekly data when time period changes
  useEffect(() => {
    if (!holdingsData) return

    const fetchFilteredIncome = async () => {
      try {
        const params = new URLSearchParams()
        params.set('year', String(selectedYear))
        if (selectedMonth !== null) params.set('month', String(selectedMonth))

        const res = await fetch(
          `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/income-by-symbol?${params}`,
          { headers: getAuthHeaders() }
        )
        if (!res.ok) return
        const data = await res.json()
        const optBySymbol: Record<string, number> = data.options_by_symbol || {}
        const divBySymbol: Record<string, number> = data.dividends_by_symbol || {}

        // Build period label for column headers
        let colLabel: string
        if (selectedMonth !== null) {
          const monthName = new Date(selectedYear, selectedMonth - 1).toLocaleString('default', { month: 'short' })
          colLabel = `${monthName} ${selectedYear}`
        } else {
          colLabel = String(selectedYear)
        }
        setIncomeColumns(makeIncomeColumns(colLabel))

        // Find the matching account
        const acct = (holdingsData.accounts || []).find((a: any) => a.name === accountName)
        if (acct) {
          const rows: HoldingsRow[] = (acct.holdings || [])
            .filter((h: any) => h.symbol !== 'CASH')
            .map((h: any) => {
              const div = divBySymbol[h.symbol] ?? 0
              const opt = optBySymbol[h.symbol] ?? 0
              return {
                symbol: h.symbol,
                shares: h.shares || 0,
                currentPrice: h.currentPrice || 0,
                value: (h.shares || 0) * (h.currentPrice || 0),
                isCash: false,
                dividendIncome: div,
                optionsIncome: opt,
                totalIncome: div + opt,
              }
            })
          setHoldingsRows(rows)
        }
      } catch (err) {
        console.error('Error fetching filtered income:', err)
      }
    }
    fetchFilteredIncome()

    // Fetch weekly breakdown if a specific month is selected
    if (selectedMonth !== null) {
      const fetchWeeklyData = async () => {
        try {
          const res = await fetch(
            `${API_BASE}/income/accounts/${encodeURIComponent(accountName)}/options/weekly?year=${selectedYear}&month=${selectedMonth}`,
            { headers: getAuthHeaders() }
          )
          if (res.ok) {
            setWeeklyData(await res.json())
          }
        } catch (err) {
          console.error('Error fetching weekly data:', err)
        }
      }
      fetchWeeklyData()
    } else {
      setWeeklyData(null)
    }
  }, [accountName, holdingsData, selectedYear, selectedMonth])

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
  
  // Helper to filter by year and optionally month
  const filterByYearAndMonth = (data: MonthlyData[]) => {
    let filtered = data.filter(d => d.year === selectedYear)
    if (selectedMonth !== null) {
      filtered = filtered.filter(d => {
        const monthNum = parseInt(d.month.split('-')[1], 10)
        return monthNum === selectedMonth
      })
    }
    return filtered
  }
  
  // Filter by selected year and month
  const filteredOptions = filterByYearAndMonth(optionsChartData)
  const filteredDividends = filterByYearAndMonth(dividendChartData)
  const filteredInterest = filterByYearAndMonth(interestChartData)
  
  // Calculate period-specific totals
  const yearOptionsTotal = filteredOptions.reduce((sum, d) => sum + d.value, 0)
  const yearDividendsTotal = filteredDividends.reduce((sum, d) => sum + d.value, 0)
  const yearInterestTotal = filteredInterest.reduce((sum, d) => sum + d.value, 0)
  const periodSales = selectedMonth === null
    ? acctSales
    : acctSales.filter((s: any) => parseInt(s.sale_date.slice(5, 7), 10) === selectedMonth)
  const yearEquityTotal = periodSales.reduce((s: number, r: any) => s + r.gain_loss, 0)
  const equityByMonth: Record<string, number> = {}
  for (const r of acctSales) {
    const k = r.sale_date.slice(0, 7)
    equityByMonth[k] = (equityByMonth[k] || 0) + r.gain_loss
  }
  const yearTotalIncome = yearOptionsTotal + yearDividendsTotal + yearInterestTotal + yearEquityTotal
  
  // Count months with income for selected period
  const yearOptionsMonths = filteredOptions.filter(d => d.value !== 0).length
  const yearDividendsMonths = filteredDividends.filter(d => d.value !== 0).length
  const yearInterestMonths = filteredInterest.filter(d => d.value !== 0).length
  
  // Period label for display
  const periodLabel = selectedMonth !== null
    ? `${new Date(selectedYear, selectedMonth - 1).toLocaleString('default', { month: 'long' })} ${selectedYear}`
    : `${selectedYear}`
  
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
          <span className={styles.detailType}>{periodLabel} Total</span>
        </div>
      </div>

      {/* Year Selector */}
      {years.length > 0 && (
        <div className={styles.yearSelector} style={{ marginBottom: 'var(--space-4)' }}>
          {years.map(year => (
            <button
              key={year}
              className={clsx(styles.yearButton, selectedYear === year && styles.active)}
              onClick={() => handleYearChange(year)}
            >
              {year}
            </button>
          ))}
        </div>
      )}

      {/* Month Selector - show for any selected year */}
      {years.length > 0 && (
        <div className={styles.monthSelectorRow} style={{ marginBottom: 'var(--space-6)' }}>
          <button
            className={clsx(styles.monthPill, selectedMonth === null && styles.active)}
            onClick={() => setSelectedMonth(null)}
          >
            Full Year
          </button>
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(month => (
            <button
              key={month}
              className={clsx(styles.monthPill, selectedMonth === month && styles.active)}
              onClick={() => setSelectedMonth(month)}
            >
              {new Date(selectedYear, month - 1).toLocaleString('default', { month: 'short' })}
            </button>
          ))}
        </div>
      )}

      {/* Source chips — hierarchy first, zeros dimmed */}
      <section className={styles.accountsSection}>
        <h2>{periodLabel} Income Breakdown</h2>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          {([
            ['Options', yearOptionsTotal, '#00D632'],
            ['Equity Sales', yearEquityTotal, '#00A3FF'],
            ['Dividends', yearDividendsTotal, '#A855F7'],
            ['Interest', yearInterestTotal, '#FFB800'],
          ] as Array<[string, number, string]>).map(([label, v, c]) => (
            <div key={label} style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 16px', minWidth: 140 }}>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{label}</div>
              <div style={{ fontWeight: 700, fontSize: 17, fontVariantNumeric: 'tabular-nums', color: v === 0 ? 'var(--color-text-tertiary)' : v < 0 ? '#FF5A5A' : c }}>
                {v === 0 ? '—' : formatFullCurrency(v)}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* One combined monthly chart, sign-colored */}
      <section className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Monthly Income</h2>
          <div className={styles.chartTotal}>{formatCurrency(yearTotalIncome)}</div>
        </div>
        {(() => {
          const map: Record<string, number> = {}
          for (const d of filteredOptions) map[d.month] = (map[d.month] || 0) + d.value
          for (const d of filteredDividends) map[d.month] = (map[d.month] || 0) + d.value
          for (const d of filteredInterest) map[d.month] = (map[d.month] || 0) + d.value
          for (const [k, v] of Object.entries(equityByMonth)) {
            if (!k.startsWith(`${selectedYear}-`)) continue
            if (selectedMonth !== null && parseInt(k.slice(5, 7), 10) !== selectedMonth) continue
            map[k] = (map[k] || 0) + v
          }
          const data = Object.entries(map)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([month, value]) => ({ month, formatted: formatMonthKey(month), value }))
          if (data.length === 0) return <div className={styles.chartEmpty}>No income for {periodLabel}</div>
          return (
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={data} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis dataKey="formatted" stroke="#737373" tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#737373" tick={{ fill: '#737373', fontSize: 11 }} tickFormatter={formatYAxis} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(value: number) => [
                      <span key="v" style={{ color: value < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>{formatFullCurrency(value)}</span>,
                      'Income',
                    ]}
                    contentStyle={{ background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px' }}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" />
                  <Bar dataKey="value" name="Income" radius={[4, 4, 0, 0]}>
                    {data.map((d, i) => (
                      <Cell key={i} fill={d.value < 0 ? '#FF5A5A' : '#00D632'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )
        })()}
      </section>

      {/* Income by Holding Table */}
      {holdingsRows.length > 0 && (
        <section className={styles.transactionsSection}>
          <h2>Income by Holding</h2>
          <HoldingsTable
            rows={holdingsRows}
            columns={incomeColumns}
            defaultSortKey="totalIncome"
          />
        </section>
      )}

      {/* Equity sales for the period */}
      {periodSales.length > 0 && (
        <section className={styles.transactionsSection}>
          <h2>Equity Sales — {periodLabel}</h2>
          <div className={styles.earningsTableContainer}>
            <table className={styles.earningsTable}>
              <thead>
                <tr><th>Date</th><th>Symbol</th><th>Qty</th><th>Proceeds</th><th>Basis</th><th>Gain / Loss</th><th>Term</th></tr>
              </thead>
              <tbody>
                {periodSales.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.sale_date}</td>
                    <td><strong>{r.symbol}</strong></td>
                    <td>{r.quantity.toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
                    <td>{formatFullCurrency(r.proceeds)}</td>
                    <td>{formatFullCurrency(r.cost_basis)}</td>
                    <td style={{ color: r.gain_loss < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>{formatFullCurrency(r.gain_loss)}</td>
                    <td>{r.is_long_term ? 'LT' : 'ST'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Weekly Breakdown — only shown when a specific month is selected */}
      {weeklyData && selectedMonth !== null && (
        <section className={styles.transactionsSection}>
          <div className={styles.weeklyHeader}>
            <h2>{weeklyData.month_formatted}</h2>
            <div className={styles.weeklyTotal}>
              Total: <span style={{ color: '#00D632' }}>{formatCurrency(weeklyData.month_total)}</span>
            </div>
          </div>

          <div className={styles.weeklySummary}>
            {weeklyData.weeks.map((week, i) => (
              <div key={week.key} className={styles.weekCell}>
                <span className={styles.weekLabel}>Week {i + 1}</span>
                <span className={styles.weekAmount}>{formatCurrency(weeklyData.weekly_totals[week.key] || 0)}</span>
                <span className={styles.weekCount}>{weeklyData.weekly_counts[week.key] || 0} contracts</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

// Salary Detail Component
// Salary Projection Config sub-component
interface SalaryProjection {
  id: number
  person: string
  monthly_net: number
  effective_from: string
  effective_to: string | null
  notes: string | null
}

function SalaryProjectionConfig({ employeeName }: { employeeName: string }) {
  const [projections, setProjections] = useState<SalaryProjection[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newRow, setNewRow] = useState({ monthly_net: '', effective_from: '', effective_to: '', notes: '' })

  const fetchProjections = async () => {
    try {
      const res = await fetch(`${API_BASE}/income/salary/projections`, { headers: getAuthHeaders() })
      if (res.ok) {
        const data = await res.json()
        // Filter to this employee's projections
        setProjections(
          data.projections.filter((p: SalaryProjection) =>
            p.person.toLowerCase() === employeeName.toLowerCase()
          )
        )
      }
    } catch (err) {
      console.error('Error fetching projections:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjections() }, [employeeName])

  const handleAdd = async () => {
    if (!newRow.monthly_net || !newRow.effective_from) return
    try {
      const res = await fetch(`${API_BASE}/income/salary/projections`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          person: employeeName,
          monthly_net: parseFloat(newRow.monthly_net),
          effective_from: newRow.effective_from,
          effective_to: newRow.effective_to || null,
          notes: newRow.notes || null,
        }),
      })
      if (res.ok) {
        setNewRow({ monthly_net: '', effective_from: '', effective_to: '', notes: '' })
        setAdding(false)
        fetchProjections()
      }
    } catch (err) {
      console.error('Error adding projection:', err)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/income/salary/projections/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (res.ok) {
        fetchProjections()
      }
    } catch (err) {
      console.error('Error deleting projection:', err)
    }
  }

  if (loading) return null

  return (
    <section className={styles.accountsSection}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h2>Current Salary (BBD Projection)</h2>
        {!adding && (
          <button
            className={styles.backButton}
            style={{ fontSize: '12px', padding: '4px 12px' }}
            onClick={() => setAdding(true)}
          >
            <Plus size={14} /> Add
          </button>
        )}
      </div>
      <p style={{ color: '#888', fontSize: '13px', marginBottom: '12px' }}>
        Monthly take-home used for BBD timeline income offset projections.
      </p>
      <div className={styles.w2Table}>
        <div className={styles.w2Header}>
          <span>Monthly Take-Home</span>
          <span>From</span>
          <span>To</span>
          <span>Notes</span>
          <span></span>
        </div>
        {projections.length === 0 && !adding && (
          <div style={{ padding: '16px', color: '#888', textAlign: 'center', fontSize: '13px' }}>
            No salary projections configured. Current salary is $0 for BBD projections.
          </div>
        )}
        {projections.map((p) => (
          <div key={p.id} className={styles.w2Row}>
            <span className={styles.w2Wages}>{formatCurrency(p.monthly_net)}/mo</span>
            <span>{p.effective_from}</span>
            <span>{p.effective_to || 'ongoing'}</span>
            <span style={{ color: '#888', fontSize: '12px' }}>{p.notes || ''}</span>
            <span>
              <button
                onClick={() => handleDelete(p.id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#EF4444', padding: '4px' }}
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </span>
          </div>
        ))}
        {adding && (
          <div className={styles.w2Row} style={{ gap: '8px' }}>
            <span>
              <input
                type="number"
                placeholder="Monthly $"
                value={newRow.monthly_net}
                onChange={(e) => setNewRow({ ...newRow, monthly_net: e.target.value })}
                style={{ width: '100px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#fff', padding: '4px 8px', fontSize: '13px' }}
              />
            </span>
            <span>
              <input
                type="text"
                placeholder="2025-01"
                value={newRow.effective_from}
                onChange={(e) => setNewRow({ ...newRow, effective_from: e.target.value })}
                style={{ width: '80px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#fff', padding: '4px 8px', fontSize: '13px' }}
              />
            </span>
            <span>
              <input
                type="text"
                placeholder="2025-12"
                value={newRow.effective_to}
                onChange={(e) => setNewRow({ ...newRow, effective_to: e.target.value })}
                style={{ width: '80px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#fff', padding: '4px 8px', fontSize: '13px' }}
              />
            </span>
            <span>
              <input
                type="text"
                placeholder="Notes"
                value={newRow.notes}
                onChange={(e) => setNewRow({ ...newRow, notes: e.target.value })}
                style={{ width: '120px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#fff', padding: '4px 8px', fontSize: '13px' }}
              />
            </span>
            <span style={{ display: 'flex', gap: '4px' }}>
              <button
                onClick={handleAdd}
                style={{ background: '#10B981', border: 'none', borderRadius: '4px', color: '#fff', padding: '4px 10px', cursor: 'pointer', fontSize: '12px' }}
              >
                Save
              </button>
              <button
                onClick={() => setAdding(false)}
                style={{ background: '#333', border: 'none', borderRadius: '4px', color: '#fff', padding: '4px 10px', cursor: 'pointer', fontSize: '12px' }}
              >
                Cancel
              </button>
            </span>
          </div>
        )}
      </div>
    </section>
  )
}


interface SalaryDetailProps {
  employeeName: string
  onBack: () => void
}

function SalaryDetail({ employeeName, onBack }: SalaryDetailProps) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<any>(null)
  const [selectedYear, setSelectedYear] = useState<number | 'all'>(2026)

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

      {/* Salary Projections Config */}
      <SalaryProjectionConfig employeeName={data.employee_name} />

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
                <CartesianGrid {...GRID_PROPS} />
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
  const [searchParams] = useSearchParams()
  const sectionParam = searchParams.get('section')
  const yearParam = searchParams.get('year')

  const initialView = (sectionParam === 'options' || sectionParam === 'dividends' || sectionParam === 'interest' || sectionParam === 'rental')
    ? sectionParam : 'main'
  const [view, setView] = useState<'main' | 'options' | 'dividends' | 'interest' | 'rental' | 'account' | 'salary_detail' | 'equity_sales' | 'salary_pick'>(initialView)
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
  const [optionsByTypeAll, setOptionsByTypeAll] = useState<Record<string, { calls: number; puts: number }>>({})
  const [optionsByTypeTaxable, setOptionsByTypeTaxable] = useState<Record<string, { calls: number; puts: number }>>({})
  const [portfolioEquity, setPortfolioEquity] = useState<number | null>(null)
  const [cashPosition, setCashPosition] = useState<number | null>(null)
  const [monthlyPositions, setMonthlyPositions] = useState<{ equity: Record<string, number>; cash: Record<string, number> }>({ equity: {}, cash: {} })
  // Unified income (monthly) — source for equity-sales/lending in the hero total
  const [unifiedMonthly, setUnifiedMonthly] = useState<Array<{ period: string; total: number; by_source: Record<string, number> }>>([])
  const [unifiedMonthlyTaxable, setUnifiedMonthlyTaxable] = useState<Array<{ period: string; total: number; by_source: Record<string, number> }>>([])
  // Per-account realized equity P/L by month (for the By Account table)
  const [realizedMonthly, setRealizedMonthly] = useState<Array<{ period: string; account_id: string; realized_pnl: number }>>([])
  // Yield-tracker goal settings (targets + margin limits)
  const [goalSettings, setGoalSettings] = useState<any>(null)
  // Period the user was viewing when they drilled into a source
  const [drillRange, setDrillRange] = useState<DrillRange | null>(null)

  // Projected net salary starting June 2026:
  //   Neel $120k gross → ~$6,986/month net after federal+FICA+CA taxes
  //   Jaya $150k gross → ~$8,435/month net after federal+FICA+CA taxes
  const SALARY_START_MONTH = '2026-06'
  const PROJECTED_SALARY_MONTHLY = 6986 + 8435  // $15,421/month combined
  const [mainSelectedYear, setMainSelectedYear] = useState<number | 'all'>(yearParam ? parseInt(yearParam) : new Date().getFullYear())
  const [mainSelectedMonth, setMainSelectedMonth] = useState<number | null>(yearParam ? null : new Date().getMonth() + 1) // null = Full Year when coming from Tax page

  // Earnings chart state
  const [earningsSummary, setEarningsSummary] = useState<any>(null)
  const [earningsView, setEarningsView] = useState<'all' | 'options' | 'equity_sales' | 'salary' | 'rental' | 'div_int'>('all')
  const [taxableOnly, setTaxableOnly] = useState(false)
  // BBD metrics for options expected values (1% of portfolio/month)
  const [optionsExpectedByMonth, setOptionsExpectedByMonth] = useState<Record<string, number>>({})
  const [capitalByMonth, setCapitalByMonth] = useState<Record<string, number>>({})
  const [taxableCapitalByMonth, setTaxableCapitalByMonth] = useState<Record<string, number>>({})

  // Current year for reference
  const currentYear = new Date().getFullYear()

  // Reset month when switching to 'all' (full year view is always available for any specific year)
  const handleYearChange = (year: number | 'all') => {
    setMainSelectedYear(year)
    if (year === 'all') {
      setMainSelectedMonth(null)
    }
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const [summaryRes, optionsRes, dividendsRes, interestRes, optionsChartRes, dividendChartRes, interestChartRes, rentalRes, rentalChartRes, salaryRes, byTypeRes, byTypeTaxableRes, holdingsRes, cashRes, monthlyPosRes, unifiedRes, unifiedTaxRes, realizedRes, goalRes] = await Promise.all([
        fetch(`${API_BASE}/income/summary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/dividends`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/interest`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/dividends/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/interest/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/rental`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/rental/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/salary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/by-type`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/by-type?taxable_only=true`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/holdings/live`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/ingestion/robinhood-cash/balances`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/monthly-positions`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/unified?granularity=month`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/unified?granularity=month&taxable_only=true`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/realized-pnl?granularity=month`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/goal-settings`, { headers: getAuthHeaders() }),
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
      if (byTypeRes.ok) {
        const data = await byTypeRes.json()
        setOptionsByTypeAll(data)
      }
      if (byTypeTaxableRes.ok) {
        const data = await byTypeTaxableRes.json()
        setOptionsByTypeTaxable(data)
      }
      if (holdingsRes.ok) {
        const data = await holdingsRes.json()
        const equity = (data.accounts || []).reduce((s: number, a: any) => s + (a.value || 0), 0)
        setPortfolioEquity(equity)
      }
      if (cashRes.ok) {
        const data = await cashRes.json()
        setCashPosition(data.total_true_cash || 0)
      }
      if (monthlyPosRes.ok) {
        const data = await monthlyPosRes.json()
        setMonthlyPositions({ equity: data.equity || {}, cash: data.cash || {} })
      }
      if (unifiedRes.ok) {
        const data = await unifiedRes.json()
        setUnifiedMonthly(data.periods || [])
      }
      if (unifiedTaxRes.ok) {
        const data = await unifiedTaxRes.json()
        setUnifiedMonthlyTaxable(data.periods || [])
      }
      if (realizedRes.ok) {
        const data = await realizedRes.json()
        setRealizedMonthly(data.periods || [])
      }
      if (goalRes.ok) {
        setGoalSettings(await goalRes.json())
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

  const fetchEarningsSummary = async () => {
    try {
      const response = await fetch(`${API_BASE}/strategies/buy-borrow-die/assumptions/summary`, {
        headers: getAuthHeaders(),
      })
      if (!response.ok) throw new Error('Failed to load summary')
      setEarningsSummary(await response.json())
    } catch (err) {
      console.error('Earnings summary fetch error:', err)
    }
  }

  useEffect(() => {
    fetchEarningsSummary()
    // Fetch taxable (brokerage-only) capital by month
    fetch(`${API_BASE}/strategies/buy-borrow-die/assumptions/taxable-capital`, { headers: getAuthHeaders() })
      .then(res => res.ok ? res.json() : null)
      .then(data => { if (data?.months) setTaxableCapitalByMonth(data.months) })
      .catch(err => console.error('Taxable capital fetch error:', err))
  }, [])

  // Fetch BBD monthly metrics for options expected values (1% of portfolio/month)
  const fetchOptionsExpected = async () => {
    try {
      // Fetch all years by getting year-level first, then monthly for each
      // For simplicity, fetch monthly metrics for available years
      const yearsToFetch = mainSelectedYear === 'all'
        ? [...new Set(optionsChartData.map(d => d.year))]
        : [mainSelectedYear as number]

      const allMetrics: Record<string, number> = {}
      const allCapital: Record<string, number> = {}
      for (const year of yearsToFetch) {
        const params = new URLSearchParams({ metric_type: 'options_yield', period_type: 'month', year: String(year) })
        const response = await fetch(`${API_BASE}/strategies/buy-borrow-die/assumptions/metrics?${params}`, {
          headers: getAuthHeaders(),
        })
        if (response.ok) {
          const data = await response.json()
          for (const m of data.metrics || []) {
            if (m.period_start) {
              const monthKey = m.period_start.substring(0, 7) // "2025-01"
              allMetrics[monthKey] = m.expected_value || 0
              allCapital[monthKey] = m.baseline_value || 0
            }
          }
        }
      }
      setOptionsExpectedByMonth(allMetrics)
      setCapitalByMonth(allCapital)
    } catch (err) {
      console.error('Options expected fetch error:', err)
    }
  }

  useEffect(() => {
    if (optionsChartData.length > 0) {
      fetchOptionsExpected()
    }
  }, [mainSelectedYear, optionsChartData.length])

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
    if (mainSelectedMonth !== null && mainSelectedYear !== 'all') {
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
  // Uses monthly_income data when filtering by specific month, converting gross to net
  const filteredRentalTotal = (() => {
    if (!rentalData?.properties) return 0
    let filteredProperties = mainSelectedYear === 'all'
      ? rentalData.properties
      : rentalData.properties.filter(p => p.year === mainSelectedYear)

    const expenseRatioFor = (p: typeof filteredProperties[0]) =>
      p.gross_income > 0 ? p.total_expenses / p.gross_income : 0

    if (mainSelectedMonth !== null && mainSelectedYear !== 'all') {
      // Single month selected
      const monthStr = `${mainSelectedYear}-${String(mainSelectedMonth).padStart(2, '0')}`
      return filteredProperties.reduce((sum, p) => {
        const monthData = p.monthly_income?.find(m => m.month === monthStr)
        if (!monthData) return sum
        return sum + monthData.amount * (1 - expenseRatioFor(p))
      }, 0)
    }

    // Full-year view: if current year, only sum months up to and including today
    if (typeof mainSelectedYear === 'number' && mainSelectedYear === currentYear) {
      const todayMonthStr = `${currentYear}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
      return filteredProperties.reduce((sum, p) => {
        const pastMonths = (p.monthly_income ?? []).filter(m => m.month <= todayMonthStr)
        if (pastMonths.length === 0) return sum + p.net_income // fallback if no monthly detail
        return sum + pastMonths.reduce((s, m) => s + m.amount * (1 - expenseRatioFor(p)), 0)
      }, 0)
    }

    return filteredProperties.reduce((sum, p) => sum + p.net_income, 0)
  })()

  // Convert rental chart data from gross to net using per-year expense ratios
  const rentalNetChartData: MonthlyData[] = (() => {
    if (!rentalData?.properties) return rentalChartData // fallback to gross if no property data
    // Build year → expense ratio map (sum across all properties per year)
    const yearTotals: Record<number, { gross: number; expenses: number }> = {}
    for (const p of rentalData.properties) {
      if (!yearTotals[p.year]) yearTotals[p.year] = { gross: 0, expenses: 0 }
      yearTotals[p.year].gross += p.gross_income
      yearTotals[p.year].expenses += p.total_expenses
    }
    return rentalChartData.map(d => {
      const t = yearTotals[d.year]
      const ratio = t && t.gross > 0 ? t.expenses / t.gross : 0
      return { ...d, value: d.value * (1 - ratio) }
    })
  })()

  const mainFilteredRentalChart = filterChartData(rentalNetChartData)

  // Build chart data from by_account, filtered to taxable (individual/brokerage) accounts only
  const NON_TAXABLE_TYPES = new Set(['retirement', 'ira', 'roth_ira', 'traditional_ira', '401k', 'hsa'])
  const buildTaxableChart = (byAccount: Record<string, any> | undefined): MonthlyData[] => {
    if (!byAccount) return []
    const monthTotals: Record<string, number> = {}
    for (const accountData of Object.values(byAccount)) {
      if (NON_TAXABLE_TYPES.has(accountData.account_type)) continue
      for (const [month, amount] of Object.entries(accountData.monthly || {})) {
        monthTotals[month] = (monthTotals[month] || 0) + (amount as number)
      }
    }
    return Object.entries(monthTotals)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, value]) => {
        const [y, m] = month.split('-')
        const d = new Date(parseInt(y), parseInt(m) - 1)
        return { month, formatted: d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }), value, year: parseInt(y) }
      })
  }

  // Effective chart data: taxable-filtered or full
  const effectiveOptionsChart = taxableOnly ? buildTaxableChart(optionsData?.by_account) : optionsChartData
  const effectiveDividendChart = taxableOnly ? buildTaxableChart(dividendData?.by_account) : dividendChartData
  const effectiveInterestChart = taxableOnly ? buildTaxableChart(interestData?.by_account) : interestChartData
  // Rental and salary are always taxable — no filtering needed

  // Calls/puts split: switch between all-accounts and taxable-only
  const optionsByType = taxableOnly ? optionsByTypeTaxable : optionsByTypeAll

  // Year-only filtered chart data (for the earnings chart — always shows full year)
  const filterChartDataYearOnly = (data: MonthlyData[]) => {
    if (mainSelectedYear === 'all') return data
    return data.filter(d => d.year === mainSelectedYear)
  }
  const yearFilteredOptionsChart = filterChartDataYearOnly(effectiveOptionsChart)
  const yearFilteredDividendChart = filterChartDataYearOnly(effectiveDividendChart)
  const yearFilteredInterestChart = filterChartDataYearOnly(effectiveInterestChart)
  const yearFilteredRentalChart = filterChartDataYearOnly(rentalNetChartData)

  // The selected month key for highlighting (e.g. "2026-02")
  const highlightedMonthKey = mainSelectedMonth !== null && mainSelectedYear !== 'all'
    ? `${mainSelectedYear}-${String(mainSelectedMonth).padStart(2, '0')}`
    : null

  // Expected monthly baselines
  // Options: 1% of portfolio value per month (from BBD assumptions API)
  // Others: trailing average from all historical data
  const getExpectedOptions = (monthKey: string) => optionsExpectedByMonth[monthKey] || 0
  const expectedMonthlyDividends = effectiveDividendChart.length > 0
    ? effectiveDividendChart.reduce((s, d) => s + d.value, 0) / effectiveDividendChart.length : 0
  const expectedMonthlyInterest = effectiveInterestChart.length > 0
    ? effectiveInterestChart.reduce((s, d) => s + d.value, 0) / effectiveInterestChart.length : 0
  const expectedMonthlyRental = rentalNetChartData.length > 0
    ? rentalNetChartData.reduce((s, d) => s + d.value, 0) / rentalNetChartData.length : 0

  // Combined income data (year-only filter for chart)
  const combinedIncomeData = (() => {
    type Row = { month: string; formatted: string; year: number; options: number; calls: number; puts: number; dividends: number; interest: number; rental: number; salary: number }
    const monthMap: Record<string, Row> = {}

    const addData = (data: MonthlyData[], key: keyof Row) => {
      for (const d of data) {
        if (!monthMap[d.month]) {
          monthMap[d.month] = { month: d.month, formatted: d.formatted, year: d.year, options: 0, calls: 0, puts: 0, dividends: 0, interest: 0, rental: 0, salary: 0 }
        }
        ;(monthMap[d.month] as any)[key] += d.value
      }
    }

    addData(yearFilteredOptionsChart, 'options')
    addData(yearFilteredDividendChart, 'dividends')
    addData(yearFilteredInterestChart, 'interest')
    addData(yearFilteredRentalChart, 'rental')

    // Merge calls/puts split from optionsByType
    for (const [month, byType] of Object.entries(optionsByType)) {
      if (monthMap[month]) {
        monthMap[month].calls = byType.calls
        monthMap[month].puts = byType.puts
      }
    }

    // Salary: projected net for months >= SALARY_START_MONTH, historical otherwise
    for (const entry of Object.values(monthMap)) {
      if (entry.month >= SALARY_START_MONTH) {
        entry.salary = PROJECTED_SALARY_MONTHLY
      } else if (salaryData?.employees) {
        entry.salary = salaryData.employees.reduce((total: number, emp: any) => {
          const yearData = emp.yearly_data.find((y: any) => y.year === entry.year)
          return total + ((yearData?.net || 0) / 12)
        }, 0)
      }
    }

    return Object.values(monthMap).sort((a, b) => a.month.localeCompare(b.month))
  })()

  // Build chart data with actual + expected lines per view (always full year)
  const earningsChartData = (() => {
    const addHighlight = (d: any) => ({ ...d, highlighted: d.month === highlightedMonthKey })

    // Every view is driven by the unified income dataset (actuals; the
    // Taxable Only toggle swaps datasets), in the user's source hierarchy.
    const rows = (taxableOnly ? unifiedMonthlyTaxable : unifiedMonthly)
      .filter(p => mainSelectedYear === 'all' || p.period.startsWith(`${mainSelectedYear}-`))
      .map(p => {
        const s = p.by_source
        const monthKey = p.period.slice(0, 7)
        const d = new Date(p.period + 'T00:00:00')
        const div_int = (s.dividends || 0) + (s.interest || 0) + (s.lending || 0)
        return addHighlight({
          month: monthKey,
          formatted: d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
          year: d.getFullYear(),
          options: s.options || 0,
          equity_sales: s.equity_sales || 0,
          salary: s.salary || 0,
          rental: s.rental || 0,
          div_int,
          actual: p.total,
        })
      })
    if (earningsView === 'all') return rows
    return rows.map(r => ({ ...r, actual: (r as any)[earningsView] || 0 }))
  })().filter(d => {
    // For current year, only show months up through the current month
    if (mainSelectedYear !== 'all' && mainSelectedYear === currentYear) {
      const now = new Date()
      const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      return d.month <= currentMonthKey
    }
    return true
  })

  // Determine which income categories have non-zero data for dynamic column visibility
  const earningsVisibleCols = earningsView === 'all' && earningsChartData.length > 0 ? {
    options: earningsChartData.some((d: any) => (d.expOptions || 0) > 0 || (d.options || 0) > 0),
    dividends: earningsChartData.some((d: any) => (d.expDividends || 0) > 0 || (d.dividends || 0) > 0),
    interest: earningsChartData.some((d: any) => (d.expInterest || 0) > 0 || (d.interest || 0) > 0),
    rental: earningsChartData.some((d: any) => (d.expRental || 0) > 0 || (d.rental || 0) > 0),
    salary: earningsChartData.some((d: any) => (d.expSalary || 0) > 0 || (d.salary || 0) > 0),
  } : null
  const earningsGroupColSpan = earningsVisibleCols
    ? Object.values(earningsVisibleCols).filter(Boolean).length + 1  // +1 for Total
    : 0

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

  // Get Jaya's salary data for specific year (prorated if month selected)
  const getJayaSalary = () => {
    const jaya = salaryData?.employees.find(e => e.name.toLowerCase().includes('jaya'))
    if (!jaya) return null

    let net: number, gross: number, isProjected = false
    if (mainSelectedYear === 'all') {
      net = jaya.total_net
      gross = jaya.total_gross
    } else {
      const yearData = jaya.yearly_data.find(y => y.year === mainSelectedYear)
      if (!yearData) {
        // Fall back to projection for current/future year when no W-2 uploaded yet
        if (typeof mainSelectedYear === 'number' && mainSelectedYear >= currentYear) {
          gross = 150000
          net = 101220
          isProjected = true
        } else {
          return null
        }
      } else {
        net = yearData.net
        gross = yearData.gross
      }
    }

    if (mainSelectedMonth !== null && mainSelectedYear !== 'all') {
      // Single month selected
      if (isProjected && mainSelectedYear === 2026 && mainSelectedMonth < 6) {
        return { net: 0, gross: 0, employer: jaya.employer, isProjected, startsAt: 'June 2026' }
      }
      net = net / 12
      gross = gross / 12
    } else if (isProjected && mainSelectedYear !== 'all' && mainSelectedMonth === null) {
      // Full-year view: only count months that have already started, up to today
      const todayMonth = new Date().getMonth() + 1 // 1-based
      const salaryStartMonth = 6 // June 2026
      const elapsedMonths = typeof mainSelectedYear === 'number' && mainSelectedYear === currentYear
        ? Math.max(0, todayMonth - salaryStartMonth + 1)
        : 12
      net = (net / 12) * elapsedMonths
      gross = (gross / 12) * elapsedMonths
    }

    return { net, gross, employer: jaya.employer, isProjected, startsAt: undefined as string | undefined }
  }

  const jayaSalary = getJayaSalary()

  // Get Neel's salary data for specific year (prorated if month selected)
  const getNeelSalary = () => {
    const neel = salaryData?.employees.find(e => e.name.toLowerCase().includes('neel'))
    if (!neel) return null

    let net: number, gross: number, isProjected = false
    if (mainSelectedYear === 'all') {
      net = neel.total_net
      gross = neel.total_gross
    } else {
      const yearData = neel.yearly_data.find(y => y.year === mainSelectedYear)
      if (!yearData) {
        // Fall back to projection for current/future year when no W-2 uploaded yet
        if (typeof mainSelectedYear === 'number' && mainSelectedYear >= currentYear) {
          gross = 120000
          net = 83832
          isProjected = true
        } else {
          return null
        }
      } else {
        net = yearData.net
        gross = yearData.gross
      }
    }

    if (mainSelectedMonth !== null && mainSelectedYear !== 'all') {
      // Single month selected
      if (isProjected && mainSelectedYear === 2026 && mainSelectedMonth < 6) {
        return { net: 0, gross: 0, employer: neel.employer, isProjected, startsAt: 'June 2026' }
      }
      net = net / 12
      gross = gross / 12
    } else if (isProjected && mainSelectedYear !== 'all' && mainSelectedMonth === null) {
      // Full-year view: only count months that have already started, up to today
      const todayMonth = new Date().getMonth() + 1
      const salaryStartMonth = 6
      const elapsedMonths = typeof mainSelectedYear === 'number' && mainSelectedYear === currentYear
        ? Math.max(0, todayMonth - salaryStartMonth + 1)
        : 12
      net = (net / 12) * elapsedMonths
      gross = (gross / 12) * elapsedMonths
    }

    return { net, gross, employer: neel.employer, isProjected, startsAt: undefined as string | undefined }
  }

  const neelSalary = getNeelSalary()

  // Derive salary total from card values so chart total always matches the sum of source cards
  const computedSalaryTotal =
    (jayaSalary?.isProjected ? (jayaSalary.net || 0) : (jayaSalary?.gross || 0)) +
    (neelSalary?.isProjected ? (neelSalary.net || 0) : (neelSalary?.gross || 0))

  // Equity-sale realized P/L + stock lending for the selected period (from the
  // unified income service) — completes the definition-of-income total.
  const filteredEquityLendingTotal = unifiedMonthly.reduce((sum, p) => {
    const [py, pm] = p.period.split('-').map(Number)
    if (mainSelectedYear !== 'all') {
      if (py !== mainSelectedYear) return sum
      if (mainSelectedMonth !== null && pm !== mainSelectedMonth) return sum
    }
    return sum + (p.by_source.equity_sales || 0) + (p.by_source.lending || 0)
  }, 0)

  const filteredTotalIncome = filteredOptionsTotal + filteredDividendTotal + filteredInterestTotal + filteredRentalTotal + computedSalaryTotal + filteredEquityLendingTotal

  const dividendsByMonth: Record<string, number> = Object.fromEntries(dividendChartData.map(d => [d.month, d.value]))

  // By-Account rows: ranked by total for the selected period, columns in
  // the income-importance hierarchy (Options, Equity, Div+Int).
  const accountRows = (() => {
    const inPeriod = (mk: string) => {
      if (mainSelectedYear === 'all') return true
      if (!mk.startsWith(`${mainSelectedYear}-`)) return false
      return mainSelectedMonth === null || mk === `${mainSelectedYear}-${String(mainSelectedMonth).padStart(2, '0')}`
    }
    const sumMonthly = (acct: any) => Object.entries(acct?.monthly || {})
      .filter(([k]) => inPeriod(k as string))
      .reduce((s, [, v]) => s + (v as number), 0)
    const idToName: Record<string, string> = {}
    const typeByName: Record<string, string> = {}
    for (const a of summary?.accounts || []) {
      idToName[a.account_id] = a.name
      typeByName[a.name] = a.account_type
    }
    const names = new Set<string>([
      ...Object.keys(optionsData?.by_account || {}),
      ...Object.keys(dividendData?.by_account || {}),
      ...Object.keys(interestData?.by_account || {}),
    ])
    const equityByName: Record<string, number> = {}
    for (const r of realizedMonthly) {
      if (!inPeriod(r.period.slice(0, 7))) continue
      const nm = idToName[r.account_id] || r.account_id
      equityByName[nm] = (equityByName[nm] || 0) + r.realized_pnl
      names.add(nm)
    }
    const NONTAX = new Set(['retirement', 'ira', 'roth_ira', 'traditional_ira', '401k', 'hsa'])
    const rows = [...names].map(name => {
      const options = sumMonthly(optionsData?.by_account?.[name])
      const divInt = sumMonthly(dividendData?.by_account?.[name]) + sumMonthly(interestData?.by_account?.[name])
      const equity = equityByName[name] || 0
      const acctType = typeByName[name] || (optionsData?.by_account?.[name] as any)?.account_type || ''
      return { name, options, equity, divInt, total: options + equity + divInt, taxable: !NONTAX.has(acctType) }
    }).filter(r => r.options !== 0 || r.equity !== 0 || r.divInt !== 0)
    rows.sort((a, b) => b.total - a.total)
    return rows
  })()

  // Level-3 table rows: straight from the unified income service (actuals);
  // projected salary shown as its own labeled column, never in totals.
  const unifiedTableRows = (taxableOnly ? unifiedMonthlyTaxable : unifiedMonthly)
    .filter(p => mainSelectedYear === 'all' || p.period.startsWith(`${mainSelectedYear}-`))
    .map(p => {
      const s = p.by_source
      const monthKey = p.period.slice(0, 7)
      const salary = s.salary || 0
      const total = (s.options || 0) + (s.equity_sales || 0) + (s.dividends || 0)
        + (s.interest || 0) + (s.lending || 0) + (s.rental || 0) + salary
      const d = new Date(p.period + 'T00:00:00')
      return {
        monthKey,
        label: d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
        options: s.options || 0, equity_sales: s.equity_sales || 0,
        dividends: s.dividends || 0, interest: s.interest || 0,
        lending: s.lending || 0, rental: s.rental || 0,
        salary, total,
        highlighted: mainSelectedYear !== 'all' && mainSelectedMonth !== null
          && monthKey === `${mainSelectedYear}-${String(mainSelectedMonth).padStart(2, '0')}`,
      }
    })

  // Build income sources list
  const incomeSources: IncomeSource[] = [
    {
      id: 'salary_jaya',
      name: "Jaya's Salary",
      type: 'salary',
      status: jayaSalary && (jayaSalary.gross > 0 || jayaSalary.startsAt) ? 'active' : 'pending_upload',
      value: jayaSalary?.isProjected ? (jayaSalary.net || 0) : (jayaSalary?.gross || 0),
      description: jayaSalary
        ? (jayaSalary.startsAt
          ? `Projected • Starts ${jayaSalary.startsAt}`
          : jayaSalary.isProjected
          ? 'Projected • $150K gross annual • Net take-home'
          : `${jayaSalary.employer} • Gross W-2 wages`)
        : 'W2 income - awaiting file upload',
      icon: Briefcase,
      color: '#A855F7',
    },
    {
      id: 'salary_neel',
      name: "Neel's Salary",
      type: 'salary',
      status: neelSalary && (neelSalary.gross > 0 || neelSalary.startsAt) ? 'active' : 'pending_upload',
      value: neelSalary?.isProjected ? (neelSalary.net || 0) : (neelSalary?.gross || 0),
      description: neelSalary
        ? (neelSalary.startsAt
          ? `Projected • Starts ${neelSalary.startsAt}`
          : neelSalary.isProjected
          ? 'Projected • $120K gross annual • Net take-home'
          : `${neelSalary.employer} • Gross W-2 wages`)
        : 'W2 income - awaiting file upload',
      icon: Briefcase,
      color: '#00A3FF',
    },
    {
      id: 'rental_income',
      name: 'Rental Income',
      type: 'rental',
      status: filteredRentalData && filteredRentalData.property_count > 0 ? 'active' : 'pending_upload',
      value: filteredRentalTotal, // Use prorated value when month is selected
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
          initialYear={typeof mainSelectedYear === 'number' ? mainSelectedYear : undefined}
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
          initialYear={typeof mainSelectedYear === 'number' ? mainSelectedYear : undefined}
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
          initialYear={typeof mainSelectedYear === 'number' ? mainSelectedYear : undefined}
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
        />
      </div>
    )
  }

  // Salary drill-down: pick the person first
  if (view === 'salary_pick') {
    const employees = [
      ...(jayaSalary ? ['Jaya'] : []),
      ...(neelSalary ? ['Neel'] : []),
    ]
    const names = employees.length > 0 ? employees : ['Jaya', 'Neel']
    return (
      <div className={styles.page}>
        <div className={styles.detailView}>
          <button className={styles.backButton} onClick={() => setView('main')}>
            <ArrowLeft size={16} /> Back to Income
          </button>
          <h1 style={{ margin: 'var(--space-4) 0' }}>Salary</h1>
          <div className={styles.sourcesGrid}>
            {names.map(name => (
              <button
                key={name}
                className={styles.sourceCard}
                onClick={() => {
                  setSelectedEmployee(name)
                  setView('salary_detail')
                }}
              >
                <h3 className={styles.sourceName}>{name}'s Salary</h3>
                <p className={styles.sourceDescription}>Payslips, W-2 history, projections</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // Equity sales detail view (realized P/L drill-down)
  if (view === 'equity_sales') {
    return (
      <div className={styles.page}>
        <EquitySalesDetail initialRange={drillRange} onBack={() => setView('main')} />
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
      {/* Level 1: unified income band — the page's single period control.
          Salary since 2026-06 is recurring ACTUAL income (salary_projections
          table) served by /income/unified; no client-side projection. */}
      <UnifiedIncomeBand
        onPeriodChange={(g, periodIso) => {
          const d = new Date(periodIso + 'T00:00:00')
          setMainSelectedYear(d.getFullYear())
          setMainSelectedMonth(g === 'year' ? null : d.getMonth() + 1)
        }}
        onDrill={(src, periodIso, g) => {
          // scope the drill-down to the period being viewed
          const d = new Date(periodIso + 'T00:00:00')
          const iso = (x: Date) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
          if (g === 'week') {
            const s = new Date(d); s.setDate(d.getDate() - 6)
            setDrillRange({ start: iso(s), end: periodIso, label: `Week ending ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` })
          } else if (g === 'month') {
            setDrillRange({ start: periodIso, end: iso(new Date(d.getFullYear(), d.getMonth() + 1, 0)), label: d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) })
          } else {
            setDrillRange({ start: `${d.getFullYear()}-01-01`, end: `${d.getFullYear()}-12-31`, label: String(d.getFullYear()) })
          }
          if (src === 'equity_sales') setView('equity_sales')
          else if (src === 'salary') setView('salary_pick')
          else setView(src as 'options' | 'dividends' | 'interest' | 'rental')
        }}
      />

      {/* Goals — actuals vs targets (yield tracker, Objective 2) */}
      <GoalsStrip
        year={mainSelectedYear}
        month={mainSelectedMonth}
        optionsByType={optionsByTypeAll}
        dividendsByMonth={dividendsByMonth}
        equityByMonth={monthlyPositions.equity}
        liveEquity={portfolioEquity}
        settings={goalSettings}
      />

      {/* Level 3: trend — chart + table on the unified definition */}
      <section className={styles.earningsSection}>
        <div className={styles.earningsChartCard}>
          {/* Header with toggle */}
          <div className={styles.earningsHeader}>
            <div>
              <h3 className={styles.earningsChartTitle}>
                {taxableOnly ? 'Taxable ' : ''}
                {earningsView === 'all' ? 'All Income' :
                 earningsView === 'options' ? 'Options Income' :
                 earningsView === 'equity_sales' ? 'Equity Sales Income' :
                 earningsView === 'salary' ? 'Salary Income' :
                 earningsView === 'rental' ? 'Rental Income' : 'Dividends + Interest + Lending'}
              </h3>
              <p className={styles.earningsChartSubtitle}>
                Monthly {taxableOnly ? 'taxable ' : ''}income{earningsView === 'all' ? ' by source' : ''}
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', alignItems: 'flex-end' }}>
              <div className={styles.tabs} style={{ marginBottom: 0 }}>
                {([
                  ['all', 'All'],
                  ['options', 'Options'],
                  ['equity_sales', 'Equity'],
                  ['salary', 'Salary'],
                  ['rental', 'Rent'],
                  ['div_int', 'Div + Int'],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    className={clsx(styles.tab, earningsView === key && styles.active)}
                    onClick={() => setEarningsView(key as any)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className={styles.taxableToggle}>
                <button
                  className={clsx(styles.toggleBtn, !taxableOnly && styles.toggleActive)}
                  onClick={() => setTaxableOnly(false)}
                >
                  All Income
                </button>
                <button
                  className={clsx(styles.toggleBtn, taxableOnly && styles.toggleActive)}
                  onClick={() => setTaxableOnly(true)}
                >
                  Taxable Only
                </button>
              </div>
            </div>
          </div>

          {/* Chart — actual income line only */}
          <div className={styles.earningsChartContainer}>
            {earningsChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={350}>
                <ComposedChart data={earningsChartData} margin={{ top: 20, right: 60, left: 20, bottom: 20 }}>
                  <CartesianGrid {...GRID_PROPS} />
                  <XAxis dataKey="formatted" stroke="#737373" tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#737373" tick={{ fill: '#737373', fontSize: 11 }} tickFormatter={formatYAxis} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      <span key="v" style={{ color: value < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>{formatFullCurrency(value)}</span>,
                      name,
                    ]}
                    contentStyle={{ background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px' }}
                  />
                  <Legend />
                  {highlightedMonthKey && (() => {
                    const idx = earningsChartData.findIndex((d: any) => d.month === highlightedMonthKey)
                    if (idx >= 0) {
                      const label = earningsChartData[idx].formatted
                      return <ReferenceLine x={label} stroke="#00D632" strokeWidth={2} strokeOpacity={0.4} />
                    }
                    return null
                  })()}
                  {earningsView === 'all' ? (
                    <>
                      {/* stacked composition, in the income-importance hierarchy */}
                      <Bar dataKey="options" name="Options" stackId="src" fill="#00D632" />
                      <Bar dataKey="equity_sales" name="Equity" stackId="src" fill="#00A3FF" />
                      <Bar dataKey="salary" name="Salary" stackId="src" fill="#A855F7" />
                      <Bar dataKey="rental" name="Rent" stackId="src" fill="#FFB800" />
                      <Bar dataKey="div_int" name="Div + Int" stackId="src" fill="#06B6D4" />
                    </>
                  ) : (() => {
                    // split green/red at the zero crossing so losses read as losses
                    const vals = earningsChartData.map((d: any) => d.actual || 0)
                    const mx = Math.max(...vals, 0)
                    const mn = Math.min(...vals, 0)
                    const zero = mx <= 0 ? 0 : mn >= 0 ? 1 : mx / (mx - mn)
                    return (
                      <>
                        <defs>
                          <linearGradient id="splitFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset={zero} stopColor="#00D632" stopOpacity={0.22} />
                            <stop offset={zero} stopColor="#FF5A5A" stopOpacity={0.28} />
                          </linearGradient>
                          <linearGradient id="splitStroke" x1="0" y1="0" x2="0" y2="1">
                            <stop offset={zero} stopColor="#00D632" />
                            <stop offset={zero} stopColor="#FF5A5A" />
                          </linearGradient>
                        </defs>
                        <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" />
                        <Area type="monotone" dataKey="actual" name="Income" fill="url(#splitFill)" stroke="url(#splitStroke)" strokeWidth={2}
                          dot={(props: any) => {
                            const { cx, cy, payload } = props
                            const c = (payload?.actual ?? 0) < 0 ? '#FF5A5A' : '#00D632'
                            if (payload?.highlighted) {
                              return <circle key={`dot-${cx}`} cx={cx} cy={cy} r={6} fill={c} stroke="#0D0D0D" strokeWidth={2} />
                            }
                            return <circle key={`dot-${cx}`} cx={cx} cy={cy} r={3.5} fill={c} fillOpacity={0.9} />
                          }}
                        />
                      </>
                    )
                  })()}
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className={styles.chartEmpty}>No income data for the selected period.</div>
            )}
          </div>

          {/* Data Table — 'all' view is driven by /income/unified (actuals);
              projected salary is a labeled column outside the total */}
          {earningsView === 'all' ? (
            unifiedTableRows.length > 0 && (
              <div className={styles.earningsTableContainer} style={{ marginTop: 'var(--space-4)' }}>
                <table className={styles.earningsTable}>
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th className={styles.earningsHighlightCol}>Options</th>
                      <th className={styles.earningsHighlightCol}>Equity Sales</th>
                      <th>Dividends</th>
                      <th>Interest</th>
                      <th>Lending</th>
                      <th>Rent</th>
                      <th>Salary</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unifiedTableRows.map((d) => (
                      <tr
                        key={d.monthKey}
                        className={clsx(
                          d.total >= 0 ? styles.earningsPositiveRow : styles.earningsNegativeRow,
                          d.highlighted && styles.earningsHighlightedRow
                        )}
                      >
                        <td><strong>{d.label}</strong></td>
                        <td className={styles.earningsHighlightCol} style={{ color: d.options < 0 ? '#FF5A5A' : '#00D632' }}>{d.options !== 0 ? formatFullCurrency(d.options) : '—'}</td>
                        <td className={styles.earningsHighlightCol} style={{ color: d.equity_sales < 0 ? '#FF5A5A' : '#00D632' }}>{d.equity_sales !== 0 ? formatFullCurrency(d.equity_sales) : '—'}</td>
                        <td style={{ color: d.dividends < 0 ? '#FF5A5A' : undefined }}>{d.dividends !== 0 ? formatFullCurrency(d.dividends) : '—'}</td>
                        <td style={{ color: d.interest < 0 ? '#FF5A5A' : undefined }}>{d.interest !== 0 ? formatFullCurrency(d.interest) : '—'}</td>
                        <td style={{ color: d.lending < 0 ? '#FF5A5A' : undefined }}>{d.lending !== 0 ? formatFullCurrency(d.lending) : '—'}</td>
                        <td style={{ color: d.rental < 0 ? '#FF5A5A' : undefined }}>{d.rental !== 0 ? formatFullCurrency(d.rental) : '—'}</td>
                        <td style={{ color: d.salary < 0 ? '#FF5A5A' : undefined }}>{d.salary !== 0 ? formatFullCurrency(d.salary) : '—'}</td>
                        <td><strong style={{ color: d.total < 0 ? '#FF5A5A' : '#00D632' }}>{formatFullCurrency(d.total)}</strong></td>
                      </tr>
                    ))}
                    {unifiedTableRows.length > 1 && (() => {
                      const t = unifiedTableRows.reduce((acc, d) => ({
                        options: acc.options + d.options,
                        equity_sales: acc.equity_sales + d.equity_sales,
                        dividends: acc.dividends + d.dividends,
                        interest: acc.interest + d.interest,
                        lending: acc.lending + d.lending,
                        rental: acc.rental + d.rental,
                        salary: acc.salary + d.salary,
                        total: acc.total + d.total,
                      }), { options: 0, equity_sales: 0, dividends: 0, interest: 0, lending: 0, rental: 0, salary: 0, total: 0 })
                      return (
                        <tr className={styles.earningsTotalRow}>
                          <td><strong>Total</strong></td>
                          <td className={styles.earningsHighlightCol} style={{ color: t.options < 0 ? '#FF5A5A' : '#00D632' }}><strong>{formatFullCurrency(t.options)}</strong></td>
                          <td className={styles.earningsHighlightCol} style={{ color: t.equity_sales < 0 ? '#FF5A5A' : '#00D632' }}><strong>{formatFullCurrency(t.equity_sales)}</strong></td>
                          <td><strong>{formatFullCurrency(t.dividends)}</strong></td>
                          <td><strong>{formatFullCurrency(t.interest)}</strong></td>
                          <td><strong>{formatFullCurrency(t.lending)}</strong></td>
                          <td><strong>{formatFullCurrency(t.rental)}</strong></td>
                          <td><strong>{formatFullCurrency(t.salary)}</strong></td>
                          <td><strong>{formatFullCurrency(t.total)}</strong></td>
                        </tr>
                      )
                    })()}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            earningsChartData.length > 0 && (
              <div className={styles.earningsTableContainer} style={{ marginTop: 'var(--space-4)' }}>
                <table className={styles.earningsTable}>
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Income</th>
                    </tr>
                  </thead>
                  <tbody>
                    {earningsChartData.map((d: any, idx: number) => (
                      <tr
                        key={idx}
                        className={clsx(
                          d.actual >= 0 ? styles.earningsPositiveRow : styles.earningsNegativeRow,
                          d.highlighted && styles.earningsHighlightedRow
                        )}
                      >
                        <td><strong>{d.formatted}</strong></td>
                        <td style={{ color: d.actual < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>{formatFullCurrency(d.actual)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>
      </section>

      {/* Account Breakdown — ranked by income, hierarchy-first columns */}
      {accountRows.length > 0 && (
        <section className={styles.accountsSection}>
          <h2>By Account {mainSelectedYear === 'all'
            ? '(All Time)'
            : mainSelectedMonth !== null
              ? `(${new Date(typeof mainSelectedYear === 'number' ? mainSelectedYear : currentYear, mainSelectedMonth - 1).toLocaleString('default', { month: 'long' })} ${mainSelectedYear})`
              : `(${mainSelectedYear})`}</h2>
          <div className={styles.accountsGrid}>
            {accountRows.map(r => (
              <button
                key={r.name}
                className={styles.accountCard}
                style={{ textAlign: 'left', cursor: 'pointer' }}
                onClick={() => { setSelectedAccount(r.name); setView('account') }}
                title={`Open ${r.name}`}
              >
                <div className={styles.accountHeader}>
                  <div>
                    <h3 className={styles.accountName}>{r.name}</h3>
                    <span className={styles.accountType} style={{ color: r.taxable ? '#FFB800' : '#737373' }}>
                      {r.taxable ? 'Taxable' : 'Sheltered'}
                    </span>
                  </div>
                  <div style={{ marginLeft: 'auto', fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: r.total < 0 ? '#FF5A5A' : '#00D632' }}>
                    {formatFullCurrency(r.total)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-5)', marginTop: 'var(--space-3)' }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>Options</div>
                    <div style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: r.options === 0 ? 'var(--color-text-tertiary)' : r.options < 0 ? '#FF5A5A' : '#00D632' }}>
                      {r.options !== 0 ? formatFullCurrency(r.options) : '—'}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>Equity</div>
                    <div style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: r.equity === 0 ? 'var(--color-text-tertiary)' : r.equity < 0 ? '#FF5A5A' : '#00A3FF' }}>
                      {r.equity !== 0 ? formatFullCurrency(r.equity) : '—'}
                    </div>
                  </div>
                  {r.divInt !== 0 && (
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>Div + Int</div>
                      <div style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-secondary)' }}>
                        {formatFullCurrency(r.divInt)}
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ marginTop: 'var(--space-3)', fontSize: 12, color: 'var(--color-text-tertiary)' }}>View details →</div>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
