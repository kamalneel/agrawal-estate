import { useState, useEffect, useMemo } from 'react'
import { ArrowLeft } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './EquitySalesDetail.module.css'

const API_BASE = '/api/v1'

interface SaleRow {
  sale_date: string
  account: string
  taxable: boolean
  symbol: string
  quantity: number
  proceeds: number
  cost_basis: number
  gain_loss: number
  is_long_term: boolean
  basis_source: string
  unresolved: boolean
}

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export interface DrillRange {
  start: string
  end: string
  label: string
}

interface EquitySalesDetailProps {
  onBack: () => void
  /** When set, opens scoped to the period clicked in the income band. */
  initialRange?: DrillRange | null
}

export function EquitySalesDetail({ onBack, initialRange }: EquitySalesDetailProps) {
  const currentYear = new Date().getFullYear()
  const [range, setRange] = useState<DrillRange | null>(initialRange || null)
  const [year, setYear] = useState<number | 'all'>(currentYear)
  const [sales, setSales] = useState<SaleRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const q = range
      ? `?start=${range.start}&end=${range.end}`
      : year === 'all' ? '' : `?year=${year}`
    fetch(`${API_BASE}/investments/realized-pnl/sales${q}`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => {
        if (!cancelled) {
          setSales(d.sales || [])
          setLoading(false)
        }
      })
      .catch(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [year, range])

  const [accountFilter, setAccountFilter] = useState<string | null>(null)
  const visibleSales = useMemo(
    () => accountFilter ? sales.filter(r => r.account === accountFilter) : sales,
    [sales, accountFilter]
  )

  const totals = useMemo(() => ({
    proceeds: visibleSales.reduce((s, r) => s + r.proceeds, 0),
    basis: visibleSales.reduce((s, r) => s + r.cost_basis, 0),
    gain: visibleSales.reduce((s, r) => s + r.gain_loss, 0),
  }), [visibleSales])

  // Per-account P/L, grouped taxable vs non-taxable — the first questions:
  // taxable or not, and in which account?
  const accountGroups = useMemo(() => {
    const byAccount = new Map<string, { gain: number; taxable: boolean; count: number }>()
    for (const r of sales) {
      const e = byAccount.get(r.account) || { gain: 0, taxable: r.taxable, count: 0 }
      e.gain += r.gain_loss
      e.count += 1
      byAccount.set(r.account, e)
    }
    const entries = [...byAccount.entries()].sort((a, b) => a[1].gain - b[1].gain)
    return {
      taxable: entries.filter(([, v]) => v.taxable),
      nonTaxable: entries.filter(([, v]) => !v.taxable),
      taxableTotal: entries.filter(([, v]) => v.taxable).reduce((s, [, v]) => s + v.gain, 0),
      nonTaxableTotal: entries.filter(([, v]) => !v.taxable).reduce((s, [, v]) => s + v.gain, 0),
    }
  }, [sales])

  const years = useMemo(() => {
    const ys: number[] = []
    for (let y = currentYear; y >= 2018; y--) ys.push(y)
    return ys
  }, [currentYear])

  return (
    <div className={styles.detail}>
      <button className={styles.backButton} onClick={onBack}>
        <ArrowLeft size={16} /> Back to Income
      </button>

      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            Equity Sales Income{range ? ` — ${range.label}` : ''}
          </h1>
          <p className={styles.subtitle}>
            Realized P/L from stock sales — call assignments included as ordinary sales.
            All accounts; holding a stock is never income.
          </p>
        </div>
        <div className={styles.summary}>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Realized P/L</span>
            <span className={clsx(styles.summaryValue, totals.gain < 0 ? styles.negative : styles.positive)}>
              {fmt(totals.gain)}
            </span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Proceeds</span>
            <span className={styles.summaryValue}>{fmt(totals.proceeds)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Cost Basis</span>
            <span className={styles.summaryValue}>{fmt(totals.basis)}</span>
          </div>
        </div>
      </div>

      <div className={styles.yearSelector}>
        {range && (
          <button
            className={clsx(styles.yearButton, styles.active)}
            onClick={() => setRange(null)}
            title="Clear period filter"
          >
            {range.label} ✕
          </button>
        )}
        <button
          className={clsx(styles.yearButton, !range && year === 'all' && styles.active)}
          onClick={() => { setRange(null); setYear('all') }}
        >
          All Time
        </button>
        {years.map(y => (
          <button
            key={y}
            className={clsx(styles.yearButton, !range && year === y && styles.active)}
            onClick={() => { setRange(null); setYear(y) }}
          >
            {y}
          </button>
        ))}
      </div>

      {/* Where did the P/L land — taxable vs non-taxable, by account */}
      {!loading && sales.length > 0 && (
        <div className={styles.groupsRow}>
          {([
            ['Taxable', accountGroups.taxable, accountGroups.taxableTotal],
            ['Non-Taxable (IRA / Roth / 401k)', accountGroups.nonTaxable, accountGroups.nonTaxableTotal],
          ] as const).map(([label, entries, total]) => (
            <div key={label} className={styles.groupCard}>
              <div className={styles.groupHeader}>
                <span className={styles.groupTitle}>{label}</span>
                <span style={{ color: total < 0 ? '#FF5A5A' : '#00D632', fontWeight: 700, fontSize: 18 }}>
                  {fmt(total)}
                </span>
              </div>
              {entries.length === 0 ? (
                <div className={styles.groupEmpty}>No sales</div>
              ) : entries.map(([name, v]) => (
                <button
                  key={name}
                  className={clsx(styles.groupAccount, accountFilter === name && styles.groupAccountActive)}
                  onClick={() => setAccountFilter(accountFilter === name ? null : name)}
                  title={accountFilter === name ? 'Clear account filter' : `Show only ${name}`}
                >
                  <span>{name} <span className={styles.groupCount}>({v.count})</span></span>
                  <span style={{ color: v.gain < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>
                    {fmt(v.gain)}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {accountFilter && (
        <div className={styles.filterNote}>
          Showing only <strong>{accountFilter}</strong>
          <button className={styles.clearFilter} onClick={() => setAccountFilter(null)}>✕ clear</button>
        </div>
      )}

      {loading ? (
        <div className={styles.loading}>Loading…</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Account</th>
                <th>Symbol</th>
                <th className={styles.num}>Qty</th>
                <th className={styles.num}>Proceeds</th>
                <th className={styles.num}>Basis</th>
                <th className={styles.num}>Gain / Loss</th>
                <th>Term</th>
                <th>Basis Source</th>
              </tr>
            </thead>
            <tbody>
              {visibleSales.map((r, i) => (
                <tr key={i} className={clsx(r.unresolved && styles.unresolvedRow)}>
                  <td>{r.sale_date}</td>
                  <td>
                    {r.account}{' '}
                    <span className={styles.taxBadge} style={{ color: r.taxable ? '#FFB800' : '#737373' }}>
                      {r.taxable ? 'taxable' : 'sheltered'}
                    </span>
                  </td>
                  <td className={styles.symbol}>{r.symbol}</td>
                  <td className={styles.num}>{r.quantity.toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
                  <td className={styles.num}>{fmt(r.proceeds)}</td>
                  <td className={styles.num}>{r.unresolved ? '—' : fmt(r.cost_basis)}</td>
                  <td className={styles.num} style={{ color: r.gain_loss < 0 ? '#FF5A5A' : '#00D632', fontWeight: 600 }}>
                    {r.unresolved ? 'pending' : fmt(r.gain_loss)}
                  </td>
                  <td>{r.is_long_term ? 'LT' : 'ST'}</td>
                  <td className={styles.source}>{r.basis_source}</td>
                </tr>
              ))}
              {visibleSales.length === 0 && (
                <tr><td colSpan={9} className={styles.empty}>No equity sales in this period</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
