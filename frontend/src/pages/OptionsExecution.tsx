import { useState, useEffect, useMemo } from 'react'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../contexts/AuthContext'
import { GoalsStrip } from '../components/GoalsStrip/GoalsStrip'
import { accountRank } from '../lib/accountOrder'
import styles from './OptionsExecution.module.css'

const API_BASE = '/api/v1'

/** Options Execution — docs/OPTIONS-EXECUTION-PAGE-SPEC.md.
 *  L1 week+pace · L2 V6 action queue · L3 open positions board. */

interface QueueItem {
  id: string
  priority: 'urgent' | 'high' | 'medium' | 'low'
  action: string
  engine: number
  rule: string
  title: string
  account: string
  symbol: string
  detail: string
  why: string
  earn: number | null
}

interface BoardRow {
  account: string
  symbol: string
  type: string
  strike: number
  expiration: string | null
  dte: number
  contracts: number
  stock_price: number | null
  price_estimated: boolean
  current_mark: number
  original_premium: number
  capture_pct: number | null
  itm: boolean
}

interface Queue {
  generated_at: string
  data_as_of: string | null
  week_ending: string
  summary: { urgent: number; high: number; medium: number; low: number; total: number }
  items: QueueItem[]
  positions: BoardRow[]
}

const PRIORITY_COLOR: Record<string, string> = {
  urgent: '#dc2626', high: '#d97706', medium: '#2563eb', low: '#6b7280',
}
const ACTION_COLOR: Record<string, string> = {
  SELL: '#00D632', ROLL: '#00A3FF', CLOSE: '#A855F7', ALERT: '#FFB800',
}

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function OptionsExecution() {
  const [queue, setQueue] = useState<Queue | null>(null)
  const [weekOptions, setWeekOptions] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [showLow, setShowLow] = useState(false)
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)

  // Goals strip data (same cluster the Income page uses)
  const [goalSettings, setGoalSettings] = useState<any>(null)
  const [putCapacity, setPutCapacity] = useState<Record<string, { capacity: number; partial: boolean }>>({})
  const [optionsByType, setOptionsByType] = useState<Record<string, { calls: number; puts: number }>>({})
  const [dividendsByMonth, setDividendsByMonth] = useState<Record<string, number>>({})
  const [equityByMonth, setEquityByMonth] = useState<Record<string, number>>({})
  const [liveEquity, setLiveEquity] = useState<number | null>(null)

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [queueRes, unifiedRes, goalRes, capRes, byTypeRes, divChartRes, posRes, holdRes] = await Promise.all([
        fetch(`${API_BASE}/strategies/v6/action-queue`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/unified?granularity=week`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/goal-settings`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/put-capacity`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/by-type`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/dividends/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/monthly-positions`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/holdings/live`, { headers: getAuthHeaders() }),
      ])
      if (queueRes.ok) {
        const q: Queue = await queueRes.json()
        setQueue(q)
        if (unifiedRes.ok) {
          const u = await unifiedRes.json()
          const wk = (u.periods || []).find((p: any) => p.period === q.week_ending)
          setWeekOptions(wk ? (wk.by_source.options || 0) : 0)
        }
      }
      if (goalRes.ok) setGoalSettings(await goalRes.json())
      if (capRes.ok) {
        const d = await capRes.json()
        setPutCapacity(Object.fromEntries((d.months || []).map((m: any) => [m.month, { capacity: m.capacity, partial: m.partial }])))
      }
      if (byTypeRes.ok) setOptionsByType(await byTypeRes.json())
      if (divChartRes.ok) {
        const d = await divChartRes.json()
        setDividendsByMonth(Object.fromEntries((d.data || []).map((x: any) => [x.month, x.value])))
      }
      if (posRes.ok) {
        const d = await posRes.json()
        setEquityByMonth(d.equity || {})
      }
      if (holdRes.ok) {
        const d = await holdRes.json()
        setLiveEquity((d.accounts || []).reduce((s: number, a: any) => s + (a.value || 0), 0))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  const now = new Date()

  // Per-account breakdown — union of accounts appearing in the queue and
  // the position board, canonical order, with priority counts so the
  // filter strip doubles as a per-account triage summary.
  const accountSummaries = useMemo(() => {
    if (!queue) return []
    const names = new Set<string>()
    queue.items.forEach(i => names.add(i.account))
    queue.positions.forEach(p => names.add(p.account))
    const rows = [...names].map(name => {
      const items = queue.items.filter(i => i.account === name && !dismissed.has(i.id))
      const positions = queue.positions.filter(p => p.account === name)
      return {
        name,
        urgent: items.filter(i => i.priority === 'urgent').length,
        high: items.filter(i => i.priority === 'high').length,
        total: items.length,
        positions: positions.length,
      }
    })
    rows.sort((a, b) => accountRank(a.name) - accountRank(b.name))
    return rows
  }, [queue, dismissed])

  const visibleItems = useMemo(() => {
    if (!queue) return []
    return queue.items.filter(i =>
      !dismissed.has(i.id) &&
      (showLow || i.priority !== 'low') &&
      (selectedAccount === null || i.account === selectedAccount))
  }, [queue, dismissed, showLow, selectedAccount])

  const byExpiry = useMemo(() => {
    const g = new Map<string, BoardRow[]>()
    for (const p of queue?.positions || []) {
      if (selectedAccount !== null && p.account !== selectedAccount) continue
      const k = p.expiration || 'no expiry'
      if (!g.has(k)) g.set(k, [])
      g.get(k)!.push(p)
    }
    return [...g.entries()].map(([exp, rows]) => ({
      exp,
      rows: rows.sort((a, b) => accountRank(a.account) - accountRank(b.account) || a.symbol.localeCompare(b.symbol)),
    }))
  }, [queue, selectedAccount])

  if (loading && !queue) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}><RefreshCw size={28} className={styles.spinner} /> Loading…</div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      {/* L1 — this week + pace */}
      <section className={styles.headerBand}>
        <div>
          <h1 className={styles.title}>Options Execution</h1>
          <div className={styles.weekLine}>
            Week ending {queue ? new Date(queue.week_ending + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '—'}
            <span className={styles.weekPremium}>
              {weekOptions !== null ? <>premium this week: <strong style={{ color: weekOptions < 0 ? '#FF5A5A' : '#00D632' }}>{fmt(weekOptions)}</strong></> : null}
            </span>
          </div>
          {queue?.data_as_of && (
            <div className={styles.dataAsOf}>data as of {new Date(queue.data_as_of).toLocaleString()}</div>
          )}
        </div>
        <button onClick={fetchAll} className={styles.refresh} title="Refresh"><RefreshCw size={18} /></button>
      </section>

      <GoalsStrip
        year={now.getFullYear()}
        month={now.getMonth() + 1}
        capacityByMonth={putCapacity}
        optionsByType={optionsByType}
        dividendsByMonth={dividendsByMonth}
        equityByMonth={equityByMonth}
        liveEquity={liveEquity}
        settings={goalSettings}
      />

      {/* Account filter — scopes both the Action Queue and the Open
          Positions board below; doubles as a per-account triage summary. */}
      {accountSummaries.length > 0 && (
        <section className={styles.acctFilterSection}>
          <div className={styles.acctFilterRow}>
            <button
              className={clsx(styles.acctPill, selectedAccount === null && styles.acctPillActive)}
              onClick={() => setSelectedAccount(null)}
            >
              <span className={styles.acctPillName}>All Accounts</span>
              <span className={styles.acctPillCount}>{queue?.summary.total ?? 0}</span>
            </button>
            {accountSummaries.map(a => (
              <button
                key={a.name}
                className={clsx(styles.acctPill, selectedAccount === a.name && styles.acctPillActive)}
                onClick={() => setSelectedAccount(selectedAccount === a.name ? null : a.name)}
                title={`${a.positions} open position${a.positions === 1 ? '' : 's'}`}
              >
                {a.urgent > 0 && <span className={styles.acctDot} style={{ background: PRIORITY_COLOR.urgent }} />}
                {a.urgent === 0 && a.high > 0 && <span className={styles.acctDot} style={{ background: PRIORITY_COLOR.high }} />}
                <span className={styles.acctPillName}>{a.name}</span>
                <span className={styles.acctPillCount}>{a.total}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* L2 — action queue */}
      <section className={styles.queueSection}>
        <div className={styles.queueHeader}>
          <h2>Action Queue{selectedAccount ? ` — ${selectedAccount}` : ''}</h2>
          {queue && (
            <div className={styles.summaryStrip}>
              <strong>{visibleItems.length} recommendation{visibleItems.length === 1 ? '' : 's'}</strong>
              {(() => {
                const urgent = selectedAccount ? accountSummaries.find(a => a.name === selectedAccount)?.urgent ?? 0 : queue.summary.urgent
                const high = selectedAccount ? accountSummaries.find(a => a.name === selectedAccount)?.high ?? 0 : queue.summary.high
                return <>
                  {urgent > 0 && <span className={clsx(styles.badge, styles.badgeUrgent)}>{urgent} URGENT</span>}
                  {high > 0 && <span className={clsx(styles.badge, styles.badgeHigh)}>{high} HIGH</span>}
                </>
              })()}
              <span className={styles.engineTag}>{queue ? 'V6.1 · engines 4+1' : ''}</span>
              <button className={styles.lowToggle} onClick={() => setShowLow(v => !v)}>
                {showLow ? 'hide low priority' : `show low priority (${queue.summary.low})`}
              </button>
              {selectedAccount && (
                <button className={styles.lowToggle} onClick={() => setSelectedAccount(null)}>
                  clear account filter ✕
                </button>
              )}
            </div>
          )}
        </div>

        <div className={styles.queueList}>
          {visibleItems.map(item => (
            <div key={item.id} className={styles.queueItem}>
              <button className={styles.itemRow} onClick={() => setExpanded(expanded === item.id ? null : item.id)}>
                <span className={styles.dot} style={{ background: PRIORITY_COLOR[item.priority] }} />
                <span className={styles.actionBadge} style={{ color: ACTION_COLOR[item.action] || '#fff', borderColor: ACTION_COLOR[item.action] || '#444' }}>
                  {item.action}
                </span>
                <span className={styles.itemSymbol}>{item.symbol}</span>
                <span className={styles.itemAccount}>{item.account}</span>
                <span className={styles.itemDetail}>
                  {item.detail.startsWith(item.symbol + ' ') ? item.detail.slice(item.symbol.length + 1) : item.detail}
                </span>
                {item.earn ? <span className={styles.earn}>Earn ~{fmt(item.earn)}</span> : null}
                {expanded === item.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              {expanded === item.id && (
                <div className={styles.why}>
                  <div className={styles.whyRule}>Engine {item.engine} — {item.rule}</div>
                  <p>{item.why}</p>
                  <button className={styles.dismiss} onClick={() => setDismissed(s => new Set(s).add(item.id))}>
                    Dismiss for today
                  </button>
                </div>
              )}
            </div>
          ))}
          {visibleItems.length === 0 && <div className={styles.empty}>Nothing needs action. 🎉</div>}
        </div>
      </section>

      {/* L3 — open positions board */}
      <section className={styles.boardSection}>
        <h2>Open Positions{selectedAccount ? ` — ${selectedAccount}` : ''}</h2>
        {byExpiry.map(({ exp, rows }) => (
          <div key={exp} className={styles.expiryGroup}>
            <div className={styles.expiryHeader}>
              {exp !== 'no expiry'
                ? <>Expires {new Date(exp + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                    <span className={styles.dteTag}>{rows[0].dte}d</span></>
                : 'No expiry'}
              <span className={styles.groupCount}>{rows.reduce((s, r) => s + r.contracts, 0)} contracts</span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Account</th><th>Symbol</th><th>Type</th>
                    <th className={styles.num}>Strike</th>
                    <th className={styles.num}>Stock</th>
                    <th className={styles.num}>Mark</th>
                    <th className={styles.num}>Collected</th>
                    <th className={styles.num}>Capture</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const near = !r.itm && r.stock_price != null &&
                      Math.abs(r.stock_price - r.strike) / r.strike < 0.03
                    const status = r.itm ? 'ITM' : near ? 'NEAR' : 'OTM'
                    const color = r.itm ? '#FF5A5A' : near ? '#FFB800' : '#00D632'
                    return (
                      <tr key={i}>
                        <td>{r.account}</td>
                        <td className={styles.sym}>{r.symbol}</td>
                        <td>{r.contracts}x {r.type.toUpperCase()}</td>
                        <td className={styles.num}>${r.strike.toLocaleString()}</td>
                        <td className={styles.num}>
                          {r.stock_price != null ? `$${r.stock_price.toLocaleString('en-US', { maximumFractionDigits: 0 })}${r.price_estimated ? '~' : ''}` : '—'}
                        </td>
                        <td className={styles.num}>${r.current_mark.toFixed(2)}</td>
                        <td className={styles.num}>${r.original_premium.toFixed(2)}</td>
                        <td className={styles.num} style={{ color: r.capture_pct == null ? undefined : r.capture_pct < 0 ? '#FF5A5A' : '#00D632' }}>
                          {r.capture_pct != null ? `${r.capture_pct.toFixed(0)}%` : '—'}
                        </td>
                        <td><span className={styles.status} style={{ color, borderColor: color }}>{status}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}
