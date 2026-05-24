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
  FlaskConical,
  X,
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
import TechnicalAnalysisModal from '../components/TechnicalAnalysisModal';
import { getAuthHeaders } from '../contexts/AuthContext';
import {
  HoldingsTable,
  symbolColumn,
  sharesColumn,
  priceColumn,
  valueColumn,
  optionsBadgeColumn,
  incomeWithYieldColumn,
} from '../components/HoldingsTable';
import type { HoldingsRow, ColumnDef } from '../components/HoldingsTable';

interface Holding {
  symbol: string;
  description: string;
  shares: number;
  price: number;
  value: number;
  options: number;
  premium_per_contract?: number;
  premium_source?: 'database' | 'hardcoded' | 'global_default' | 'user_override' | 'actual_puts';
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  sold_contracts?: number;
  unsold_contracts?: number;
  utilization_status?: 'none' | 'partial' | 'full';
  is_cash_row?: boolean;
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
  cost_basis?: number;
  avg_cost_per_share?: number;
  options: number;
  premium_per_contract: number;
  put_premium_per_contract?: number;
  premium_source?: 'database' | 'hardcoded' | 'global_default' | 'user_override' | 'actual_puts';
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  account_count: number;
  accounts: string[];
  sold_contracts?: number;
  unsold_contracts?: number;
  utilization_status?: 'none' | 'partial' | 'full';
  is_cash_row?: boolean;
}

interface OptionSignal {
  action: 'sell' | 'hold' | 'buy_back';
  confidence: 'strong' | 'moderate' | 'weak';
  score: number;
  reason: string;
}

interface PutPremiumData {
  symbol: string;
  put_premium_per_contract: number;
  put_contracts_sold?: number;
  put_net_total?: number;
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
  total_cash_for_puts?: number;
}

interface PutPosition {
  account: string;
  strike_price: number;
  contracts: number;
  value_locked: number;
  expiration_date: string | null;
  original_premium: number | null;
  current_premium: number | null;
}

interface PutSymbolSummary {
  symbol: string;
  total_contracts: number;
  shares_equivalent: number;
  value_locked: number;
  current_price: number | null;
  avg_cost_per_share: number | null;
  strikes: number[];
  positions: PutPosition[];
  weekly_income: number;
  monthly_income: number;
  yearly_income: number;
  account_count: number;
  accounts: string[];
}

interface SoldOptionsSnapshot {
  id: number;
  source: string;
  account_name?: string;
  snapshot_date: string;
  created_at: string;
}

interface IncomePeriod {
  start: string;
  end: string;
  label: string;
}

interface IncomePeriods {
  weekly?: IncomePeriod;
  monthly?: IncomePeriod;
  yearly?: IncomePeriod;
}

interface OptionsData {
  params: {
    default_premium: number;
    symbol_premiums: Record<string, number>;
    delta: number;
    weeks_per_year: number;
  };
  portfolio_summary: PortfolioSummary;
  income_periods?: IncomePeriods;
  sold_options_snapshot?: SoldOptionsSnapshot | null;
  symbols: SymbolSummary[];
  put_symbols: PutSymbolSummary[];
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

// Acquisition Watchlist interfaces
interface AcquisitionPutOption {
  strike: number;
  bid: number;
  ask: number;
  delta: number;
  otm_pct: number;
  premium: number;
  effective_buy_price: number;
  discount_pct: number;
  capital_required: number;
  expiration: string;
  prob_otm: number;
}

interface AcquisitionWatchlistItem {
  id: number;
  symbol: string;
  target_price: number | null;
  notes: string | null;
  created_at: string;
  current_price: number | null;
  put_options: AcquisitionPutOption[];
  ta_summary: {
    rsi: number;
    rsi_status: string;
    bb_position_pct: number;
    trend: string;
  } | null;
}

// Put Opportunities interface
interface PutOpportunity {
  symbol: string;
  current_price: number;
  strike: number;
  otm_pct: number;
  bid: number;
  ask: number;
  premium: number;
  grade: string;
  score: number;
  roi_pct: number;
  capital_required: number;
  expiration: string;
  delta: number;
  prob_otm: number;
  rsi: number;
  rsi_status: string;
  bb_position_pct: number;
  bb_status: string;
  ta_score: number;
  premium_score: number;
  trend: string;
  rationale: string;
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
type SortField = 'symbol' | 'shares' | 'price' | 'value' | 'options' | 'weekly' | 'monthly' | 'yearly' | 'expectedWeekly' | 'actualWeekly' | 'expectedMonthly' | 'actualMonthly';

const COLORS = ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EF4444', '#EC4899'];

// Cache configuration
const CACHE_KEY = 'options_selling_data';
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes

interface CachedData {
  data: OptionsData;
  timestamp: number;
  symbolPremiums: Record<string, number>;
}

const getCachedData = (): CachedData | null => {
  try {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (!cached) return null;
    const parsed: CachedData = JSON.parse(cached);
    return parsed;
  } catch {
    return null;
  }
};

const setCachedData = (data: OptionsData, symbolPremiums: Record<string, number>) => {
  try {
    const cacheEntry: CachedData = {
      data,
      timestamp: Date.now(),
      symbolPremiums
    };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheEntry));
  } catch {
    // Ignore storage errors
  }
};

const isCacheFresh = (cached: CachedData | null): boolean => {
  if (!cached) return false;
  return Date.now() - cached.timestamp < CACHE_TTL_MS;
};

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
  const [dataLastUpdated, setDataLastUpdated] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [taSymbol, setTaSymbol] = useState<string | null>(null);
  const [optionSignals, setOptionSignals] = useState<Record<string, OptionSignal>>({});
  const [signalsLoading, setSignalsLoading] = useState(false);
  
  // Settings
  const [defaultPremium, setDefaultPremium] = useState(60);
  const [symbolPremiums, setSymbolPremiums] = useState<Record<string, number>>({});
  const [callNetTotals, setCallNetTotals] = useState<Record<string, number>>({}); // Total net premium (4 weeks) per symbol
  const [putPremiums, setPutPremiums] = useState<Record<string, PutPremiumData>>({});
  const [delta, setDelta] = useState(10);
  const [weeksPerYear, setWeeksPerYear] = useState(50);

  // V6 account-type delta targets
  const [iraDelta, setIraDelta] = useState(75);
  const [taxableDelta, setTaxableDelta] = useState(90);

  // Sorting state for premium sections (Settings tab)
  type PremiumSortField = 'netTotal' | 'roc' | 'premium' | 'symbol';
  const [callPremiumSort, setCallPremiumSort] = useState<PremiumSortField>('netTotal');
  const [putPremiumSort, setPutPremiumSort] = useState<PremiumSortField>('netTotal');

  // Sorting state for overview
  const [overviewSort, setOverviewSort] = useState<{ field: SortField; direction: SortDirection }>({
    field: 'options',
    direction: 'desc'
  });

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
    // Check for fresh cached data first
    const cached = getCachedData();
    if (isCacheFresh(cached) && cached) {
      // Use cached data immediately - no loading state
      setData(cached.data);
      setSymbolPremiums(cached.symbolPremiums);
      setDataLastUpdated(new Date(cached.timestamp));
      setLoading(false);
    } else {
      // No fresh cache, fetch from server
      fetchData();
    }
  }, []);

  const fetchData = async (customPremiums?: Record<string, number>, forceRefresh: boolean = false) => {
    // If not forcing refresh and we have data, show refreshing indicator instead of full loading
    if (forceRefresh && data) {
      setIsRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const response = await fetch('/api/v1/strategies/options-selling/income-projection-with-status', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          default_premium: defaultPremium,
          symbol_premiums: customPremiums || symbolPremiums,
          delta: delta,
          weeks_per_year: weeksPerYear,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      setData(result);

      // Update symbol premiums from API response (which includes database values)
      const newPremiums = result.params?.symbol_premiums
        ? { ...symbolPremiums, ...result.params.symbol_premiums }
        : symbolPremiums;

      if (result.params?.symbol_premiums) {
        setSymbolPremiums(newPremiums);
      }

      // Save to cache
      setCachedData(result, newPremiums);
      setDataLastUpdated(new Date());
    } catch (err) {
      console.error('Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  // Fetch directional signals for all symbols when data loads
  const fetchOptionSignals = async (symbols: SymbolSummary[]) => {
    setSignalsLoading(true);
    try {
      const payload = symbols
        .filter(s => !s.is_cash_row && s.symbol !== 'CASH')
        .map(s => ({ symbol: s.symbol, utilization: s.utilization_status || 'none' }));
      const response = await fetch('/api/v1/strategies/technical-analysis/batch-signals', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: payload }),
      });
      if (response.ok) {
        const result = await response.json();
        setOptionSignals(result.signals || {});
      }
    } catch (err) {
      console.error('Failed to fetch option signals:', err);
    } finally {
      setSignalsLoading(false);
    }
  };

  useEffect(() => {
    if (data?.symbols?.length) {
      fetchOptionSignals(data.symbols);
    }
  }, [data?.symbols]);

  // Manual refresh function - forces a fresh fetch
  const handleRefresh = () => {
    fetchData(undefined, true);
  };

  const applySettings = () => {
    fetchData(symbolPremiums);
  };

  // Fetch premium settings including PUT premiums and call_net_total for ROC calculation
  const fetchPremiumSettings = async () => {
    try {
      const response = await fetch('/api/v1/strategies/premium-settings', {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const settings = await response.json();
        const putData: Record<string, PutPremiumData> = {};
        const callNetData: Record<string, number> = {};
        Object.entries(settings).forEach(([symbol, data]: [string, any]) => {
          // Store call_net_total for ROC calculation
          if (data.call_net_total) {
            callNetData[symbol] = data.call_net_total;
          }
          // Store put premium data
          if (data.put_premium_per_contract) {
            putData[symbol] = {
              symbol,
              put_premium_per_contract: data.put_premium_per_contract,
              put_contracts_sold: data.put_contracts_sold,
              put_net_total: data.put_net_total,
            };
          }
        });
        setCallNetTotals(callNetData);
        setPutPremiums(putData);
      }
    } catch (err) {
      console.error('Failed to fetch premium settings:', err);
    }
  };

  // Fetch premium settings on mount and when Settings tab is active
  // This provides call_net_total data for accurate ROC calculation
  useEffect(() => {
    fetchPremiumSettings();
  }, []);

  useEffect(() => {
    if (activeTab === 'settings') {
      fetchPremiumSettings();
    }
  }, [activeTab]);

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

  // Put Opportunities state
  const [putOpportunities, setPutOpportunities] = useState<PutOpportunity[]>([]);
  const [putLoading, setPutLoading] = useState(false);
  const [putLastUpdated, setPutLastUpdated] = useState<Date | null>(null);
  const [putSortField, setPutSortField] = useState<'score' | 'premium' | 'roi_pct' | 'capital_required'>('score');
  const [putSortDesc, setPutSortDesc] = useState(true);

  // Acquisition Watchlist state
  const [acquisitionWatchlist, setAcquisitionWatchlist] = useState<AcquisitionWatchlistItem[]>([]);
  const [acquisitionLoading, setAcquisitionLoading] = useState(false);
  const [showAddAcquisition, setShowAddAcquisition] = useState(false);
  const [newAcquisitionSymbol, setNewAcquisitionSymbol] = useState('');
  const [newAcquisitionTargetPrice, setNewAcquisitionTargetPrice] = useState('');
  const [newAcquisitionNotes, setNewAcquisitionNotes] = useState('');

  // Test Mode state
  const [testModeEnabled, setTestModeEnabled] = useState(false);
  const [testModeLoading, setTestModeLoading] = useState(false);
  const [cacheStatus, setCacheStatus] = useState<{
    is_market_hours: boolean;
    prices_ttl_display: string;
  } | null>(null);

  // Fetch test mode status on mount
  const fetchTestModeStatus = async () => {
    try {
      const response = await fetch('/api/v1/strategies/debug/cache-status');
      if (response.ok) {
        const data = await response.json();
        setTestModeEnabled(data.test_mode?.enabled || false);
        setCacheStatus({
          is_market_hours: data.market_status?.is_market_hours || false,
          prices_ttl_display: data.effective_cache_ttl?.prices_ttl_display || 'unknown',
        });
      }
    } catch (err) {
      console.error('Error fetching test mode status:', err);
    }
  };

  // Toggle test mode
  const toggleTestMode = async () => {
    setTestModeLoading(true);
    try {
      const response = await fetch(`/api/v1/strategies/debug/test-mode?enable=${!testModeEnabled}`, {
        method: 'POST',
      });
      if (response.ok) {
        const data = await response.json();
        setTestModeEnabled(data.test_mode_enabled);
        // Refresh cache status
        await fetchTestModeStatus();
      }
    } catch (err) {
      console.error('Error toggling test mode:', err);
    } finally {
      setTestModeLoading(false);
    }
  };

  // Fetch test mode status on component mount
  useEffect(() => {
    fetchTestModeStatus();
  }, []);

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

  // Fetch put selling opportunities (from database cache)
  const fetchPutOpportunities = async (forceRefresh: boolean = false) => {
    setPutLoading(true);
    try {
      const url = forceRefresh
        ? '/api/v1/strategies/put-opportunities?refresh=true'
        : '/api/v1/strategies/put-opportunities';
      const response = await fetch(url, {
        headers: getAuthHeaders()
      });
      if (!response.ok) {
        throw new Error('Failed to fetch put opportunities');
      }
      const result = await response.json();
      setPutOpportunities(result.opportunities || []);
      if (result.updated_at) {
        setPutLastUpdated(new Date(result.updated_at));
      }
    } catch (err) {
      console.error('Error fetching put opportunities:', err);
    } finally {
      setPutLoading(false);
    }
  };

  // Load put opportunities on mount
  useEffect(() => {
    fetchPutOpportunities(false); // Load from cache on mount
    fetchAcquisitionWatchlist(); // Load acquisition watchlist
  }, []);

  // Fetch acquisition watchlist
  const fetchAcquisitionWatchlist = async () => {
    setAcquisitionLoading(true);
    try {
      const response = await fetch('/api/v1/strategies/acquisition-watchlist', {
        headers: getAuthHeaders()
      });
      if (!response.ok) {
        throw new Error('Failed to fetch acquisition watchlist');
      }
      const result = await response.json();
      setAcquisitionWatchlist(result.watchlist || []);
    } catch (err) {
      console.error('Error fetching acquisition watchlist:', err);
    } finally {
      setAcquisitionLoading(false);
    }
  };

  // Add to acquisition watchlist
  const addToAcquisitionWatchlist = async () => {
    if (!newAcquisitionSymbol.trim()) return;

    try {
      const response = await fetch('/api/v1/strategies/acquisition-watchlist', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: newAcquisitionSymbol.toUpperCase(),
          target_price: newAcquisitionTargetPrice ? parseFloat(newAcquisitionTargetPrice) : null,
          notes: newAcquisitionNotes || null,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to add to watchlist');
      }

      // Reset form and refresh
      setNewAcquisitionSymbol('');
      setNewAcquisitionTargetPrice('');
      setNewAcquisitionNotes('');
      setShowAddAcquisition(false);
      fetchAcquisitionWatchlist();
    } catch (err) {
      console.error('Error adding to watchlist:', err);
    }
  };

  // Remove from acquisition watchlist
  const removeFromAcquisitionWatchlist = async (symbol: string) => {
    try {
      const response = await fetch(`/api/v1/strategies/acquisition-watchlist/${symbol}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Failed to remove from watchlist');
      }

      fetchAcquisitionWatchlist();
    } catch (err) {
      console.error('Error removing from watchlist:', err);
    }
  };

  // Sorted put opportunities
  const sortedPutOpportunities = useMemo(() => {
    return [...putOpportunities].sort((a, b) => {
      const aVal = a[putSortField] || 0;
      const bVal = b[putSortField] || 0;
      return putSortDesc ? bVal - aVal : aVal - bVal;
    });
  }, [putOpportunities, putSortField, putSortDesc]);

  // Helper for grade color
  const getGradeColor = (grade: string) => {
    if (grade === 'A+') return '#00D632';
    if (grade === 'A') return '#4CAF50';
    if (grade === 'B+') return '#8BC34A';
    if (grade === 'B') return '#FFC107';
    if (grade === 'C') return '#FF9800';
    return '#F44336';
  };

  // Generate rationale tooltip for put opportunity
  const getPutRationale = (opp: PutOpportunity) => {
    const rsiDesc = opp.rsi < 30 ? 'oversold' : opp.rsi < 40 ? 'near oversold' : opp.rsi < 50 ? 'neutral-bullish' : 'neutral';
    const bbDesc = opp.bb_position_pct < 20 ? 'at support (bottom of range)' :
                   opp.bb_position_pct < 35 ? 'in lower half of range' :
                   opp.bb_position_pct < 50 ? 'below middle' : 'at middle';

    const probOtm = ((1 - Math.abs(opp.delta || 0.1)) * 100).toFixed(0);

    return `Why ${opp.symbol} is a good put sell:

📊 RSI at ${opp.rsi?.toFixed(0)} (${rsiDesc}) - Stock has pulled back
📈 Bollinger Band at ${opp.bb_position_pct?.toFixed(0)}% (${bbDesc}) - Near lower support
📉 Stock at $${opp.current_price?.toFixed(2)}, selling $${opp.strike?.toFixed(0)} put (${opp.otm_pct?.toFixed(1)}% below)

💡 Recommendation: Sell the $${opp.strike?.toFixed(0)} put for $${opp.premium?.toFixed(0)} premium.
• ${probOtm}% chance it expires worthless (you keep premium)
• If assigned, you buy ${opp.symbol} at $${opp.strike?.toFixed(0)} (${opp.otm_pct?.toFixed(1)}% discount)
• Capital required: $${(opp.capital_required || 0).toLocaleString()}`;
  };


  // V6: determine delta target by account type
  const getV6DeltaTarget = (accountType: string) => {
    return ['retirement', 'ira', 'roth_ira'].includes(accountType)
      ? { delta: iraDelta, label: 'IRA', style: 'ira' as const }
      : { delta: taxableDelta, label: 'Taxable', style: 'taxable' as const };
  };

  // V6: assignment stance for puts — compare strike vs cost basis
  const getAssignmentStance = (put: PutSymbolSummary): { label: string; stance: 'good' | 'neutral' | 'bad' } | null => {
    if (!put.avg_cost_per_share || put.avg_cost_per_share === 0 || put.strikes.length === 0) return null;
    const avgStrike = put.strikes.reduce((a, b) => a + b, 0) / put.strikes.length;
    const diff = (avgStrike - put.avg_cost_per_share) / put.avg_cost_per_share;
    if (diff < -0.02) return { label: 'Lowers avg', stance: 'good' };
    if (diff <= 0.02) return { label: 'Neutral', stance: 'neutral' };
    return { label: 'Raises avg', stance: 'bad' };
  };

  // V6: nearest expiration across all positions for a put symbol
  const getNearestExpiry = (put: PutSymbolSummary): string | null => {
    const dates = put.positions.map(p => p.expiration_date).filter(Boolean) as string[];
    if (dates.length === 0) return null;
    return dates.sort()[0];
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

  // Use backend's actual income values (from historical transactions)
  const getSymbolIncome = (symbol: SymbolSummary) => {
    return {
      premium: symbol.premium_per_contract,
      weekly: symbol.weekly_income,
      monthly: symbol.monthly_income,
      yearly: symbol.yearly_income
    };
  };

  const getHoldingIncome = (holding: Holding) => {
    // Use the backend's actual income values directly (from historical transactions)
    return {
      premium: holding.premium_per_contract ?? 0,
      weekly: holding.weekly_income,
      monthly: holding.monthly_income,
      yearly: holding.yearly_income
    };
  };

  // Use actual income from backend (not projections)
  // The backend now calculates income from actual historical transactions:
  // - Weekly: Last complete week
  // - Monthly: Last complete month
  // - Yearly: Last complete year
  const portfolioTotals = useMemo(() => {
    if (!data) return null;

    // Use the backend's actual income values directly
    const totalWeekly = data.portfolio_summary.weekly_income;
    const totalMonthly = data.portfolio_summary.monthly_income;
    const totalYearly = data.portfolio_summary.yearly_income;

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
  }, [data]);

  // Use actual account income from backend (not projections)
  const getAccountTotals = (account: Account) => {
    // Use the backend's actual income values directly
    return {
      weekly: account.weekly_income,
      monthly: account.monthly_income,
      yearly: account.yearly_income,
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
    
    const symbolsWithCalc = data.symbols.map(sym => {
      const income = getSymbolIncome(sym);
      return {
        ...sym,
        ...income,
        expectedWeekly: sym.value * 0.01 / 4,
        expectedMonthly: sym.value * 0.01,
        actualWeekly: income.weekly,
        actualMonthly: income.monthly,
      };
    });

    if (overviewSort.direction === null) return symbolsWithCalc;

    return [...symbolsWithCalc].sort((a, b) => {
      let aVal: number | string, bVal: number | string;
      switch (overviewSort.field) {
        case 'symbol': aVal = a.symbol; bVal = b.symbol; break;
        case 'shares': aVal = a.shares; bVal = b.shares; break;
        case 'price': aVal = a.price; bVal = b.price; break;
        case 'value': aVal = a.value; bVal = b.value; break;
        case 'options': aVal = a.options; bVal = b.options; break;
        case 'expectedWeekly': aVal = a.expectedWeekly; bVal = b.expectedWeekly; break;
        case 'actualWeekly': aVal = a.actualWeekly; bVal = b.actualWeekly; break;
        case 'expectedMonthly': aVal = a.expectedMonthly; bVal = b.expectedMonthly; break;
        case 'actualMonthly': aVal = a.actualMonthly; bVal = b.actualMonthly; break;
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

  // Call symbols only (exclude CASH/put rows)
  const callSymbols = sortedSymbols.filter(s => !s.is_cash_row && s.symbol !== 'CASH');

  // Put symbols: open positions (with value locked) sorted by value locked, then historical-only by yearly income
  const sortedPutSymbols = useMemo(() => {
    if (!data?.put_symbols) return [];
    return [...data.put_symbols].sort((a, b) => {
      if (b.value_locked !== a.value_locked) return b.value_locked - a.value_locked;
      return Math.abs(b.yearly_income) - Math.abs(a.yearly_income);
    });
  }, [data?.put_symbols]);

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

  // --- Shared HoldingsTable integration for per-account views ---
  const holdingToRow = (holding: Holding & { premium?: number; weekly: number; monthly: number; yearly: number }): HoldingsRow => ({
    symbol: holding.symbol,
    shares: holding.shares,
    currentPrice: holding.price,
    value: holding.value,
    isCash: holding.is_cash_row || holding.symbol === 'CASH',
    options: holding.options,
    soldContracts: holding.sold_contracts,
    unsoldContracts: holding.unsold_contracts,
    utilizationStatus: holding.utilization_status,
    weeklyIncome: holding.weekly,
    monthlyIncome: holding.monthly,
    yearlyIncome: holding.yearly,
    premiumSource: holding.premium_source,
    subtitle: holding.utilization_status === 'none' ? undefined : undefined,
  })

  const optionsAccountColumns: ColumnDef[] = [
    symbolColumn({ showSubtitle: true }),
    sharesColumn(),
    priceColumn(),
    valueColumn(),
    optionsBadgeColumn(),
    incomeWithYieldColumn('weekly', 'Weekly', 'weeklyIncome', data?.income_periods?.weekly?.label),
    incomeWithYieldColumn('monthly', 'Monthly', 'monthlyIncome', data?.income_periods?.monthly?.label),
    incomeWithYieldColumn('yearly', 'Yearly', 'yearlyIncome', data?.income_periods?.yearly?.label),
  ]

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
              Weekly income from the options wheel — covered calls + cash-secured puts
            </p>
          </div>
        </div>
        {/* Refresh button and last updated indicator */}
        {!loading && data && (
          <div className={styles.headerActions}>
            <span className={styles.lastUpdated}>
              {dataLastUpdated ? `Updated ${formatTimestamp(dataLastUpdated)}` : ''}
            </span>
            <button
              className={styles.refreshButton}
              onClick={handleRefresh}
              disabled={isRefreshing}
              title="Refresh data"
            >
              <RefreshCw size={16} className={isRefreshing ? styles.spinner : ''} />
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </button>
            {/* Test Mode Toggle */}
            <button
              className={`${styles.testModeToggle} ${testModeEnabled ? styles.testModeActive : ''}`}
              onClick={toggleTestMode}
              disabled={testModeLoading}
              title={testModeEnabled ? 'Disable Test Mode' : 'Enable Test Mode (uses cached data)'}
            >
              <FlaskConical size={16} />
              {testModeLoading ? '...' : testModeEnabled ? 'Test Mode ON' : 'Test Mode'}
            </button>
          </div>
        )}
      </header>

      {/* Test Mode Banner */}
      {testModeEnabled && (
        <div className={styles.testModeBanner}>
          <div className={styles.testModeBannerContent}>
            <FlaskConical size={18} />
            <span>
              <strong>Test Mode Active</strong> — Using cached data (no live API calls).
              Cache TTL: {cacheStatus?.prices_ttl_display || '24h'}.
              {cacheStatus?.is_market_hours ? ' Market is OPEN.' : ' Market is closed.'}
            </span>
          </div>
          <button
            className={styles.testModeBannerClose}
            onClick={toggleTestMode}
            title="Disable Test Mode"
          >
            <X size={18} />
          </button>
        </div>
      )}

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
          const v6 = getV6DeltaTarget(account.account_type);

          return (
            <button
              key={account.account_id}
              className={`${styles.tab} ${activeTab === account.account_id ? styles.activeTab : ''}`}
              onClick={() => setActiveTab(account.account_id)}
            >
              <span>{shortLabel}</span>
              <span className={v6.style === 'ira' ? styles.deltaChipIra : styles.deltaChipTaxable}>
                Δ{v6.delta}
              </span>
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
                <TrendingDown size={20} />
                <div>
                  <span className={styles.strategyLabel}>IRA Puts</span>
                  <span className={styles.strategyValue}>Delta {iraDelta} — aggressive, trade freely</span>
                </div>
              </div>
              <div className={styles.strategyDetail}>
                <TrendingUp size={20} />
                <div>
                  <span className={styles.strategyLabel}>Taxable Puts</span>
                  <span className={styles.strategyValue}>Delta {taxableDelta} — conservative, trillion+ only</span>
                </div>
              </div>
              <div className={styles.strategyDetail}>
                <DollarSign size={20} />
                <div>
                  <span className={styles.strategyLabel}>Total Options Income</span>
                  <span className={styles.strategyValue}>Calls + Puts · {formatCurrency(portfolioTotals.weekly_income)}/wk</span>
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

            {/* Covered Calls Table */}
            <div className={styles.tableCard}>
              <div className={styles.tableSectionHeader}>
                <div className={styles.tableSectionTitle}>
                  <TrendingUp size={18} />
                  <h3 className={styles.tableTitle}>Covered Calls by Symbol</h3>
                </div>
                <span className={styles.tableSectionBadge}>{callSymbols.length} symbol{callSymbols.length !== 1 ? 's' : ''}</span>
              </div>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th rowSpan={2} className={styles.sortableHeader} onClick={() => handleOverviewSort('symbol')}>
                      Symbol {getSortIcon('symbol', overviewSort)}
                    </th>
                    <th rowSpan={2} className={styles.sortableHeader} onClick={() => handleOverviewSort('value')}>
                      Value {getSortIcon('value', overviewSort)}
                    </th>
                    <th rowSpan={2} className={styles.sortableHeader} onClick={() => handleOverviewSort('shares')}>
                      Shares {getSortIcon('shares', overviewSort)}
                    </th>
                    <th rowSpan={2} className={styles.sortableHeader} onClick={() => handleOverviewSort('price')}>
                      Price {getSortIcon('price', overviewSort)}
                    </th>
                    <th rowSpan={2} className={styles.sortableHeader} onClick={() => handleOverviewSort('options')}>
                      Options {getSortIcon('options', overviewSort)}
                    </th>
                    <th rowSpan={2} className={styles.signalHeader}>
                      Signal
                    </th>
                    <th colSpan={2} className={styles.tableGroupHeader}>
                      Weekly
                      {data?.income_periods?.weekly && <span className={styles.periodLabel}>{data.income_periods.weekly.label}</span>}
                    </th>
                    <th colSpan={2} className={styles.tableGroupHeader}>
                      Monthly
                      {data?.income_periods?.monthly && <span className={styles.periodLabel}>{data.income_periods.monthly.label}</span>}
                    </th>
                  </tr>
                  <tr>
                    <th className={`${styles.sortableHeader} ${styles.subHeader}`} onClick={() => handleOverviewSort('expectedWeekly')}>
                      Expected {getSortIcon('expectedWeekly', overviewSort)}
                    </th>
                    <th className={`${styles.sortableHeader} ${styles.subHeader}`} onClick={() => handleOverviewSort('actualWeekly')}>
                      Actual {getSortIcon('actualWeekly', overviewSort)}
                    </th>
                    <th className={`${styles.sortableHeader} ${styles.subHeader}`} onClick={() => handleOverviewSort('expectedMonthly')}>
                      Expected {getSortIcon('expectedMonthly', overviewSort)}
                    </th>
                    <th className={`${styles.sortableHeader} ${styles.subHeader}`} onClick={() => handleOverviewSort('actualMonthly')}>
                      Actual {getSortIcon('actualMonthly', overviewSort)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {callSymbols.map((symbol) => (
                    <tr
                      key={symbol.symbol}
                      className={symbol.utilization_status === 'none' ? styles.unsoldRow : ''}
                    >
                      <td>
                        <div className={styles.symbolCell}>
                          <strong
                            className={styles.clickableSymbol}
                            onClick={() => setTaSymbol(symbol.symbol)}
                          >
                            {symbol.symbol}
                          </strong>
                          <span className={styles.accountCount}>
                            {symbol.account_count} account{symbol.account_count > 1 ? 's' : ''}
                          </span>
                        </div>
                      </td>
                      <td>{formatCurrency(symbol.value)}</td>
                      <td>{symbol.shares.toLocaleString()}</td>
                      <td>{formatCurrency(symbol.price)}</td>
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
                      <td>
                        {optionSignals[symbol.symbol] ? (
                          <div
                            className={`${styles.signalBadge} ${styles[`signal_${optionSignals[symbol.symbol].action}`]} ${styles[`confidence_${optionSignals[symbol.symbol].confidence}`]}`}
                            title={optionSignals[symbol.symbol].reason}
                          >
                            <span className={styles.signalAction}>
                              {optionSignals[symbol.symbol].action === 'sell' ? 'SELL' :
                               optionSignals[symbol.symbol].action === 'buy_back' ? 'BUY BACK' : 'HOLD'}
                            </span>
                            <span className={styles.signalConfidence}>
                              {optionSignals[symbol.symbol].confidence}
                            </span>
                          </div>
                        ) : signalsLoading ? (
                          <RefreshCw size={14} className={styles.spinner} />
                        ) : (
                          <span>—</span>
                        )}
                      </td>
                      <td className={styles.expectedCol}>{formatCurrency(symbol.expectedWeekly)}</td>
                      <td className={`${styles.actualCol} ${symbol.actualWeekly >= symbol.expectedWeekly ? styles.incomeOnTarget : styles.incomeBelowTarget}`}>
                        {formatCurrency(symbol.actualWeekly)}
                      </td>
                      <td className={styles.expectedCol}>{formatCurrency(symbol.expectedMonthly)}</td>
                      <td className={`${styles.actualCol} ${symbol.actualMonthly >= symbol.expectedMonthly ? styles.incomeOnTarget : styles.incomeBelowTarget}`}>
                        {formatCurrency(symbol.actualMonthly)}
                      </td>
                    </tr>
                  ))}
                  <tr className={styles.totalRow}>
                    <td><strong>TOTAL</strong></td>
                    <td><strong>{formatCurrency(callSymbols.reduce((s, sym) => s + sym.value, 0))}</strong></td>
                    <td></td>
                    <td></td>
                    <td><strong>{portfolioTotals.total_options}</strong></td>
                    <td></td>
                    <td className={styles.expectedCol}>
                      <strong>{formatCurrency(callSymbols.reduce((s, sym) => s + sym.expectedWeekly, 0))}</strong>
                    </td>
                    <td className={styles.actualCol}>
                      <strong>{formatCurrency(callSymbols.reduce((s, sym) => s + sym.actualWeekly, 0))}</strong>
                    </td>
                    <td className={styles.expectedCol}>
                      <strong>{formatCurrency(callSymbols.reduce((s, sym) => s + sym.expectedMonthly, 0))}</strong>
                    </td>
                    <td className={styles.actualCol}>
                      <strong>{formatCurrency(callSymbols.reduce((s, sym) => s + sym.actualMonthly, 0))}</strong>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Cash-Secured Puts Table */}
            <div className={styles.tableCard}>
              <div className={styles.putsSectionHeader}>
                <div className={styles.tableSectionTitle}>
                  <TrendingDown size={18} />
                  <h3 className={styles.tableTitle}>Cash-Secured Puts by Symbol</h3>
                </div>
                <div className={styles.cashAvailableStat}>
                  <Wallet size={14} />
                  <span className={styles.cashAvailableLabel}>Cash Available</span>
                  <strong className={styles.cashAvailableValue}>
                    {formatCurrency(data.portfolio_summary.total_cash_for_puts ?? 0)}
                  </strong>
                </div>
              </div>

              {sortedPutSymbols.length === 0 ? (
                <div className={styles.putsEmptyState}>
                  <p>No put positions recorded yet. Sell a cash-secured put and upload a snapshot to see it here.</p>
                </div>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th className={styles.numericCol}>Value Locked</th>
                      <th className={styles.numericCol}>Shares</th>
                      <th className={styles.numericCol}>Strike</th>
                      <th className={styles.numericCol}>Stock Price</th>
                      <th className={styles.numericCol}>Options</th>
                      <th>Expiry</th>
                      <th>Assignment</th>
                      <th className={styles.actualCol}>
                        Weekly
                        {data?.income_periods?.weekly && <span className={styles.periodLabel}>{data.income_periods.weekly.label}</span>}
                      </th>
                      <th className={styles.actualCol}>
                        Monthly
                        {data?.income_periods?.monthly && <span className={styles.periodLabel}>{data.income_periods.monthly.label}</span>}
                      </th>
                      <th className={styles.actualCol}>
                        Yearly
                        {data?.income_periods?.yearly && <span className={styles.periodLabel}>{data.income_periods.yearly.label}</span>}
                      </th>
                      <th>Accounts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPutSymbols.map((put) => {
                      const strikeLabel = put.strikes.length === 0 ? '—'
                        : put.strikes.length === 1 ? `$${put.strikes[0].toLocaleString()}`
                        : put.strikes.map(s => `$${s}`).join(', ');
                      return (
                        <tr key={put.symbol}>
                          <td>
                            <div className={styles.symbolCell}>
                              <strong
                                className={styles.clickableSymbol}
                                onClick={() => setTaSymbol(put.symbol)}
                              >
                                {put.symbol}
                              </strong>
                              <span className={styles.accountCount}>
                                {put.account_count} account{put.account_count !== 1 ? 's' : ''}
                              </span>
                            </div>
                          </td>
                          <td className={styles.numericCol}>
                            {put.value_locked > 0 ? formatCurrency(put.value_locked) : '—'}
                          </td>
                          <td className={styles.numericCol}>
                            {put.shares_equivalent > 0 ? put.shares_equivalent.toLocaleString() : '—'}
                          </td>
                          <td className={styles.numericCol}>
                            <span className={styles.strikeBadge}>{strikeLabel}</span>
                          </td>
                          <td className={styles.numericCol}>
                            {put.current_price != null ? `$${put.current_price.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : '—'}
                          </td>
                          <td className={styles.numericCol}>
                            {put.total_contracts > 0 ? put.total_contracts : '—'}
                          </td>
                          <td>
                            {(() => {
                              const exp = getNearestExpiry(put);
                              if (!exp) return <span className={styles.accountCount}>—</span>;
                              const expDate = new Date(exp + 'T00:00:00');
                              const daysOut = Math.round((expDate.getTime() - Date.now()) / 86400000);
                              const label = expDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                              return (
                                <span className={daysOut <= 2 ? styles.expiringWarning : styles.expiryLabel}>
                                  {label} {daysOut >= 0 ? `(${daysOut}d)` : '(exp)'}
                                </span>
                              );
                            })()}
                          </td>
                          <td>
                            {(() => {
                              const stance = getAssignmentStance(put);
                              if (!stance) return <span className={styles.accountCount}>—</span>;
                              return (
                                <span className={
                                  stance.stance === 'good' ? styles.assignmentGood :
                                  stance.stance === 'neutral' ? styles.assignmentNeutral :
                                  styles.assignmentBad
                                }>
                                  {stance.label}
                                </span>
                              );
                            })()}
                          </td>
                          <td className={`${styles.actualCol} ${put.weekly_income > 0 ? styles.incomeOnTarget : styles.incomeBelowTarget}`}>
                            {formatCurrency(put.weekly_income)}
                          </td>
                          <td className={`${styles.actualCol} ${put.monthly_income > 0 ? styles.incomeOnTarget : styles.incomeBelowTarget}`}>
                            {formatCurrency(put.monthly_income)}
                          </td>
                          <td className={`${styles.actualCol} ${put.yearly_income > 0 ? styles.incomeOnTarget : styles.incomeBelowTarget}`}>
                            {formatCurrency(put.yearly_income)}
                          </td>
                          <td>
                            <span className={styles.accountCount}>{put.accounts.join(', ')}</span>
                          </td>
                        </tr>
                      );
                    })}
                    <tr className={styles.totalRow}>
                      <td><strong>TOTAL</strong></td>
                      <td className={styles.numericCol}>
                        <strong>{formatCurrency(sortedPutSymbols.reduce((s, p) => s + p.value_locked, 0))}</strong>
                      </td>
                      <td className={styles.numericCol}></td>
                      <td className={styles.numericCol}></td>
                      <td className={styles.numericCol}></td>
                      <td className={styles.numericCol}>
                        <strong>{sortedPutSymbols.reduce((s, p) => s + p.total_contracts, 0)}</strong>
                      </td>
                      <td></td>
                      <td></td>
                      <td className={styles.actualCol}>
                        <strong>{formatCurrency(sortedPutSymbols.reduce((s, p) => s + p.weekly_income, 0))}</strong>
                      </td>
                      <td className={styles.actualCol}>
                        <strong>{formatCurrency(sortedPutSymbols.reduce((s, p) => s + p.monthly_income, 0))}</strong>
                      </td>
                      <td className={styles.actualCol}>
                        <strong>{formatCurrency(sortedPutSymbols.reduce((s, p) => s + p.yearly_income, 0))}</strong>
                      </td>
                      <td></td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {/* Individual Account Views */}
        {!loading && !error && data && sortedAccounts.map((account) => {
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
                  <span className={styles.statValue}>{account.unsold_options ?? account.total_options}</span>
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
                {(() => {
                  const v6 = getV6DeltaTarget(account.account_type);
                  return (
                    <div className={`${styles.accountStat} ${v6.style === 'ira' ? styles.v6DeltaStatIra : styles.v6DeltaStatTaxable}`}>
                      <span className={styles.statLabel}>V6 Put Delta</span>
                      <span className={styles.statValue}>Δ{v6.delta}</span>
                      <span className={styles.statNote}>{v6.label} · {v6.style === 'ira' ? 'trade freely' : 'trillion+ only'}</span>
                    </div>
                  );
                })()}
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
                <HoldingsTable
                  rows={account.holdings.map(h => holdingToRow({ ...h, ...getHoldingIncome(h) }))}
                  columns={optionsAccountColumns}
                  defaultSortKey="options"
                />
              </div>

              {/* Account-specific Puts Table */}
              {(() => {
                const accountPuts = sortedPutSymbols
                  .map(put => {
                    const acctPositions = put.positions.filter(p => p.account === account.account_name);
                    if (acctPositions.length === 0) return null;
                    const totalContracts = acctPositions.reduce((s, p) => s + p.contracts, 0);
                    const valueLocked = acctPositions.reduce((s, p) => s + p.value_locked, 0);
                    return {
                      ...put,
                      positions: acctPositions,
                      total_contracts: totalContracts,
                      shares_equivalent: totalContracts * 100,
                      value_locked: valueLocked,
                      strikes: [...new Set(acctPositions.map(p => p.strike_price))].sort((a, b) => a - b),
                    };
                  })
                  .filter(Boolean) as typeof sortedPutSymbols;

                if (accountPuts.length === 0) return null;

                const v6 = getV6DeltaTarget(account.account_type);

                return (
                  <div className={styles.tableCard}>
                    <div className={styles.tableSectionHeader}>
                      <div className={styles.tableSectionTitle}>
                        <TrendingDown size={18} />
                        <h3 className={styles.tableTitle}>Cash-Secured Puts</h3>
                      </div>
                      <div className={styles.putsAccountMeta}>
                        <span className={v6.style === 'ira' ? styles.deltaChipIra : styles.deltaChipTaxable}>
                          Δ{v6.delta} target
                        </span>
                        <span className={styles.tableSectionBadge}>
                          {accountPuts.length} symbol{accountPuts.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                    </div>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th className={styles.numericCol}>Value Locked</th>
                          <th className={styles.numericCol}>Shares</th>
                          <th className={styles.numericCol}>Strike</th>
                          <th className={styles.numericCol}>Stock Price</th>
                          <th className={styles.numericCol}>Options</th>
                          <th>Expiry</th>
                          <th>Assignment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {accountPuts.map(put => {
                          const strikeLabel = put.strikes.length === 0 ? '—'
                            : put.strikes.length === 1 ? `$${put.strikes[0].toLocaleString()}`
                            : put.strikes.map(s => `$${s}`).join(', ');
                          return (
                            <tr key={put.symbol}>
                              <td>
                                <div className={styles.symbolCell}>
                                  <strong
                                    className={styles.clickableSymbol}
                                    onClick={() => setTaSymbol(put.symbol)}
                                  >
                                    {put.symbol}
                                  </strong>
                                </div>
                              </td>
                              <td className={styles.numericCol}>{formatCurrency(put.value_locked)}</td>
                              <td className={styles.numericCol}>{put.shares_equivalent.toLocaleString()}</td>
                              <td className={styles.numericCol}>
                                <span className={styles.strikeBadge}>{strikeLabel}</span>
                              </td>
                              <td className={styles.numericCol}>
                                {put.current_price != null
                                  ? `$${put.current_price.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
                                  : '—'}
                              </td>
                              <td className={styles.numericCol}>{put.total_contracts}</td>
                              <td>
                                {(() => {
                                  const exp = getNearestExpiry(put);
                                  if (!exp) return <span className={styles.accountCount}>—</span>;
                                  const expDate = new Date(exp + 'T00:00:00');
                                  const daysOut = Math.round((expDate.getTime() - Date.now()) / 86400000);
                                  const label = expDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                                  return (
                                    <span className={daysOut <= 2 ? styles.expiringWarning : styles.expiryLabel}>
                                      {label} {daysOut >= 0 ? `(${daysOut}d)` : '(exp)'}
                                    </span>
                                  );
                                })()}
                              </td>
                              <td>
                                {(() => {
                                  const stance = getAssignmentStance(put);
                                  if (!stance) return <span className={styles.accountCount}>—</span>;
                                  return (
                                    <span className={
                                      stance.stance === 'good' ? styles.assignmentGood :
                                      stance.stance === 'neutral' ? styles.assignmentNeutral :
                                      styles.assignmentBad
                                    }>
                                      {stance.label}
                                    </span>
                                  );
                                })()}
                              </td>
                            </tr>
                          );
                        })}
                        <tr className={styles.totalRow}>
                          <td><strong>TOTAL</strong></td>
                          <td className={styles.numericCol}>
                            <strong>{formatCurrency(accountPuts.reduce((s, p) => s + p.value_locked, 0))}</strong>
                          </td>
                          <td className={styles.numericCol}></td>
                          <td className={styles.numericCol}></td>
                          <td className={styles.numericCol}></td>
                          <td className={styles.numericCol}>
                            <strong>{accountPuts.reduce((s, p) => s + p.total_contracts, 0)}</strong>
                          </td>
                          <td></td>
                          <td></td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                );
              })()}
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

            {/* Put Opportunities Section */}
            <div className={styles.putOpportunitiesSection}>
              <div className={styles.putOpportunitiesHeader}>
                <div className={styles.putOpportunitiesTitle}>
                  <Target size={24} />
                  <div>
                    <h2>Put Entry Opportunities</h2>
                    <p>Stocks with favorable TA entry conditions (RSI oversold / lower Bollinger band)</p>
                  </div>
                </div>
                <div className={styles.putOpportunitiesActions}>
                  {putLastUpdated && (
                    <span className={styles.lastUpdated}>
                      Updated: {putLastUpdated.toLocaleTimeString()}
                    </span>
                  )}
                  <button
                    className={styles.refreshPricesButton}
                    onClick={() => fetchPutOpportunities(true)}
                    disabled={putLoading}
                    title="Recalculate from live TA data and options chains"
                  >
                    {putLoading ? (
                      <RefreshCw size={16} className={styles.spinning} />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    {putLoading ? 'Analyzing...' : 'Refresh'}
                  </button>
                </div>
              </div>

              {putOpportunities.length === 0 && !putLoading && (
                <div className={styles.emptyState}>
                  <Target size={48} />
                  <h3>No Put Opportunities Found</h3>
                  <p>No stocks currently meet the criteria (Score ≥ 80, Grade A).</p>
                  <p>Click below to analyze your portfolio stocks for put selling opportunities.</p>
                  <button onClick={() => fetchPutOpportunities(true)} className={styles.refreshButton}>
                    <RefreshCw size={16} />
                    Analyze Now
                  </button>
                </div>
              )}

              {putLoading && (
                <div className={styles.loadingState}>
                  <RefreshCw size={32} className={styles.spinning} />
                  <p>Analyzing portfolio stocks...</p>
                </div>
              )}

              {sortedPutOpportunities.length > 0 && (
                <div className={styles.putOpportunitiesTable}>
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Current</th>
                        <th>Strike</th>
                        <th>OTM%</th>
                        <th
                          className={styles.sortable}
                          onClick={() => {
                            if (putSortField === 'premium') setPutSortDesc(!putSortDesc);
                            else { setPutSortField('premium'); setPutSortDesc(true); }
                          }}
                        >
                          Premium {putSortField === 'premium' && (putSortDesc ? '↓' : '↑')}
                        </th>
                        <th>Grade</th>
                        <th
                          className={styles.sortable}
                          onClick={() => {
                            if (putSortField === 'score') setPutSortDesc(!putSortDesc);
                            else { setPutSortField('score'); setPutSortDesc(true); }
                          }}
                        >
                          Score {putSortField === 'score' && (putSortDesc ? '↓' : '↑')}
                        </th>
                        <th
                          className={styles.sortable}
                          onClick={() => {
                            if (putSortField === 'roi_pct') setPutSortDesc(!putSortDesc);
                            else { setPutSortField('roi_pct'); setPutSortDesc(true); }
                          }}
                        >
                          ROI% {putSortField === 'roi_pct' && (putSortDesc ? '↓' : '↑')}
                        </th>
                        <th
                          className={styles.sortable}
                          onClick={() => {
                            if (putSortField === 'capital_required') setPutSortDesc(!putSortDesc);
                            else { setPutSortField('capital_required'); setPutSortDesc(false); }
                          }}
                        >
                          Capital {putSortField === 'capital_required' && (putSortDesc ? '↓' : '↑')}
                        </th>
                        <th>RSI</th>
                        <th>BB%</th>
                        <th>Expiry</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPutOpportunities.map((opp, idx) => (
                        <tr
                          key={`${opp.symbol}-${idx}`}
                          className={styles.putRow}
                          title={getPutRationale(opp)}
                        >
                          <td className={styles.symbolCell}>
                            <div className={styles.symbolWithInfo}>
                              {opp.symbol}
                              <span className={styles.infoIcon} title={getPutRationale(opp)}>ⓘ</span>
                            </div>
                          </td>
                          <td>${opp.current_price?.toFixed(2)}</td>
                          <td>${opp.strike?.toFixed(0)}</td>
                          <td>{opp.otm_pct?.toFixed(1)}%</td>
                          <td className={styles.premiumCell}>${opp.premium?.toFixed(0)}</td>
                          <td>
                            <span
                              className={styles.gradeBadge}
                              style={{ backgroundColor: getGradeColor(opp.grade) }}
                            >
                              {opp.grade}
                            </span>
                          </td>
                          <td>{opp.score?.toFixed(0)}</td>
                          <td>{opp.roi_pct?.toFixed(2)}%</td>
                          <td>${(opp.capital_required || 0).toLocaleString()}</td>
                          <td>
                            <span className={opp.rsi < 40 ? styles.goodRsi : ''}>
                              {opp.rsi?.toFixed(0)}
                            </span>
                          </td>
                          <td>
                            <span className={opp.bb_position_pct < 35 ? styles.goodBb : ''}>
                              {opp.bb_position_pct?.toFixed(0)}%
                            </span>
                          </td>
                          <td>{opp.expiration ? new Date(opp.expiration).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className={styles.v6DeltaNote}>
                <strong>V6 Delta Targets:</strong> Strike shown here is for reference (conservative OTM). For actual trades: IRA accounts sell at delta ~{iraDelta} (much closer to ATM), taxable accounts at delta ~{taxableDelta}. Classify each stock as <em>runaway</em> (structural catalyst → roll at zero cost) or <em>oscillating</em> (sentiment → use RSI entry, expect mean reversion).
              </div>
              <div className={styles.putLegend}>
                <span><strong>Grade A+ (≥90):</strong> Strong TA entry signal</span>
                <span><strong>Grade A (≥80):</strong> Good TA entry signal</span>
                <span><strong>RSI {'<'} 40:</strong> Near oversold — good entry for oscillating stocks</span>
                <span><strong>BB% {'<'} 35:</strong> Lower Bollinger band — near support</span>
              </div>
            </div>

            {/* Acquisition Puts Section */}
            <div className={styles.acquisitionSection}>
              <div className={styles.acquisitionHeader}>
                <div className={styles.acquisitionTitle}>
                  <Wallet size={24} />
                  <div>
                    <h2>Acquisition Puts</h2>
                    <p>Stocks you want to buy - get paid while waiting for lower prices</p>
                  </div>
                </div>
                <div className={styles.acquisitionActions}>
                  <button
                    className={styles.refreshPricesButton}
                    onClick={fetchAcquisitionWatchlist}
                    disabled={acquisitionLoading}
                  >
                    {acquisitionLoading ? (
                      <RefreshCw size={16} className={styles.spinning} />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    Refresh
                  </button>
                  <button
                    className={styles.addPositionButton}
                    onClick={() => setShowAddAcquisition(!showAddAcquisition)}
                  >
                    <Plus size={16} />
                    Add Stock
                  </button>
                </div>
              </div>

              {/* Add Stock Form */}
              {showAddAcquisition && (
                <div className={styles.addAcquisitionForm}>
                  <div className={styles.formGrid}>
                    <div className={styles.formField}>
                      <label>Symbol</label>
                      <input
                        type="text"
                        placeholder="LLY"
                        value={newAcquisitionSymbol}
                        onChange={(e) => setNewAcquisitionSymbol(e.target.value.toUpperCase())}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label>Target Price (optional)</label>
                      <input
                        type="number"
                        placeholder="1050"
                        value={newAcquisitionTargetPrice}
                        onChange={(e) => setNewAcquisitionTargetPrice(e.target.value)}
                      />
                    </div>
                    <div className={styles.formField} style={{ gridColumn: 'span 2' }}>
                      <label>Notes (optional)</label>
                      <input
                        type="text"
                        placeholder="Why I want to own this stock..."
                        value={newAcquisitionNotes}
                        onChange={(e) => setNewAcquisitionNotes(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className={styles.formActions}>
                    <button className={styles.cancelButton} onClick={() => setShowAddAcquisition(false)}>
                      Cancel
                    </button>
                    <button
                      className={styles.submitButton}
                      onClick={addToAcquisitionWatchlist}
                      disabled={!newAcquisitionSymbol.trim()}
                    >
                      <Plus size={16} />
                      Add to Watchlist
                    </button>
                  </div>
                </div>
              )}

              {/* Watchlist Items */}
              {acquisitionWatchlist.length === 0 && !acquisitionLoading && (
                <div className={styles.emptyState}>
                  <Wallet size={48} />
                  <h3>No Stocks in Acquisition Watchlist</h3>
                  <p>Add stocks you want to buy at a lower price.</p>
                  <p>Sell puts to get paid while waiting!</p>
                </div>
              )}

              {acquisitionLoading && (
                <div className={styles.loadingState}>
                  <RefreshCw size={32} className={styles.spinning} />
                  <p>Loading acquisition targets...</p>
                </div>
              )}

              {acquisitionWatchlist.length > 0 && (
                <div className={styles.acquisitionList}>
                  {acquisitionWatchlist.map((item) => (
                    <div key={item.id} className={styles.acquisitionCard}>
                      <div className={styles.acquisitionCardHeader}>
                        <div className={styles.acquisitionSymbol}>
                          <span className={styles.symbolName}>{item.symbol}</span>
                          {item.current_price && (
                            <span className={styles.currentPrice}>${item.current_price.toFixed(2)}</span>
                          )}
                          {item.target_price && (
                            <span className={styles.targetPrice}>Target: ${item.target_price.toFixed(0)}</span>
                          )}
                        </div>
                        <button
                          className={styles.removeButton}
                          onClick={() => removeFromAcquisitionWatchlist(item.symbol)}
                          title="Remove from watchlist"
                        >
                          <XCircle size={18} />
                        </button>
                      </div>

                      {item.notes && (
                        <div className={styles.acquisitionNotes}>{item.notes}</div>
                      )}

                      {item.ta_summary && (
                        <div className={styles.taSummary}>
                          <span>RSI: {item.ta_summary.rsi.toFixed(0)} ({item.ta_summary.rsi_status})</span>
                          <span>BB: {item.ta_summary.bb_position_pct.toFixed(0)}%</span>
                          <span>Trend: {item.ta_summary.trend}</span>
                        </div>
                      )}

                      {item.put_options.length > 0 ? (
                        <div className={styles.putOptionsTable}>
                          <table>
                            <thead>
                              <tr>
                                <th>Strike</th>
                                <th>Premium</th>
                                <th>If Assigned</th>
                                <th>Discount</th>
                                <th>Prob OTM</th>
                                <th>Capital</th>
                              </tr>
                            </thead>
                            <tbody>
                              {item.put_options.map((opt, idx) => (
                                <tr key={idx}>
                                  <td>${opt.strike.toFixed(0)}</td>
                                  <td className={styles.premiumCell}>${opt.premium.toFixed(0)}</td>
                                  <td>${opt.effective_buy_price.toFixed(2)}</td>
                                  <td className={styles.discountCell}>{opt.discount_pct.toFixed(1)}%</td>
                                  <td>{opt.prob_otm}%</td>
                                  <td>${opt.capital_required.toLocaleString()}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className={styles.noPutOptions}>
                          No put options available. Click Refresh to load.
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <div className={styles.acquisitionLegend}>
                <span><strong>If Assigned:</strong> Effective buy price (strike - premium)</span>
                <span><strong>Discount:</strong> How much below current price you'd buy</span>
                <span><strong>Prob OTM:</strong> Chance put expires worthless (you keep premium)</span>
              </div>
            </div>

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
            
            {/* V6 Account-Type Delta Targets */}
            <div className={styles.v6DeltaSettings}>
              <div className={styles.v6DeltaSettingsTitle}>V6 Put Delta Targets (by Account Type)</div>
              <div className={styles.settingsRow}>
                <div className={styles.settingItem}>
                  <label>IRA Put Delta</label>
                  <div className={styles.inputGroup}>
                    <input
                      type="number"
                      value={iraDelta}
                      onChange={(e) => setIraDelta(parseInt(e.target.value) || 75)}
                      step="5"
                      min="50"
                      max="95"
                    />
                  </div>
                  <span className={styles.settingHint}>
                    Aggressive — no tax on assignment, trade freely. Default: 75.
                  </span>
                </div>
                <div className={styles.settingItem}>
                  <label>Taxable Put Delta</label>
                  <div className={styles.inputGroup}>
                    <input
                      type="number"
                      value={taxableDelta}
                      onChange={(e) => setTaxableDelta(parseInt(e.target.value) || 90)}
                      step="5"
                      min="70"
                      max="99"
                    />
                  </div>
                  <span className={styles.settingHint}>
                    Conservative — tax-sensitive, trillion+ stocks only. Default: 90.
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
              </div>
            </div>

            <div className={styles.settingsRow}>
              <div className={styles.settingItem}>
                <label>Income Projection Delta</label>
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
                  Used in backend income projection model (reference only)
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

            {/* Per-Symbol CALL Premiums */}
            <div className={styles.symbolPremiumsSection}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h4 className={styles.sectionTitle} style={{ margin: 0 }}>Weekly CALL Premium per Contract by Symbol</h4>
                <div style={{ display: 'flex', gap: '4px', fontSize: '12px' }}>
                  <span style={{ color: '#888', marginRight: '4px' }}>Sort:</span>
                  {(['netTotal', 'roc', 'premium', 'symbol'] as PremiumSortField[]).map((field) => (
                    <button
                      key={field}
                      onClick={() => setCallPremiumSort(field)}
                      style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        border: 'none',
                        background: callPremiumSort === field ? '#10b981' : '#333',
                        color: callPremiumSort === field ? '#000' : '#888',
                        cursor: 'pointer',
                        fontSize: '11px',
                      }}
                    >
                      {field === 'netTotal' ? 'Total $' : field === 'roc' ? 'ROC %' : field === 'premium' ? '$/wk' : 'A-Z'}
                    </button>
                  ))}
                </div>
              </div>
              <p className={styles.sectionHint}>
                NET premium (after buy-backs) for covered calls based on 4-week history.
                <strong> Changes update instantly in all calculations.</strong>
              </p>

              <div className={styles.symbolPremiumsGrid}>
                {[...data.symbols]
                  .map((symbol) => {
                    const currentPremium = symbolPremiums[symbol.symbol] ?? symbol.premium_per_contract ?? defaultPremium;
                    const avgCostPerShare = symbol.avg_cost_per_share || symbol.price || 0;
                    const callNetTotal = callNetTotals[symbol.symbol] || 0;
                    const capitalTiedUp = symbol.options * 100 * avgCostPerShare;
                    const monthlyReturnPct = capitalTiedUp > 0 ? (callNetTotal / capitalTiedUp) * 100 : 0;
                    return { ...symbol, currentPremium, callNetTotal, monthlyReturnPct };
                  })
                  .sort((a, b) => {
                    switch (callPremiumSort) {
                      case 'netTotal': return (b.callNetTotal || 0) - (a.callNetTotal || 0);
                      case 'roc': return (b.monthlyReturnPct || 0) - (a.monthlyReturnPct || 0);
                      case 'premium': return (b.currentPremium || 0) - (a.currentPremium || 0);
                      case 'symbol': return a.symbol.localeCompare(b.symbol);
                      default: return 0;
                    }
                  })
                  .map((symbol) => (
                    <div key={symbol.symbol} className={styles.symbolPremiumItem}>
                      <div className={styles.symbolInfo}>
                        <span className={styles.symbolName}>{symbol.symbol}</span>
                        <span className={styles.symbolOptions}>{symbol.options} options</span>
                      </div>
                      <div className={styles.premiumInput}>
                        <span>$</span>
                        <input
                          type="number"
                          value={symbol.currentPremium}
                          onChange={(e) => updateSymbolPremium(symbol.symbol, parseFloat(e.target.value) || 0)}
                          step="5"
                          min="0"
                        />
                        <span className={styles.perWeek}>/wk</span>
                      </div>
                      <div className={styles.projectedIncome}>
                        <span className={styles.weeklyProjection}>
                          {symbol.monthlyReturnPct.toFixed(1)}%/mo
                        </span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Per-Symbol PUT Premiums */}
            {Object.keys(putPremiums).length > 0 && (
              <div className={styles.symbolPremiumsSection}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h4 className={styles.sectionTitle} style={{ margin: 0 }}>Weekly PUT Premium per Contract by Symbol</h4>
                  <div style={{ display: 'flex', gap: '4px', fontSize: '12px' }}>
                    <span style={{ color: '#888', marginRight: '4px' }}>Sort:</span>
                    {(['netTotal', 'roc', 'premium', 'symbol'] as PremiumSortField[]).map((field) => (
                      <button
                        key={field}
                        onClick={() => setPutPremiumSort(field)}
                        style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          border: 'none',
                          background: putPremiumSort === field ? '#10b981' : '#333',
                          color: putPremiumSort === field ? '#000' : '#888',
                          cursor: 'pointer',
                          fontSize: '11px',
                        }}
                      >
                        {field === 'netTotal' ? 'Total $' : field === 'roc' ? 'ROC %' : field === 'premium' ? '$/wk' : 'A-Z'}
                      </button>
                    ))}
                  </div>
                </div>
                <p className={styles.sectionHint}>
                  NET premium (after buy-backs) for cash-secured puts based on 4-week history.
                  Put income is attributed to your CASH position.
                </p>

                <div className={styles.symbolPremiumsGrid}>
                  {Object.values(putPremiums)
                    .map((putData) => {
                      const premiumPerWeek = putData.put_premium_per_contract || 0;
                      const symbolData = data.symbols.find(s => s.symbol === putData.symbol);
                      const stockPrice = symbolData?.price || 0;
                      const putNetTotal = putData.put_net_total || 0;
                      const avgContractsHeld = Math.ceil((putData.put_contracts_sold || 0) / 4);
                      const capitalTiedUp = avgContractsHeld * 100 * stockPrice;
                      const monthlyReturnPct = capitalTiedUp > 0 ? (putNetTotal / capitalTiedUp) * 100 : 0;
                      return { ...putData, premiumPerWeek, putNetTotal, monthlyReturnPct, stockPrice };
                    })
                    .sort((a, b) => {
                      switch (putPremiumSort) {
                        case 'netTotal': return (b.putNetTotal || 0) - (a.putNetTotal || 0);
                        case 'roc': return (b.monthlyReturnPct || 0) - (a.monthlyReturnPct || 0);
                        case 'premium': return (b.premiumPerWeek || 0) - (a.premiumPerWeek || 0);
                        case 'symbol': return a.symbol.localeCompare(b.symbol);
                        default: return 0;
                      }
                    })
                    .map((putData) => (
                      <div key={putData.symbol} className={styles.symbolPremiumItem}>
                        <div className={styles.symbolInfo}>
                          <span className={styles.symbolName}>{putData.symbol}</span>
                          <span className={styles.symbolOptions}>
                            {putData.put_contracts_sold || 0} puts sold
                          </span>
                        </div>
                        <div className={styles.premiumInput}>
                          <span>$</span>
                          <input
                            type="number"
                            value={putData.premiumPerWeek?.toFixed(0) || 0}
                            readOnly
                            style={{ background: '#2a2a2a', cursor: 'not-allowed' }}
                          />
                          <span className={styles.perWeek}>/wk</span>
                        </div>
                        <div className={styles.projectedIncome}>
                          <span className={styles.weeklyProjection} style={{ color: '#10b981' }}>
                            {putData.monthlyReturnPct > 0 ? `${putData.monthlyReturnPct.toFixed(1)}%/mo` : '-'}
                          </span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            <div className={styles.deltaGuide}>
              <h4>V6 Delta Reference — Puts</h4>
              <table className={styles.deltaTable}>
                <thead>
                  <tr>
                    <th>Delta</th>
                    <th>Assignment Probability</th>
                    <th>Premium Level</th>
                    <th>Account Type</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={taxableDelta === 90 ? styles.selected : ''}>
                    <td>90</td>
                    <td>~90% chance of assignment</td>
                    <td>Very high — near ATM</td>
                    <td>Taxable (conservative)</td>
                  </tr>
                  <tr className={iraDelta === 80 ? styles.selected : ''}>
                    <td>80</td>
                    <td>~80% chance of assignment</td>
                    <td>High</td>
                    <td>IRA (aggressive range)</td>
                  </tr>
                  <tr className={iraDelta === 75 ? styles.selected : ''}>
                    <td>75</td>
                    <td>~75% chance of assignment</td>
                    <td>High</td>
                    <td>IRA (default)</td>
                  </tr>
                  <tr className={iraDelta === 70 ? styles.selected : ''}>
                    <td>70</td>
                    <td>~70% chance of assignment</td>
                    <td>Moderate-High</td>
                    <td>IRA (less aggressive)</td>
                  </tr>
                  <tr>
                    <td>10–20</td>
                    <td>10–20% chance of assignment</td>
                    <td>Low — far OTM</td>
                    <td>Old V3.4 strategy (not recommended)</td>
                  </tr>
                </tbody>
              </table>
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', marginTop: 'var(--space-2)' }}>
                V6 note: High delta = you WANT to be assigned (you believe in the stock). The premium is higher, and assignment is the plan, not the risk.
              </p>
            </div>

            <button className={styles.applyButton} onClick={applySettings}>
              <RefreshCw size={18} />
              Save & Sync with Server
            </button>
          </div>
        )}
      </div>

      <TechnicalAnalysisModal
        symbol={taSymbol || ''}
        isOpen={!!taSymbol}
        onClose={() => setTaSymbol(null)}
      />
    </div>
  );
}
