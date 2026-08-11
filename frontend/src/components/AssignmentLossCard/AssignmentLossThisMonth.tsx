import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
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
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setLoss(d.this_month_loss))
      .catch(() => {})
  }, [])

  if (loss === null) return null

  return (
    <button
      type="button"
      className={styles.card}
      onClick={() => navigate('/investments#assignment-loss')}
    >
      <div className={styles.header}>
        <span className={styles.title}>Assignment Loss — this month</span>
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
