import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './AssignmentLossThisMonth.module.css'

const API_BASE = '/api/v1'

interface AssignmentLossThisMonthProps {
  /** Period to report. Omit both (Options Execution) for the current
   *  month. `month: null` with a year sums that whole year. */
  year?: number | 'all'
  month?: number | null
  /** Drop the standalone max-width/margin so the card can sit as a
   *  cell inside the GoalsStrip grid rather than in its own row. */
  inGrid?: boolean
}

/**
 * Options Execution page is scoped to THIS PERIOD ("what should I do
 * today, am I on pace?") — no history here, that's what the Investments
 * page's full AssignmentLossCard is for (Neel, 2026-07-22: the first
 * version put a multi-year chart on a current-pace page, which broke
 * the page's own scope). This is just the current-month figure,
 * matching the Holdings/Cash Goal cards beside it.
 *
 * On the Income page the same card is a third cell in the goals strip.
 * There it takes `year`/`month` and follows the strip's period control —
 * a fixed "this month" figure sitting beside two period-scoped gauges
 * would read as the same period and disagree with them the moment the
 * user pages back a month.
 */
export function AssignmentLossThisMonth({ year, month, inGrid }: AssignmentLossThisMonthProps = {}) {
  const [data, setData] = useState<{ this_month_loss: number; by_month: Record<string, number> } | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  const scoped = useMemo(() => {
    if (!data) return null
    const now = new Date()
    // No period given (Options Execution) — current month, as before.
    if (year === undefined) return { loss: data.this_month_loss, label: 'this month' }
    if (year === 'all') {
      const total = Object.values(data.by_month).reduce((s, v) => s + v, 0)
      return { loss: total, label: 'all time' }
    }
    if (month === null || month === undefined) {
      const loss = Object.entries(data.by_month)
        .filter(([k]) => k.startsWith(`${year}-`))
        .reduce((s, [, v]) => s + v, 0)
      return { loss, label: String(year) }
    }
    const key = `${year}-${String(month).padStart(2, '0')}`
    const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1
    return {
      loss: data.by_month[key] || 0,
      label: isCurrent
        ? 'this month'
        : new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
    }
  }, [data, year, month])

  if (!scoped) return null
  const { loss, label } = scoped

  return (
    <button
      type="button"
      className={clsx(styles.card, inGrid && styles.cardInGrid)}
      onClick={() => navigate('/investments#assignment-loss')}
    >
      <div className={styles.header}>
        <span className={styles.title}>Assignment Loss — {label}</span>
      </div>
      <div className={styles.value} style={{ color: loss === 0 ? '#6b7280' : loss > 0 ? '#FF5A5A' : '#00D632' }}>
        {loss === 0 ? '$0' : `${loss > 0 ? '-' : '+'}$${Math.abs(loss).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
      </div>
      <div className={styles.sub}>
        puts: strike vs. market at assignment · calls: cost basis vs. strike — view the events behind this
        <ChevronRight size={13} style={{ verticalAlign: '-2px', marginLeft: 2 }} />
      </div>
    </button>
  )
}
