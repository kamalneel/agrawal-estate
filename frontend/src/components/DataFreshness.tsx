/**
 * Global data-freshness pill (every page, bottom-right).
 *
 * Answers "is what I'm looking at current?" — green when the newest synced
 * data landed at/after the most recent scheduled MCP refresh slot, amber
 * when a slot appears to have been missed (Mac asleep, Robinhood token
 * expired, backend down). The slots come from the backend
 * (/ingestion/freshness `schedule`), so this comment does not go stale;
 * they live in scripts/com.agrawal.estate.refresh.plist.
 * Hover for the per-source breakdown.
 *
 * Click = run the same FULL MCP sync the schedule runs (POST
 * /ingestion/refresh-now kicks the launchd job); the pill shows
 * "Refreshing…" and polls until the data timestamps advance (~5-6 min).
 * The per-page "Sync accounts" / "Sync prices" buttons (SyncButton.tsx)
 * are the narrower, cheaper versions of the same pull — note that only
 * "Sync prices" covers tracked symbols you do not hold.
 */
import { useEffect, useRef, useState } from 'react'
import { RefreshCw, AlertTriangle } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import styles from './DataFreshness.module.css'

interface Freshness {
  sources: Record<string, string | null>
  overall: string | null
  last_expected_run: string | null
  status: 'fresh' | 'stale'
  hours_since: number | null
  schedule: string
}

const POLL_MS = 5 * 60 * 1000
const REFRESH_POLL_MS = 20 * 1000
const REFRESH_TIMEOUT_MS = 12 * 60 * 1000

function fmtTime(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  const now = new Date()
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dayDiff = Math.round((startOfDay(now) - startOfDay(d)) / 86400000)
  if (dayDiff === 0) return `${time} today`
  if (dayDiff === 1) return `${time} yesterday`
  if (dayDiff < 7) return `${d.toLocaleDateString('en-US', { weekday: 'short' })} ${time}`
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}, ${time}`
}

export function DataFreshness() {
  const [data, setData] = useState<Freshness | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const refreshBaseline = useRef<string | null>(null)
  const refreshStartedAt = useRef<number>(0)

  const load = () =>
    fetch('/api/v1/ingestion/freshness', { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : null))
      .then((d: Freshness | null) => {
        if (!d) return
        setData(d)
        // refresh completes when the overall timestamp advances past the
        // value captured at click time (or we give up after the timeout)
        if (refreshBaseline.current !== null) {
          const advanced = d.overall && d.overall > refreshBaseline.current
          const timedOut = Date.now() - refreshStartedAt.current > REFRESH_TIMEOUT_MS
          if (advanced || timedOut) {
            refreshBaseline.current = null
            setRefreshing(false)
          }
        }
      })
      .catch(() => {})

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // tighter polling while a manual refresh is in flight
  useEffect(() => {
    if (!refreshing) return
    const id = setInterval(load, REFRESH_POLL_MS)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshing])

  const startRefresh = () => {
    if (refreshing || !data) return
    refreshBaseline.current = data.overall ?? ''
    refreshStartedAt.current = Date.now()
    setRefreshing(true)
    fetch('/api/v1/ingestion/refresh-now', { method: 'POST', headers: getAuthHeaders() })
      .then(r => { if (!r.ok) throw new Error() })
      .catch(() => {
        refreshBaseline.current = null
        setRefreshing(false)
      })
  }

  if (!data || !data.overall) return null

  const stale = data.status === 'stale'
  const tooltip = refreshing
    ? 'Full Robinhood sync running (~5–6 min) — the pill updates when fresh data lands'
    : [
        `Refresh schedule: ${data.schedule}`,
        `Positions/options: ${fmtTime(data.sources.options)}`,
        `Cash: ${fmtTime(data.sources.cash)}`,
        `Prices/holdings: ${fmtTime(data.sources.holdings)}`,
        `Last activity import: ${fmtTime(data.sources.activity)}`,
        stale ? `Expected a run at ${fmtTime(data.last_expected_run)} — check logs/refresh/ (MCP token? Mac asleep?)` : '',
        'Click to refresh now',
      ].filter(Boolean).join('\n')

  return (
    <button
      className={refreshing ? styles.pillRefreshing : stale ? styles.pillStale : styles.pill}
      title={tooltip}
      onClick={startRefresh}
      disabled={refreshing}
    >
      {stale && !refreshing
        ? <AlertTriangle size={12} />
        : <RefreshCw size={12} className={refreshing ? styles.spin : undefined} />}
      {refreshing
        ? 'Refreshing… (~5 min)'
        : stale
          ? `Refresh missed — data from ${fmtTime(data.overall)}`
          : `Data as of ${fmtTime(data.overall)}`}
    </button>
  )
}
