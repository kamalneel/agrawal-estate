import { useMemo } from 'react'
import styles from './GoalsStrip.module.css'

/** Yield-tracker gauges (Objective 2): 1%/mo on holdings, 2%/mo on cash
 *  (cash = margin capacity per goal_settings). Current month shows pace —
 *  earned vs where the target should be by today. */

interface GoalSettings {
  holdings_goal: { monthly_target_pct: number }
  cash_goal: { monthly_target_pct: number }
  margin_limits: Record<string, number>
}

interface CapacityMonth {
  capacity: number
  partial: boolean
}

interface GoalsStripProps {
  year: number | 'all'
  month: number | null
  capacityByMonth: Record<string, CapacityMonth>
  optionsByType: Record<string, { calls: number; puts: number }>
  dividendsByMonth: Record<string, number>
  equityByMonth: Record<string, number>
  liveEquity: number | null
  settings: GoalSettings | null
}

function fmt(v: number): string {
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function monthKey(y: number, m: number): string {
  return `${y}-${String(m).padStart(2, '0')}`
}

export function GoalsStrip({ year, month, capacityByMonth, optionsByType, dividendsByMonth, equityByMonth, liveEquity, settings }: GoalsStripProps) {
  const now = new Date()
  const curKey = monthKey(now.getFullYear(), now.getMonth() + 1)

  const gauges = useMemo(() => {
    if (!settings || year === 'all') return null
    const holdingsPct = settings.holdings_goal.monthly_target_pct / 100
    const cashPct = settings.cash_goal.monthly_target_pct / 100
    const marginTotal = Object.values(settings.margin_limits).reduce((s, v) => s + v, 0)

    // holdings base for a month: positions history, else latest earlier
    // entry, else live value
    const equityKeys = Object.keys(equityByMonth).sort()
    const holdingsBase = (key: string): number | null => {
      if (equityByMonth[key]) return equityByMonth[key]
      const earlier = equityKeys.filter(k => k < key)
      if (earlier.length) return equityByMonth[earlier[earlier.length - 1]]
      return liveEquity
    }

    // months included in the selected period (elapsed only for current year)
    const months: string[] = []
    if (month !== null) {
      months.push(monthKey(year, month))
    } else {
      const last = year === now.getFullYear() ? now.getMonth() + 1 : 12
      for (let m = 1; m <= last; m++) months.push(monthKey(year, m))
    }

    // put capacity per month (margin lines + cash across accounts);
    // carry the latest earlier month forward when a month is missing
    const capKeys = Object.keys(capacityByMonth).sort()
    const capacityFor = (key: string): CapacityMonth | null => {
      if (capacityByMonth[key]) return capacityByMonth[key]
      const earlier = capKeys.filter(k => k < key)
      return earlier.length ? capacityByMonth[earlier[earlier.length - 1]] : null
    }

    let holdingsIncome = 0, cashIncome = 0, holdingsTarget = 0, cashTarget = 0
    let baseShown: number | null = null
    let cashBaseShown: number | null = null
    let anyPartial = false
    for (const k of months) {
      const bt = optionsByType[k] || { calls: 0, puts: 0 }
      holdingsIncome += (bt.calls || 0) + (dividendsByMonth[k] || 0)
      cashIncome += bt.puts || 0
      const base = holdingsBase(k)
      baseShown = base ?? baseShown
      const cap = capacityFor(k)
      const cashBase = cap ? cap.capacity : marginTotal
      cashBaseShown = cashBase
      if (cap?.partial) anyPartial = true
      // current month targets are paced to today
      const paceFactor = k === curKey ? now.getDate() / new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() : 1
      if (base) holdingsTarget += base * holdingsPct * paceFactor
      cashTarget += cashBase * cashPct * paceFactor
    }

    const isPaced = months.includes(curKey)
    return {
      holdings: {
        income: holdingsIncome, target: holdingsTarget,
        base: baseShown, pct: baseShown ? (holdingsIncome / baseShown) * 100 : null,
        targetPct: settings.holdings_goal.monthly_target_pct * (month !== null ? 1 : months.length),
      },
      cash: {
        income: cashIncome, target: cashTarget,
        base: cashBaseShown ?? marginTotal,
        pct: cashBaseShown ? (cashIncome / cashBaseShown) * 100 : null,
        targetPct: settings.cash_goal.monthly_target_pct * (month !== null ? 1 : months.length),
      },
      isPaced,
      anyPartial,
      nMonths: months.length,
    }
  }, [settings, year, month, capacityByMonth, optionsByType, dividendsByMonth, equityByMonth, liveEquity])

  if (!gauges) return null

  const rows: Array<{ title: string; sub: string; g: { income: number; target: number; base: number | null; pct: number | null; targetPct: number } }> = [
    {
      title: `Holdings Goal — ${settings!.holdings_goal.monthly_target_pct}%/mo`,
      sub: `calls + dividends on ${gauges.holdings.base ? fmt(gauges.holdings.base) : '—'} holdings`,
      g: gauges.holdings,
    },
    {
      title: `Cash Goal — ${settings!.cash_goal.monthly_target_pct}%/mo`,
      sub: `puts on ${fmt(gauges.cash.base!)} put capacity (margin lines + cash)`
        + (gauges.anyPartial ? ' — margin-only history before Jun 2026' : ''),
      g: gauges.cash,
    },
  ]

  return (
    <div className={styles.strip}>
      {rows.map(({ title, sub, g }) => {
        const ratio = g.target > 0 ? g.income / g.target : 0
        const color = ratio >= 1 ? '#00D632' : ratio >= 0.7 ? '#FFB800' : '#FF5A5A'
        return (
          <div key={title} className={styles.gauge}>
            <div className={styles.gaugeHeader}>
              <span className={styles.gaugeTitle}>{title}</span>
              <span className={styles.gaugePct} style={{ color }}>
                {g.target > 0 ? `${Math.round(ratio * 100)}%` : '—'}
              </span>
            </div>
            <div className={styles.gaugeAmounts}>
              <span className={styles.earned} style={{ color }}>{fmt(g.income)}</span>
              <span className={styles.target}>
                of {fmt(g.target)}{gauges.isPaced ? ' pace-to-date' : ' target'}
              </span>
            </div>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%`, background: color }}
              />
            </div>
            <div className={styles.gaugeSub}>{sub}</div>
          </div>
        )
      })}
    </div>
  )
}
