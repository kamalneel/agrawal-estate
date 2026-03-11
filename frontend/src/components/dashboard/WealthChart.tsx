import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import styles from './WealthChart.module.css'
import {
  formatCurrency as sharedFormatCurrency,
  formatCurrencyShort,
  GRID_PROPS,
  X_AXIS_PROPS,
  Y_AXIS_PROPS,
  CHART_MARGINS,
  CHART_GREEN,
} from '../charts'

interface WealthDataPoint {
  year: number
  age: number
  netWorth: number
}

interface WealthChartProps {
  data: WealthDataPoint[]
}

const formatCurrency = (value: number | undefined) => {
  if (value === undefined || value === null || isNaN(value)) return '$0'
  return formatCurrencyShort(value)
}

const formatFullCurrency = (value: number | undefined) => {
  if (value === undefined || value === null || isNaN(value)) return '$0'
  return sharedFormatCurrency(value)
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{
    value: number
    payload: WealthDataPoint
  }>
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    return (
      <div className={styles.tooltip}>
        <div className={styles.tooltipYear}>{data.year}</div>
        <div className={styles.tooltipAge}>Age {data.age}</div>
        <div className={styles.tooltipValue}>{formatFullCurrency(data.netWorth)}</div>
      </div>
    )
  }
  return null
}

export function WealthChart({ data }: WealthChartProps) {
  return (
    <div className={styles.chartContainer}>
      <ResponsiveContainer width="100%" height={400}>
        <AreaChart data={data} margin={CHART_MARGINS}>
          <defs>
            <linearGradient id="wealthGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.3} />
              <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="year"
            {...X_AXIS_PROPS}
            interval={2}
            tickFormatter={(year) => `${year}`}
          />
          <YAxis
            {...Y_AXIS_PROPS}
            tickFormatter={formatCurrency}
            width={80}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="netWorth"
            stroke={CHART_GREEN}
            strokeWidth={3}
            fill="url(#wealthGradient)"
            animationDuration={1500}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Age markers */}
      <div className={styles.ageMarkers}>
        {data
          .filter((_, i) => i % 5 === 0 || i === data.length - 1)
          .map((point) => (
            <div key={point.year} className={styles.ageMarker}>
              <span className={styles.ageLabel}>Age {point.age}</span>
              <span className={styles.ageValue}>{formatCurrency(point.netWorth)}</span>
            </div>
          ))}
      </div>
    </div>
  )
}
