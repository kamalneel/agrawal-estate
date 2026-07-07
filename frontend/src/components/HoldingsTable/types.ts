import { ReactNode } from 'react'

export interface HoldingsRow {
  optionsSold?: number
  optionsBought?: number
  symbol: string
  shares: number
  currentPrice: number
  value: number
  isCash?: boolean

  // Investment variant fields
  percentOfPortfolio?: number
  optionIncomeAllTime?: number | null
  optionIncomeRecent?: number | null

  // Options variant fields
  options?: number
  soldContracts?: number
  unsoldContracts?: number
  utilizationStatus?: 'none' | 'partial' | 'full'
  weeklyIncome?: number
  monthlyIncome?: number
  yearlyIncome?: number
  premiumSource?: string
  subtitle?: string

  // Income variant fields
  dividendIncome?: number
  optionsIncome?: number
  totalIncome?: number

  // Investment growth variant fields
  costBasis?: number | null
  totalReturnPct?: number | null
  growthYTD?: number | null
  growth1Y?: number | null
  growth5Y?: number | null
  holdingPeriodDays?: number | null
}

export interface TableContext {
  totalPortfolioValue: number
  rows: HoldingsRow[]
}

export interface ColumnDef {
  key: string
  header: string
  headerSub?: string
  align?: 'left' | 'center' | 'right'
  hideForCash?: boolean
  sortValue: (row: HoldingsRow, ctx: TableContext) => number | string
  renderCell: (row: HoldingsRow, ctx: TableContext) => ReactNode
  renderFooter?: (rows: HoldingsRow[], ctx: TableContext) => ReactNode
}

export interface HoldingsTableProps {
  rows: HoldingsRow[]
  columns: ColumnDef[]
  defaultSortKey?: string
  defaultSortDir?: 'asc' | 'desc'
  className?: string
  showFooter?: boolean
}
