import { useState, useEffect } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Plus,
  Edit,
  RefreshCw,
  DollarSign,
  Building2,
  FileText,
  AlertCircle,
  Globe,
  Search,
  Clock,
  Settings,
} from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './IndiaInvestments.module.css'

const API_BASE = '/api/v1/india-investments'

interface BankAccount {
  id: number
  account_name: string
  bank_name: string
  account_number?: string
  owner: string
  cash_balance: number
}

interface InvestmentAccount {
  id: number
  account_name: string
  platform: string
  account_number?: string
  owner: string
  linked_bank_account_id?: number
}

interface Stock {
  id: number
  investment_account_id: number
  symbol: string
  company_name?: string
  quantity: number
  average_price: number
  current_price: number
  cost_basis: number
  current_value: number
  profit_loss: number
}

interface MutualFund {
  id: number
  investment_account_id: number
  fund_name: string
  fund_code?: string
  category: string
  units: number
  nav: number
  purchase_price: number
  cost_basis: number
  current_value: number
  profit_loss: number
}

interface FixedDeposit {
  id: number
  bank_account_id: number
  fd_number?: string
  description?: string
  principal: number
  interest_rate: number
  start_date: string
  maturity_date: string
  current_value: number
  accrued_interest: number
  maturity_value: number
  days_to_maturity: number
}

interface ExchangeRate {
  from_currency: string
  to_currency: string
  rate: number
  updated_at?: string
}

interface FatherMutualFundHolding {
  id: number
  investment_date: string
  fund_name: string
  folio_number?: string
  scheme_code?: string
  isin?: string
  initial_invested_amount: number
  amount_march_2025?: number
  current_amount?: number
  // Returns
  return_1y?: number
  return_3y?: number
  return_5y?: number
  return_10y?: number
  // Risk metrics
  volatility?: number
  sharpe_ratio?: number
  alpha?: number
  beta?: number
  // Fund details (from Kuvera)
  aum?: number
  expense_ratio?: number
  fund_rating?: number
  fund_start_date?: string
  crisil_rating?: string
  fund_category?: string
  notes?: string
  last_updated?: string
}

interface FatherMutualFundSummary {
  total_invested: number
  total_march_2025: number
  total_current: number
  total_gain_loss?: number
  count: number
}

interface FatherStockHolding {
  id: number
  investment_date: string
  symbol: string
  company_name?: string
  quantity: number
  average_price?: number
  initial_invested_amount: number
  amount_march_2025?: number
  current_price?: number
  current_amount?: number
  sector?: string
  notes?: string
  last_updated?: string
}

interface FatherStockSummary {
  total_invested: number
  total_march_2025: number
  total_current: number
  total_gain_loss?: number
  count: number
}

interface Summary {
  bank_accounts: BankAccount[]
  investment_accounts: InvestmentAccount[]
  stocks: Stock[]
  mutual_funds: MutualFund[]
  fixed_deposits: FixedDeposit[]
  total_value_inr: number
  total_value_usd: number
  exchange_rate: number
}

function formatCurrencyINR(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)
}

// Abbreviated format: 1.3L, 85Cr, etc.
function formatAUMShort(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '-'
  if (amount >= 10000) {
    // Show in Cr with 1 decimal if >= 10,000 Cr
    return `${(amount / 1).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`
  } else if (amount >= 100) {
    // Show in Cr for 100-10,000
    return `${amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`
  } else {
    return `${amount.toFixed(0)} Cr`
  }
}

// Format percentage as whole number
function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return `${Math.round(value)}%`
}

function formatCurrencyUSD(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

export function IndiaInvestments() {
  const [activeTab, setActiveTab] = useState<'mutual-funds' | 'stocks' | 'research'>('mutual-funds')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [exchangeRate, setExchangeRate] = useState<ExchangeRate | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddAccount, setShowAddAccount] = useState(false)
  const [selectedOwner, setSelectedOwner] = useState<'Neel' | 'Father'>('Father')
  const [showSettings, setShowSettings] = useState(false)

  useEffect(() => {
    fetchData()
    fetchExchangeRate()
  }, [selectedOwner])

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const ownerParam = selectedOwner !== 'all' ? `?owner=${selectedOwner}` : ''
      const response = await fetch(`${API_BASE}/summary${ownerParam}`, {
        headers: getAuthHeaders(),
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch data' }))
        throw new Error(errorData.detail || `HTTP ${response.status}: Failed to fetch data`)
      }
      const data = await response.json()
      setSummary(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const fetchExchangeRate = async () => {
    try {
      const response = await fetch(`${API_BASE}/exchange-rate`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        setExchangeRate(data)
      }
    } catch (err) {
      console.error('Failed to fetch exchange rate:', err)
    }
  }

  const updateExchangeRate = async (newRate: number) => {
    try {
      const response = await fetch(`${API_BASE}/exchange-rate`, {
        method: 'PUT',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ rate: newRate }),
      })
      if (response.ok) {
        await fetchExchangeRate()
        await fetchData() // Refresh to update USD values
      }
    } catch (err) {
      console.error('Failed to update exchange rate:', err)
    }
  }

  if (loading && !summary) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>{error}</span>
        </div>
      </div>
    )
  }

  if (!summary) return null

  // Filter data by selected owner
  const filteredSummary = {
    ...summary,
    bank_accounts: summary.bank_accounts.filter(acc => acc.owner === selectedOwner),
    investment_accounts: summary.investment_accounts.filter(acc => acc.owner === selectedOwner),
    stocks: summary.stocks.filter(stock => {
      const account = summary.investment_accounts.find(acc => acc.id === stock.investment_account_id)
      return account?.owner === selectedOwner
    }),
    mutual_funds: summary.mutual_funds.filter(mf => {
      const account = summary.investment_accounts.find(acc => acc.id === mf.investment_account_id)
      return account?.owner === selectedOwner
    }),
    fixed_deposits: summary.fixed_deposits.filter(fd => {
      const account = summary.bank_accounts.find(acc => acc.id === fd.bank_account_id)
      return account?.owner === selectedOwner
    }),
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Globe size={24} />
          </div>
          <div>
            <h1 className={styles.title}>India Investments</h1>
            <p className={styles.subtitle}>Track your Indian stocks, mutual funds, and fixed deposits</p>
          </div>
        </div>
        <div className={styles.headerActions}>
          <div className={styles.settingsContainer}>
            <button 
              onClick={() => setShowSettings(!showSettings)} 
              className={styles.settingsButton}
              title="Settings"
            >
              <Settings size={18} />
            </button>
            {showSettings && exchangeRate && (
              <div className={styles.settingsDropdown}>
                <div className={styles.settingsHeader}>Settings</div>
                <div className={styles.settingsItem}>
                  <span className={styles.settingsLabel}>Exchange Rate (1 USD = INR)</span>
                  <input
                    type="number"
                    step="0.01"
                    value={exchangeRate.rate}
                    onChange={(e) => {
                      const newRate = parseFloat(e.target.value)
                      if (!isNaN(newRate) && newRate > 0) {
                        setExchangeRate({ ...exchangeRate, rate: newRate })
                      }
                    }}
                    onBlur={(e) => {
                      const newRate = parseFloat(e.target.value)
                      if (!isNaN(newRate) && newRate > 0) {
                        updateExchangeRate(newRate)
                      }
                    }}
                    className={styles.settingsInput}
                  />
                </div>
                {exchangeRate.updated_at && (
                  <div className={styles.settingsFooter}>
                    Last updated: {new Date(exchangeRate.updated_at).toLocaleDateString()}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Owner Filter */}
      <div className={styles.ownerFilter}>
        <button
          className={selectedOwner === 'Father' ? styles.active : ''}
          onClick={() => setSelectedOwner('Father')}
        >
          Father's Accounts
        </button>
        <button
          className={selectedOwner === 'Neel' ? styles.active : ''}
          onClick={() => setSelectedOwner('Neel')}
        >
          Neel's Accounts
        </button>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={activeTab === 'mutual-funds' ? styles.active : ''}
          onClick={() => setActiveTab('mutual-funds')}
        >
          Mutual Funds
        </button>
        <button
          className={activeTab === 'stocks' ? styles.active : ''}
          onClick={() => setActiveTab('stocks')}
        >
          Stocks
        </button>
        <button
          className={activeTab === 'research' ? styles.active : ''}
          onClick={() => setActiveTab('research')}
        >
          Research
        </button>
      </div>

      {/* Tab Content */}
      <div className={styles.tabContent}>
        {activeTab === 'mutual-funds' && (
          <MutualFundHoldingsSection owner={selectedOwner} />
        )}
        {activeTab === 'stocks' && (
          selectedOwner === 'Father' ? (
            <StockHoldingsSection owner="Father" />
          ) : (
          <StocksSection
            stocks={filteredSummary.stocks}
            investmentAccounts={filteredSummary.investment_accounts}
          />
          )
        )}
        {activeTab === 'research' && (
          <MutualFundResearchSection />
        )}
      </div>
    </div>
  )
}

// Stocks Section Component
function StocksSection({ stocks, investmentAccounts }: { stocks: Stock[], investmentAccounts: InvestmentAccount[] }) {
  const getAccountName = (accountId: number) => {
    const account = investmentAccounts.find(acc => acc.id === accountId)
    return account?.account_name || 'Unknown Account'
  }

  if (stocks.length === 0) {
    return (
      <div className={styles.emptyState}>
        <TrendingUp size={48} />
        <p>No stocks added yet</p>
        <button className={styles.addButton}>
          <Plus size={18} />
          Add Stock
        </button>
      </div>
    )
  }

  return (
    <div className={styles.section}>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Account</th>
              <th>Symbol</th>
              <th>Company</th>
              <th>Quantity</th>
              <th>Avg Price</th>
              <th>Current Price</th>
              <th>Cost Basis</th>
              <th>Current Value</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock) => (
              <tr key={stock.id}>
                <td>{getAccountName(stock.investment_account_id)}</td>
                <td className={styles.symbol}>{stock.symbol}</td>
                <td>{stock.company_name || '-'}</td>
                <td>{stock.quantity.toFixed(2)}</td>
                <td>{formatCurrencyINR(stock.average_price)}</td>
                <td>{formatCurrencyINR(stock.current_price)}</td>
                <td>{formatCurrencyINR(stock.cost_basis)}</td>
                <td>{formatCurrencyINR(stock.current_value)}</td>
                <td className={stock.profit_loss >= 0 ? styles.profit : styles.loss}>
                  {stock.profit_loss >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  {formatCurrencyINR(Math.abs(stock.profit_loss))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Mutual Funds Section Component
function MutualFundsSection({ mutualFunds, investmentAccounts }: { mutualFunds: MutualFund[], investmentAccounts: InvestmentAccount[] }) {
  const getAccountName = (accountId: number) => {
    const account = investmentAccounts.find(acc => acc.id === accountId)
    return account?.account_name || 'Unknown Account'
  }

  const indiaFunds = mutualFunds.filter(mf => mf.category === 'india_fund')
  const internationalFunds = mutualFunds.filter(mf => mf.category === 'international_fund')

  if (mutualFunds.length === 0) {
    return (
      <div className={styles.emptyState}>
        <FileText size={48} />
        <p>No mutual funds added yet</p>
        <button className={styles.addButton}>
          <Plus size={18} />
          Add Mutual Fund
        </button>
      </div>
    )
  }

  return (
    <div className={styles.section}>
      {internationalFunds.length > 0 && (
        <div className={styles.categorySection}>
          <h3>International Funds</h3>
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Fund Name</th>
                  <th>Fund Code</th>
                  <th>Units</th>
                  <th>NAV</th>
                  <th>Purchase Price</th>
                  <th>Cost Basis</th>
                  <th>Current Value</th>
                  <th>P&L</th>
                </tr>
              </thead>
              <tbody>
                {internationalFunds.map((mf) => (
                  <tr key={mf.id}>
                    <td>{getAccountName(mf.investment_account_id)}</td>
                    <td>{mf.fund_name}</td>
                    <td>{mf.fund_code || '-'}</td>
                    <td>{mf.units.toFixed(4)}</td>
                    <td>{formatCurrencyINR(mf.nav)}</td>
                    <td>{formatCurrencyINR(mf.purchase_price)}</td>
                    <td>{formatCurrencyINR(mf.cost_basis)}</td>
                    <td>{formatCurrencyINR(mf.current_value)}</td>
                    <td className={mf.profit_loss >= 0 ? styles.profit : styles.loss}>
                      {mf.profit_loss >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {formatCurrencyINR(Math.abs(mf.profit_loss))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {indiaFunds.length > 0 && (
        <div className={styles.categorySection}>
          <h3>India Funds</h3>
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Fund Name</th>
                  <th>Fund Code</th>
                  <th>Units</th>
                  <th>NAV</th>
                  <th>Purchase Price</th>
                  <th>Cost Basis</th>
                  <th>Current Value</th>
                  <th>P&L</th>
                </tr>
              </thead>
              <tbody>
                {indiaFunds.map((mf) => (
                  <tr key={mf.id}>
                    <td>{getAccountName(mf.investment_account_id)}</td>
                    <td>{mf.fund_name}</td>
                    <td>{mf.fund_code || '-'}</td>
                    <td>{mf.units.toFixed(4)}</td>
                    <td>{formatCurrencyINR(mf.nav)}</td>
                    <td>{formatCurrencyINR(mf.purchase_price)}</td>
                    <td>{formatCurrencyINR(mf.cost_basis)}</td>
                    <td>{formatCurrencyINR(mf.current_value)}</td>
                    <td className={mf.profit_loss >= 0 ? styles.profit : styles.loss}>
                      {mf.profit_loss >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {formatCurrencyINR(Math.abs(mf.profit_loss))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// Bonds & Fixed Deposits Section Component
function BondsFDsSection({ fixedDeposits, bankAccounts }: { fixedDeposits: FixedDeposit[], bankAccounts: BankAccount[] }) {
  const getAccountName = (accountId: number) => {
    const account = bankAccounts.find(acc => acc.id === accountId)
    return account?.account_name || 'Unknown Account'
  }

  if (fixedDeposits.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Building2 size={48} />
        <p>No fixed deposits added yet</p>
        <button className={styles.addButton}>
          <Plus size={18} />
          Add Fixed Deposit
        </button>
      </div>
    )
  }

  return (
    <div className={styles.section}>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Account</th>
              <th>FD Number</th>
              <th>Description</th>
              <th>Principal</th>
              <th>Interest Rate</th>
              <th>Start Date</th>
              <th>Maturity Date</th>
              <th>Current Value</th>
              <th>Accrued Interest</th>
              <th>Maturity Value</th>
              <th>Days to Maturity</th>
            </tr>
          </thead>
          <tbody>
            {fixedDeposits.map((fd) => (
              <tr key={fd.id}>
                <td>{getAccountName(fd.bank_account_id)}</td>
                <td>{fd.fd_number || '-'}</td>
                <td>{fd.description || '-'}</td>
                <td>{formatCurrencyINR(fd.principal)}</td>
                <td>{fd.interest_rate.toFixed(2)}%</td>
                <td>{new Date(fd.start_date).toLocaleDateString()}</td>
                <td>{new Date(fd.maturity_date).toLocaleDateString()}</td>
                <td>{formatCurrencyINR(fd.current_value)}</td>
                <td>{formatCurrencyINR(fd.accrued_interest)}</td>
                <td>{formatCurrencyINR(fd.maturity_value)}</td>
                <td>{fd.days_to_maturity} days</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Helper function to get tax classification from category
function getTaxClassification(category: string | null): string {
  if (!category) return '-'
  
  const categoryLower = category.toLowerCase()
  if (categoryLower.includes('equity') || categoryLower.includes('elss')) {
    return 'Equity'
  } else if (categoryLower.includes('debt') || categoryLower.includes('bond')) {
    return 'Debt'
  } else if (categoryLower.includes('hybrid') || categoryLower.includes('balanced')) {
    return 'Hybrid'
  } else if (categoryLower.includes('international') || categoryLower.includes('global')) {
    return 'Equity' // International funds are typically equity-oriented
  }
  return 'Other'
}

// Helper function to create a compact fund name
function getCompactFundName(fullName: string): string {
  if (!fullName) return ''
  
  // Extract fund house (usually first part before "Mutual Fund" or similar)
  let parts = fullName.split(' - ')
  let fundHouse = parts[0] || ''
  
  // Remove "Mutual Fund" suffix if present
  fundHouse = fundHouse.replace(/\s+Mutual Fund$/, '').trim()
  
  // Extract category keywords (Flexi Cap, Large Cap, etc.)
  let category = ''
  const categoryKeywords = [
    'Flexi Cap', 'Large Cap', 'Mid Cap', 'Small Cap', 'Multi Cap', 
    'ELSS', 'Index', 'Global', 'International', 'Overseas', 'Equity',
    'Clean Energy', 'Innovation', 'S&P 500'
  ]
  for (const keyword of categoryKeywords) {
    if (fullName.includes(keyword)) {
      category = keyword
      break
    }
  }
  
  // Extract plan type
  let planType = ''
  if (fullName.includes('Direct')) planType = 'D'
  else if (fullName.includes('Regular')) planType = 'R'
  
  // Build compact name: FundHouse Category (PlanType)
  let compact = fundHouse
  if (category) {
    compact += ` ${category}`
  }
  if (planType) {
    compact += ` (${planType})`
  }
  
  // Limit to 35 characters for better table fit
  if (compact.length > 35) {
    // Try to shorten fund house name if too long
    if (fundHouse.length > 20) {
      const shortHouse = fundHouse.substring(0, 15) + '...'
      compact = shortHouse + (category ? ` ${category}` : '') + (planType ? ` (${planType})` : '')
    }
    if (compact.length > 35) {
      compact = compact.substring(0, 32) + '...'
    }
  }
  
  return compact || fullName.substring(0, 35)
}

// Fund name mapping to proper names and categories
const FUND_NAME_MAPPING: { [key: string]: { properName: string; category: string } } = {
  'SBI Global': { properName: 'SBI Magnum Global Fund (MNC Fund)', category: 'Equity - MNC/Thematic' },
  'PPF': { properName: 'Public Provident Fund', category: 'Government Scheme' },
  'ICICI Asset Allocator': { properName: 'ICICI Prudential Asset Allocator Fund', category: 'Hybrid - Asset Allocation' },
  'ICICI Banking Plus SIP': { properName: 'ICICI Prudential Banking & Financial Services Fund', category: 'Equity - Sectoral (Banking)' },
  'Franklin Prima Plus SIP': { properName: 'Franklin India Prima Fund (Mid Cap Fund)', category: 'Equity - Mid Cap' },
  'ABSL Banking Plus SIP': { properName: 'Aditya Birla SL Banking & Financial Services Fund', category: 'Equity - Sectoral (Banking)' },
  'ICICI Blue Chip Plus SIP': { properName: 'ICICI Prudential Bluechip Fund (Large Cap Fund)', category: 'Equity - Large Cap' },
  'ICICI Balance Limited': { properName: 'ICICI Prudential Balanced Advantage Fund', category: 'Hybrid - Balanced Advantage' },
  'ABSL Frontline SIP': { properName: 'Aditya Birla Sun Life Frontline Equity Fund', category: 'Equity - Large Cap' },
  'Edelweiss Small Cap': { properName: 'Edelweiss Small Cap Fund', category: 'Equity - Small Cap' },
  'Franklin Focused Equity Fund': { properName: 'Franklin India Focused Equity Fund', category: 'Equity - Focused' },
  'DSP Aggressive Hybrid Fund': { properName: 'DSP Aggressive Hybrid Fund', category: 'Hybrid - Aggressive' },
  'Reliance': { properName: 'Reliance [Stock or Mutual Fund?]', category: 'Unknown - Need Clarification' },
  'ABSL Business Cycle Fund': { properName: 'Aditya Birla SL Business Cycle Fund', category: 'Equity - Thematic' },
  'Mirae Asset Mutual Fund': { properName: 'Mirae Asset [Which Fund?]', category: 'Unknown - Need Clarification' },
  'Edelweiss Aggressive Hybrid Fund': { properName: 'Edelweiss Aggressive Hybrid Fund', category: 'Hybrid - Aggressive' },
  'DSP Flexi Cap Quality 30 Index Fund': { properName: 'DSP Flexi Cap Fund', category: 'Equity - Flexi Cap' },
  'Edelweiss Balance Advantage': { properName: 'Edelweiss Balanced Advantage Fund', category: 'Hybrid - Balanced Advantage' },
  'Invesco Indian Business Cycle Fund': { properName: 'Invesco India Business Cycle Fund', category: 'Equity - Thematic' },
}

// Mutual Fund Holdings Section Component (supports both Father and Neel)
type MFHoldingSortColumn = 'nrank' | 'investment_date' | 'fund_name' | 'folio_number' | 'initial_invested_amount' | 'amount_march_2025' | 'current_amount' | 'return_1y' | 'return_3y' | 'return_5y' | null

function MutualFundHoldingsSection({ owner }: { owner: 'Father' | 'Neel' }) {
  const [holdings, setHoldings] = useState<FatherMutualFundHolding[]>([])
  const [summary, setSummary] = useState<FatherMutualFundSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingHolding, setEditingHolding] = useState<FatherMutualFundHolding | null>(null)
  const [sortColumn, setSortColumn] = useState<MFHoldingSortColumn>('investment_date')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')
  const [selectedFundForDetails, setSelectedFundForDetails] = useState<FatherMutualFundHolding | null>(null)
  const [refreshingReturns, setRefreshingReturns] = useState(false)
  const [enrichingData, setEnrichingData] = useState(false)
  const [showDetailsModal, setShowDetailsModal] = useState(false)

  // Calculate N-Rank v3 score for a holding (same algorithm as Research section)
  // v3: Aggressive wealth transfer - 50% returns weight, sector bonuses
  const calculateHoldingNRank = (holding: FatherMutualFundHolding): number => {
    let score = 0
    const name = holding.fund_name?.toLowerCase() || ''
    const category = holding.fund_category?.toLowerCase() || ''
    
    // Detect sector/category for strategic fit
    const isTech = category.includes('tech') || name.includes('tech') || name.includes('fang') || name.includes('nasdaq')
    const isUSEquity = category.includes('us') || name.includes('us equity') || name.includes('bluechip')
    const isInternational = category.includes('international') || category.includes('global') || category.includes('europe') || category.includes('fof')
    const isHealthcare = category.includes('health') || category.includes('pharma')
    const isConsumption = category.includes('consumption') || category.includes('fmcg')
    const isBanking = category.includes('banking') || category.includes('financial') || name.includes('banking') || name.includes('financial')
    const isInfra = category.includes('infra')
    const isDirect = name.includes('direct')
    
    // DIMENSION 1: QUALITY (20 points)
    // Fund Rating (10 points)
    if (holding.fund_rating) {
      const ratingMap: { [key: number]: number } = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 }
      score += ratingMap[holding.fund_rating] || 0
    }
    // AUM (7 points)
    if (holding.aum) {
      if (holding.aum < 500) score += 0
      else if (holding.aum < 2000) score += 2
      else if (holding.aum < 10000) score += 5
      else if (holding.aum < 50000) score += 7
      else score += 5
    }
    // Fund Age (3 points)
    if (holding.return_10y) score += 3
    else if (holding.return_5y) score += 2
    else if (holding.return_3y) score += 1
    
    // DIMENSION 2: RETURNS (50 points max - PRIMARY for aggressive v3)
    // 1Y Return (15 to -10 points)
    if (holding.return_1y != null) {
      if (holding.return_1y > 30) score += 15
      else if (holding.return_1y > 20) score += 12
      else if (holding.return_1y > 15) score += 9
      else if (holding.return_1y > 10) score += 6
      else if (holding.return_1y > 5) score += 3
      else if (holding.return_1y > 0) score += 0
      else if (holding.return_1y > -5) score -= 5
      else score -= 10
    }
    // 3Y Return (20 to -5 points) - Most important
    if (holding.return_3y != null) {
      if (holding.return_3y > 30) score += 20
      else if (holding.return_3y > 25) score += 16
      else if (holding.return_3y > 20) score += 12
      else if (holding.return_3y > 15) score += 8
      else if (holding.return_3y > 10) score += 4
      else if (holding.return_3y > 5) score += 0
      else score -= 5
    }
    // 5Y Return (15 to -5 points)
    if (holding.return_5y != null) {
      if (holding.return_5y > 25) score += 15
      else if (holding.return_5y > 20) score += 12
      else if (holding.return_5y > 15) score += 8
      else if (holding.return_5y > 10) score += 4
      else if (holding.return_5y > 5) score += 0
      else score -= 5
    }
    // Momentum penalty (0 to -5 points)
    if (holding.return_1y != null && holding.return_3y != null) {
      const momentumGap = holding.return_3y - holding.return_1y
      if (momentumGap > 20) score -= 5
      else if (momentumGap > 15) score -= 3
      else if (momentumGap > 10) score -= 2
    }
    
    // DIMENSION 3: RISK-ADJUSTED (15 points max - reduced in v3)
    // Sharpe Ratio (10 to -5 points)
    if (holding.sharpe_ratio != null) {
      if (holding.sharpe_ratio > 1.5) score += 10
      else if (holding.sharpe_ratio > 1.0) score += 8
      else if (holding.sharpe_ratio > 0.7) score += 6
      else if (holding.sharpe_ratio > 0.5) score += 4
      else if (holding.sharpe_ratio > 0.3) score += 2
      else if (holding.sharpe_ratio > 0) score += 0
      else if (holding.sharpe_ratio > -0.5) score -= 2
      else score -= 5
    }
    // Alpha (7 to -5 points)
    if (holding.alpha != null) {
      if (holding.alpha > 7) score += 7
      else if (holding.alpha > 5) score += 5
      else if (holding.alpha > 3) score += 4
      else if (holding.alpha > 1) score += 2
      else if (holding.alpha > 0) score += 1
      else if (holding.alpha > -3) score -= 2
      else score -= 5
    }
    // Volatility penalty - only extreme (0 to -2 points)
    if (holding.volatility != null && holding.volatility > 20) {
      if (holding.volatility > 25) score -= 2
      else score -= 1
    }
    
    // DIMENSION 4: COST (5 points max - reduced in v3)
    if (holding.expense_ratio != null) {
      if (holding.expense_ratio < 0.5) score += 5
      else if (holding.expense_ratio < 0.75) score += 4
      else if (holding.expense_ratio < 1.0) score += 3
      else if (holding.expense_ratio < 1.5) score += 2
      else if (holding.expense_ratio < 2.0) score += 0
      else score -= 3
    }
    
    // DIMENSION 5: STRATEGIC FIT (10 points)
    // Sector diversification bonus
    if (isTech) score += 5
    else if (isHealthcare) score += 4
    else if (isInternational || isUSEquity) score += 4
    else if (isConsumption) score += 3
    else if (isInfra) score += 2
    else if (isBanking) score += 0  // Already over-allocated
    
    // Direct plan bonus
    if (isDirect) score += 2
    
    // Clean history bonus
    if (holding.return_10y) score += 3
    else if (holding.return_5y) score += 2
    
    // Floor at 0, cap at 100
    return Math.max(0, Math.min(100, Math.round(score)))
  }

  // Get N-Rank tier for styling (v3 thresholds)
  const getNRankTier = (score: number): 'excellent' | 'good' | 'caution' | 'poor' | 'unknown' => {
    if (score === 0) return 'unknown'
    if (score >= 60) return 'excellent'
    if (score >= 45) return 'good'
    if (score >= 30) return 'caution'
    return 'poor'
  }

  useEffect(() => {
    fetchHoldings()
  }, [owner])

  const fetchHoldings = async () => {
    setLoading(true)
    setError(null)
    try {
      // For now, only Father has holdings - Neel's will show empty
      if (owner === 'Father') {
        const response = await fetch(`${API_BASE}/father-mutual-funds`, {
          headers: getAuthHeaders(),
        })
        if (!response.ok) {
          throw new Error('Failed to fetch holdings')
        }
        const data = await response.json()
        setHoldings(data.holdings || [])
        setSummary(data.summary || null)
      } else {
        // Neel's holdings - empty for now
        setHoldings([])
        setSummary(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const handleRefreshReturns = async () => {
    if (owner !== 'Father') return
    
    setRefreshingReturns(true)
    try {
      const response = await fetch(`${API_BASE}/father-mutual-funds/refresh-returns`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      
      if (!response.ok) {
        throw new Error('Failed to refresh returns')
      }
      
      const data = await response.json()
      console.log(`Refreshed returns: ${data.updated} updated, ${data.errors} errors`)
      
      // Refresh holdings to show updated returns
      await fetchHoldings()
    } catch (err) {
      console.error('Failed to refresh returns:', err)
      alert(err instanceof Error ? err.message : 'Failed to refresh returns')
    } finally {
      setRefreshingReturns(false)
    }
  }

  const handleEnrichHoldings = async () => {
    if (owner !== 'Father') return
    
    setEnrichingData(true)
    try {
      const response = await fetch(`${API_BASE}/father-mutual-funds/enrich-holdings`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      
      if (!response.ok) {
        throw new Error('Failed to enrich holdings')
      }
      
      const data = await response.json()
      console.log(`Enriched ${data.enriched} holdings, ${data.errors} errors`)
      
      if (data.errors > 0) {
        console.warn('Enrich errors:', data.details.errors)
      }
      
      // Refresh holdings to show enriched data
      await fetchHoldings()
    } catch (err) {
      console.error('Failed to enrich holdings:', err)
      alert(err instanceof Error ? err.message : 'Failed to enrich holdings')
    } finally {
      setEnrichingData(false)
    }
  }

  const handleSaveHolding = async (holdingData: Partial<FatherMutualFundHolding>) => {
    try {
      const url = editingHolding 
        ? `${API_BASE}/father-mutual-funds/${editingHolding.id}`
        : `${API_BASE}/father-mutual-funds`
      
      const response = await fetch(url, {
        method: editingHolding ? 'PUT' : 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(holdingData),
      })

      if (!response.ok) {
        throw new Error('Failed to save holding')
      }

      setShowAddModal(false)
      setEditingHolding(null)
      await fetchHoldings()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  const handleDeleteHolding = async (id: number) => {
    if (!confirm('Are you sure you want to delete this holding?')) return
    
    try {
      const response = await fetch(`${API_BASE}/father-mutual-funds/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })

      if (!response.ok) {
        throw new Error('Failed to delete holding')
      }

      await fetchHoldings()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  // Handle column sorting
  const handleSort = (column: MFHoldingSortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      // Default to descending for amounts/returns, ascending for text
      const descendingColumns: MFHoldingSortColumn[] = ['nrank', 'initial_invested_amount', 'amount_march_2025', 'current_amount', 'return_1y', 'return_3y', 'return_5y', 'investment_date']
      setSortDirection(descendingColumns.includes(column) ? 'desc' : 'asc')
    }
  }

  // Sort holdings
  const sortedHoldings = [...holdings].sort((a, b) => {
    if (!sortColumn) return 0
    
    let aVal: any
    let bVal: any
    
    // Handle N-Rank sorting (calculated field)
    if (sortColumn === 'nrank') {
      aVal = calculateHoldingNRank(a)
      bVal = calculateHoldingNRank(b)
    } else {
      aVal = a[sortColumn]
      bVal = b[sortColumn]
    }
    
    // Handle nulls - push to bottom
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    // Handle date comparison
    if (sortColumn === 'investment_date') {
      aVal = new Date(aVal).getTime()
      bVal = new Date(bVal).getTime()
    }
    
    // Handle string comparison
    if (sortColumn === 'fund_name' || sortColumn === 'folio_number') {
      aVal = String(aVal).toLowerCase()
      bVal = String(bVal).toLowerCase()
      if (sortDirection === 'asc') {
        return aVal.localeCompare(bVal)
      } else {
        return bVal.localeCompare(aVal)
      }
    }
    
    // Numeric comparison
    if (sortDirection === 'asc') {
      return aVal - bVal
    } else {
      return bVal - aVal
    }
  })

  // Helper function to calculate estimated current value for a holding
  const calculateEstimatedCurrent = (holding: FatherMutualFundHolding): number | null => {
    const now = new Date()
    const march2025 = new Date(2025, 2, 31) // March 31, 2025
    
    if (holding.amount_march_2025 && holding.return_1y !== null && holding.return_1y !== undefined) {
      // Has March 2025 data: use 1Y return prorated
      const monthsSinceMarch = (now.getTime() - march2025.getTime()) / (30.44 * 24 * 60 * 60 * 1000)
      const proratedReturn = (holding.return_1y / 100) * (monthsSinceMarch / 12)
      return holding.amount_march_2025 * (1 + proratedReturn)
    } else if (holding.investment_date && holding.initial_invested_amount) {
      // No March 2025 data: use appropriate return based on investment age
      const investDate = new Date(holding.investment_date)
      const yearsSinceInvest = (now.getTime() - investDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
      
      // Pick closest return: <2Y → 1Y, 2-4Y → 3Y, ≥4Y → 5Y
      let returnRate: number | null = null
      if (yearsSinceInvest < 2 && holding.return_1y != null) {
        returnRate = holding.return_1y
      } else if (yearsSinceInvest < 4 && holding.return_3y != null) {
        returnRate = holding.return_3y
      } else if (holding.return_5y != null) {
        returnRate = holding.return_5y
      } else if (holding.return_3y != null) {
        returnRate = holding.return_3y
      } else if (holding.return_1y != null) {
        returnRate = holding.return_1y
      }
      
      if (returnRate !== null) {
        // Compound growth: Initial × (1 + return)^years
        return holding.initial_invested_amount * Math.pow(1 + returnRate / 100, yearsSinceInvest)
      }
    }
    
    return holding.current_amount || null
  }

  // Calculate total estimated current value
  const totalEstimatedCurrent = holdings.reduce((sum, h) => {
    const est = calculateEstimatedCurrent(h)
    return sum + (est || 0)
  }, 0)

  // Sort indicator component
  const SortIndicator = ({ column }: { column: MFHoldingSortColumn }) => {
    if (sortColumn !== column) {
      return <span className={styles.sortIndicator}>↕</span>
    }
    return (
      <span className={styles.sortIndicatorActive}>
        {sortDirection === 'asc' ? '↑' : '↓'}
      </span>
    )
  }

  if (loading) {
    return (
      <div className={styles.emptyState}>
        <RefreshCw size={48} className={styles.spinner} />
        <p>Loading mutual fund holdings...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.emptyState}>
        <AlertCircle size={48} />
        <p>Error: {error}</p>
        <button onClick={fetchHoldings} className={styles.searchButton}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className={styles.section}>
      {/* Header with Action Buttons */}
      <div className={styles.researchHeader}>
        <div className={styles.searchBox}>
          {owner === 'Father' && (
            <>
              <button 
                onClick={handleEnrichHoldings} 
                className={styles.searchButton}
                disabled={enrichingData}
                title="Fetch latest returns, AUM, Expense Ratio, Ratings from Kuvera"
              >
                <RefreshCw size={18} className={enrichingData ? styles.spinner : ''} />
                {enrichingData ? 'Refreshing...' : 'Refresh Data'}
              </button>
              <button onClick={() => { setEditingHolding(null); setShowAddModal(true); }} className={styles.searchButton}>
                <Plus size={18} />
                Add Holding
              </button>
            </>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className={styles.summaryCards} style={{ marginBottom: 'var(--space-6)' }}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Holdings</div>
            <div className={styles.summaryCardValue}>{summary.count}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Total Invested</div>
            <div className={styles.summaryCardValue}>{formatCurrencyINR(summary.total_invested)}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Value (Mar 31, 2025)</div>
            <div className={styles.summaryCardValue}>{formatCurrencyINR(summary.total_march_2025)}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Est. Current Value</div>
            <div className={`${styles.summaryCardValue} ${styles.internetDataCell}`}>
              {totalEstimatedCurrent > 0 ? formatCurrencyINR(totalEstimatedCurrent) : '-'}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Total Gain/Loss</div>
            <div className={`${styles.summaryCardValue} ${totalEstimatedCurrent - summary.total_invested >= 0 ? styles.profit : styles.loss}`}>
              {totalEstimatedCurrent > 0 ? formatCurrencyINR(totalEstimatedCurrent - summary.total_invested) : '-'}
            </div>
          </div>
        </div>
      )}

      {/* Holdings Table */}
      {holdings.length === 0 ? (
        <div className={styles.emptyState}>
          <FileText size={48} />
          <p>No mutual fund holdings added yet</p>
          <p className={styles.emptyStateSubtext}>Add mutual fund holdings to track performance</p>
          {owner === 'Father' && (
            <button onClick={() => setShowAddModal(true)} className={styles.addButton}>
              <Plus size={18} />
              Add First Holding
            </button>
          )}
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                {/* N-Rank Column - Sortable */}
                <th 
                  className={`${styles.sortableHeader} ${styles.tooltipHeader}`} 
                  style={{ width: '70px', textAlign: 'center' }}
                  onClick={() => handleSort('nrank')}
                >
                  <span className={styles.headerContent}>N-Rank <SortIndicator column="nrank" /></span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Neel Rank - Score (0-100) combining Quality, Risk, Returns, Cost.</div>
                    <div className={styles.tooltipLine2}>Click the score to see detailed breakdown. Click "Refresh Data" to fetch missing metrics.</div>
                  </div>
                </th>
                {/* Actual Data Columns */}
                <th className={styles.sortableHeader} onClick={() => handleSort('investment_date')}>
                  <span className={styles.headerContent}>Date <SortIndicator column="investment_date" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('fund_name')}>
                  <span className={styles.headerContent}>Fund Name <SortIndicator column="fund_name" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('initial_invested_amount')}>
                  <span className={styles.headerContent}>Initial <SortIndicator column="initial_invested_amount" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('amount_march_2025')}>
                  <span className={styles.headerContent}>Mar 2025 <SortIndicator column="amount_march_2025" /></span>
                </th>
                <th>CAGR</th>
                {/* Internet/Estimated Data Columns - visually differentiated */}
                <th className={`${styles.sortableHeader} ${styles.internetDataHeader}`} onClick={() => handleSort('current_amount')}>
                  <span className={styles.headerContent}>Est. Current <SortIndicator column="current_amount" /></span>
                </th>
                <th className={`${styles.sortableHeader} ${styles.internetDataHeader}`} onClick={() => handleSort('return_1y')}>
                  <span className={styles.headerContent}>1Y <SortIndicator column="return_1y" /></span>
                </th>
                <th className={`${styles.sortableHeader} ${styles.internetDataHeader}`} onClick={() => handleSort('return_3y')}>
                  <span className={styles.headerContent}>3Y <SortIndicator column="return_3y" /></span>
                </th>
                <th className={`${styles.sortableHeader} ${styles.internetDataHeader}`} onClick={() => handleSort('return_5y')}>
                  <span className={styles.headerContent}>5Y <SortIndicator column="return_5y" /></span>
                </th>
                <th>Edit</th>
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((holding) => {
                const nRankScore = calculateHoldingNRank(holding)
                const nRankTier = getNRankTier(nRankScore)
                return (
                <tr key={holding.id}>
                  {/* N-Rank Score */}
                  <td className={styles.neelScoreCell}>
                    <span 
                      className={`${styles.neelScore} ${styles.neelScoreClickable} ${
                        nRankTier === 'excellent' ? styles.neelScoreExcellent :
                        nRankTier === 'good' ? styles.neelScoreGood :
                        nRankTier === 'caution' ? styles.neelScoreCaution :
                        nRankTier === 'unknown' ? styles.neelScoreLow :
                        styles.neelScorePoor
                      }`}
                      onClick={() => { setSelectedFundForDetails(holding); setShowDetailsModal(true); }}
                      title={nRankScore === 0 ? 'Click "Enrich Data" to calculate N-Rank' : `N-Rank: ${nRankScore}/100`}
                    >
                      {nRankScore === 0 ? '?' : nRankScore}
                    </span>
                  </td>
                  <td className={styles.mono}>
                    {holding.investment_date 
                      ? new Date(holding.investment_date).toLocaleDateString('en-GB', { 
                          day: '2-digit', 
                          month: '2-digit', 
                          year: '2-digit' 
                        })
                      : '-'}
                  </td>
                  <td className={styles.fundName}>
                    <span 
                      className={styles.fundNameClickable}
                      onClick={() => { setSelectedFundForDetails(holding); setShowDetailsModal(true); }}
                      title={FUND_NAME_MAPPING[holding.fund_name]?.properName || holding.fund_name}
                    >
                      {holding.fund_name}
                    </span>
                  </td>
                  <td className={styles.mono}>{formatCurrencyINR(holding.initial_invested_amount)}</td>
                  <td className={styles.mono}>
                    {holding.amount_march_2025 ? formatCurrencyINR(holding.amount_march_2025) : '-'}
                  </td>
                  {/* CAGR - calculated from actuals */}
                  <td className={styles.mono}>
                    {(() => {
                      const initial = holding.initial_invested_amount || 0
                      const final = holding.amount_march_2025 || initial
                      
                      // Can't calculate if no initial investment
                      if (initial <= 0 || !holding.investment_date) return '-'
                      
                      const investDate = new Date(holding.investment_date)
                      const marchDate = new Date(2025, 2, 31) // March 31, 2025
                      const years = (marchDate.getTime() - investDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
                      
                      // Future investment - can't calculate CAGR yet
                      if (years <= 0) return <span style={{ color: 'var(--color-text-tertiary)' }}>N/A</span>
                      
                      const cagr = (Math.pow(final / initial, 1 / years) - 1) * 100
                      const isPositive = cagr >= 0
                      
                      return (
                        <span className={isPositive ? styles.profit : styles.loss}>
                          {cagr.toFixed(1)}%
                        </span>
                      )
                    })()}
                  </td>
                  {/* Internet/Estimated Data - italicized with muted colors */}
                  <td className={styles.internetDataCell}>
                    {(() => {
                      const est = calculateEstimatedCurrent(holding)
                      return est ? formatCurrencyINR(est) : '-'
                    })()}
                  </td>
                  <td className={`${styles.internetDataCell} ${holding.return_1y && holding.return_1y > 0 ? styles.profit : holding.return_1y && holding.return_1y < 0 ? styles.loss : ''}`}>
                    {holding.return_1y !== null && holding.return_1y !== undefined 
                      ? `${holding.return_1y.toFixed(1)}%` 
                      : '-'}
                  </td>
                  <td className={`${styles.internetDataCell} ${holding.return_3y && holding.return_3y > 0 ? styles.profit : holding.return_3y && holding.return_3y < 0 ? styles.loss : ''}`}>
                    {holding.return_3y !== null && holding.return_3y !== undefined 
                      ? `${holding.return_3y.toFixed(1)}%` 
                      : '-'}
                  </td>
                  <td className={`${styles.internetDataCell} ${holding.return_5y && holding.return_5y > 0 ? styles.profit : holding.return_5y && holding.return_5y < 0 ? styles.loss : ''}`}>
                    {holding.return_5y !== null && holding.return_5y !== undefined 
                      ? `${holding.return_5y.toFixed(1)}%` 
                      : '-'}
                  </td>
                  <td>
                    <button 
                      onClick={() => { setEditingHolding(holding); setShowAddModal(true); }}
                      className={styles.editIconButton}
                      title="Edit"
                    >
                      <Edit size={16} />
                    </button>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <MutualFundHoldingModal
          holding={editingHolding}
          onClose={() => { setShowAddModal(false); setEditingHolding(null); }}
          onSave={handleSaveHolding}
          onDelete={editingHolding ? () => handleDeleteHolding(editingHolding.id) : undefined}
        />
      )}

      {/* Fund Details Modal with N-Rank Breakdown */}
      {showDetailsModal && selectedFundForDetails && (
        <HoldingDetailsModal
          holding={selectedFundForDetails}
          onClose={() => { setShowDetailsModal(false); setSelectedFundForDetails(null); }}
          calculateNRank={calculateHoldingNRank}
          getNRankTier={getNRankTier}
        />
      )}
    </div>
  )
}

// Stock Holdings Section Component (for Father's stocks)
type StockHoldingSortColumn = 'investment_date' | 'symbol' | 'company_name' | 'quantity' | 'initial_invested_amount' | 'amount_march_2025' | 'current_amount' | null

function StockHoldingsSection({ owner }: { owner: 'Father' | 'Neel' }) {
  const [holdings, setHoldings] = useState<FatherStockHolding[]>([])
  const [summary, setSummary] = useState<FatherStockSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingHolding, setEditingHolding] = useState<FatherStockHolding | null>(null)
  const [sortColumn, setSortColumn] = useState<StockHoldingSortColumn>('investment_date')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    fetchHoldings()
  }, [owner])

  const fetchHoldings = async () => {
    setLoading(true)
    setError(null)
    try {
      if (owner === 'Father') {
        const response = await fetch(`${API_BASE}/father-stocks`, {
          headers: getAuthHeaders(),
        })
        if (!response.ok) {
          throw new Error('Failed to fetch stock holdings')
        }
        const data = await response.json()
        setHoldings(data.holdings || [])
        setSummary(data.summary || null)
      } else {
        setHoldings([])
        setSummary(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveHolding = async (holdingData: Partial<FatherStockHolding>) => {
    try {
      const url = editingHolding 
        ? `${API_BASE}/father-stocks/${editingHolding.id}`
        : `${API_BASE}/father-stocks`
      const method = editingHolding ? 'PUT' : 'POST'
      
      const response = await fetch(url, {
        method,
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(holdingData),
      })
      
      if (!response.ok) {
        throw new Error('Failed to save holding')
      }
      
      await fetchHoldings()
      setShowAddModal(false)
      setEditingHolding(null)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  const handleDeleteHolding = async (id: number) => {
    if (!confirm('Are you sure you want to delete this holding?')) return
    
    try {
      const response = await fetch(`${API_BASE}/father-stocks/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      
      if (!response.ok) {
        throw new Error('Failed to delete holding')
      }
      
      await fetchHoldings()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  const handleSort = (column: StockHoldingSortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      const descendingColumns: StockHoldingSortColumn[] = ['initial_invested_amount', 'amount_march_2025', 'current_amount', 'quantity', 'investment_date']
      setSortDirection(descendingColumns.includes(column) ? 'desc' : 'asc')
    }
  }

  const sortedHoldings = [...holdings].sort((a, b) => {
    if (!sortColumn) return 0
    
    let aVal: any = a[sortColumn]
    let bVal: any = b[sortColumn]
    
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    if (sortColumn === 'investment_date') {
      aVal = new Date(aVal).getTime()
      bVal = new Date(bVal).getTime()
    }
    
    if (sortColumn === 'symbol' || sortColumn === 'company_name') {
      aVal = String(aVal).toLowerCase()
      bVal = String(bVal).toLowerCase()
      return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
    }
    
    return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
  })

  const SortIndicator = ({ column }: { column: StockHoldingSortColumn }) => {
    if (sortColumn !== column) return <span className={styles.sortIndicator}>↕</span>
    return <span className={styles.sortIndicator}>{sortDirection === 'asc' ? '↑' : '↓'}</span>
  }

  // Calculate CAGR for a holding
  const calculateCAGR = (holding: FatherStockHolding): number | null => {
    const initial = holding.initial_invested_amount || 0
    const final = holding.amount_march_2025 || initial
    if (initial <= 0 || !holding.investment_date) return null
    
    const investDate = new Date(holding.investment_date)
    const marchDate = new Date(2025, 2, 31)
    const years = (marchDate.getTime() - investDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
    if (years <= 0) return null
    
    return (Math.pow(final / initial, 1 / years) - 1) * 100
  }

  if (loading) {
    return (
      <div className={styles.emptyState}>
        <RefreshCw size={48} className={styles.spinner} />
        <p>Loading stock holdings...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.emptyState}>
        <AlertCircle size={48} />
        <p>Error: {error}</p>
        <button onClick={fetchHoldings} className={styles.searchButton}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className={styles.section}>
      {/* Header */}
      <div className={styles.researchHeader}>
        <div className={styles.searchBox}>
          {owner === 'Father' && (
            <button onClick={() => { setEditingHolding(null); setShowAddModal(true); }} className={styles.searchButton}>
              <Plus size={18} />
              Add Stock
            </button>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {summary && summary.count > 0 && (
        <div className={styles.summaryCards} style={{ marginBottom: 'var(--space-6)' }}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Holdings</div>
            <div className={styles.summaryCardValue}>{summary.count}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Total Invested</div>
            <div className={styles.summaryCardValue}>{formatCurrencyINR(summary.total_invested)}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Value (Mar 31, 2025)</div>
            <div className={styles.summaryCardValue}>{formatCurrencyINR(summary.total_march_2025)}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryCardLabel}>Total Gain/Loss</div>
            <div className={`${styles.summaryCardValue} ${(summary.total_gain_loss || 0) >= 0 ? styles.profit : styles.loss}`}>
              {summary.total_gain_loss ? formatCurrencyINR(summary.total_gain_loss) : '-'}
            </div>
          </div>
        </div>
      )}

      {/* Holdings Table */}
      {holdings.length === 0 ? (
        <div className={styles.emptyState}>
          <TrendingUp size={48} />
          <p>No stock holdings added yet</p>
          <p className={styles.emptyStateSubtext}>Add stock holdings to track performance</p>
          {owner === 'Father' && (
            <button onClick={() => setShowAddModal(true)} className={styles.addButton}>
              <Plus size={18} />
              Add First Stock
            </button>
          )}
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.sortableHeader} onClick={() => handleSort('investment_date')}>
                  <span className={styles.headerContent}>Date <SortIndicator column="investment_date" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('symbol')}>
                  <span className={styles.headerContent}>Symbol <SortIndicator column="symbol" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('company_name')}>
                  <span className={styles.headerContent}>Company <SortIndicator column="company_name" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('quantity')}>
                  <span className={styles.headerContent}>Qty <SortIndicator column="quantity" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('initial_invested_amount')}>
                  <span className={styles.headerContent}>Initial <SortIndicator column="initial_invested_amount" /></span>
                </th>
                <th className={styles.sortableHeader} onClick={() => handleSort('amount_march_2025')}>
                  <span className={styles.headerContent}>Mar 2025 <SortIndicator column="amount_march_2025" /></span>
                </th>
                <th>CAGR</th>
                <th>Edit</th>
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((holding) => {
                const cagr = calculateCAGR(holding)
                return (
                  <tr key={holding.id}>
                    <td className={styles.mono}>
                      {holding.investment_date 
                        ? new Date(holding.investment_date).toLocaleDateString('en-GB', { 
                            day: '2-digit', month: '2-digit', year: '2-digit' 
                          })
                        : '-'}
                    </td>
                    <td className={styles.symbol}>{holding.symbol}</td>
                    <td>{holding.company_name || '-'}</td>
                    <td className={styles.mono}>{holding.quantity?.toLocaleString() || '-'}</td>
                    <td className={styles.mono}>{formatCurrencyINR(holding.initial_invested_amount)}</td>
                    <td className={styles.mono}>
                      {holding.amount_march_2025 ? formatCurrencyINR(holding.amount_march_2025) : '-'}
                    </td>
                    <td className={styles.mono}>
                      {cagr !== null ? (
                        <span className={cagr >= 0 ? styles.profit : styles.loss}>
                          {cagr.toFixed(1)}%
                        </span>
                      ) : '-'}
                    </td>
                    <td>
                      <button 
                        onClick={() => { setEditingHolding(holding); setShowAddModal(true); }}
                        className={styles.editIconButton}
                        title="Edit"
                      >
                        <Edit size={16} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <StockHoldingModal
          holding={editingHolding}
          onClose={() => { setShowAddModal(false); setEditingHolding(null); }}
          onSave={handleSaveHolding}
          onDelete={editingHolding ? () => handleDeleteHolding(editingHolding.id) : undefined}
        />
      )}
    </div>
  )
}

// Stock Holding Add/Edit Modal
function StockHoldingModal({
  holding,
  onClose,
  onSave,
  onDelete
}: {
  holding: FatherStockHolding | null
  onClose: () => void
  onSave: (data: Partial<FatherStockHolding>) => void
  onDelete?: () => void
}) {
  const [formData, setFormData] = useState({
    investment_date: holding?.investment_date || new Date().toISOString().split('T')[0],
    symbol: holding?.symbol || '',
    company_name: holding?.company_name || '',
    quantity: holding?.quantity?.toString() || '',
    average_price: holding?.average_price?.toString() || '',
    initial_invested_amount: holding?.initial_invested_amount?.toString() || '',
    amount_march_2025: holding?.amount_march_2025?.toString() || '',
    sector: holding?.sector || '',
    notes: holding?.notes || '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      investment_date: formData.investment_date,
      symbol: formData.symbol.toUpperCase(),
      company_name: formData.company_name || undefined,
      quantity: parseFloat(formData.quantity) || 0,
      average_price: formData.average_price ? parseFloat(formData.average_price) : undefined,
      initial_invested_amount: parseFloat(formData.initial_invested_amount) || 0,
      amount_march_2025: formData.amount_march_2025 ? parseFloat(formData.amount_march_2025) : undefined,
      sector: formData.sector || undefined,
      notes: formData.notes || undefined,
    })
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2>{holding ? 'Edit Stock' : 'Add Stock'}</h2>
          <button onClick={onClose} className={styles.modalClose}>×</button>
        </div>
        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <div className={styles.formRow}>
            <label>
              Investment Date *
              <input
                type="date"
                value={formData.investment_date}
                onChange={e => setFormData({ ...formData, investment_date: e.target.value })}
                required
              />
            </label>
            <label>
              Symbol *
              <input
                type="text"
                value={formData.symbol}
                onChange={e => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                placeholder="RELIANCE"
                required
              />
            </label>
          </div>
          <div className={styles.formRow}>
            <label>
              Company Name
              <input
                type="text"
                value={formData.company_name}
                onChange={e => setFormData({ ...formData, company_name: e.target.value })}
                placeholder="Reliance Industries Ltd"
              />
            </label>
            <label>
              Sector
              <input
                type="text"
                value={formData.sector}
                onChange={e => setFormData({ ...formData, sector: e.target.value })}
                placeholder="Oil & Gas"
              />
            </label>
          </div>
          <div className={styles.formRow}>
            <label>
              Quantity *
              <input
                type="number"
                value={formData.quantity}
                onChange={e => setFormData({ ...formData, quantity: e.target.value })}
                step="0.0001"
                placeholder="100"
                required
              />
            </label>
            <label>
              Average Price (₹)
              <input
                type="number"
                value={formData.average_price}
                onChange={e => setFormData({ ...formData, average_price: e.target.value })}
                step="0.01"
                placeholder="1200.50"
              />
            </label>
          </div>
          <div className={styles.formRow}>
            <label>
              Initial Investment (₹) *
              <input
                type="number"
                value={formData.initial_invested_amount}
                onChange={e => setFormData({ ...formData, initial_invested_amount: e.target.value })}
                step="0.01"
                required
              />
            </label>
            <label>
              Amount March 2025 (₹)
              <input
                type="number"
                value={formData.amount_march_2025}
                onChange={e => setFormData({ ...formData, amount_march_2025: e.target.value })}
                step="0.01"
              />
            </label>
          </div>
          <label>
            Notes
            <textarea
              value={formData.notes}
              onChange={e => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
            />
          </label>
          <div className={styles.modalActions}>
            {onDelete && (
              <button type="button" onClick={onDelete} className={styles.deleteButton}>
                Delete
              </button>
            )}
            <div style={{ flex: 1 }} />
            <button type="button" onClick={onClose} className={styles.cancelButton}>
              Cancel
            </button>
            <button type="submit" className={styles.saveButton}>
              {holding ? 'Update' : 'Add'} Stock
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Fund Holding Details Modal
function FundHoldingDetailsModal({ 
  holding, 
  onClose 
}: { 
  holding: FatherMutualFundHolding
  onClose: () => void
}) {
  const fundInfo = FUND_NAME_MAPPING[holding.fund_name] || { 
    properName: holding.fund_name, 
    category: 'Unknown' 
  }

  // Calculate metrics
  const initial = holding.initial_invested_amount || 0
  const march2025 = holding.amount_march_2025 || initial
  const current = holding.current_amount || march2025
  const absoluteGain = march2025 - initial
  const percentageGain = initial > 0 ? ((march2025 - initial) / initial) * 100 : 0
  
  // Calculate CAGR
  let cagr = 0
  let years = 0
  if (initial > 0 && holding.investment_date) {
    const investDate = new Date(holding.investment_date)
    const marchDate = new Date(2025, 2, 31)
    years = (marchDate.getTime() - investDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
    if (years > 0) {
      cagr = (Math.pow(march2025 / initial, 1 / years) - 1) * 100
    }
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.fundDetailsModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <h2>{holding.fund_name}</h2>
            <p className={styles.modalSubtitle}>{fundInfo.properName}</p>
          </div>
          <button onClick={onClose} className={styles.modalClose}>×</button>
        </div>
        
        <div className={styles.modalContent}>
          <div className={styles.modalSection}>
            <h3>Fund Information</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Common Name</span>
                <span className={styles.modalValue}>{holding.fund_name}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Proper Fund Name</span>
                <span className={styles.modalValue}>{fundInfo.properName}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Category</span>
                <span className={styles.modalValue}>{fundInfo.category}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Folio Number</span>
                <span className={styles.modalValue}>{holding.folio_number || '-'}</span>
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Investment Details</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Investment Date</span>
                <span className={styles.modalValue}>
                  {holding.investment_date 
                    ? new Date(holding.investment_date).toLocaleDateString('en-IN', { 
                        day: 'numeric', 
                        month: 'long', 
                        year: 'numeric' 
                      })
                    : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Holding Period</span>
                <span className={styles.modalValue}>
                  {years > 0 ? `${years.toFixed(1)} years` : 'N/A'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Initial Investment</span>
                <span className={styles.modalValue}>{formatCurrencyINR(initial)}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Value (Mar 31, 2025)</span>
                <span className={styles.modalValue}>
                  {holding.amount_march_2025 ? formatCurrencyINR(march2025) : '-'}
                </span>
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Performance</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Absolute Gain/Loss</span>
                <span className={`${styles.modalValue} ${absoluteGain >= 0 ? styles.profit : styles.loss}`}>
                  {holding.amount_march_2025 ? formatCurrencyINR(absoluteGain) : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Total Return</span>
                <span className={`${styles.modalValue} ${percentageGain >= 0 ? styles.profit : styles.loss}`}>
                  {holding.amount_march_2025 ? `${percentageGain.toFixed(1)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>CAGR (Annualized)</span>
                <span className={`${styles.modalValue} ${cagr >= 0 ? styles.profit : styles.loss}`}>
                  {years > 0 && holding.amount_march_2025 ? `${cagr.toFixed(1)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Est. Current Value</span>
                <span className={styles.modalValue}>
                  {holding.current_amount ? formatCurrencyINR(current) : '-'}
                </span>
              </div>
            </div>
          </div>

          {holding.notes && (
            <div className={styles.modalSection}>
              <h3>Notes</h3>
              <p style={{ color: 'var(--color-text-secondary)', margin: 0 }}>{holding.notes}</p>
            </div>
          )}

          <div className={styles.modalFooter}>
            <p className={styles.modalNote}>
              Performance calculated from investment date to March 31, 2025. 
              CAGR = Compound Annual Growth Rate.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// Enhanced Holding Details Modal with N-Rank Breakdown
function HoldingDetailsModal({ 
  holding, 
  onClose,
  calculateNRank,
  getNRankTier
}: { 
  holding: FatherMutualFundHolding
  onClose: () => void
  calculateNRank: (h: FatherMutualFundHolding) => number
  getNRankTier: (score: number) => 'excellent' | 'good' | 'caution' | 'poor' | 'unknown'
}) {
  const fundInfo = FUND_NAME_MAPPING[holding.fund_name] || { 
    properName: holding.fund_name, 
    category: holding.fund_category || 'Unknown' 
  }

  const nRankScore = calculateNRank(holding)
  const nRankTier = getNRankTier(nRankScore)
  
  // Check if fund is international
  const isInternational = holding.fund_category && 
    ['International', 'US Tech', 'US Broad', 'Global', 'Europe', 'FoF'].some(
      cat => holding.fund_category?.includes(cat) || holding.fund_name?.includes(cat)
    )

  // Calculate metrics
  const initial = holding.initial_invested_amount || 0
  const march2025 = holding.amount_march_2025 || initial
  const absoluteGain = march2025 - initial
  const percentageGain = initial > 0 ? ((march2025 - initial) / initial) * 100 : 0
  
  // Calculate CAGR
  let cagr = 0
  let years = 0
  if (initial > 0 && holding.investment_date) {
    const investDate = new Date(holding.investment_date)
    const marchDate = new Date(2025, 2, 31)
    years = (marchDate.getTime() - investDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
    if (years > 0) {
      cagr = (Math.pow(march2025 / initial, 1 / years) - 1) * 100
    }
  }

  // Calculate individual N-Rank components for breakdown
  const getBreakdown = () => {
    // v3: Updated weights for aggressive strategy
    const breakdown = {
      quality: { score: 0, max: 20, details: [] as any[] },
      returns: { score: 0, max: 50, details: [] as any[] },
      riskAdjusted: { score: 0, max: 15, details: [] as any[] },
      cost: { score: 0, max: 5, details: [] as any[] },
      strategicFit: { score: 0, max: 10, details: [] as any[] },
    }
    
    const name = holding.fund_name?.toLowerCase() || ''
    const category = holding.fund_category?.toLowerCase() || ''
    const isTech = category.includes('tech') || name.includes('fang')
    const isHealthcare = category.includes('health') || category.includes('pharma')
    const isBanking = category.includes('banking') || category.includes('financial')
    const isDirect = name.includes('direct')
    
    // Quality (20 pts)
    let ratingPts = 0
    if (holding.fund_rating) {
      const map: any = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 }
      ratingPts = map[holding.fund_rating] || 0
    }
    breakdown.quality.details.push({ name: 'Fund Rating', value: holding.fund_rating ? `${holding.fund_rating}★` : 'N/A', points: ratingPts, max: 10 })
    breakdown.quality.score += ratingPts
    
    let aumPts = 0
    if (holding.aum) {
      if (holding.aum >= 50000) aumPts = 5
      else if (holding.aum >= 10000) aumPts = 7
      else if (holding.aum >= 2000) aumPts = 5
      else if (holding.aum >= 500) aumPts = 2
    }
    breakdown.quality.details.push({ name: 'AUM', value: holding.aum ? `₹${holding.aum.toLocaleString()} Cr` : 'N/A', points: aumPts, max: 7 })
    breakdown.quality.score += aumPts
    
    let agePts = holding.return_10y ? 3 : holding.return_5y ? 2 : holding.return_3y ? 1 : 0
    breakdown.quality.details.push({ name: 'Fund Age', value: holding.return_10y ? '10+ yrs' : holding.return_5y ? '5+ yrs' : holding.return_3y ? '3+ yrs' : 'N/A', points: agePts, max: 3 })
    breakdown.quality.score += agePts
    
    // Returns (50 pts) - PRIMARY in v3
    let ret1yPts = 0
    if (holding.return_1y != null) {
      if (holding.return_1y > 30) ret1yPts = 15
      else if (holding.return_1y > 20) ret1yPts = 12
      else if (holding.return_1y > 15) ret1yPts = 9
      else if (holding.return_1y > 10) ret1yPts = 6
      else if (holding.return_1y > 5) ret1yPts = 3
      else if (holding.return_1y > 0) ret1yPts = 0
      else if (holding.return_1y > -5) ret1yPts = -5
      else ret1yPts = -10
    }
    breakdown.returns.details.push({ name: '1Y Return', value: holding.return_1y ? `${holding.return_1y.toFixed(1)}%` : 'N/A', points: ret1yPts, max: 15 })
    breakdown.returns.score += ret1yPts
    
    let ret3yPts = 0
    if (holding.return_3y != null) {
      if (holding.return_3y > 30) ret3yPts = 20
      else if (holding.return_3y > 25) ret3yPts = 16
      else if (holding.return_3y > 20) ret3yPts = 12
      else if (holding.return_3y > 15) ret3yPts = 8
      else if (holding.return_3y > 10) ret3yPts = 4
      else if (holding.return_3y > 5) ret3yPts = 0
      else ret3yPts = -5
    }
    breakdown.returns.details.push({ name: '3Y Return ⭐', value: holding.return_3y ? `${holding.return_3y.toFixed(1)}%` : 'N/A', points: ret3yPts, max: 20 })
    breakdown.returns.score += ret3yPts
    
    let ret5yPts = 0
    if (holding.return_5y != null) {
      if (holding.return_5y > 25) ret5yPts = 15
      else if (holding.return_5y > 20) ret5yPts = 12
      else if (holding.return_5y > 15) ret5yPts = 8
      else if (holding.return_5y > 10) ret5yPts = 4
      else if (holding.return_5y > 5) ret5yPts = 0
      else ret5yPts = -5
    }
    breakdown.returns.details.push({ name: '5Y Return', value: holding.return_5y ? `${holding.return_5y.toFixed(1)}%` : 'N/A', points: ret5yPts, max: 15 })
    breakdown.returns.score += ret5yPts
    
    // Risk-Adjusted (15 pts) - reduced in v3
    let sharpePts = 0
    if (holding.sharpe_ratio != null) {
      if (holding.sharpe_ratio > 1.5) sharpePts = 10
      else if (holding.sharpe_ratio > 1.0) sharpePts = 8
      else if (holding.sharpe_ratio > 0.7) sharpePts = 6
      else if (holding.sharpe_ratio > 0.5) sharpePts = 4
      else if (holding.sharpe_ratio > 0.3) sharpePts = 2
      else if (holding.sharpe_ratio > 0) sharpePts = 0
      else if (holding.sharpe_ratio > -0.5) sharpePts = -2
      else sharpePts = -5
    }
    breakdown.riskAdjusted.details.push({ name: 'Sharpe Ratio', value: holding.sharpe_ratio?.toFixed(2) || 'N/A', points: sharpePts, max: 10 })
    breakdown.riskAdjusted.score += sharpePts
    
    let alphaPts = 0
    if (holding.alpha != null) {
      if (holding.alpha > 7) alphaPts = 7
      else if (holding.alpha > 5) alphaPts = 5
      else if (holding.alpha > 3) alphaPts = 4
      else if (holding.alpha > 1) alphaPts = 2
      else if (holding.alpha > 0) alphaPts = 1
      else if (holding.alpha > -3) alphaPts = -2
      else alphaPts = -5
    }
    breakdown.riskAdjusted.details.push({ name: 'Alpha', value: holding.alpha ? `${holding.alpha.toFixed(1)}%` : 'N/A', points: alphaPts, max: 7 })
    breakdown.riskAdjusted.score += alphaPts
    
    // Cost (5 pts) - reduced in v3
    let expPts = 0
    if (holding.expense_ratio != null) {
      if (holding.expense_ratio < 0.5) expPts = 5
      else if (holding.expense_ratio < 0.75) expPts = 4
      else if (holding.expense_ratio < 1.0) expPts = 3
      else if (holding.expense_ratio < 1.5) expPts = 2
      else if (holding.expense_ratio < 2.0) expPts = 0
      else expPts = -3
    }
    breakdown.cost.details.push({ name: 'Expense Ratio', value: holding.expense_ratio ? `${holding.expense_ratio.toFixed(2)}%` : 'N/A', points: expPts, max: 5 })
    breakdown.cost.score += expPts
    
    // Strategic Fit (10 pts) - replaces User Fit in v3
    let sectorPts = 0
    let sectorNote = ''
    if (isTech) { sectorPts = 5; sectorNote = 'Tech: Missing sector' }
    else if (isHealthcare) { sectorPts = 4; sectorNote = 'Healthcare: Missing' }
    else if (isInternational) { sectorPts = 4; sectorNote = 'International: Diversification' }
    else if (isBanking) { sectorPts = 0; sectorNote = 'Banking: Over-allocated' }
    else { sectorPts = 1; sectorNote = 'General' }
    breakdown.strategicFit.details.push({ name: 'Sector', value: holding.fund_category || 'N/A', points: sectorPts, max: 5, note: sectorNote })
    breakdown.strategicFit.score += sectorPts
    
    if (isDirect) {
      breakdown.strategicFit.details.push({ name: 'Plan Type', value: 'Direct', points: 2, max: 2 })
      breakdown.strategicFit.score += 2
    }
    
    let historyPts = holding.return_10y ? 3 : holding.return_5y ? 2 : 0
    breakdown.strategicFit.details.push({ name: 'Track Record', value: holding.return_10y ? '10+ yrs' : holding.return_5y ? '5+ yrs' : 'Limited', points: historyPts, max: 3 })
    breakdown.strategicFit.score += historyPts
    
    return breakdown
  }
  
  const breakdown = getBreakdown()
  const hasEnrichedData = holding.aum || holding.expense_ratio || holding.fund_rating

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.fundDetailsModal} onClick={(e) => e.stopPropagation()} style={{ maxWidth: '800px' }}>
        <div className={styles.modalHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <span className={`${styles.neelScore} ${
              nRankTier === 'excellent' ? styles.neelScoreExcellent :
              nRankTier === 'good' ? styles.neelScoreGood :
              nRankTier === 'caution' ? styles.neelScoreCaution :
              nRankTier === 'unknown' ? styles.neelScoreLow :
              styles.neelScorePoor
            }`} style={{ fontSize: 'var(--text-xl)', minWidth: '48px', height: '40px' }}>
              {nRankScore === 0 ? '?' : nRankScore}
            </span>
            <div>
              <h2 style={{ margin: 0 }}>{holding.fund_name}</h2>
              <p className={styles.modalSubtitle}>{fundInfo.properName} • {holding.fund_category || fundInfo.category}</p>
            </div>
          </div>
          <button onClick={onClose} className={styles.modalClose}>×</button>
        </div>
        
        <div className={styles.modalContent} style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {!hasEnrichedData && (
            <div style={{ 
              padding: 'var(--space-3)', 
              background: 'rgba(255, 184, 0, 0.1)', 
              border: '1px solid var(--color-warning)',
              borderRadius: 'var(--radius-md)',
              marginBottom: 'var(--space-4)',
              fontSize: 'var(--text-sm)',
              color: 'var(--color-warning)'
            }}>
              ⚠️ Missing fund data. Click "Enrich Data" button to fetch AUM, Expense Ratio, and Rating from Kuvera API.
            </div>
          )}
          
          {/* N-Rank Breakdown */}
          <div className={styles.modalSection}>
            <h3>N-Rank Breakdown ({nRankScore}/100)</h3>
            <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
              {/* Quality */}
              <div className={styles.breakdownSection}>
                <div className={styles.breakdownSectionHeader}>
                  <span>Quality & Credibility</span>
                  <span className={styles.breakdownSectionScore}>{breakdown.quality.score}/{breakdown.quality.max}</span>
                </div>
                {breakdown.quality.details.map((d, i) => (
                  <div key={i} className={styles.breakdownRow}>
                    <span className={styles.breakdownLabel}>{d.name}</span>
                    <span className={styles.breakdownValue}>{d.value}</span>
                    <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                  </div>
                ))}
              </div>
              
              {/* Risk-Adjusted */}
              <div className={styles.breakdownSection}>
                <div className={styles.breakdownSectionHeader}>
                  <span>Risk-Adjusted Performance</span>
                  <span className={styles.breakdownSectionScore}>{breakdown.riskAdjusted.score}/{breakdown.riskAdjusted.max}</span>
                </div>
                {breakdown.riskAdjusted.details.map((d, i) => (
                  <div key={i} className={styles.breakdownRow}>
                    <span className={styles.breakdownLabel}>{d.name}</span>
                    <span className={styles.breakdownValue}>{d.value}</span>
                    <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                  </div>
                ))}
              </div>
              
              {/* Returns */}
              <div className={styles.breakdownSection}>
                <div className={styles.breakdownSectionHeader}>
                  <span>Absolute Returns</span>
                  <span className={styles.breakdownSectionScore}>{breakdown.returns.score}/{breakdown.returns.max}</span>
                </div>
                {breakdown.returns.details.map((d, i) => (
                  <div key={i} className={styles.breakdownRow}>
                    <span className={styles.breakdownLabel}>{d.name}</span>
                    <span className={styles.breakdownValue}>{d.value}</span>
                    <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                  </div>
                ))}
              </div>
              
              {/* Cost */}
              <div className={styles.breakdownSection}>
                <div className={styles.breakdownSectionHeader}>
                  <span>Cost Efficiency</span>
                  <span className={styles.breakdownSectionScore}>{breakdown.cost.score}/{breakdown.cost.max}</span>
                </div>
                {breakdown.cost.details.map((d, i) => (
                  <div key={i} className={styles.breakdownRow}>
                    <span className={styles.breakdownLabel}>{d.name}</span>
                    <span className={styles.breakdownValue}>{d.value}</span>
                    <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                  </div>
                ))}
              </div>
              
              {/* Strategic Fit */}
              {breakdown.strategicFit.details.length > 0 && (
                <div className={styles.breakdownSection}>
                  <div className={styles.breakdownSectionHeader}>
                    <span>Strategic Fit</span>
                    <span className={styles.breakdownSectionScore}>{breakdown.strategicFit.score}/{breakdown.strategicFit.max}</span>
                  </div>
                  {breakdown.strategicFit.details.map((d, i) => (
                    <div key={i} className={styles.breakdownRow}>
                      <span className={styles.breakdownLabel}>{d.name}</span>
                      <span className={styles.breakdownValue}>{d.value}</span>
                      <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Investment Performance */}
          <div className={styles.modalSection}>
            <h3>Your Investment</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Investment Date</span>
                <span className={styles.modalValue}>
                  {holding.investment_date 
                    ? new Date(holding.investment_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
                    : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Holding Period</span>
                <span className={styles.modalValue}>{years > 0 ? `${years.toFixed(1)} years` : 'N/A'}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Initial Investment</span>
                <span className={styles.modalValue}>{formatCurrencyINR(initial)}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Value (Mar 2025)</span>
                <span className={styles.modalValue}>{holding.amount_march_2025 ? formatCurrencyINR(march2025) : '-'}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Gain/Loss</span>
                <span className={`${styles.modalValue} ${absoluteGain >= 0 ? styles.profit : styles.loss}`}>
                  {holding.amount_march_2025 ? formatCurrencyINR(absoluteGain) : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>CAGR</span>
                <span className={`${styles.modalValue} ${cagr >= 0 ? styles.profit : styles.loss}`}>
                  {years > 0 && holding.amount_march_2025 ? `${cagr.toFixed(1)}%` : '-'}
                </span>
              </div>
            </div>
          </div>

          {/* Fund Details from Kuvera */}
          {hasEnrichedData && (
            <div className={styles.modalSection}>
              <h3>Fund Details</h3>
              <div className={styles.modalGrid}>
                {holding.aum && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>AUM</span>
                    <span className={styles.modalValue}>₹{holding.aum.toLocaleString()} Cr</span>
                  </div>
                )}
                {holding.expense_ratio && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>Expense Ratio</span>
                    <span className={styles.modalValue}>{holding.expense_ratio.toFixed(2)}%</span>
                  </div>
                )}
                {holding.fund_rating && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>Fund Rating</span>
                    <span className={styles.modalValue}>{'★'.repeat(holding.fund_rating)}{'☆'.repeat(5 - holding.fund_rating)}</span>
                  </div>
                )}
                {holding.crisil_rating && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>CRISIL Rating</span>
                    <span className={styles.modalValue}>{holding.crisil_rating}</span>
                  </div>
                )}
                {holding.volatility && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>Volatility</span>
                    <span className={styles.modalValue}>{holding.volatility.toFixed(1)}%</span>
                  </div>
                )}
                {holding.fund_start_date && (
                  <div className={styles.modalMetric}>
                    <span className={styles.modalLabel}>Fund Start Date</span>
                    <span className={styles.modalValue}>
                      {new Date(holding.fund_start_date).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Mutual Fund Holding Add/Edit Modal
function MutualFundHoldingModal({ 
  holding, 
  onClose, 
  onSave,
  onDelete 
}: { 
  holding: FatherMutualFundHolding | null
  onClose: () => void
  onSave: (data: Partial<FatherMutualFundHolding>) => void
  onDelete?: () => void
}) {
  const [formData, setFormData] = useState({
    investment_date: holding?.investment_date || '',
    fund_name: holding?.fund_name || '',
    folio_number: holding?.folio_number || '',
    initial_invested_amount: holding?.initial_invested_amount?.toString() || '',
    amount_march_2025: holding?.amount_march_2025?.toString() || '',
    current_amount: holding?.current_amount?.toString() || '',
    return_1y: holding?.return_1y?.toString() || '',
    return_3y: holding?.return_3y?.toString() || '',
    return_5y: holding?.return_5y?.toString() || '',
    fund_category: holding?.fund_category || '',
    notes: holding?.notes || '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      investment_date: formData.investment_date,
      fund_name: formData.fund_name,
      folio_number: formData.folio_number || undefined,
      initial_invested_amount: parseFloat(formData.initial_invested_amount) || 0,
      amount_march_2025: formData.amount_march_2025 ? parseFloat(formData.amount_march_2025) : undefined,
      current_amount: formData.current_amount ? parseFloat(formData.current_amount) : undefined,
      return_1y: formData.return_1y ? parseFloat(formData.return_1y) : undefined,
      return_3y: formData.return_3y ? parseFloat(formData.return_3y) : undefined,
      return_5y: formData.return_5y ? parseFloat(formData.return_5y) : undefined,
      fund_category: formData.fund_category || undefined,
      notes: formData.notes || undefined,
    })
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.fundDetailsModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2>{holding ? 'Edit' : 'Add'} Mutual Fund Holding</h2>
          <button onClick={onClose} className={styles.modalClose}>×</button>
        </div>
        
        <form onSubmit={handleSubmit} className={styles.modalContent}>
          <div className={styles.modalSection}>
            <h3>Basic Information</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Investment Date *</label>
                <input
                  type="date"
                  value={formData.investment_date}
                  onChange={(e) => setFormData({ ...formData, investment_date: e.target.value })}
                  required
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Folio Number</label>
                <input
                  type="text"
                  value={formData.folio_number}
                  onChange={(e) => setFormData({ ...formData, folio_number: e.target.value })}
                  placeholder="e.g., 1234567890"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric} style={{ gridColumn: '1 / -1' }}>
                <label className={styles.modalLabel}>Fund Name *</label>
                <input
                  type="text"
                  value={formData.fund_name}
                  onChange={(e) => setFormData({ ...formData, fund_name: e.target.value })}
                  required
                  placeholder="e.g., HDFC Mid-Cap Opportunities Fund"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Fund Category</label>
                <input
                  type="text"
                  value={formData.fund_category}
                  onChange={(e) => setFormData({ ...formData, fund_category: e.target.value })}
                  placeholder="e.g., Equity, Debt, Hybrid"
                  className={styles.modalInput}
                />
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Amounts (₹)</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Initial Investment *</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.initial_invested_amount}
                  onChange={(e) => setFormData({ ...formData, initial_invested_amount: e.target.value })}
                  required
                  placeholder="e.g., 100000"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Value as of Mar 31, 2025</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.amount_march_2025}
                  onChange={(e) => setFormData({ ...formData, amount_march_2025: e.target.value })}
                  placeholder="e.g., 150000"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>Current Value</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.current_amount}
                  onChange={(e) => setFormData({ ...formData, current_amount: e.target.value })}
                  placeholder="e.g., 155000"
                  className={styles.modalInput}
                />
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Fund Performance (%)</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>1-Year Return</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.return_1y}
                  onChange={(e) => setFormData({ ...formData, return_1y: e.target.value })}
                  placeholder="e.g., 15.5"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>3-Year Return</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.return_3y}
                  onChange={(e) => setFormData({ ...formData, return_3y: e.target.value })}
                  placeholder="e.g., 12.3"
                  className={styles.modalInput}
                />
              </div>
              <div className={styles.modalMetric}>
                <label className={styles.modalLabel}>5-Year Return</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.return_5y}
                  onChange={(e) => setFormData({ ...formData, return_5y: e.target.value })}
                  placeholder="e.g., 18.7"
                  className={styles.modalInput}
                />
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Notes</h3>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Any additional notes..."
              className={styles.modalInput}
              style={{ minHeight: '80px', resize: 'vertical' }}
            />
          </div>

          <div className={styles.modalFooter} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            {onDelete && (
              <button 
                type="button" 
                onClick={onDelete}
                style={{ 
                  padding: 'var(--space-2) var(--space-4)', 
                  background: 'var(--color-negative)', 
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  cursor: 'pointer'
                }}
              >
                Delete
              </button>
            )}
            <div style={{ display: 'flex', gap: 'var(--space-2)', marginLeft: 'auto' }}>
              <button type="button" onClick={onClose} className={styles.cancelButton}>
                Cancel
              </button>
              <button type="submit" className={styles.saveButton}>
                {holding ? 'Update' : 'Add'} Holding
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

// Mutual Fund Research Section Component
// Sort column type
type SortColumn = 'neel_score' | 'recommendation_rank' | 'scheme_name' | 'fund_category' | 'aum' | 'expense_ratio' | 'return_1y' | 'return_3y' | 'return_5y' | 'volatility' | 'sharpe_ratio' | 'beta' | 'alpha' | 'value_research_rating' | null
type SortDirection = 'asc' | 'desc'

function MutualFundResearchSection() {
  const [funds, setFunds] = useState<any[]>([])
  const [loading, setLoading] = useState(true) // Initial loading state
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<Date | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [categories, setCategories] = useState<string[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [selectedFund, setSelectedFund] = useState<any | null>(null)
  const [showFundDetailsModal, setShowFundDetailsModal] = useState(false)
  const [isEditingFund, setIsEditingFund] = useState(false)
  const [editedFundData, setEditedFundData] = useState<any>({})
  const [sortColumn, setSortColumn] = useState<SortColumn>('recommendation_rank')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [showScoreBreakdown, setShowScoreBreakdown] = useState<string | null>(null) // fund id for popover

  // Load cached data on mount - don't auto-refresh, just show cached data
  useEffect(() => {
    let hasCachedData = false
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const cacheKey = `mf_research_cache_${selectedCategory}`
        const cached = localStorage.getItem(cacheKey)
        if (cached) {
          const parsed = JSON.parse(cached)
          // Always load cached data regardless of age - user can manually refresh
          if (parsed.funds && parsed.funds.length > 0) {
            setFunds(parsed.funds || [])
            hasCachedData = true
            if (parsed.generated_at) {
              setGeneratedAt(new Date(parsed.generated_at))
            }
          }
        }
      }
    } catch (e) {
      console.error('Error loading cached funds:', e)
    }
    
    // If we have cached data, don't show loading spinner
    if (hasCachedData) {
      setLoading(false)
    }
    
    // Load initial data from database (stale data)
    fetchFunds(false)
    fetchCategories()
  }, [selectedCategory])

  const fetchFunds = async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true)
    } else {
      // Only set loading on initial fetch if we don't have data
      if (funds.length === 0) {
        setLoading(true)
      }
    }
    setError(null)
    
    try {
      const categoryParam = selectedCategory !== 'all' ? `?category=${selectedCategory}` : ''
      const response = await fetch(`${API_BASE}/mf-research/compare${categoryParam}`, {
        headers: getAuthHeaders(),
        // Add timestamp to bypass browser cache during refresh
        ...(isRefresh && { cache: 'no-store' })
      })
      
      if (response.ok) {
        const data = await response.json()
        const fetchedFunds = data.funds || []
        
        // Update state with fresh data
        setFunds(fetchedFunds)
        setGeneratedAt(new Date())
        setLoading(false) // Clear loading state
        
        // Cache the results for next load
        try {
          const cacheKey = `mf_research_cache_${selectedCategory}`
          localStorage.setItem(cacheKey, JSON.stringify({
            funds: fetchedFunds,
            generated_at: new Date().toISOString(),
            timestamp: new Date().toISOString()
          }))
        } catch (e) {
          console.warn('Failed to cache funds:', e)
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch funds' }))
        // Only set error if we don't have cached data to show
        if (funds.length === 0) {
          setError(errorData.detail || `Error: ${response.status}`)
          setLoading(false) // Clear loading state on error
        } else {
          // We have stale data, just log the error
          console.warn('Failed to refresh funds, showing stale data:', errorData.detail)
        }
      }
    } catch (err) {
      console.error('Error fetching funds:', err)
      // Only set error if we don't have cached data to show
      if (funds.length === 0) {
        setError(err instanceof Error ? err.message : 'Failed to fetch funds')
        setLoading(false) // Clear loading state on error
      } else {
        // We have stale data, just log the error
        console.warn('Failed to refresh funds, showing stale data:', err)
      }
    } finally {
      if (isRefresh) {
        setRefreshing(false)
      }
    }
  }

  const fetchCategories = async () => {
    try {
      const response = await fetch(`${API_BASE}/mf-research/categories`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        setCategories(data.categories || [])
      }
    } catch (err) {
      console.error('Error fetching categories:', err)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    
    try {
      const response = await fetch(`${API_BASE}/mf-research/search?q=${encodeURIComponent(searchQuery)}`, {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        setSearchResults(data.results || [])
        setShowAddModal(true)
      }
    } catch (err) {
      console.error('Error searching funds:', err)
    }
  }

  const handleOpenFundDetails = (fund: any) => {
    setSelectedFund(fund)
    setShowFundDetailsModal(true)
  }

  const handleAddFund = async (schemeCode: string) => {
    try {
      const response = await fetch(`${API_BASE}/mf-research/add`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ scheme_code: schemeCode }),
      })
      if (response.ok) {
        setShowAddModal(false)
        setSearchQuery('')
        setSearchResults([])
        // Refresh to show the newly added fund
        await fetchFunds(true)
      }
    } catch (err) {
      console.error('Error adding fund:', err)
    }
  }

  // Handle column sorting
  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      // Set new column - default to ascending for rank/expense (lower is better), desc for others
      setSortColumn(column)
      const ascendingColumns: SortColumn[] = ['recommendation_rank', 'expense_ratio', 'volatility']
      setSortDirection(ascendingColumns.includes(column) ? 'asc' : 'desc')
    }
  }

  // Calculate Neel Score v3 helper - must be defined before sortedFunds uses it
  // v3: Aggressive wealth transfer strategy with 50% returns weight, sector bonuses
  // See docs/n-rank-v3-algorithm.md for full documentation
  const getNeelScore = (fund: any): number => {
    if (!fund) return 0
    
    try {
      let score = 0
      const name = fund.scheme_name?.toLowerCase() || ''
      const category = fund.fund_category?.toLowerCase() || ''
      
      // Detect sector/category for strategic fit
      const isTech = category.includes('tech') || name.includes('tech') || name.includes('fang') || name.includes('nasdaq')
      const isUSEquity = category.includes('us') || name.includes('us equity') || name.includes('bluechip')
      const isInternational = category.includes('international') || category.includes('global') || category.includes('europe') || category.includes('fof overseas')
      const isHealthcare = category.includes('health') || category.includes('pharma')
      const isConsumption = category.includes('consumption') || category.includes('fmcg')
      const isBanking = category.includes('banking') || category.includes('financial') || name.includes('banking') || name.includes('financial')
      const isInfra = category.includes('infra')
      const isDirect = name.includes('direct')
      
      // ========== DIMENSION 1: QUALITY (20 points) ==========
      // VR Rating (10 points)
      if (fund.value_research_rating) {
        const ratingMap: { [key: number]: number } = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 }
        score += ratingMap[fund.value_research_rating] || 0
      }
      // AUM (7 points)
      if (fund.aum) {
        if (fund.aum < 500) score += 0
        else if (fund.aum < 2000) score += 2
        else if (fund.aum < 10000) score += 5
        else if (fund.aum < 50000) score += 7
        else score += 5
      }
      // Fund Age (3 points)
      if (fund.return_10y) score += 3
      else if (fund.return_5y) score += 2
      else if (fund.return_3y) score += 1
      
      // ========== DIMENSION 2: RETURNS (50 points max, PRIMARY for aggressive) ==========
      // 1Y Return (15 to -10 points)
      if (fund.return_1y != null) {
        if (fund.return_1y > 30) score += 15
        else if (fund.return_1y > 20) score += 12
        else if (fund.return_1y > 15) score += 9
        else if (fund.return_1y > 10) score += 6
        else if (fund.return_1y > 5) score += 3
        else if (fund.return_1y > 0) score += 0
        else if (fund.return_1y > -5) score -= 5
        else score -= 10
      }
      // 3Y Return (20 to -5 points) - Most important
      if (fund.return_3y != null) {
        if (fund.return_3y > 30) score += 20
        else if (fund.return_3y > 25) score += 16
        else if (fund.return_3y > 20) score += 12
        else if (fund.return_3y > 15) score += 8
        else if (fund.return_3y > 10) score += 4
        else if (fund.return_3y > 5) score += 0
        else score -= 5
      }
      // 5Y Return (15 to -5 points)
      if (fund.return_5y != null) {
        if (fund.return_5y > 25) score += 15
        else if (fund.return_5y > 20) score += 12
        else if (fund.return_5y > 15) score += 8
        else if (fund.return_5y > 10) score += 4
        else if (fund.return_5y > 5) score += 0
        else score -= 5
      }
      // Momentum penalty (0 to -5 points)
      if (fund.return_1y != null && fund.return_3y != null) {
        const momentumGap = fund.return_3y - fund.return_1y
        if (momentumGap > 20) score -= 5
        else if (momentumGap > 15) score -= 3
        else if (momentumGap > 10) score -= 2
      }
      
      // ========== DIMENSION 3: RISK-ADJUSTED (15 points max, reduced for aggressive) ==========
      // Sharpe Ratio (10 to -5 points)
      if (fund.sharpe_ratio != null) {
        if (fund.sharpe_ratio > 1.5) score += 10
        else if (fund.sharpe_ratio > 1.0) score += 8
        else if (fund.sharpe_ratio > 0.7) score += 6
        else if (fund.sharpe_ratio > 0.5) score += 4
        else if (fund.sharpe_ratio > 0.3) score += 2
        else if (fund.sharpe_ratio > 0) score += 0
        else if (fund.sharpe_ratio > -0.5) score -= 2
        else score -= 5
      }
      // Alpha (7 to -5 points)
      if (fund.alpha != null) {
        if (fund.alpha > 7) score += 7
        else if (fund.alpha > 5) score += 5
        else if (fund.alpha > 3) score += 4
        else if (fund.alpha > 1) score += 2
        else if (fund.alpha > 0) score += 1
        else if (fund.alpha > -3) score -= 2
        else score -= 5
      }
      // Volatility penalty - only extreme (0 to -2 points)
      if (fund.volatility != null && fund.volatility > 20) {
        if (fund.volatility > 25) score -= 2
        else score -= 1
      }
      
      // ========== DIMENSION 4: COST (5 points max, reduced weight) ==========
      if (fund.expense_ratio != null) {
        if (fund.expense_ratio < 0.5) score += 5
        else if (fund.expense_ratio < 0.75) score += 4
        else if (fund.expense_ratio < 1.0) score += 3
        else if (fund.expense_ratio < 1.5) score += 2
        else if (fund.expense_ratio < 2.0) score += 0
        else score -= 3
      }
      
      // ========== DIMENSION 5: STRATEGIC FIT (10 points) ==========
      // Sector diversification bonus - reward missing sectors
      if (isTech) score += 5                    // Tech: Missing, high growth
      else if (isHealthcare) score += 4         // Healthcare: Missing, defensive+growth
      else if (isInternational || isUSEquity) score += 4  // International: Missing, geographic div
      else if (isConsumption) score += 3        // Consumption: Steady growth
      else if (isInfra) score += 2              // Infrastructure: India story
      else if (isBanking) score += 0            // Banking: Already over-allocated, no bonus
      
      // Direct plan bonus
      if (isDirect) score += 2
      
      // Clean history bonus (proxy: if has 10Y data)
      if (fund.return_10y) score += 3
      else if (fund.return_5y) score += 2
      
      // Floor at 0, cap at 100
      return Math.max(0, Math.min(100, Math.round(score)))
    } catch (err) {
      console.error('Error calculating Neel Score:', err)
      return 0
    }
  }

  // Sort funds based on current sort column and direction
  const sortedFunds = [...funds].sort((a, b) => {
    if (!sortColumn) return 0
    if (!a || !b) return 0
    
    try {
    let aVal: any
    let bVal: any
    
    // Special handling for neel_score (calculated field)
    if (sortColumn === 'neel_score') {
        aVal = getNeelScore(a)
        bVal = getNeelScore(b)
    } else {
      aVal = a[sortColumn]
      bVal = b[sortColumn]
    }
    
    // Handle nulls - push to bottom
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    // Handle string comparison for fund name and category
    if (sortColumn === 'scheme_name' || sortColumn === 'fund_category') {
        aVal = String(aVal || '').toLowerCase()
        bVal = String(bVal || '').toLowerCase()
      if (sortDirection === 'asc') {
        return aVal.localeCompare(bVal)
      } else {
        return bVal.localeCompare(aVal)
      }
    }
    
      // Numeric comparison - ensure values are numbers
      const numA = typeof aVal === 'number' ? aVal : parseFloat(aVal) || 0
      const numB = typeof bVal === 'number' ? bVal : parseFloat(bVal) || 0
      
    if (sortDirection === 'asc') {
        return numA - numB
    } else {
        return numB - numA
      }
    } catch (err) {
      console.error('Error sorting funds:', err)
      return 0
    }
  })

  // Sort indicator component
  const SortIndicator = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) {
      return <span className={styles.sortIndicator}>↕</span>
    }
    return (
      <span className={styles.sortIndicatorActive}>
        {sortDirection === 'asc' ? '↑' : '↓'}
      </span>
    )
  }

  // ========== NEEL INDICATOR CALCULATION v3 ==========
  // Calculate Neel Score for a fund (0-100 scale, higher is better)
  // v3: Aggressive wealth transfer strategy - 50% returns weight, sector bonuses
  // See docs/n-rank-v3-algorithm.md for full documentation
  const calculateNeelScore = (fund: any): number => {
    let score = 0
    const name = fund.scheme_name?.toLowerCase() || ''
    const category = fund.fund_category?.toLowerCase() || ''
    
    // Detect sector/category for strategic fit
    const isTech = category.includes('tech') || name.includes('tech') || name.includes('fang') || name.includes('nasdaq')
    const isUSEquity = category.includes('us') || name.includes('us equity') || name.includes('bluechip')
    const isInternational = category.includes('international') || category.includes('global') || category.includes('europe') || category.includes('fof overseas')
    const isHealthcare = category.includes('health') || category.includes('pharma')
    const isConsumption = category.includes('consumption') || category.includes('fmcg')
    const isBanking = category.includes('banking') || category.includes('financial') || name.includes('banking') || name.includes('financial')
    const isInfra = category.includes('infra')
    const isDirect = name.includes('direct')
    
    // ========== DIMENSION 1: QUALITY (20 points) ==========
    // VR Rating (10 points)
    if (fund.value_research_rating) {
      const ratingMap: { [key: number]: number } = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 }
      score += ratingMap[fund.value_research_rating] || 0
    }
    // AUM (7 points)
    if (fund.aum) {
      if (fund.aum < 500) score += 0
      else if (fund.aum < 2000) score += 2
      else if (fund.aum < 10000) score += 5
      else if (fund.aum < 50000) score += 7
      else score += 5
    }
    // Fund Age (3 points)
    if (fund.return_10y) score += 3
    else if (fund.return_5y) score += 2
    else if (fund.return_3y) score += 1
    
    // ========== DIMENSION 2: RETURNS (50 points max, PRIMARY for aggressive) ==========
    // 1Y Return (15 to -10 points)
    if (fund.return_1y !== null && fund.return_1y !== undefined) {
      if (fund.return_1y > 30) score += 15
      else if (fund.return_1y > 20) score += 12
      else if (fund.return_1y > 15) score += 9
      else if (fund.return_1y > 10) score += 6
      else if (fund.return_1y > 5) score += 3
      else if (fund.return_1y > 0) score += 0
      else if (fund.return_1y > -5) score -= 5
      else score -= 10
    }
    // 3Y Return (20 to -5 points) - Most important
    if (fund.return_3y !== null && fund.return_3y !== undefined) {
      if (fund.return_3y > 30) score += 20
      else if (fund.return_3y > 25) score += 16
      else if (fund.return_3y > 20) score += 12
      else if (fund.return_3y > 15) score += 8
      else if (fund.return_3y > 10) score += 4
      else if (fund.return_3y > 5) score += 0
      else score -= 5
    }
    // 5Y Return (15 to -5 points)
    if (fund.return_5y !== null && fund.return_5y !== undefined) {
      if (fund.return_5y > 25) score += 15
      else if (fund.return_5y > 20) score += 12
      else if (fund.return_5y > 15) score += 8
      else if (fund.return_5y > 10) score += 4
      else if (fund.return_5y > 5) score += 0
      else score -= 5
    }
    // Momentum penalty (0 to -5 points)
    if (fund.return_1y !== null && fund.return_3y !== null && 
        fund.return_1y !== undefined && fund.return_3y !== undefined) {
      const momentumGap = fund.return_3y - fund.return_1y
      if (momentumGap > 20) score -= 5
      else if (momentumGap > 15) score -= 3
      else if (momentumGap > 10) score -= 2
    }
    
    // ========== DIMENSION 3: RISK-ADJUSTED (15 points max, reduced for aggressive) ==========
    // Sharpe Ratio (10 to -5 points)
    if (fund.sharpe_ratio !== null && fund.sharpe_ratio !== undefined) {
      if (fund.sharpe_ratio > 1.5) score += 10
      else if (fund.sharpe_ratio > 1.0) score += 8
      else if (fund.sharpe_ratio > 0.7) score += 6
      else if (fund.sharpe_ratio > 0.5) score += 4
      else if (fund.sharpe_ratio > 0.3) score += 2
      else if (fund.sharpe_ratio > 0) score += 0
      else if (fund.sharpe_ratio > -0.5) score -= 2
      else score -= 5
    }
    // Alpha (7 to -5 points)
    if (fund.alpha !== null && fund.alpha !== undefined) {
      if (fund.alpha > 7) score += 7
      else if (fund.alpha > 5) score += 5
      else if (fund.alpha > 3) score += 4
      else if (fund.alpha > 1) score += 2
      else if (fund.alpha > 0) score += 1
      else if (fund.alpha > -3) score -= 2
      else score -= 5
    }
    // Volatility penalty - only extreme (0 to -2 points)
    if (fund.volatility !== null && fund.volatility !== undefined && fund.volatility > 20) {
      if (fund.volatility > 25) score -= 2
      else score -= 1
    }
    
    // ========== DIMENSION 4: COST (5 points max, reduced weight) ==========
    if (fund.expense_ratio !== null && fund.expense_ratio !== undefined) {
      if (fund.expense_ratio < 0.5) score += 5
      else if (fund.expense_ratio < 0.75) score += 4
      else if (fund.expense_ratio < 1.0) score += 3
      else if (fund.expense_ratio < 1.5) score += 2
      else if (fund.expense_ratio < 2.0) score += 0
      else score -= 3
    }
    
    // ========== DIMENSION 5: STRATEGIC FIT (10 points) ==========
    // Sector diversification bonus - reward missing sectors
    if (isTech) score += 5                    // Tech: Missing, high growth
    else if (isHealthcare) score += 4         // Healthcare: Missing, defensive+growth
    else if (isInternational || isUSEquity) score += 4  // International: Missing, geographic div
    else if (isConsumption) score += 3        // Consumption: Steady growth
    else if (isInfra) score += 2              // Infrastructure: India story
    else if (isBanking) score += 0            // Banking: Already over-allocated, no bonus
    
    // Direct plan bonus
    if (isDirect) score += 2
    
    // Clean history bonus (proxy: if has 10Y data)
    if (fund.return_10y) score += 3
    else if (fund.return_5y) score += 2
    
    // Floor at 0, cap at 100
    return Math.max(0, Math.min(100, Math.round(score)))
  }

  // Get detailed breakdown of Neel Score v3 for display
  // v3: Aggressive wealth transfer - 50% returns, sector bonuses
  interface ScoreBreakdown {
    total: number
    tier: 'excellent' | 'good' | 'caution' | 'poor'
    quality: { score: number; max: number; details: { name: string; value: string; points: number; max: number; note?: string }[] }
    returns: { score: number; max: number; min: number; details: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] }
    riskAdjusted: { score: number; max: number; min: number; details: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] }
    cost: { score: number; max: number; min: number; details: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] }
    strategicFit: { score: number; max: number; details: { name: string; value: string; points: number; max: number; note?: string }[] }
    warnings: { text: string }[]
    summary: string
  }

  const getNeelScoreBreakdown = (fund: any): ScoreBreakdown => {
    const name = fund.scheme_name?.toLowerCase() || ''
    const category = fund.fund_category?.toLowerCase() || ''
    
    // Detect sector/category for strategic fit
    const isTech = category.includes('tech') || name.includes('tech') || name.includes('fang') || name.includes('nasdaq')
    const isUSEquity = category.includes('us') || name.includes('us equity') || name.includes('bluechip')
    const isInternational = category.includes('international') || category.includes('global') || category.includes('europe') || category.includes('fof overseas')
    const isHealthcare = category.includes('health') || category.includes('pharma')
    const isConsumption = category.includes('consumption') || category.includes('fmcg')
    const isBanking = category.includes('banking') || category.includes('financial') || name.includes('banking') || name.includes('financial')
    const isInfra = category.includes('infra')
    const isDirect = name.includes('direct')
    
    // ========== DIMENSION 1: QUALITY (20 points) ==========
    const qualityDetails: { name: string; value: string; points: number; max: number; note?: string }[] = []
    let qualityScore = 0
    
    // VR Rating (10 points)
    let vrPoints = 0
    if (fund.value_research_rating) {
      const ratingMap: { [key: number]: number } = { 5: 10, 4: 7, 3: 4, 2: 2, 1: 0 }
      vrPoints = ratingMap[fund.value_research_rating] || 0
    }
    qualityDetails.push({
      name: 'VR Rating',
      value: fund.value_research_rating ? '★'.repeat(fund.value_research_rating) + '☆'.repeat(5 - fund.value_research_rating) : 'N/A',
      points: vrPoints,
      max: 10,
      note: vrPoints === 10 ? 'excellent' : vrPoints >= 7 ? 'very good' : vrPoints >= 4 ? 'average' : 'below avg'
    })
    qualityScore += vrPoints

    // AUM Size (7 points - reduced in v3)
    let aumPoints = 0
    let aumNote = ''
    if (fund.aum) {
      if (fund.aum < 500) { aumPoints = 0; aumNote = 'too small, closure risk' }
      else if (fund.aum < 2000) { aumPoints = 2; aumNote = 'small but acceptable' }
      else if (fund.aum < 10000) { aumPoints = 5; aumNote = 'good size' }
      else if (fund.aum < 50000) { aumPoints = 7; aumNote = 'OPTIMAL' }
      else { aumPoints = 5; aumNote = 'very large' }
    }
    qualityDetails.push({
      name: 'AUM',
      value: fund.aum ? `₹${fund.aum.toLocaleString('en-IN')} Cr` : 'N/A',
      points: aumPoints,
      max: 7,
      note: aumNote
    })
    qualityScore += aumPoints

    // Fund Age (3 points - reduced in v3)
    let agePoints = 0
    let ageNote = ''
    if (fund.return_10y) { agePoints = 3; ageNote = '10+ years - proven' }
    else if (fund.return_5y) { agePoints = 2; ageNote = '5-10 years' }
    else if (fund.return_3y) { agePoints = 1; ageNote = '3-5 years' }
    else { agePoints = 0; ageNote = '<3 years - new' }
    qualityDetails.push({
      name: 'Fund Age',
      value: fund.return_10y ? '10+ yrs' : fund.return_5y ? '5+ yrs' : fund.return_3y ? '3+ yrs' : '<3 yrs',
      points: agePoints,
      max: 3,
      note: ageNote
    })
    qualityScore += agePoints

    // ========== DIMENSION 2: RETURNS (50 points max - PRIMARY for aggressive v3) ==========
    const returnsDetails: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] = []
    let returnsScore = 0

    // 1-Year CAGR (15 to -10 points) - increased in v3
    let return1yPoints = 0
    let return1yNote = ''
    if (fund.return_1y !== null && fund.return_1y !== undefined) {
      if (fund.return_1y > 30) { return1yPoints = 15; return1yNote = '🔥 exceptional' }
      else if (fund.return_1y > 20) { return1yPoints = 12; return1yNote = 'excellent' }
      else if (fund.return_1y > 15) { return1yPoints = 9; return1yNote = 'very good' }
      else if (fund.return_1y > 10) { return1yPoints = 6; return1yNote = 'good' }
      else if (fund.return_1y > 5) { return1yPoints = 3; return1yNote = 'moderate' }
      else if (fund.return_1y > 0) { return1yPoints = 0; return1yNote = 'low positive' }
      else if (fund.return_1y > -5) { return1yPoints = -5; return1yNote = '⚠️ negative' }
      else { return1yPoints = -10; return1yNote = '🚨 SEVERE LOSS' }
    }
    returnsDetails.push({
      name: '1Y Return',
      value: fund.return_1y !== null && fund.return_1y !== undefined ? `${fund.return_1y.toFixed(1)}%` : 'N/A',
      points: return1yPoints,
      max: 15,
      min: -10,
      note: return1yNote
    })
    returnsScore += return1yPoints

    // 3-Year CAGR (20 to -5 points) - MOST IMPORTANT in v3
    let return3yPoints = 0
    let return3yNote = ''
    if (fund.return_3y !== null && fund.return_3y !== undefined) {
      if (fund.return_3y > 30) { return3yPoints = 20; return3yNote = '🔥 exceptional' }
      else if (fund.return_3y > 25) { return3yPoints = 16; return3yNote = 'excellent' }
      else if (fund.return_3y > 20) { return3yPoints = 12; return3yNote = 'very good' }
      else if (fund.return_3y > 15) { return3yPoints = 8; return3yNote = 'good' }
      else if (fund.return_3y > 10) { return3yPoints = 4; return3yNote = 'moderate' }
      else if (fund.return_3y > 5) { return3yPoints = 0; return3yNote = 'below avg' }
      else { return3yPoints = -5; return3yNote = '⚠️ poor' }
    }
    returnsDetails.push({
      name: '3Y CAGR ⭐',
      value: fund.return_3y ? `${fund.return_3y.toFixed(1)}%` : 'N/A',
      points: return3yPoints,
      max: 20,
      min: -5,
      note: return3yNote
    })
    returnsScore += return3yPoints

    // 5-Year CAGR (15 to -5 points) - increased in v3
    let return5yPoints = 0
    let return5yNote = ''
    if (fund.return_5y !== null && fund.return_5y !== undefined) {
      if (fund.return_5y > 25) { return5yPoints = 15; return5yNote = '🔥 exceptional' }
      else if (fund.return_5y > 20) { return5yPoints = 12; return5yNote = 'excellent' }
      else if (fund.return_5y > 15) { return5yPoints = 8; return5yNote = 'good' }
      else if (fund.return_5y > 10) { return5yPoints = 4; return5yNote = 'moderate' }
      else if (fund.return_5y > 5) { return5yPoints = 0; return5yNote = 'below avg' }
      else { return5yPoints = -5; return5yNote = '⚠️ poor' }
    }
    returnsDetails.push({
      name: '5Y CAGR',
      value: fund.return_5y ? `${fund.return_5y.toFixed(1)}%` : 'N/A',
      points: return5yPoints,
      max: 15,
      min: -5,
      note: return5yNote
    })
    returnsScore += return5yPoints

    // Momentum Penalty (0 to -5 points)
    let momentumPoints = 0
    let momentumNote = ''
    if (fund.return_1y !== null && fund.return_3y !== null && 
        fund.return_1y !== undefined && fund.return_3y !== undefined) {
      const momentumGap = fund.return_3y - fund.return_1y
      if (momentumGap > 20) { momentumPoints = -5; momentumNote = '🚨 SEVERE deterioration' }
      else if (momentumGap > 15) { momentumPoints = -3; momentumNote = '⚠️ deteriorating' }
      else if (momentumGap > 10) { momentumPoints = -2; momentumNote = '⚠️ slight deterioration' }
      else { momentumPoints = 0; momentumNote = 'stable or improving' }
      
      if (momentumGap > 10 || momentumPoints !== 0) {
        returnsDetails.push({
          name: 'Momentum',
          value: `Gap: ${momentumGap.toFixed(1)}pp`,
          points: momentumPoints,
          max: 0,
          min: -5,
          note: momentumNote
        })
        returnsScore += momentumPoints
      }
    }

    // ========== DIMENSION 3: RISK-ADJUSTED (15 points max - reduced in v3) ==========
    const riskDetails: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] = []
    let riskScore = 0

    // Sharpe Ratio (10 to -5 points) - reduced from 15 in v3
    let sharpePoints = 0
    let sharpeNote = ''
    if (fund.sharpe_ratio !== null && fund.sharpe_ratio !== undefined) {
      if (fund.sharpe_ratio > 1.5) { sharpePoints = 10; sharpeNote = 'exceptional' }
      else if (fund.sharpe_ratio > 1.0) { sharpePoints = 8; sharpeNote = 'excellent' }
      else if (fund.sharpe_ratio > 0.7) { sharpePoints = 6; sharpeNote = 'good' }
      else if (fund.sharpe_ratio > 0.5) { sharpePoints = 4; sharpeNote = 'average' }
      else if (fund.sharpe_ratio > 0.3) { sharpePoints = 2; sharpeNote = 'below avg' }
      else if (fund.sharpe_ratio > 0) { sharpePoints = 0; sharpeNote = 'low' }
      else if (fund.sharpe_ratio > -0.5) { sharpePoints = -2; sharpeNote = '⚠️ negative' }
      else { sharpePoints = -5; sharpeNote = '🚨 poor' }
    }
    riskDetails.push({
      name: 'Sharpe Ratio',
      value: fund.sharpe_ratio !== null && fund.sharpe_ratio !== undefined ? fund.sharpe_ratio.toFixed(2) : 'N/A',
      points: sharpePoints,
      max: 10,
      min: -5,
      note: sharpeNote
    })
    riskScore += sharpePoints

    // Alpha (7 to -5 points)
    let alphaPoints = 0
    let alphaNote = ''
    if (fund.alpha !== null && fund.alpha !== undefined) {
      if (fund.alpha > 7) { alphaPoints = 7; alphaNote = 'exceptional' }
      else if (fund.alpha > 5) { alphaPoints = 5; alphaNote = 'very good' }
      else if (fund.alpha > 3) { alphaPoints = 4; alphaNote = 'good' }
      else if (fund.alpha > 1) { alphaPoints = 2; alphaNote = 'slight outperformance' }
      else if (fund.alpha > 0) { alphaPoints = 1; alphaNote = 'marginal' }
      else if (fund.alpha > -3) { alphaPoints = -2; alphaNote = '⚠️ underperforming' }
      else { alphaPoints = -5; alphaNote = '🚨 significant underperformance' }
    }
    riskDetails.push({
      name: 'Alpha',
      value: fund.alpha !== null && fund.alpha !== undefined ? `${fund.alpha.toFixed(2)}%` : 'N/A',
      points: alphaPoints,
      max: 7,
      min: -5,
      note: alphaNote
    })
    riskScore += alphaPoints

    // Volatility penalty - only extreme in v3 (0 to -2 points)
    let stdDevPoints = 0
    let stdDevNote = 'acceptable for aggressive strategy'
    if (fund.volatility !== null && fund.volatility !== undefined) {
      if (fund.volatility > 25) { stdDevPoints = -2; stdDevNote = '⚠️ very high volatility' }
      else if (fund.volatility > 20) { stdDevPoints = -1; stdDevNote = '⚠️ high volatility' }
      else { stdDevPoints = 0; stdDevNote = 'acceptable' }
    }
    if (fund.volatility !== null && fund.volatility !== undefined) {
      riskDetails.push({
        name: 'Volatility',
        value: `${fund.volatility.toFixed(1)}%`,
        points: stdDevPoints,
        max: 0,
        min: -2,
        note: stdDevNote
      })
      riskScore += stdDevPoints
    }

    // ========== DIMENSION 4: COST (5 points max - reduced in v3) ==========
    const costDetails: { name: string; value: string; points: number; max: number; min?: number; note?: string }[] = []
    let costScore = 0

    let expensePoints = 0
    let expenseNote = ''
    if (fund.expense_ratio !== null && fund.expense_ratio !== undefined) {
      if (fund.expense_ratio < 0.5) { expensePoints = 5; expenseNote = 'excellent' }
      else if (fund.expense_ratio < 0.75) { expensePoints = 4; expenseNote = 'very good' }
      else if (fund.expense_ratio < 1.0) { expensePoints = 3; expenseNote = 'good' }
      else if (fund.expense_ratio < 1.5) { expensePoints = 2; expenseNote = 'moderate' }
      else if (fund.expense_ratio < 2.0) { expensePoints = 0; expenseNote = 'high' }
      else { expensePoints = -3; expenseNote = '⚠️ excessive' }
    }
    costDetails.push({
      name: 'Expense Ratio',
      value: fund.expense_ratio ? `${fund.expense_ratio.toFixed(2)}%` : 'N/A',
      points: expensePoints,
      max: 5,
      min: -3,
      note: expenseNote
    })
    costScore += expensePoints

    // ========== DIMENSION 5: STRATEGIC FIT (10 points) ==========
    const strategicFitDetails: { name: string; value: string; points: number; max: number; note?: string }[] = []
    let strategicFitScore = 0

    // Sector diversification bonus (5 points)
    let sectorPoints = 0
    let sectorValue = 'Other'
    let sectorNote = ''
    if (isTech) { sectorPoints = 5; sectorValue = 'Technology'; sectorNote = '🔥 HIGH GROWTH - Missing sector!' }
    else if (isHealthcare) { sectorPoints = 4; sectorValue = 'Healthcare'; sectorNote = '💊 Defensive + Growth - Missing!' }
    else if (isInternational || isUSEquity) { sectorPoints = 4; sectorValue = 'International'; sectorNote = '🌍 Geographic diversification - Missing!' }
    else if (isConsumption) { sectorPoints = 3; sectorValue = 'Consumption'; sectorNote = 'Steady growth' }
    else if (isInfra) { sectorPoints = 2; sectorValue = 'Infrastructure'; sectorNote = 'India growth story' }
    else if (isBanking) { sectorPoints = 0; sectorValue = 'Banking/Financial'; sectorNote = '⚠️ OVER-ALLOCATED - No bonus' }
    else { sectorPoints = 1; sectorValue = fund.fund_category || 'Diversified'; sectorNote = 'General diversification' }
    
    strategicFitDetails.push({
      name: 'Sector Bonus',
      value: sectorValue,
      points: sectorPoints,
      max: 5,
      note: sectorNote
    })
    strategicFitScore += sectorPoints

    // Direct plan bonus (2 points)
    const directPoints = isDirect ? 2 : 0
    strategicFitDetails.push({
      name: 'Plan Type',
      value: isDirect ? 'Direct' : 'Regular',
      points: directPoints,
      max: 2,
      note: isDirect ? 'Lower costs, tax efficient' : 'Higher expense ratio'
    })
    strategicFitScore += directPoints

    // Clean history bonus (3 points)
    let historyPoints = 0
    let historyNote = ''
    if (fund.return_10y) { historyPoints = 3; historyNote = 'Proven through cycles' }
    else if (fund.return_5y) { historyPoints = 2; historyNote = 'Good track record' }
    else { historyPoints = 0; historyNote = 'Limited history' }
    strategicFitDetails.push({
      name: 'Track Record',
      value: fund.return_10y ? '10+ years' : fund.return_5y ? '5+ years' : '<5 years',
      points: historyPoints,
      max: 3,
      note: historyNote
    })
    strategicFitScore += historyPoints

    // Calculate raw total (can be negative)
    const rawTotal = qualityScore + returnsScore + riskScore + costScore + strategicFitScore
    // Floor at 0, cap at 100
    const total = Math.max(0, Math.min(100, rawTotal))

    // Calculate tier based on score (v3 thresholds)
    let tier: 'excellent' | 'good' | 'caution' | 'poor' = 'poor'
    if (total >= 60) tier = 'excellent'
    else if (total >= 45) tier = 'good'
    else if (total >= 30) tier = 'caution'
    else tier = 'poor'

    // Calculate warnings based on elimination criteria (v3)
    const warnings: { text: string }[] = []
    
    // v3: Banking sector over-allocation warning
    if (isBanking) {
      warnings.push({ text: `⚠️ Banking/Financial sector - portfolio already over-allocated (45%+)` })
    }
    
    // v3: Missing sector opportunity
    if (isTech || isHealthcare || isInternational || isUSEquity) {
      // These are good - no warning needed
    }
    
    // v3: Negative 1Y return warning (most important)
    if (fund.return_1y !== null && fund.return_1y !== undefined && fund.return_1y < 0) {
      warnings.push({ text: `🚨 Negative 1Y return (${fund.return_1y.toFixed(1)}%) - recent poor performance` })
    }
    
    // v3: Negative Sharpe warning
    if (fund.sharpe_ratio !== null && fund.sharpe_ratio !== undefined && fund.sharpe_ratio < 0) {
      warnings.push({ text: `⚠️ Negative Sharpe ratio (${fund.sharpe_ratio.toFixed(2)}) - poor risk-adjusted returns` })
    }
    
    // v3: Negative Alpha warning
    if (fund.alpha !== null && fund.alpha !== undefined && fund.alpha < 0) {
      warnings.push({ text: `⚠️ Negative Alpha (${fund.alpha.toFixed(1)}%) - underperforming benchmark` })
    }
    
    // v3: Momentum deterioration warning (stricter threshold)
    if (fund.return_1y !== null && fund.return_3y !== null && 
        fund.return_1y !== undefined && fund.return_3y !== undefined) {
      const momentumGap = fund.return_3y - fund.return_1y
      if (momentumGap > 15) {
        warnings.push({ text: `🚨 SEVERE deterioration (1Y ${fund.return_1y.toFixed(1)}% vs 3Y ${fund.return_3y.toFixed(1)}%)` })
      } else if (momentumGap > 10) {
        warnings.push({ text: `⚠️ Deteriorating momentum (1Y ${fund.return_1y.toFixed(1)}% vs 3Y ${fund.return_3y.toFixed(1)}%)` })
      }
    }
    
    // VR Rating below 3 stars
    if (fund.value_research_rating && fund.value_research_rating < 3) {
      warnings.push({ text: `VR Rating below 3 stars (${fund.value_research_rating}★) - quality concern` })
    }
    
    // AUM too small
    if (fund.aum && fund.aum < 500) {
      warnings.push({ text: `AUM too small (₹${fund.aum} Cr) - closure risk` })
    }
    
    // Expense ratio too high (v3: simplified)
    if (fund.expense_ratio && fund.expense_ratio > 2.0) {
      warnings.push({ text: `Expense ratio high (${fund.expense_ratio.toFixed(2)}%) - fee drag` })
    }

    // Generate summary (v3: focus on returns and strategic fit)
    let summary = ''
    const strengths: string[] = []
    const weaknesses: string[] = []
    
    // v3: Returns are most important (50 points)
    if (returnsScore >= 35) strengths.push('🔥 exceptional returns')
    else if (returnsScore >= 25) strengths.push('strong returns')
    else if (returnsScore < 0) weaknesses.push('poor recent returns')
    
    // Strategic fit
    if (isTech || isHealthcare) strengths.push('fills portfolio gap')
    if (isInternational || isUSEquity) strengths.push('geographic diversification')
    if (isBanking) weaknesses.push('sector over-allocated')
    
    // Quality
    if (qualityScore >= 15) strengths.push('high quality')
    else if (qualityScore < 10) weaknesses.push('quality concerns')
    
    // Risk
    if (riskScore >= 10) strengths.push('good risk-adjusted')
    else if (riskScore < 0) weaknesses.push('poor risk metrics')
    
    if (strengths.length > 0) summary = `Strengths: ${strengths.join(', ')}.`
    if (weaknesses.length > 0) summary += ` Watch: ${weaknesses.join(', ')}.`
    if (!summary) summary = 'Moderate fund - consider alternatives.'

    return {
      total,
      tier,
      quality: { score: qualityScore, max: 20, details: qualityDetails },
      returns: { score: returnsScore, max: 50, min: -20, details: returnsDetails },
      riskAdjusted: { score: riskScore, max: 15, min: -12, details: riskDetails },
      cost: { score: costScore, max: 5, min: -3, details: costDetails },
      strategicFit: { score: strategicFitScore, max: 10, details: strategicFitDetails },
      warnings,
      summary
    }
  }

  // Calculate Neel Indicator allocation for top 3 funds
  const calculateNeelAllocation = (fund: any, allFunds: any[]): string | null => {
    // Only calculate for top 3 ranked funds
    if (!fund.recommendation_rank || fund.recommendation_rank > 3) {
      return null
    }
    
    // Get the top 3 funds by rank
    const top3 = allFunds
      .filter(f => f.recommendation_rank && f.recommendation_rank <= 3)
      .sort((a, b) => a.recommendation_rank - b.recommendation_rank)
    
    if (top3.length < 3) return null
    
    // Calculate Neel Scores for top 3
    const scores = top3.map(f => calculateNeelScore(f))
    const totalScore = scores.reduce((sum, s) => sum + Math.max(0, s), 0)
    
    if (totalScore === 0) return null
    
    const rank = fund.recommendation_rank
    const fundScore = scores[rank - 1]
    
    // Calculate proportional allocation with constraints
    let allocation: number
    if (rank === 1) {
      // Rank 1: 35-45%
      allocation = Math.max(35, Math.min(45, (fundScore / totalScore) * 100))
    } else if (rank === 2) {
      // Rank 2: 30-40%
      allocation = Math.max(30, Math.min(40, (fundScore / totalScore) * 100))
    } else {
      // Rank 3: Gets remainder (typically 20-30%)
      const alloc1 = Math.max(35, Math.min(45, (scores[0] / totalScore) * 100))
      const alloc2 = Math.max(30, Math.min(40, (scores[1] / totalScore) * 100))
      allocation = 100 - Math.round(alloc1 / 5) * 5 - Math.round(alloc2 / 5) * 5
    }
    
    // Round to nearest 5%
    allocation = Math.round(allocation / 5) * 5
    
    return `${allocation}%`
  }

  // Get Neel Score for display
  const getNeelScoreDisplay = (fund: any): string => {
    const score = calculateNeelScore(fund)
    return score.toFixed(1)
  }

  // Only show loading if we're still loading and have no data
  if (loading && funds.length === 0 && !error) {
    return (
      <div className={styles.emptyState}>
        <RefreshCw size={48} className={styles.spinner} />
        <p>Loading fund data...</p>
      </div>
    )
  }

  // Only show error state if we have no data to display
  if (error && funds.length === 0) {
    return (
      <div className={styles.emptyState}>
        <AlertCircle size={48} />
        <p>Error loading fund data</p>
        <p className={styles.emptyStateSubtext}>{error}</p>
        <button onClick={() => fetchFunds(true)} className={styles.searchButton} style={{ marginTop: 'var(--space-4)' }}>
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    )
  }

  const handleRefreshAll = async () => {
    setRefreshing(true)
    setError(null)
    
    try {
      // Step 1: Refresh data from MFapi.in (this updates the database)
      const refreshController = new AbortController()
      const refreshTimeout = setTimeout(() => {
        refreshController.abort()
        console.warn('Refresh timed out after 60 seconds - continuing with stale data')
      }, 60000) // 60 second timeout for refresh
      
      try {
        const refreshResponse = await fetch(`${API_BASE}/mf-research/refresh-all`, {
          method: 'POST',
          headers: getAuthHeaders(),
          signal: refreshController.signal
        })
        clearTimeout(refreshTimeout)
        
        if (refreshResponse.ok) {
          const refreshData = await refreshResponse.json()
          console.log('Funds refreshed:', refreshData)
          
          // Step 2: Fetch fresh data from database (now updated)
          await fetchFunds(true)
          
          // Show success message
          if (refreshData.refreshed > 0) {
            // Use a subtle notification instead of alert
            const message = `Refreshed ${refreshData.refreshed} funds${refreshData.failed > 0 ? `, ${refreshData.failed} failed` : ''}`
            console.log(message)
            // Could show a toast notification here instead of alert
          }
        } else {
          const errorData = await refreshResponse.json().catch(() => ({ detail: 'Failed to refresh funds' }))
          // Continue with stale data - don't block the UI
          console.warn('Refresh failed, showing stale data:', errorData.detail)
          // Still try to fetch current database state
          await fetchFunds(true)
        }
      } catch (refreshErr: any) {
        clearTimeout(refreshTimeout)
        if (refreshErr.name === 'AbortError') {
          console.warn('Refresh timed out (continuing with stale data)')
        } else {
          console.warn('Refresh failed (continuing with stale data):', refreshErr)
        }
        // Continue with stale data - fetch current database state
        await fetchFunds(true)
      }
    } catch (err) {
      console.error('Error refreshing funds:', err)
      // Don't set error if we have stale data to show
      if (funds.length === 0) {
        setError(err instanceof Error ? err.message : 'Failed to refresh funds')
      }
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className={styles.section}>
      {/* Search and Add */}
      <div className={styles.researchHeader}>
        <div className={styles.searchBox}>
          <input
            type="text"
            placeholder="Search mutual funds (e.g., DSP Global Equity, PPFAS)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            className={styles.searchInput}
            disabled={refreshing}
          />
          <button onClick={handleSearch} className={styles.searchButton} disabled={refreshing}>
            <Search size={18} />
            Search
          </button>
          <button 
            onClick={handleRefreshAll} 
            className={styles.refreshButton}
            disabled={refreshing}
            title="Refresh all funds with latest data from MFapi.in"
          >
            <RefreshCw size={18} className={refreshing ? styles.spinner : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh All'}
          </button>
        </div>
        
        {/* Data Freshness Indicator */}
        {generatedAt && (
          <div className={styles.freshnessInfo}>
            <span className={`${styles.lastUpdated} ${
              // Mark as stale if more than 1 hour old
              (new Date().getTime() - generatedAt.getTime() > 60 * 60 * 1000) ? styles.stale : ''
            }`}>
              <Clock size={14} />
              Last refreshed: {(() => {
                const now = new Date()
                const diffMs = now.getTime() - generatedAt.getTime()
                const diffMins = Math.floor(diffMs / 60000)
                const diffHours = Math.floor(diffMs / 3600000)
                const diffDays = Math.floor(diffMs / 86400000)
                
                if (diffMins < 1) return 'Just now'
                if (diffMins < 60) return `${diffMins}m ago`
                if (diffHours < 24) return `${diffHours}h ago`
                return `${diffDays}d ago`
              })()}
              {refreshing && ' (refreshing...)'}
            </span>
          </div>
        )}
        
        {/* Category Filter */}
        <div className={styles.categoryFilter}>
          <button
            className={selectedCategory === 'all' ? styles.active : ''}
            onClick={() => setSelectedCategory('all')}
          >
            All Categories
          </button>
          {categories.map(cat => (
            <button
              key={cat}
              className={selectedCategory === cat ? styles.active : ''}
              onClick={() => setSelectedCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Add Fund Modal */}
      {showAddModal && (
        <div className={styles.modalOverlay} onClick={() => setShowAddModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>Search Results</h3>
              <button onClick={() => setShowAddModal(false)} className={styles.modalClose}>×</button>
            </div>
            <div className={styles.modalContent}>
              {searchResults.length === 0 ? (
                <p>No funds found</p>
              ) : (
                <div className={styles.searchResultsList}>
                  {searchResults.map((result) => (
                    <div key={result.schemeCode} className={styles.searchResultItem}>
                      <div>
                        <div className={styles.resultName}>{result.schemeName}</div>
                        <div className={styles.resultCode}>Code: {result.schemeCode}</div>
                      </div>
                      <button
                        onClick={() => handleAddFund(result.schemeCode)}
                        className={styles.addFundButton}
                      >
                        <Plus size={16} />
                        Add
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Error Banner (only show if we have data, so it doesn't block the UI) */}
      {error && funds.length > 0 && (
        <div className={styles.errorBanner}>
          <AlertCircle size={16} />
          <span>{error}</span>
          <button onClick={() => setError(null)} className={styles.dismissError}>×</button>
        </div>
      )}

      {/* Comparison Table */}
      {funds.length === 0 ? (
        <div className={styles.emptyState}>
          <FileText size={48} />
          <p>No funds added for comparison yet</p>
          <p className={styles.emptyStateSubtext}>Search and add funds to compare their performance</p>
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table className={styles.researchTable}>
            <thead>
              <tr>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('neel_score')}>
                  <span className={styles.headerContent}>
                    N-Rank
                    <SortIndicator column="neel_score" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Neel Rank - Score (0-100) combining 5 dimensions: Quality, Risk-Adjusted Performance, Returns, Cost, and Fit.</div>
                    <div className={styles.tooltipLine2}>Higher is better. See docs/NEEL_INDICATOR.md for full methodology.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('scheme_name')}>
                  <span className={styles.headerContent}>
                    Fund Name
                    <SortIndicator column="scheme_name" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>The official name of the mutual fund scheme.</div>
                    <div className={styles.tooltipLine2}>Click to sort. Click fund name in table to view details.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('fund_category')}>
                  <span className={styles.headerContent}>
                    Category
                    <SortIndicator column="fund_category" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Type of fund classification.</div>
                    <div className={styles.tooltipLine2}>Flexi-Cap (Indian all-cap), US Tech (US technology), US Broad (broad US market), Europe, Global, Large-Cap, Mid-Cap, etc.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('aum')}>
                  <span className={styles.headerContent}>
                    AUM (₹Cr)
                    <SortIndicator column="aum" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Assets Under Management - total money in the fund.</div>
                    <div className={styles.tooltipLine2}>Avoid &lt;₹500 Cr (closure risk). Sweet spot: ₹2,000-50,000 Cr. Very large &gt;₹50,000 Cr = proven but less agile.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('expense_ratio')}>
                  <span className={styles.headerContent}>
                    Expense
                    <SortIndicator column="expense_ratio" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Annual fee charged by fund. Lower is better.</div>
                    <div className={styles.tooltipLine2}>For ₹10 lakh: 0.5% = ₹5,000/year, 2% = ₹20,000/year. Directly reduces returns. Passive: 0.1-0.5%, Active: 0.6-2.5%.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('return_1y')}>
                  <span className={styles.headerContent}>
                    1Y Return
                    <SortIndicator column="return_1y" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Returns over last 1 year.</div>
                    <div className={styles.tooltipLine2}>Good for recent performance check, but don't chase - can be misleading. Focus on 3Y &amp; 5Y instead.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('return_3y')}>
                  <span className={styles.headerContent}>
                    3Y Return
                    <SortIndicator column="return_3y" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Average annual returns over 3 years (CAGR).</div>
                    <div className={styles.tooltipLine2}>Most reliable metric - shows consistency through market cycles. Compare to category average.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('return_5y')}>
                  <span className={styles.headerContent}>
                    5Y Return
                    <SortIndicator column="return_5y" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Average annual returns over 5 years (CAGR).</div>
                    <div className={styles.tooltipLine2}>Best long-term indicator. Higher is better but check risk metrics too. Gold standard for comparison.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('volatility')}>
                  <span className={styles.headerContent}>
                    Std Dev
                    <SortIndicator column="volatility" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Volatility/risk - how much returns fluctuate. Lower is better.</div>
                    <div className={styles.tooltipLine2}>&lt;10 = Low risk/smooth, 10-15 = Medium, &gt;15 = High risk/bumpy. Expect ±SD variation yearly.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('sharpe_ratio')}>
                  <span className={styles.headerContent}>
                    Sharpe
                    <SortIndicator column="sharpe_ratio" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Returns per unit of risk taken. Higher is better.</div>
                    <div className={styles.tooltipLine2}>&gt;1.0 = Excellent, 0.5-1.0 = Good, &lt;0.5 = Poor risk/reward. Measures efficiency of converting risk to returns.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('beta')}>
                  <span className={styles.headerContent}>
                    Beta
                    <SortIndicator column="beta" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>How much fund moves vs market.</div>
                    <div className={styles.tooltipLine2}>1 = same as market, &gt;1 = amplifies market (more volatile), &lt;1 = less volatile. Beta 1.2 = 20% more movement than market.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('alpha')}>
                  <span className={styles.headerContent}>
                    Alpha
                    <SortIndicator column="alpha" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Fund manager's value-add above benchmark. Positive is good.</div>
                    <div className={styles.tooltipLine2}>&gt;5 = Exceptional, 2-5 = Good, 0-2 = Average, &lt;0 = Underperforming - pick index instead.</div>
                  </div>
                </th>
                <th className={`${styles.tooltipHeader} ${styles.sortableHeader}`} onClick={() => handleSort('value_research_rating')}>
                  <span className={styles.headerContent}>
                    VR Rating
                    <SortIndicator column="value_research_rating" />
                  </span>
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Value Research star rating (1-5 stars) based on risk-adjusted returns.</div>
                    <div className={styles.tooltipLine2}>★★★★★ = Top performers, ★★★★ = Very good, ★★★ = Average. 4+ stars recommended.</div>
                  </div>
                </th>
                <th className={styles.tooltipHeader}>
                  Tax Class
                  <div className={styles.tooltip}>
                    <div className={styles.tooltipLine1}>Tax classification for capital gains.</div>
                    <div className={styles.tooltipLine2}>Equity: 15% STCG (&lt;1yr), 10% LTCG (&gt;1yr, &gt;₹1L). Debt: Income tax slab. Hybrid: Based on equity allocation.</div>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedFunds.map((fund) => {
                const breakdown = getNeelScoreBreakdown(fund)
                return (
                <tr key={fund.id}>
                  <td className={styles.neelScoreCell}>
                    <div className={styles.neelScoreWrapper}>
                      <span 
                        className={`${styles.neelScore} ${styles.neelScoreClickable} ${
                          breakdown.tier === 'excellent' ? styles.neelScoreExcellent :
                          breakdown.tier === 'good' ? styles.neelScoreGood :
                          breakdown.tier === 'caution' ? styles.neelScoreCaution :
                          styles.neelScorePoor
                        }`}
                        onClick={() => setShowScoreBreakdown(showScoreBreakdown === fund.id ? null : fund.id)}
                      >
                        {breakdown.total}
                    </span>
                      {showScoreBreakdown === fund.id && (
                        <div className={styles.scoreBreakdownPopover}>
                          <div className={styles.breakdownHeader}>
                            <h4>N-Rank Breakdown: {breakdown.total}/100</h4>
                            <button onClick={() => setShowScoreBreakdown(null)} className={styles.breakdownClose}>×</button>
                          </div>
                          <div className={styles.breakdownContent}>
                            {/* Quality */}
                            <div className={styles.breakdownSection}>
                              <div className={styles.breakdownSectionHeader}>
                                <span>Quality & Credibility</span>
                                <span className={styles.breakdownSectionScore}>{breakdown.quality.score}/{breakdown.quality.max}</span>
                              </div>
                              {breakdown.quality.details.map((d, i) => (
                                <div key={i} className={styles.breakdownRow}>
                                  <span className={styles.breakdownLabel}>{d.name}</span>
                                  <span className={styles.breakdownValue}>{d.value}</span>
                                  <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                                  {d.note && <span className={styles.breakdownNote}>{d.note}</span>}
                                </div>
                              ))}
                            </div>
                            {/* Risk-Adjusted */}
                            <div className={styles.breakdownSection}>
                              <div className={styles.breakdownSectionHeader}>
                                <span>Risk-Adjusted Performance</span>
                                <span className={styles.breakdownSectionScore}>{breakdown.riskAdjusted.score}/{breakdown.riskAdjusted.max}</span>
                              </div>
                              {breakdown.riskAdjusted.details.map((d, i) => (
                                <div key={i} className={styles.breakdownRow}>
                                  <span className={styles.breakdownLabel}>{d.name}</span>
                                  <span className={styles.breakdownValue}>{d.value}</span>
                                  <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                                  {d.note && <span className={styles.breakdownNote}>{d.note}</span>}
                                </div>
                              ))}
                            </div>
                            {/* Returns */}
                            <div className={styles.breakdownSection}>
                              <div className={styles.breakdownSectionHeader}>
                                <span>Absolute Returns</span>
                                <span className={styles.breakdownSectionScore}>{breakdown.returns.score}/{breakdown.returns.max}</span>
                              </div>
                              {breakdown.returns.details.map((d, i) => (
                                <div key={i} className={styles.breakdownRow}>
                                  <span className={styles.breakdownLabel}>{d.name}</span>
                                  <span className={styles.breakdownValue}>{d.value}</span>
                                  <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                                  {d.note && <span className={styles.breakdownNote}>{d.note}</span>}
                                </div>
                              ))}
                            </div>
                            {/* Cost */}
                            <div className={styles.breakdownSection}>
                              <div className={styles.breakdownSectionHeader}>
                                <span>Cost Efficiency</span>
                                <span className={styles.breakdownSectionScore}>{breakdown.cost.score}/{breakdown.cost.max}</span>
                              </div>
                              {breakdown.cost.details.map((d, i) => (
                                <div key={i} className={styles.breakdownRow}>
                                  <span className={styles.breakdownLabel}>{d.name}</span>
                                  <span className={styles.breakdownValue}>{d.value}</span>
                                  <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                                  {d.note && <span className={styles.breakdownNote}>{d.note}</span>}
                                </div>
                              ))}
                            </div>
                            {/* User Fit */}
                            <div className={styles.breakdownSection}>
                              <div className={styles.breakdownSectionHeader}>
                                <span>Strategic Fit</span>
                                <span className={styles.breakdownSectionScore}>{breakdown.strategicFit.score}/{breakdown.strategicFit.max}</span>
                              </div>
                              {breakdown.strategicFit.details.map((d, i) => (
                                <div key={i} className={styles.breakdownRow}>
                                  <span className={styles.breakdownLabel}>{d.name}</span>
                                  <span className={styles.breakdownValue}>{d.value}</span>
                                  <span className={styles.breakdownPoints}>{d.points}/{d.max}</span>
                                  {d.note && <span className={styles.breakdownNote}>{d.note}</span>}
                                </div>
                              ))}
                            </div>
                            {/* Summary */}
                            <div className={styles.breakdownSummary}>
                              {breakdown.summary}
                            </div>
                            
                            {/* Warnings */}
                            {breakdown.warnings.length > 0 ? (
                              <div className={styles.breakdownWarnings}>
                                <div className={styles.breakdownWarningsHeader}>
                                  <span>⚠️</span>
                                  <span>Warnings ({breakdown.warnings.length})</span>
                                </div>
                                {breakdown.warnings.map((warning, i) => (
                                  <div key={i} className={styles.warningItem}>
                                    <span className={styles.warningIcon}>•</span>
                                    <span className={styles.warningText}>{warning.text}</span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className={styles.noWarnings}>
                                <span className={styles.checkIcon}>✓</span>
                                <span>No warnings - passes all quality checks</span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </td>
                  <td className={styles.fundName}>
                    <span 
                      title={fund.scheme_name}
                      className={styles.fundNameClickable}
                      onClick={() => handleOpenFundDetails(fund)}
                    >
                      {getCompactFundName(fund.scheme_name)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.categoryBadge}>{fund.fund_category || '-'}</span>
                  </td>
                  <td>{formatAUMShort(fund.aum)}</td>
                  <td>{fund.expense_ratio ? `${fund.expense_ratio.toFixed(2)}%` : '-'}</td>
                  <td className={fund.return_1y && fund.return_1y > 0 ? styles.profit : fund.return_1y && fund.return_1y < 0 ? styles.loss : ''}>
                    {formatPercent(fund.return_1y)}
                  </td>
                  <td className={fund.return_3y && fund.return_3y > 0 ? styles.profit : fund.return_3y && fund.return_3y < 0 ? styles.loss : ''}>
                    {formatPercent(fund.return_3y)}
                  </td>
                  <td className={fund.return_5y && fund.return_5y > 0 ? styles.profit : fund.return_5y && fund.return_5y < 0 ? styles.loss : ''}>
                    {formatPercent(fund.return_5y)}
                  </td>
                  <td>{fund.volatility ? `${Math.round(fund.volatility)}%` : '-'}</td>
                  <td>{fund.sharpe_ratio ? fund.sharpe_ratio.toFixed(2) : '-'}</td>
                  <td>{fund.beta ? fund.beta.toFixed(2) : '-'}</td>
                  <td className={fund.alpha && fund.alpha > 0 ? styles.profit : fund.alpha && fund.alpha < 0 ? styles.loss : ''}>
                    {fund.alpha ? `${Math.round(fund.alpha)}%` : '-'}
                  </td>
                  <td>
                    {fund.value_research_rating ? (
                      <span className={styles.ratingStars}>
                        {'★'.repeat(fund.value_research_rating)}
                        {'☆'.repeat(5 - fund.value_research_rating)}
                      </span>
                    ) : '-'}
                  </td>
                  <td>
                    <span className={styles.taxBadge}>
                      {getTaxClassification(fund.fund_category)}
                    </span>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
        </div>
      )}

      {/* Fund Details Modal */}
      {showFundDetailsModal && selectedFund && (
        <FundDetailsModal
          fund={selectedFund}
          isOpen={showFundDetailsModal}
          onClose={() => {
            setShowFundDetailsModal(false)
            setSelectedFund(null)
          }}
          onUpdate={(updatedFund) => {
            // Update the fund in the local state
            setFunds(funds.map(f => f.id === updatedFund.id ? updatedFund : f))
            setSelectedFund(updatedFund)
          }}
        />
      )}
    </div>
  )
}

// Fund Details Modal Component
function FundDetailsModal({ fund, isOpen, onClose, onUpdate }: { fund: any, isOpen: boolean, onClose: () => void, onUpdate?: (updatedFund: any) => void }) {
  // Import getAuthHeaders from parent scope or define locally
  const getAuthHeaders = () => {
    const token = localStorage.getItem('token')
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }
  const [isEditing, setIsEditing] = useState(false)
  const [editedData, setEditedData] = useState({
    aum: fund.aum || '',
    expense_ratio: fund.expense_ratio || '',
    beta: fund.beta || '',
    alpha: fund.alpha || '',
    value_research_rating: fund.value_research_rating || '',
    exit_load: fund.exit_load || '',
  })
  const [saving, setSaving] = useState(false)

  if (!isOpen) return null

  const handleSave = async () => {
    setSaving(true)
    try {
      const response = await fetch(`/api/v1/india-investments/mf-research/fund/${fund.scheme_code}`, {
        method: 'PATCH',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          aum: editedData.aum ? parseFloat(editedData.aum.toString()) : null,
          expense_ratio: editedData.expense_ratio ? parseFloat(editedData.expense_ratio.toString()) : null,
          beta: editedData.beta ? parseFloat(editedData.beta.toString()) : null,
          alpha: editedData.alpha ? parseFloat(editedData.alpha.toString()) : null,
          value_research_rating: editedData.value_research_rating ? parseInt(editedData.value_research_rating.toString()) : null,
          exit_load: editedData.exit_load || null,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to update fund data')
      }

      const updated = await response.json()
      setIsEditing(false)
      if (onUpdate) {
        onUpdate(updated)
      }
    } catch (error) {
      console.error('Error saving fund data:', error)
      alert('Failed to save changes. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.fundDetailsModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <h2>{fund.scheme_name}</h2>
            <p className={styles.modalSubtitle}>{fund.fund_house} · {fund.fund_category}</p>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {!isEditing ? (
              <button onClick={() => setIsEditing(true)} className={styles.editButton}>
                Edit
              </button>
            ) : (
              <>
                <button onClick={handleSave} className={styles.saveButton} disabled={saving}>
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={() => {
                  setIsEditing(false)
                  setEditedData({
                    aum: fund.aum || '',
                    expense_ratio: fund.expense_ratio || '',
                    beta: fund.beta || '',
                    alpha: fund.alpha || '',
                    value_research_rating: fund.value_research_rating || '',
                    exit_load: fund.exit_load || '',
                  })
                }} className={styles.cancelButton}>
                  Cancel
                </button>
              </>
            )}
            <button onClick={onClose} className={styles.modalClose}>×</button>
          </div>
        </div>
        
        <div className={styles.modalContent}>
          <div className={styles.modalSection}>
            <h3>Basic Information</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Fund Name</span>
                <span className={styles.modalValue}>{fund.scheme_name}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Category</span>
                <span className={styles.modalValue}>{fund.fund_category || '-'}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Fund House</span>
                <span className={styles.modalValue}>{fund.fund_house || '-'}</span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Current NAV</span>
                <span className={styles.modalValue}>
                  {fund.current_nav ? formatCurrencyINR(fund.current_nav) : '-'}
                </span>
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Size & Costs</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>AUM (₹Cr)</span>
                {isEditing ? (
                  <input
                    type="number"
                    value={editedData.aum}
                    onChange={(e) => setEditedData({ ...editedData, aum: e.target.value })}
                    placeholder="Enter AUM in crores"
                    className={styles.modalInput}
                  />
                ) : (
                  <span className={styles.modalValue}>
                    {fund.aum ? `${fund.aum.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr` : '-'}
                  </span>
                )}
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Expense Ratio (%)</span>
                {isEditing ? (
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.expense_ratio}
                    onChange={(e) => setEditedData({ ...editedData, expense_ratio: e.target.value })}
                    placeholder="e.g., 1.25"
                    className={styles.modalInput}
                  />
                ) : (
                  <span className={styles.modalValue}>
                    {fund.expense_ratio ? `${fund.expense_ratio.toFixed(2)}%` : '-'}
                  </span>
                )}
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Exit Load</span>
                {isEditing ? (
                  <input
                    type="text"
                    value={editedData.exit_load}
                    onChange={(e) => setEditedData({ ...editedData, exit_load: e.target.value })}
                    placeholder="e.g., 1% if redeemed within 1 year"
                    className={styles.modalInput}
                  />
                ) : (
                  <span className={styles.modalValue}>{fund.exit_load || '-'}</span>
                )}
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Returns (Annualized %)</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>1 Year</span>
                <span className={`${styles.modalValue} ${fund.return_1y && fund.return_1y > 0 ? styles.profit : ''}`}>
                  {fund.return_1y ? `${fund.return_1y.toFixed(2)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>3 Year CAGR</span>
                <span className={`${styles.modalValue} ${fund.return_3y && fund.return_3y > 0 ? styles.profit : ''}`}>
                  {fund.return_3y ? `${fund.return_3y.toFixed(2)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>5 Year CAGR</span>
                <span className={`${styles.modalValue} ${fund.return_5y && fund.return_5y > 0 ? styles.profit : ''}`}>
                  {fund.return_5y ? `${fund.return_5y.toFixed(2)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>10 Year CAGR</span>
                <span className={`${styles.modalValue} ${fund.return_10y && fund.return_10y > 0 ? styles.profit : ''}`}>
                  {fund.return_10y ? `${fund.return_10y.toFixed(2)}%` : '-'}
                </span>
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Risk Metrics</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Standard Deviation</span>
                <span className={styles.modalValue}>
                  {fund.volatility ? `${fund.volatility.toFixed(2)}%` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Sharpe Ratio</span>
                <span className={styles.modalValue}>
                  {fund.sharpe_ratio ? fund.sharpe_ratio.toFixed(2) : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Beta</span>
                {isEditing ? (
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.beta}
                    onChange={(e) => setEditedData({ ...editedData, beta: e.target.value })}
                    placeholder="e.g., 0.95"
                    className={styles.modalInput}
                  />
                ) : (
                  <span className={styles.modalValue}>
                    {fund.beta ? fund.beta.toFixed(2) : '-'}
                  </span>
                )}
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Alpha (%)</span>
                {isEditing ? (
                  <input
                    type="number"
                    step="0.01"
                    value={editedData.alpha}
                    onChange={(e) => setEditedData({ ...editedData, alpha: e.target.value })}
                    placeholder="e.g., 2.5"
                    className={styles.modalInput}
                  />
                ) : (
                  <span className={styles.modalValue}>
                    {fund.alpha ? `${fund.alpha.toFixed(2)}%` : '-'}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Ratings</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Value Research Rating</span>
                {isEditing ? (
                  <select
                    value={editedData.value_research_rating}
                    onChange={(e) => setEditedData({ ...editedData, value_research_rating: e.target.value })}
                    className={styles.modalInput}
                  >
                    <option value="">Not Rated</option>
                    <option value="1">1 Star</option>
                    <option value="2">2 Stars</option>
                    <option value="3">3 Stars</option>
                    <option value="4">4 Stars</option>
                    <option value="5">5 Stars</option>
                  </select>
                ) : (
                  <span className={styles.modalValue}>
                    {fund.value_research_rating ? (
                      <span className={styles.ratingStars}>
                        {'★'.repeat(fund.value_research_rating)}
                        {'☆'.repeat(5 - fund.value_research_rating)}
                      </span>
                    ) : '-'}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className={styles.modalSection}>
            <h3>Recommendation</h3>
            <div className={styles.modalGrid}>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Score</span>
                <span className={styles.modalValue}>
                  {fund.recommendation_score ? fund.recommendation_score.toFixed(1) : '-'}
                </span>
              </div>
              <div className={styles.modalMetric}>
                <span className={styles.modalLabel}>Rank</span>
                <span className={styles.modalValue}>
                  {fund.recommendation_rank ? `#${fund.recommendation_rank}` : '-'}
                </span>
              </div>
              <div className={styles.modalMetric} style={{ gridColumn: '1 / -1' }}>
                <span className={styles.modalLabel}>Reason</span>
                <span className={styles.modalValue}>{fund.recommendation_reason || '-'}</span>
              </div>
            </div>
          </div>

          <div className={styles.modalFooter}>
            <p className={styles.modalNote}>
              Note: Additional metrics (portfolio composition, benchmark comparison, ratings, etc.) 
              will be available once we integrate AMFI data and benchmark indices.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}


