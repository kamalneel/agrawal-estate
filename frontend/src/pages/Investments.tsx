import React, { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { TrendingUp, TrendingDown, ArrowLeft, User, Heart, Briefcase, RefreshCw, AlertCircle, ChevronRight } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  ResponsiveContainer,
} from 'recharts'
import styles from './Investments.module.css'
import clsx from 'clsx'
import { AssignmentLossCard } from '../components/AssignmentLossCard/AssignmentLossCard'
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
  PeriodSelector,
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
  /** Days since the cost-weighted average purchase date across open lots */
  held_days?: number | null
  /** CAGR %; null for positions held <90 days (annualizing is meaningless) */
  annualized_pct?: number | null
}

/** "12d", "5w", "8mo", "2.3y" from a day count */
function formatHeld(days: number): string {
  if (days < 14) return `${days}d`
  if (days < 70) return `${Math.round(days / 7)}w`
  if (days < 365) return `${Math.round(days / 30.44)}mo`
  return `${(days / 365).toFixed(1)}y`
}

// ── Winners & Losers sorting ────────────────────────────────────────────
// Same interaction as HoldingsTable: click cycles desc → asc → unsorted
// (unsorted restores the backend's gain-ranked order, which IS the point
// of the panel — winners top, losers bottom).
type SortDir = 'asc' | 'desc' | null

/** Sort value per column; null/undefined always sinks to the bottom */
const OPEN_SORT_VALUES: Record<string, (p: PurePosition) => number | string | null | undefined> = {
  symbol: p => p.symbol,
  weight: p => p.weight_pct,
  value: p => p.value,
  cost_basis: p => p.cost_basis,
  gain: p => p.gain,
  gain_pct: p => p.gain_pct,
  held: p => p.held_days,
  annualized: p => p.annualized_pct,
}

const CLOSED_SORT_VALUES: Record<string, (p: PurePosition) => number | string | null | undefined> = {
  symbol: p => p.symbol,
  closed_date: p => p.closed_date,
  proceeds: p => p.proceeds,
  cost_basis: p => p.cost_basis,
  gain: p => p.gain,
  gain_pct: p => p.gain_pct,
}

function sortPositions(
  rows: PurePosition[],
  key: string,
  dir: SortDir,
  accessors: Record<string, (p: PurePosition) => number | string | null | undefined>,
): PurePosition[] {
  const get = accessors[key]
  if (dir === null || !get) return rows
  const sign = dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const va = get(a)
    const vb = get(b)
    // Missing values (— cells: no ann. return, no close date) stay last in
    // both directions — they carry no rank, so flipping them is noise.
    if (va == null && vb == null) return a.symbol.localeCompare(b.symbol)
    if (va == null) return 1
    if (vb == null) return -1
    const cmp = typeof va === 'string' || typeof vb === 'string'
      ? String(va).localeCompare(String(vb))
      : (va as number) - (vb as number)
    return sign * cmp
  })
}

function SortTh({ label, sortKey, active, dir, onSort, numeric = true }: {
  label: string
  sortKey: string
  active: string
  dir: SortDir
  onSort: (key: string) => void
  numeric?: boolean
}) {
  const isActive = active === sortKey && dir !== null
  return (
    <th
      className={clsx(numeric && styles.num, styles.sortableTh, isActive && styles.sortedTh)}
      onClick={() => onSort(sortKey)}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(sortKey) } }}
      tabIndex={0}
      role="columnheader"
      aria-sort={isActive ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      {label}
      <span className={clsx(styles.sortIcon, !isActive && styles.sortIconIdle)}>
        {isActive ? (dir === 'asc' ? '↑' : '↓') : '⇅'}
      </span>
    </th>
  )
}

/** account_id → short human label for the allocation routing cells */
const ACCT_LABELS: Record<string, string> = {
  neel_brokerage: 'Neel Brok', neel_retirement: 'Neel IRA', neel_roth_ira: 'Neel Roth',
  jaya_brokerage: 'Jaya Brok', jaya_ira: 'Jaya IRA', jaya_roth_ira: 'Jaya Roth',
  alisha_brokerage: 'Alisha Brok', family_hsa: 'HSA',
}
const acctLabel = (id: string) => ACCT_LABELS[id] ?? id

// Allocation targets — see docs/INVESTMENTS-PAGE-SPEC.md, "Allocation
// targets & execution". Targets are declared share counts in
// data/allocation_targets.json; the backend turns each gap into the ATM
// option order that closes it.
interface AllocOrder {
  option_type: 'put' | 'call'
  /** sell = write new contracts; roll = existing far-OTM calls occupy the
      shares and must be rolled down to ATM to actually produce the exit */
  instruction: 'sell' | 'roll'
  contracts: number
  sell_contracts: number
  roll_contracts: number
  strike: number
  est_premium: number
  expiration: string
}

interface AllocAccount {
  account_id: string
  held_as: string
  shares: number
  sheltered: boolean
  cost_per_share: number | null
}

interface AllocLot {
  purchase_date: string
  shares: number
  cost_per_share: number
  realized_gain: number
}

interface AllocRouting {
  /** trim/exit: which accounts to sell calls in, cheapest tax first, with the
      exact lots each leg would deliver (highest basis first) */
  legs?: { account_id: string; shares: number; contracts: number; sheltered: boolean; realized_gain: number | null; lots?: AllocLot[] }[]
  /** total gain/loss the recommended routing realizes */
  realized_gain?: number
  /** gain avoided vs FIFO — GAIN, not tax (the rate is Neel's) */
  gain_avoided_vs_worst?: number
  basis_unknown?: boolean
  /** buy: which account to sell puts in */
  buy_account?: string
  consolidates?: boolean
  funded?: boolean
  shortfall?: number
}

interface AllocRow {
  symbol: string
  accounts: AllocAccount[]
  routing: AllocRouting | null
  baseline_shares: number | null
  shares_moved: number | null
  gap_closed_pct: number | null
  current_shares: number
  current_value: number
  current_pct: number | null
  target_shares: number
  target_value: number | null
  target_pct: number | null
  gap_shares: number
  gap_value: number | null
  action: 'buy' | 'trim' | 'exit' | 'hold' | 'done'
  contracts: number
  /** shares the round-lot rule can't express as a contract (MU's 60) */
  residual_shares: number
  open_contracts: number
  order: AllocOrder | null
  guidance: string | null
  optionable: boolean
  price: number | null
  price_source: 'live' | 'reference' | 'none'
  price_as_of: string | null
}

interface AllocBucket {
  key: string
  label: string
  note: string | null
  target_pct: number | null
  rows: AllocRow[]
  current_value: number
  current_pct: number | null
  target_value: number
  target_computed_pct: number | null
  shares_needed: number
  shares_moved: number
  gap_closed_pct: number
}

interface AllocProgression {
  since: string
  days_elapsed: number
  /** false until enough history exists — velocity off 1 day is noise */
  measurable: boolean
  shares_needed: number
  shares_moved: number
  gap_closed_pct: number
  shares_per_week: number | null
  weeks_to_target: number | null
  premium_since: number
  note: string
  early_note: string | null
}

interface AllocationPlan {
  as_of: string
  policy_as_of: string | null
  base_value: number
  expiration: string
  buckets: AllocBucket[]
  exit_rows: AllocRow[]
  progression: AllocProgression
  feasibility: {
    put_collateral_needed: number
    total_cash: number | null
    /** excludes collateral already securing open puts and margin-drawn accounts */
    deployable_cash: number
    cash_by_account: Record<string, { account_name: string; total_cash: number; deployable_cash: number; collateral_committed: number; margin_used: number; sheltered: boolean }>
    largest_single_put_affordable: number
    unaffordable_today: string[]
    exit_and_trim_proceeds: number
    headroom: number
    covered: boolean
    covered_by_cash_alone: boolean
    note: string
  }
  reference_priced_symbols: string[]
  premium_disclaimer: string
}

// Two-book strategy deviations — see docs/INVESTMENTS-PAGE-SPEC.md,
// "Strategy model & policy deviations"
interface CoreExit {
  account_id: string
  account_name: string
  symbol: string
  exit_date: string
  shares_sold: number
  sale_px: number
  price_now: number | null
  shares_recovered: number
  shares_unrecovered: number
  open_put_contracts: number
  put_premium_since: number
  gap: number | null
  days_since_exit: number
  status: 'recovered' | 'recovering' | 'idle'
}

interface IdleInventory {
  account_id: string
  account_name: string
  symbol: string
  shares: number
  coverable_contracts: number
  open_call_contracts: number
  uncovered_contracts: number
  idle_value: number | null
}

interface PolicyDeviations {
  as_of: string
  policy: { core: string[]; inventory: string[]; unclassified: string[] }
  core_exits: CoreExit[]
  idle_inventory: IdleInventory[]
  distraction: { open_exit_gap: number; inventory_put_income_since: number; since: string | null }
}

// Ghost freeze-curve — "vs. Buy & Hold" (docs/INVESTMENTS-PAGE-SPEC.md)
interface GhostCurve {
  as_of: string
  actual_today: number
  curve: { anchor: string; ghost_value_today: number; delta: number; unpriced_symbols: string[] }[]
  anchors_from: string
  anchors_limited_reason: string
  assignments: { date: string; symbol: string; contracts: number }[]
  premium_collected_window: number
  stale_prices: Record<string, string>
}

interface GhostDetail {
  anchor: string
  ghost_series: { date: string; value: number }[]
  actual_series: { date: string; value: number }[]
  divergence: { symbol: string; ghost_shares: number; actual_shares: number; delta_shares: number; delta_value: number }[]
  premium_since: number
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

// Per-symbol trade provenance shown when a Winners & Losers row is
// expanded — answers "when did I buy/sell this, at what price, where?"
// Sign convention: cash out (BUY) = red negative, cash in (SELL) = green
// positive — the old Capital Flow table had this inverted.
function BetTradeHistory({ symbol, trades }: { symbol: string; trades: CapitalEvent[] | null }) {
  if (trades === null) return <div className={styles.betDrillLoading}>Loading trades…</div>
  const rows = trades.filter(t => t.symbol === symbol)
  if (rows.length === 0) return <div className={styles.betDrillLoading}>No recorded trades for {symbol}.</div>
  return (
    <table className={styles.betDrillTable}>
      <thead>
        <tr>
          <th>Date</th><th>Type</th><th className={styles.num}>Shares</th>
          <th className={styles.num}>Price/Share</th><th>Account</th>
          <th className={styles.num}>Cash Flow</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t, i) => {
          const isBuy = t.type === 'BUY'
          const flow = isBuy ? -t.amount : t.amount
          return (
            <tr key={i}>
              <td>{t.formatted}</td>
              <td>
                <span className={styles.betDrillType} style={{ color: isBuy ? '#00A3FF' : '#A855F7' }}>{t.type}</span>
              </td>
              <td className={styles.num}>{t.quantity != null ? Math.round(t.quantity).toLocaleString() : '—'}</td>
              <td className={styles.num}>{t.price_per_share != null ? `$${t.price_per_share.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}</td>
              <td>{t.account_name}</td>
              <td className={styles.num} style={{ color: flow >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                {flow >= 0 ? '+' : '-'}{formatCurrency(Math.abs(flow))}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// Module-level cache for stock growth data (survives re-mounts across page navigations)
let _stockGrowthCache: { data: Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }>; ts: number } | null = null
const STOCK_GROWTH_CACHE_TTL = 60 * 60 * 1000 // 1 hour in ms

// Main Investments Component
export function Investments() {
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [stockGrowthData, setStockGrowthData] = useState<Record<string, { growth_ytd: number | null; growth_1y: number | null; growth_5y: number | null; holding_period_days: number | null }> | null>(_stockGrowthCache?.data ?? null)
  const [cashBreakdown, setCashBreakdown] = useState<{ total_true_cash: number; total_margin_used: number; total_options_collateral: number; accounts: (CashAccountData & { account_name: string })[] } | null>(null)
  const [acctTruePortHistory, setAcctTruePortHistory] = useState<{ date: string; stock_value: number; true_cash: number; true_portfolio: number; is_real: boolean }[]>([])
  const [acctRealDataStart, setAcctRealDataStart] = useState<string | null>(null)
  const [acctTruePortPeriod, setAcctTruePortPeriod] = useState<string | null>(null)
  const [purePerf, setPurePerf] = useState<PurePerformance | null>(null)
  const [showClosedBets, setShowClosedBets] = useState(false)
  const [showSmallOpen, setShowSmallOpen] = useState(false)
  const [showSmallClosed, setShowSmallClosed] = useState(false)
  const [expandedBet, setExpandedBet] = useState<string | null>(null)
  // null dir = backend's gain-ranked order (the panel's default reading)
  const [openSortKey, setOpenSortKey] = useState('gain')
  const [openSortDir, setOpenSortDir] = useState<SortDir>(null)
  const [closedSortKey, setClosedSortKey] = useState('gain')
  const [closedSortDir, setClosedSortDir] = useState<SortDir>(null)
  const [betTrades, setBetTrades] = useState<CapitalEvent[] | null>(null)
  const [pureChartPeriod, setPureChartPeriod] = useState<string | null>(null)
  const [deviations, setDeviations] = useState<PolicyDeviations | null>(null)
  const [allocation, setAllocation] = useState<AllocationPlan | null>(null)
  const [showArchive, setShowArchive] = useState(false)
  const [showRecoveredExits, setShowRecoveredExits] = useState(false)
  const [ghost, setGhost] = useState<GhostCurve | null>(null)
  const [ghostDetail, setGhostDetail] = useState<GhostDetail | null>(null)
  const [ghostDetailLoading, setGhostDetailLoading] = useState(false)

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

  // All BUY/SELL trades, fetched once on first Winners & Losers drill —
  // per-symbol provenance ("when did I buy all this?") lives behind a
  // click, not on the default page (see INVESTMENTS-PAGE-SPEC).
  const toggleBetDrill = (symbol: string) => {
    setExpandedBet(prev => (prev === symbol ? null : symbol))
    if (betTrades === null) {
      fetch(`${API_BASE}/investments/capital-events?min_amount=0`, { headers: getAuthHeaders() })
        .then(r => r.ok ? r.json() : null)
        .then(d => d && setBetTrades(d.events || []))
        .catch(() => {})
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
    fetchStockGrowth()
    fetch(`${API_BASE}/ingestion/robinhood-cash/balances`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setCashBreakdown(d))
      .catch(() => {})
    fetchPurePerformance()
    fetchPolicyDeviations()
    fetchAllocationPlan()
  }, [])

  const fetchAllocationPlan = () => {
    fetch(`${API_BASE}/investments/allocation-plan`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setAllocation(d))
      .catch(() => {})
  }

  const fetchPurePerformance = () => {
    fetch(`${API_BASE}/investments/pure-performance`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setPurePerf(d))
      .catch(() => {})
  }

  const fetchPolicyDeviations = () => {
    fetch(`${API_BASE}/investments/policy-deviations`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setDeviations(d))
      .catch(() => {})
  }

  useEffect(() => {
    fetch(`${API_BASE}/investments/ghost-curve`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.curve?.length && setGhost(d))
      .catch(() => {})
  }, [])

  const openGhostDetail = (anchor: string) => {
    setGhostDetailLoading(true)
    fetch(`${API_BASE}/investments/ghost-curve/detail?anchor=${anchor}`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && !d.error) setGhostDetail(d) })
      .finally(() => setGhostDetailLoading(false))
  }

  const totalEquity = accounts.reduce((sum, acc) => sum + acc.value, 0)
  const totalChange = accounts.reduce((sum, acc) => sum + acc.change, 0)
  const totalChangePercent = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : 0

  // Period options for the pure chart: drop 1D (meaningless at daily
  // resolution — a weekend click left <2 points and silently fell back
  // to all-time, Neel 2026-07-18) and hide presets whose cutoff predates
  // the data (they'd duplicate ALL exactly; YTD/1Y reappear once the
  // history reaches back that far).
  const pureChartPeriodOptions = useMemo(() => {
    const first = purePerf?.chart?.[0]?.date
    const today = new Date()
    const cutoffISO = (key: string | null): string | null => {
      switch (key) {
        case '1w': return new Date(today.getTime() - 7 * 86400000).toISOString().slice(0, 10)
        case '30d': return new Date(today.getTime() - 30 * 86400000).toISOString().slice(0, 10)
        case '90d': return new Date(today.getTime() - 90 * 86400000).toISOString().slice(0, 10)
        case 'ytd': return `${today.getFullYear()}-01-01`
        case '1y': return new Date(today.getTime() - 365 * 86400000).toISOString().slice(0, 10)
        default: return null
      }
    }
    return PERIOD_PRESETS.EXTENDED.filter(o => {
      if (o.key === '1d') return false
      if (o.key === null || !first) return true
      const c = cutoffISO(o.key)
      return c !== null && c >= first
    })
  }, [purePerf])

  // if the selected period's button disappeared, fall back to ALL
  useEffect(() => {
    if (pureChartPeriod && !pureChartPeriodOptions.some(o => o.key === pureChartPeriod)) {
      setPureChartPeriod(null)
    }
  }, [pureChartPeriodOptions, pureChartPeriod])

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
          <div className={styles.pureHeroControls}>
            <PeriodSelector
              options={pureChartPeriodOptions}
              value={pureChartPeriod}
              onChange={setPureChartPeriod}
            />
            <button onClick={() => { fetchHoldings(); fetchStockGrowth(true); fetchPurePerformance(); }} className={styles.heroRefresh} title="Refresh data">
              <RefreshCw size={18} />
            </button>
          </div>
        </section>
      )}

      {/* L1.5 — Allocation targets. Sits above Winners & Losers because the
          target is now the primary read: W&L says how the bets did, this
          says what the book should become and what order closes the gap.
          Spec: "Allocation targets & execution". */}
      {allocation && allocation.buckets.length > 0 && (() => {
        const pct = (v: number | null) => v == null ? '—' : `${v.toFixed(1)}%`
        // Fractional shares are real (MU is 41.873) but 3 decimals in a share
        // column is noise — show 2 only when the position actually is partial.
        const sh = (v: number) => Number.isInteger(v)
          ? v.toLocaleString()
          : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        const actionChip = (r: AllocRow) => {
          if (r.action === 'hold' || r.action === 'done') return null
          const cls = r.action === 'buy' ? styles.allocBuy
            : r.action === 'trim' ? styles.allocTrim : styles.allocExit
          return <span className={clsx(styles.allocChip, cls)}>{r.action}</span>
        }
        // The order IS the instruction — "sell 10 puts @ $216.53" is what
        // gets placed. Roll vs sell matters: existing Tier-1 calls occupy
        // the shares but are too far OTM to ever produce the exit.
        // Which account to place it in. For trims this is the tax decision —
        // the same 600 NVDA shares realise $143K of gain from Jaya's
        // Brokerage (basis $18.93) and nothing from Jaya's IRA (basis $215).
        const routingCell = (r: AllocRow) => {
          const rt = r.routing
          if (!rt) return null
          if (rt.legs?.length) {
            const g = rt.realized_gain ?? 0
            return (
              <span className={styles.allocRouting}>
                in {rt.legs.map(l => (
                  <span key={l.account_id}>
                    <strong>{acctLabel(l.account_id)}</strong> ({l.contracts}c
                    {l.sheltered && <span className={styles.allocShelter} title="Sheltered — sale is not a taxable event">tax-free</span>})
                    {' '}
                  </span>
                ))}
                {/* The exact lots the sale delivers, highest basis first.
                    Without this the recommendation is un-checkable: "sell 4
                    TSLA calls" reads identically whether it realizes a $32K
                    loss or a $97K gain — the difference is only which lots go. */}
                {rt.legs.some(l => l.lots?.length) && (
                  <span className={styles.allocLots}>
                    {/* index in the key: same-day same-price lots are common
                        (IBIT has several), so date+basis is not unique */}
                    {rt.legs.flatMap(l => (l.lots ?? []).map((lot, i) => (
                      <span key={`${l.account_id}-${i}-${lot.purchase_date}`} className={styles.allocLotLine}>
                        {acctLabel(l.account_id)} · {lot.shares.toLocaleString()} sh @ ${lot.cost_per_share.toFixed(2)}
                        {' '}({new Date(lot.purchase_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' })})
                        <span style={{ color: lot.realized_gain >= 0 ? 'var(--color-negative, #FF5A5A)' : 'var(--color-positive, #00D632)' }}>
                          {' '}{lot.realized_gain >= 0 ? '+' : '−'}{formatCurrency(Math.abs(lot.realized_gain))}
                        </span>
                      </span>
                    )))}
                  </span>
                )}
                {rt.realized_gain != null && rt.legs.some(l => !l.sheltered) && (
                  <span className={g <= 0 ? styles.allocSaves : styles.allocUnfunded}>
                    realizes {g <= 0 ? 'a LOSS of ' : 'a gain of '}{formatCurrency(Math.abs(g))}
                    {(rt.gain_avoided_vs_worst ?? 0) > 500 && ` · ${formatCurrency(rt.gain_avoided_vs_worst!)} better than FIFO`}
                  </span>
                )}
                {rt.legs.every(l => l.sheltered) && (rt.gain_avoided_vs_worst ?? 0) > 500 && (
                  <span className={styles.allocSaves}>tax-free — avoids {formatCurrency(rt.gain_avoided_vs_worst!)} of gain vs. the taxable account</span>
                )}
              </span>
            )
          }
          if (rt.buy_account) {
            return (
              <span className={styles.allocRouting}>
                in <strong>{acctLabel(rt.buy_account)}</strong>
                {rt.consolidates && <span className={styles.allocShelter} title="Already holds this symbol — keeps the position in one account">consolidates</span>}
                {rt.funded === false && (
                  <span className={styles.allocUnfunded}>
                    can’t secure yet — short {formatCurrency(rt.shortfall ?? 0)}
                  </span>
                )}
              </span>
            )
          }
          return null
        }
        const orderCell = (r: AllocRow) => {
          if (!r.order) {
            return (
              <>
                <span className={styles.allocGuidance}>{r.guidance ?? '—'}</span>
                {routingCell(r)}
              </>
            )
          }
          const o = r.order
          return (
            <>
              <span className={styles.allocOrder}>
                {o.instruction === 'roll' ? 'roll' : 'sell'} {o.contracts} {o.option_type}
                {o.contracts === 1 ? '' : 's'} → ATM ${o.strike.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
              <span className={styles.allocOrderMeta}>
                est {formatCurrency(o.est_premium)}/wk · exp {new Date(o.expiration + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                {o.instruction === 'roll' && ' · existing calls too far OTM to assign'}
                {r.residual_shares > 0 && ` · +${r.residual_shares} sh odd lot`}
              </span>
              {routingCell(r)}
            </>
          )
        }
        const allocRow = (r: AllocRow) => (
          <tr key={r.symbol} className={styles.betRow}>
            <td className={styles.betSym}>
              {r.symbol}
              {r.price_source === 'reference' && (
                <span className={styles.allocRefPx} title={`Not held — no quote source. Reference price from data/allocation_targets.json, ${r.price_as_of}`}>ref</span>
              )}
            </td>
            <td className={styles.num}>{pct(r.current_pct)}</td>
            <td className={styles.num}>{formatCurrency(r.current_value)}</td>
            <td className={styles.num}>{sh(r.current_shares)}</td>
            <td className={styles.num}>{pct(r.target_pct)}</td>
            <td className={styles.num}>{r.target_value != null ? formatCurrency(r.target_value) : '—'}</td>
            <td className={styles.num}>{sh(r.target_shares)}</td>
            <td className={styles.num} style={{ color: Math.abs(r.gap_shares) < 1 ? undefined : r.gap_shares > 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
              {Math.abs(r.gap_shares) < 1 ? '—' : `${r.gap_shares > 0 ? '+' : ''}${sh(Math.round(r.gap_shares))}`}
            </td>
            <td className={styles.allocActionCell}>{actionChip(r)}{orderCell(r)}</td>
          </tr>
        )
        const header = (
          <tr>
            <th>Symbol</th>
            <th className={styles.num}>Now %</th><th className={styles.num}>Now $</th><th className={styles.num}>Now sh</th>
            <th className={styles.num}>Target %</th><th className={styles.num}>Target $</th><th className={styles.num}>Target sh</th>
            <th className={styles.num}>Gap sh</th>
            <th>Order</th>
          </tr>
        )
        const f = allocation.feasibility
        return (
          <section className={styles.betsSection}>
            <div className={styles.allocHeader}>
              <h2>Allocation Targets</h2>
              <span className={styles.allocSub}>
                base {formatCurrency(allocation.base_value)} · policy {allocation.policy_as_of}
              </span>
            </div>

            {/* Progress is counted in SHARES. At ATM roughly half the
                contracts expire unassigned, so premium can climb for months
                while the position never moves — showing dollars first would
                make a stalled plan look like a working one. */}
            {(() => {
              const p = allocation.progression
              return (
                <div className={styles.allocProgress}>
                  <div className={styles.allocProgressBarWrap}>
                    <div className={styles.allocProgressBar} style={{ width: `${Math.min(100, p.gap_closed_pct)}%` }} />
                  </div>
                  <div className={styles.allocProgressStats}>
                    <span className={styles.allocProgressMain}>{p.gap_closed_pct}% of the plan executed</span>
                    <span className={styles.allocProgressStat}>{p.shares_moved.toLocaleString()} of {p.shares_needed.toLocaleString()} shares moved</span>
                    <span className={styles.allocProgressStat}>premium since {p.since}: <strong>{formatCurrency(p.premium_since)}</strong></span>
                    {p.measurable && p.shares_per_week != null && (
                      <span className={styles.allocProgressStat}>{p.shares_per_week.toLocaleString()} sh/wk</span>
                    )}
                    {p.measurable && p.weeks_to_target != null && (
                      <span className={styles.allocProgressStat}>≈{p.weeks_to_target} weeks to target</span>
                    )}
                  </div>
                  <p className={styles.allocProgressNote}>{p.early_note ?? p.note}</p>
                </div>
              )
            })()}

            {allocation.buckets.map(b => (
              <div key={b.key} className={styles.allocBucket}>
                <h3 className={styles.devSubhead}>
                  {b.label}
                  <span className={styles.allocBucketPct}>
                    now {pct(b.current_pct)} → target {b.target_pct}%
                    {b.target_computed_pct != null && ` (these share counts = ${b.target_computed_pct.toFixed(1)}%)`}
                    {b.shares_needed > 0 && ` · ${b.gap_closed_pct}% executed, ${b.shares_moved.toLocaleString()}/${b.shares_needed.toLocaleString()} sh`}
                  </span>
                </h3>
                {b.note && <p className={styles.allocNote}>{b.note}</p>}
                <div className={styles.betsTableWrap}>
                  <table className={styles.betsTable}>
                    <thead>{header}</thead>
                    <tbody>{b.rows.map(allocRow)}</tbody>
                  </table>
                </div>
              </div>
            ))}

            {allocation.exit_rows.length > 0 && (
              <div className={styles.allocBucket}>
                <h3 className={styles.devSubhead}>
                  Off-thesis — exit
                  <span className={styles.allocBucketPct}>
                    {formatCurrency(allocation.exit_rows.reduce((s, r) => s + r.current_value, 0))} to recycle
                  </span>
                </h3>
                <div className={styles.betsTableWrap}>
                  <table className={styles.betsTable}>
                    <thead>{header}</thead>
                    <tbody>{allocation.exit_rows.map(allocRow)}</tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Feasibility: ATM puts tie up the full strike notional, so the
                buy program is gated on the sells clearing first. Saying this
                beats listing orders that can't be placed. */}
            <p className={styles.allocFeasibility}>
              Put collateral needed <strong>{formatCurrency(f.put_collateral_needed)}</strong>
              {' · '}deployable cash <strong style={{ color: f.covered_by_cash_alone ? undefined : 'var(--color-negative, #FF5A5A)' }}>{formatCurrency(f.deployable_cash)}</strong>
              {' '}<span className={styles.allocOrderMeta}>(of {formatCurrency(f.total_cash ?? 0)} total — the rest is collateral already securing open puts, or margin-drawn)</span>
              {' · '}exit + trim proceeds <strong>{formatCurrency(f.exit_and_trim_proceeds)}</strong>
              <br />
              Largest single put you can secure today: <strong>{formatCurrency(f.largest_single_put_affordable)}</strong>
              {f.unaffordable_today.length > 0 && (
                <> — <strong style={{ color: 'var(--color-negative, #FF5A5A)' }}>{f.unaffordable_today.join(', ')}</strong> cannot be sold as cash-secured puts until the sells clear.</>
              )}
              <br />{f.note}
            </p>
            <p className={styles.allocDisclaimer}>
              {allocation.premium_disclaimer}
              {allocation.reference_priced_symbols.length > 0 && (
                <> Reference-priced (not held, no live quote): {allocation.reference_priced_symbols.join(', ')}.</>
              )}
              {' '}Placement, per-account sizing and this week's RSI gate stay on{' '}
              <Link to="/strategies/options-selling" className={styles.allocLink}>Options Execution</Link>.
            </p>
          </section>
        )
      })()}

      {purePerf && purePerf.chart.length > 1 && (
        <ChartWrapper
          title="Value vs. Capital Invested"
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


      {/* Assignment Loss history — moved here from Options Execution
          2026-07-22: that page is scoped to "what should I do today, am
          I on pace" (current period only); this is retrospective
          analysis, which belongs with Strategy Deviations / Ghost Curve
          here instead. Options Execution keeps just the current-month
          figure (AssignmentLossThisMonth). */}
      <AssignmentLossCard />

      {/* vs. Buy & Hold — ghost freeze-curve (spec: "vs. Buy & Hold").
          Each point: "if I had frozen the options game on this date
          (bought back open options, held shares+cash), what would that be
          worth today vs. what I actually have?" Above zero = freezing
          would have won. Click a point to drill. */}
      {ghost && (() => {
        const data = ghost.curve.map(c => ({ ...c, label: new Date(c.anchor + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }))
        const assignByDate = new Map<string, string[]>()
        ghost.assignments.forEach(a => {
          const cur = assignByDate.get(a.date) ?? []
          if (!cur.includes(a.symbol)) cur.push(a.symbol)
          assignByDate.set(a.date, cur)
        })
        const markers = data.filter(d => assignByDate.has(d.anchor))
        const latest = data[data.length - 1]
        return (
          <section className={styles.betsSection}>
            <h2>vs. Buy &amp; Hold</h2>
            <p className={styles.ghostSub}>
              Each point: freeze the options game that day (buy back open options, hold shares + cash) — what would it be worth today
              vs. actual {formatCurrency(ghost.actual_today)}? Above zero: freezing would have won. ▲ = assignment days. Click to drill.
            </p>
            <div className={styles.ghostStatRow}>
              <span>Latest anchor gap: <strong style={{ color: (latest?.delta ?? 0) > 0 ? 'var(--color-negative, #FF5A5A)' : 'var(--color-positive, #00D632)' }}>
                {latest && latest.delta > 0 ? `buy & hold +${formatCurrency(latest.delta)}` : `options game +${formatCurrency(Math.abs(latest?.delta ?? 0))}`}</strong></span>
              <span>Premium collected in window: <strong>{formatCurrency(ghost.premium_collected_window)}</strong></span>
              <span className={styles.ghostCaveat}>{ghost.anchors_limited_reason}</span>
            </div>
            <div style={{ cursor: 'pointer' }}>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={data} margin={CHART_MARGINS}
                onClick={(e: any) => { const a = e?.activePayload?.[0]?.payload?.anchor; if (a) openGhostDetail(a) }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="label" {...X_AXIS_PROPS} />
                <YAxis {...Y_AXIS_PROPS} tickFormatter={(v: number) => formatCurrencyShort(v)} />
                <Tooltip
                  formatter={(v: number) => [
                    `${v > 0 ? 'buy & hold ahead by ' : 'options game ahead by '}${formatCurrency(Math.abs(v))}`,
                    'freeze here vs. actual']}
                  labelFormatter={(l: string, p: any) => {
                    const anchor = p?.[0]?.payload?.anchor
                    const syms = anchor ? assignByDate.get(anchor) : undefined
                    return `Freeze on ${l}${syms ? ` · assignments: ${syms.join(', ')}` : ''} — click to drill`
                  }}
                />
                <ReferenceLine y={0} stroke="var(--color-border)" strokeDasharray="4 4" />
                <Area type="monotone" dataKey="delta" stroke="#C49A3C" fill="#C49A3C22" strokeWidth={2}
                  activeDot={{ r: 6, cursor: 'pointer',
                               onClick: (_: any, dot: any) => { const a = dot?.payload?.anchor; if (a) openGhostDetail(a) } }} />
                {markers.map(m => (
                  <ReferenceDot key={m.anchor} x={m.label} y={m.delta} r={4} fill="#C49A3C" stroke="var(--color-bg-primary)" />
                ))}
              </AreaChart>
            </ResponsiveContainer>
            </div>
            {ghostDetailLoading && <p className={styles.ghostSub}>Loading drill-down…</p>}
            {ghostDetail && (
              <div className={styles.ghostModalOverlay} onClick={() => setGhostDetail(null)}>
                <div className={styles.ghostModal} onClick={e => e.stopPropagation()}>
                  <div className={styles.ghostModalHead}>
                    <h3>Frozen on {new Date(ghostDetail.anchor + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} vs. actual</h3>
                    <button onClick={() => setGhostDetail(null)}>✕</button>
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    {/* both series merged onto one sorted date grid — two
                        Lines with separate data arrays make recharts append
                        ghost-only dates AFTER the actual dates (Jun 30
                        rendered right of Jul 16, gold line zigzagging back
                        through the chart; Neel's screenshot 2026-07-18) */}
                    <LineChart margin={CHART_MARGINS} data={(() => {
                      const byDate = new Map<string, { date: string; actual?: number; ghostV?: number }>()
                      ghostDetail.actual_series.forEach(p => byDate.set(p.date, { ...(byDate.get(p.date) ?? { date: p.date }), actual: p.value }))
                      ghostDetail.ghost_series.forEach(p => byDate.set(p.date, { ...(byDate.get(p.date) ?? { date: p.date }), ghostV: p.value }))
                      return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
                    })()}>
                      <CartesianGrid {...GRID_PROPS} />
                      <XAxis dataKey="date" {...X_AXIS_PROPS} />
                      <YAxis {...Y_AXIS_PROPS} domain={['auto', 'auto']} tickFormatter={(v: number) => formatCurrencyShort(v)} />
                      <Tooltip formatter={(v: number, name: string) => [formatCurrency(v), name]} />
                      <Line dataKey="actual" name="Actual" type="monotone" stroke={CHART_GREEN} dot={false} strokeWidth={2} connectNulls />
                      <Line dataKey="ghostV" name="Ghost (frozen)" type="monotone" stroke="#C49A3C" dot={false} strokeWidth={2} strokeDasharray="6 4" connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                  <p className={styles.ghostSub}>Options premium collected since this date: <strong>{formatCurrency(ghostDetail.premium_since)}</strong></p>
                  {ghostDetail.divergence.length > 0 && (
                    <div className={styles.betsTableWrap}>
                      <table className={styles.betsTable}>
                        <thead>
                          <tr><th>Symbol</th><th className={styles.num}>Ghost holds</th><th className={styles.num}>You hold</th><th className={styles.num}>Δ shares</th><th className={styles.num}>Δ value today</th></tr>
                        </thead>
                        <tbody>
                          {ghostDetail.divergence.map(r => (
                            <tr key={r.symbol} className={styles.betRow}>
                              <td className={styles.betSym}>{r.symbol}</td>
                              <td className={styles.num}>{r.ghost_shares.toLocaleString()}</td>
                              <td className={styles.num}>{r.actual_shares.toLocaleString()}</td>
                              <td className={styles.num}>{r.delta_shares > 0 ? '+' : ''}{r.delta_shares.toLocaleString()}</td>
                              <td className={styles.num} style={{ color: r.delta_value >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                                {r.delta_value >= 0 ? '+' : '-'}{formatCurrency(Math.abs(r.delta_value))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        )
      })()}

      {/* L2 — winners & losers: which bets are working, ranked by return.
          Positions under $5K fold into one expandable line — space follows
          money (playbook), and a $24 FIG row shouldn't get equal billing
          with a $787K TSLA bet. */}
      {purePerf && purePerf.open_positions.length > 0 && (() => {
        const SMALL = 5000
        const isSmallOpen = (p: PurePosition) => Math.max(p.value ?? 0, p.cost_basis) < SMALL
        const isSmallClosed = (p: PurePosition) => Math.max(p.proceeds ?? 0, p.cost_basis) < SMALL
        const sortOpen = (rows: PurePosition[]) => sortPositions(rows, openSortKey, openSortDir, OPEN_SORT_VALUES)
        const sortClosed = (rows: PurePosition[]) => sortPositions(rows, closedSortKey, closedSortDir, CLOSED_SORT_VALUES)
        // Small positions sort within their fold, not into the main list —
        // the <$5K rollup stays one collapsed block whatever the sort.
        const mainOpen = sortOpen(purePerf.open_positions.filter(p => !isSmallOpen(p)))
        const smallOpen = sortOpen(purePerf.open_positions.filter(isSmallOpen))
        const mainClosed = sortClosed(purePerf.closed_positions.filter(p => !isSmallClosed(p)))
        const smallClosed = sortClosed(purePerf.closed_positions.filter(isSmallClosed))
        const smallOpenNet = smallOpen.reduce((s, p) => s + (p.gain ?? 0), 0)
        const smallClosedNet = smallClosed.reduce((s, p) => s + (p.gain ?? 0), 0)

        // Direction comes from the functional setter, not a param — the
        // caller's `dir` would be a stale closure on rapid clicks.
        const cycleSort = (
          key: string,
          activeKey: string,
          setKey: (k: string) => void,
          setDir: (d: SortDir | ((d: SortDir) => SortDir)) => void,
        ) => {
          if (activeKey !== key) {
            setKey(key)
            setDir(key === 'symbol' ? 'asc' : 'desc')
          } else {
            setDir(d => (d === 'desc' ? 'asc' : d === 'asc' ? null : 'desc'))
          }
        }
        const sortOpenBy = (key: string) => cycleSort(key, openSortKey, setOpenSortKey, setOpenSortDir)
        const sortClosedBy = (key: string) => cycleSort(key, closedSortKey, setClosedSortKey, setClosedSortDir)

        const openRow = (p: PurePosition) => (
          <React.Fragment key={p.symbol}>
            <tr className={styles.betRow} onClick={() => toggleBetDrill(p.symbol)}>
              <td className={styles.betSym}>
                {p.symbol}
                <ChevronRight size={12} className={clsx(styles.betChevron, expandedBet === p.symbol && styles.betChevronOpen)} />
              </td>
              <td className={styles.num}>{p.weight_pct != null ? `${p.weight_pct.toFixed(1)}%` : '—'}</td>
              <td className={styles.num}>{p.value != null ? formatCurrency(p.value) : '—'}</td>
              <td className={styles.num}>{formatCurrency(p.cost_basis)}</td>
              <td className={styles.num} style={{ color: p.gain == null ? undefined : p.gain >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                {p.gain != null ? `${p.gain >= 0 ? '+' : '-'}${formatCurrency(Math.abs(p.gain))}` : '—'}
              </td>
              <td className={styles.num} style={{ color: p.gain_pct == null ? undefined : p.gain_pct >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
                {p.gain_pct != null ? `${p.gain_pct >= 0 ? '+' : ''}${p.gain_pct.toFixed(1)}%` : '—'}
              </td>
              <td className={styles.num}>{p.held_days != null ? formatHeld(p.held_days) : '—'}</td>
              <td
                className={styles.num}
                style={{ color: p.annualized_pct == null ? undefined : p.annualized_pct >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}
                title={p.annualized_pct == null && p.held_days != null && p.held_days < 90 ? 'Held under 90 days — too early to annualize' : undefined}
              >
                {p.annualized_pct != null ? `${p.annualized_pct >= 0 ? '+' : ''}${p.annualized_pct.toFixed(1)}%` : '—'}
              </td>
            </tr>
            {expandedBet === p.symbol && (
              <tr>
                <td colSpan={8} className={styles.betDrillCell}>
                  <BetTradeHistory symbol={p.symbol} trades={betTrades} />
                </td>
              </tr>
            )}
          </React.Fragment>
        )

        const closedRow = (p: PurePosition) => (
          <React.Fragment key={p.symbol}>
            <tr className={styles.betRow} onClick={() => toggleBetDrill(p.symbol)}>
              <td className={styles.betSym}>
                {p.symbol}
                <ChevronRight size={12} className={clsx(styles.betChevron, expandedBet === p.symbol && styles.betChevronOpen)} />
              </td>
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
            {expandedBet === p.symbol && (
              <tr>
                <td colSpan={6} className={styles.betDrillCell}>
                  <BetTradeHistory symbol={p.symbol} trades={betTrades} />
                </td>
              </tr>
            )}
          </React.Fragment>
        )

        const foldRow = (count: number, net: number, open: boolean, toggle: () => void, extraCols = 0) => (
          <tr className={styles.betRow} onClick={toggle}>
            <td colSpan={4} className={styles.smallFoldLabel}>
              <ChevronRight size={12} className={clsx(styles.betChevron, open && styles.betChevronOpen)} />
              {count} small position{count === 1 ? '' : 's'} (&lt;$5K)
            </td>
            <td className={styles.num} style={{ color: net >= 0 ? 'var(--color-positive, #00D632)' : 'var(--color-negative, #FF5A5A)' }}>
              {net >= 0 ? '+' : '-'}{formatCurrency(Math.abs(net))}
            </td>
            <td className={styles.num}>—</td>
            {Array.from({ length: extraCols }, (_, i) => <td key={i} className={styles.num}>—</td>)}
          </tr>
        )

        return (
        <section className={styles.betsSection}>
          <h2>Winners &amp; Losers</h2>
          <div className={styles.betsTableWrap}>
            <table className={styles.betsTable}>
              <thead>
                <tr>
                  {([
                    ['Symbol', 'symbol', false],
                    ['Weight', 'weight', true],
                    ['Value', 'value', true],
                    ['Cost Basis', 'cost_basis', true],
                    ['Gain', 'gain', true],
                    ['Return', 'gain_pct', true],
                    ['Held', 'held', true],
                    ['Ann. Return', 'annualized', true],
                  ] as [string, string, boolean][]).map(([label, key, numeric]) => (
                    <SortTh key={key} label={label} sortKey={key} numeric={numeric}
                      active={openSortKey} dir={openSortDir} onSort={sortOpenBy} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {mainOpen.map(openRow)}
                {smallOpen.length > 0 && foldRow(smallOpen.length, smallOpenNet, showSmallOpen, () => setShowSmallOpen(v => !v), 2)}
                {showSmallOpen && smallOpen.map(openRow)}
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
                        {([
                          ['Symbol', 'symbol', false],
                          ['Closed', 'closed_date', false],
                          ['Proceeds', 'proceeds', true],
                          ['Cost Basis', 'cost_basis', true],
                          ['Gain', 'gain', true],
                          ['Return', 'gain_pct', true],
                        ] as [string, string, boolean][]).map(([label, key, numeric]) => (
                          <SortTh key={key} label={label} sortKey={key} numeric={numeric}
                            active={closedSortKey} dir={closedSortDir} onSort={sortClosedBy} />
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {mainClosed.map(closedRow)}
                      {smallClosed.length > 0 && foldRow(smallClosed.length, smallClosedNet, showSmallClosed, () => setShowSmallClosed(v => !v))}
                      {showSmallClosed && smallClosed.map(closedRow)}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
        )
      })()}

      <section className={styles.accountsSection}>
        {/* Cash-inclusive total lives here because it IS the sum of these
            cards — not a competing page headline (that's pure performance). */}
        <div className={styles.accountsHeader}>
          <h2>Brokerage Accounts ({accounts.length})</h2>
          <div className={styles.trueStripBody}>
            {(() => {
              const trueCash = cashBreakdown?.total_true_cash ?? 0
              const truePortfolio = totalEquity + trueCash
              const dayPct = totalEquity > 0 ? (totalChange / (totalEquity - totalChange)) * 100 : null
              return (
                <>
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
        </div>
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


      {/* Archive — Strategy Deviations. Demoted from above Winners &
          Losers 2026-08-08 (Neel: "this is not helping me in any way").
          Kept, not deleted: the core-exit ledger and idle-inventory facts
          still inform the delta rules on Options Execution, they just are
          not a weekly read anymore. Collapsed by default. */}
      {deviations && (
        <div className={styles.closedBetsToggle}>
          <button onClick={() => setShowArchive(v => !v)}>
            {showArchive ? 'hide' : 'show'} archive — Strategy Deviations
          </button>
          {showArchive && (<>
      {/* Strategy Deviations — two-book model (spec: "Strategy model &
          policy deviations"). Core exits must be recovered; inventory must
          have exit calls. Facts + gap math only; option actions stay on
          the Options Execution page. */}
      {deviations && (() => {
        const openExits = deviations.core_exits.filter(e => e.status !== 'recovered')
        const recoveredExits = deviations.core_exits.filter(e => e.status === 'recovered')
        const statusChip = (s: CoreExit['status']) => (
          <span className={clsx(styles.devChip,
            s === 'idle' ? styles.devChipIdle : s === 'recovering' ? styles.devChipRecovering : styles.devChipOk)}>
            {s === 'idle' ? 'idle — no re-entry' : s}
          </span>
        )
        const exitRow = (e: CoreExit) => (
          <tr key={`${e.account_id}-${e.symbol}-${e.exit_date}`} className={styles.betRow}>
            <td className={styles.betSym}>{e.symbol}</td>
            <td>{e.account_name}</td>
            <td>{new Date(e.exit_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · {formatHeld(e.days_since_exit)} ago</td>
            <td className={styles.num}>{e.shares_unrecovered.toLocaleString()} of {e.shares_sold.toLocaleString()}</td>
            <td className={styles.num}>{formatCurrency(e.sale_px)}</td>
            <td className={styles.num}>{e.price_now != null ? formatCurrency(e.price_now) : '—'}</td>
            <td className={styles.num}>{e.open_put_contracts > 0 ? `${e.open_put_contracts} open` : '—'}</td>
            <td className={styles.num}>{formatCurrency(e.put_premium_since)}</td>
            <td className={styles.num} style={{ color: e.gap == null ? undefined : e.gap > 0 ? 'var(--color-negative, #FF5A5A)' : 'var(--color-positive, #00D632)' }}>
              {e.gap != null ? `${e.gap > 0 ? '−' : '+'}${formatCurrency(Math.abs(e.gap))}` : '—'}
            </td>
            <td>{statusChip(e.status)}</td>
          </tr>
        )
        return (
          <section className={styles.betsSection}>
            <h2>Strategy Deviations</h2>
            {openExits.length === 0 && deviations.idle_inventory.length === 0 && (
              <p className={styles.devAllClear}>No open deviations — every core exit is recovered or recovering, and all inventory has exit calls written.</p>
            )}
            {openExits.length > 0 && (
              <>
                <h3 className={styles.devSubhead}>Core exits awaiting re-entry ({openExits.length})</h3>
                <div className={styles.betsTableWrap}>
                  <table className={styles.betsTable}>
                    <thead>
                      <tr>
                        <th>Symbol</th><th>Account</th><th>Exited</th>
                        <th className={styles.num}>Unrecovered</th>
                        <th className={styles.num}>Sold @</th><th className={styles.num}>Now</th>
                        <th className={styles.num}>Puts</th>
                        <th className={styles.num}>Put prem. since</th>
                        <th className={styles.num}>Gap</th><th>Status</th>
                      </tr>
                    </thead>
                    <tbody>{openExits.map(exitRow)}</tbody>
                  </table>
                </div>
                <p className={styles.devAggregate}>
                  Cost of waiting across open exits: <strong style={{ color: 'var(--color-negative, #FF5A5A)' }}>−{formatCurrency(deviations.distraction.open_exit_gap)}</strong>
                  {deviations.distraction.since && (
                    <> · inventory-book put income since {new Date(deviations.distraction.since + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}: <strong>{formatCurrency(deviations.distraction.inventory_put_income_since)}</strong></>
                  )} — the honest version of the "puts pay 4–6x more" comparison.
                </p>
              </>
            )}
            {deviations.idle_inventory.length > 0 && (
              <>
                <h3 className={styles.devSubhead}>Idle inventory — no exit call written ({deviations.idle_inventory.length})</h3>
                <div className={styles.betsTableWrap}>
                  <table className={styles.betsTable}>
                    <thead>
                      <tr>
                        <th>Symbol</th><th>Account</th>
                        <th className={styles.num}>Shares</th>
                        <th className={styles.num}>Calls open</th>
                        <th className={styles.num}>Uncovered</th>
                        <th className={styles.num}>Idle value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deviations.idle_inventory.map(i => (
                        <tr key={`${i.account_id}-${i.symbol}`} className={styles.betRow}>
                          <td className={styles.betSym}>{i.symbol}</td>
                          <td>{i.account_name}</td>
                          <td className={styles.num}>{i.shares.toLocaleString()}</td>
                          <td className={styles.num}>{i.open_call_contracts}</td>
                          <td className={styles.num}>{i.uncovered_contracts} contract{i.uncovered_contracts === 1 ? '' : 's'}</td>
                          <td className={styles.num}>{i.idle_value != null ? formatCurrency(i.idle_value) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {deviations.policy.unclassified.length > 0 && (
              <p className={styles.devUnclassified}>
                Unclassified holdings (edit <code>data/investment_policy.json</code>): {deviations.policy.unclassified.join(', ')}
              </p>
            )}
            {recoveredExits.length > 0 && (
              <div className={styles.closedBetsToggle}>
                <button onClick={() => setShowRecoveredExits(v => !v)}>
                  {showRecoveredExits ? 'hide' : 'show'} recovered exits ({recoveredExits.length})
                </button>
                {showRecoveredExits && (
                  <div className={styles.betsTableWrap}>
                    <table className={styles.betsTable}>
                      <tbody>{recoveredExits.map(exitRow)}</tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </section>
        )
      })()}
          </>)}
        </div>
      )}

    </div>
  )
}
