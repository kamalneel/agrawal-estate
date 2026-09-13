/**
 * Reusable period selector button group for chart time ranges.
 *
 * Usage:
 *   <PeriodSelector options={PERIOD_PRESETS.STANDARD} value={period} onChange={setPeriod} />
 *
 * Two kinds of key: rolling windows ('1w', '30d', '90d', 'ytd', '1y') and
 * calendar years ('y2025'). `periodBounds` turns either into a date range
 * so every chart filters the same way instead of each keeping its own
 * switch statement.
 */
import clsx from 'clsx'
import styles from './PeriodSelector.module.css'

export interface PeriodOption {
  key: string | null
  label: string
  /** visual gap before this button — separates rolling windows from calendar years */
  gapBefore?: boolean
}

interface PeriodSelectorProps {
  options: readonly PeriodOption[]
  value: string | null
  onChange: (key: string | null) => void
}

/** Standard presets used across multiple pages */
export const PERIOD_PRESETS = {
  /** 1M / 3M / YTD / 1Y / ALL — used for account-level charts */
  STANDARD: [
    { key: '30d', label: '1M' },
    { key: '90d', label: '3M' },
    { key: 'ytd', label: 'YTD' },
    { key: '1y', label: '1Y' },
    { key: null, label: 'ALL' },
  ] as const,
  /** 1D / 1W / 1M / 3M / YTD / 1Y / ALL — Robinhood-style for portfolio charts */
  EXTENDED: [
    { key: '1d', label: '1D' },
    { key: '1w', label: '1W' },
    { key: '30d', label: '1M' },
    { key: '90d', label: '3M' },
    { key: 'ytd', label: 'YTD' },
    { key: '1y', label: '1Y' },
    { key: null, label: 'ALL' },
  ] as const,
} as const

const YEAR_KEY = /^y(\d{4})$/
const DAY_MS = 86400000

const isoDate = (d: Date) => d.toISOString().slice(0, 10)

/**
 * Inclusive ISO date range for a period key, or null for ALL / unknown.
 * Rolling windows are open-ended (`to` undefined); calendar years are
 * bounded on both sides so '2025' never bleeds into January 2026.
 */
export function periodBounds(key: string | null, today = new Date()): { from: string; to?: string } | null {
  if (!key) return null
  const year = YEAR_KEY.exec(key)
  if (year) return { from: `${year[1]}-01-01`, to: `${year[1]}-12-31` }
  switch (key) {
    case '1d':  return { from: isoDate(new Date(today.getTime() - 1 * DAY_MS)) }
    case '1w':  return { from: isoDate(new Date(today.getTime() - 7 * DAY_MS)) }
    case '30d': return { from: isoDate(new Date(today.getTime() - 30 * DAY_MS)) }
    case '90d': return { from: isoDate(new Date(today.getTime() - 90 * DAY_MS)) }
    case 'ytd': return { from: `${today.getFullYear()}-01-01` }
    case '1y':  return { from: isoDate(new Date(today.getTime() - 365 * DAY_MS)) }
    default:    return null
  }
}

/** Filter a dated series to a period key. ALL / unknown keys return it untouched. */
export function filterByPeriod<T extends { date: string }>(rows: T[], key: string | null, today = new Date()): T[] {
  const b = periodBounds(key, today)
  if (!b) return rows
  return rows.filter(r => r.date >= b.from && (b.to === undefined || r.date <= b.to))
}

/**
 * One button per calendar year the data covers, newest first, so '2024'
 * appears the day history reaches back that far and never before (an empty
 * chart looks like a bug, not an absence of data). The first is flagged
 * `gapBefore` so the years read as their own group after the rolling windows.
 */
export function yearPeriodOptions(firstDate: string | undefined, lastDate: string | undefined): PeriodOption[] {
  if (!firstDate || !lastDate) return []
  const first = Number(firstDate.slice(0, 4))
  const last = Number(lastDate.slice(0, 4))
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first) return []
  const out: PeriodOption[] = []
  for (let y = last; y >= first; y--) out.push({ key: `y${y}`, label: String(y), gapBefore: y === last })
  return out
}

export function PeriodSelector({ options, value, onChange }: PeriodSelectorProps) {
  return (
    <div className={styles.periodButtons}>
      {options.map(({ key, label, gapBefore }) => (
        <button
          key={label}
          className={clsx(styles.periodButton, gapBefore && styles.periodButtonGap, value === key && styles.periodButtonActive)}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
