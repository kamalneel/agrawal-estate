/**
 * Reusable period selector button group for chart time ranges.
 *
 * Usage:
 *   <PeriodSelector options={PERIOD_PRESETS.STANDARD} value={period} onChange={setPeriod} />
 */
import clsx from 'clsx'
import styles from './PeriodSelector.module.css'

export interface PeriodOption {
  key: string | null
  label: string
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

export function PeriodSelector({ options, value, onChange }: PeriodSelectorProps) {
  return (
    <div className={styles.periodButtons}>
      {options.map(({ key, label }) => (
        <button
          key={label}
          className={clsx(styles.periodButton, value === key && styles.periodButtonActive)}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
