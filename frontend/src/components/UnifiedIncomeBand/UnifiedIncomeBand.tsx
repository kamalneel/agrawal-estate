import { useState, useEffect, useMemo } from 'react'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './UnifiedIncomeBand.module.css'

const API_BASE = '/api/v1'

type Granularity = 'week' | 'month' | 'year'

interface UnifiedPeriod {
  period: string
  total: number
  fixed: number
  dynamic: number
  by_source: Record<string, number>
  by_account: Record<string, number>
  unresolved_basis_rows: number
}

// Display order + labels; drillable sources navigate to a detail view.
const SOURCES: Array<{ key: string; label: string; kind: 'fixed' | 'dynamic'; drill?: string }> = [
  { key: 'salary', label: 'Salary', kind: 'fixed', drill: 'salary' },
  { key: 'rental', label: 'Rent', kind: 'fixed', drill: 'rental' },
  { key: 'options', label: 'Options', kind: 'dynamic', drill: 'options' },
  { key: 'equity_sales', label: 'Equity Sales', kind: 'dynamic', drill: 'equity_sales' },
  { key: 'dividends', label: 'Dividends', kind: 'dynamic', drill: 'dividends' },
  { key: 'interest', label: 'Interest', kind: 'dynamic', drill: 'interest' },
  { key: 'lending', label: 'Lending', kind: 'dynamic' },
]

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function periodLabel(iso: string, g: Granularity): string {
  const d = new Date(iso + 'T00:00:00')
  if (g === 'week') {
    return `Week ending ${d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}`
  }
  if (g === 'month') {
    return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  }
  return String(d.getFullYear())
}

interface UnifiedIncomeBandProps {
  onDrill?: (source: string) => void
  /** Reports the selected period so the rest of the page can follow. */
  onPeriodChange?: (granularity: Granularity, periodIso: string) => void
  /** Salary projection (labeled, never mixed into actual totals). */
  projectedSalary?: { monthly: number; startMonth: string }  // startMonth: 'YYYY-MM'
}

export function UnifiedIncomeBand({ onDrill, onPeriodChange, projectedSalary }: UnifiedIncomeBandProps) {
  const [granularity, setGranularity] = useState<Granularity>('month')
  const [periods, setPeriods] = useState<UnifiedPeriod[]>([])
  const [cursor, setCursor] = useState<number>(-1)
  const [loading, setLoading] = useState(true)
  const [showAccounts, setShowAccounts] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/income/unified?granularity=${granularity}`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(data => {
        if (cancelled) return
        const ps: UnifiedPeriod[] = data.periods || []
        setPeriods(ps)
        // default to the current period (last period whose date <= today's bucket end)
        const today = new Date().toISOString().slice(0, 10)
        let idx = ps.length - 1
        for (let i = ps.length - 1; i >= 0; i--) {
          if (ps[i].period <= today || i === 0) { idx = i; break }
        }
        // week periods are Friday-ending: current week's Friday may be > today
        if (granularity === 'week') {
          const next = ps.findIndex(p => p.period >= today)
          if (next !== -1) idx = next
        }
        setCursor(idx)
        setLoading(false)
      })
      .catch(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [granularity])

  const p = cursor >= 0 ? periods[cursor] : undefined
  const accounts = useMemo(
    () => Object.entries(p?.by_account || {}).sort((a, b) => b[1] - a[1]),
    [p]
  )

  useEffect(() => {
    if (p && onPeriodChange) onPeriodChange(granularity, p.period)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [granularity, p?.period])

  // Projected salary for this period (labeled line, excluded from totals).
  const projected = useMemo(() => {
    if (!projectedSalary || !p) return 0
    if ((p.by_source.salary || 0) > 0) return 0  // actuals win
    const [sy, sm] = projectedSalary.startMonth.split('-').map(Number)
    const d = new Date(p.period + 'T00:00:00')
    if (granularity === 'month') {
      return (d.getFullYear() > sy || (d.getFullYear() === sy && d.getMonth() + 1 >= sm))
        ? projectedSalary.monthly : 0
    }
    if (granularity === 'year') {
      const y = d.getFullYear()
      if (y < sy) return 0
      const startM = y === sy ? sm : 1
      return (12 - startM + 1) * projectedSalary.monthly
    }
    return 0  // weekly projection would be noise
  }, [projectedSalary, p, granularity])

  return (
    <section className={styles.band}>
      <div className={styles.topRow}>
        <span className={styles.title}>All Income</span>
        <div className={styles.granularityToggle}>
          {(['week', 'month', 'year'] as Granularity[]).map(g => (
            <button
              key={g}
              className={clsx(styles.granButton, granularity === g && styles.active)}
              onClick={() => setGranularity(g)}
            >
              {g === 'week' ? 'Weekly' : g === 'month' ? 'Monthly' : 'Yearly'}
            </button>
          ))}
        </div>
        <div className={styles.periodNav}>
          <button
            className={styles.navButton}
            disabled={cursor <= 0}
            onClick={() => setCursor(c => Math.max(0, c - 1))}
            aria-label="Previous period"
          >
            <ChevronLeft size={16} />
          </button>
          <span className={styles.periodLabel}>
            {p ? periodLabel(p.period, granularity) : '—'}
          </span>
          <button
            className={styles.navButton}
            disabled={cursor >= periods.length - 1}
            onClick={() => setCursor(c => Math.min(periods.length - 1, c + 1))}
            aria-label="Next period"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading…</div>
      ) : !p ? (
        <div className={styles.loading}>No income data</div>
      ) : (
        <>
          <div className={styles.totalsRow}>
            <div className={styles.total}>
              <span className={styles.totalLabel}>Total</span>
              <span className={clsx(styles.totalValue, p.total < 0 && styles.negative)}>{fmt(p.total)}</span>
            </div>
            <div className={styles.split}>
              <div className={styles.splitItem}>
                <span className={styles.splitLabel}>Fixed</span>
                <span className={styles.splitValue}>{fmt(p.fixed)}</span>
              </div>
              <div className={styles.splitItem}>
                <span className={styles.splitLabel}>Dynamic</span>
                <span className={clsx(styles.splitValue, p.dynamic < 0 && styles.negative)}>{fmt(p.dynamic)}</span>
              </div>
            </div>
            {p.unresolved_basis_rows > 0 && (
              <span className={styles.unresolvedBadge} title="Sales excluded from P/L pending basis resolution">
                <AlertTriangle size={12} /> {p.unresolved_basis_rows} unresolved
              </span>
            )}
          </div>

          {projected > 0 && (
            <div className={styles.projectedLine}>
              + {fmt(projected)} projected salary
              {granularity === 'year' ? ' this year' : '/mo'} (starts {projectedSalary!.startMonth} — not in actuals)
            </div>
          )}

          <div className={styles.chipsRow}>
            {SOURCES.map(s => {
              const v = p.by_source[s.key] ?? 0
              const clickable = !!(s.drill && onDrill)
              return (
                <button
                  key={s.key}
                  className={clsx(styles.chip, clickable && styles.clickable)}
                  onClick={clickable ? () => onDrill!(s.drill!) : undefined}
                  disabled={!clickable}
                  title={clickable ? `Drill into ${s.label}` : undefined}
                >
                  <span className={styles.chipLabel}>
                    {s.label}
                    <span className={styles.chipKind}>{s.kind === 'fixed' ? 'F' : 'D'}</span>
                  </span>
                  <span className={clsx(styles.chipValue, v < 0 ? styles.negative : v > 0 ? styles.positive : styles.zero)}>
                    {fmt(v)}
                  </span>
                </button>
              )
            })}
          </div>

          {accounts.length > 0 && (
            <div className={styles.accountsSection}>
              <button className={styles.accountsToggle} onClick={() => setShowAccounts(v => !v)}>
                {showAccounts ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                By account ({accounts.length})
              </button>
              {showAccounts && (
                <div className={styles.accountsGrid}>
                  {accounts.map(([name, v]) => (
                    <div key={name} className={styles.accountRow}>
                      <span className={styles.accountName}>{name}</span>
                      <span className={clsx(styles.accountValue, v < 0 ? styles.negative : styles.positive)}>
                        {fmt(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
