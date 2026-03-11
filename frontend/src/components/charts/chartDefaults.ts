/**
 * Shared default props for Recharts components.
 * Pages import these and spread onto CartesianGrid, XAxis, YAxis.
 */

export const GRID_PROPS = {
  strokeDasharray: '3 3',
  stroke: 'rgba(255,255,255,0.05)',
  vertical: false,
} as const

export const X_AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tick: { fill: '#737373', fontSize: 12 },
  dy: 10,
} as const

export const Y_AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tick: { fill: '#737373', fontSize: 12 },
  dx: -10,
  width: 70,
} as const

export const CHART_MARGINS = {
  top: 20,
  right: 30,
  left: 20,
  bottom: 20,
} as const

/** Standard color used for primary charts */
export const CHART_GREEN = '#00D632'
