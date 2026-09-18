import { useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'

/**
 * Sync buttons — start a real Robinhood pull (POST /strategies/sync?mode=…,
 * which runs scripts/scheduled_refresh.sh headlessly) and show progress
 * until it lands. Neel, 2026-09-18: one button per kind of sync, so a
 * quick price refresh does not cost a full five-minute account sync.
 *
 *   state  — positions, cash and fills for all six accounts (~5 min)
 *   prices — live quotes + implied vol for every tracked symbol (~1 min)
 *   chains — option chains for tracked symbols (not built yet)
 *
 * The page re-fetches when a sync lands (useDataAsOfPoll); this component
 * only starts runs and reports state. Only a failed run emails.
 */

export type SyncMode = 'state' | 'prices' | 'chains' | 'full'

interface SyncStatus {
  running?: boolean
  ok?: boolean
  ran_at?: string
  started_at?: string
  trigger?: string
  mode?: string
  report?: string
}

const API = '/api/v1/strategies'
const POLL_MS = 10_000

const LABEL: Record<SyncMode, string> = { state: 'Sync accounts', prices: 'Sync prices', chains: 'Sync chains', full: 'Full sync' }
const HELP: Record<SyncMode, string> = {
  state: 'Positions, cash and fills for all six accounts. About 5 minutes.',
  prices: 'Live stock prices and implied vol for every tracked symbol (held, allocation targets, policy). About a minute.',
  chains: 'Option chains for tracked symbols. Not built yet.',
  full: 'Everything the scheduled run does. About 5 minutes.',
}

export function SyncButtons({ className, modes = ['state', 'prices', 'chains'], onDone }: {
  className?: string; modes?: SyncMode[]; onDone?: () => void
}) {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const [busyMode, setBusyMode] = useState<SyncMode | null>(null)
  const [note, setNote] = useState<string>('')
  const timer = useRef<number | null>(null)

  const readStatus = async (): Promise<SyncStatus | null> => {
    try {
      const r = await fetch(`${API}/sync/status`, { headers: getAuthHeaders() })
      if (!r.ok) return null
      const s = (await r.json()) as SyncStatus
      setStatus(s)
      return s
    } catch { return null }
  }

  const stopPolling = () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null } }

  const pollUntilDone = () => {
    stopPolling()
    timer.current = window.setInterval(async () => {
      const s = await readStatus()
      if (s && !s.running) {
        stopPolling()
        setBusyMode(null)
        setNote(s.ok ? `${s.mode ?? 'sync'} done` : `${s.mode ?? 'sync'} failed — ${(s.report || '').split('\n')[0].slice(0, 120)}`)
        onDone?.()
      }
    }, POLL_MS)
  }

  useEffect(() => {
    readStatus().then(s => { if (s?.running) { setBusyMode((s.mode as SyncMode) || 'full'); setNote('Sync in progress…'); pollUntilDone() } })
    return stopPolling
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const start = async (mode: SyncMode) => {
    setBusyMode(mode)
    setNote(`Starting ${LABEL[mode].toLowerCase()}…`)
    try {
      const r = await fetch(`${API}/sync?mode=${mode}`, { method: 'POST', headers: getAuthHeaders() })
      if (r.status === 202) { setNote(`${LABEL[mode]} running…`); pollUntilDone() }
      else if (r.status === 409) { setNote('A sync is already running…'); pollUntilDone() }
      else { setBusyMode(null); setNote(`Could not start (HTTP ${r.status})`) }
    } catch (e) {
      setBusyMode(null)
      setNote(`Could not start: ${String(e)}`)
    }
  }

  const last = status?.ran_at
    ? `last ${status.mode ?? 'sync'} ${new Date(status.ran_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}${status.ok === false ? ' FAILED' : ''}`
    : ''

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }} title={busyMode ? note : last}>
      {modes.map(m => (
        <button key={m} className={className} onClick={() => start(m)} disabled={busyMode !== null || m === 'chains'}
          title={busyMode ? note : `${HELP[m]}${last ? ` · ${last}` : ''}`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, width: 'auto', padding: '0 10px', whiteSpace: 'nowrap', opacity: m === 'chains' ? 0.5 : 1 }}>
          <RefreshCw size={14} style={busyMode === m ? { animation: 'spin 1s linear infinite' } : undefined} />
          <span style={{ fontSize: 'var(--text-xs)' }}>{busyMode === m ? 'Syncing…' : LABEL[m]}</span>
        </button>
      ))}
      {note && !busyMode && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>{note}</span>}
      <style>{'@keyframes spin { to { transform: rotate(360deg) } }'}</style>
    </div>
  )
}

/** Back-compat single button (full sync). */
export function SyncButton({ className, onDone }: { className?: string; onDone?: () => void }) {
  return <SyncButtons className={className} modes={['full']} onDone={onDone} />
}
