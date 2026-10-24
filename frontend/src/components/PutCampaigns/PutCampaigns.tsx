import { Fragment, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './PutCampaigns.module.css'

const API_BASE = '/api/v1'

/**
 * Put Campaigns — Neel, 2026-10-22. The Assignment Loss section freezes
 * the loss on the day a put is assigned; "that stock then goes up or
 * down". This is the wheel-trader view, per stock: what the assigned
 * shares are worth today (or what they sold for), plus the net premium
 * collected across the roll chain that led to each assignment.
 *
 *   Shares today   = held × today's price + sale proceeds − strike × shares
 *   Campaign       = Shares today + put premium + call premium
 *   Adjusted basis = strike − all premium per share
 *
 * Call premium (2026-10-23): the wheel's third phase. Each account's calls
 * on a stock are split by shares between this section (put-assigned) and
 * Covered Call Income (bought), so every call counts once. Unrealized for anything still held, so it lives here (the
 * look-back page), not in the Income table. See get_put_campaigns in
 * assignment_loss_service.py.
 *
 * Every assignment-loss figure links here (Neel, 2026-10-23: Options
 * Execution sent him to a different table than Income did). The link
 * carries its period — ?assigned=2026-10 or ?assigned=2026 — so the
 * number clicked is shown on arrival and its stocks are highlighted.
 */

interface CampaignEvent {
  date: string
  account_name: string
  symbol: string
  strike: number
  shares: number
  price_at_assignment: number | null
  loss_at_assignment: number
  shares_held: number
  shares_sold: number
  sale_proceeds: number
  last_sale: string | null
  price_today: number | null
  shares_result: number | null
  premium_collected: number
  premium_chain_weeks: number
  premium_incomplete: boolean
  call_premium: number
  adjusted_basis: number
  campaign: number | null
  traced: boolean
}

interface Campaign {
  symbol: string
  assignments: number
  shares: number
  shares_held: number
  avg_strike: number | null
  adjusted_basis: number | null
  price_today: number | null
  status: 'held' | 'partly sold' | 'closed'
  loss_at_assignment: number
  shares_result: number
  premium_collected: number
  call_premium: number
  campaign: number
  unpriced: number
  untraced: number
  first: string
  last: string
  events: CampaignEvent[]
}

interface CampaignData {
  stocks: Campaign[]
  totals: { loss_at_assignment: number; shares_result: number; premium_collected: number; call_premium: number; campaign: number }
  assignments: number
  unpriced: number
  untraced: number
}

type SortKey = 'symbol' | 'shares' | 'avg_strike' | 'adjusted_basis' | 'price_today' | 'loss_at_assignment'
  | 'shares_result' | 'premium_collected' | 'call_premium' | 'campaign'

const COLUMNS: Array<[SortKey, string, string]> = [
  ['symbol', 'Stock', ''],
  ['shares', 'Assigned', 'Shares assigned across every put on this stock'],
  ['avg_strike', 'Avg strike', 'Share-weighted average strike of the assigned puts'],
  ['adjusted_basis', 'Adj. basis', 'Strike minus every premium collected, put and call, per share — the price at which the campaign breaks even'],
  ['price_today', 'Today', 'Latest price (from the last sync)'],
  ['loss_at_assignment', 'Loss when assigned', 'Strike vs. the market on the day each put was assigned — the Assignment Loss figure above'],
  ['shares_result', 'Shares today', 'Shares still held at today\'s price, plus what sold shares fetched, minus what they cost at the strike'],
  ['premium_collected', 'Put premium', 'Net premium across every roll of the puts that ended in these assignments'],
  ['call_premium', 'Call premium', 'Net premium from calls sold on these shares (sold minus bought back). Where an account also held bought shares, only the put-assigned share of its calls counts; the rest is Covered Call Income.'],
  ['campaign', 'Campaign', 'Shares today + put premium + call premium: all in, did the wheel on this stock work?'],
]

const usd = (v: number) => `$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const signedUsd = (v: number | null) => v == null ? '—' : v === 0 ? '$0' : `${v < 0 ? '−' : '+'}${usd(v)}`
const tone = (v: number | null) => v == null || v === 0 ? undefined : v < 0 ? styles.neg : styles.pos
const shortDate = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
const price = (v: number | null) => v == null ? '—' : `$${v.toFixed(2)}`
const periodLabel = (p: string) => /^\d{4}-\d{2}$/.test(p)
  ? new Date(`${p}-01T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  : p

/** The arithmetic behind one assignment's Shares-today figure. */
function sharesText(e: CampaignEvent): string {
  const parts: string[] = []
  if (e.shares_held > 1e-6) parts.push(`${e.shares_held.toLocaleString()} held × ${price(e.price_today)}`)
  if (e.shares_sold > 1e-6) parts.push(`${e.shares_sold.toLocaleString()} sold for ${usd(e.sale_proceeds)}`)
  return `${parts.join(' + ')} − ${e.shares.toLocaleString()} × $${e.strike.toFixed(2)}`
}

export function PutCampaigns() {
  const [data, setData] = useState<CampaignData | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('campaign')
  const [sortDir, setSortDir] = useState<1 | -1>(1)
  const [params, setParams] = useSearchParams()
  const assigned = params.get('assigned')   // 'YYYY-MM' or 'YYYY' — the period the link came from
  const inPeriod = (d: string) => !!assigned && d.startsWith(assigned)

  useEffect(() => {
    fetch(`${API_BASE}/strategies/v6/put-campaigns`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setData(d))
      .catch(() => {})
  }, [])

  // Arriving from an assignment-loss figure (Options Execution, Income).
  // A single stock assigned in the period opens on arrival.
  useEffect(() => {
    if (!data) return
    if (assigned) {
      const syms = data.stocks.filter(s => s.events.some(e => e.date.startsWith(assigned))).map(s => s.symbol)
      if (syms.length === 1) setOpen(syms[0])
    }
    if (window.location.hash === '#put-campaigns') {
      document.getElementById('put-campaigns')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [data, assigned])

  if (!data || data.stocks.length === 0) return null

  const sort = (key: SortKey) => {
    if (key === sortKey) setSortDir(d => (d === 1 ? -1 : 1))
    else { setSortKey(key); setSortDir(1) }
  }
  const hit = (s: Campaign) => s.events.some(e => inPeriod(e.date))
  const stocks = [...data.stocks].sort((a, b) => {
    // the period's stocks first, in the chosen order
    if (hit(a) !== hit(b)) return hit(a) ? -1 : 1
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * sortDir
    return ((va as number) - (vb as number)) * sortDir
  })
  const t = data.totals
  const recovered = t.shares_result - t.loss_at_assignment
  const periodEvents = assigned ? data.stocks.flatMap(s => s.events.filter(e => inPeriod(e.date))) : []
  const periodLoss = periodEvents.reduce((sum, e) => sum + e.loss_at_assignment, 0)
  const periodSyms = [...new Set(periodEvents.map(e => e.symbol))]
  const clearPeriod = () => setParams(p => { p.delete('assigned'); return p }, { replace: true })

  return (
    <section id="put-campaigns" className={styles.section}>
      <h2 className={styles.title}>Put Campaigns</h2>
      <p className={styles.subtitle}>
        Every put that was assigned, followed through to today. <strong>Shares today</strong> is the assigned shares
        at today's price — or what they sold for, once sold — against what they cost at the strike.{' '}
        <strong>Campaign</strong> adds the premium: the puts rolled on the way to each assignment, and the calls sold on
        the shares afterwards — all in, did the wheel on this stock work? <strong>Adj. basis</strong> is the strike less
        all that premium per share: above it, the campaign is in profit. Unrealized while the shares are held, so it is not part of income.
      </p>

      <div className={styles.card}>
        {assigned && (
          <div className={styles.periodBanner}>
            {periodEvents.length === 0 ? (
              <span>No puts were assigned in {periodLabel(assigned)}.</span>
            ) : (
              <span>
                Assigned in {periodLabel(assigned)}:{' '}
                <strong className={tone(periodLoss)}>{signedUsd(periodLoss)}</strong> when assigned ·{' '}
                {periodEvents.length} put{periodEvents.length > 1 ? 's' : ''} on {periodSyms.join(', ')} — highlighted
                below; each row is that stock's whole campaign to date.
              </span>
            )}
            <button className={styles.periodClear} onClick={clearPeriod}>show all ✕</button>
          </div>
        )}
        <div className={styles.statRow}>
          <div>
            <div className={clsx(styles.statValue, tone(t.loss_at_assignment))}>{signedUsd(t.loss_at_assignment)}</div>
            <div className={styles.statLabel}>loss when assigned · {data.assignments} puts</div>
          </div>
          <div>
            <div className={clsx(styles.statValue, tone(t.shares_result))}>{signedUsd(t.shares_result)}</div>
            <div className={styles.statLabel}>
              shares today · {recovered >= 0 ? `${usd(recovered)} better` : `${usd(recovered)} worse`} than when assigned
            </div>
          </div>
          <div>
            <div className={clsx(styles.statValue, styles.pos)}>{signedUsd(t.premium_collected)}</div>
            <div className={styles.statLabel}>put premium, on the way to assignment</div>
          </div>
          <div>
            <div className={clsx(styles.statValue, tone(t.call_premium))}>{signedUsd(t.call_premium)}</div>
            <div className={styles.statLabel}>call premium on the shares since</div>
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
                  <tr className={clsx(styles.row, hit(s) && styles.highlight)} onClick={() => setOpen(o => (o === s.symbol ? null : s.symbol))}>
                    <td className={clsx(styles.left, styles.symbol)}>
                      {open === s.symbol ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      {s.symbol}
                      {s.status !== 'held' && <span className={styles.status}>{s.status}</span>}
                    </td>
                    <td className={styles.num}>
                      {s.shares.toLocaleString()} sh
                      <span className={styles.dim}> · {s.assignments}</span>
                    </td>
                    <td className={styles.num}>{price(s.avg_strike)}</td>
                    <td className={styles.num}>{price(s.adjusted_basis)}</td>
                    <td className={styles.num}>{s.shares_held > 1e-6 ? price(s.price_today) : '—'}</td>
                    <td className={clsx(styles.num, tone(s.loss_at_assignment))}>{signedUsd(s.loss_at_assignment)}</td>
                    <td className={clsx(styles.num, tone(s.shares_result))}>
                      {signedUsd(s.shares_result)}
                      {s.unpriced > 0 && <span className={styles.flag} title={`${s.unpriced} assignment(s) have no current price and are left out`}>⚠</span>}
                    </td>
                    <td className={clsx(styles.num, styles.pos)}>{signedUsd(s.premium_collected)}</td>
                    <td className={clsx(styles.num, tone(s.call_premium))}>{signedUsd(s.call_premium)}</td>
                    <td className={clsx(styles.num, styles.strong, tone(s.campaign))}>{signedUsd(s.campaign)}</td>
                  </tr>
                  {open === s.symbol && s.events.map((e, i) => (
                    <tr key={i} className={clsx(styles.detail, inPeriod(e.date) && styles.highlight)}>
                      <td className={styles.left}>{shortDate(e.date)} · {e.account_name}</td>
                      <td className={styles.num}>{e.shares.toLocaleString()} sh</td>
                      <td className={styles.num}>{price(e.strike)}</td>
                      <td className={styles.num}>{price(e.adjusted_basis)}</td>
                      <td className={styles.num}>{e.shares_held > 1e-6 ? price(e.price_today) : e.last_sale ? `sold ${shortDate(e.last_sale)}` : '—'}</td>
                      <td className={clsx(styles.num, tone(e.loss_at_assignment))}>{signedUsd(e.loss_at_assignment)}</td>
                      <td className={clsx(styles.num, tone(e.shares_result))} title={sharesText(e)}>
                        {signedUsd(e.shares_result)}
                        {!e.traced && <span className={styles.flag} title="No matching share lot found — valued as still held at today's price">~</span>}
                      </td>
                      <td className={clsx(styles.num, styles.pos)}>
                        {signedUsd(e.premium_collected)}
                        {e.premium_chain_weeks > 1 && <span className={styles.dim}> ({e.premium_chain_weeks}wk)</span>}
                        {e.premium_incomplete && <span className={styles.flag} title="The roll chain hits a gap in the transaction history; the true total reaches further back">⚠</span>}
                      </td>
                      <td className={clsx(styles.num, tone(e.call_premium))} title="This assignment's share, by shares, of its account's calls on the stock">{signedUsd(e.call_premium)}</td>
                      <td className={clsx(styles.num, tone(e.campaign))}>{signedUsd(e.campaign)}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              <tr className={styles.totalRow}>
                <td className={styles.left}>Total</td>
                <td colSpan={4} />
                <td className={clsx(styles.num, tone(t.loss_at_assignment))}>{signedUsd(t.loss_at_assignment)}</td>
                <td className={clsx(styles.num, tone(t.shares_result))}>{signedUsd(t.shares_result)}</td>
                <td className={clsx(styles.num, styles.pos)}>{signedUsd(t.premium_collected)}</td>
                <td className={clsx(styles.num, tone(t.call_premium))}>{signedUsd(t.call_premium)}</td>
                <td className={clsx(styles.num, styles.strong, tone(t.campaign))}>{signedUsd(t.campaign)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className={styles.footnote}>
          Each assignment is traced to its own share lot. When an account also held bought shares, which lot a later
          sale used follows the lot method (FIFO or highest cost first), so a sale can land on the other lot; the
          stock's total is unaffected. Call premium is split by share count within each account, not by how long each
          share was held. Hover a figure in an expanded row to see its arithmetic.
        </p>
      </div>
    </section>
  )
}
