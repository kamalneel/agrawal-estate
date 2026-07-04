import { useState, useEffect, useMemo } from 'react'
import { ArrowLeft } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './EquitySalesDetail.module.css'

const API_BASE = '/api/v1'

interface SaleRow {
  sale_date: string
  account: string
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

interface EquitySalesDetailProps {
  onBack: () => void
}

export function EquitySalesDetail({ onBack }: EquitySalesDetailProps) {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState<number | 'all'>(currentYear)
  const [sales, setSales] = useState<SaleRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const q = year === 'all' ? '' : `?year=${year}`
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
  }, [year])

  const totals = useMemo(() => ({
    proceeds: sales.reduce((s, r) => s + r.proceeds, 0),
    basis: sales.reduce((s, r) => s + r.cost_basis, 0),
    gain: sales.reduce((s, r) => s + r.gain_loss, 0),
  }), [sales])

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
          <h1 className={styles.title}>Equity Sales Income</h1>
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
        <button
          className={clsx(styles.yearButton, year === 'all' && styles.active)}
          onClick={() => setYear('all')}
        >
          All Time
        </button>
        {years.map(y => (
          <button
            key={y}
            className={clsx(styles.yearButton, year === y && styles.active)}
            onClick={() => setYear(y)}
          >
            {y}
          </button>
        ))}
      </div>

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
              {sales.map((r, i) => (
                <tr key={i} className={clsx(r.unresolved && styles.unresolvedRow)}>
                  <td>{r.sale_date}</td>
                  <td>{r.account}</td>
                  <td className={styles.symbol}>{r.symbol}</td>
                  <td className={styles.num}>{r.quantity.toLocaleString('en-US', { maximumFractionDigits: 2 })}</td>
                  <td className={styles.num}>{fmt(r.proceeds)}</td>
                  <td className={styles.num}>{r.unresolved ? '—' : fmt(r.cost_basis)}</td>
                  <td className={clsx(styles.num, r.gain_loss < 0 ? styles.negative : styles.positive)}>
                    {r.unresolved ? 'pending' : fmt(r.gain_loss)}
                  </td>
                  <td>{r.is_long_term ? 'LT' : 'ST'}</td>
                  <td className={styles.source}>{r.basis_source}</td>
                </tr>
              ))}
              {sales.length === 0 && (
                <tr><td colSpan={9} className={styles.empty}>No equity sales in this period</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
