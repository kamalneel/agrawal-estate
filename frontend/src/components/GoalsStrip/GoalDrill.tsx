import { useState, useEffect, useMemo } from 'react'
import { ArrowLeft } from 'lucide-react'
import { getAuthHeaders } from '../../contexts/AuthContext'
import { accountRank } from '../../lib/accountOrder'
import styles from './GoalDrill.module.css'

const API_BASE = '/api/v1'

interface HoldingRow {
  account: string
  symbol: string
  position_value: number
  calls: number
  dividends: number
  income: number
  yield_pct: number | null
}

interface CashAccount {
  account: string
  capacity: number
  detail: string
  puts: number
  yield_pct: number | null
}

interface GoalDrillProps {
  kind: 'holdings' | 'cash'
  year: number
  month: number | null
  targetPctPerMonth: number
  onBack: () => void
}

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function GoalDrill({ kind, year, month, targetPctPerMonth, onBack }: GoalDrillProps) {
  const [data, setData] = useState<{ holdings: HoldingRow[]; cash_accounts: CashAccount[]; n_months: number } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const q = month !== null ? `?year=${year}&month=${month}` : `?year=${year}`
    fetch(`${API_BASE}/income/goal-drill${q}`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [year, month])

  const periodLabel = month !== null
    ? `${new Date(year, month - 1).toLocaleString('default', { month: 'long' })} ${year}`
    : String(year)
  const targetPct = targetPctPerMonth * (data?.n_months ?? 1)

  const statusColor = (yieldPct: number | null) => {
    if (yieldPct === null) return 'var(--color-text-tertiary)'
    const ratio = yieldPct / targetPct
    return ratio >= 1 ? '#00D632' : ratio >= 0.7 ? '#FFB800' : '#FF5A5A'
  }

  const holdings = useMemo(() => {
    const rows = data?.holdings ?? []
    return [...rows].sort((a, b) =>
      accountRank(a.account) - accountRank(b.account) || b.position_value - a.position_value)
  }, [data])

  const cashAccounts = useMemo(() => {
    const rows = data?.cash_accounts ?? []
    return [...rows]
      .filter(r => r.capacity > 1000 || r.puts !== 0)
      .sort((a, b) => accountRank(a.account) - accountRank(b.account))
  }, [data])

  const totals = useMemo(() => {
    if (kind === 'holdings') {
      const value = holdings.reduce((s, r) => s + r.position_value, 0)
      const income = holdings.reduce((s, r) => s + r.income, 0)
      return { base: value, income, yieldPct: value ? (income / value) * 100 : null }
    }
    const cap = cashAccounts.reduce((s, r) => s + r.capacity, 0)
    const income = cashAccounts.reduce((s, r) => s + r.puts, 0)
    return { base: cap, income, yieldPct: cap ? (income / cap) * 100 : null }
  }, [kind, holdings, cashAccounts])

  return (
    <div className={styles.drill}>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={16} /> Back to Income
      </button>

      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            {kind === 'holdings' ? 'Holdings Goal' : 'Cash Goal'} — {periodLabel}
          </h1>
          <p className={styles.subtitle}>
            {kind === 'holdings'
              ? `Target ${targetPct.toFixed(0)}% for the period: covered-call premium + dividends on each position. Zero-income rows are idle collateral.`
              : `Target ${targetPct.toFixed(0)}% for the period: put premium on each account's put capacity (margin line + cash, or cash incl. collateral).`}
          </p>
        </div>
        <div className={styles.summary}>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Earned</span>
            <span className={styles.summaryValue} style={{ color: statusColor(totals.yieldPct) }}>
              {fmt(totals.income)}
            </span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>{kind === 'holdings' ? 'Holdings' : 'Capacity'}</span>
            <span className={styles.summaryValue}>{fmt(totals.base)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Yield</span>
            <span className={styles.summaryValue} style={{ color: statusColor(totals.yieldPct) }}>
              {totals.yieldPct !== null ? `${totals.yieldPct.toFixed(2)}%` : '—'}
            </span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading…</div>
      ) : kind === 'holdings' ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Account</th>
                <th>Symbol</th>
                <th className={styles.num}>Position Value</th>
                <th className={styles.num}>Calls</th>
                <th className={styles.num}>Dividends</th>
                <th className={styles.num}>Income</th>
                <th className={styles.num}>Yield</th>
                <th className={styles.num}>vs {targetPct.toFixed(0)}%</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((r, i) => (
                <tr key={i} className={r.income === 0 && r.position_value > 0 ? styles.idleRow : undefined}>
                  <td>{r.account}</td>
                  <td className={styles.symbol}>{r.symbol}</td>
                  <td className={styles.num}>{r.position_value ? fmt(r.position_value) : '—'}</td>
                  <td className={styles.num} style={{ color: r.calls === 0 ? 'var(--color-text-tertiary)' : r.calls < 0 ? '#FF5A5A' : '#00D632' }}>
                    {r.calls !== 0 ? fmt(r.calls) : '—'}
                  </td>
                  <td className={styles.num} style={{ color: r.dividends === 0 ? 'var(--color-text-tertiary)' : undefined }}>
                    {r.dividends !== 0 ? fmt(r.dividends) : '—'}
                  </td>
                  <td className={styles.num} style={{ color: statusColor(r.yield_pct), fontWeight: 600 }}>
                    {r.income !== 0 ? fmt(r.income) : '—'}
                  </td>
                  <td className={styles.num} style={{ color: statusColor(r.yield_pct) }}>
                    {r.yield_pct !== null ? `${r.yield_pct.toFixed(2)}%` : '—'}
                  </td>
                  <td className={styles.num}>
                    {r.yield_pct !== null && r.position_value > 0 ? (
                      <span style={{ color: statusColor(r.yield_pct) }}>
                        {r.yield_pct >= targetPct ? '✓' : r.income === 0 ? 'idle' : `${Math.round((r.yield_pct / targetPct) * 100)}%`}
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Account</th>
                <th className={styles.num}>Put Capacity</th>
                <th>How</th>
                <th className={styles.num}>Puts Earned</th>
                <th className={styles.num}>Yield</th>
                <th className={styles.num}>vs {targetPct.toFixed(0)}%</th>
              </tr>
            </thead>
            <tbody>
              {cashAccounts.map((r, i) => (
                <tr key={i} className={r.puts === 0 ? styles.idleRow : undefined}>
                  <td>{r.account}</td>
                  <td className={styles.num}>{fmt(r.capacity)}</td>
                  <td className={styles.detail}>{r.detail}</td>
                  <td className={styles.num} style={{ color: r.puts === 0 ? 'var(--color-text-tertiary)' : r.puts < 0 ? '#FF5A5A' : '#00A3FF', fontWeight: 600 }}>
                    {r.puts !== 0 ? fmt(r.puts) : '—'}
                  </td>
                  <td className={styles.num} style={{ color: statusColor(r.yield_pct) }}>
                    {r.yield_pct !== null ? `${r.yield_pct.toFixed(2)}%` : '—'}
                  </td>
                  <td className={styles.num}>
                    {r.yield_pct !== null ? (
                      <span style={{ color: statusColor(r.yield_pct) }}>
                        {r.yield_pct >= targetPct ? '✓' : r.puts === 0 ? 'idle' : `${Math.round((r.yield_pct / targetPct) * 100)}%`}
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
