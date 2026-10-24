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
 *
 * Puts only, on both pages (Neel, 2026-10-23, UX audit). Call assignments
 * are share sales, already in Income's Equity Sales — adding them here
 * counted the same loss twice (2026-10-15: IBIT and ZM) and made Options
 * Execution show −$23,224 for October where Income showed −$14,698.
 * The click goes to Put Campaigns for the same period, where the figure
 * is shown on arrival and its stocks are highlighted.
 */
export function AssignmentLossThisMonth({ year, month, inGrid }: AssignmentLossThisMonthProps = {}) {
  const [raw, setRaw] = useState<{
    this_month_puts: number
    by_month_type: Record<string, { put: number; call: number }>
  } | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setRaw(d))
      .catch(() => {})
  }, [])

  const data = useMemo(() => raw && {
    this_month_loss: raw.this_month_puts,
    by_month: Object.fromEntries(Object.entries(raw.by_month_type || {}).map(([m, t]) => [m, t.put || 0])),
  }, [raw])

  const scoped = useMemo(() => {
    if (!data) return null
    const now = new Date()
    // No period given (Options Execution) — current month, as before.
    const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    if (year === undefined) return { loss: data.this_month_loss, label: 'this month', period: thisMonth }
    if (year === 'all') {
      const total = Object.values(data.by_month).reduce((s, v) => s + v, 0)
      return { loss: total, label: 'all time', period: null }
    }
    if (month === null || month === undefined) {
      const loss = Object.entries(data.by_month)
        .filter(([k]) => k.startsWith(`${year}-`))
        .reduce((s, [, v]) => s + v, 0)
      return { loss, label: String(year), period: String(year) }
    }
    const key = `${year}-${String(month).padStart(2, '0')}`
    const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1
    return {
      loss: data.by_month[key] || 0,
      period: key,
      label: isCurrent
        ? 'this month'
        : new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
    }
  }, [data, year, month])

  if (!scoped) return null
  const { loss, label, period } = scoped

  return (
    <button
      type="button"
      className={clsx(styles.card, inGrid && styles.cardInGrid)}
      onClick={() => navigate(`/investments${period ? `?assigned=${period}` : ''}#put-campaigns`)}
    >
      <div className={styles.header}>
        <span className={styles.title}>Put Assignment Loss — {label}</span>
      </div>
      <div className={styles.value} style={{ color: loss === 0 ? '#6b7280' : loss > 0 ? '#FF5A5A' : '#00D632' }}>
        {loss === 0 ? '$0' : `${loss > 0 ? '-' : '+'}$${Math.abs(loss).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
      </div>
      <div className={styles.sub}>
        strike vs. market when each put was assigned · call assignments are in Equity Sales — see these in Put Campaigns
        <ChevronRight size={13} style={{ verticalAlign: '-2px', marginLeft: 2 }} />
      </div>
    </button>
  )
}
