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
  ScrollText,
  Lightbulb,
  DollarSign,
  ChevronDown,
  ChevronRight,
  Target,
  LineChart,
  Banknote,
  PiggyBank,
  Settings,
  Bell,
  Globe,
  Brain,
  Link2,
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
  { path: '/', label: 'Notifications', icon: <Bell size={20} /> },
  { path: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
  { path: '/income', label: 'Income', icon: <Wallet size={20} /> },
  { path: '/investments', label: 'Investments', icon: <TrendingUp size={20} /> },
  { path: '/equity', label: 'Equity', icon: <DollarSign size={20} /> },
  { path: '/real-estate', label: 'Real Estate', icon: <Building2 size={20} /> },
  { path: '/cash', label: 'Cash & Banking', icon: <Receipt size={20} /> },
  { path: '/tax', label: 'Tax Center', icon: <FileText size={20} /> },
]

const strategiesGroup: NavGroup = {
  label: 'Strategies',
  icon: <Target size={20} />,
  items: [
    { path: '/strategies/tax-optimization', label: 'Tax Optimization', icon: <Lightbulb size={18} /> },
    { path: '/strategies/options-selling', label: 'Options Selling', icon: <LineChart size={18} /> },
    { path: '/strategies/buy-borrow-die', label: 'Buy/Borrow/Die', icon: <Banknote size={18} /> },
    { path: '/strategies/retirement-deductions', label: 'Retirement Deductions', icon: <PiggyBank size={18} /> },
    { path: '/strategies/management', label: 'Strategy Management', icon: <Settings size={18} /> },
    { path: '/strategies/learning', label: 'RLHF Learning', icon: <Brain size={18} /> },
  ],
}

const bottomNavItems: NavItem[] = [
  { path: '/estate-planning', label: 'Estate Planning', icon: <ScrollText size={20} /> },
  { path: '/india-investments', label: 'India Investments', icon: <Globe size={20} /> },
  { path: '/integrations/plaid', label: 'Plaid Integration', icon: <Link2 size={20} /> },
  { path: '/data-ingestion', label: 'Data Ingestion', icon: <Database size={20} /> },
]

export function Sidebar() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  
  // Check if any strategy route is active
  const isStrategyActive = strategiesGroup.items.some(item => 
    location.pathname.startsWith(item.path)
  )
  
  const [strategiesExpanded, setStrategiesExpanded] = useState(isStrategyActive)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleStrategies = () => {
    setStrategiesExpanded(!strategiesExpanded)
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>🏛️</span>
        <span className={styles.logoText}>Agrawal Estate</span>
      </div>

      <nav className={styles.nav}>
        {/* Main nav items */}
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

        {/* Strategies group */}
        <div className={styles.navGroup}>
          <button
            className={`${styles.navGroupHeader} ${isStrategyActive ? styles.active : ''}`}
            onClick={toggleStrategies}
          >
            {strategiesGroup.icon}
            <span>{strategiesGroup.label}</span>
            <span className={styles.chevron}>
              {strategiesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </span>
          </button>
          
          <div className={`${styles.navGroupItems} ${strategiesExpanded ? styles.expanded : ''}`}>
            {strategiesGroup.items.map((item) => (
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

        {/* Bottom nav items */}
        {bottomNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
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
