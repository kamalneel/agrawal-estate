import { useState, useEffect, useMemo } from 'react';
import {
  LineChart,
  TrendingUp,
  DollarSign,
  Settings,
  RefreshCw,
  AlertTriangle,
  Wallet,
  PieChart,
  BarChart3,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  CheckCircle,
  XCircle,
  Clock,
  Bell,
  Timer,
  Zap,
  Play,
  Eye,
  Plus,
  Target,
  TrendingDown,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart as RechartsPie,
  Pie,
} from 'recharts';
import styles from './OptionsSelling.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface Holding {
  symbol: string;
  description: string;
  shares: number;
  price: number;
  value: number;
  options: number;
  premium_per_contract?: number;
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  sold_contracts?: number;
  unsold_contracts?: number;
  utilization_status?: 'none' | 'partial' | 'full';
}

interface Account {
  account_id: string;
  account_name: string;
  account_type: string;
  holdings: Holding[];
  total_value: number;
  total_shares: number;
  total_options: number;
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  unsold_options?: number;
  sold_options_snapshot?: {
    id: number;
    source: string;
    account_name: string;
    snapshot_date: string;
  };
}

interface SymbolSummary {
  symbol: string;
  description: string;
  shares: number;
  price: number;
  value: number;
  options: number;
  premium_per_contract: number;
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  account_count: number;
  accounts: string[];
  sold_contracts?: number;
  unsold_contracts?: number;
  utilization_status?: 'none' | 'partial' | 'full';
}

interface PortfolioSummary {
  total_value: number;
  total_options: number;
  total_sold?: number;
  total_unsold?: number;
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  weekly_yield_percent: number;
  yearly_yield_percent: number;
}

interface SoldOptionsSnapshot {
  id: number;
  source: string;
  account_name?: string;
  snapshot_date: string;
  created_at: string;
}

interface OptionsData {
  params: {
    default_premium: number;
    symbol_premiums: Record<string, number>;
    delta: number;
    weeks_per_year: number;
  };
  portfolio_summary: PortfolioSummary;
  sold_options_snapshot?: SoldOptionsSnapshot | null;
  symbols: SymbolSummary[];
  accounts: Account[];
}

// Roll Monitor interfaces
interface RollAlert {
  symbol: string;
  strike_price: number;
  option_type: string;
  expiration_date: string;
  contracts: number;
  original_premium: number;
  current_premium: number;
  profit_amount: number;
  profit_percent: number;
  days_to_expiry: number;
  urgency: 'low' | 'medium' | 'high';
  recommendation: string;
  position_id?: number;
}

interface RollCheckResponse {
  success: boolean;
  positions_checked: number;
  alerts_count: number;
  new_alerts_saved: number;
  profit_threshold: string;
  alerts: RollAlert[];
  message: string;
}

interface MonitoredPosition {
  id: number;
  symbol: string;
  strike_price: number;
  option_type: string;
  expiration_date: string;
  contracts: number;
  original_premium: number | null;
  premium_source?: string;
  current_premium?: number;
  gain_loss_percent?: number;
  status: string;
  account?: string;
  days_to_expiry?: number;
  can_monitor: boolean;
  data_source?: 'live' | 'stored';
  snapshot_date?: string;
}

interface HistoricalAlert {
  id: number;
  symbol: string;
  strike_price: number;
  option_type: string;
  expiration_date: string;
  contracts: number;
  original_premium: number;
  current_premium: number;
  profit_percent: number;
  alert_type: string;
  alert_triggered_at: string;
  acknowledged: boolean;
  action_taken?: string;
}

type SortDirection = 'asc' | 'desc' | null;
type SortField = 'symbol' | 'shares' | 'price' | 'value' | 'options' | 'weekly' | 'monthly' | 'yearly';

const COLORS = ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EF4444', '#EC4899'];

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
};

// Helper function to format timestamps with relative time
const formatTimestamp = (date: Date | null): string => {
  if (!date) return 'Unknown';
  
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  
  // For older dates, show full date and time
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
};

export default function OptionsSelling() {
  const [data, setData] = useState<OptionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('overview');
  
  // Settings
  const [defaultPremium, setDefaultPremium] = useState(60);
  const [symbolPremiums, setSymbolPremiums] = useState<Record<string, number>>({});
  const [delta, setDelta] = useState(10);
  const [weeksPerYear, setWeeksPerYear] = useState(50);

  // Sorting state for overview
  const [overviewSort, setOverviewSort] = useState<{ field: SortField; direction: SortDirection }>({
    field: 'options',
    direction: 'desc'
  });

  // Sorting state for each account
  const [accountSorts, setAccountSorts] = useState<Record<string, { field: SortField; direction: SortDirection }>>({});

  // Roll Monitor state
  const [rollAlerts, setRollAlerts] = useState<RollAlert[]>([]);
  const [monitoredPositions, setMonitoredPositions] = useState<MonitoredPosition[]>([]);
  const [historicalAlerts, setHistoricalAlerts] = useState<HistoricalAlert[]>([]);
  const [rollCheckLoading, setRollCheckLoading] = useState(false);
  const [rollCheckMessage, setRollCheckMessage] = useState<string | null>(null);
  const [profitThreshold, setProfitThreshold] = useState(80);
  const [lastCheckTime, setLastCheckTime] = useState<Date | null>(null);
  
  
  // Monitored positions sorting state
  type MonitorSortField = 'symbol' | 'strike_price' | 'expiration_date' | 'days_to_expiry' | 'contracts' | 'original_premium' | 'current_premium' | 'gain_loss_percent' | 'account';
  const [monitorSort, setMonitorSort] = useState<{ field: MonitorSortField; direction: 'asc' | 'desc' }>({
    field: 'expiration_date',
    direction: 'asc'
  });
  
  // Add position form
  const [showAddPosition, setShowAddPosition] = useState(false);
  const [newPosition, setNewPosition] = useState({
    symbol: '',
    strike_price: '',
    option_type: 'call',
    expiration_date: '',
    contracts: '1',
    original_premium: '',
    account_name: ''
  });

  // Sorted monitored positions
  const sortedMonitoredPositions = useMemo(() => {
    const sorted = [...monitoredPositions];
    sorted.sort((a, b) => {
      let aVal: string | number | null = null;
      let bVal: string | number | null = null;
      
      switch (monitorSort.field) {
        case 'symbol':
          aVal = a.symbol;
          bVal = b.symbol;
          break;
        case 'strike_price':
          aVal = a.strike_price;
          bVal = b.strike_price;
          break;
        case 'expiration_date':
          aVal = a.expiration_date || '';
          bVal = b.expiration_date || '';
          break;
        case 'days_to_expiry':
          aVal = a.days_to_expiry ?? 999;
          bVal = b.days_to_expiry ?? 999;
          break;
        case 'contracts':
          aVal = a.contracts;
          bVal = b.contracts;
          break;
        case 'original_premium':
          aVal = a.original_premium ?? 0;
          bVal = b.original_premium ?? 0;
          break;
        case 'current_premium':
          aVal = a.current_premium ?? 0;
          bVal = b.current_premium ?? 0;
          break;
        case 'gain_loss_percent':
          aVal = a.gain_loss_percent ?? -999;
          bVal = b.gain_loss_percent ?? -999;
          break;
        case 'account':
          aVal = a.account || '';
          bVal = b.account || '';
          break;
      }
      
      if (aVal === null || bVal === null) return 0;
      
      let comparison = 0;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        comparison = aVal.localeCompare(bVal);
      } else {
        comparison = (aVal as number) - (bVal as number);
      }
      
      return monitorSort.direction === 'asc' ? comparison : -comparison;
    });
    return sorted;
  }, [monitoredPositions, monitorSort]);

  const handleMonitorSort = (field: MonitorSortField) => {
    setMonitorSort(prev => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  // Initialize symbol premiums from API data (which includes database values)
  // The income projection endpoint already returns the correct database values
  useEffect(() => {
    if (data?.params?.symbol_premiums) {
      console.log('Loading premium settings from API response:', data.params.symbol_premiums);
      setSymbolPremiums(data.params.symbol_premiums);
    }
  }, [data?.params?.symbol_premiums]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async (customPremiums?: Record<string, number>) => {
    setLoading(true);
    setError(null);
    try {
      // Use the enhanced endpoint that includes sold/unsold status
      // Add cache-busting timestamp to ensure fresh data after data ingestion
      const response = await fetch('/api/v1/strategies/options-selling/income-projection-with-status', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify({
          default_premium: defaultPremium,
          symbol_premiums: customPremiums || symbolPremiums,
          delta: delta,
          weeks_per_year: weeksPerYear,
          _timestamp: Date.now(), // Cache-busting parameter
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      setData(result);
      
      // Update symbol premiums from API response (which includes database values)
      // This ensures we have the latest values after the API call
      if (result.params?.symbol_premiums) {
        setSymbolPremiums(prev => {
          // Merge: API response values (from database) override any stale values
          return { ...prev, ...result.params.symbol_premiums };
        });
      }
    } catch (err) {
      console.error('Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const applySettings = () => {
    fetchData(symbolPremiums);
  };

  // Roll Monitor functions
  const checkRollOpportunities = async () => {
    setRollCheckLoading(true);
    setRollCheckMessage(null);
    try {
      const response = await fetch(
        `/api/v1/strategies/option-monitor/check?profit_threshold=${profitThreshold / 100}`,
        { headers: getAuthHeaders() }
      );
      const result: RollCheckResponse = await response.json();
      
      if (result.success) {
        setRollAlerts(result.alerts);
        setRollCheckMessage(result.message);
        setLastCheckTime(new Date());
        // Refresh positions after check (use stored data to avoid extra API calls)
        fetchMonitoredPositions(false);
      }
    } catch (err) {
      console.error('Roll check error:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to check roll opportunities';
      setRollCheckMessage(`Error: ${errorMessage}`);
      setRollAlerts([]);
    } finally {
      setRollCheckLoading(false);
    }
  };

  const [positionsLoading, setPositionsLoading] = useState(false);
  const [priceUpdateTime, setPriceUpdateTime] = useState<Date | null>(null);
  const [usingLivePrices, setUsingLivePrices] = useState(false);

  const fetchMonitoredPositions = async (useLivePrices: boolean = false) => {
    setPositionsLoading(true);
    try {
      const response = await fetch(
        `/api/v1/strategies/option-monitor/positions?status=open&use_live_prices=${useLivePrices}`,
        { headers: getAuthHeaders() }
      );
      const result = await response.json();
      setMonitoredPositions(result.positions || []);
      if (result.price_update_time) {
        setPriceUpdateTime(new Date(result.price_update_time));
      }
      setUsingLivePrices(result.using_live_prices || false);
    } catch (err) {
      console.error('Error fetching positions:', err);
    } finally {
      setPositionsLoading(false);
    }
  };

  const fetchHistoricalAlerts = async () => {
    try {
      const response = await fetch('/api/v1/strategies/option-monitor/alerts?limit=20', {
        headers: getAuthHeaders()
      });
      const result = await response.json();
      setHistoricalAlerts(result.alerts || []);
    } catch (err) {
      console.error('Error fetching alerts:', err);
    }
  };


  const acknowledgeAlert = async (alertId: number, action: string) => {
    try {
      await fetch(
        `/api/v1/strategies/option-monitor/alerts/${alertId}/acknowledge?action_taken=${action}`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      fetchHistoricalAlerts();
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  };

  const addMonitoredPosition = async () => {
    try {
      const response = await fetch('/api/v1/strategies/option-monitor/positions', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: newPosition.symbol.toUpperCase(),
          strike_price: parseFloat(newPosition.strike_price),
          option_type: newPosition.option_type,
          expiration_date: newPosition.expiration_date,
          contracts: parseInt(newPosition.contracts),
          original_premium: parseFloat(newPosition.original_premium),
          account_name: newPosition.account_name || null
        })
      });
      
      if (response.ok) {
        setShowAddPosition(false);
        setNewPosition({
          symbol: '', strike_price: '', option_type: 'call',
          expiration_date: '', contracts: '1', original_premium: '', account_name: ''
        });
        fetchMonitoredPositions();
      }
    } catch (err) {
      console.error('Error adding position:', err);
    }
  };

  // Fetch data when tab is activated
  useEffect(() => {
    if (activeTab === 'roll-monitor') {
      fetchMonitoredPositions(false);
      fetchHistoricalAlerts();
    }
  }, [activeTab]);

  const updateSymbolPremium = (symbol: string, value: number) => {
    setSymbolPremiums(prev => ({
      ...prev,
      [symbol]: value
    }));
  };

  // Calculate income based on current symbol premiums (real-time preview)
  const getSymbolIncome = (symbol: SymbolSummary) => {
    const premium = symbolPremiums[symbol.symbol] ?? symbol.premium_per_contract;
    const weekly = symbol.options * premium;
    const monthly = weekly * 4;
    const yearly = weekly * weeksPerYear;
    return { premium, weekly, monthly, yearly };
  };

  const getHoldingIncome = (holding: Holding) => {
    const premium = symbolPremiums[holding.symbol] ?? holding.premium_per_contract ?? 60;
    const weekly = holding.options * premium;
    const monthly = weekly * 4;
    const yearly = weekly * weeksPerYear;
    return { premium, weekly, monthly, yearly };
  };

  // Calculate portfolio totals with current premiums
  const portfolioTotals = useMemo(() => {
    if (!data) return null;
    
    let totalWeekly = 0;
    data.symbols.forEach(sym => {
      const { weekly } = getSymbolIncome(sym);
      totalWeekly += weekly;
    });
    
    const totalMonthly = totalWeekly * 4;
    const totalYearly = totalWeekly * weeksPerYear;
    const weeklyYield = data.portfolio_summary.total_value > 0 
      ? (totalWeekly / data.portfolio_summary.total_value) * 100 
      : 0;
    const yearlyYield = data.portfolio_summary.total_value > 0 
      ? (totalYearly / data.portfolio_summary.total_value) * 100 
      : 0;

    return {
      total_value: data.portfolio_summary.total_value,
      total_options: data.portfolio_summary.total_options,
      weekly_income: totalWeekly,
      monthly_income: totalMonthly,
      yearly_income: totalYearly,
      weekly_yield_percent: weeklyYield,
      yearly_yield_percent: yearlyYield,
    };
  }, [data, symbolPremiums, weeksPerYear]);

  // Calculate account totals with current premiums
  const getAccountTotals = (account: Account) => {
    let totalWeekly = 0;
    account.holdings.forEach(holding => {
      const { weekly } = getHoldingIncome(holding);
      totalWeekly += weekly;
    });
    return {
      weekly: totalWeekly,
      monthly: totalWeekly * 4,
      yearly: totalWeekly * weeksPerYear,
    };
  };

  // Sorting functions
  const handleOverviewSort = (field: SortField) => {
    setOverviewSort(prev => ({
      field,
      direction: prev.field === field 
        ? prev.direction === 'asc' ? 'desc' : prev.direction === 'desc' ? null : 'asc'
        : 'desc'
    }));
  };

  const handleAccountSort = (accountId: string, field: SortField) => {
    setAccountSorts(prev => ({
      ...prev,
      [accountId]: {
        field,
        direction: prev[accountId]?.field === field 
          ? prev[accountId]?.direction === 'asc' ? 'desc' : prev[accountId]?.direction === 'desc' ? null : 'asc'
          : 'desc'
      }
    }));
  };

  const getSortIcon = (field: SortField, currentSort: { field: SortField; direction: SortDirection }) => {
    if (currentSort.field !== field || currentSort.direction === null) {
      return <ArrowUpDown size={14} className={styles.sortIconInactive} />;
    }
    return currentSort.direction === 'asc' 
      ? <ArrowUp size={14} className={styles.sortIconActive} />
      : <ArrowDown size={14} className={styles.sortIconActive} />;
  };

  // Sort symbols for overview
  const sortedSymbols = useMemo(() => {
    if (!data) return [];
    
    const symbolsWithCalc = data.symbols.map(sym => ({
      ...sym,
      ...getSymbolIncome(sym)
    }));

    if (overviewSort.direction === null) return symbolsWithCalc;

    return [...symbolsWithCalc].sort((a, b) => {
      let aVal: number | string, bVal: number | string;
      switch (overviewSort.field) {
        case 'symbol': aVal = a.symbol; bVal = b.symbol; break;
        case 'shares': aVal = a.shares; bVal = b.shares; break;
        case 'price': aVal = a.price; bVal = b.price; break;
        case 'value': aVal = a.value; bVal = b.value; break;
        case 'options': aVal = a.options; bVal = b.options; break;
        case 'weekly': aVal = a.weekly; bVal = b.weekly; break;
        case 'monthly': aVal = a.monthly; bVal = b.monthly; break;
        case 'yearly': aVal = a.yearly; bVal = b.yearly; break;
        default: return 0;
      }
      if (typeof aVal === 'string') {
        return overviewSort.direction === 'asc' 
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return overviewSort.direction === 'asc' ? aVal - (bVal as number) : (bVal as number) - aVal;
    });
  }, [data, symbolPremiums, overviewSort, weeksPerYear]);

  // Sort holdings for accounts
  const getSortedHoldings = (account: Account) => {
    const sort = accountSorts[account.account_id] || { field: 'options', direction: 'desc' };
    
    const holdingsWithCalc = account.holdings.map(h => ({
      ...h,
      ...getHoldingIncome(h)
    }));

    if (sort.direction === null) return holdingsWithCalc;

    return [...holdingsWithCalc].sort((a, b) => {
      let aVal: number | string, bVal: number | string;
      switch (sort.field) {
        case 'symbol': aVal = a.symbol; bVal = b.symbol; break;
        case 'shares': aVal = a.shares; bVal = b.shares; break;
        case 'price': aVal = a.price; bVal = b.price; break;
        case 'value': aVal = a.value; bVal = b.value; break;
        case 'options': aVal = a.options; bVal = b.options; break;
        case 'weekly': aVal = a.weekly; bVal = b.weekly; break;
        case 'monthly': aVal = a.monthly; bVal = b.monthly; break;
        case 'yearly': aVal = a.yearly; bVal = b.yearly; break;
        default: return 0;
      }
      if (typeof aVal === 'string') {
        return sort.direction === 'asc' 
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return sort.direction === 'asc' ? aVal - (bVal as number) : (bVal as number) - aVal;
    });
  };

  // Sort accounts in desired order: Neel's Inv -> Neel's IRA -> Jaya's Inv -> Jaya's IRA
  const sortedAccounts = useMemo(() => {
    if (!data) return [];
    
    const getAccountOrder = (account: Account) => {
      const name = account.account_name.toLowerCase();
      const isNeel = name.includes('neel');
      const isJaya = name.includes('jaya');
      const isBrokerage = account.account_type === 'brokerage';
      const isRetirement = ['retirement', 'ira', 'roth_ira'].includes(account.account_type);
      
      // Order: Neel Brokerage (0), Neel IRA (1), Jaya Brokerage (2), Jaya IRA (3), Others (4+)
      if (isNeel && isBrokerage) return 0;
      if (isNeel && isRetirement) return 1;
      if (isJaya && isBrokerage) return 2;
      if (isJaya && isRetirement) return 3;
      return 4; // Other accounts
    };
    
    return [...data.accounts].sort((a, b) => getAccountOrder(a) - getAccountOrder(b));
  }, [data]);

  // Chart data using calculated values
  const symbolChartData = sortedSymbols.slice(0, 6).map((sym, idx) => ({
    name: sym.symbol,
    weekly: sym.weekly,
    options: sym.options,
    fill: COLORS[idx % COLORS.length],
  }));

  const pieData = sortedSymbols.slice(0, 6).map((sym, idx) => ({
    name: sym.symbol,
    value: sym.yearly,
    fill: COLORS[idx % COLORS.length],
  }));

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <LineChart size={32} />
          </div>
          <div>
            <h1 className={styles.title}>Options Selling Strategy</h1>
            <p className={styles.subtitle}>
              Weekly income from selling covered calls using Delta {delta} strategy
            </p>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'overview' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <BarChart3 size={16} />
          <span>Overview</span>
        </button>
        {sortedAccounts.map((account) => {
          const accountName = account.account_name.split("'s ")[0];
          const accountType = account.account_type === 'retirement' ? 'IRA' : 
                             account.account_type === 'ira' ? 'IRA' :
                             account.account_type === 'roth_ira' ? 'Roth' :
                             'Inv';
          const shortLabel = `${accountName}'s ${accountType}`;
          
          return (
            <button
              key={account.account_id}
              className={`${styles.tab} ${activeTab === account.account_id ? styles.activeTab : ''}`}
              onClick={() => setActiveTab(account.account_id)}
            >
              <span>{shortLabel}</span>
              {account.unsold_options !== undefined && account.unsold_options > 0 && (
                <span className={styles.unsoldBadge}>{account.unsold_options}</span>
              )}
            </button>
          );
        })}
        <button
          className={`${styles.tab} ${activeTab === 'roll-monitor' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('roll-monitor')}
        >
          <Timer size={16} />
          <span>Monitor</span>
          {rollAlerts.length > 0 && (
            <span className={styles.alertBadge}>{rollAlerts.length}</span>
          )}
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'settings' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings size={16} />
          <span>Settings</span>
        </button>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {loading && (
          <div className={styles.loadingState}>
            <RefreshCw size={32} className={styles.spinner} />
            <p>Calculating options income...</p>
          </div>
        )}

        {error && (
          <div className={styles.errorState}>
            <AlertTriangle size={32} />
            <p>{error}</p>
            <button onClick={() => fetchData()}>Retry</button>
          </div>
        )}

        {!loading && !error && data && portfolioTotals && activeTab === 'overview' && (
          <>
            {/* Summary Cards */}
            <div className={styles.summaryGrid}>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Total Options Pool</span>
                <span className={styles.summaryValue}>{portfolioTotals.total_options}</span>
                <span className={styles.summaryNote}>
                  <span className={styles.soldNote}>
                    <CheckCircle size={12} /> {data.portfolio_summary.total_sold ?? 0} sold
                  </span>
                  {' · '}
                  <span className={styles.unsoldNote}>
                    <XCircle size={12} /> {data.portfolio_summary.total_unsold ?? 0} unsold
                  </span>
                </span>
              </div>
              <div className={`${styles.summaryCard} ${styles.highlight}`}>
                <span className={styles.summaryLabel}>Weekly Income</span>
                <span className={styles.summaryValue}>{formatCurrency(portfolioTotals.weekly_income)}</span>
                <span className={styles.summaryNote}>{portfolioTotals.weekly_yield_percent.toFixed(3)}% yield</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Monthly Income</span>
                <span className={styles.summaryValue}>{formatCurrency(portfolioTotals.monthly_income)}</span>
                <span className={styles.summaryNote}>4 weeks</span>
              </div>
              <div className={`${styles.summaryCard} ${styles.success}`}>
                <span className={styles.summaryLabel}>Yearly Income</span>
                <span className={styles.summaryValue}>{formatCurrency(portfolioTotals.yearly_income)}</span>
                <span className={styles.summaryNote}>{portfolioTotals.yearly_yield_percent.toFixed(1)}% yield</span>
              </div>
            </div>

            {/* Strategy Info */}
            <div className={styles.strategyInfo}>
              <div className={styles.strategyDetail}>
                <DollarSign size={20} />
                <div>
                  <span className={styles.strategyLabel}>Premium (per symbol)</span>
                  <span className={styles.strategyValue}>Customized in Settings</span>
                </div>
              </div>
              <div className={styles.strategyDetail}>
                <TrendingUp size={20} />
                <div>
                  <span className={styles.strategyLabel}>Delta Strategy</span>
                  <span className={styles.strategyValue}>Delta {delta} (~{100 - delta}% win rate)</span>
                </div>
              </div>
              <div className={styles.strategyDetail}>
                <Wallet size={20} />
                <div>
                  <span className={styles.strategyLabel}>Portfolio Value</span>
                  <span className={styles.strategyValue}>{formatCurrency(portfolioTotals.total_value)}</span>
                </div>
              </div>
            </div>

            {/* Charts */}
            <div className={styles.chartsGrid}>
              {/* Weekly Income by Symbol */}
              <div className={styles.chartCard}>
                <h3 className={styles.chartTitle}>
                  <BarChart3 size={20} />
                  Weekly Income by Symbol
                </h3>
                <div className={styles.chartContainer}>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={symbolChartData} layout="vertical" margin={{ left: 60 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis type="number" tickFormatter={(v) => `$${v.toLocaleString()}`} stroke="#888" />
                      <YAxis type="category" dataKey="name" stroke="#888" tick={{ fontSize: 12 }} />
                      <Tooltip 
                        formatter={(value: number) => [formatCurrency(value), 'Weekly Income']}
                        contentStyle={{ background: '#1a1a2e', border: '1px solid #333' }}
                      />
                      <Bar dataKey="weekly" radius={[0, 4, 4, 0]}>
                        {symbolChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Yearly Income Distribution */}
              <div className={styles.chartCard}>
                <h3 className={styles.chartTitle}>
                  <PieChart size={20} />
                  Yearly Income by Symbol
                </h3>
                <div className={styles.chartContainer}>
                  <ResponsiveContainer width="100%" height={300}>
                    <RechartsPie>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={2}
                        dataKey="value"
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        labelLine={false}
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip 
                        formatter={(value: number) => formatCurrency(value)}
                        contentStyle={{ background: '#1a1a2e', border: '1px solid #333' }}
                      />
                    </RechartsPie>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Symbol Breakdown Table */}
            <div className={styles.tableCard}>
              <h3 className={styles.tableTitle}>Options by Stock Symbol</h3>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('symbol')}>
                      Symbol {getSortIcon('symbol', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('shares')}>
                      Shares {getSortIcon('shares', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('price')}>
                      Price {getSortIcon('price', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('value')}>
                      Value {getSortIcon('value', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('options')}>
                      Options {getSortIcon('options', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('weekly')}>
                      Weekly {getSortIcon('weekly', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('monthly')}>
                      Monthly {getSortIcon('monthly', overviewSort)}
                    </th>
                    <th className={styles.sortableHeader} onClick={() => handleOverviewSort('yearly')}>
                      Yearly {getSortIcon('yearly', overviewSort)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSymbols.map((symbol) => (
                    <tr key={symbol.symbol} className={symbol.utilization_status === 'none' ? styles.unsoldRow : ''}>
                      <td>
                        <div className={styles.symbolCell}>
                          <strong>{symbol.symbol}</strong>
                          <span className={styles.accountCount}>{symbol.account_count} account{symbol.account_count > 1 ? 's' : ''}</span>
                        </div>
                      </td>
                      <td>{symbol.shares.toLocaleString()}</td>
                      <td>{formatCurrency(symbol.price)}</td>
                      <td>{formatCurrency(symbol.value)}</td>
                      <td>
                        <div className={styles.optionsCell}>
                          <span className={`${styles.optionsBadge} ${
                            symbol.utilization_status === 'full' ? styles.optionsFull :
                            symbol.utilization_status === 'partial' ? styles.optionsPartial :
                            styles.optionsNone
                          }`}>
                            {symbol.options}
                          </span>
                          {symbol.sold_contracts !== undefined && symbol.unsold_contracts !== undefined && (
                            <div className={styles.soldUnsoldInfo}>
                              {symbol.sold_contracts > 0 && (
                                <span className={styles.soldCount} title="Sold">
                                  <CheckCircle size={12} /> {symbol.sold_contracts}
                                </span>
                              )}
                              {symbol.unsold_contracts > 0 && (
                                <span className={styles.unsoldCount} title="Unsold">
                                  <XCircle size={12} /> {symbol.unsold_contracts}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className={styles.incomeCell}>{formatCurrency(symbol.weekly)}</td>
                      <td className={styles.incomeCell}>{formatCurrency(symbol.monthly)}</td>
                      <td className={styles.incomeCell}>{formatCurrency(symbol.yearly)}</td>
                    </tr>
                  ))}
                  <tr className={styles.totalRow}>
                    <td><strong>TOTAL</strong></td>
                    <td></td>
                    <td></td>
                    <td><strong>{formatCurrency(portfolioTotals.total_value)}</strong></td>
                    <td><strong>{portfolioTotals.total_options}</strong></td>
                    <td><strong>{formatCurrency(portfolioTotals.weekly_income)}</strong></td>
                    <td><strong>{formatCurrency(portfolioTotals.monthly_income)}</strong></td>
                    <td><strong>{formatCurrency(portfolioTotals.yearly_income)}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Individual Account Views */}
        {!loading && !error && data && sortedAccounts.map((account) => {
          const accountSort = accountSorts[account.account_id] || { field: 'options', direction: 'desc' };
          const sortedHoldings = getSortedHoldings(account);
          const accountTotals = getAccountTotals(account);
          
          return activeTab === account.account_id && (
            <div key={account.account_id} className={styles.accountView}>
              <div className={styles.accountHeader}>
                <h2>{account.account_name}</h2>
                <span className={styles.accountType}>{account.account_type}</span>
              </div>

              {/* Account Summary */}
              <div className={styles.accountSummary}>
                <div className={styles.accountStat}>
                  <span className={styles.statLabel}>Total Value</span>
                  <span className={styles.statValue}>{formatCurrency(account.total_value)}</span>
                </div>
                <div className={styles.accountStat}>
                  <span className={styles.statLabel}>Options Available</span>
                  <span className={styles.statValue}>{account.total_options}</span>
                </div>
                <div className={`${styles.accountStat} ${styles.highlight}`}>
                  <span className={styles.statLabel}>Weekly Income</span>
                  <span className={styles.statValue}>{formatCurrency(accountTotals.weekly)}</span>
                </div>
                <div className={styles.accountStat}>
                  <span className={styles.statLabel}>Monthly Income</span>
                  <span className={styles.statValue}>{formatCurrency(accountTotals.monthly)}</span>
                </div>
                <div className={`${styles.accountStat} ${styles.success}`}>
                  <span className={styles.statLabel}>Yearly Income</span>
                  <span className={styles.statValue}>{formatCurrency(accountTotals.yearly)}</span>
                </div>
              </div>

              {/* Sold Options Data Info */}
              {account.sold_options_snapshot && (
                <div className={styles.snapshotInfo}>
                  <Clock size={14} />
                  <span>
                    Options data from: {new Date(account.sold_options_snapshot.snapshot_date + 'Z').toLocaleString('en-US', { 
                      timeZone: 'America/Los_Angeles',
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                      hour12: true
                    })} PT
                  </span>
                </div>
              )}

              {/* Unsold Options Alert for This Account */}
              {account.unsold_options !== undefined && account.unsold_options > 0 && (
                <div className={styles.alertBanner}>
                  <Bell size={20} />
                  <div className={styles.alertContent}>
                    <strong>{account.unsold_options} unsold option contracts</strong>
                    <span> in this account</span>
                  </div>
                </div>
              )}

              {/* Holdings Table */}
              <div className={styles.tableCard}>
                <h3 className={styles.tableTitle}>Holdings & Options Income</h3>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'symbol')}>
                        Symbol {getSortIcon('symbol', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'shares')}>
                        Shares {getSortIcon('shares', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'price')}>
                        Price {getSortIcon('price', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'value')}>
                        Value {getSortIcon('value', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'options')}>
                        Options {getSortIcon('options', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'weekly')}>
                        Weekly {getSortIcon('weekly', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'monthly')}>
                        Monthly {getSortIcon('monthly', accountSort)}
                      </th>
                      <th className={styles.sortableHeader} onClick={() => handleAccountSort(account.account_id, 'yearly')}>
                        Yearly {getSortIcon('yearly', accountSort)}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedHoldings.map((holding) => (
                      <tr key={holding.symbol} className={holding.utilization_status === 'none' ? styles.unsoldRow : ''}>
                        <td>
                          <div className={styles.symbolCell}>
                            <strong>{holding.symbol}</strong>
                            {holding.utilization_status === 'none' && (
                              <span className={styles.unsoldLabel}>Not Sold</span>
                            )}
                          </div>
                        </td>
                        <td>{holding.shares.toLocaleString()}</td>
                        <td>{formatCurrency(holding.price)}</td>
                        <td>{formatCurrency(holding.value)}</td>
                        <td>
                          <div className={styles.optionsCell}>
                            <span className={`${styles.optionsBadge} ${
                              holding.utilization_status === 'full' ? styles.optionsFull :
                              holding.utilization_status === 'partial' ? styles.optionsPartial :
                              styles.optionsNone
                            }`}>
                              {holding.options}
                            </span>
                            {holding.sold_contracts !== undefined && holding.unsold_contracts !== undefined && (
                              <div className={styles.soldUnsoldInfo}>
                                {holding.sold_contracts > 0 && (
                                  <span className={styles.soldCount} title="Sold">
                                    <CheckCircle size={12} /> {holding.sold_contracts}
                                  </span>
                                )}
                                {holding.unsold_contracts > 0 && (
                                  <span className={styles.unsoldCount} title="Unsold">
                                    <XCircle size={12} /> {holding.unsold_contracts}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className={styles.incomeCell}>{formatCurrency(holding.weekly)}</td>
                        <td className={styles.incomeCell}>{formatCurrency(holding.monthly)}</td>
                        <td className={styles.incomeCell}>{formatCurrency(holding.yearly)}</td>
                      </tr>
                    ))}
                    <tr className={styles.totalRow}>
                      <td><strong>TOTAL</strong></td>
                      <td></td>
                      <td></td>
                      <td><strong>{formatCurrency(account.total_value)}</strong></td>
                      <td><strong>{account.total_options}</strong></td>
                      <td><strong>{formatCurrency(accountTotals.weekly)}</strong></td>
                      <td><strong>{formatCurrency(accountTotals.monthly)}</strong></td>
                      <td><strong>{formatCurrency(accountTotals.yearly)}</strong></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}

        {activeTab === 'roll-monitor' && (
          <div className={styles.rollMonitorView}>
            {/* Header with Check Button */}
            <div className={styles.rollMonitorHeader}>
              <div className={styles.rollMonitorTitle}>
                <Timer size={24} />
                <div>
                  <h2>Early Roll Monitor</h2>
                  <p>Track positions for 80%+ profit opportunities to roll early</p>
                </div>
              </div>
              <div className={styles.rollMonitorActions}>
                <div className={styles.thresholdInput}>
                  <label>Profit Threshold:</label>
                  <input
                    type="number"
                    value={profitThreshold}
                    onChange={(e) => setProfitThreshold(parseInt(e.target.value) || 80)}
                    min="50"
                    max="95"
                    step="5"
                  />
                  <span>%</span>
                </div>
                <button
                  className={styles.checkButton}
                  onClick={checkRollOpportunities}
                  disabled={rollCheckLoading}
                >
                  {rollCheckLoading ? (
                    <>
                      <RefreshCw size={18} className={styles.spinner} />
                      Checking...
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      Check Now
                    </>
                  )}
                </button>
              </div>
            </div>

            {lastCheckTime && (
              <div className={styles.lastCheckInfo}>
                <Clock size={14} />
                <span>
                  <strong>Last checked:</strong> {formatTimestamp(lastCheckTime)}
                  {' · '}
                  {lastCheckTime.toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                  })}
                </span>
              </div>
            )}

            {/* Active Alerts */}
            {rollAlerts.length > 0 && (
              <div className={styles.alertsSection}>
                <h3 className={styles.sectionTitle}>
                  <Zap size={20} />
                  Roll Opportunities ({rollAlerts.length})
                </h3>
                <div className={styles.alertsGrid}>
                  {rollAlerts.map((alert, idx) => (
                    <div 
                      key={idx} 
                      className={`${styles.alertCard} ${styles[`urgency${alert.urgency.charAt(0).toUpperCase() + alert.urgency.slice(1)}`]}`}
                    >
                      <div className={styles.alertHeader}>
                        <span className={styles.alertSymbol}>{alert.symbol}</span>
                        <span className={`${styles.urgencyBadge} ${styles[alert.urgency]}`}>
                          {alert.urgency.toUpperCase()}
                        </span>
                      </div>
                      <div className={styles.alertDetails}>
                        <div className={styles.alertRow}>
                          <span>Strike:</span>
                          <strong>${alert.strike_price} {alert.option_type.toUpperCase()}</strong>
                        </div>
                        <div className={styles.alertRow}>
                          <span>Expiry:</span>
                          <strong>{new Date(alert.expiration_date).toLocaleDateString()} ({alert.days_to_expiry}d)</strong>
                        </div>
                        <div className={styles.alertRow}>
                          <span>Contracts:</span>
                          <strong>{alert.contracts}</strong>
                        </div>
                        <div className={styles.alertPremiums}>
                          <div className={styles.premiumItem}>
                            <span>Sold at:</span>
                            <strong>${alert.original_premium.toFixed(2)}</strong>
                          </div>
                          <TrendingDown size={16} className={styles.premiumArrow} />
                          <div className={styles.premiumItem}>
                            <span>Now:</span>
                            <strong>${alert.current_premium.toFixed(2)}</strong>
                          </div>
                        </div>
                        <div className={styles.alertProfit}>
                          <span className={styles.profitLabel}>PROFIT</span>
                          <span className={styles.profitValue}>{alert.profit_percent.toFixed(1)}%</span>
                          <span className={styles.profitAmount}>(${alert.profit_amount.toFixed(2)})</span>
                        </div>
                      </div>
                      <div className={styles.alertRecommendation}>
                        <Target size={14} />
                        {alert.recommendation}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {rollCheckMessage && rollAlerts.length === 0 && (
              <div className={styles.noAlertsMessage}>
                <CheckCircle size={24} />
                <p>{rollCheckMessage}</p>
              </div>
            )}

            {/* Monitored Positions */}
            <div className={styles.positionsSection}>
              <div className={styles.sectionHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>
                    <Eye size={20} />
                    Monitored Positions ({monitoredPositions.length})
                  </h3>
                  <div className={styles.dataSourceIndicator}>
                    {usingLivePrices ? (
                      <span className={styles.liveIndicator}>
                        <Zap size={12} />
                        <strong>Live Prices</strong>
                        {priceUpdateTime && (
                          <span className={styles.updateTime}>
                            {' · '}
                            <strong>Updated:</strong> {formatTimestamp(priceUpdateTime)}
                            {' · '}
                            {priceUpdateTime.toLocaleString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              hour: 'numeric',
                              minute: '2-digit',
                              hour12: true
                            })}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className={styles.storedIndicator}>
                        <Clock size={12} />
                        <strong>Historical Data</strong>
                        {monitoredPositions.length > 0 && monitoredPositions[0].snapshot_date && (
                          <span className={styles.updateTime}>
                            {' · '}
                            <strong>From:</strong> {formatTimestamp(new Date(monitoredPositions[0].snapshot_date))}
                            {' · '}
                            {new Date(monitoredPositions[0].snapshot_date).toLocaleString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                              hour: 'numeric',
                              minute: '2-digit',
                              hour12: true
                            })}
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                </div>
                <div className={styles.positionActions}>
                  <button
                    className={styles.refreshPricesButton}
                    onClick={() => fetchMonitoredPositions(true)}
                    disabled={positionsLoading}
                  >
                    {positionsLoading ? (
                      <RefreshCw size={16} className={styles.spinning} />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    Refresh Prices
                  </button>
                  <button
                    className={styles.addPositionButton}
                    onClick={() => setShowAddPosition(!showAddPosition)}
                  >
                    <Plus size={16} />
                    Add Position
                  </button>
                </div>
              </div>

              {/* Add Position Form */}
              {showAddPosition && (
                <div className={styles.addPositionForm}>
                  <div className={styles.formGrid}>
                    <div className={styles.formField}>
                      <label>Symbol</label>
                      <input
                        type="text"
                        placeholder="AAPL"
                        value={newPosition.symbol}
                        onChange={(e) => setNewPosition({...newPosition, symbol: e.target.value})}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label>Strike Price</label>
                      <input
                        type="number"
                        placeholder="275.00"
                        step="0.5"
                        value={newPosition.strike_price}
                        onChange={(e) => setNewPosition({...newPosition, strike_price: e.target.value})}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label>Type</label>
                      <select
                        value={newPosition.option_type}
                        onChange={(e) => setNewPosition({...newPosition, option_type: e.target.value})}
                      >
                        <option value="call">Call</option>
                        <option value="put">Put</option>
                      </select>
                    </div>
                    <div className={styles.formField}>
                      <label>Expiration</label>
                      <input
                        type="date"
                        value={newPosition.expiration_date}
                        onChange={(e) => setNewPosition({...newPosition, expiration_date: e.target.value})}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label>Contracts</label>
                      <input
                        type="number"
                        min="1"
                        value={newPosition.contracts}
                        onChange={(e) => setNewPosition({...newPosition, contracts: e.target.value})}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label>Premium Received ($)</label>
                      <input
                        type="number"
                        placeholder="4.50"
                        step="0.01"
                        value={newPosition.original_premium}
                        onChange={(e) => setNewPosition({...newPosition, original_premium: e.target.value})}
                      />
                    </div>
                  </div>
                  <div className={styles.formActions}>
                    <button className={styles.cancelButton} onClick={() => setShowAddPosition(false)}>
                      Cancel
                    </button>
                    <button 
                      className={styles.submitButton}
                      onClick={addMonitoredPosition}
                      disabled={!newPosition.symbol || !newPosition.strike_price || !newPosition.expiration_date || !newPosition.original_premium}
                    >
                      <Plus size={16} />
                      Add Position
                    </button>
                  </div>
                </div>
              )}

              {/* Positions Table */}
              {monitoredPositions.length > 0 ? (
                <>
                  <div className={styles.positionsSummary}>
                    <span>{monitoredPositions.length} positions</span>
                    <span className={styles.monitorableCount}>
                      {monitoredPositions.filter(p => p.can_monitor).length} can be monitored
                    </span>
                  </div>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th 
                          onClick={() => handleMonitorSort('symbol')} 
                          className={styles.sortableHeader}
                        >
                          Symbol {monitorSort.field === 'symbol' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('strike_price')} 
                          className={styles.sortableHeader}
                        >
                          Strike {monitorSort.field === 'strike_price' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th>Type</th>
                        <th 
                          onClick={() => handleMonitorSort('expiration_date')} 
                          className={styles.sortableHeader}
                        >
                          Expiry {monitorSort.field === 'expiration_date' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('days_to_expiry')} 
                          className={styles.sortableHeader}
                        >
                          Days {monitorSort.field === 'days_to_expiry' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('contracts')} 
                          className={styles.sortableHeader}
                        >
                          Contracts {monitorSort.field === 'contracts' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('original_premium')} 
                          className={styles.sortableHeader}
                        >
                          Original $ {monitorSort.field === 'original_premium' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('current_premium')} 
                          className={styles.sortableHeader}
                        >
                          Current $ {monitorSort.field === 'current_premium' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('gain_loss_percent')} 
                          className={styles.sortableHeader}
                        >
                          G/L % {monitorSort.field === 'gain_loss_percent' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th 
                          onClick={() => handleMonitorSort('account')} 
                          className={styles.sortableHeader}
                        >
                          Account {monitorSort.field === 'account' && (monitorSort.direction === 'asc' ? '↑' : '↓')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedMonitoredPositions.map((pos) => (
                        <tr key={pos.id} className={!pos.can_monitor ? styles.cannotMonitor : ''}>
                          <td><strong>{pos.symbol}</strong></td>
                          <td>${pos.strike_price.toFixed(0)}</td>
                          <td className={styles.optionType}>{pos.option_type.toUpperCase()}</td>
                          <td>{pos.expiration_date ? new Date(pos.expiration_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}</td>
                          <td>
                            <span className={pos.days_to_expiry !== undefined && pos.days_to_expiry <= 2 ? styles.expiringWarning : ''}>
                              {pos.days_to_expiry ?? '-'}
                            </span>
                          </td>
                          <td>{pos.contracts}</td>
                          <td>
                            {pos.original_premium ? (
                              <span title={`Source: ${pos.premium_source}`}>
                                ${pos.original_premium.toFixed(2)}
                                {pos.premium_source === 'calculated' && <sup>*</sup>}
                              </span>
                            ) : '-'}
                          </td>
                          <td>{pos.current_premium ? `$${pos.current_premium.toFixed(2)}` : '-'}</td>
                          <td>
                            {pos.gain_loss_percent !== undefined && pos.gain_loss_percent !== null ? (
                              <span className={pos.gain_loss_percent >= 0 ? styles.profitText : styles.lossText}>
                                {pos.gain_loss_percent >= 0 ? '+' : ''}{pos.gain_loss_percent.toFixed(1)}%
                              </span>
                            ) : '-'}
                          </td>
                          <td className={styles.accountCell}>
                            {pos.account?.replace("'s ", " ").split(' ')[0] || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className={styles.tableFootnote}>
                    <sup>*</sup> Original premium calculated from gain/loss %
                  </div>
                </>
              ) : (
                <div className={styles.emptyState}>
                  <Eye size={32} />
                  <p>No positions found</p>
                  <span>Paste your sold options in the account tabs, or add positions manually above</span>
                </div>
              )}
            </div>

            {/* Historical Alerts */}
            {historicalAlerts.length > 0 && (
              <div className={styles.historySection}>
                <h3 className={styles.sectionTitle}>
                  <Clock size={20} />
                  Recent Alerts
                </h3>
                <div className={styles.historyList}>
                  {historicalAlerts.slice(0, 5).map((alert) => (
                    <div 
                      key={alert.id} 
                      className={`${styles.historyItem} ${alert.acknowledged ? styles.acknowledged : ''}`}
                    >
                      <div className={styles.historyMain}>
                        <span className={styles.historySymbol}>{alert.symbol}</span>
                        <span className={styles.historyStrike}>${alert.strike_price} {alert.option_type}</span>
                        <span className={styles.historyProfit}>{alert.profit_percent.toFixed(1)}% profit</span>
                        <span className={styles.historyTime}>
                          {new Date(alert.alert_triggered_at).toLocaleString()}
                        </span>
                      </div>
                      {!alert.acknowledged && (
                        <div className={styles.historyActions}>
                          <button onClick={() => acknowledgeAlert(alert.id, 'rolled')} title="Rolled">
                            <RefreshCw size={14} />
                          </button>
                          <button onClick={() => acknowledgeAlert(alert.id, 'closed')} title="Closed">
                            <XCircle size={14} />
                          </button>
                          <button onClick={() => acknowledgeAlert(alert.id, 'ignored')} title="Ignored">
                            <Eye size={14} />
                          </button>
                        </div>
                      )}
                      {alert.acknowledged && alert.action_taken && (
                        <span className={styles.actionTaken}>{alert.action_taken}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Info Section */}
            <div className={styles.infoSection}>
              <h4>How It Works</h4>
              <div className={styles.infoGrid}>
                <div className={styles.infoItem}>
                  <div className={styles.infoNumber}>1</div>
                  <div>
                    <strong>Add Positions</strong>
                    <p>When you sell an option, add it here with the premium you received</p>
                  </div>
                </div>
                <div className={styles.infoItem}>
                  <div className={styles.infoNumber}>2</div>
                  <div>
                    <strong>Click "Check Now"</strong>
                    <p>Fetches current option prices from Yahoo Finance and calculates profit</p>
                  </div>
                </div>
                <div className={styles.infoItem}>
                  <div className={styles.infoNumber}>3</div>
                  <div>
                    <strong>Get Alerted</strong>
                    <p>When profit reaches {profitThreshold}%+, you'll see an alert to roll early</p>
                  </div>
                </div>
                <div className={styles.infoItem}>
                  <div className={styles.infoNumber}>4</div>
                  <div>
                    <strong>Take Action</strong>
                    <p>Close the position in Robinhood and open a new one for next week</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {!loading && activeTab === 'settings' && data && (
          <div className={styles.settingsCard}>
            <h3 className={styles.settingsTitle}>
              <Settings size={20} />
              Options Strategy Parameters
            </h3>
            
            <div className={styles.settingsRow}>
              <div className={styles.settingItem}>
                <label>Delta</label>
                <div className={styles.inputGroup}>
                  <input
                    type="number"
                    value={delta}
                    onChange={(e) => setDelta(parseInt(e.target.value) || 10)}
                    step="5"
                    min="5"
                    max="50"
                  />
                </div>
                <span className={styles.settingHint}>
                  Delta 10 = ~90% win rate
                </span>
              </div>

              <div className={styles.settingItem}>
                <label>Active Weeks per Year</label>
                <div className={styles.inputGroup}>
                  <input
                    type="number"
                    value={weeksPerYear}
                    onChange={(e) => setWeeksPerYear(parseInt(e.target.value) || 50)}
                    min="40"
                    max="52"
                  />
                </div>
                <span className={styles.settingHint}>
                  Weeks actively selling options
                </span>
              </div>

              <div className={styles.settingItem}>
                <label>Default Premium (Other)</label>
                <div className={styles.inputGroup}>
                  <span>$</span>
                  <input
                    type="number"
                    value={defaultPremium}
                    onChange={(e) => setDefaultPremium(parseFloat(e.target.value) || 60)}
                    step="5"
                    min="0"
                  />
                </div>
                <span className={styles.settingHint}>
                  For symbols not listed below
                </span>
              </div>
            </div>

            {/* Per-Symbol Premiums */}
            <div className={styles.symbolPremiumsSection}>
              <h4 className={styles.sectionTitle}>Weekly Premium per Contract by Symbol</h4>
              <p className={styles.sectionHint}>
                Set the expected weekly premium for each stock based on its volatility. 
                <strong> Changes update instantly in all calculations.</strong>
              </p>
              
              <div className={styles.symbolPremiumsGrid}>
                {data.symbols.map((symbol) => {
                  // Prioritize database settings (symbolPremiums) over API response
                  const currentPremium = symbolPremiums[symbol.symbol] ?? symbol.premium_per_contract ?? defaultPremium;
                  const projectedWeekly = symbol.options * currentPremium;
                  return (
                    <div key={symbol.symbol} className={styles.symbolPremiumItem}>
                      <div className={styles.symbolInfo}>
                        <span className={styles.symbolName}>{symbol.symbol}</span>
                        <span className={styles.symbolOptions}>{symbol.options} options</span>
                      </div>
                      <div className={styles.premiumInput}>
                        <span>$</span>
                        <input
                          type="number"
                          value={currentPremium}
                          onChange={(e) => updateSymbolPremium(symbol.symbol, parseFloat(e.target.value) || 0)}
                          step="5"
                          min="0"
                        />
                        <span className={styles.perWeek}>/wk</span>
                      </div>
                      <div className={styles.projectedIncome}>
                        <span className={styles.weeklyProjection}>
                          {formatCurrency(projectedWeekly)}/wk
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className={styles.deltaGuide}>
              <h4>Delta Guide (Reference)</h4>
              <table className={styles.deltaTable}>
                <thead>
                  <tr>
                    <th>Delta</th>
                    <th>Win Rate</th>
                    <th>Est. Premium</th>
                    <th>Risk Level</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={delta === 5 ? styles.selected : ''}>
                    <td>5</td>
                    <td>~95%</td>
                    <td>$30-40/contract</td>
                    <td>Very Low</td>
                  </tr>
                  <tr className={delta === 10 ? styles.selected : ''}>
                    <td>10</td>
                    <td>~90%</td>
                    <td>$50-80/contract</td>
                    <td>Low</td>
                  </tr>
                  <tr className={delta === 15 ? styles.selected : ''}>
                    <td>15</td>
                    <td>~85%</td>
                    <td>$80-120/contract</td>
                    <td>Medium-Low</td>
                  </tr>
                  <tr className={delta === 20 ? styles.selected : ''}>
                    <td>20</td>
                    <td>~80%</td>
                    <td>$100-150/contract</td>
                    <td>Medium</td>
                  </tr>
                  <tr className={delta === 30 ? styles.selected : ''}>
                    <td>30</td>
                    <td>~70%</td>
                    <td>$150-250/contract</td>
                    <td>Higher</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <button className={styles.applyButton} onClick={applySettings}>
              <RefreshCw size={18} />
              Save & Sync with Server
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
