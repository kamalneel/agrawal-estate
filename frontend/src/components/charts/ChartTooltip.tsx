/**
 * Shared chart tooltip component.
 *
 * Supports single-value and multi-series tooltips via Recharts' <Tooltip content={...} />.
 *
 * Usage:
 *   <Tooltip content={<ChartTooltip />} />
 *   <Tooltip content={<ChartTooltip valueFormatter={formatCurrencyPrecise} />} />
 */
import styles from './ChartTooltip.module.css'

interface ChartTooltipProps {
  active?: boolean
  payload?: Array<{
    value: number
    name?: string
    dataKey?: string
    color?: string
    payload?: Record<string, any>
  }>
  label?: string
  /** Custom label key from the data point (defaults to using `label` prop) */
  labelKey?: string
  /** Custom formatter for values. Defaults to USD currency (no decimals). */
  valueFormatter?: (value: number) => string
  /** Custom formatter for the label/header line */
  labelFormatter?: (label: string) => string
}

const defaultFormat = (v: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(v)

export function ChartTooltip({
  active,
  payload,
  label,
  labelKey,
  valueFormatter = defaultFormat,
  labelFormatter,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null

  const displayLabel = labelKey
    ? payload[0]?.payload?.[labelKey] ?? label
    : label

  const formattedLabel = labelFormatter
    ? labelFormatter(String(displayLabel))
    : String(displayLabel ?? '')

  // Single series — simple layout
  if (payload.length === 1) {
    return (
      <div className={styles.chartTooltip}>
        <div className={styles.tooltipLabel}>{formattedLabel}</div>
        <div className={styles.tooltipValue}>{valueFormatter(payload[0].value)}</div>
      </div>
    )
  }

  // Multi-series
  return (
    <div className={styles.chartTooltip}>
      <div className={styles.tooltipLabel}>{formattedLabel}</div>
      {payload.map((entry, i) => (
        <div key={i} className={styles.tooltipRow}>
          {entry.color && (
            <span className={styles.tooltipDot} style={{ background: entry.color }} />
          )}
          <span className={styles.tooltipRowName}>{entry.name ?? entry.dataKey}</span>
          <span className={styles.tooltipRowValue}>{valueFormatter(entry.value)}</span>
        </div>
      ))}
    </div>
  )
}
