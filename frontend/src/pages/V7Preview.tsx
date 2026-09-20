/**
 * V7 Preview — the two-book / four-layer notification engine, read-only,
 * beside the live V6 queue on Option Execution. Built 2026-09-13 so Neel
 * can judge it during a live trading day before anything is switched.
 * Laid out like Option Execution (Neel, 2026-09-14): account pills, one
 * queue, sort by account — the layer is a tag on the row, not a section.
 * Spec: docs/OPTIONS-STRATEGY-V7-SPEC.md · policy: data/policy_v2.json.
 */
import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, AlertTriangle, ChevronDown, Settings } from 'lucide-react'
import { SyncButtons } from '../components/SyncButton'
import clsx from 'clsx'
import { getAuthHeaders } from '../contexts/AuthContext'
import { formatCurrency } from '../components/charts'
import { useDataAsOfPoll } from '../hooks/useDataAsOfPoll'
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

interface Knob { value: number; label: string; group: string; description: string; unit: string; step?: number; min?: number; max?: number }

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

const ACCOUNT_ORDER = ["Neel's Brokerage", "Neel's Retirement", "Neel's Roth IRA",
  "Jaya's Brokerage", "Jaya's IRA", "Jaya's Roth IRA", "Alisha's Brokerage", "Agrawal Family HSA"]

const LAYER_NAME: Record<number, string> = { 1: 'Long-term calls', 2: 'Short-term calls', 3: 'Short-term puts', 4: 'Recovery' }
const LAYER_RULE: Record<number, string> = {
  1: 'Long-term book: delta 10-15 calls on every name. Stuck calls roll weekly at the same strike for a credit; buy back on a dip; the roll before ex-dividend goes 3-4 weeks out. Puts only to re-enter after a call assignment.',
  2: 'Short-term book: calls between delta 20 and 40, the technicals pick the number (low RSI → nearer 20). Never at the money. Same rule whether the shares were assigned or bought.',
  3: 'Short-term puts against cash and margin, to maximise option income. Capacity = margin line + cash − open collateral − margin drawn. None once the short-term book is at 20%.',
  4: 'Recovery: a notice with a dollar amount, never a pick. Margin drawn by shares instead of puts; the 80/20 split drifting.',
}

const ACTION_COLOR: Record<string, string> = {
  SELL: 'var(--color-positive)', 'SELL PUT': 'var(--color-positive)', ROLL: 'var(--color-warning)',
  'BUY BACK': 'var(--color-accent)', WAIT: 'var(--color-text-tertiary)', HOLD: 'var(--color-text-tertiary)',
  'LET ASSIGN': 'var(--color-warning)', NOTICE: 'var(--color-negative)', REVIEW: 'var(--color-warning)',
}

const acctRank = (a: string) => { const i = ACCOUNT_ORDER.indexOf(a); return i < 0 ? 99 : i }

export default function V7Preview() {
  const [data, setData] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState<string | null>(null)
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [sort, setSort] = useState<'account' | 'layer'>('account')
  const [showRules, setShowRules] = useState(false)
  const [showKnobs, setShowKnobs] = useState(false)
  const [knobs, setKnobs] = useState<Record<string, Knob> | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const loadKnobs = () => {
    fetch(`${API_BASE}/strategies/v7/knobs`, { headers: getAuthHeaders() })
      .then(r => r.json())
      .then(d => { setKnobs(d.knobs); setDraft(Object.fromEntries(Object.entries(d.knobs as Record<string, Knob>).map(([k, v]) => [k, String(v.value)]))) })
      .catch(() => setKnobs(null))
  }
  const saveKnobs = () => {
    if (!knobs) return
    const values: Record<string, number> = {}
    for (const [k, v] of Object.entries(draft)) {
      const n = Number(v)
      if (!Number.isNaN(n) && n !== knobs[k].value) values[k] = n
    }
    if (Object.keys(values).length === 0) { setSaving('nothing changed'); return }
    setSaving('saving…')
    fetch(`${API_BASE}/strategies/v7/knobs`, {
      method: 'PUT', headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ values }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`); return r.json() })
      .then(d => { setSaving(`saved ${Object.keys(d.changed).length} — rebuilding`); setKnobs(d.knobs); load() })
      .catch(e => setSaving(`error: ${e.message}`))
  }

  const load = () => {
    setLoading(true)
    fetch(`${API_BASE}/strategies/v7/preview`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load(); loadKnobs() }, [])
  useDataAsOfPoll(load)   // re-build when a sync lands

  const all = useMemo(() => (data ? data.layers.flatMap(L => L.items) : []), [data])

  // account pills — every account that has holdings or cards, canonical order
  const accounts = useMemo(() => {
    const names = new Set<string>(all.map(c => c.account).filter(a => a && a !== 'Portfolio'))
    data?.accounts.forEach(a => names.add(a.account))
    return Array.from(names).sort((a, b) => acctRank(a) - acctRank(b)).map(name => ({
      name,
      total: all.filter(c => c.account === name).length,
      notices: all.filter(c => c.account === name && c.layer === 4).length,
    }))
  }, [all, data])

  const rows = useMemo(() => {
    const list = selectedAccount ? all.filter(c => c.account === selectedAccount || c.account === 'Portfolio') : all
    return [...list].sort((a, b) => sort === 'account'
      ? (acctRank(a.account) - acctRank(b.account)) || (a.layer - b.layer) || a.symbol.localeCompare(b.symbol)
      : (a.layer - b.layer) || (acctRank(a.account) - acctRank(b.account)) || a.symbol.localeCompare(b.symbol))
  }, [all, selectedAccount, sort])

  if (error) return <div className={styles.page}><p className={styles.error}>Could not load the V7 preview: {error}</p></div>
  if (loading || !data) return <div className={styles.page}><p className={styles.muted}>Building the V7 queue…</p></div>

  const { split } = data
  const stOver = split.short_term_pct > split.target.short_term_pct
  const estTotal = rows.reduce((s, c) => s + (c.earn ?? 0), 0)

  // group headers when sorted by account
  let lastGroup: string | null = null

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
        <div className={styles.headerBtns}>
          <button className={clsx(styles.refresh, showKnobs && styles.refreshActive)} onClick={() => setShowKnobs(v => !v)} title="Knobs — every number the engine uses"><Settings size={16} /></button>
          <SyncButtons className={styles.refresh} onDone={load} />
          <button className={styles.refresh} onClick={load} title="Rebuild from the data already synced"><RefreshCw size={16} /></button>
        </div>
      </header>

      {showKnobs && knobs && (() => {
        const groups = Array.from(new Set(Object.values(knobs).map(k => k.group)))
        return (
          <section className={styles.knobs}>
            <div className={styles.knobsHead}>
              <div>
                <strong>Knobs</strong>
                <span className={styles.muted}> — every number the engine uses. A change is written to data/policy_v2.json and the next build picks it up.</span>
              </div>
              <div className={styles.knobsActions}>
                {saving && <span className={styles.muted}>{saving}</span>}
                <button className={styles.knobSave} onClick={saveKnobs}>Save &amp; rebuild</button>
              </div>
            </div>
            {groups.map(g => (
              <div key={g} className={styles.knobGroup}>
                <div className={styles.knobGroupName}>{g}</div>
                {Object.entries(knobs).filter(([, k]) => k.group === g).map(([key, k]) => {
                  const dirty = Number(draft[key]) !== k.value
                  return (
                    <label key={key} className={clsx(styles.knob, dirty && styles.knobDirty)} title={key}>
                      <span className={styles.knobLabel}>{k.label}</span>
                      <span className={styles.knobInput}>
                        <input type="number" value={draft[key] ?? ''} step={k.step ?? 1} min={k.min} max={k.max}
                               onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))} />
                        <span className={styles.knobUnit}>{k.unit}</span>
                      </span>
                      <span className={styles.knobDesc}>{k.description}</span>
                    </label>
                  )
                })}
              </div>
            ))}
          </section>
        )
      })()}

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
            target {split.target.short_term_pct}% · {formatCurrency(split.short_term_value)} in shares (put collateral is bucket C, not counted) · {data.lists.short_term.join(' ')}
          </div>
        </div>
        {data.accounts.filter(a => a.line).map(a => (
          <div key={a.account} className={clsx(styles.stateCard, a.margin_used > 1000 && styles.stateWarn)}>
            <div className={styles.stateLabel}>{a.account} margin</div>
            <div className={styles.stateValue}>{formatCurrency(a.margin_used)} drawn</div>
            <div className={styles.stateSub}>line {formatCurrency(a.line!)} · put collateral {formatCurrency(a.collateral)} · cash {formatCurrency(a.cash)}</div>
          </div>
        ))}
      </section>

      {/* account pills — same control as Option Execution */}
      <div className={styles.acctFilterRow}>
        <button className={clsx(styles.acctPill, selectedAccount === null && styles.acctPillActive)} onClick={() => setSelectedAccount(null)}>
          <span className={styles.acctPillName}>All Accounts</span>
          <span className={styles.acctPillCount}>{all.length}</span>
        </button>
        {accounts.map(a => (
          <button key={a.name} className={clsx(styles.acctPill, selectedAccount === a.name && styles.acctPillActive)}
                  onClick={() => setSelectedAccount(selectedAccount === a.name ? null : a.name)}>
            {a.notices > 0 && <span className={styles.acctDot} />}
            <span className={styles.acctPillName}>{a.name}</span>
            <span className={styles.acctPillCount}>{a.total}</span>
          </button>
        ))}
      </div>

      <div className={styles.queueHeader}>
        <h2>Action Queue</h2>
        <span className={styles.summary}>{rows.length} recommendation{rows.length === 1 ? '' : 's'}</span>
        {estTotal > 0 && <span className={styles.summaryEarn}>est {formatCurrency(estTotal)} this week</span>}
        <span className={styles.engineTag}>V7 · two books, four layers</span>
        <span className={styles.sortToggle}>
          <span className={styles.sortToggleLabel}>Sort:</span>
          <button className={clsx(styles.sortToggleBtn, sort === 'account' && styles.sortToggleBtnActive)} onClick={() => setSort('account')}>Account</button>
          <button className={clsx(styles.sortToggleBtn, sort === 'layer' && styles.sortToggleBtnActive)} onClick={() => setSort('layer')}>Layer</button>
        </span>
        <button className={styles.rulesToggle} onClick={() => setShowRules(v => !v)}>{showRules ? 'hide' : 'show'} the four layers</button>
      </div>

      {showRules && (
        <div className={styles.rules}>
          {[1, 2, 3, 4].map(n => (
            <div key={n} className={styles.rule}><span className={styles.layerTag}>L{n}</span> <strong>{LAYER_NAME[n]}</strong> — {LAYER_RULE[n]}</div>
          ))}
        </div>
      )}

      <div className={styles.list}>
        {rows.length === 0 && <p className={styles.muted}>Nothing to do.</p>}
        {rows.map(c => {
          const group = sort === 'account' ? c.account : `L${c.layer} ${LAYER_NAME[c.layer]}`
          const header = group !== lastGroup ? group : null
          lastGroup = group
          const rsi = c.context?.rsi as number | null | undefined
          return (
            <div key={c.id}>
              {header && <div className={styles.groupHeader}>{header}</div>}
              <div className={styles.item}>
                <button className={styles.row} onClick={() => setOpen(open === c.id ? null : c.id)}>
                  <span className={styles.action} style={{ color: ACTION_COLOR[c.action] ?? 'var(--color-text-secondary)', borderColor: ACTION_COLOR[c.action] ?? 'var(--color-border)' }}>{c.action}</span>
                  <span className={styles.sym}>{c.symbol}</span>
                  <span className={styles.acct}>{c.account}</span>
                  <span className={styles.title}>{c.title}<span className={styles.detailInline}> · {c.detail}</span></span>
                  <span className={styles.layerTag} title={LAYER_NAME[c.layer]}>L{c.layer}</span>
                  {rsi != null && <span className={styles.chip}>RSI {Math.round(rsi)}</span>}
                  {c.assumption && <span className={styles.flag} title={c.assumption}>assumption</span>}
                  {c.earn != null && <span className={styles.earn}>Earn ~{formatCurrency(c.earn)}</span>}
                  <ChevronDown size={14} className={clsx(styles.chev, open === c.id && styles.chevOpen)} />
                </button>
                {open === c.id && (
                  <div className={styles.why}>
                    <div className={styles.whyRule}>{LAYER_NAME[c.layer]}</div>
                    <div className={styles.whyDetail}>{c.detail}</div>
                    <div>{c.why}</div>
                    {c.assumption && <div className={styles.assumption}>⚠ {c.assumption}</div>}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <p className={styles.footnote}>
        Strikes and premiums are the same heuristics V6 uses — estimates, not quotes. Cards marked <em>assumption</em> encode a rule Neel has not stated yet; they are listed in data/policy_v2.json. Undecided names: {data.lists.undecided.join(', ')}.
      </p>
    </div>
  )
}
