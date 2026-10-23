import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
// Same section idiom as Put Campaigns directly above — one stylesheet.
import styles from '../PutCampaigns/PutCampaigns.module.css'

const API_BASE = '/api/v1'

/**
 * Covered Call Income — Neel, 2026-10-23. Calls on shares held to keep,
 * measured against holding the same shares without the calls:
 *
 *   Net = net premium (every sale − every buy-back, so roll losses are in)
 *         − upside given up (call assigned below the market that day)
 *
 * Open calls are not marked to their cost to close — that assumes exiting
 * today, which is not the plan (Neel, 2026-10-23).
 *
 * Shares that came from an assigned put are the Put Campaign's, so each
 * account's calls are counted in proportion to its bought shares
 * ("Covered %"). See covered_call_service.py.
 */

interface AccountPart {
  account_name: string
  covered_pct: number
  net_premium: number
  upside_given_up: number
  net: number
}

interface CallAssignment {
  date: string
  account_name: string
  strike: number
  price_at_assignment: number | null
  shares: number
  covered_pct: number
  upside_given_up: number | null
}

interface Stock {
  symbol: string
  covered_pct: number
  first: string | null
  net_premium: number
  upside_given_up: number
  net: number
  assignments: number
  unpriced_assignments: number
  accounts: AccountPart[]
  events: CallAssignment[]
}

interface Data {
  stocks: Stock[]
  totals: { net_premium: number; upside_given_up: number; net: number }
  unpriced_assignments: number
}

type SortKey = 'symbol' | 'covered_pct' | 'first' | 'net_premium' | 'upside_given_up' | 'net'

const COLUMNS: Array<[SortKey, string, string]> = [
  ['symbol', 'Stock', ''],
  ['covered_pct', 'Covered', 'Share of the calls counted here: bought shares ÷ all shares acquired. The rest were on shares from assigned puts — those belong to Put Campaigns.'],
  ['first', 'Since', 'First call sold on this stock'],
  ['net_premium', 'Net premium', 'Every call sold minus every call bought back — roll buy-backs, including any intrinsic paid, are already netted in'],
  ['upside_given_up', 'Upside given up', 'At each call assignment: (market that day − strike) × shares — what the shares were worth above the price you had to sell at'],
  ['net', 'Net', 'Net premium − upside given up: did selling calls earn more than it gave away?'],
]

const usd = (v: number) => `$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const signedUsd = (v: number | null) => v == null ? '—' : Math.round(v) === 0 ? '$0' : `${v < 0 ? '−' : '+'}${usd(v)}`
const minus = (v: number | null) => v == null ? '—' : Math.round(v) === 0 ? '—' : `−${usd(v)}`
const tone = (v: number | null) => v == null || Math.round(v) === 0 ? undefined : v < 0 ? styles.neg : styles.pos
const shortDate = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
const monthYear = (d: string | null) => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '—'

export function CoveredCallIncome() {
  const [data, setData] = useState<Data | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('net')
  const [sortDir, setSortDir] = useState<1 | -1>(1)

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/covered-call-income`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  if (!data || data.stocks.length === 0) return null

  const sort = (key: SortKey) => {
    if (key === sortKey) setSortDir(d => (d === 1 ? -1 : 1))
    else { setSortKey(key); setSortDir(1) }
  }
  const stocks = [...data.stocks].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * sortDir
    return ((va as number) - (vb as number)) * sortDir
  })
  const t = data.totals

  return (
    <section id="covered-call-income" className={styles.section}>
      <h2 className={styles.title}>Covered Call Income</h2>
      <p className={styles.subtitle}>
        Calls sold on shares you hold to keep, against simply holding those shares. <strong>Net premium</strong> is
        every call sold minus every call bought back. <strong>Upside given up</strong> is what the shares were worth
        above the strike when a call was assigned. <strong>Net</strong>: did selling calls earn more than it gave away? Shares that came from an
        assigned put are left to Put Campaigns, so a stock held both ways counts only its bought share ("Covered").
      </p>

      <div className={styles.card}>
        <div className={styles.statRow}>
          <div>
            <div className={clsx(styles.statValue, tone(t.net_premium))}>{signedUsd(t.net_premium)}</div>
            <div className={styles.statLabel}>net premium, after buy-backs</div>
          </div>
          <div>
            <div className={clsx(styles.statValue, styles.neg)}>{minus(t.upside_given_up)}</div>
            <div className={styles.statLabel}>upside given up at call assignments</div>
          </div>
          <div>
            <div className={clsx(styles.statValue, tone(t.net))}>{signedUsd(t.net)}</div>
            <div className={styles.statLabel}>net vs. holding without calls</div>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {COLUMNS.map(([key, label, hint]) => (
                  <th key={key} className={key === 'symbol' ? styles.left : undefined} title={hint || undefined}>
                    <button className={styles.thBtn} onClick={() => sort(key)}>
                      {label}
                      {sortKey === key && <span className={styles.sortArrow}>{sortDir === 1 ? '▲' : '▼'}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stocks.map(s => (
                <Fragment key={s.symbol}>
                  <tr className={styles.row} onClick={() => setOpen(o => (o === s.symbol ? null : s.symbol))}>
                    <td className={clsx(styles.left, styles.symbol)}>
                      {open === s.symbol ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      {s.symbol}
                    </td>
                    <td className={styles.num}>{s.covered_pct < 99.95 ? `${Math.round(s.covered_pct)}%` : 'all'}</td>
                    <td className={styles.num}>{monthYear(s.first)}</td>
                    <td className={clsx(styles.num, tone(s.net_premium))}>{signedUsd(s.net_premium)}</td>
                    <td className={clsx(styles.num, Math.round(s.upside_given_up) ? styles.neg : undefined)}>
                      {minus(s.upside_given_up)}
                      {s.assignments > 0 && <span className={styles.dim}> ({s.assignments})</span>}
                      {s.unpriced_assignments > 0 && <span className={styles.flag} title={`${s.unpriced_assignments} assignment(s) have no market price that day and are left out`}>⚠</span>}
                    </td>
                    <td className={clsx(styles.num, styles.strong, tone(s.net))}>{signedUsd(s.net)}</td>
                  </tr>
                  {open === s.symbol && (
                    <>
                      {s.accounts.map(a => (
                        <tr key={a.account_name} className={styles.detail}>
                          <td className={styles.left}>{a.account_name}</td>
                          <td className={styles.num}>{a.covered_pct < 99.95 ? `${Math.round(a.covered_pct)}%` : 'all'}</td>
                          <td />
                          <td className={clsx(styles.num, tone(a.net_premium))}>{signedUsd(a.net_premium)}</td>
                          <td className={styles.num}>{minus(a.upside_given_up)}</td>
                          <td className={clsx(styles.num, tone(a.net))}>{signedUsd(a.net)}</td>
                        </tr>
                      ))}
                      {s.events.map((e, i) => (
                        <tr key={`e${i}`} className={styles.detail}>
                          <td className={styles.left} colSpan={4}>
                            Assigned {shortDate(e.date)} · {e.account_name} · {e.shares.toLocaleString()} sh at ${e.strike.toFixed(2)}
                            {e.price_at_assignment != null && <> while the market was ${e.price_at_assignment.toFixed(2)}</>}
                            {e.covered_pct < 99.95 && <span className={styles.dim}> · {Math.round(e.covered_pct)}% counted</span>}
                          </td>
                          <td className={styles.num}>{minus(e.upside_given_up)}</td>
                          <td />
                        </tr>
                      ))}
                    </>
                  )}
                </Fragment>
              ))}
              <tr className={styles.totalRow}>
                <td className={styles.left}>Total</td>
                <td colSpan={2} />
                <td className={clsx(styles.num, tone(t.net_premium))}>{signedUsd(t.net_premium)}</td>
                <td className={clsx(styles.num, styles.neg)}>{minus(t.upside_given_up)}</td>
                <td className={clsx(styles.num, styles.strong, tone(t.net))}>{signedUsd(t.net)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className={styles.footnote}>
          Upside given up is an opportunity cost, not money lost: the shares sold at the strike, and the market would
          have paid more that day. Covered % is by share count, not by how long each share was held, so for a stock
          held both ways the split is an approximation. Calls still open count at the premium received; if one is assigned above the
          market, that shows up here when it happens.
        </p>
      </div>
    </section>
  )
}
