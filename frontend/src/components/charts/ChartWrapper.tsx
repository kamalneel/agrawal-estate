/**
 * Chart section layout wrapper: title + optional period selector + chart container + empty state.
 *
 * This is a layout container, NOT a chart abstraction. Pages compose their own
 * Recharts chart types (AreaChart, BarChart, etc.) as children.
 *
 * Usage:
 *   <ChartWrapper title="Portfolio Growth" periodOptions={PERIOD_PRESETS.EXTENDED} periodValue={period} onPeriodChange={setPeriod}>
 *     <ResponsiveContainer width="100%" height={300}>
 *       <AreaChart data={data}>...</AreaChart>
 *     </ResponsiveContainer>
 *   </ChartWrapper>
 */
import type { ReactNode } from 'react'
import { PeriodSelector } from './PeriodSelector'
import type { PeriodOption } from './PeriodSelector'
import styles from './ChartWrapper.module.css'

interface ChartWrapperProps {
  title: string
  children: ReactNode
  /** Pass period selector options to show the selector. Omit to hide it. */
  periodOptions?: readonly PeriodOption[]
  periodValue?: string | null
  onPeriodChange?: (key: string | null) => void
  /** Shown when there is no data */
  emptyMessage?: string
  /** Whether to show the empty state instead of children */
  isEmpty?: boolean
}

export function ChartWrapper({
  title,
  children,
  periodOptions,
  periodValue,
  onPeriodChange,
  emptyMessage = 'No data available.',
  isEmpty = false,
}: ChartWrapperProps) {
  return (
    <section className={styles.chartSection}>
      <div className={styles.chartHeader}>
        <h2>{title}</h2>
        {periodOptions && onPeriodChange && (
          <PeriodSelector
            options={periodOptions}
            value={periodValue ?? null}
            onChange={onPeriodChange}
          />
        )}
      </div>
      {isEmpty ? (
        <div className={styles.chartEmpty}>
          <p>{emptyMessage}</p>
        </div>
      ) : (
        <div className={styles.chartContainer}>{children}</div>
      )}
    </section>
  )
}
