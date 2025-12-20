import { useState, useEffect, useCallback } from 'react'
import {
  Building2,
  TrendingUp,
  TrendingDown,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  BadgeCheck,
  Clock,
  Coins,
  FileText,
  ChevronRight,
  DollarSign,
  Check,
  Pencil,
} from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './Equity.module.css'
import clsx from 'clsx'

const API_BASE = '/api/v1'

// Types
interface CompanyHolding {
  id: number
  name: string
  status: string
  current_fmv: number | null
  fmv_date: string | null
  qsbs_eligible: boolean
  total_options: number
  vested_options: number
  exercised_options: number
  total_shares: number
  total_rsas: number
  safe_principal: number
  estimated_value: number
}

interface Grant {
  id: number
  grant_id: string
  grant_type: 'ISO' | 'NSO'
  grant_date: string | null
  total_options: number
  vested_options: number
  exercised_options: number
  unvested_options: number
  exercisable_options: number
  exercise_price: number | null
  status: string
  expiration_date: string | null
}

interface ShareHolding {
  id: number
  certificate_id: string
  share_type: string
  num_shares: number
  acquisition_date: string | null
  cost_basis_per_share: number | null
  source: string
  status: string
}

interface RSA {
  id: number
  rsa_id: string
  total_shares: number
  vested_shares: number
  grant_date: string | null
  status: string
  election_83b_filed: boolean
}

interface SAFE {
  id: number
  safe_id: string
  principal_amount: number
  investment_date: string | null
  valuation_cap: number | null
  discount_rate: number | null
  status: string
}

interface CompanyDetail {
  company: {
    id: number
    name: string
    dba_name: string | null
    status: string
    current_fmv: number | null
    fmv_date: string | null
    qsbs_eligible: boolean
    qsbs_notes: string | null
    notes: string | null
  }
  grants: Grant[]
  shares: ShareHolding[]
  rsas: RSA[]
  safes: SAFE[]
}

interface EquitySummary {
  total_estimated_value: number
  total_cost_basis: number
  total_unrealized_gain: number
  num_companies: number
  holdings_by_company: CompanyHolding[]
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

const formatNumber = (value: number) => {
  return new Intl.NumberFormat('en-US').format(value)
}

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const statusColors: Record<string, string> = {
    active: 'var(--color-positive)',
    terminated: 'var(--color-warning)',
    expired: 'var(--color-negative)',
    held: 'var(--color-positive)',
    canceled: 'var(--color-text-tertiary)',
    outstanding: 'var(--color-accent)',
    fully_vested: 'var(--color-positive)',
  }

  return (
    <span
      className={styles.statusBadge}
      style={{ background: `${statusColors[status] || 'var(--color-text-tertiary)'}20`, color: statusColors[status] || 'var(--color-text-tertiary)' }}
    >
      {status.replace('_', ' ')}
    </span>
  )
}

// Company Card Component
function CompanyCard({
  company,
  onClick,
  delay,
}: {
  company: CompanyHolding
  onClick: () => void
  delay: number
}) {
  const hasValue = company.estimated_value > 0
  const exercisable = company.vested_options - company.exercised_options

  return (
    <button
      className={styles.companyCard}
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={styles.companyHeader}>
        <div className={styles.companyIcon}>
          <Building2 size={24} />
        </div>
        <div className={styles.companyInfo}>
          <h3 className={styles.companyName}>{company.name}</h3>
          <div className={styles.companyTags}>
            {company.qsbs_eligible && (
              <span className={styles.qsbsBadge}>
                <BadgeCheck size={14} />
                QSBS
              </span>
            )}
            {company.current_fmv && (
              <span className={styles.fmvBadge}>
                FMV: {formatCurrencyPrecise(company.current_fmv)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className={styles.companyMetrics}>
        {company.total_options > 0 && (
          <div className={styles.metric}>
            <span className={styles.metricLabel}>Options</span>
            <span className={styles.metricValue}>{formatNumber(company.total_options)}</span>
            {exercisable > 0 && (
              <span className={styles.metricSub}>{formatNumber(exercisable)} exercisable</span>
            )}
          </div>
        )}
        {company.total_shares > 0 && (
          <div className={styles.metric}>
            <span className={styles.metricLabel}>Shares</span>
            <span className={styles.metricValue}>{formatNumber(company.total_shares)}</span>
          </div>
        )}
        {company.total_rsas > 0 && (
          <div className={styles.metric}>
            <span className={styles.metricLabel}>RSAs</span>
            <span className={styles.metricValue}>{formatNumber(company.total_rsas)}</span>
          </div>
        )}
        {company.safe_principal > 0 && (
          <div className={styles.metric}>
            <span className={styles.metricLabel}>SAFE</span>
            <span className={styles.metricValue}>{formatCurrency(company.safe_principal)}</span>
          </div>
        )}
      </div>

      {hasValue && (
        <div className={styles.companyValue}>
          <span className={styles.valueLabel}>Estimated Value</span>
          <span className={styles.valueAmount}>{formatCurrency(company.estimated_value)}</span>
        </div>
      )}

      <div className={styles.viewDetails}>
        View Details <ChevronRight size={16} />
      </div>
    </button>
  )
}

// Grants Table
function GrantsTable({ grants }: { grants: Grant[] }) {
  if (grants.length === 0) return null

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>
        <Coins size={20} />
        Stock Options ({grants.length})
      </h3>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Grant ID</th>
              <th>Type</th>
              <th>Grant Date</th>
              <th className={styles.alignRight}>Total</th>
              <th className={styles.alignRight}>Vested</th>
              <th className={styles.alignRight}>Exercised</th>
              <th className={styles.alignRight}>Exercisable</th>
              <th className={styles.alignRight}>Strike Price</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {grants.map((grant) => (
              <tr key={grant.id} className={styles.tableRow}>
                <td className={styles.grantId}>{grant.grant_id || '—'}</td>
                <td>
                  <span className={clsx(styles.typeBadge, grant.grant_type === 'ISO' ? styles.iso : styles.nso)}>
                    {grant.grant_type}
                  </span>
                </td>
                <td className={styles.date}>{formatDate(grant.grant_date)}</td>
                <td className={styles.alignRight}>{formatNumber(grant.total_options)}</td>
                <td className={styles.alignRight}>{formatNumber(grant.vested_options)}</td>
                <td className={styles.alignRight}>{formatNumber(grant.exercised_options)}</td>
                <td className={clsx(styles.alignRight, styles.highlight)}>
                  {formatNumber(grant.exercisable_options)}
                </td>
                <td className={styles.alignRight}>
                  {grant.exercise_price ? formatCurrencyPrecise(grant.exercise_price) : '—'}
                </td>
                <td><StatusBadge status={grant.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Shares Table
function SharesTable({ shares }: { shares: ShareHolding[] }) {
  if (shares.length === 0) return null

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>
        <FileText size={20} />
        Shares ({shares.length})
      </h3>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Certificate</th>
              <th>Type</th>
              <th>Acquired</th>
              <th className={styles.alignRight}>Shares</th>
              <th className={styles.alignRight}>Cost Basis</th>
              <th>Source</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {shares.map((share) => (
              <tr key={share.id} className={styles.tableRow}>
                <td className={styles.certId}>{share.certificate_id || '—'}</td>
                <td className={styles.shareType}>{share.share_type}</td>
                <td className={styles.date}>{formatDate(share.acquisition_date)}</td>
                <td className={clsx(styles.alignRight, styles.highlight)}>
                  {formatNumber(share.num_shares)}
                </td>
                <td className={styles.alignRight}>
                  {share.cost_basis_per_share ? formatCurrencyPrecise(share.cost_basis_per_share) : '—'}
                </td>
                <td>{share.source || '—'}</td>
                <td><StatusBadge status={share.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// RSAs Section
function RSAsSection({ rsas }: { rsas: RSA[] }) {
  if (rsas.length === 0) return null

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>
        <Clock size={20} />
        Restricted Stock Awards ({rsas.length})
      </h3>
      <div className={styles.rsaGrid}>
        {rsas.map((rsa) => (
          <div key={rsa.id} className={styles.rsaCard}>
            <div className={styles.rsaHeader}>
              <span className={styles.rsaId}>{rsa.rsa_id || 'RSA'}</span>
              <StatusBadge status={rsa.status} />
            </div>
            <div className={styles.rsaStats}>
              <div className={styles.rsaStat}>
                <span className={styles.rsaStatLabel}>Total</span>
                <span className={styles.rsaStatValue}>{formatNumber(rsa.total_shares)}</span>
              </div>
              <div className={styles.rsaStat}>
                <span className={styles.rsaStatLabel}>Vested</span>
                <span className={styles.rsaStatValue}>{formatNumber(rsa.vested_shares)}</span>
              </div>
            </div>
            {rsa.election_83b_filed && (
              <div className={styles.rsa83b}>
                <BadgeCheck size={14} />
                83(b) Filed
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// SAFEs Section
function SAFEsSection({ safes }: { safes: SAFE[] }) {
  if (safes.length === 0) return null

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>
        <FileText size={20} />
        SAFE Investments ({safes.length})
      </h3>
      <div className={styles.safeGrid}>
        {safes.map((safe) => (
          <div key={safe.id} className={styles.safeCard}>
            <div className={styles.safeHeader}>
              <span className={styles.safeId}>{safe.safe_id || 'SAFE'}</span>
              <StatusBadge status={safe.status} />
            </div>
            <div className={styles.safePrincipal}>
              {formatCurrency(safe.principal_amount)}
            </div>
            <div className={styles.safeDetails}>
              {safe.investment_date && (
                <span>Invested: {formatDate(safe.investment_date)}</span>
              )}
              {safe.valuation_cap && (
                <span>Cap: {formatCurrency(safe.valuation_cap)}</span>
              )}
              {safe.discount_rate && (
                <span>Discount: {safe.discount_rate}%</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Empty State
function EmptyState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={styles.emptyState}>
      <Building2 size={48} />
      <h3>No Equity Holdings</h3>
      <p>No startup equity found. Add your Carta data to get started.</p>
      <button onClick={onRefresh} className={styles.refreshButton}>
        <RefreshCw size={18} />
        Refresh Data
      </button>
    </div>
  )
}

// Equity Calculator Row Component
function EquityCalculatorRow({
  company,
  localFmv,
  localStrikePrice,
  onFmvUpdate,
  onStrikePriceUpdate,
}: {
  company: CompanyHolding
  localFmv: number | null
  localStrikePrice: number | null
  onFmvUpdate: (companyId: number, fmv: number | null) => void
  onStrikePriceUpdate: (companyId: number, strikePrice: number | null) => void
}) {
  const [editingFmv, setEditingFmv] = useState(false)
  const [editingStrike, setEditingStrike] = useState(false)
  const [fmvInput, setFmvInput] = useState(localFmv?.toString() || '')
  const [strikeInput, setStrikeInput] = useState(localStrikePrice?.toString() || '')
  const [savingFmv, setSavingFmv] = useState(false)

  const currentFmv = localFmv ?? company.current_fmv
  const exercisableOptions = company.vested_options - company.exercised_options

  // Calculate values
  const sharesValue = currentFmv && company.total_shares > 0 
    ? company.total_shares * currentFmv 
    : 0
  
  // Options spread value: (FMV - Strike) * exercisable options (only if in-the-money)
  const optionsSpread = currentFmv && localStrikePrice !== null && exercisableOptions > 0
    ? Math.max(0, (currentFmv - localStrikePrice) * exercisableOptions)
    : 0

  const totalValue = sharesValue + optionsSpread

  const handleFmvSave = async () => {
    setSavingFmv(true)
    const newFmv = fmvInput ? parseFloat(fmvInput) : null
    
    try {
      const response = await fetch(`${API_BASE}/equity/companies/${company.id}`, {
        method: 'PUT',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_fmv: newFmv,
          fmv_date: newFmv ? new Date().toISOString().split('T')[0] : null,
        }),
      })

      if (response.ok) {
        onFmvUpdate(company.id, newFmv)
        setEditingFmv(false)
      }
    } catch (err) {
      console.error('Error updating FMV:', err)
    } finally {
      setSavingFmv(false)
    }
  }

  const handleStrikeSave = () => {
    const newStrike = strikeInput ? parseFloat(strikeInput) : null
    onStrikePriceUpdate(company.id, newStrike)
    setEditingStrike(false)
  }

  return (
    <div className={styles.calcRow}>
      <div className={styles.calcCompany}>
        <span className={styles.calcCompanyName}>{company.name}</span>
        {company.qsbs_eligible && (
          <span className={styles.calcQsbs}>QSBS</span>
        )}
      </div>
      
      {/* Shares */}
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Shares</span>
        <span className={styles.calcNumber}>{formatNumber(company.total_shares)}</span>
      </div>
      
      {/* Options */}
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Options</span>
        <span className={styles.calcNumber}>
          {exercisableOptions > 0 ? formatNumber(exercisableOptions) : '—'}
        </span>
        {exercisableOptions > 0 && (
          <span className={styles.calcSub}>exercisable</span>
        )}
      </div>
      
      {/* FMV Input */}
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>FMV/Share</span>
        {editingFmv ? (
          <div className={styles.calcInputGroup}>
            <span className={styles.calcDollar}>$</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={fmvInput}
              onChange={(e) => setFmvInput(e.target.value)}
              className={styles.calcInput}
              placeholder="0.00"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleFmvSave()}
            />
            <button onClick={handleFmvSave} disabled={savingFmv} className={styles.calcSaveBtn}>
              {savingFmv ? <RefreshCw size={12} className={styles.spinner} /> : <Check size={12} />}
            </button>
          </div>
        ) : (
          <button
            onClick={() => { setFmvInput(currentFmv?.toString() || ''); setEditingFmv(true) }}
            className={styles.calcEditBtn}
          >
            {currentFmv ? formatCurrencyPrecise(currentFmv) : 'Set'} <Pencil size={10} />
          </button>
        )}
      </div>
      
      {/* Strike Price Input (only if has options) */}
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Strike Price</span>
        {exercisableOptions > 0 ? (
          editingStrike ? (
            <div className={styles.calcInputGroup}>
              <span className={styles.calcDollar}>$</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={strikeInput}
                onChange={(e) => setStrikeInput(e.target.value)}
                className={styles.calcInput}
                placeholder="0.00"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleStrikeSave()}
              />
              <button onClick={handleStrikeSave} className={styles.calcSaveBtn}>
                <Check size={12} />
              </button>
            </div>
          ) : (
            <button
              onClick={() => { setStrikeInput(localStrikePrice?.toString() || ''); setEditingStrike(true) }}
              className={styles.calcEditBtn}
            >
              {localStrikePrice !== null ? formatCurrencyPrecise(localStrikePrice) : 'Set'} <Pencil size={10} />
            </button>
          )
        ) : (
          <span className={styles.calcNumber}>—</span>
        )}
      </div>
      
      {/* Calculated Values */}
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Shares Value</span>
        <span className={styles.calcValue}>{sharesValue > 0 ? formatCurrency(sharesValue) : '—'}</span>
      </div>
      
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Options Value</span>
        <span className={styles.calcValue}>{optionsSpread > 0 ? formatCurrency(optionsSpread) : '—'}</span>
      </div>
      
      <div className={styles.calcCell}>
        <span className={styles.calcLabel}>Total</span>
        <span className={styles.calcTotal}>{totalValue > 0 ? formatCurrency(totalValue) : '—'}</span>
      </div>
    </div>
  )
}

// Main Component
export function Equity() {
  const [summary, setSummary] = useState<EquitySummary | null>(null)
  const [selectedCompany, setSelectedCompany] = useState<CompanyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [localFmvs, setLocalFmvs] = useState<Record<number, number | null>>({})
  const [localStrikePrices, setLocalStrikePrices] = useState<Record<number, number | null>>({})

  // Calculate total portfolio value based on local inputs
  const calculateTotalValue = useCallback((holdings: CompanyHolding[]) => {
    return holdings.reduce((total, company) => {
      const fmv = localFmvs[company.id] ?? company.current_fmv
      const strikePrice = localStrikePrices[company.id] ?? null
      const exercisable = company.vested_options - company.exercised_options
      
      const sharesValue = fmv && company.total_shares > 0 ? company.total_shares * fmv : 0
      const optionsValue = fmv && strikePrice !== null && exercisable > 0
        ? Math.max(0, (fmv - strikePrice) * exercisable)
        : 0
      
      return total + sharesValue + optionsValue
    }, 0)
  }, [localFmvs, localStrikePrices])

  // Handle FMV update from editor
  const handleFmvUpdate = useCallback((companyId: number, fmv: number | null) => {
    setLocalFmvs(prev => ({ ...prev, [companyId]: fmv }))
    // Update the summary data with new FMV
    setSummary(prev => {
      if (!prev) return prev
      const updatedHoldings = prev.holdings_by_company.map(company => {
        if (company.id === companyId) {
          return {
            ...company,
            current_fmv: fmv,
          }
        }
        return company
      })
      return {
        ...prev,
        holdings_by_company: updatedHoldings,
      }
    })
  }, [])

  // Handle strike price update (local only, not saved to DB)
  const handleStrikePriceUpdate = useCallback((companyId: number, strikePrice: number | null) => {
    setLocalStrikePrices(prev => ({ ...prev, [companyId]: strikePrice }))
  }, [])

  const fetchSummary = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/equity/summary`, {
        headers: getAuthHeaders(),
      })

      if (!response.ok) {
        throw new Error('Failed to fetch equity summary')
      }

      const data = await response.json()
      setSummary(data)
    } catch (err) {
      console.error('Error fetching equity:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const fetchCompanyDetail = async (companyId: number) => {
    try {
      const response = await fetch(`${API_BASE}/equity/companies/${companyId}`, {
        headers: getAuthHeaders(),
      })

      if (!response.ok) {
        throw new Error('Failed to fetch company details')
      }

      const data = await response.json()
      setSelectedCompany(data)
    } catch (err) {
      console.error('Error fetching company:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    }
  }

  useEffect(() => {
    fetchSummary()
  }, [])

  // Loading state
  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading equity holdings...</p>
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
          <button onClick={fetchSummary} className={styles.refreshButton}>
            <RefreshCw size={18} />
            Try Again
          </button>
        </div>
      </div>
    )
  }

  // Detail View
  if (selectedCompany) {
    const company = selectedCompany.company
    const hasGrants = selectedCompany.grants.length > 0
    const hasShares = selectedCompany.shares.length > 0
    const hasRSAs = selectedCompany.rsas.length > 0
    const hasSAFEs = selectedCompany.safes.length > 0

    // Calculate totals
    const totalShares = selectedCompany.shares
      .filter(s => s.status === 'held')
      .reduce((sum, s) => sum + s.num_shares, 0)
    const totalOptions = selectedCompany.grants.reduce((sum, g) => sum + g.total_options, 0)
    const exercisableOptions = selectedCompany.grants.reduce((sum, g) => sum + g.exercisable_options, 0)
    const estimatedValue = company.current_fmv
      ? totalShares * company.current_fmv
      : 0

    return (
      <div className={styles.page}>
        <button
          className={styles.backButton}
          onClick={() => setSelectedCompany(null)}
        >
          <ArrowLeft size={20} />
          Back to Equity
        </button>

        <div className={styles.detailHeader}>
          <div className={styles.detailIcon}>
            <Building2 size={32} />
          </div>
          <div className={styles.detailInfo}>
            <h1>{company.dba_name || company.name}</h1>
            {company.dba_name && (
              <span className={styles.legalName}>{company.name}</span>
            )}
            <div className={styles.detailTags}>
              {company.qsbs_eligible && (
                <span className={styles.qsbsBadge}>
                  <BadgeCheck size={14} />
                  QSBS Eligible
                </span>
              )}
              {company.current_fmv && (
                <span className={styles.fmvBadge}>
                  FMV: {formatCurrencyPrecise(company.current_fmv)}
                  {company.fmv_date && ` (${formatDate(company.fmv_date)})`}
                </span>
              )}
            </div>
          </div>
          <div className={styles.detailValue}>
            <div className={styles.detailStats}>
              {totalOptions > 0 && (
                <div className={styles.detailStat}>
                  <span className={styles.detailStatLabel}>Total Options</span>
                  <span className={styles.detailStatValue}>{formatNumber(totalOptions)}</span>
                </div>
              )}
              {totalShares > 0 && (
                <div className={styles.detailStat}>
                  <span className={styles.detailStatLabel}>Shares Held</span>
                  <span className={styles.detailStatValue}>{formatNumber(totalShares)}</span>
                </div>
              )}
            </div>
            {estimatedValue > 0 && (
              <div className={styles.detailEstimate}>
                <span className={styles.estimateLabel}>Estimated Value</span>
                <span className={styles.estimateValue}>{formatCurrency(estimatedValue)}</span>
              </div>
            )}
          </div>
        </div>

        {company.qsbs_notes && (
          <div className={styles.qsbsNote}>
            <BadgeCheck size={18} />
            <span>{company.qsbs_notes}</span>
          </div>
        )}

        {hasGrants && <GrantsTable grants={selectedCompany.grants} />}
        {hasShares && <SharesTable shares={selectedCompany.shares} />}
        {hasRSAs && <RSAsSection rsas={selectedCompany.rsas} />}
        {hasSAFEs && <SAFEsSection safes={selectedCompany.safes} />}
      </div>
    )
  }

  // Empty state
  if (!summary || summary.num_companies === 0) {
    return (
      <div className={styles.page}>
        <EmptyState onRefresh={fetchSummary} />
      </div>
    )
  }

  // Main View - use calculator's total for consistency
  const calculatedTotal = calculateTotalValue(summary.holdings_by_company)

  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>Startup Equity Holdings</div>
          <div className={styles.heroValue}>{formatCurrency(calculatedTotal)}</div>
          <div className={styles.heroSubtext}>
            {summary.num_companies} companies · {formatNumber(
              summary.holdings_by_company.reduce((sum, c) => sum + c.total_shares, 0)
            )} shares held
          </div>
        </div>
        <button onClick={fetchSummary} className={styles.heroRefresh} title="Refresh data">
          <RefreshCw size={20} />
        </button>
      </section>

      {/* Summary Stats */}
      <section className={styles.summaryStats}>
        <div className={styles.statCard}>
          <Building2 size={24} />
          <div className={styles.statContent}>
            <span className={styles.statValue}>{summary.num_companies}</span>
            <span className={styles.statLabel}>Companies</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <Coins size={24} />
          <div className={styles.statContent}>
            <span className={styles.statValue}>
              {formatNumber(
                summary.holdings_by_company.reduce((sum, c) => sum + c.total_options, 0)
              )}
            </span>
            <span className={styles.statLabel}>Total Options</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <FileText size={24} />
          <div className={styles.statContent}>
            <span className={styles.statValue}>
              {formatNumber(
                summary.holdings_by_company.reduce((sum, c) => sum + c.total_shares, 0)
              )}
            </span>
            <span className={styles.statLabel}>Total Shares</span>
          </div>
        </div>
      </section>

      {/* Equity Value Calculator */}
      <section className={styles.calculatorSection}>
        <div className={styles.calcHeader}>
          <h2>
            <DollarSign size={20} />
            Equity Value Calculator
          </h2>
          <p className={styles.calcSubtitle}>
            Enter FMV and strike prices to calculate your equity value
          </p>
        </div>
        <div className={styles.calcTable}>
          {summary.holdings_by_company.map((company) => (
            <EquityCalculatorRow
              key={company.id}
              company={company}
              localFmv={localFmvs[company.id] ?? null}
              localStrikePrice={localStrikePrices[company.id] ?? null}
              onFmvUpdate={handleFmvUpdate}
              onStrikePriceUpdate={handleStrikePriceUpdate}
            />
          ))}
          <div className={styles.calcTotalRow}>
            <span className={styles.calcTotalLabel}>Total Portfolio Value</span>
            <span className={styles.calcGrandTotal}>
              {formatCurrency(calculateTotalValue(summary.holdings_by_company))}
            </span>
          </div>
        </div>
      </section>

      {/* Company Cards */}
      <section className={styles.companiesSection}>
        <h2>Portfolio Companies ({summary.num_companies})</h2>
        <div className={styles.companiesGrid}>
          {summary.holdings_by_company.map((company, index) => (
            <CompanyCard
              key={company.id}
              company={company}
              onClick={() => fetchCompanyDetail(company.id)}
              delay={index * 50}
            />
          ))}
        </div>
      </section>
    </div>
  )
}

