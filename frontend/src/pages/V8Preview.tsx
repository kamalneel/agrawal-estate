/**
 * V8 Preview — the next rulebook, read-only, beside live V7 on Option
 * Execution. (Born as the V7 preview beside V6; renamed 2026-10-12 once
 * V7 went live — Neel: "why not just call it V8 Preview?")
 * Originally the two-book / four-layer engine, read-only,
 * beside the live V6 queue on Option Execution. Built 2026-09-13 so Neel
 * can judge it during a live trading day before anything is switched.
 * Laid out like Option Execution (Neel, 2026-09-14): account pills, one
 * queue, sort by account — the layer is a tag on the row, not a section.
 * Spec: docs/OPTIONS-STRATEGY-V7-SPEC.md · policy: data/policy_v2.json.
 * V7/V8 toggle (Neel, 2026-10-12): V8 is the same engine reading
 * data/policy_v8.json; in V8 mode each card is tagged new / changed
 * against V7, and V7 cards V8 drops are listed under the queue.
 */
import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, AlertTriangle, ChevronDown, Settings } from 'lucide-react'
import { SyncButtons } from '../components/SyncButton'
import clsx from 'clsx'
import { getAuthHeaders } from '../contexts/AuthContext'
import { formatCurrency } from '../components/charts'
import { useDataAsOfPoll } from '../hooks/useDataAsOfPoll'
import styles from './V8Preview.module.css'

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

type Engine = 'v7' | 'v8'

interface Preview {
  as_of: string
  version?: Engine
  differences_from_v7?: string[]
  overridden_knobs?: string[]
  policy_status: string
  data_as_of: { options: string; cash: string }
  split: {
    long_term_pct: number; short_term_pct: number; other_pct: number
    target: { long_term_pct: number; short_term_pct: number }
    total_value: number; short_term_value: number; short_term_put_collateral: number
  }
  accounts: { account: string; line: number | null; margin_used: number; collateral: number; cash: number; as_of: string }[]
  lists: { long_term: string[]; short_term: string[]; put_only: string[] }
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

// Same account / symbol / layer / action = the same decision; a different
// title on it means V8 sized or priced it differently.
const cardKey = (c: Card) => `${c.account}|${c.symbol}|${c.layer}|${c.action}`

// V8 went live on Option Execution 2026-10-22; this page now opens on V7,
// the previous rulebook, so it stays one click away. The V8 tab keeps the
// card-by-card comparison against V7. New key so the old 'v8' choice
// doesn't carry over.
const ENGINE_KEY = 'notifications.engine'
const readEngine = (): Engine => {
  try { return localStorage.getItem(ENGINE_KEY) === 'v8' ? 'v8' : 'v7' } catch { return 'v7' }
}

export default function V8Preview() {
  const [engine, setEngine] = useState<Engine>(readEngine)
  const [data, setData] = useState<Preview | null>(null)
  const [v7Cards, setV7Cards] = useState<Card[] | null>(null)   // V8 mode: the baseline to compare against
  const [showDropped, setShowDropped] = useState(true)
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

  const fetchPreview = (v: Engine): Promise<Preview> =>
    fetch(`${API_BASE}/strategies/${v}/preview`, { headers: getAuthHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))

  const load = (v: Engine = engine) => {
    setLoading(true)
    setError(null)
    Promise.all([fetchPreview(v), v === 'v8' ? fetchPreview('v7') : Promise.resolve(null)])
      .then(([d, base]) => { setData(d); setV7Cards(base ? base.layers.flatMap(L => L.items) : null) })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }
  const switchEngine = (v: Engine) => {
    if (v === engine) return
    setEngine(v)
    try { localStorage.setItem(ENGINE_KEY, v) } catch { /* remembered tab is a convenience */ }
    setOpen(null)
    load(v)
  }
  useEffect(() => { load(); loadKnobs() }, [])
  useDataAsOfPoll(() => load())   // re-build when a sync lands

  const all = useMemo(() => (data ? data.layers.flatMap(L => L.items) : []), [data])

  // V8 mode only: how each card compares with V7, and what V7 had that V8 dropped
  const diff = useMemo(() => {
    if (engine !== 'v8' || !v7Cards) return null
    const v7Titles = new Set(v7Cards.map(c => `${cardKey(c)}|${c.title}`))
    const v7ByKey = new Map<string, Card[]>()
    v7Cards.forEach(c => v7ByKey.set(cardKey(c), [...(v7ByKey.get(cardKey(c)) ?? []), c]))
    const v8Titles = new Set(all.map(c => `${cardKey(c)}|${c.title}`))
    const v8Keys = new Set(all.map(cardKey))
    const tag = new Map<string, { kind: 'new' | 'changed'; was?: string }>()
    all.forEach(c => {
      if (v7Titles.has(`${cardKey(c)}|${c.title}`)) return
      const prior = v7ByKey.get(cardKey(c))
      tag.set(c.id, prior ? { kind: 'changed', was: prior.map(p => p.title).join(' / ') } : { kind: 'new' })
    })
    const dropped = v7Cards.filter(c => !v8Keys.has(cardKey(c)) && !v8Titles.has(`${cardKey(c)}|${c.title}`))
    return { tag, dropped }
  }, [engine, v7Cards, all])

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

  const V = engine.toUpperCase()
  if (error) return <div className={styles.page}><p className={styles.error}>Could not load the {V} queue: {error}</p></div>
  if (loading || !data) return <div className={styles.page}><p className={styles.muted}>Building the {V} queue…</p></div>
  const dropped = (diff?.dropped ?? []).filter(c => !selectedAccount || c.account === selectedAccount || c.account === 'Portfolio')

  const { split } = data
  const stOver = split.short_term_pct > split.target.short_term_pct
  const estTotal = rows.reduce((s, c) => s + (c.earn ?? 0), 0)

  // group headers when sorted by account
  let lastGroup: string | null = null

  return (
    <div className={styles.page}>
      <div className={styles.banner}>
        <AlertTriangle size={16} />
        {engine === 'v8'
          ? <span><strong>V8 — the live rulebook</strong> since 10/22; the same queue drives Option Execution and the email. Cards tagged <em>new</em> or <em>changed</em> differ from V7; V7 cards V8 drops are listed under the queue.</span>
          : <span><strong>V7 — the previous rulebook</strong>, kept for reference. Nothing here is acted on; Option Execution and the email run V8.</span>}
      </div>

      <header className={styles.header}>
        <div>
          <h1>{engine === 'v8' ? 'Notifications V8 (live)' : 'Notifications V7 (previous)'}</h1>
          <div className={styles.sub}>
            as of {data.as_of} · positions {data.data_as_of.options?.slice(0, 16)} · cash {data.data_as_of.cash}
          </div>
        </div>
        <div className={styles.headerBtns}>
          <span className={styles.engineToggle} role="group" aria-label="Engine">
            {(['v7', 'v8'] as Engine[]).map(v => (
              <button key={v} className={clsx(styles.engineToggleBtn, engine === v && styles.engineToggleBtnActive)}
                      onClick={() => switchEngine(v)} aria-pressed={engine === v}
                      title={v === 'v7' ? 'V7 — the previous rulebook' : 'V8 — the live rulebook, compared card by card with V7'}>
                {v.toUpperCase()}
              </button>
            ))}
          </span>
          <button className={clsx(styles.refresh, showKnobs && styles.refreshActive)} onClick={() => setShowKnobs(v => !v)} title="Knobs — every number the engine uses"><Settings size={16} /></button>
          <SyncButtons className={styles.refresh} onDone={load} />
          <button className={styles.refresh} onClick={() => load()} title="Rebuild from the data already synced"><RefreshCw size={16} /></button>
        </div>
      </header>

      {showKnobs && knobs && (() => {
        const groups = Array.from(new Set(Object.values(knobs).map(k => k.group)))
        return (
          <section className={styles.knobs}>
            <div className={styles.knobsHead}>
              <div>
                <strong>Knobs</strong>
                <span className={styles.muted}> — every number the engine uses. A change is written to data/policy_v2.json and the next build picks it up.
                  {engine === 'v8' && ' V8 inherits these; the ones marked V8 are pinned in data/policy_v8.json, so editing them here changes V7 only.'}</span>
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
                      <span className={styles.knobLabel}>{k.label}{engine === 'v8' && data.overridden_knobs?.includes(key) && <span className={styles.v8Tag}>V8</span>}</span>
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

      {engine === 'v8' && (data.differences_from_v7?.length ?? 0) > 0 && (
        <details className={styles.v8Rules}>
          <summary>What V8 does differently ({data.differences_from_v7!.length} rules)</summary>
          <ul>{data.differences_from_v7!.map((d, i) => <li key={i}>{d}</li>)}</ul>
        </details>
      )}

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
        <span className={styles.engineTag}>{V} · two books, four layers
          {diff && ` · ${diff.tag.size} differ from V7, ${dropped.length} dropped`}</span>
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
          const d8 = diff?.tag.get(c.id)
          return (
            <div key={c.id}>
              {header && <div className={styles.groupHeader}>{header}</div>}
              <div className={clsx(styles.item, d8 && styles.itemV8)}>
                <button className={styles.row} onClick={() => setOpen(open === c.id ? null : c.id)}>
                  <span className={styles.action} style={{ color: ACTION_COLOR[c.action] ?? 'var(--color-text-secondary)', borderColor: ACTION_COLOR[c.action] ?? 'var(--color-border)' }}>{c.action}</span>
                  <span className={styles.sym}>{c.symbol}</span>
                  <span className={styles.acct}>{c.account}</span>
                  <span className={styles.title}>{c.title}<span className={styles.detailInline}> · {c.detail}</span></span>
                  <span className={styles.layerTag} title={LAYER_NAME[c.layer]}>L{c.layer}</span>
                  {d8 && <span className={styles.v8Tag} title={d8.was ? `V7: ${d8.was}` : 'Not in V7'}>{d8.kind}</span>}
                  {rsi != null && <span className={styles.chip}>RSI {Math.round(rsi)}</span>}
                  {c.assumption && <span className={styles.flag} title={c.assumption}>assumption</span>}
                  {c.earn != null && <span className={styles.earn}>Earn ~{formatCurrency(c.earn)}</span>}
                  <ChevronDown size={14} className={clsx(styles.chev, open === c.id && styles.chevOpen)} />
                </button>
                {open === c.id && (
                  <div className={styles.why}>
                    <div className={styles.whyRule}>{LAYER_NAME[c.layer]}</div>
                    <div className={styles.whyDetail}>{c.detail}</div>
                    {d8?.was && <div className={styles.whyDetail}>V7 instead: {d8.was}</div>}
                    <div>{c.why}</div>
                    {c.assumption && <div className={styles.assumption}>⚠ {c.assumption}</div>}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {engine === 'v8' && dropped.length > 0 && (
        <div className={styles.dropped}>
          <button className={styles.rulesToggle} onClick={() => setShowDropped(v => !v)}>
            {showDropped ? 'hide' : 'show'} {dropped.length} V7 card{dropped.length === 1 ? '' : 's'} V8 drops
          </button>
          {showDropped && dropped.sort((a, b) => (acctRank(a.account) - acctRank(b.account)) || (a.layer - b.layer)).map(c => (
            <div key={c.id} className={clsx(styles.item, styles.itemDropped)}>
              <div className={styles.row}>
                <span className={styles.action}>{c.action}</span>
                <span className={styles.sym}>{c.symbol}</span>
                <span className={styles.acct}>{c.account}</span>
                <span className={styles.title}>{c.title}</span>
                <span className={styles.layerTag}>L{c.layer}</span>
                <span className={styles.v8Tag}>dropped</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className={styles.footnote}>
        Strikes and premiums are the same heuristics V6 uses — estimates, not quotes. Cards marked <em>assumption</em> encode a rule Neel has not stated yet; they are listed in data/policy_v2.json. Put-only names (bucket C): {data.lists.put_only.join(', ')}.
      </p>
    </div>
  )
}
