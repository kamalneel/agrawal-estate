import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './AssignmentLossCard.module.css'

const API_BASE = '/api/v1'

/**
 * Assignment Loss — Neel's idea, 2026-07-22.
 *
 * The only concrete, non-theoretical "loss" from a forced assignment is
 * the gap between the strike and the market price AT THE MOMENT OF
 * ASSIGNMENT — not cost-basis-vs-today (which drifts forever and bets
 * on recovery, a forecast not a fact). Deliberately shown separately
 * from premium (the Cash Goal above already counts that) rather than
 * netted — netting would double-count the same dollars in two places.
 */

interface AssignmentEvent {
  date: string
  month: string
  account_name: string
  symbol: string
  option_type: 'put' | 'call'
  strike: number
  price_at_assignment: number
  price_source: 'daily' | 'weekly'
  shares: number
  loss: number
  premium_collected: number
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

export function AssignmentLossCard() {
  const [data, setData] = useState<AssignmentLossData | null>(null)
  const [showEvents, setShowEvents] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/assignment-loss`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  if (!data || data.events.length === 0) return null

  const chartData = Object.entries(data.by_month).map(([month, loss]) => ({
    month, label: monthLabel(month), loss,
  }))
  const curMonth = new Date().toISOString().slice(0, 7)

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Assignment Loss</h3>
          <p className={styles.subtitle}>
            Strike vs. market price at the moment of forced assignment — the one concrete cost of an assignment,
            separate from premium (already counted in Cash Goal above) and separate from today's price, which just
            drifts and bets on recovery.
          </p>
        </div>
      </div>

      <div className={styles.statRow}>
        <div>
          <div className={styles.statValue} style={{ color: data.this_month_loss > 0 ? '#FF5A5A' : '#6b7280' }}>
            {data.this_month_loss > 0 ? `-${fmt(data.this_month_loss)}` : '$0'}
          </div>
          <div className={styles.statLabel}>this month</div>
        </div>
        <div>
          <div className={styles.statValue} style={{ color: '#FF5A5A' }}>-{fmt(data.total_loss)}</div>
          <div className={styles.statLabel}>all-time</div>
        </div>
        <div>
          <div className={styles.statValue} style={{ color: '#00D632' }}>{fmt(data.total_premium_on_assigned_contracts)}</div>
          <div className={styles.statLabel}>premium collected on these same contracts</div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#737373', fontSize: 11 }} axisLine={false} tickLine={false}
                 tickFormatter={(v: number) => v >= 1000 ? `$${Math.round(v / 1000)}K` : `$${v}`} />
          <Tooltip
            formatter={(v: number) => [`-${fmt(v)}`, 'Assignment loss']}
            contentStyle={{ background: '#1a1a1a', border: '1px solid #333', fontSize: 12 }}
          />
          <Bar dataKey="loss" radius={[3, 3, 0, 0]}>
            {chartData.map(d => (
              <Cell key={d.month} fill={d.month === curMonth ? '#FFB800' : '#FF5A5A'} />
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
                <th>Date</th><th>Account</th><th>Symbol</th><th>Type</th>
                <th className={styles.num}>Strike</th><th className={styles.num}>Price at assignment</th>
                <th className={styles.num}>Shares</th><th className={styles.num}>Loss</th>
                <th className={styles.num}>Premium collected</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={i}>
                  <td>{new Date(e.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}</td>
                  <td>{e.account_name}</td>
                  <td className={styles.symbol}>{e.symbol}</td>
                  <td>{e.option_type}</td>
                  <td className={styles.num}>${e.strike.toLocaleString()}</td>
                  <td className={styles.num}>
                    ${e.price_at_assignment.toLocaleString()}
                    {e.price_source === 'weekly' && <span className={styles.estFlag} title="Nearest weekly price, not the exact-day close">~</span>}
                  </td>
                  <td className={styles.num}>{e.shares.toLocaleString()}</td>
                  <td className={styles.num} style={{ color: '#FF5A5A' }}>-{fmt(e.loss)}</td>
                  <td className={styles.num} style={{ color: '#00D632' }}>{fmt(e.premium_collected)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
