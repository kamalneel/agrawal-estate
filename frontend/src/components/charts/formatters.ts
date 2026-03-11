/**
 * Shared chart formatting functions used across all chart pages.
 */

/** Format as currency with no decimals: $1,234 */
export const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

/** Format as currency with 2 decimals: $1,234.56 */
export const formatCurrencyPrecise = (value: number): string =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)

/** Short currency for Y-axis labels: $12K, $1.5M */
export const formatCurrencyShort = (value: number): string => {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`
  return `$${value}`
}

/** Format as percentage with sign: +2.50% or -1.30% */
export const formatPercent = (value: number): string => {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

/** Format a number with commas: 1,234 */
export const formatNumber = (value: number): string =>
  new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
