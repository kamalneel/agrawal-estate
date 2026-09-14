/**
 * V7 Preview — the two-book / four-layer notification engine, read-only,
 * beside the live V6 queue on Option Execution. Built 2026-09-13 so Neel
 * can judge it during a live trading day before anything is switched.
 * Spec: docs/INVESTMENT-THESIS-V2-DRAFT.md · policy: data/policy_v2.json.
 */
import { useEffect, useState } from 'react'
import { RefreshCw, AlertTriangle, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getAuthHeaders } from '../contexts/AuthContext'
import { formatCurrency } from '../components/charts'
import styles from './V7Preview.module.css'

const API_BASE = '/api/v1'

interface Card {
  id: string
  layer: number
  action: string
  account: string
  symbol: string
  title: string
  detail: string
  why: string
  earn: number | null
  assumption: string | null
  context: Record<string, unknown>
}

interface Layer { n: number; name: string; items: Card[] }

interface Preview {
  as_of: string
  policy_status: string
  data_as_of: { options: string; cash: string }
  split: {
    long_term_pct: number; short_term_pct: number; other_pct: number
    target: { long_term_pct: number; short_term_pct: number }
    total_value: number; short_term_value: number; short_term_put_collateral: number
  }
  accounts: { account: string; line: number | null; margin_used: number; collateral: number; cash: number; as_of: string }[]
  lists: { long_term: string[]; short_term: string[]; undecided: string[] }
  layers: Layer[]
  counts: Record<string, number>
}

const LAYER_BLURB: Record<number, string> = {
  1: 'Long-term book — delta 10-15 calls on every name, consistently. Stuck calls roll weekly at the same strike for a credit; buy back on a dip; the roll before ex-dividend goes 3-4 weeks out. Puts only to re-enter after a call assignment.',
  2: 'Short-term book — calls between delta 20 and 40, the technicals pick the number (low RSI → nearer 20). Never at the money. Same rule whether the shares were assigned or bought.',
  3: 'Short-term puts against cash and margin, to maximise option income. Capacity = margin line + cash − open collateral − margin already drawn. No new put once the short-term book is at 20%.',
  4: 'Recovery — a notice with a dollar amount, never a pick. Margin drawn by shares instead of puts; the 80/20 split drifting. No hurry: the cost of the abnormal state is put income (~2%/mo) becoming call income (~1%/mo).',
}

const ACTION_COLOR: Record<string, string> = {
  SELL: 'var(--color-positive)', 'SELL PUT': 'var(--color-positive)', ROLL: 'var(--color-warning)',
  'BUY BACK': 'var(--color-accent)', WAIT: 'var(--color-text-tertiary)', HOLD: 'var(--color-text-tertiary)',
  'LET ASSIGN': 'var(--color-warning)', NOTICE: 'var(--color-negative)', REVIEW: 'var(--color-warning)',
}

export default function V7Preview() {
  const [data, setData] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    fetch(`${API_BASE}/strategies/v7/preview`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  if (error) return <div className={styles.page}><p className={styles.error}>Could not load the V7 preview: {error}</p></div>
  if (loading || !data) return <div className={styles.page}><p className={styles.muted}>Building the V7 queue…</p></div>

  const { split } = data
  const stOver = split.short_term_pct > split.target.short_term_pct

  return (
    <div className={styles.page}>
      <div className={styles.banner}>
        <AlertTriangle size={16} />
        <span><strong>Preview.</strong> V6 is still the live notification engine. {data.policy_status}</span>
      </div>

      <header className={styles.header}>
        <div>
          <h1>Notifications V7</h1>
          <div className={styles.sub}>
            as of {data.as_of} · positions {data.data_as_of.options?.slice(0, 16)} · cash {data.data_as_of.cash}
          </div>
        </div>
        <button className={styles.refresh} onClick={load} title="Rebuild"><RefreshCw size={16} /></button>
      </header>

      {/* State: the two books and the margin lines */}
      <section className={styles.state}>
        <div className={styles.stateCard}>
          <div className={styles.stateLabel}>Long-term book</div>
          <div className={styles.stateValue}>{split.long_term_pct.toFixed(1)}%</div>
          <div className={styles.stateSub}>target {split.target.long_term_pct}% · {data.lists.long_term.join(' ')}</div>
        </div>
        <div className={clsx(styles.stateCard, stOver && styles.stateWarn)}>
          <div className={styles.stateLabel}>Short-term book</div>
          <div className={styles.stateValue}>{split.short_term_pct.toFixed(1)}%</div>
          <div className={styles.stateSub}>
            target {split.target.short_term_pct}% · {formatCurrency(split.short_term_value)} held + {formatCurrency(split.short_term_put_collateral)} put collateral · {data.lists.short_term.join(' ')}
          </div>
        </div>
        {data.accounts.filter(a => a.line).map(a => (
          <div key={a.account} className={clsx(styles.stateCard, a.margin_used > 1000 && styles.stateWarn)}>
            <div className={styles.stateLabel}>{a.account} margin</div>
            <div className={styles.stateValue}>{formatCurrency(a.margin_used)} drawn</div>
            <div className={styles.stateSub}>line {formatCurrency(a.line!)} · put collateral {formatCurrency(a.collateral)} · cash {formatCurrency(a.cash)}</div>
          </div>
        ))}
        {data.lists.undecided.length > 0 && (
          <div className={styles.stateCard}>
            <div className={styles.stateLabel}>Undecided</div>
            <div className={styles.stateValueSm}>{data.lists.undecided.join(' · ')}</div>
            <div className={styles.stateSub}>in V6 core; asked 2026-09-13 whether they stay as share-purchase targets</div>
          </div>
        )}
      </section>

      {data.layers.map(L => (
        <section key={L.n} className={styles.layer}>
          <h2><span className={styles.layerNum}>{L.n}</span> {L.name} <span className={styles.count}>({L.items.length})</span></h2>
          <p className={styles.blurb}>{LAYER_BLURB[L.n]}</p>
          {L.items.length === 0 ? (
            <p className={styles.muted}>Nothing to do.</p>
          ) : (
            <div className={styles.list}>
              {L.items.map(c => (
                <div key={c.id} className={styles.item}>
                  <button className={styles.row} onClick={() => setOpen(open === c.id ? null : c.id)}>
                    <span className={styles.action} style={{ color: ACTION_COLOR[c.action] ?? 'var(--color-text-secondary)', borderColor: ACTION_COLOR[c.action] ?? 'var(--color-border)' }}>{c.action}</span>
                    <span className={styles.sym}>{c.symbol}</span>
                    <span className={styles.acct}>{c.account}</span>
                    <span className={styles.title}>{c.title}</span>
                    {c.earn != null && <span className={styles.earn}>est {formatCurrency(c.earn)}</span>}
                    {c.assumption && <span className={styles.flag} title={c.assumption}>assumption</span>}
                    <ChevronRight size={14} className={clsx(styles.chev, open === c.id && styles.chevOpen)} />
                  </button>
                  <div className={styles.detail}>{c.detail}</div>
                  {open === c.id && (
                    <div className={styles.why}>
                      <div>{c.why}</div>
                      {c.assumption && <div className={styles.assumption}>⚠ {c.assumption}</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      ))}

      <p className={styles.footnote}>
        Strikes and premiums are the same heuristics V6 uses — estimates, not quotes. Cards marked <em>assumption</em> encode a rule Neel has not stated yet; they are listed in data/policy_v2.json.
      </p>
    </div>
  )
}
