import { useEffect, useState } from 'react'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './AssignmentLossThisMonth.module.css'

const API_BASE = '/api/v1'

/**
 * Options Execution page is scoped to THIS PERIOD ("what should I do
 * today, am I on pace?") — no history here, that's what the Investments
 * page's full AssignmentLossCard is for (Neel, 2026-07-22: the first
 * version put a multi-year chart on a current-pace page, which broke
 * the page's own scope). This is just the current-month figure,
 * matching the Holdings/Cash Goal cards beside it.
 */
export function AssignmentLossThisMonth() {
  const [loss, setLoss] = useState<number | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setLoss(d.this_month_loss))
      .catch(() => {})
  }, [])

  if (loss === null) return null

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.title}>Assignment Loss — this month</span>
      </div>
      <div className={styles.value} style={{ color: loss > 0 ? '#FF5A5A' : '#6b7280' }}>
        {loss > 0 ? `-$${loss.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '$0'}
      </div>
      <div className={styles.sub}>strike vs. market price at the moment of assignment — see Investments for history</div>
    </div>
  )
}
