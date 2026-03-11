import { useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Wallet,
  TrendingUp,
  Building2,
  Receipt,
  FileText,
  Database,
  LogOut,
  Lightbulb,
  DollarSign,
  ChevronDown,
  ChevronRight,
  LineChart,
  Banknote,
  PiggyBank,
  Settings,
  Bell,
  Globe,
  Link2,
  CreditCard,
  Layers,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import styles from './Sidebar.module.css'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
}

interface NavGroup {
  label: string
  icon: React.ReactNode
  items: NavItem[]
}

const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
  { path: '/income', label: 'Income', icon: <Wallet size={20} /> },
  { path: '/strategies/options-selling', label: 'Option Income', icon: <LineChart size={20} /> },
  { path: '/investments', label: 'Investments', icon: <TrendingUp size={20} /> },
  { path: '/strategies/spending', label: 'Spending', icon: <CreditCard size={20} /> },
  { path: '/strategies/buy-borrow-die', label: 'Buy/Borrow/Die', icon: <Banknote size={20} /> },
  { path: '/', label: 'Notifications', icon: <Bell size={20} /> },
  { path: '/data-ingestion', label: 'Import Data', icon: <Database size={20} /> },
]

const moreGroup: NavGroup = {
  label: 'More',
  icon: <Layers size={20} />,
  items: [
    { path: '/equity', label: 'Private Equity', icon: <DollarSign size={18} /> },
    { path: '/real-estate', label: 'Real Estate', icon: <Building2 size={18} /> },
    { path: '/cash', label: 'Cash', icon: <Receipt size={18} /> },
    { path: '/india-investments', label: 'India Holdings', icon: <Globe size={18} /> },
    { path: '/airbnb', label: 'Airbnb', icon: <Building2 size={18} /> },
    { path: '/tax', label: 'Tax Center', icon: <FileText size={18} /> },
    { path: '/strategies/retirement-deductions', label: 'Retirement', icon: <PiggyBank size={18} /> },
    { path: '/strategies/tax-optimization', label: 'Tax Planning', icon: <Lightbulb size={18} /> },
    { path: '/strategies/management', label: 'Strategy Settings', icon: <Settings size={18} /> },
    { path: '/integrations/plaid', label: 'Bank Connections', icon: <Link2 size={18} /> },
  ],
}

export function Sidebar() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // Check if any "More" route is active
  const isMoreActive = moreGroup.items.some(item =>
    location.pathname === item.path || location.pathname.startsWith(item.path + '/')
  )

  const [moreExpanded, setMoreExpanded] = useState(isMoreActive)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleMore = () => {
    setMoreExpanded(!moreExpanded)
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>🏛️</span>
        <span className={styles.logoText}>Agrawal Estate</span>
      </div>

      <nav className={styles.nav}>
        {/* Top-level nav items */}
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
            end={item.path === '/'}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}

        {/* More group */}
        <div className={`${styles.navGroup} ${styles.moreGroup}`}>
          <button
            className={`${styles.navGroupHeader} ${isMoreActive ? styles.active : ''}`}
            onClick={toggleMore}
          >
            {moreGroup.icon}
            <span>{moreGroup.label}</span>
            <span className={styles.chevron}>
              {moreExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </span>
          </button>

          <div className={`${styles.navGroupItems} ${moreExpanded ? styles.expanded : ''}`}>
            {moreGroup.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `${styles.navItem} ${styles.subItem} ${isActive ? styles.active : ''}`
                }
              >
                {item.icon}
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      <div className={styles.footer}>
        <button className={styles.logoutButton} onClick={handleLogout}>
          <LogOut size={20} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  )
}
