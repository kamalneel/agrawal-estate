import { FileText } from 'lucide-react'
import styles from './PlaceholderPage.module.css'

export function EstatePlanning() {
  return (
    <div className={styles.page}>
      <div className={styles.icon}>
        <FileText size={48} />
      </div>
      <h1>Estate Planning</h1>
      <p>Wills, trusts, beneficiaries, and important legal documents.</p>
      <span className={styles.badge}>Coming Soon</span>
    </div>
  )
}















