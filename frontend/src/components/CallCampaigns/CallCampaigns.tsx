import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
// The call half of the wheel view — same section idiom as Put Campaigns
// directly above, one stylesheet.
import styles from '../PutCampaigns/PutCampaigns.module.css'

const API_BASE = '/api/v1'

/**
 * Call Campaigns — the sibling of Put Campaigns (docs/OPTIONS-UX-AUDIT.md,
 * step 2, 2026-10-24; was "Covered Call Income", 2026-10-23). Calls on
 * shares bought to keep, measured against holding the same shares without
 * the calls:
 *
 *   Campaign = net premium (every sale − every buy-back, so roll losses are in)
 *              − upside given up (call assigned below the market that day)
 *
 * Upside is measured on the day of each assignment, not followed to today
 * (Neel, 2026-10-24: option (a)). Open calls are not marked to their cost
 * to close — that assumes exiting today, which is not the plan
 * (2026-10-23).
 *
 * Shares that came from an assigned put are the Put Campaign's, so each
 * account's calls are counted in proportion to its bought shares
 * ("Covered"). See covered_call_service.py.
 */

interface AccountPart {
  account_name: string
  covered_pct: number
  net_premium: number
  upside_given_up: number
  campaign: number
}

interface CallAssignment {
  date: string
  account_name: string
  strike: number
  price_at_assignment: number | null
  shares: number
  covered_pct: number
  upside_given_up: number | null
  chain_premium: number
  chain_weeks: number
  chain_incomplete: boolean
}

interface Campaign {
  symbol: string
  status: 'held' | 'closed'
  covered_pct: number
  first: string | null
  assignments: number
  shares_called: number
  avg_strike: number | null
  net_premium: number
  upside_given_up: number
  campaign: number
  unpriced_assignments: number
  accounts: AccountPart[]
  events: CallAssignment[]
}

interface CampaignData {
  stocks: Campaign[]
  totals: { net_premium: number; upside_given_up: number; campaign: number; shares_called: number }
  assignments: number
  unpriced_assignments: number
}

type SortKey = 'symbol' | 'covered_pct' | 'first' | 'shares_called' | 'avg_strike'
  | 'net_premium' | 'upside_given_up' | 'campaign'

const COLUMNS: Array<[SortKey, string, string]> = [
  ['symbol', 'Stock', ''],
  ['covered_pct', 'Covered', 'Share of the calls counted here: bought shares ÷ all shares acquired. The rest were on shares from assigned puts — those are in Put Campaigns.'],
  ['first', 'Since', 'First call sold on this stock'],
  ['shares_called', 'Called away', 'Shares called away across every call assignment on this stock (counted share)'],
  ['avg_strike', 'Avg strike', 'Share-weighted average strike of the assigned calls'],
  ['net_premium', 'Net premium', 'Every call sold minus every call bought back — roll buy-backs, including any intrinsic paid, are already netted in'],
  ['upside_given_up', 'Upside given up', 'At each call assignment: (market that day − strike) × shares — what the shares were worth above the price you had to sell at'],
  ['campaign', 'Campaign', 'Net premium − upside given up: did selling calls earn more than it gave away?'],
]

const usd = (v: number) => `$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const signedUsd = (v: number | null) => v == null ? '—' : Math.round(v) === 0 ? '$0' : `${v < 0 ? '−' : '+'}${usd(v)}`
const minus = (v: number | null) => v == null ? '—' : Math.round(v) === 0 ? '—' : `−${usd(v)}`
const tone = (v: number | null) => v == null || Math.round(v) === 0 ? undefined : v < 0 ? styles.neg : styles.pos
const shortDate = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
const monthYear = (d: string | null) => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '—'
const price = (v: number | null) => v == null ? '—' : `$${v.toFixed(2)}`
const covered = (pct: number) => pct < 99.95 ? `${Math.round(pct)}%` : 'all'

export function CallCampaigns() {
  const [data, setData] = useState<CampaignData | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('campaign')
  const [sortDir, setSortDir] = useState<1 | -1>(1)

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/call-campaigns`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (data && window.location.hash === '#call-campaigns') {
      document.getElementById('call-campaigns')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [data])

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
    <section id="call-campaigns" className={styles.section}>
      <h2 className={styles.title}>Call Campaigns</h2>
      <p className={styles.subtitle}>
        Every call sold on shares you bought to keep, against simply holding those shares. <strong>Net
        premium</strong> is every call sold minus every call bought back. <strong>Upside given up</strong> is what the
        shares were worth above the strike on the day a call was assigned. <strong>Campaign</strong>: did selling calls
        earn more than it gave away? Calls on shares that came from an assigned put are in Put Campaigns above, so a
        stock held both ways counts only its bought share here ("Covered").
      </p>

      <div className={styles.card}>
        <div className={styles.statRow}>
          <div>
            <div className={clsx(styles.statValue, tone(t.net_premium))}>{signedUsd(t.net_premium)}</div>
            <div className={styles.statLabel}>net premium, after buy-backs</div>
          </div>
          <div>
            <div className={clsx(styles.statValue, styles.neg)}>{minus(t.upside_given_up)}</div>
            <div className={styles.statLabel}>
              upside given up · {data.assignments} call{data.assignments === 1 ? '' : 's'} assigned, {Math.round(t.shares_called).toLocaleString()} sh
            </div>
          </div>
          <div>
            <div className={clsx(styles.statValue, tone(t.campaign))}>{signedUsd(t.campaign)}</div>
            <div className={styles.statLabel}>campaign, all in</div>
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
                      {s.status !== 'held' && <span className={styles.status}>{s.status}</span>}
                    </td>
                    <td className={styles.num}>{covered(s.covered_pct)}</td>
                    <td className={styles.num}>{monthYear(s.first)}</td>
                    <td className={styles.num}>
                      {s.assignments > 0
                        ? <>{Math.round(s.shares_called).toLocaleString()} sh<span className={styles.dim}> · {s.assignments}</span></>
                        : '—'}
                    </td>
                    <td className={styles.num}>{price(s.avg_strike)}</td>
                    <td className={clsx(styles.num, tone(s.net_premium))}>{signedUsd(s.net_premium)}</td>
                    <td className={clsx(styles.num, Math.round(s.upside_given_up) ? styles.neg : undefined)}>
                      {minus(s.upside_given_up)}
                      {s.unpriced_assignments > 0 && <span className={styles.flag} title={`${s.unpriced_assignments} assignment(s) have no market price that day and are left out`}>⚠</span>}
                    </td>
                    <td className={clsx(styles.num, styles.strong, tone(s.campaign))}>{signedUsd(s.campaign)}</td>
                  </tr>
                  {open === s.symbol && (
                    <>
                      {s.accounts.map(a => (
                        <tr key={a.account_name} className={styles.detail}>
                          <td className={styles.left}>{a.account_name}</td>
                          <td className={styles.num}>{covered(a.covered_pct)}</td>
                          <td colSpan={3} />
                          <td className={clsx(styles.num, tone(a.net_premium))}>{signedUsd(a.net_premium)}</td>
                          <td className={styles.num}>{minus(a.upside_given_up)}</td>
                          <td className={clsx(styles.num, tone(a.campaign))}>{signedUsd(a.campaign)}</td>
                        </tr>
                      ))}
                      {s.events.map((e, i) => (
                        <tr key={`e${i}`} className={styles.detail}>
                          <td className={styles.left} colSpan={3}>
                            Called away {shortDate(e.date)} · {e.account_name}
                            {e.covered_pct < 99.95 && <span className={styles.dim}> · {Math.round(e.covered_pct)}% counted</span>}
                          </td>
                          <td className={styles.num}>{e.shares.toLocaleString()} sh</td>
                          <td className={styles.num}
                              title={e.price_at_assignment != null ? `Market that day $${e.price_at_assignment.toFixed(2)}` : undefined}>
                            {price(e.strike)}
                            {e.price_at_assignment != null && <span className={styles.dim}> vs ${e.price_at_assignment.toFixed(2)}</span>}
                          </td>
                          <td className={clsx(styles.num, styles.dim)}
                              title="What the calls that ended in this assignment paid across their rolls. Already inside the stock's net premium, which also holds every call that expired — so these rows do not add up to it.">
                            {Math.round(e.chain_premium) !== 0 && <>incl. {signedUsd(e.chain_premium)}{e.chain_weeks > 1 && ` (${e.chain_weeks}wk)`}</>}
                            {e.chain_incomplete && <span className={styles.flag} title="The roll chain hits a gap in the transaction history; the true total reaches further back">⚠</span>}
                          </td>
                          <td className={styles.num}
                              title={e.price_at_assignment != null ? `($${e.price_at_assignment.toFixed(2)} market − $${e.strike.toFixed(2)} strike) × ${e.shares.toLocaleString()} sh${e.covered_pct < 99.95 ? ` × ${Math.round(e.covered_pct)}%` : ''}` : undefined}>
                            {minus(e.upside_given_up)}
                          </td>
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
                <td className={styles.num}>{Math.round(t.shares_called).toLocaleString()} sh</td>
                <td />
                <td className={clsx(styles.num, tone(t.net_premium))}>{signedUsd(t.net_premium)}</td>
                <td className={clsx(styles.num, styles.neg)}>{minus(t.upside_given_up)}</td>
                <td className={clsx(styles.num, styles.strong, tone(t.campaign))}>{signedUsd(t.campaign)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className={styles.footnote}>
          Upside given up is an opportunity cost, not money lost: the shares sold at the strike, and the market would
          have paid more that day. It is measured on the day of each assignment, not followed to today. Covered is by
          share count, not by how long each share was held, so for a stock held both ways the split is an
          approximation. Calls still open count at the premium received; if one is assigned above the market, that
          shows up here when it happens. "Closed": none of the bought shares are held any more. Hover a figure in an
          expanded row to see its arithmetic.
        </p>
      </div>
    </section>
  )
}
