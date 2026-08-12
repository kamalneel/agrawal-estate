import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './AssignmentLossCard.module.css'

const API_BASE = '/api/v1'

/**
 * Assignment Loss — Neel's idea, 2026-07-22. Redefined 2026-08-08.
 *
 * PUT loss: strike vs. market price AT THE MOMENT OF ASSIGNMENT — a put
 * assignment creates a brand-new lot, so there's no prior purchase price
 * to compare against; strike-vs-market-that-moment is the only real
 * "did I overpay" question, and it's always >= 0 (filtered server-side).
 *
 * CALL loss: cost basis vs. strike — what the shares actually cost vs.
 * what they were forced to sell for. SIGNED: a call assigned above cost
 * is a real gain, shown as one (not clamped to zero like puts). The
 * strike-vs-market version doesn't answer "did I lose money" for a call
 * (Neel, 2026-08-08, re: an $89 SPCX example that wasn't a real loss).
 *
 * Both deliberately exclude premium (the Cash Goal card above already
 * counts that) — netting here would double-count the same dollars in
 * the opposite direction. Premium is still shown alongside for context —
 * as the TRUE NET across the whole roll chain (every STO open minus every
 * BTC close, back to the first sale), not just the final contract's own
 * STO (Neel, 2026-08-12: a $9,005 figure turned out to be one transaction,
 * not a total of what was actually collected while rolling week over week).
 */

interface AssignmentEvent {
  date: string
  month: string
  account_name: string
  symbol: string
  option_type: 'put' | 'call'
  strike: number
  price_at_assignment: number | null
  price_source: 'daily' | 'weekly' | null
  shares: number
  loss: number
  premium_collected: number
  premium_chain_weeks: number
  premium_incomplete: boolean
  cost_basis_per_share: number | null
  cost_basis_source: 'live' | 'reconstructed' | null
  cost_basis_incomplete: boolean | null
}

interface AssignmentLossData {
  events: AssignmentEvent[]
  by_month: Record<string, number>
  this_month_loss: number
  total_loss: number
  total_premium_on_assigned_contracts: number
  skipped_no_price_data: number
}

function fmt(v: number): string {
  return `$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
}

type EventSortKey = 'date' | 'account_name' | 'symbol' | 'option_type' | 'strike'
  | 'price_at_assignment' | 'shares' | 'cost_basis_per_share' | 'loss' | 'premium_collected'

function eventSortValue(e: AssignmentEvent, key: EventSortKey): number | string | null {
  return e[key]
}

function compareEvents(a: AssignmentEvent, b: AssignmentEvent, key: EventSortKey, dir: 1 | -1): number {
  const va = eventSortValue(a, key)
  const vb = eventSortValue(b, key)
  // price_at_assignment / cost_basis_per_share are null on some rows
  // (calls skip price lookup; puts have no cost basis) — sort those to
  // the end regardless of direction, same as other nullable columns.
  if (va == null && vb == null) return 0
  if (va == null) return 1
  if (vb == null) return -1
  if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * dir
  return ((va as number) - (vb as number)) * dir
}

const EVENT_COLUMNS: Array<[EventSortKey, string]> = [
  ['date', 'Date'], ['account_name', 'Account'], ['symbol', 'Symbol'], ['option_type', 'Type'],
  ['strike', 'Strike'], ['price_at_assignment', 'Price at assignment'], ['shares', 'Shares'],
  ['cost_basis_per_share', 'Cost basis'], ['loss', 'Loss'], ['premium_collected', 'Premium collected (net, all rolls)'],
]

export function AssignmentLossCard() {
  const [data, setData] = useState<AssignmentLossData | null>(null)
  const [showEvents, setShowEvents] = useState(false)
  const [sortKey, setSortKey] = useState<EventSortKey | null>(null)
  const [sortDir, setSortDir] = useState<1 | -1>(1)

  const handleSort = (key: EventSortKey) => {
    if (sortKey === key) setSortDir(d => (d === 1 ? -1 : 1))
    else { setSortKey(key); setSortDir(1) }
  }

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  // Arriving via the Options Execution card's link (#assignment-loss) —
  // scroll to this card and open the events table straight away.
  useEffect(() => {
    if (window.location.hash === '#assignment-loss') {
      setShowEvents(true)
      document.getElementById('assignment-loss')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [data])

  if (!data || data.events.length === 0) return null

  const chartData = Object.entries(data.by_month).map(([month, loss]) => ({
    month, label: monthLabel(month), loss,
  }))
  const curMonth = new Date().toISOString().slice(0, 7)

  const sortedEvents = sortKey
    ? [...data.events].sort((a, b) => compareEvents(a, b, sortKey, sortDir))
    : data.events

  return (
    <section id="assignment-loss" className={styles.card}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Assignment Loss</h3>
          <p className={styles.subtitle}>
            Puts: strike vs. market price at the moment of forced assignment (a put creates a new lot, so market-that-moment
            is the real comparison). Calls: cost basis vs. strike — what the shares cost vs. what they sold for, signed
            (a call assigned above cost is a real gain, shown as one). Both exclude premium, already counted in Cash Goal above.
          </p>
        </div>
      </div>

      <div className={styles.statRow}>
        <div>
          <div className={styles.statValue} style={{ color: data.this_month_loss === 0 ? '#6b7280' : data.this_month_loss > 0 ? '#FF5A5A' : '#00D632' }}>
            {data.this_month_loss === 0 ? '$0' : `${data.this_month_loss > 0 ? '-' : '+'}${fmt(data.this_month_loss)}`}
          </div>
          <div className={styles.statLabel}>this month</div>
        </div>
        <div>
          <div className={styles.statValue} style={{ color: data.total_loss >= 0 ? '#FF5A5A' : '#00D632' }}>
            {data.total_loss >= 0 ? '-' : '+'}{fmt(data.total_loss)}
          </div>
          <div className={styles.statLabel}>all-time</div>
        </div>
        <div>
          <div className={styles.statValue} style={{ color: '#00D632' }}>{fmt(data.total_premium_on_assigned_contracts)}</div>
          <div className={styles.statLabel}>net premium collected across every roll of these positions</div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false}
                 tickFormatter={(v: number) => Math.abs(v) >= 1000 ? `${v < 0 ? '-' : ''}$${Math.round(Math.abs(v) / 1000)}K` : `$${v}`} />
          <Tooltip
            formatter={(v: number) => [`${v >= 0 ? '-' : '+'}${fmt(v)}`, v >= 0 ? 'Assignment loss' : 'Assignment gain']}
            contentStyle={{ background: '#1a1a1a', border: '1px solid #333', fontSize: 12 }}
          />
          <Bar dataKey="loss" radius={[3, 3, 0, 0]}>
            {chartData.map(d => (
              <Cell key={d.month} fill={d.loss < 0 ? '#00D632' : d.month === curMonth ? '#FFB800' : '#FF5A5A'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <button className={styles.toggle} onClick={() => setShowEvents(v => !v)}>
        {showEvents ? 'hide' : 'show'} the {data.events.length} assignment event{data.events.length === 1 ? '' : 's'} behind this
        {showEvents ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {showEvents && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {EVENT_COLUMNS.map(([key, label]) => (
                  <th key={key} className={styles.num}>
                    <button className={styles.thBtn} onClick={() => handleSort(key)}>
                      {label}
                      {sortKey === key && <span className={styles.sortArrow}>{sortDir === 1 ? '▲' : '▼'}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedEvents.map((e, i) => (
                <tr key={i}>
                  <td>{new Date(e.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}</td>
                  <td>{e.account_name}</td>
                  <td className={styles.symbol}>{e.symbol}</td>
                  <td>{e.option_type}</td>
                  <td className={styles.num}>${e.strike.toFixed(2)}</td>
                  <td className={styles.num}>
                    {e.price_at_assignment == null ? '—' : (
                      <>
                        ${e.price_at_assignment.toFixed(2)}
                        {e.price_source === 'weekly' && <span className={styles.estFlag} title="Nearest available symbol-level close — used when it lands closer to the assignment date than this account's own held-share price history (e.g. shares briefly at zero around the assignment)">~</span>}
                      </>
                    )}
                  </td>
                  <td className={styles.num}>{e.shares.toLocaleString()}</td>
                  <td className={styles.num}>
                    {e.cost_basis_per_share == null ? '—' : (
                      <>
                        ${e.cost_basis_per_share.toFixed(2)}
                        <span
                          className={styles.estFlag}
                          title={
                            (e.cost_basis_source === 'reconstructed' ? 'Reconstructed from buy history, not Robinhood-reported' : 'Robinhood-reported average cost')
                            + (e.cost_basis_incomplete ? '. Incomplete: buy history falls short of shares assigned, treat as an estimate.' : '')
                          }
                        >
                          {e.cost_basis_incomplete ? '⚠' : e.cost_basis_source === 'reconstructed' ? '~' : ''}
                        </span>
                      </>
                    )}
                  </td>
                  <td className={styles.num} style={{ color: e.loss >= 0 ? '#FF5A5A' : '#00D632' }}>
                    {e.loss >= 0 ? '-' : '+'}{fmt(e.loss)}
                  </td>
                  <td className={styles.num} style={{ color: '#00D632' }}>
                    {fmt(e.premium_collected)}
                    {e.premium_chain_weeks > 1 && (
                      <span className={styles.estFlag} title={`Net of every open (STO) and close (BTC) across ${e.premium_chain_weeks} weekly rolls, not just the final contract's own premium.`}>
                        {` (${e.premium_chain_weeks}wk)`}
                      </span>
                    )}
                    {e.premium_incomplete && (
                      <span className={styles.estFlag} title="This account's transaction history has a gap further back — an earlier leg was closed but its own opening sale is missing from the ledger, so the chain stops here. The true total (if the full history existed) would extend earlier than this.">⚠</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
