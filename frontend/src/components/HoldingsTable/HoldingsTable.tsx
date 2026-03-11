import { useState } from 'react'
import type { HoldingsTableProps, TableContext } from './types'
import styles from './HoldingsTable.module.css'

type SortDir = 'asc' | 'desc' | null

export function HoldingsTable({
  rows,
  columns,
  defaultSortKey = 'value',
  defaultSortDir = 'desc',
  className,
  showFooter = true,
}: HoldingsTableProps) {
  const [sortKey, setSortKey] = useState<string>(defaultSortKey)
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir)

  const handleSort = (key: string) => {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir(key === 'symbol' ? 'asc' : 'desc')
    } else {
      // 3-state toggle: desc -> asc -> null
      setSortDir((d) => (d === 'desc' ? 'asc' : d === 'asc' ? null : 'desc'))
    }
  }

  const sortIndicator = (key: string) => {
    if (sortKey !== key || sortDir === null)
      return <span className={styles.sortIcon} style={{ opacity: 0.3 }}>⇅</span>
    return <span className={styles.sortIcon}>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  // Separate stock holdings from CASH row
  const stockRows = rows.filter((r) => !r.isCash)
  const cashRows = rows.filter((r) => r.isCash)

  // Compute context
  const totalPortfolioValue =
    stockRows.reduce((sum, r) => sum + r.shares * r.currentPrice, 0) +
    cashRows.reduce((sum, r) => sum + r.value, 0)

  const ctx: TableContext = { totalPortfolioValue, rows }

  // Sort stock rows
  const activeCol = columns.find((c) => c.key === sortKey)
  const sortedStockRows =
    sortDir === null || !activeCol
      ? stockRows
      : [...stockRows].sort((a, b) => {
          const va = activeCol.sortValue(a, ctx)
          const vb = activeCol.sortValue(b, ctx)
          const cmp =
            typeof va === 'string'
              ? va.localeCompare(vb as string)
              : (va as number) - (vb as number)
          return sortDir === 'asc' ? cmp : -cmp
        })

  const allRows = [...sortedStockRows, ...cashRows]

  return (
    <div className={`${styles.tableContainer} ${className || ''}`}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={styles.sortableHeader}
                style={{ textAlign: col.align || 'center' }}
                onClick={() => handleSort(col.key)}
              >
                {col.header} {sortIndicator(col.key)}
                {col.headerSub && (
                  <span className={styles.headerSub}>{col.headerSub}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedStockRows.map((row) => (
            <tr
              key={row.symbol}
              className={`${styles.tableRow} ${
                row.utilizationStatus === 'none' ? styles.unsoldRow : ''
              }`}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ textAlign: col.align || 'center' }}
                >
                  {col.renderCell(row, ctx)}
                </td>
              ))}
            </tr>
          ))}
          {cashRows.map((row) => (
            <tr key={row.symbol} className={`${styles.tableRow} ${styles.cashRow}`}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ textAlign: col.align || 'center' }}
                >
                  {col.hideForCash ? '—' : col.renderCell(row, ctx)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {showFooter && (
          <tfoot>
            <tr className={styles.totalsRow}>
              {columns.map((col, i) => (
                <td
                  key={col.key}
                  style={{ textAlign: col.align || 'center' }}
                >
                  {i === 0 ? (
                    <span className={styles.totalLabel}>TOTAL</span>
                  ) : col.renderFooter ? (
                    col.renderFooter(allRows, ctx)
                  ) : null}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}
