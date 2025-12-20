import { TrendingUp, TrendingDown, LucideIcon } from 'lucide-react'
import styles from './AssetCard.module.css'
import clsx from 'clsx'

interface AssetCardProps {
  label: string
  description: string
  value: number
  change?: number
  changePercent?: number
  icon: LucideIcon
  isLiability?: boolean
  delay?: number
}

export function AssetCard({
  label,
  description,
  value,
  change,
  changePercent,
  icon: Icon,
  isLiability = false,
  delay = 0,
}: AssetCardProps) {
  const formatCurrency = (val: number | undefined) => {
    if (val === undefined || val === null || isNaN(val)) return '$0'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(val)
  }

  const formatPercent = (val: number | undefined) => {
    if (val === undefined || val === null || isNaN(val)) return '+0.00%'
    const sign = val >= 0 ? '+' : ''
    return `${sign}${val.toFixed(2)}%`
  }

  // For liabilities, negative change (paying down debt) is positive
  const hasChange = change !== undefined && change !== 0
  const isPositiveChange = isLiability ? (change || 0) < 0 : (change || 0) >= 0

  return (
    <div
      className={clsx(styles.card, isLiability && styles.liability)}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={styles.header}>
        <div className={clsx(styles.iconWrapper, isLiability && styles.liabilityIcon)}>
          <Icon size={24} />
        </div>
        <div className={styles.info}>
          <h3 className={styles.label}>{label}</h3>
          <p className={styles.description}>{description}</p>
        </div>
      </div>

      <div className={styles.valueSection}>
        <div className={clsx(styles.value, isLiability && styles.liabilityValue)}>
          {isLiability && '-'}{formatCurrency(value)}
        </div>
        {hasChange && (
          <div className={clsx(
            styles.change,
            isPositiveChange ? styles.positive : styles.negative
          )}>
            {isPositiveChange ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
            <span>{formatCurrency(Math.abs(change || 0))}</span>
            <span className={styles.changePercent}>{formatPercent(changePercent)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
