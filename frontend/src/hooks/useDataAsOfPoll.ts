/**
 * Poll the backend's cheap freshness probe and call `onChange` when a sync
 * has landed since the page last loaded. The hourly Robinhood sync writes
 * new positions; without this a tab drawn before the sync keeps showing
 * cards for trades already made (Neel, 2026-09-17: a "sell 6 NVDA calls"
 * card for calls sold the day before).
 *
 * Polls every `intervalMs` (default 2 min) while the tab is visible; also
 * checks immediately when the tab becomes visible again.
 */
import { useEffect, useRef } from 'react'
import { getAuthHeaders } from '../contexts/AuthContext'

const API_BASE = '/api/v1'

export function useDataAsOfPoll(onChange: () => void, intervalMs = 120_000) {
  const last = useRef<string | null>(null)
  const cb = useRef(onChange)
  cb.current = onChange

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const r = await fetch(`${API_BASE}/strategies/data-as-of`, { headers: getAuthHeaders() })
        if (!r.ok) return
        const d = await r.json()
        const stamp = `${d.positions}|${d.cash}`
        if (last.current === null) { last.current = stamp; return }   // first read = baseline
        if (stamp !== last.current && !cancelled) { last.current = stamp; cb.current() }
      } catch { /* network blip — try again next tick */ }
    }
    check()
    const id = setInterval(check, intervalMs)
    const onVis = () => { if (document.visibilityState === 'visible') check() }
    document.addEventListener('visibilitychange', onVis)
    return () => { cancelled = true; clearInterval(id); document.removeEventListener('visibilitychange', onVis) }
  }, [intervalMs])
}
