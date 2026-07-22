import { useState, useEffect, useMemo } from 'react'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../contexts/AuthContext'
import { GoalsStrip } from '../components/GoalsStrip/GoalsStrip'
import { AssignmentLossCard } from '../components/AssignmentLossCard/AssignmentLossCard'
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
  context?: {
    next_earnings?: { date: string; timing: string | null; days: number; verified: boolean }
    entry_timing?: { rsi: number | null; wait: boolean; reason: string | null;
                     consecutive_down_days: number | null; change_pct: number | null }
    roll_streak?: { weeks_rolled: number; trend: 'worsening' | 'stable' | 'improving' | null;
                    itm_pct_at_start?: number; itm_pct_now?: number }
    [key: string]: unknown
  }
}

function fmtEarningsDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return `${d.getMonth() + 1}/${d.getDate()}`
}

interface BoardRow {
  account: string
  symbol: string
  type: string
  strike: number | null
  expiration: string | null
  dte: number | null
  contracts: number
  stock_price: number | null
  price_estimated: boolean
  current_mark: number | null
  original_premium: number | null
  capture_pct: number | null
  itm: boolean
  uncovered?: boolean
  uncovered_shares?: number
  uncovered_cash?: number
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
const HOLD_COLOR = '#FACC15'

/** SELL badge reads "HOLD" in yellow when the real entry-timing check
 * says wait (Neel, 2026-07-22: seeing a green "Earn ~$X" SELL badge next
 * to a red WAIT flag read as contradictory — the action badge itself
 * should reflect the caution, not just a smaller badge beside it). */
function displayAction(item: QueueItem): { label: string; color: string } {
  if (item.action === 'SELL' && item.context?.entry_timing?.wait) {
    return { label: 'HOLD', color: HOLD_COLOR }
  }
  return { label: item.action, color: ACTION_COLOR[item.action] || '#fff' }
}
const PRIORITY_RANK: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 }

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function statusOf(r: BoardRow): string {
  if (r.uncovered) return r.uncovered_cash != null ? 'AVAILABLE' : 'NOT SOLD'
  const near = !r.itm && r.stock_price != null && r.strike != null &&
    Math.abs(r.stock_price - r.strike) / r.strike < 0.03
  return r.itm ? 'ITM' : near ? 'NEAR' : 'OTM'
}

type BoardSortKey = 'account' | 'symbol' | 'type' | 'expiry' | 'strike' | 'stock' | 'mark' | 'collected' | 'capture' | 'status'

function boardSortValue(r: BoardRow, key: BoardSortKey): number | string | null {
  switch (key) {
    case 'account': return accountRank(r.account)
    case 'symbol': return r.symbol
    case 'type': return r.uncovered_cash ?? r.contracts
    case 'expiry': return r.expiration
    case 'strike': return r.strike
    case 'stock': return r.stock_price
    case 'mark': return r.current_mark
    case 'collected': return r.original_premium
    case 'capture': return r.capture_pct
    case 'status': return statusOf(r)
  }
}

function compareBoardRows(a: BoardRow, b: BoardRow, key: BoardSortKey, dir: 1 | -1): number {
  const va = boardSortValue(a, key)
  const vb = boardSortValue(b, key)
  if (va == null && vb == null) return 0
  if (va == null) return 1
  if (vb == null) return -1
  if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * dir
  return ((va as number) - (vb as number)) * dir
}

export function OptionsExecution() {
  const [queue, setQueue] = useState<Queue | null>(null)
  const [weekOptions, setWeekOptions] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [showLow, setShowLow] = useState(false)
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [queueSortBy, setQueueSortBy] = useState<'priority' | 'account'>('priority')
  const [boardSortKey, setBoardSortKey] = useState<BoardSortKey | null>(null)
  const [boardSortDir, setBoardSortDir] = useState<1 | -1>(1)

  const handleBoardSort = (key: BoardSortKey) => {
    if (boardSortKey === key) setBoardSortDir(d => (d === 1 ? -1 : 1))
    else { setBoardSortKey(key); setBoardSortDir(1) }
  }

  // Goals strip data (same cluster the Income page uses)
  const [goalSettings, setGoalSettings] = useState<any>(null)
  const [putCapacity, setPutCapacity] = useState<Record<string, { capacity: number; partial: boolean }>>({})
  const [optionsByType, setOptionsByType] = useState<Record<string, { calls: number; puts: number }>>({})
  const [dividendsByMonth, setDividendsByMonth] = useState<Record<string, number>>({})
  const [equityByMonth, setEquityByMonth] = useState<Record<string, number>>({})
  const [liveEquity, setLiveEquity] = useState<number | null>(null)
  const [allAccountNames, setAllAccountNames] = useState<string[]>([])

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [queueRes, unifiedRes, goalRes, capRes, byTypeRes, divChartRes, posRes, holdRes, acctRes] = await Promise.all([
        fetch(`${API_BASE}/strategies/v6/action-queue`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/unified?granularity=week`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/goal-settings`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/put-capacity`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/options/by-type`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/dividends/chart`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/income/monthly-positions`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/holdings/live`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/investments/accounts`, { headers: getAuthHeaders() }),
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
      if (acctRes.ok) {
        const d = await acctRes.json()
        setAllAccountNames((d.accounts || []).map((a: any) => a.name))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  const now = new Date()

  // Per-account breakdown — every active account (from /investments/accounts,
  // so an account with nothing to do still gets a pill instead of silently
  // vanishing) union'd with whatever appears in the queue/board, canonical
  // order, with priority counts so the filter strip doubles as a
  // per-account triage summary.
  const accountSummaries = useMemo(() => {
    if (!queue) return []
    const names = new Set<string>(allAccountNames)
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
  }, [queue, dismissed, allAccountNames])

  const visibleItems = useMemo(() => {
    if (!queue) return []
    const filtered = queue.items.filter(i =>
      !dismissed.has(i.id) &&
      (showLow || i.priority !== 'low') &&
      (selectedAccount === null || i.account === selectedAccount))
    if (queueSortBy === 'account') {
      // stable sort: within an account, keep the backend's smart order
      // (priority -> actionable-first -> soonest expiry)
      return [...filtered].sort((a, b) => accountRank(a.account) - accountRank(b.account))
    }
    return filtered // backend order: priority -> actionable-first -> expiry -> account -> symbol
  }, [queue, dismissed, showLow, selectedAccount, queueSortBy])

  // Calls / Puts grouping, always — this is how a call book vs. a put
  // wheel actually gets managed, whether viewing one account or all of
  // them. Expiry is a per-row column rather than the grouping key, so
  // uncovered ("not sold") rows sit naturally alongside sold calls.
  const boardGroups = useMemo(() => {
    const rowsForAccount = (queue?.positions || []).filter(
      p => selectedAccount === null || p.account === selectedAccount)

    const calls = rowsForAccount.filter(p => p.type === 'call')
    const puts = rowsForAccount.filter(p => p.type === 'put')
    const byAcctExpirySymbol = (a: BoardRow, b: BoardRow) =>
      accountRank(a.account) - accountRank(b.account)
      || (a.expiration || '').localeCompare(b.expiration || '')
      || a.symbol.localeCompare(b.symbol)
    return [
      { key: 'call', label: 'Calls', rows: calls.sort(byAcctExpirySymbol) },
      { key: 'put', label: 'Puts', rows: puts.sort(byAcctExpirySymbol) },
    ].filter(g => g.rows.length > 0)
  }, [queue, selectedAccount])

  // User-driven column sort overrides the default account/expiry/symbol
  // order above; shared across the Calls and Puts tables (same columns).
  const displayGroups = useMemo(() => {
    if (!boardSortKey) return boardGroups
    return boardGroups.map(g => ({
      ...g,
      rows: [...g.rows].sort((a, b) => compareBoardRows(a, b, boardSortKey, boardSortDir)),
    }))
  }, [boardGroups, boardSortKey, boardSortDir])

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
        <button onClick={fetchAll} className={styles.refresh} title="Refresh" disabled={loading}>
          <RefreshCw size={18} className={loading ? styles.spinner : undefined} />
        </button>
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

      {/* Third pacing panel, Neel's idea 2026-07-22: the only concrete
          cost of a forced assignment is strike vs. market price AT THE
          MOMENT of assignment — not cost-basis-vs-today, which just
          drifts. Self-fetching, renders nothing if there's no history. */}
      <AssignmentLossCard />

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
              <div className={styles.sortToggle}>
                <span className={styles.sortToggleLabel}>Sort:</span>
                <button
                  className={clsx(styles.sortToggleBtn, queueSortBy === 'priority' && styles.sortToggleBtnActive)}
                  onClick={() => setQueueSortBy('priority')}
                >
                  Priority
                </button>
                <button
                  className={clsx(styles.sortToggleBtn, queueSortBy === 'account' && styles.sortToggleBtnActive)}
                  onClick={() => setQueueSortBy('account')}
                >
                  Account
                </button>
              </div>
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
                <span className={styles.actionBadge} style={{ color: displayAction(item).color, borderColor: displayAction(item).color }}>
                  {displayAction(item).label}
                </span>
                <span className={styles.itemSymbol}>{item.symbol}</span>
                <span className={styles.itemAccount}>{item.account}</span>
                <span className={styles.itemDetail}>
                  {item.detail.startsWith(item.symbol + ' ') ? item.detail.slice(item.symbol.length + 1) : item.detail}
                </span>
                {item.context?.next_earnings && (
                  <span
                    className={styles.earningsBadge}
                    title={`${item.symbol} reports ${item.context.next_earnings.date}${item.context.next_earnings.timing === 'pm' ? ' after close' : item.context.next_earnings.timing === 'am' ? ' before open' : ''}${item.context.next_earnings.verified ? '' : ' (unconfirmed)'} — premium through that date is event-inflated; IV crushes after the call`}
                  >
                    📅 ER {fmtEarningsDate(item.context.next_earnings.date)}
                  </span>
                )}
                {item.context?.entry_timing?.wait && (
                  <span className={styles.waitBadge} title={item.context.entry_timing.reason ?? undefined}>
                    ⏸ WAIT{item.context.entry_timing.rsi != null ? ` (RSI ${Math.round(item.context.entry_timing.rsi)})` : ''}
                  </span>
                )}
                {item.context?.roll_streak && item.context.roll_streak.weeks_rolled >= 2 && (
                  <span
                    className={item.context.roll_streak.trend === 'worsening' ? styles.streakBadgeWarn : styles.streakBadge}
                    title={
                      item.context.roll_streak.trend
                        ? `Rolled ${item.context.roll_streak.weeks_rolled} weeks running · ITM% ${item.context.roll_streak.itm_pct_at_start?.toFixed(0)}%→${item.context.roll_streak.itm_pct_now?.toFixed(0)}% (${item.context.roll_streak.trend})`
                        : `Rolled ${item.context.roll_streak.weeks_rolled} weeks running · not enough price history to judge trend`
                    }
                  >
                    {item.context.roll_streak.trend === 'worsening' ? '⚠' : '↻'} {item.context.roll_streak.weeks_rolled}wk roll
                  </span>
                )}
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

      {/* L3 — open positions board. All Accounts: grouped by expiry
          (triage). One account selected: grouped by Calls/Puts, with
          uncovered-holding rows included so the Calls group shows what's
          NOT sold alongside what is. */}
      <section className={styles.boardSection}>
        <h2>Open Positions{selectedAccount ? ` — ${selectedAccount}` : ''}</h2>
        {displayGroups.map(({ key, label, rows }) => (
          <div key={key} className={styles.expiryGroup}>
            <div className={styles.expiryHeader}>
              {label}
              <span className={styles.groupCount}>{rows.reduce((s, r) => s + r.contracts, 0)} contracts</span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    {([
                      ['account', 'Account', false], ['symbol', 'Symbol', false], ['type', 'Type', false],
                      ['expiry', 'Expiry', false], ['strike', 'Strike', true], ['stock', 'Stock', true],
                      ['mark', 'Mark', true], ['collected', 'Collected', true], ['capture', 'Capture', true],
                      ['status', 'Status', false],
                    ] as Array<[BoardSortKey, string, boolean]>).map(([k, label2, numeric]) => (
                      <th key={k} className={numeric ? styles.num : undefined}>
                        <button className={styles.thBtn} onClick={() => handleBoardSort(k)}>
                          {label2}
                          {boardSortKey === k && <span className={styles.sortArrow}>{boardSortDir === 1 ? '▲' : '▼'}</span>}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const status = statusOf(r)
                    if (r.uncovered) {
                      const isCash = r.uncovered_cash != null
                      return (
                        <tr key={i} className={styles.uncoveredRow}>
                          <td>{r.account}</td>
                          <td className={styles.sym}>{r.symbol}</td>
                          <td>
                            {isCash
                              ? `${fmt(r.uncovered_cash!)} available`
                              : `${(r.uncovered_shares ?? r.contracts * 100).toLocaleString()} sh · ${r.contracts}x lot`}
                          </td>
                          <td>—</td>
                          <td className={styles.num}>—</td>
                          <td className={styles.num}>
                            {r.stock_price != null ? `$${r.stock_price.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                          </td>
                          <td className={styles.num}>—</td>
                          <td className={styles.num}>—</td>
                          <td className={styles.num}>—</td>
                          <td><span className={styles.status} style={{ color: '#00D632', borderColor: '#00D632' }}>{status}</span></td>
                        </tr>
                      )
                    }
                    const color = r.itm ? '#FF5A5A' : status === 'NEAR' ? '#FFB800' : '#00D632'
                    return (
                      <tr key={i}>
                        <td>{r.account}</td>
                        <td className={styles.sym}>{r.symbol}</td>
                        <td>{r.contracts}x {r.type.toUpperCase()}</td>
                        <td>{r.expiration ? new Date(r.expiration + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</td>
                        <td className={styles.num}>{r.strike != null ? `$${r.strike.toLocaleString()}` : '—'}</td>
                        <td className={styles.num}>
                          {r.stock_price != null ? `$${r.stock_price.toLocaleString('en-US', { maximumFractionDigits: 0 })}${r.price_estimated ? '~' : ''}` : '—'}
                        </td>
                        <td className={styles.num}>{r.current_mark != null ? `$${r.current_mark.toFixed(2)}` : '—'}</td>
                        <td className={styles.num}>{r.original_premium != null ? `$${r.original_premium.toFixed(2)}` : '—'}</td>
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
