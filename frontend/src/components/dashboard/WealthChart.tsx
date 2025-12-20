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
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`
  }
  if (value >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`
  }
  return `$${value}`
}

const formatFullCurrency = (value: number | undefined) => {
  if (value === undefined || value === null || isNaN(value)) return '$0'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
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
        <AreaChart
          data={data}
          margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
        >
          <defs>
            <linearGradient id="wealthGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00D632" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#00D632" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.05)"
            vertical={false}
          />
          <XAxis
            dataKey="year"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#737373', fontSize: 12 }}
            dy={10}
            interval={2}
            tickFormatter={(year) => `${year}`}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#737373', fontSize: 12 }}
            tickFormatter={formatCurrency}
            dx={-10}
            width={80}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="netWorth"
            stroke="#00D632"
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

