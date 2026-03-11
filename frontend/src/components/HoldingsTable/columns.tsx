import { CheckCircle, XCircle } from 'lucide-react'
import type { ColumnDef } from './types'
import styles from './HoldingsTable.module.css'

// --- Formatting helpers ---

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

const formatNumber = (value: number) =>
  new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

// --- Core columns (used by all variants) ---

export function symbolColumn(opts?: { showSubtitle?: boolean }): ColumnDef {
  return {
    key: 'symbol',
    header: 'Symbol',
    align: 'left',
    sortValue: (row) => row.symbol,
    renderCell: (row) => (
      <div className={styles.symbolCell}>
        <strong>{row.symbol}</strong>
        {row.isCash && <span className={styles.cashLabel}>Cash-Secured Puts</span>}
        {opts?.showSubtitle && !row.isCash && row.subtitle && (
          <span className={styles.subtitle}>{row.subtitle}</span>
        )}
        {opts?.showSubtitle && !row.isCash && row.utilizationStatus === 'none' && (
          <span className={styles.unsoldLabel}>Not Sold</span>
        )}
      </div>
    ),
  }
}

export function sharesColumn(): ColumnDef {
  return {
    key: 'shares',
    header: 'Shares',
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row.shares,
    renderCell: (row) => (row.isCash ? '—' : formatNumber(row.shares)),
  }
}

export function priceColumn(headerText?: string): ColumnDef {
  return {
    key: 'price',
    header: headerText || 'Price',
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row.currentPrice,
    renderCell: (row) => (row.isCash ? '—' : formatCurrency(row.currentPrice)),
  }
}

export function valueColumn(): ColumnDef {
  return {
    key: 'value',
    header: 'Total Value',
    align: 'center',
    sortValue: (row) => row.isCash ? row.value : row.shares * row.currentPrice,
    renderCell: (row) => (
      <span className={styles.valueCell}>
        {formatCurrency(row.isCash ? row.value : row.shares * row.currentPrice)}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce(
        (sum, r) => sum + (r.isCash ? r.value : r.shares * r.currentPrice),
        0
      )
      return <strong>{formatCurrency(total)}</strong>
    },
  }
}

// --- Investment variant columns ---

export function percentPortfolioColumn(): ColumnDef {
  return {
    key: 'percent',
    header: '% Portfolio',
    align: 'center',
    sortValue: (row) => row.isCash ? row.value : row.shares * row.currentPrice,
    renderCell: (row, ctx) => {
      const val = row.isCash ? row.value : row.shares * row.currentPrice
      const pct = ctx.totalPortfolioValue > 0 ? (val / ctx.totalPortfolioValue) * 100 : 0
      return (
        <div className={styles.percentBar}>
          <div
            className={styles.percentFill}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
          <span>{pct.toFixed(1)}%</span>
        </div>
      )
    },
  }
}

export function optionIncomeAllTimeColumn(): ColumnDef {
  return {
    key: 'optionIncomeAllTime',
    header: 'Options (All Time)',
    align: 'center',
    sortValue: (row) => row.optionIncomeAllTime ?? -Infinity,
    renderCell: (row) => (
      <span className={row.optionIncomeAllTime ? styles.incomePositive : ''}>
        {row.optionIncomeAllTime ? formatCurrency(row.optionIncomeAllTime) : '—'}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.optionIncomeAllTime ?? 0), 0)
      return total > 0 ? (
        <strong className={styles.incomePositive}>{formatCurrency(total)}</strong>
      ) : (
        '—'
      )
    },
  }
}

export function optionIncomeRecentColumn(header?: string): ColumnDef {
  return {
    key: 'optionIncomeRecent',
    header: header || 'Options (Recent)',
    align: 'center',
    sortValue: (row) => row.optionIncomeRecent ?? -Infinity,
    renderCell: (row) => (
      <span className={row.optionIncomeRecent ? styles.incomePositive : ''}>
        {row.optionIncomeRecent ? formatCurrency(row.optionIncomeRecent) : '—'}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.optionIncomeRecent ?? 0), 0)
      const grandValue = rows.reduce(
        (sum, r) => sum + (r.isCash ? r.value : r.shares * r.currentPrice),
        0
      )
      if (total <= 0) return '—'
      const annualized = total * 52 / 48
      const yieldPct = grandValue > 0 ? (total / grandValue * 52 / 48 * 100).toFixed(2) : '0.00'
      return (
        <strong className={styles.incomePositive}>
          {formatCurrency(annualized)} ({yieldPct}%)
        </strong>
      )
    },
  }
}

export function monthlyYieldColumn(): ColumnDef {
  return {
    key: 'monthlyYield',
    header: '% Monthly Yield',
    align: 'center',
    sortValue: (row) => {
      const val = row.shares * row.currentPrice
      return row.optionIncomeRecent && val > 0
        ? (row.optionIncomeRecent / val) * 52 / 48
        : -Infinity
    },
    renderCell: (row) => {
      if (row.isCash) return '—'
      const val = row.shares * row.currentPrice
      if (row.optionIncomeRecent && val > 0) {
        return (
          <span className={styles.incomePositive}>
            {((row.optionIncomeRecent / val) * 52 / 48 * 100).toFixed(2)}%
          </span>
        )
      }
      return '—'
    },
  }
}

// --- Options variant columns ---

export function optionsBadgeColumn(): ColumnDef {
  return {
    key: 'options',
    header: 'Options',
    align: 'center',
    sortValue: (row) => row.options ?? 0,
    renderCell: (row) => {
      if (row.isCash) return <span className={styles.putsLabel}>Puts</span>
      return (
        <div className={styles.optionsCell}>
          <span
            className={`${styles.optionsBadge} ${
              row.utilizationStatus === 'full'
                ? styles.optionsFull
                : row.utilizationStatus === 'partial'
                  ? styles.optionsPartial
                  : styles.optionsNone
            }`}
          >
            {row.options}
          </span>
          {row.soldContracts !== undefined && row.unsoldContracts !== undefined && (
            <div className={styles.soldUnsoldInfo}>
              {(row.soldContracts ?? 0) > 0 && (
                <span className={styles.soldCount} title="Sold">
                  <CheckCircle size={12} /> {row.soldContracts}
                </span>
              )}
              {(row.unsoldContracts ?? 0) > 0 && (
                <span className={styles.unsoldCount} title="Unsold">
                  <XCircle size={12} /> {row.unsoldContracts}
                </span>
              )}
            </div>
          )}
        </div>
      )
    },
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.options ?? 0), 0)
      return <strong>{total}</strong>
    },
  }
}

export function incomeWithYieldColumn(
  key: string,
  header: string,
  field: 'weeklyIncome' | 'monthlyIncome' | 'yearlyIncome',
  headerSub?: string
): ColumnDef {
  return {
    key,
    header,
    headerSub,
    align: 'center',
    sortValue: (row) => row[field] ?? 0,
    renderCell: (row) => {
      const income = row[field] ?? 0
      const isHardcoded =
        row.premiumSource === 'hardcoded' || row.premiumSource === 'global_default'
      return (
        <div className={`${styles.incomeCellWrap} ${isHardcoded ? styles.hardcodedIncome : ''}`}>
          {isHardcoded && (
            <span className={styles.hardcodedMarker} title="Using hardcoded default premium">
              *
            </span>
          )}
          {formatCurrency(income)}
          {row.value > 0 && (
            <span className={styles.yieldPercent}>
              ({((income / row.value) * 100).toFixed(2)}%)
            </span>
          )}
        </div>
      )
    },
    renderFooter: (rows) => {
      const totalIncome = rows.reduce((sum, r) => sum + (r[field] ?? 0), 0)
      const totalValue = rows.reduce(
        (sum, r) => sum + (r.isCash ? r.value : r.shares * r.currentPrice),
        0
      )
      return (
        <div>
          <strong>{formatCurrency(totalIncome)}</strong>
          {totalValue > 0 && (
            <span className={styles.yieldPercent}>
              ({((totalIncome / totalValue) * 100).toFixed(2)}%)
            </span>
          )}
        </div>
      )
    },
  }
}

// --- Investment growth variant columns ---

export function costBasisColumn(): ColumnDef {
  return {
    key: 'costBasis',
    header: 'Cost Basis',
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row.costBasis ?? -Infinity,
    renderCell: (row) => {
      if (row.isCash || row.costBasis == null) return '—'
      return formatCurrency(row.costBasis)
    },
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.costBasis ?? 0), 0)
      return total > 0 ? <strong>{formatCurrency(total)}</strong> : '—'
    },
  }
}

export function totalReturnColumn(): ColumnDef {
  return {
    key: 'totalReturn',
    header: 'Total Return',
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row.totalReturnPct ?? -Infinity,
    renderCell: (row) => {
      if (row.isCash || row.totalReturnPct == null) return '—'
      const isPositive = row.totalReturnPct >= 0
      return (
        <span style={{ color: isPositive ? '#00D632' : '#FF5A5A' }}>
          {isPositive ? '+' : ''}{row.totalReturnPct.toFixed(1)}%
        </span>
      )
    },
    renderFooter: (rows) => {
      const totalValue = rows.reduce(
        (sum, r) => sum + (r.isCash ? r.value : r.shares * r.currentPrice),
        0
      )
      const totalCost = rows.reduce((sum, r) => sum + (r.costBasis ?? 0), 0)
      if (totalCost > 0) {
        const pct = ((totalValue - totalCost) / totalCost) * 100
        const isPositive = pct >= 0
        return (
          <strong style={{ color: isPositive ? '#00D632' : '#FF5A5A' }}>
            {isPositive ? '+' : ''}{pct.toFixed(1)}%
          </strong>
        )
      }
      return '—'
    },
  }
}

export function stockGrowthColumn(
  key: string,
  header: string,
  field: 'growthYTD' | 'growth1Y' | 'growth5Y'
): ColumnDef {
  return {
    key,
    header,
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row[field] ?? -Infinity,
    renderCell: (row) => {
      if (row.isCash || row[field] == null) return '—'
      const val = row[field]!
      const isPositive = val >= 0
      return (
        <span style={{ color: isPositive ? '#00D632' : '#FF5A5A' }}>
          {isPositive ? '+' : ''}{val.toFixed(1)}%
        </span>
      )
    },
    renderFooter: (rows) => {
      // Weighted average: sum(growth_i * value_i) / sum(value_i) for holdings with data
      let weightedSum = 0
      let totalValue = 0
      for (const r of rows) {
        if (r.isCash || r[field] == null) continue
        const val = r.shares * r.currentPrice
        weightedSum += r[field]! * val
        totalValue += val
      }
      if (totalValue <= 0) return '—'
      const avg = weightedSum / totalValue
      const isPositive = avg >= 0
      return (
        <strong style={{ color: isPositive ? '#00D632' : '#FF5A5A' }}>
          {isPositive ? '+' : ''}{avg.toFixed(1)}%
        </strong>
      )
    },
  }
}

export function holdingPeriodColumn(): ColumnDef {
  return {
    key: 'holdingPeriod',
    header: 'Held',
    align: 'center',
    hideForCash: true,
    sortValue: (row) => row.holdingPeriodDays ?? -Infinity,
    renderCell: (row) => {
      if (row.isCash || row.holdingPeriodDays == null) return '—'
      const years = row.holdingPeriodDays / 365
      return `${years.toFixed(1)}y`
    },
  }
}

// --- Income variant columns ---

export function dividendIncomeColumn(): ColumnDef {
  return {
    key: 'dividendIncome',
    header: 'Dividends',
    align: 'center',
    sortValue: (row) => row.dividendIncome ?? 0,
    renderCell: (row) => (
      <span className={row.dividendIncome ? styles.incomePositive : ''}>
        {row.dividendIncome ? formatCurrency(row.dividendIncome) : '—'}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.dividendIncome ?? 0), 0)
      return total > 0 ? (
        <strong className={styles.incomePositive}>{formatCurrency(total)}</strong>
      ) : (
        '—'
      )
    },
  }
}

export function optionsIncomeColumn(): ColumnDef {
  return {
    key: 'optionsIncome',
    header: 'Options',
    align: 'center',
    sortValue: (row) => row.optionsIncome ?? 0,
    renderCell: (row) => (
      <span className={row.optionsIncome ? styles.incomePositive : ''}>
        {row.optionsIncome ? formatCurrency(row.optionsIncome) : '—'}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.optionsIncome ?? 0), 0)
      return total > 0 ? (
        <strong className={styles.incomePositive}>{formatCurrency(total)}</strong>
      ) : (
        '—'
      )
    },
  }
}

export function totalIncomeColumn(): ColumnDef {
  return {
    key: 'totalIncome',
    header: 'Total Income',
    align: 'center',
    sortValue: (row) => row.totalIncome ?? 0,
    renderCell: (row) => (
      <span className={row.totalIncome ? styles.incomePositive : ''}>
        {row.totalIncome ? formatCurrency(row.totalIncome) : '—'}
      </span>
    ),
    renderFooter: (rows) => {
      const total = rows.reduce((sum, r) => sum + (r.totalIncome ?? 0), 0)
      return total > 0 ? (
        <strong className={styles.incomePositive}>{formatCurrency(total)}</strong>
      ) : (
        '—'
      )
    },
  }
}

export function totalYieldColumn(): ColumnDef {
  return {
    key: 'totalYield',
    header: '% Yield',
    align: 'center',
    sortValue: (row) => {
      const val = row.isCash ? row.value : row.shares * row.currentPrice
      return row.totalIncome && val > 0 ? row.totalIncome / val : -Infinity
    },
    renderCell: (row) => {
      if (row.isCash) return '—'
      const val = row.shares * row.currentPrice
      if (row.totalIncome && val > 0) {
        return (
          <span className={styles.incomePositive}>
            {((row.totalIncome / val) * 100).toFixed(2)}%
          </span>
        )
      }
      return '—'
    },
    renderFooter: (rows) => {
      const totalIncome = rows.reduce((sum, r) => sum + (r.totalIncome ?? 0), 0)
      const totalValue = rows.reduce(
        (sum, r) => sum + (r.isCash ? r.value : r.shares * r.currentPrice),
        0
      )
      if (totalIncome > 0 && totalValue > 0) {
        return (
          <strong className={styles.incomePositive}>
            {((totalIncome / totalValue) * 100).toFixed(2)}%
          </strong>
        )
      }
      return '—'
    },
  }
}
