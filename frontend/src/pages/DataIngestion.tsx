import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, CheckCircle, AlertCircle, FolderOpen, FileText, Clock, Clipboard, Send, ChevronDown, ChevronUp, TrendingUp, BarChart3, Eye, X, DollarSign } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './DataIngestion.module.css'
import clsx from 'clsx'

const API_BASE = '/api/v1'

interface InboxFolder {
  folder: string
  path: string
  pending_files: number
}

interface RefreshResult {
  success: boolean
  files_processed: number
  records_imported: number
  errors: string[]
  details: {
    folder: string
    files: string[]
    records: number
  }[]
  ingestion_ids?: number[]
}

interface ImportedTransaction {
  ingestion_id: number | null
  symbol: string
  transaction_date: string | null
  amount: number
  transaction_type: string
  description: string | null
}

interface FileSummary {
  ingestion_id: number
  file_name: string
  count: number
  total: number
}

type SortKey = 'symbol' | 'transaction_date' | 'amount' | 'transaction_type'
type SortDir = 'asc' | 'desc'

interface ParsedStock {
  symbol: string
  name: string
  shares: number
  market_value: number
  current_price: number
}

interface ParsedOption {
  symbol: string
  strike_price: number
  option_type: string
  expiration_date: string | null
  contracts: number
  current_premium: number | null
  original_premium: number | null
  gain_loss_percent: number | null
}

interface PreviewResult {
  success: boolean
  detected_format: string
  stocks_count: number
  options_count: number
  has_options_section?: boolean
  has_stocks_section?: boolean
  requires_confirmation?: boolean
  confirmation_message?: string
  stocks: ParsedStock[]
  options: ParsedOption[]
  warnings: string[]
}

interface StockCreatedDetail {
  symbol: string
  name: string
  shares: number
  price: number
  market_value: number
}

interface StockUpdatedDetail {
  symbol: string
  shares: number
  old_shares: number
  price: number
  old_price: number
  market_value: number
  old_market_value: number
}

interface StockRemovedDetail {
  symbol: string
  shares?: number
  last_price?: number
  market_value?: number
  warning?: string
}

interface OptionSavedDetail {
  symbol: string
  strike_price: number
  option_type: string
  expiration_date: string | null
  contracts: number
}

interface PendingOrderDetail {
  symbol: string
  order_type: string
  option_type: string | null
  strike_price: number | null
  contracts: number
  limit_price: number | null
}

interface SaveResult {
  success: boolean
  account_name: string
  stocks_saved: number
  stocks_updated: number
  stocks_removed: number
  options_saved: number
  pending_orders_saved: number
  snapshot_id: number | null
  detected_format: string
  stocks_created_details: StockCreatedDetail[]
  stocks_updated_details: StockUpdatedDetail[]
  stocks_removed_details: StockRemovedDetail[]
  options_saved_details: OptionSavedDetail[]
  pending_orders_details: PendingOrderDetail[]
}

interface AccountOption {
  account_id: string
  name: string
  last_updated: string | null
}

interface CashBreakdownResult {
  success: boolean
  format: 'brokerage' | 'ira'
  account_name: string
  cash: number | null
  margin_total: number | null
  margin_used: number | null
  options_collateral: number | null
  pending_orders: number | null
  net_total: number | null
  true_cash: number
}

// Account order matching Income and Investments pages
// Order: Neel's Brokerage → Neel's Retirement → Neel's Roth IRA → Jaya's Brokerage → Jaya's IRA → Jaya's Roth IRA → Alisha's Brokerage → Agrawal Family HSA
const ACCOUNT_ORDER: Record<string, number> = {
  "Neel's Brokerage": 1,
  "Neel's Retirement": 2,
  "Neel's Roth IRA": 3,
  "Jaya's Brokerage": 4,
  "Jaya's IRA": 5,
  "Jaya's Roth IRA": 6,
  "Alisha's Brokerage": 7,
  "Agrawal Family HSA": 8,
}

// All expected Robinhood accounts - shown even if no data exists yet
// This allows importing data for new accounts that haven't been set up
const ALL_ROBINHOOD_ACCOUNTS: AccountOption[] = [
  { account_id: "neel_brokerage", name: "Neel's Brokerage" },
  { account_id: "neel_retirement", name: "Neel's Retirement" },
  { account_id: "neel_roth_ira", name: "Neel's Roth IRA" },
  { account_id: "jaya_brokerage", name: "Jaya's Brokerage" },
  { account_id: "jaya_ira", name: "Jaya's IRA" },
  { account_id: "jaya_roth_ira", name: "Jaya's Roth IRA" },
  { account_id: "alisha_brokerage", name: "Alisha's Brokerage" },
  { account_id: "agrawal_hsa", name: "Agrawal Family HSA" },
]

const HIDDEN_ACCOUNTS = ['robinhood_default']

function CashBreakdownTable({ result }: { result: CashBreakdownResult }) {
  const fmtAmt = (v: number | null) =>
    v == null ? '—' : `$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  const isIra = result.format === 'ira'

  const rows: { label: string; value: number | null; note?: string }[] = isIra
    ? [
        { label: 'Total IRA cash',     value: result.margin_total,      note: 'all your money in this account' },
        { label: 'Options collateral', value: result.options_collateral, note: 'locked for puts — included above' },
        { label: 'Buying power',       value: result.net_total,          note: 'free to deploy' },
      ]
    : [
        { label: 'Free cash',          value: result.cash },
        { label: 'Margin credit line', value: result.margin_total },
        { label: 'Margin used',        value: result.margin_used,        note: 'borrowed — subtracted from true cash' },
        { label: 'Options collateral', value: result.options_collateral, note: 'your money, locked for puts' },
        { label: 'Pending orders',     value: result.pending_orders,     note: 'reserved for open orders' },
        { label: 'Net buying power',   value: result.net_total },
      ]

  const trueFormula = isIra ? 'buying power + collateral' : 'free + collateral + pending − margin'

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {isIra ? 'IRA account' : 'Brokerage / margin account'}
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
        <tbody>
          {rows.map(({ label, value, note }) => (
            <tr key={label} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <td style={{ padding: '6px 0', color: 'var(--color-text-secondary)' }}>{label}</td>
              <td style={{ padding: '6px 0', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtAmt(value)}</td>
              {note && <td style={{ padding: '6px 0 6px 12px', color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>{note}</td>}
              {!note && <td />}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ padding: '10px 0 4px', fontWeight: 600, color: 'var(--color-accent, #00D632)' }}>True cash</td>
            <td style={{ padding: '10px 0 4px', textAlign: 'right', fontWeight: 700, color: 'var(--color-accent, #00D632)', fontVariantNumeric: 'tabular-nums' }}>
              ${result.true_cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </td>
            <td style={{ padding: '10px 0 4px', fontSize: '0.8rem', color: 'var(--color-text-tertiary)', paddingLeft: 12 }}>
              {trueFormula}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export function DataIngestion() {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [inboxStatus, setInboxStatus] = useState<InboxFolder[] | null>(null)
  const [lastRefresh, setLastRefresh] = useState<RefreshResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Robinhood paste state
  const [pasteText, setPasteText] = useState('')
  const [robinhoodAccounts, setRobinhoodAccounts] = useState<AccountOption[]>([])
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null)
  const [saveResult, setSaveResult] = useState<SaveResult | null>(null)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [showPreviewDetails, setShowPreviewDetails] = useState(false)

  // Cash breakdown paste state
  const [cashPasteText, setCashPasteText] = useState('')
  const [cashSelectedAccount, setCashSelectedAccount] = useState<string>('')
  const [isCashPreviewing, setIsCashPreviewing] = useState(false)
  const [isCashSaving, setIsCashSaving] = useState(false)
  const [cashPreview, setCashPreview] = useState<CashBreakdownResult | null>(null)
  const [cashSaveResult, setCashSaveResult] = useState<CashBreakdownResult | null>(null)
  const [cashError, setCashError] = useState<string | null>(null)

  // Imported transactions table state
  const [importedTransactions, setImportedTransactions] = useState<ImportedTransaction[]>([])
  const [fileSummaries, setFileSummaries] = useState<FileSummary[]>([])
  const [showImportedTable, setShowImportedTable] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('transaction_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const friendlyType = (txType: string, description: string | null): string => {
    const upper = txType.toUpperCase()
    if (upper === 'STO') {
      if (description) {
        const d = description.toLowerCase()
        if (d.includes('call')) return 'Call'
        if (d.includes('put')) return 'Put'
      }
      return 'STO'
    }
    if (upper === 'BTC') return 'BTC'
    if (upper === 'BUY') return 'Buy'
    if (upper === 'SELL') return 'Sell'
    if (upper === 'DIVIDEND') return 'Dividend'
    if (upper === 'INTEREST' || upper === 'SLIP') return 'Interest'
    return txType
  }

  const handleSort = useCallback((key: SortKey) => {
    setSortKey(prev => {
      if (prev === key) {
        setSortDir(d => d === 'asc' ? 'desc' : 'asc')
        return key
      }
      setSortDir('asc')
      return key
    })
  }, [])

  const sortedTransactions = [...importedTransactions].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1
    switch (sortKey) {
      case 'symbol':
        return dir * a.symbol.localeCompare(b.symbol)
      case 'transaction_date':
        return dir * ((a.transaction_date ?? '').localeCompare(b.transaction_date ?? ''))
      case 'amount':
        return dir * (a.amount - b.amount)
      case 'transaction_type':
        return dir * friendlyType(a.transaction_type, a.description).localeCompare(friendlyType(b.transaction_type, b.description))
      default:
        return 0
    }
  })

  const fetchImportedTransactions = async (ids: number[]) => {
    if (!ids.length) return
    try {
      const response = await fetch(
        `${API_BASE}/ingestion/imported-transactions?ingestion_ids=${ids.join(',')}`,
        { headers: getAuthHeaders() }
      )
      if (response.ok) {
        const data = await response.json()
        if (data.transactions && data.transactions.length > 0) {
          setImportedTransactions(data.transactions)
          setSortKey('transaction_date')
          setSortDir('desc')

          // Compute per-file summaries
          // Exclude pure balance transfers — they aren't income and skew the total
          const TRANSFER_TYPES = new Set(['INTERNAL_TRANSFER', 'TRANSFER', 'ACH', 'ACATI', 'ACATO', 'ABIP'])
          const files: Record<string, string> = data.files ?? {}
          const byFile = new Map<number, { count: number; total: number }>()
          for (const tx of data.transactions as ImportedTransaction[]) {
            const id = tx.ingestion_id ?? 0
            const existing = byFile.get(id) ?? { count: 0, total: 0 }
            const incomeAmount = TRANSFER_TYPES.has(tx.transaction_type) ? 0 : tx.amount
            byFile.set(id, { count: existing.count + 1, total: existing.total + incomeAmount })
          }
          const summaries: FileSummary[] = Array.from(byFile.entries()).map(([id, stats]) => ({
            ingestion_id: id,
            file_name: files[String(id)] ?? `File ${id}`,
            count: stats.count,
            total: stats.total,
          }))
          setFileSummaries(summaries)
          setShowImportedTable(true)
        }
      }
    } catch (err) {
      console.error('Failed to fetch imported transactions:', err)
    }
  }

  const handlePreview = async () => {
    if (!pasteText.trim()) {
      setPasteError('Please paste some data from Robinhood')
      return
    }

    setIsPreviewing(true)
    setPasteError(null)
    setPreviewResult(null)
    setSaveResult(null)

    try {
      const response = await fetch('/api/v1/ingestion/robinhood-paste/preview', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: pasteText,
          account_name: robinhoodAccounts.find(a => a.account_id === selectedAccount)?.name || selectedAccount,
        }),
      })

      if (response.ok) {
        const result = await response.json()
        setPreviewResult(result)
        setShowPreviewDetails(true)
      } else {
        const errData = await response.json()
        setPasteError(errData.detail || 'Failed to parse data')
      }
    } catch (err) {
      setPasteError('Unable to connect to server')
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleSave = async () => {
    if (!pasteText.trim()) return

    setIsSaving(true)
    setPasteError(null)

    // First, run preview to check for empty sections
    let currentPreviewResult = previewResult
    if (!currentPreviewResult) {
      try {
        const previewResponse = await fetch('/api/v1/ingestion/robinhood-paste/preview', {
          method: 'POST',
          headers: {
            ...getAuthHeaders(),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            text: pasteText,
            account_name: robinhoodAccounts.find(a => a.account_id === selectedAccount)?.name || selectedAccount,
          }),
        })
        if (previewResponse.ok) {
          currentPreviewResult = await previewResponse.json()
          setPreviewResult(currentPreviewResult)
        }
      } catch (err) {
        // Continue without preview
      }
    }

    // Check if confirmation is required for empty sections
    let shouldConfirmEmpty = currentPreviewResult?.requires_confirmation || false
    if (shouldConfirmEmpty) {
      const confirmed = window.confirm(
        currentPreviewResult?.confirmation_message || 
        "Empty sections detected. This will clear all data for empty sections. Do you want to proceed?"
      )
      if (!confirmed) {
        setIsSaving(false)
        return // User cancelled
      }
    }

    try {
      const response = await fetch('/api/v1/ingestion/robinhood-paste/save', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: pasteText,
          account_name: robinhoodAccounts.find(a => a.account_id === selectedAccount)?.name || selectedAccount,
          save_stocks: true,
          save_options: true,
          confirm_empty_sections: shouldConfirmEmpty,
        }),
      })

      if (response.ok) {
        const result = await response.json()
        setSaveResult(result)
        setShowSaveModal(true)
        // Clear the text area after successful save
        setPasteText('')
        setPreviewResult(null)
        // Refresh accounts to update the timestamp
        await fetchRobinhoodAccounts()
      } else {
        const errData = await response.json()
        setPasteError(errData.detail || 'Failed to save data')
      }
    } catch (err) {
      setPasteError('Unable to connect to server')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCashPreview = async () => {
    if (!cashPasteText.trim()) {
      setCashError('Please paste the cash section from Robinhood')
      return
    }
    setIsCashPreviewing(true)
    setCashError(null)
    setCashPreview(null)
    setCashSaveResult(null)
    try {
      const accountName = robinhoodAccounts.find(a => a.account_id === cashSelectedAccount)?.name || cashSelectedAccount
      const res = await fetch('/api/v1/ingestion/robinhood-cash/preview', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cashPasteText, account_name: accountName }),
      })
      if (res.ok) {
        setCashPreview(await res.json())
      } else {
        const err = await res.json()
        setCashError(err.detail || 'Failed to parse cash data')
      }
    } catch {
      setCashError('Unable to connect to server')
    } finally {
      setIsCashPreviewing(false)
    }
  }

  const handleCashSave = async () => {
    if (!cashPasteText.trim()) return
    setIsCashSaving(true)
    setCashError(null)
    try {
      const accountName = robinhoodAccounts.find(a => a.account_id === cashSelectedAccount)?.name || cashSelectedAccount
      const res = await fetch('/api/v1/ingestion/robinhood-cash/save', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cashPasteText, account_name: accountName }),
      })
      if (res.ok) {
        const result = await res.json()
        setCashSaveResult(result)
        setCashPasteText('')
        setCashPreview(null)
      } else {
        const err = await res.json()
        setCashError(err.detail || 'Failed to save cash data')
      }
    } catch {
      setCashError('Unable to connect to server')
    } finally {
      setIsCashSaving(false)
    }
  }

  const fetchInboxStatus = async () => {
    try {
      const response = await fetch('/api/v1/ingestion/inbox-status', {
        headers: getAuthHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        setInboxStatus(data.folders)
      }
    } catch (err) {
      console.error('Failed to fetch inbox status:', err)
    }
  }

  const handleRefreshData = async () => {
    setIsRefreshing(true)
    setError(null)
    setLastRefresh(null)
    setShowImportedTable(false)
    setImportedTransactions([])
    setFileSummaries([])

    try {
      const response = await fetch('/api/v1/ingestion/process-all', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const result = await response.json()
        setLastRefresh(result)
        // Refresh inbox status after processing
        await fetchInboxStatus()
        // Fetch imported transactions if any records were imported
        if (result.records_imported > 0 && result.ingestion_ids?.length) {
          await fetchImportedTransactions(result.ingestion_ids)
        }
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Failed to refresh data')
      }
    } catch (err) {
      setError('Unable to connect to server')
    } finally {
      setIsRefreshing(false)
    }
  }

  // Fetch Robinhood accounts on mount
  // Merge predefined accounts with database accounts to ensure all accounts are available
  const fetchRobinhoodAccounts = async () => {
    try {
      // Start with all predefined accounts
      const accountsMap = new Map<string, AccountOption>()
      
      // Add all predefined accounts first (ensures all accounts appear even without data)
      for (const acc of ALL_ROBINHOOD_ACCOUNTS) {
        accountsMap.set(acc.account_id, { ...acc })
      }
      
      // Fetch existing accounts from database to get last_updated timestamps
      const response = await fetch(`${API_BASE}/investments/accounts`, {
        headers: getAuthHeaders(),
      })
      
      if (response.ok) {
        const data = await response.json()
        // Merge database accounts - update timestamps for accounts that have data
        for (const acc of (data.accounts || [])) {
          if (acc.source === 'robinhood' && 
              !HIDDEN_ACCOUNTS.includes(acc.account_id) &&
              !HIDDEN_ACCOUNTS.includes(acc.name)) {
            // Update existing entry with last_updated from database
            const existing = accountsMap.get(acc.account_id)
            if (existing) {
              accountsMap.set(acc.account_id, {
                ...existing,
                last_updated: acc.last_updated,
              })
            } else {
              // Account exists in DB but not in predefined list - add it
              accountsMap.set(acc.account_id, {
                account_id: acc.account_id,
                name: acc.name,
                last_updated: acc.last_updated,
              })
            }
          }
        }
      }
      
      // Convert to array and sort
      const robinhood = Array.from(accountsMap.values())
        .sort((a: AccountOption, b: AccountOption) => {
          const orderA = ACCOUNT_ORDER[a.name] ?? 100
          const orderB = ACCOUNT_ORDER[b.name] ?? 100
          return orderA - orderB
        })
      
      setRobinhoodAccounts(robinhood)
      if (robinhood.length > 0 && !selectedAccount) {
        setSelectedAccount(robinhood[0].account_id)
      }
      if (robinhood.length > 0 && !cashSelectedAccount) {
        setCashSelectedAccount(robinhood[0].account_id)
      }
    } catch (err) {
      console.error('Error fetching accounts:', err)
      // Even on error, show predefined accounts
      const robinhood = [...ALL_ROBINHOOD_ACCOUNTS].sort((a, b) => {
        const orderA = ACCOUNT_ORDER[a.name] ?? 100
        const orderB = ACCOUNT_ORDER[b.name] ?? 100
        return orderA - orderB
      })
      setRobinhoodAccounts(robinhood)
      if (robinhood.length > 0 && !selectedAccount) {
        setSelectedAccount(robinhood[0].account_id)
      }
      if (robinhood.length > 0 && !cashSelectedAccount) {
        setCashSelectedAccount(robinhood[0].account_id)
      }
    }
  }

  // Fetch inbox status and accounts on mount
  useEffect(() => {
    fetchInboxStatus()
    fetchRobinhoodAccounts()
  }, [])

  const totalPendingFiles = inboxStatus?.reduce((sum, f) => sum + f.pending_files, 0) ?? 0

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1>Data Import</h1>
          <p className={styles.subtitle}>
            Drop files in the inbox folders, then click Refresh Data to import.
          </p>
        </div>
      </div>

      {/* Robinhood Paste Section */}
      <div className={styles.pasteSection}>
        <div className={styles.pasteSectionHeader}>
          <div className={styles.pasteIcon}>
            <Clipboard size={28} />
          </div>
          <div>
            <h2>Paste from Robinhood</h2>
            <p>Copy your positions from Robinhood and paste below. Supports stocks, options list, and option detail views.</p>
          </div>
        </div>

        <div className={styles.pasteContent}>
          <div className={styles.pasteControls}>
            <label className={styles.accountLabel}>
              Account:
              <select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className={styles.accountSelect}
                disabled={robinhoodAccounts.length === 0}
              >
                {robinhoodAccounts.length === 0 ? (
                  <option>Loading accounts...</option>
                ) : (
                  robinhoodAccounts.map((account) => (
                    <option key={account.account_id} value={account.account_id}>
                      {account.name}
                    </option>
                  ))
                )}
              </select>
            </label>
            {selectedAccount && robinhoodAccounts.length > 0 && (() => {
              const account = robinhoodAccounts.find(a => a.account_id === selectedAccount)
              if (!account) {
                return (
                  <div className={styles.lastUpdateInfo}>
                    <Clock size={14} />
                    <span>Account not found</span>
                  </div>
                )
              }
              
              if (account.last_updated) {
                try {
                  // Handle both date-only and datetime strings
                  let dateStr = account.last_updated
                  if (!dateStr.includes('T')) {
                    // Date-only format, add time
                    dateStr = dateStr + 'T00:00:00Z'
                  } else if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
                    // If it has 'T' but no timezone indicator, assume UTC and add 'Z'
                    dateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
                  }
                  const updateDate = new Date(dateStr)
                  
                  if (!isNaN(updateDate.getTime())) {
                    // Calculate relative time
                    const now = new Date()
                    const diffMs = now.getTime() - updateDate.getTime()
                    const diffMins = Math.floor(diffMs / 60000)
                    const diffHours = Math.floor(diffMs / 3600000)
                    const diffDays = Math.floor(diffMs / 86400000)
                    
                    let relativeTime = ''
                    if (diffMins < 1) {
                      relativeTime = 'just now'
                    } else if (diffMins < 60) {
                      relativeTime = `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
                    } else if (diffHours < 24) {
                      relativeTime = `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
                    } else if (diffDays < 7) {
                      relativeTime = `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
                    } else {
                      // For older dates, show full date
                      relativeTime = updateDate.toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: updateDate.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
                      })
                    }
                    
                    // Format full date/time
                    const fullDateTime = updateDate.toLocaleString('en-US', {
                      timeZone: 'America/Los_Angeles',
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                      hour12: true
                    })
                    
                    return (
                      <div className={styles.lastUpdateInfo}>
                        <Clock size={14} />
                        <span>
                          Last updated: {fullDateTime} PT
                          {diffDays < 7 && (
                            <span className={styles.relativeTime}> ({relativeTime})</span>
                          )}
                        </span>
                      </div>
                    )
                  }
                } catch (e) {
                  console.error('Error parsing date:', e, account.last_updated)
                }
              }
              
              // Show message even if no timestamp
              return (
                <div className={styles.lastUpdateInfo}>
                  <Clock size={14} />
                  <span>No data imported yet for this account</span>
                </div>
              )
            })()}
          </div>

          <textarea
            className={styles.pasteTextarea}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={`Paste your Robinhood data here...

Supported formats:
• Positions Held list (stocks and options)
• Option detail view (with Average credit)

Example:
AAPL $285 Call
12/5 · 1 sell
$2.84
+54.35%`}
            rows={10}
          />

          <div className={styles.pasteActions}>
            <button
              className={styles.previewButton}
              onClick={handlePreview}
              disabled={isPreviewing || !pasteText.trim()}
            >
              {isPreviewing ? (
                <>
                  <RefreshCw size={16} className={styles.spinning} />
                  Parsing...
                </>
              ) : (
                <>
                  <Eye size={16} />
                  Preview
                </>
              )}
            </button>
            <button
              className={styles.saveButton}
              onClick={handleSave}
              disabled={isSaving || !pasteText.trim()}
            >
              {isSaving ? (
                <>
                  <RefreshCw size={16} className={styles.spinning} />
                  Saving...
                </>
              ) : (
                <>
                  <Send size={16} />
                  Save to Database
                </>
              )}
            </button>
          </div>

          {/* Error Message */}
          {pasteError && (
            <div className={styles.pasteError}>
              <AlertCircle size={16} />
              {pasteError}
            </div>
          )}

          {/* Preview Result */}
          {previewResult && (
            <div className={styles.previewResult}>
              <div 
                className={styles.previewHeader}
                onClick={() => setShowPreviewDetails(!showPreviewDetails)}
              >
                <div className={styles.previewSummary}>
                  <CheckCircle size={18} className={styles.successIcon} />
                  <span>
                    Detected: <strong>{previewResult.detected_format}</strong>
                  </span>
                  <span className={styles.previewCounts}>
                    {(previewResult.has_stocks_section || previewResult.stocks_count > 0) && (
                      <span className={styles.stockBadge}>
                        <BarChart3 size={14} />
                        {previewResult.stocks_count > 0 
                          ? `${previewResult.stocks_count} stocks`
                          : '0 stocks (empty section)'}
                      </span>
                    )}
                    {(previewResult.has_options_section || previewResult.options_count > 0) && (
                      <span className={styles.optionBadge}>
                        <TrendingUp size={14} />
                        {previewResult.options_count > 0 
                          ? `${previewResult.options_count} options`
                          : '0 options (empty section)'}
                      </span>
                    )}
                  </span>
                </div>
                <button className={styles.toggleDetails}>
                  {showPreviewDetails ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
              </div>

              {previewResult.requires_confirmation && (
                <div className={styles.confirmationWarning}>
                  <AlertCircle size={18} />
                  <div>
                    <strong>⚠️ Confirmation Required</strong>
                    <p>{previewResult.confirmation_message}</p>
                    <p className={styles.confirmationNote}>
                      You will be asked to confirm before saving.
                    </p>
                  </div>
                </div>
              )}

              {showPreviewDetails && (
                <div className={styles.previewDetails}>
                  {(previewResult.has_stocks_section || previewResult.stocks.length > 0) && (
                    <div className={styles.previewTable}>
                      <h4>Stocks</h4>
                      {previewResult.stocks.length > 0 ? (
                        <table>
                          <thead>
                            <tr>
                              <th>Symbol</th>
                              <th>Shares</th>
                              <th>Price</th>
                              <th>Value</th>
                            </tr>
                          </thead>
                          <tbody>
                            {previewResult.stocks.map((stock, i) => (
                              <tr key={i}>
                                <td><strong>{stock.symbol}</strong></td>
                                <td>{stock.shares.toLocaleString()}</td>
                                <td>${stock.current_price.toFixed(2)}</td>
                                <td>${stock.market_value.toLocaleString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className={styles.emptySection}>
                          <p>No stocks found in this section.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {(previewResult.has_options_section || previewResult.options.length > 0) && (
                    <div className={styles.previewTable}>
                      <h4>Options</h4>
                      {previewResult.options.length > 0 ? (
                        <table>
                          <thead>
                            <tr>
                              <th>Symbol</th>
                              <th>Strike</th>
                              <th>Type</th>
                              <th>Exp</th>
                              <th>#</th>
                              <th>Current</th>
                              <th>Original</th>
                              <th>G/L</th>
                            </tr>
                          </thead>
                          <tbody>
                            {previewResult.options.map((opt, i) => (
                              <tr key={i}>
                                <td><strong>{opt.symbol}</strong></td>
                                <td>${opt.strike_price}</td>
                                <td>{opt.option_type}</td>
                                <td>{opt.expiration_date || '-'}</td>
                                <td>{opt.contracts}</td>
                                <td>{opt.current_premium ? `$${opt.current_premium.toFixed(2)}` : '-'}</td>
                                <td className={opt.original_premium ? styles.hasOriginal : ''}>
                                  {opt.original_premium ? `$${opt.original_premium.toFixed(2)}` : '-'}
                                </td>
                                <td className={clsx(
                                  opt.gain_loss_percent !== null && opt.gain_loss_percent >= 0 && styles.profit,
                                  opt.gain_loss_percent !== null && opt.gain_loss_percent < 0 && styles.loss
                                )}>
                                  {opt.gain_loss_percent !== null ? `${opt.gain_loss_percent > 0 ? '+' : ''}${opt.gain_loss_percent.toFixed(1)}%` : '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className={styles.emptySection}>
                          <p>No options found in this section.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {previewResult.warnings.length > 0 && (
                    <div className={styles.previewWarnings}>
                      {previewResult.warnings.map((w, i) => (
                        <div key={i} className={styles.warningItem}>
                          <AlertCircle size={14} />
                          {w}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Save Result */}
          {saveResult && (
            <div className={styles.saveResult}>
              <CheckCircle size={20} className={styles.successIcon} />
              <div>
                <strong>Saved successfully!</strong>
                <p>
                  {[
                    saveResult.stocks_saved > 0 && `${saveResult.stocks_saved} stocks created`,
                    saveResult.stocks_updated > 0 && `${saveResult.stocks_updated} stocks updated`,
                    saveResult.stocks_removed > 0 && `${saveResult.stocks_removed} stocks removed`,
                    saveResult.options_saved > 0 && `${saveResult.options_saved} options saved`,
                    saveResult.pending_orders_saved > 0 && `${saveResult.pending_orders_saved} pending orders`,
                  ].filter(Boolean).join(', ')}
                </p>
              </div>
              <button
                className={styles.viewDetailsButton}
                onClick={() => setShowSaveModal(true)}
              >
                <Eye size={14} /> View Details
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Cash Breakdown Paste Section */}
      <div className={styles.pasteSection}>
        <div className={styles.pasteSectionHeader}>
          <div className={styles.pasteIcon}>
            <DollarSign size={28} />
          </div>
          <div>
            <h2>Paste Cash Breakdown</h2>
            <p>
              In Robinhood, tap <strong>Investing → Account</strong>, then copy the "Cash" section
              (Cash, Margin total, Margin used, Options collateral, Pending orders, Total) and paste below.
              This enables the <strong>True Portfolio</strong> view on the Investments page.
            </p>
          </div>
        </div>

        <div className={styles.pasteContent}>
          <div className={styles.pasteControls}>
            <label className={styles.accountLabel}>
              Account:
              <select
                value={cashSelectedAccount}
                onChange={(e) => setCashSelectedAccount(e.target.value)}
                className={styles.accountSelect}
                disabled={robinhoodAccounts.length === 0}
              >
                {robinhoodAccounts.map((account) => (
                  <option key={account.account_id} value={account.account_id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <textarea
            className={styles.pasteTextarea}
            value={cashPasteText}
            onChange={(e) => setCashPasteText(e.target.value)}
            placeholder={`Paste the Cash section from Robinhood here...

Expected format:
Cash
$0.00

Margin total
$200,000.00

Margin used
-$5,594.67

Options collateral
-$188,500.00

Pending orders
-$2,106.00

Total
$3,799.33`}
            rows={10}
          />

          <div className={styles.pasteActions}>
            <button
              className={styles.previewButton}
              onClick={handleCashPreview}
              disabled={isCashPreviewing || !cashPasteText.trim()}
            >
              {isCashPreviewing ? (
                <><RefreshCw size={16} className={styles.spinning} />Parsing...</>
              ) : (
                <><Eye size={16} />Preview</>
              )}
            </button>
            <button
              className={styles.saveButton}
              onClick={handleCashSave}
              disabled={isCashSaving || !cashPasteText.trim()}
            >
              {isCashSaving ? (
                <><RefreshCw size={16} className={styles.spinning} />Saving...</>
              ) : (
                <><Send size={16} />Save to Database</>
              )}
            </button>
          </div>

          {cashError && (
            <div className={styles.pasteError}>
              <AlertCircle size={16} />
              {cashError}
            </div>
          )}

          {cashPreview && (
            <div className={styles.previewResult}>
              <div className={styles.previewSummary}>
                <CheckCircle size={18} className={styles.successIcon} />
                <span>Parsed — <strong>{cashPreview.account_name}</strong></span>
              </div>
              <CashBreakdownTable result={cashPreview} />
            </div>
          )}

          {cashSaveResult && (
            <div className={styles.saveResult}>
              <CheckCircle size={20} className={styles.successIcon} />
              <div>
                <strong>Saved successfully!</strong>
                <p>True cash for {cashSaveResult.account_name}: ${cashSaveResult.true_cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* File-based Import Section */}
      <div className={styles.actionCard}>
        <div className={styles.actionContent}>
          <div className={styles.actionIcon}>
            <RefreshCw size={32} />
          </div>
          <div className={styles.actionText}>
            <h2>Refresh Data from Files</h2>
            <p>
              Scan all inbox folders and import new files into the database.
              {totalPendingFiles > 0 && (
                <span className={styles.pendingBadge}>
                  {totalPendingFiles} file{totalPendingFiles !== 1 ? 's' : ''} pending
                </span>
              )}
            </p>
          </div>
        </div>
        <button
          className={styles.refreshButton}
          onClick={handleRefreshData}
          disabled={isRefreshing}
        >
          {isRefreshing ? (
            <>
              <RefreshCw size={20} className={styles.spinning} />
              Processing...
            </>
          ) : (
            <>
              <RefreshCw size={20} />
              Refresh Data
            </>
          )}
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className={styles.errorCard}>
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      {/* Success Result */}
      {lastRefresh && lastRefresh.success && (
        <div className={styles.successCard}>
          <div className={styles.successHeader}>
            <CheckCircle size={24} />
            <div>
              <h3>Data Refreshed Successfully</h3>
              <p>
                Processed {lastRefresh.files_processed} file{lastRefresh.files_processed !== 1 ? 's' : ''}, 
                imported {lastRefresh.records_imported} record{lastRefresh.records_imported !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
          {lastRefresh.details && lastRefresh.details.length > 0 && (
            <div className={styles.successDetails}>
              {lastRefresh.details.map((detail, i) => (
                <div key={i} className={styles.detailItem}>
                  <FolderOpen size={16} />
                  <span className={styles.detailFolder}>{detail.folder}</span>
                  <span className={styles.detailCount}>
                    {detail.files.length} file{detail.files.length !== 1 ? 's' : ''} → {detail.records} records
                  </span>
                </div>
              ))}
            </div>
          )}
          {lastRefresh.errors && lastRefresh.errors.length > 0 && (
            <div className={styles.warningSection}>
              <h4>Warnings</h4>
              {lastRefresh.errors.map((err, i) => (
                <div key={i} className={styles.warningItem}>{err}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Imported Transactions Table */}
      {showImportedTable && sortedTransactions.length > 0 && (() => {
        const overallTotal = fileSummaries.reduce((s, f) => s + f.total, 0)
        const overallCount = fileSummaries.reduce((s, f) => s + f.count, 0)
        const fmt = (n: number) =>
          `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        return (
          <div className={styles.importedCard}>
            <div className={styles.importedHeader}>
              <h3>Newly Imported Transactions ({sortedTransactions.length})</h3>
              <button
                className={styles.dismissButton}
                onClick={() => setShowImportedTable(false)}
                aria-label="Dismiss"
              >
                <X size={18} />
              </button>
            </div>

            {/* Per-file summary */}
            {fileSummaries.length > 0 && (
              <div className={styles.fileSummary}>
                <table className={styles.fileSummaryTable}>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Transactions</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fileSummaries.map((f) => (
                      <tr key={f.ingestion_id}>
                        <td className={styles.fileSummaryName}>{f.file_name}</td>
                        <td>{f.count}</td>
                        <td className={f.total >= 0 ? styles.positive : styles.negative}>
                          {fmt(f.total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {fileSummaries.length > 1 && (
                    <tfoot>
                      <tr className={styles.fileSummaryTotalRow}>
                        <td>Overall Total</td>
                        <td>{overallCount}</td>
                        <td className={overallTotal >= 0 ? styles.positive : styles.negative}>
                          {fmt(overallTotal)}
                        </td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}

            <div className={styles.importedTableWrap}>
              <table className={styles.importedTable}>
                <thead>
                  <tr>
                    {([
                      ['symbol', 'Stock'],
                      ['transaction_date', 'Date'],
                      ['amount', 'Amount'],
                      ['transaction_type', 'Type'],
                    ] as [SortKey, string][]).map(([key, label]) => (
                      <th
                        key={key}
                        className={styles.sortableHeader}
                        onClick={() => handleSort(key)}
                      >
                        {label}
                        {sortKey === key && (
                          <span className={styles.sortArrow}>
                            {sortDir === 'asc' ? ' \u25B2' : ' \u25BC'}
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedTransactions.map((tx, i) => (
                    <tr key={i}>
                      <td><strong>{tx.symbol}</strong></td>
                      <td>{tx.transaction_date ?? '-'}</td>
                      <td className={tx.amount >= 0 ? styles.positive : styles.negative}>
                        ${Math.abs(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td>{friendlyType(tx.transaction_type, tx.description)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })()}

      {/* Inbox Folders Status */}
      <div className={styles.foldersSection}>
        <h2>
          <FolderOpen size={20} />
          Inbox Folders
        </h2>
        <p className={styles.foldersSubtitle}>
          Drop your files into these folders, then click Refresh Data above.
        </p>
        
        <div className={styles.foldersList}>
          {inboxStatus ? (
            inboxStatus.map((folder) => (
              <div key={folder.folder} className={styles.folderItem}>
                <div className={styles.folderInfo}>
                  <FileText size={18} />
                  <span className={styles.folderName}>{folder.folder}</span>
                </div>
                <div className={clsx(
                  styles.folderCount,
                  folder.pending_files > 0 && styles.hasPending
                )}>
                  {folder.pending_files > 0 ? (
                    <>{folder.pending_files} pending</>
                  ) : (
                    <>Empty</>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className={styles.loadingFolders}>
              <Clock size={18} />
              Loading folder status...
            </div>
          )}
        </div>
      </div>

      {/* Instructions */}
      <div className={styles.instructions}>
        <h2>How to Import Data</h2>
        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <div className={styles.stepContent}>
              <h3>Download from your broker</h3>
              <p>Export transaction history or holdings CSV from Robinhood, Schwab, etc.</p>
            </div>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <div className={styles.stepContent}>
              <h3>Drop in the inbox folder</h3>
              <p>Copy files to <code>data/inbox/investments/robinhood/</code> or the appropriate folder.</p>
            </div>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <div className={styles.stepContent}>
              <h3>Click Refresh Data</h3>
              <p>The app scans all folders, parses files, and imports with automatic deduplication.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Save Details Modal */}
      {showSaveModal && saveResult && (
        <div className={styles.modalOverlay} onClick={() => setShowSaveModal(false)}>
          <div className={styles.saveModal} onClick={e => e.stopPropagation()}>
            <div className={styles.saveModalHeader}>
              <h3>Save Details — {saveResult.account_name}</h3>
              <button className={styles.modalClose} onClick={() => setShowSaveModal(false)}>
                <X size={18} />
              </button>
            </div>
            <div className={styles.saveModalBody}>
              <div className={styles.saveModalSummary}>
                {saveResult.stocks_saved > 0 && (
                  <span className={clsx(styles.badge, styles.badgeCreated)}>{saveResult.stocks_saved} Created</span>
                )}
                {saveResult.stocks_updated > 0 && (
                  <span className={clsx(styles.badge, styles.badgeUpdated)}>{saveResult.stocks_updated} Updated</span>
                )}
                {saveResult.stocks_removed > 0 && (
                  <span className={clsx(styles.badge, styles.badgeRemoved)}>{saveResult.stocks_removed} Removed</span>
                )}
                {saveResult.options_saved > 0 && (
                  <span className={clsx(styles.badge, styles.badgeOptions)}>{saveResult.options_saved} Options</span>
                )}
                {saveResult.pending_orders_saved > 0 && (
                  <span className={clsx(styles.badge, styles.badgePending)}>{saveResult.pending_orders_saved} Pending</span>
                )}
              </div>

              {saveResult.stocks_created_details.length > 0 && (
                <div className={styles.saveModalSection}>
                  <h4>Stocks Created</h4>
                  <table className={styles.saveModalTable}>
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Shares</th><th>Price</th><th>Value</th></tr>
                    </thead>
                    <tbody>
                      {saveResult.stocks_created_details.map((s, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td className={styles.symbolCell}>{s.symbol}</td>
                          <td>{s.shares}</td>
                          <td>${s.price.toFixed(2)}</td>
                          <td>${s.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {saveResult.stocks_updated_details.length > 0 && (
                <div className={styles.saveModalSection}>
                  <h4>Stocks Updated</h4>
                  <table className={styles.saveModalTable}>
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Shares</th><th>Price</th><th>Value</th></tr>
                    </thead>
                    <tbody>
                      {saveResult.stocks_updated_details.map((s, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td className={styles.symbolCell}>{s.symbol}</td>
                          <td>
                            {s.old_shares !== s.shares ? (
                              <><span className={styles.oldValue}>{s.old_shares}</span><span className={styles.arrow}>&rarr;</span>{s.shares}</>
                            ) : s.shares}
                          </td>
                          <td>
                            {s.old_price !== s.price ? (
                              <><span className={styles.oldValue}>${s.old_price.toFixed(2)}</span><span className={styles.arrow}>&rarr;</span>${s.price.toFixed(2)}</>
                            ) : `$${s.price.toFixed(2)}`}
                          </td>
                          <td>
                            {s.old_market_value !== s.market_value ? (
                              <><span className={styles.oldValue}>${s.old_market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span><span className={styles.arrow}>&rarr;</span>${s.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</>
                            ) : `$${s.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {saveResult.stocks_removed_details.length > 0 && (
                <div className={styles.saveModalSection}>
                  <h4>Stocks Removed</h4>
                  <table className={styles.saveModalTable}>
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Shares</th><th>Last Price</th><th>Last Value</th></tr>
                    </thead>
                    <tbody>
                      {saveResult.stocks_removed_details.map((s, i) =>
                        s.warning ? (
                          <tr key={i}>
                            <td colSpan={5} style={{ color: 'var(--color-warning, #fbbf24)', fontStyle: 'italic' }}>{s.warning}</td>
                          </tr>
                        ) : (
                          <tr key={i}>
                            <td>{i + 1}</td>
                            <td className={styles.symbolCell}>{s.symbol}</td>
                            <td>{s.shares}</td>
                            <td>${(s.last_price ?? 0).toFixed(2)}</td>
                            <td>${(s.market_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {saveResult.options_saved_details.length > 0 && (
                <div className={styles.saveModalSection}>
                  <h4>Options Saved</h4>
                  <table className={styles.saveModalTable}>
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Type</th><th>Strike</th><th>Expiration</th><th>Contracts</th></tr>
                    </thead>
                    <tbody>
                      {saveResult.options_saved_details.map((o, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td className={styles.symbolCell}>{o.symbol}</td>
                          <td>{o.option_type}</td>
                          <td>${o.strike_price.toFixed(2)}</td>
                          <td>{o.expiration_date || '—'}</td>
                          <td>{o.contracts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {saveResult.pending_orders_details.length > 0 && (
                <div className={styles.saveModalSection}>
                  <h4>Pending Orders</h4>
                  <table className={styles.saveModalTable}>
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Order</th><th>Type</th><th>Strike</th><th>Contracts</th></tr>
                    </thead>
                    <tbody>
                      {saveResult.pending_orders_details.map((p, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td className={styles.symbolCell}>{p.symbol}</td>
                          <td>{p.order_type}</td>
                          <td>{p.option_type || '—'}</td>
                          <td>{p.strike_price ? `$${p.strike_price.toFixed(2)}` : '—'}</td>
                          <td>{p.contracts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {saveResult.stocks_saved === 0 && saveResult.stocks_updated === 0 && saveResult.stocks_removed === 0 && saveResult.options_saved === 0 && saveResult.pending_orders_saved === 0 && (
                <p style={{ color: 'var(--color-text-tertiary)' }}>No changes were made.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
