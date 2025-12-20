import { useState, useEffect } from 'react'
import { RefreshCw, CheckCircle, AlertCircle, FolderOpen, FileText, Clock, Clipboard, Send, ChevronDown, ChevronUp, TrendingUp, BarChart3, Eye } from 'lucide-react'
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
}

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

interface SaveResult {
  success: boolean
  account_name: string
  stocks_saved: number
  stocks_updated: number
  options_saved: number
  snapshot_id: number | null
  detected_format: string
}

interface AccountOption {
  account_id: string
  name: string
  last_updated: string | null
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
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [showPreviewDetails, setShowPreviewDetails] = useState(false)

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
                  {saveResult.stocks_saved > 0 && `${saveResult.stocks_saved} stocks created`}
                  {saveResult.stocks_updated > 0 && `, ${saveResult.stocks_updated} stocks updated`}
                  {saveResult.options_saved > 0 && `, ${saveResult.options_saved} options saved`}
                </p>
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
    </div>
  )
}
