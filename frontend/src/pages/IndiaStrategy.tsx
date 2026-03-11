import { useState, useEffect, useCallback } from 'react'
import { Globe, Plus, Pencil, Trash2, ArrowLeft, RefreshCw, AlertCircle } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './IndiaStrategy.module.css'
import clsx from 'clsx'

const API_BASE = '/api/v1'

// Types
interface IndiaHolding {
  id: number
  symbol: string
  exchange: string
  name: string | null
  shares: number
  avgCostInr: number | null
  currentPriceInr: number | null
  targetValueInr: number | null
  currentValueInr: number | null
  gapToTargetInr: number | null
  accountName: string
  notes: string | null
}

interface IndiaAccount {
  accountName: string
  totalValueInr: number
  totalTargetInr: number
  holdingsCount: number
}

type SortKey = 'symbol' | 'exchange' | 'shares' | 'avgCost' | 'price' | 'value' | 'target' | 'gap'
type SortDir = 'asc' | 'desc'

const formatINR = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

const formatNumber = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

// --- Add/Edit Modal ---
interface ModalProps {
  holding?: IndiaHolding | null
  onClose: () => void
  onSave: (data: HoldingFormData) => Promise<void>
}

interface HoldingFormData {
  symbol: string
  exchange: string
  name: string
  shares: string
  avg_cost_inr: string
  current_price_inr: string
  target_value_inr: string
  account_name: string
  notes: string
}

function HoldingModal({ holding, onClose, onSave }: ModalProps) {
  const [form, setForm] = useState<HoldingFormData>({
    symbol: holding?.symbol ?? '',
    exchange: holding?.exchange ?? 'NSE',
    name: holding?.name ?? '',
    shares: holding?.shares?.toString() ?? '0',
    avg_cost_inr: holding?.avgCostInr?.toString() ?? '',
    current_price_inr: holding?.currentPriceInr?.toString() ?? '',
    target_value_inr: holding?.targetValueInr?.toString() ?? '',
    account_name: holding?.accountName ?? 'Default',
    notes: holding?.notes ?? '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.symbol.trim()) return
    setSaving(true)
    try {
      await onSave(form)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  const set = (field: keyof HoldingFormData, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }))

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h3>{holding ? 'Edit Holding' : 'Add Symbol'}</h3>
        <form onSubmit={handleSubmit}>
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label>Symbol *</label>
              <input
                value={form.symbol}
                onChange={e => set('symbol', e.target.value)}
                placeholder="e.g. RELIANCE"
                required
              />
            </div>
            <div className={styles.formGroup}>
              <label>Exchange</label>
              <select value={form.exchange} onChange={e => set('exchange', e.target.value)}>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
              </select>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label>Company Name</label>
            <input
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="e.g. Reliance Industries Ltd"
            />
          </div>

          <div className={styles.formGroup}>
            <label>Account</label>
            <input
              value={form.account_name}
              onChange={e => set('account_name', e.target.value)}
              placeholder="e.g. Zerodha, Groww"
            />
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label>Shares</label>
              <input
                type="number"
                step="any"
                value={form.shares}
                onChange={e => set('shares', e.target.value)}
              />
            </div>
            <div className={styles.formGroup}>
              <label>Avg Cost (INR)</label>
              <input
                type="number"
                step="any"
                value={form.avg_cost_inr}
                onChange={e => set('avg_cost_inr', e.target.value)}
                placeholder="Per share"
              />
            </div>
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label>Current Price (INR)</label>
              <input
                type="number"
                step="any"
                value={form.current_price_inr}
                onChange={e => set('current_price_inr', e.target.value)}
                placeholder="Per share"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Target Value (INR)</label>
              <input
                type="number"
                step="any"
                value={form.target_value_inr}
                onChange={e => set('target_value_inr', e.target.value)}
                placeholder="Total target amount"
              />
            </div>
          </div>

          <div className={styles.formGroup}>
            <label>Notes</label>
            <textarea
              value={form.notes}
              onChange={e => set('notes', e.target.value)}
              placeholder="Optional notes..."
            />
          </div>

          <div className={styles.formActions}>
            <button type="button" className={styles.cancelButton} onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className={styles.submitButton} disabled={saving || !form.symbol.trim()}>
              {saving ? 'Saving...' : holding ? 'Update' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// --- Main Page ---
export default function IndiaStrategy() {
  const [holdings, setHoldings] = useState<IndiaHolding[]>([])
  const [accounts, setAccounts] = useState<IndiaAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [showModal, setShowModal] = useState(false)
  const [editingHolding, setEditingHolding] = useState<IndiaHolding | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [holdingsRes, accountsRes] = await Promise.all([
        fetch(`${API_BASE}/strategies/india-strategy/holdings`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/strategies/india-strategy/accounts`, { headers: getAuthHeaders() }),
      ])
      if (!holdingsRes.ok || !accountsRes.ok) throw new Error('Failed to fetch data')
      setHoldings(await holdingsRes.json())
      setAccounts(await accountsRes.json())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSave = async (data: HoldingFormData) => {
    const body = {
      symbol: data.symbol,
      exchange: data.exchange,
      name: data.name || null,
      shares: parseFloat(data.shares) || 0,
      avg_cost_inr: data.avg_cost_inr ? parseFloat(data.avg_cost_inr) : null,
      current_price_inr: data.current_price_inr ? parseFloat(data.current_price_inr) : null,
      target_value_inr: data.target_value_inr ? parseFloat(data.target_value_inr) : null,
      account_name: data.account_name || 'Default',
      notes: data.notes || null,
    }

    const url = editingHolding
      ? `${API_BASE}/strategies/india-strategy/holdings/${editingHolding.id}`
      : `${API_BASE}/strategies/india-strategy/holdings`

    const res = await fetch(url, {
      method: editingHolding ? 'PUT' : 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Failed to save')
    await fetchData()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this holding?')) return
    await fetch(`${API_BASE}/strategies/india-strategy/holdings/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    await fetchData()
  }

  const openAdd = () => { setEditingHolding(null); setShowModal(true) }
  const openEdit = (h: IndiaHolding) => { setEditingHolding(h); setShowModal(true) }

  // Sorting
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sortIndicator = (key: SortKey) =>
    sortKey === key
      ? <span className={styles.sortIcon}>{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
      : null

  // Filter by account
  const filtered = selectedAccount
    ? holdings.filter(h => h.accountName === selectedAccount)
    : holdings

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1
    const val = (h: IndiaHolding): number | string => {
      switch (sortKey) {
        case 'symbol': return h.symbol
        case 'exchange': return h.exchange
        case 'shares': return h.shares
        case 'avgCost': return h.avgCostInr ?? -Infinity
        case 'price': return h.currentPriceInr ?? -Infinity
        case 'value': return h.currentValueInr ?? -Infinity
        case 'target': return h.targetValueInr ?? -Infinity
        case 'gap': return h.gapToTargetInr ?? -Infinity
      }
    }
    const va = val(a), vb = val(b)
    if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * dir
    return ((va as number) - (vb as number)) * dir
  })

  // Totals
  const totalValue = filtered.reduce((s, h) => s + (h.currentValueInr ?? 0), 0)
  const totalTarget = filtered.reduce((s, h) => s + (h.targetValueInr ?? 0), 0)

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading India Investments...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <AlertCircle size={32} />
          <p>{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      {/* Back button when viewing specific account */}
      {selectedAccount && (
        <button className={styles.backButton} onClick={() => setSelectedAccount(null)}>
          <ArrowLeft size={18} /> All Accounts
        </button>
      )}

      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>
            {selectedAccount ? selectedAccount : 'India Investments'}
          </div>
          <div className={styles.heroValue}>
            {totalValue > 0 ? formatINR(totalValue) : '--'}
          </div>
          {totalTarget > 0 && (
            <div className={styles.heroTarget}>
              Target: <span>{formatINR(totalTarget)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Account Cards - only in "all" view */}
      {!selectedAccount && accounts.length > 0 && (
        <div className={styles.accountsSection}>
          <h2>Brokerage Accounts</h2>
          <div className={styles.accountsGrid}>
            {accounts.map(acct => (
              <button
                key={acct.accountName}
                className={styles.accountCard}
                onClick={() => setSelectedAccount(acct.accountName)}
              >
                <div className={styles.accountName}>{acct.accountName}</div>
                <div className={styles.accountValues}>
                  <div className={styles.accountValue}>
                    {acct.totalValueInr > 0 ? formatINR(acct.totalValueInr) : '--'}
                  </div>
                  {acct.totalTargetInr > 0 && (
                    <div className={styles.accountTarget}>
                      Target: {formatINR(acct.totalTargetInr)}
                    </div>
                  )}
                </div>
                <div className={styles.accountHoldings}>
                  {acct.holdingsCount} holding{acct.holdingsCount !== 1 ? 's' : ''}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Holdings */}
      <div className={styles.holdingsSection}>
        <div className={styles.holdingsHeader}>
          <h2>{selectedAccount ? `${selectedAccount} Holdings` : 'Total Portfolio Holdings'}</h2>
          <button className={styles.addButton} onClick={openAdd}>
            <Plus size={16} /> Add Symbol
          </button>
        </div>

        {sorted.length === 0 ? (
          <div className={styles.emptyState}>
            <Globe size={48} />
            <h3>No Indian Holdings Yet</h3>
            <p>
              Add your first Indian stock or investment goal to get started.
              You can add symbols even without current holdings to track your target allocation.
            </p>
            <button className={styles.emptyAddButton} onClick={openAdd}>
              <Plus size={18} /> Add Symbol
            </button>
          </div>
        ) : (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.sortableHeader} onClick={() => handleSort('symbol')}>
                    Symbol{sortIndicator('symbol')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('exchange')}>
                    Exchange{sortIndicator('exchange')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('shares')}>
                    Shares{sortIndicator('shares')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('avgCost')}>
                    Avg Cost{sortIndicator('avgCost')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('price')}>
                    Price{sortIndicator('price')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('value')}>
                    Current Value{sortIndicator('value')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('target')}>
                    Target Value{sortIndicator('target')}
                  </th>
                  <th className={styles.sortableHeader} onClick={() => handleSort('gap')}>
                    Gap{sortIndicator('gap')}
                  </th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(h => (
                  <tr key={h.id} className={styles.tableRow}>
                    <td>
                      <span className={styles.symbol}>{h.symbol}</span>
                      {h.name && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>{h.name}</div>}
                    </td>
                    <td className={styles.alignCenter}>{h.exchange}</td>
                    <td className={styles.alignCenter}>
                      <span className={styles.totalValue}>{formatNumber(h.shares)}</span>
                    </td>
                    <td className={styles.alignCenter}>
                      <span className={styles.totalValue}>
                        {h.avgCostInr != null ? formatINR(h.avgCostInr) : '--'}
                      </span>
                    </td>
                    <td className={styles.alignCenter}>
                      <span className={styles.totalValue}>
                        {h.currentPriceInr != null ? formatINR(h.currentPriceInr) : '--'}
                      </span>
                    </td>
                    <td className={styles.alignCenter}>
                      <span className={styles.totalValue}>
                        {h.currentValueInr != null ? formatINR(h.currentValueInr) : '--'}
                      </span>
                    </td>
                    <td className={styles.alignCenter}>
                      <span className={styles.totalValue}>
                        {h.targetValueInr != null ? formatINR(h.targetValueInr) : '--'}
                      </span>
                    </td>
                    <td className={styles.alignCenter}>
                      {h.gapToTargetInr != null ? (
                        <span className={h.gapToTargetInr <= 0 ? styles.gapPositive : styles.gapNegative}>
                          {h.gapToTargetInr <= 0 ? 'Met' : formatINR(h.gapToTargetInr)}
                        </span>
                      ) : '--'}
                    </td>
                    <td>
                      <div className={styles.actions}>
                        <button className={styles.actionButton} onClick={() => openEdit(h)} title="Edit">
                          <Pencil size={14} />
                        </button>
                        <button
                          className={clsx(styles.actionButton, styles.delete)}
                          onClick={() => handleDelete(h.id)}
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className={styles.totalsRow}>
                  <td><span className={styles.totalLabel}>TOTAL</span></td>
                  <td />
                  <td />
                  <td />
                  <td />
                  <td className={styles.alignCenter}>
                    <span className={styles.totalValue}>{totalValue > 0 ? formatINR(totalValue) : '--'}</span>
                  </td>
                  <td className={styles.alignCenter}>
                    <span className={styles.totalValue}>{totalTarget > 0 ? formatINR(totalTarget) : '--'}</span>
                  </td>
                  <td />
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <HoldingModal
          holding={editingHolding}
          onClose={() => { setShowModal(false); setEditingHolding(null) }}
          onSave={handleSave}
        />
      )}
    </div>
  )
}
