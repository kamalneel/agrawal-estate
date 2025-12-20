import { useState, useEffect, useMemo } from 'react';
import {
  Bell,
  RefreshCw,
  Filter,
  Calendar,
  AlertTriangle,
  CheckCircle,
  Clock,
  TrendingUp,
  Target,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  X,
  Eye,
  Check,
  XCircle,
} from 'lucide-react';
import TechnicalAnalysisModal from '../components/TechnicalAnalysisModal';
import styles from './Notifications.module.css';

interface Recommendation {
  id: string;
  type: string;
  category: string;
  priority: string;
  title: string;
  description: string;
  rationale: string;
  action: string;
  action_type: string;
  potential_income?: number;
  potential_risk?: string;
  symbol?: string;
  account_name?: string;
  context?: any;
  created_at?: string;
  expires_at?: string;
  status?: string;
  // Triple Witching fields
  is_triple_witching?: boolean;
  hide_roll_options?: boolean;
  show_close_guidance?: boolean;
  triple_witching_override?: {
    original_action?: string;
    new_action?: string;
    reason?: string;
    alternative?: string;
    itm_pct?: number;
    intrinsic_value?: number;
    close_cost_per_share?: number;
    close_cost_total?: number;
  };
  triple_witching_execution?: {
    is_triple_witching: boolean;
    current_window: string;
    window_quality: string;
    window_message: string;
    best_window: string;
    avoid_windows: string[];
    expected_slippage: string;
    slippage_vs_normal: string;
    fill_time: string;
    execution_strategy: string[];
    timing_rationale: string;
    close_guidance?: {
      start_price: string;
      max_price: string;
      adjustment_interval: string;
      expected_fill_location: string;
    };
  };
}

const getAuthHeaders = () => {
  const token = localStorage.getItem('agrawal_auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

interface DataFreshness {
  last_options_fetch: string | null;
  last_prices_fetch: string | null;
  cache_ttl_seconds: number;
  cache_ttl_display: string;
  is_market_hours: boolean;
  errors: {
    [key: string]: {
      time: string;
      message: string;
    };
  } | null;
  data_sources: {
    [key: string]: string;
  } | null;
}

export default function Notifications() {
  // State for recommendations
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<Date | null>(null);
  const [dataFreshness, setDataFreshness] = useState<DataFreshness | null>(null);
  
  // Filters
  const [filters, setFilters] = useState({
    priority: null as string | null,
    strategy: null as string | null,
    status: null as string | null,
    account: null as string | null,
    dateRange: 'all' as 'today' | 'week' | 'month' | 'all',
  });
  const [showFilters, setShowFilters] = useState(false);
  
  // Expanded recommendations
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  
  // Technical Analysis Modal
  const [taModalOpen, setTaModalOpen] = useState(false);
  const [taSymbol, setTaSymbol] = useState<string | null>(null);
  
  // Helper function to fetch history from DB
  // Always fetches all data (365 days) - filtering happens in frontend via filteredRecommendations
  const fetchHistoryFromDB = async (): Promise<Recommendation[]> => {
    try {
      const response = await fetch(
        `/api/v1/strategies/notifications/history?days_back=365&limit=500`,
        { headers: getAuthHeaders() }
      );
      
      if (response.ok) {
        const result = await response.json();
        return result.history || [];
      }
    } catch (err) {
      console.warn('Failed to fetch history from DB:', err);
    }
    return [];
  };

  // On mount: Show localStorage cache instantly, then fetch from DB for consistency
  useEffect(() => {
    // Step 1: Show cached data immediately for instant feedback
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const cached = localStorage.getItem('notifications_cache');
        if (cached) {
          const parsed = JSON.parse(cached);
          setRecommendations(parsed.recommendations || []);
          if (parsed.generated_at) {
            setGeneratedAt(new Date(parsed.generated_at));
          }
        }
      }
    } catch (e) {
      console.error('Error loading cached notifications:', e);
    }
    
    // Step 2: Fetch from DB for consistency across browsers (non-blocking)
    // ALWAYS update from DB - it's the single source of truth
    fetchHistoryFromDB().then(historyData => {
      setRecommendations(historyData);
      
      // Use the most recent created_at from the data as the "last refreshed" time
      // NOT the current time (that would be misleading on page refresh)
      if (historyData.length > 0) {
        const mostRecentCreatedAt = historyData.reduce((latest, rec) => {
          const recDate = new Date(rec.created_at);
          return recDate > latest ? recDate : latest;
        }, new Date(0));
        setGeneratedAt(mostRecentCreatedAt);
      }
      
      // Always update cache (even if empty) to stay in sync with DB
      try {
        localStorage.setItem('notifications_cache', JSON.stringify({
          recommendations: historyData,
          generated_at: historyData.length > 0 ? historyData[0].created_at : null,
          timestamp: new Date().toISOString()
        }));
      } catch (e) {
        console.warn('Failed to update cache:', e);
      }
    });
  }, []);
  
  const fetchRecommendations = async () => {
    setRefreshing(true);
    setError(null);
    
    try {
      // ============================================================
      // STEP 1: Show existing history from DB immediately
      // This gives instant feedback while we run the slow operations
      // ============================================================
      console.log('Step 1: Fetching existing history from DB...');
      const initialHistory = await fetchHistoryFromDB();
      if (initialHistory.length > 0) {
        setRecommendations(initialHistory);
        console.log(`Showing ${initialHistory.length} existing notifications from DB`);
      }
      
      // ============================================================
      // STEP 2: Refresh price data from Yahoo Finance
      // ============================================================
      console.log('Step 2: Refreshing price data from Yahoo Finance...');
      const priceRefreshController = new AbortController();
      const priceRefreshTimeout = setTimeout(() => {
        priceRefreshController.abort();
        console.warn('Price refresh timed out after 30 seconds - continuing with cached data');
      }, 30000);
      
      try {
        const refreshResponse = await fetch(
          `/api/v1/investments/holdings/refresh-prices`,
          {
            method: 'POST',
            headers: getAuthHeaders(),
            signal: priceRefreshController.signal
          }
        );
        clearTimeout(priceRefreshTimeout);
        if (refreshResponse.ok) {
          const refreshData = await refreshResponse.json();
          console.log('Price data refreshed:', refreshData);
        }
      } catch (refreshErr: any) {
        clearTimeout(priceRefreshTimeout);
        if (refreshErr.name === 'AbortError') {
          console.warn('Price refresh timed out (continuing with cached data)');
        } else {
          console.warn('Price refresh failed (continuing anyway):', refreshErr);
        }
      }
      
      // ============================================================
      // STEP 3: Run strategies + generate + save + send notifications
      // This is the slow operation - it saves new recs to DB
      // ============================================================
      console.log('Step 3: Running strategies and generating recommendations...');
      const timestamp = new Date().getTime();
      const liveController = new AbortController();
      const liveTimeout = setTimeout(() => {
        liveController.abort();
        console.warn('Live recommendations fetch timed out after 90 seconds');
      }, 90000);
      
      try {
        const liveResponse = await fetch(
          `/api/v1/strategies/options-selling/recommendations?default_premium=60&profit_threshold=0.80&send_notification=true&notification_priority=high&_t=${timestamp}`,
          { 
            headers: getAuthHeaders(),
            signal: liveController.signal,
            cache: 'no-store'
          }
        );
        
        clearTimeout(liveTimeout);
        
        if (liveResponse.ok) {
          const liveResult = await liveResponse.json();
          console.log(`Strategies generated ${liveResult.count || 0} recommendations, notifications sent:`, liveResult.notifications_sent);
          
          if (liveResult.generated_at) {
            setGeneratedAt(new Date(liveResult.generated_at));
          }
        } else {
          const errorText = await liveResponse.text();
          console.error(`Live recommendations API returned ${liveResponse.status}:`, errorText);
        }
      } catch (liveErr: any) {
        clearTimeout(liveTimeout);
        if (liveErr.name === 'AbortError') {
          console.warn('Live recommendations fetch timed out');
        } else {
          console.error('Live recommendations fetch failed:', liveErr);
        }
      }
      
      // ============================================================
      // STEP 4: Re-fetch history from DB (now includes new recs)
      // This is the single source of truth - same data for all browsers
      // ============================================================
      console.log('Step 4: Re-fetching complete history from DB...');
      const finalHistory = await fetchHistoryFromDB();
      
      // Use history as the single source of truth
      setRecommendations(finalHistory);
      // Set to NOW because user just clicked Refresh
      const refreshTime = new Date();
      setGeneratedAt(refreshTime);
      console.log(`Displaying ${finalHistory.length} total notifications from DB`);
      
      // Cache for next page load (instant display)
      try {
        localStorage.setItem('notifications_cache', JSON.stringify({
          recommendations: finalHistory,
          generated_at: refreshTime.toISOString(),
          timestamp: refreshTime.toISOString()
        }));
      } catch (e) {
        console.warn('Failed to cache notifications:', e);
      }
      
      // Fetch data freshness info
      try {
        const freshnessResponse = await fetch('/api/v1/strategies/data-freshness', {
          headers: getAuthHeaders()
        });
        if (freshnessResponse.ok) {
          const freshnessData = await freshnessResponse.json();
          setDataFreshness(freshnessData);
        }
      } catch (e) {
        console.warn('Failed to fetch data freshness:', e);
      }
      
    } catch (err: any) {
      console.error('Error fetching notifications:', err);
      setError(`Failed to load: ${err.message || 'Unknown error'}`);
    } finally {
      setRefreshing(false);
    }
  };
  
  const updateNotificationStatus = async (recordId: number, status: string, actionTaken?: string) => {
    try {
      const params = new URLSearchParams({ status });
      if (actionTaken) params.append('action_taken', actionTaken);
      
      const response = await fetch(
        `/api/v1/strategies/notifications/${recordId}/status?${params}`,
        { 
          method: 'PUT',
          headers: getAuthHeaders()
        }
      );
      
      if (response.ok) {
        // Update local state
        setRecommendations(prev => 
          prev.map(rec => 
            (rec as any).id === recordId 
              ? { ...rec, status } 
              : rec
          )
        );
      }
    } catch (err) {
      console.error('Error updating notification status:', err);
    }
  };
  
  const toggleExpanded = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };
  
  const openTechnicalAnalysis = (symbol: string) => {
    setTaSymbol(symbol);
    setTaModalOpen(true);
  };
  
  // Filter recommendations
  const filteredRecommendations = useMemo(() => {
    return recommendations.filter(rec => {
      if (filters.priority && rec.priority !== filters.priority) return false;
      if (filters.strategy && rec.type !== filters.strategy) return false;
      if (filters.status && rec.status !== filters.status) return false;
      if (filters.account && rec.account_name !== filters.account) return false;
      
      if (filters.dateRange !== 'all' && rec.created_at) {
        const recDate = new Date(rec.created_at);
        const now = new Date();
        
        if (filters.dateRange === 'today') {
          if (recDate.toDateString() !== now.toDateString()) return false;
        } else if (filters.dateRange === 'week') {
          const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
          if (recDate < weekAgo) return false;
        } else if (filters.dateRange === 'month') {
          const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
          if (recDate < monthAgo) return false;
        }
      }
      
      return true;
    });
  }, [recommendations, filters]);
  
  // Group recommendations by time, sorted by priority within each group
  // This matches the order shown in phone notifications
  const groupedRecommendations = useMemo(() => {
    const groups: Record<string, Recommendation[]> = {};
    const groupLatestTime: Record<string, Date> = {}; // Track most recent time in each group
    const priorityOrder: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 };
    
    filteredRecommendations.forEach(rec => {
      const actualDate = rec.created_at ? new Date(rec.created_at) : new Date();
      // Round to nearest 30 minutes for grouping purposes
      const groupDate = new Date(actualDate);
      const roundedMinutes = Math.floor(groupDate.getMinutes() / 30) * 30;
      groupDate.setMinutes(roundedMinutes, 0, 0);
      const groupKey = groupDate.toISOString();
      
      if (!groups[groupKey]) {
        groups[groupKey] = [];
        groupLatestTime[groupKey] = actualDate;
      } else {
        // Track the most recent time in this group
        if (actualDate > groupLatestTime[groupKey]) {
          groupLatestTime[groupKey] = actualDate;
        }
      }
      groups[groupKey].push(rec);
    });
    
    // Sort by time (most recent first)
    const sortedKeys = Object.keys(groups).sort((a, b) => 
      new Date(b).getTime() - new Date(a).getTime()
    );
    
    // Sort recommendations within each group by priority (matches phone notification order)
    // Use the most recent actual time for display, not the rounded group key
    return sortedKeys.map(groupKey => ({
      timeKey: groupLatestTime[groupKey].toISOString(), // Display the most recent time
      recommendations: groups[groupKey].sort((a, b) => {
        const priorityA = priorityOrder[a.priority] ?? 99;
        const priorityB = priorityOrder[b.priority] ?? 99;
        return priorityA - priorityB;
      })
    }));
  }, [filteredRecommendations]);
  
  // Get unique values for filters
  const uniqueStrategies = useMemo(() => {
    const types = new Set(recommendations.map(r => r.type));
    return Array.from(types);
  }, [recommendations]);
  
  const uniqueAccounts = useMemo(() => {
    const accounts = new Set(recommendations.map(r => r.account_name).filter(Boolean));
    return Array.from(accounts).sort();
  }, [recommendations]);
  
  const formatTimeHeader = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();
    
    const timeStr = date.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: '2-digit',
      hour12: true 
    });
    
    if (isToday) {
      return `Today at ${timeStr}`;
    } else if (isYesterday) {
      return `Yesterday at ${timeStr}`;
    } else {
      return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
      }) + ` at ${timeStr}`;
    }
  };
  
  const formatGroupSummary = (recs: Recommendation[]) => {
    const counts: { priority: string; count: number; color: string }[] = [];
    
    const urgent = recs.filter(r => r.priority === 'urgent').length;
    const high = recs.filter(r => r.priority === 'high').length;
    const medium = recs.filter(r => r.priority === 'medium').length;
    const low = recs.filter(r => r.priority === 'low').length;
    
    if (urgent > 0) counts.push({ priority: 'urgent', count: urgent, color: '#ef4444' });
    if (high > 0) counts.push({ priority: 'high', count: high, color: '#f97316' });
    if (medium > 0) counts.push({ priority: 'medium', count: medium, color: '#eab308' });
    if (low > 0) counts.push({ priority: 'low', count: low, color: '#22c55e' });
    
    return counts;
  };
  
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return '#ef4444';
      case 'high': return '#f97316';
      case 'medium': return '#eab308';
      case 'low': return '#22c55e';
      default: return '#6b7280';
    }
  };
  
  const getStrategyLabel = (type: string) => {
    const labels: Record<string, string> = {
      sell_unsold_contracts: 'New Call',
      early_roll_opportunity: 'Roll',
      adjust_premium_expectation: 'Adjust',
      diversify_holdings: 'Diversify',
      close_early_opportunity: 'Take Profit',
      roll_options: 'Roll',
      new_covered_call: 'New Call',
      bull_put_spread: 'Bull Put Portfolio', // Portfolio holdings
      mega_cap_bull_put: 'Bull Put Not In Portfolio', // Mega-cap stocks (not necessarily in portfolio)
    };
    return labels[type] || type.replace(/_/g, ' ');
  };
  
  const formatContextAsBullets = (rec: Recommendation) => {
    const bullets: string[] = [];
    const ctx = rec.context || {};
    
    // Only show the rationale (the "why") - skip redundant details that are in the title
    if (rec.rationale && rec.rationale !== rec.description && !rec.rationale.startsWith('**')) {
      bullets.push(rec.rationale);
    }
    
    // Only show additional risk factors if present
    if (ctx.risk_factors && Array.isArray(ctx.risk_factors) && ctx.risk_factors.length > 1) {
      bullets.push(`Risk factors: ${ctx.risk_factors.join(', ')}`);
    }
    
    // Only show days to expiry if it's urgent (2 days or less)
    if (ctx.days_to_expiry !== undefined && ctx.days_to_expiry <= 2) {
      bullets.push(`⚠️ Expires in ${ctx.days_to_expiry} day${ctx.days_to_expiry === 1 ? '' : 's'}`);
    }
    
    return bullets;
  };
  
  // Check if this is an ITM optimized roll with multiple options
  // Also check for hide_roll_options flag from Triple Witching override
  const hasRollOptions = (rec: Recommendation) => {
    const ctx = rec.context || {};
    // If Triple Witching override says to hide roll options, don't show them
    if (rec.hide_roll_options) {
      return false;
    }
    return ctx.scenario === 'C_itm_optimized' && ctx.roll_options && ctx.roll_options.length > 0;
  };
  
  // Check if this notification has Triple Witching execution guidance
  const hasTripleWitchingGuidance = (rec: Recommendation) => {
    return rec.triple_witching_execution && rec.is_triple_witching;
  };
  
  // Render Triple Witching execution guidance
  const renderTripleWitchingGuidance = (rec: Recommendation) => {
    const execution = rec.triple_witching_execution;
    const override = rec.triple_witching_override;
    
    if (!execution) return null;
    
    return (
      <div className={styles.tripleWitchingSection}>
        <h5>🔴 Triple Witching Execution Guidance</h5>
        
        {/* Current Window Status */}
        <div className={styles.windowStatus}>
          <span className={`${styles.windowBadge} ${
            execution.window_quality === 'GOOD' ? styles.goodWindow :
            execution.window_quality === 'FAIR' ? styles.fairWindow :
            styles.poorWindow
          }`}>
            {execution.window_message}
          </span>
        </div>
        
        {/* Time Windows */}
        <div className={styles.timeWindows}>
          <div className={styles.bestWindow}>
            <strong>Best Window:</strong> {execution.best_window}
          </div>
          <div className={styles.avoidWindows}>
            <strong>Avoid:</strong>
            <ul>
              {execution.avoid_windows?.map((window: string, i: number) => (
                <li key={i}>{window}</li>
              ))}
            </ul>
          </div>
        </div>
        
        {/* Execution Strategy */}
        <div className={styles.executionStrategy}>
          <strong>Execution Strategy:</strong>
          <ul>
            {execution.execution_strategy?.map((step: string, i: number) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
        </div>
        
        {/* Slippage Expectations */}
        <div className={styles.slippageWarning}>
          <strong>⚠️ Expected Slippage:</strong> {execution.expected_slippage}
          <span className={styles.slippageNote}>
            ({execution.slippage_vs_normal}, {execution.fill_time})
          </span>
        </div>
        
        {/* Close Cost (if CLOSE_DONT_ROLL) */}
        {override?.close_cost_per_share && (
          <div className={styles.closeCost}>
            <strong>Estimated Close Cost:</strong>
            <span className={styles.costAmount}>
              ${override.close_cost_per_share.toFixed(2)}/share
              {override.intrinsic_value && (
                <span className={styles.intrinsicNote}>
                  (${override.intrinsic_value.toFixed(2)} intrinsic value)
                </span>
              )}
            </span>
          </div>
        )}
        
        {/* Timing Rationale */}
        <div className={styles.timingRationale}>
          <em>{execution.timing_rationale}</em>
        </div>
      </div>
    );
  };
  
  // Render ITM roll options table
  const renderRollOptionsTable = (rec: Recommendation) => {
    const ctx = rec.context || {};
    const rollOptions = ctx.roll_options || [];
    const buyBackCost = ctx.buy_back_cost || 0;
    const buyBackTotal = ctx.buy_back_total || 0;
    const recommendedOption = ctx.recommended_option || 'Moderate';
    const techSignals = ctx.technical_signals || {};
    
    return (
      <div className={styles.rollOptionsSection}>
        <div className={styles.costSummary}>
          <h5>Cost to Buy Back Current Position</h5>
          <div className={styles.costDetails}>
            <span className={styles.costPerShare}>${buyBackCost.toFixed(2)}/share</span>
            <span className={styles.costTotal}>${buyBackTotal.toLocaleString()} total</span>
          </div>
        </div>
        
        <div className={styles.rollOptionsTable}>
          <h5>Roll Options Comparison</h5>
          <table>
            <thead>
              <tr>
                <th>Option</th>
                <th>Expiration</th>
                <th>Strike</th>
                <th>Net Cost</th>
                <th>Prob OTM</th>
              </tr>
            </thead>
            <tbody>
              {rollOptions.map((opt: any) => (
                <tr 
                  key={opt.label}
                  className={opt.label === recommendedOption ? styles.recommendedRow : ''}
                >
                  <td>
                    <span className={`${styles.optionLabel} ${styles[opt.label.toLowerCase()]}`}>
                      {opt.label}
                      {opt.label === recommendedOption && <span className={styles.recBadge}>★</span>}
                    </span>
                  </td>
                  <td>{opt.expiration_display} ({opt.weeks_out}w)</td>
                  <td>${opt.strike.toFixed(0)}</td>
                  <td className={opt.net_cost < 0 ? styles.creditCell : styles.debitCell}>
                    {opt.net_cost < 0 
                      ? `+$${Math.abs(opt.net_cost).toFixed(2)} credit` 
                      : opt.net_cost === 0 
                        ? 'Even'
                        : `-$${opt.net_cost.toFixed(2)} debit`
                    }
                    <span className={styles.totalCost}>
                      ({opt.net_cost < 0 ? '+' : '-'}${Math.abs(opt.net_cost_total).toLocaleString()})
                    </span>
                  </td>
                  <td>{opt.probability_otm.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {techSignals.ta_recommendation && (
          <div className={styles.taSignal}>
            <h5>Technical Analysis Signal</h5>
            <p>{techSignals.ta_recommendation}</p>
            <div className={styles.taDetails}>
              {techSignals.rsi && <span>RSI: {techSignals.rsi} ({techSignals.rsi_signal})</span>}
              {techSignals.weekly_volatility_pct && <span>Weekly Vol: {techSignals.weekly_volatility_pct}%</span>}
              {techSignals.trend && <span>Trend: {techSignals.trend}</span>}
            </div>
          </div>
        )}
      </div>
    );
  };
  
  const clearFilters = () => {
    setFilters({
      priority: null,
      strategy: null,
      status: null,
      account: null,
      dateRange: 'all',
    });
  };
  
  const hasActiveFilters = filters.priority || filters.strategy || filters.status || filters.account || filters.dateRange !== 'all';

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Bell size={28} />
          </div>
          <div className={styles.headerText}>
            <h1>Notifications</h1>
            <p>Strategy recommendations and alerts across your portfolio</p>
          </div>
        </div>
        
        <div className={styles.headerActions}>
          <div className={styles.freshnessInfo}>
            {generatedAt ? (
              <span className={`${styles.lastUpdated} ${
                // Mark as stale if more than 1 hour old
                (new Date().getTime() - generatedAt.getTime() > 60 * 60 * 1000) ? styles.stale : ''
              }`}>
                <Clock size={14} />
                Last refreshed: {(() => {
                  const now = new Date();
                  const diffMs = now.getTime() - generatedAt.getTime();
                  const diffMins = Math.floor(diffMs / 60000);
                  const diffHours = Math.floor(diffMs / 3600000);
                  const diffDays = Math.floor(diffMs / 86400000);
                  
                  if (diffMins < 1) return 'Just now';
                  if (diffMins < 60) return `${diffMins}m ago`;
                  if (diffHours < 24) return `${diffHours}h ago`;
                  return `${diffDays}d ago`;
                })()}
                {' · '}
                {generatedAt.toLocaleString('en-US', { 
                  month: 'short', 
                  day: 'numeric',
                  hour: 'numeric', 
                  minute: '2-digit',
                  hour12: true
                })}
              </span>
            ) : (
              <span className={`${styles.lastUpdated} ${styles.stale}`}>
                <Clock size={14} />
                Never refreshed - click Refresh to load
              </span>
            )}
            <div className={styles.statusRow}>
              {dataFreshness && (
                <span 
                  className={styles.cacheInfo} 
                  title={`Data cached for ${dataFreshness.cache_ttl_display}. ${dataFreshness.is_market_hours ? 'Market is open.' : 'Market is closed.'}`}
                >
                  {dataFreshness.is_market_hours ? '🟢' : '🔴'} Cache: {dataFreshness.cache_ttl_display}
                </span>
              )}
              {dataFreshness?.data_sources?.options && (
                <span 
                  className={`${styles.dataSource} ${dataFreshness.data_sources.options === 'nasdaq' ? styles.fallback : ''}`}
                  title={dataFreshness.data_sources.options === 'nasdaq' 
                    ? 'Using NASDAQ API as backup (Yahoo Finance rate-limited)' 
                    : 'Using Yahoo Finance API'}
                >
                  {dataFreshness.data_sources.options === 'nasdaq' ? '📊 NASDAQ (backup)' : '📈 Yahoo'}
                </span>
              )}
            </div>
            {/* Only show error if fallback also failed (no data source available) */}
            {dataFreshness?.errors && 
             Object.keys(dataFreshness.errors).length > 0 && 
             !dataFreshness.data_sources?.options && (
              <div className={styles.apiErrorBanner}>
                ⚠️ {Object.values(dataFreshness.errors)[0]?.message || 'Data fetch issue'}
              </div>
            )}
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`${styles.filterToggle} ${hasActiveFilters ? styles.hasFilters : ''}`}
          >
            <Filter size={18} />
            Filters
            {hasActiveFilters && <span className={styles.filterBadge}>{
              [filters.priority, filters.strategy, filters.status, filters.account, filters.dateRange !== 'all' ? 1 : null].filter(Boolean).length
            }</span>}
          </button>
          <button 
            onClick={fetchRecommendations}
            className={styles.refreshButton}
            disabled={refreshing}
          >
            <RefreshCw size={18} className={refreshing ? styles.spinning : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </header>
      
      {/* Filters Panel */}
      {showFilters && (
        <div className={styles.filtersPanel}>
          <div className={styles.filterGroup}>
            <label>Priority</label>
            <select 
              value={filters.priority || ''}
              onChange={(e) => setFilters({...filters, priority: e.target.value || null})}
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          
          <div className={styles.filterGroup}>
            <label>Strategy Type</label>
            <select 
              value={filters.strategy || ''}
              onChange={(e) => setFilters({...filters, strategy: e.target.value || null})}
            >
              <option value="">All Strategies</option>
              {uniqueStrategies.map(type => (
                <option key={type} value={type}>{getStrategyLabel(type)}</option>
              ))}
            </select>
          </div>
          
          <div className={styles.filterGroup}>
            <label>Time Period</label>
            <select 
              value={filters.dateRange}
              onChange={(e) => setFilters({...filters, dateRange: e.target.value as any})}
            >
              <option value="all">All Time</option>
              <option value="today">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
            </select>
          </div>
          
          <div className={styles.filterGroup}>
            <label>Status</label>
            <select 
              value={filters.status || ''}
              onChange={(e) => setFilters({...filters, status: e.target.value || null})}
            >
              <option value="">All Status</option>
              <option value="new">New</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="acted">Acted Upon</option>
              <option value="dismissed">Dismissed</option>
            </select>
          </div>
          
          <div className={styles.filterGroup}>
            <label>Account</label>
            <select 
              value={filters.account || ''}
              onChange={(e) => setFilters({...filters, account: e.target.value || null})}
            >
              <option value="">All Accounts</option>
              {uniqueAccounts.map(account => (
                <option key={account} value={account}>{account}</option>
              ))}
            </select>
          </div>
          
          {hasActiveFilters && (
            <button onClick={clearFilters} className={styles.clearFilters}>
              <X size={14} />
              Clear Filters
            </button>
          )}
        </div>
      )}
      
      {/* Error Banner */}
      {error && (
        <div className={styles.errorBanner}>
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button onClick={() => setError(null)} className={styles.dismissError}>×</button>
        </div>
      )}
      
      {/* Main Content */}
      <div className={styles.content}>
        {groupedRecommendations.length === 0 ? (
          <div className={styles.emptyState}>
            <Bell size={48} />
            <h3>No notifications</h3>
            <p>
              {hasActiveFilters 
                ? 'No notifications match your current filters. Try adjusting or clearing filters.'
                : 'Recommendations will appear here when strategies identify opportunities.'}
            </p>
            {hasActiveFilters && (
              <button onClick={clearFilters} className={styles.clearFiltersBtn}>
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <div className={styles.timeline}>
            {groupedRecommendations.map(group => (
              <div key={group.timeKey} className={styles.timeGroup}>
                <div className={styles.timeHeader}>
                  <Calendar size={14} />
                  <span>{formatTimeHeader(group.timeKey)}</span>
                  <div className={styles.groupSummary}>
                    <span className={styles.groupCount}>
                      {group.recommendations.length} notification{group.recommendations.length !== 1 ? 's' : ''}
                    </span>
                    {formatGroupSummary(group.recommendations).length > 0 && (
                      <span className={styles.priorityBreakdown}>
                        {formatGroupSummary(group.recommendations).map((item, idx) => (
                          <span key={item.priority} className={styles.priorityChip} style={{ color: item.color }}>
                            {idx > 0 && ', '}
                            {item.count} {item.priority}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className={styles.notificationsList}>
                  {group.recommendations.map(rec => (
                    <div 
                      key={rec.id} 
                      className={`${styles.notificationCard} ${expandedIds.has(rec.id) ? styles.expanded : ''} ${rec.status === 'acted' ? styles.acted : ''} ${rec.status === 'dismissed' ? styles.dismissed : ''}`}
                    >
                      <div 
                        className={styles.notificationHeader}
                        onClick={() => toggleExpanded(rec.id)}
                      >
                        <div 
                          className={styles.priorityIndicator}
                          style={{ backgroundColor: getPriorityColor(rec.priority) }}
                        />
                        
                        <div className={styles.notificationMain}>
                          <div className={styles.notificationMeta}>
                            {rec.account_name && <span className={styles.accountBadge}>{rec.account_name}</span>}
                            {rec.symbol && <span className={styles.symbolBadge}>{rec.symbol}</span>}
                            <span className={styles.strategyBadge}>{getStrategyLabel(rec.type)}</span>
                          </div>
                          <h4 className={styles.notificationTitle}>{rec.title}</h4>
                          <p className={styles.notificationDescription}>{rec.description}</p>
                        </div>
                        
                        <div className={styles.notificationActions}>
                          {rec.potential_income && rec.potential_income > 0 && (
                            <span className={styles.incomeTag}>
                              <TrendingUp size={12} />
                              ${rec.potential_income.toLocaleString()}/yr
                            </span>
                          )}
                          <span className={styles.expandIcon}>
                            {expandedIds.has(rec.id) ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                          </span>
                        </div>
                      </div>
                      
                      {expandedIds.has(rec.id) && (
                        <div className={styles.notificationDetails}>
                          <div className={styles.actionSection}>
                            <h5><Target size={14} /> Recommended Action</h5>
                            <p className={styles.actionText}>{rec.action}</p>
                          </div>
                          
                          {/* Triple Witching Execution Guidance */}
                          {hasTripleWitchingGuidance(rec) && renderTripleWitchingGuidance(rec)}
                          
                          {/* Special ITM Roll Options Table */}
                          {hasRollOptions(rec) && renderRollOptionsTable(rec)}
                          
                          {/* Standard bullet points (skip if we showed roll options) */}
                          {!hasRollOptions(rec) && formatContextAsBullets(rec).length > 0 && (
                            <div className={styles.rationaleSection}>
                              <h5><AlertTriangle size={14} /> Analysis</h5>
                              <ul className={styles.bulletList}>
                                {formatContextAsBullets(rec).map((bullet, i) => (
                                  <li key={i}>{bullet}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          
                          {/* Strike data source indicator */}
                          {rec.context?.strike_source && (
                            <div className={styles.dataSourceInfo}>
                              {rec.context.strike_source === 'options_chain' ? (
                                <span className={styles.liveSource} title="Strike calculated from live options chain delta">
                                  📈 Live Delta
                                </span>
                              ) : rec.context.strike_source === 'fallback_estimate' ? (
                                <span className={styles.fallbackSource} title="Strike estimated from volatility model (options chain unavailable)">
                                  📊 Estimated
                                </span>
                              ) : (
                                <span className={styles.fallbackSource} title="Fallback calculation">
                                  ⚠️ Fallback
                                </span>
                              )}
                            </div>
                          )}
                          
                          <div className={styles.detailActions}>
                            {rec.symbol && (
                              <button 
                                className={styles.taButton}
                                onClick={() => openTechnicalAnalysis(rec.symbol!)}
                              >
                                <Eye size={14} />
                                View Technical Analysis
                              </button>
                            )}
                            {rec.status !== 'acted' && (
                              <button 
                                className={styles.actedButton}
                                onClick={() => updateNotificationStatus((rec as any).id, 'acted')}
                              >
                                <Check size={14} />
                                Mark as Acted
                              </button>
                            )}
                            {rec.status !== 'dismissed' && (
                              <button 
                                className={styles.dismissButton}
                                onClick={() => updateNotificationStatus((rec as any).id, 'dismissed')}
                              >
                                <XCircle size={14} />
                                Dismiss
                              </button>
                            )}
                            {rec.status === 'acted' && (
                              <span className={styles.statusBadge} style={{color: '#10b981'}}>
                                <CheckCircle size={14} /> Acted Upon
                              </span>
                            )}
                            {rec.status === 'dismissed' && (
                              <span className={styles.statusBadge} style={{color: '#6b7280'}}>
                                <XCircle size={14} /> Dismissed
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Technical Analysis Modal */}
      {taSymbol && (
        <TechnicalAnalysisModal
          symbol={taSymbol}
          isOpen={taModalOpen}
          onClose={() => {
            setTaModalOpen(false);
            setTaSymbol(null);
          }}
        />
      )}
    </div>
  );
}

