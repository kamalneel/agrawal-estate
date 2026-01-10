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
  DollarSign,
  MoreVertical,
  MessageSquare,
  ThumbsDown,
  BarChart3,
  Lightbulb,
  History,
} from 'lucide-react';
import TechnicalAnalysisModal from '../components/TechnicalAnalysisModal';
import styles from './Notifications.module.css';

// Account ordering - consistent with Income, Investments, and other pages
// Order: Neel's accounts first, then Jaya's, then others
const ACCOUNT_ORDER: Record<string, number> = {
  "Neel's Brokerage": 1,
  "Neel's Retirement": 2,
  "Neel's Roth IRA": 3,
  "Jaya's Brokerage": 4,
  "Jaya's IRA": 5,
  "Jaya's Roth IRA": 6,
  "Alisha's Brokerage": 7,
  "Agrawal Family HSA": 8,
  "Other": 99,  // Catch-all for unknown accounts
};

const getAccountSortOrder = (accountName: string): number => {
  return ACCOUNT_ORDER[accountName] ?? 50;  // Unknown accounts go in the middle
};

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
  // V2 Snapshot fields
  snapshot_number?: number;
  total_snapshots?: number;
  action_changed?: boolean;
  target_changed?: boolean;
  priority_changed?: boolean;
  notification_mode?: 'verbose' | 'smart';
  source_strike?: number;
  source_expiration?: string;
  target_strike?: number;
  target_expiration?: string;
  stock_price?: number;
  profit_pct?: number;
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
  // V3.4: Enhanced explanation fields
  ta_summary?: {
    current_price: number;
    strike_price: number;
    option_type: string;
    is_itm: boolean;
    itm_pct?: number;
    otm_pct?: number;
    days_to_expiry: number;
    bollinger: {
      upper: number;
      middle: number;
      lower: number;
      position_pct: number;
      position_desc: string;
    };
    rsi: {
      value: number;
      status: string;
    };
    support?: number;
    resistance?: number;
    ma_50?: number;
    ma_200?: number;
  };
  decision_rationale?: string;
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

interface FeedbackItem {
  id: number;
  recommendation_id: string;
  source: string;
  raw_feedback: string;
  reason_code: string | null;
  reason_detail: string | null;
  threshold_hint: number | null;
  symbol: string | null;
  account_name: string | null;
  sentiment: string | null;
  actionable_insight: string | null;
  created_at: string;
}

interface FeedbackInsights {
  period_days: number;
  total_feedback: number;
  patterns: {
    type: string;
    reason_code?: string;
    count?: number;
    percentage?: number;
    description?: string;
    average_mentioned?: number;
    symbol?: string;
    skip_count?: number;
  }[];
  suggestions: {
    finding: string;
    suggestion: string;
    config_key: string;
    suggested_value: any;
  }[];
  generated_at: string;
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
  
  // Notification Mode: 'verbose' (all snapshots) or 'smart' (changes only)
  // Matches mobile (Telegram) which also has these two modes
  const [notificationMode, setNotificationMode] = useState<'verbose' | 'smart'>('verbose');
  
  // Expanded recommendations
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  
  // Technical Analysis Modal
  const [taModalOpen, setTaModalOpen] = useState(false);
  const [taSymbol, setTaSymbol] = useState<string | null>(null);
  
  // Feedback Modal
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false);
  const [feedbackRecId, setFeedbackRecId] = useState<string | null>(null);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  
  // Tab state
  const [activeTab, setActiveTab] = useState<'recommendations' | 'feedback'>('recommendations');
  
  // Feedback History state
  const [feedbackHistory, setFeedbackHistory] = useState<FeedbackItem[]>([]);
  const [feedbackInsights, setFeedbackInsights] = useState<FeedbackInsights | null>(null);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [telegramPolling, setTelegramPolling] = useState(false);
  const [telegramPollResult, setTelegramPollResult] = useState<string | null>(null);
  
  // Helper function to fetch history from DB
  // Fetches notification HISTORY - shows all past notifications like Telegram chat history
  // Uses /history endpoint to include resolved recommendations, not just active ones
  const fetchHistoryFromDB = async (mode?: 'verbose' | 'smart'): Promise<Recommendation[]> => {
    try {
      const effectiveMode = mode || 'verbose';
      // Use /history endpoint to get ALL past notifications (like Telegram chat history)
      // This includes resolved recommendations, not just active ones
      const response = await fetch(
        `/api/v1/strategies/notifications/v2/history?mode=${effectiveMode}&days_back=7&limit=200`,
        { headers: getAuthHeaders() }
      );
      
      if (response.ok) {
        const result = await response.json();
        const history = result.history || [];
        console.log(`[Notifications] V2 history API returned ${history.length} notifications (${effectiveMode} mode, last 7 days)`);
        return history;
      } else {
        const errorText = await response.text();
        console.error(`[Notifications] V2 history API error ${response.status}: ${errorText}`);
        throw new Error(`API returned ${response.status}: ${errorText}`);
      }
    } catch (err) {
      console.error('[Notifications] Failed to fetch history from DB:', err);
      throw err; // Re-throw so caller can handle it
    }
  };
  
  // Fetch feedback history
  const fetchFeedbackHistory = async () => {
    setFeedbackLoading(true);
    try {
      const [historyRes, insightsRes] = await Promise.all([
        fetch('/api/v1/strategies/feedback/history?days_back=90&limit=100', {
          headers: getAuthHeaders()
        }),
        fetch('/api/v1/strategies/feedback/insights?days_back=30&min_occurrences=2', {
          headers: getAuthHeaders()
        })
      ]);
      
      if (historyRes.ok) {
        const historyData = await historyRes.json();
        setFeedbackHistory(historyData.feedback || []);
      }
      
      if (insightsRes.ok) {
        const insightsData = await insightsRes.json();
        setFeedbackInsights(insightsData);
      }
    } catch (err) {
      console.error('Failed to fetch feedback:', err);
    } finally {
      setFeedbackLoading(false);
    }
  };
  
  // Poll Telegram for replies
  const pollTelegramReplies = async () => {
    setTelegramPolling(true);
    setTelegramPollResult(null);
    try {
      const response = await fetch('/api/v1/strategies/telegram/poll-replies', {
        method: 'POST',
        headers: getAuthHeaders()
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.feedback_saved > 0) {
          setTelegramPollResult(`✅ Found ${result.feedback_saved} new Telegram replies!`);
          // Refresh the feedback list
          fetchFeedbackHistory();
        } else if (result.status === 'no_updates') {
          setTelegramPollResult('No new Telegram replies');
        } else {
          setTelegramPollResult(`Checked ${result.updates_received || 0} updates`);
        }
      } else {
        setTelegramPollResult('Failed to poll Telegram');
      }
    } catch (err) {
      console.error('Failed to poll Telegram:', err);
      setTelegramPollResult('Error polling Telegram');
    } finally {
      setTelegramPolling(false);
      // Clear message after 5 seconds
      setTimeout(() => setTelegramPollResult(null), 5000);
    }
  };
  
  // Load feedback when tab changes
  useEffect(() => {
    if (activeTab === 'feedback' && feedbackHistory.length === 0) {
      fetchFeedbackHistory();
    }
  }, [activeTab]);

  // On mount: Show localStorage cache instantly, then fetch from DB for consistency
  useEffect(() => {
    // Step 1: Show cached data immediately for instant feedback
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const cached = localStorage.getItem('notifications_cache');
        if (cached) {
          const parsed = JSON.parse(cached);
          const cachedRecs = parsed.recommendations || [];
          setRecommendations(cachedRecs);
          
          // Use the most recent notification's created_at from cached data
          // This will be overwritten by DB fetch, but shows something meaningful immediately
          if (cachedRecs.length > 0) {
            const mostRecentCreatedAt = cachedRecs.reduce((latest: Date, rec: Recommendation) => {
              if (!rec.created_at) return latest;
              const recDate = new Date(rec.created_at);
              return recDate > latest ? recDate : latest;
            }, new Date(0));
            setGeneratedAt(mostRecentCreatedAt);
            console.log(`[Notifications] Using cached data, most recent: ${mostRecentCreatedAt.toISOString()}`);
          }
        }
      }
    } catch (e) {
      console.error('Error loading cached notifications:', e);
    }
    
    // Step 2: Fetch from DB for consistency across browsers (non-blocking)
    // ALWAYS update from DB - it's the single source of truth
    fetchHistoryFromDB(notificationMode)
      .then(historyData => {
        console.log(`[Notifications] Fetched ${historyData.length} notifications from DB on page load`);
        
        // Compare with cached data to see if we got newer notifications
        try {
          const cached = localStorage.getItem('notifications_cache');
          if (cached) {
            const parsed = JSON.parse(cached);
            const cachedRecs = parsed.recommendations || [];
            const cachedCount = cachedRecs.length;
            
            // Find the most recent timestamp in both cache and DB (not just first item)
            const cachedLatest = cachedRecs.reduce((latest: Date | null, rec: Recommendation) => {
              if (!rec.created_at) return latest;
              const recDate = new Date(rec.created_at);
              return !latest || recDate > latest ? recDate : latest;
            }, null as Date | null);
            
            const dbLatest = historyData.reduce((latest: Date | null, rec: Recommendation) => {
              if (!rec.created_at) return latest;
              const recDate = new Date(rec.created_at);
              return !latest || recDate > latest ? recDate : latest;
            }, null as Date | null);
            
            console.log(`[Notifications] Cache had ${cachedCount} notifications, DB has ${historyData.length}`);
            if (cachedLatest && dbLatest) {
              if (dbLatest > cachedLatest) {
                console.log(`[Notifications] ✅ DB has newer data! Cache latest: ${cachedLatest.toISOString()}, DB latest: ${dbLatest.toISOString()}`);
              } else if (cachedLatest > dbLatest) {
                console.log(`[Notifications] ⚠️ Cache is newer than DB! Cache: ${cachedLatest.toISOString()}, DB: ${dbLatest.toISOString()}`);
              } else {
                console.log(`[Notifications] ✅ Cache and DB are in sync (same latest timestamp: ${cachedLatest.toISOString()})`);
              }
            } else {
              console.log(`[Notifications] Could not compare timestamps (cachedLatest: ${cachedLatest?.toISOString()}, dbLatest: ${dbLatest?.toISOString()})`);
            }
          }
        } catch (e) {
          console.warn('[Notifications] Error comparing cache:', e);
        }
        
        // Update state with fresh data from DB
        setRecommendations(historyData);
        
        // Always use the most recent notification's created_at to show data freshness
        // This reflects when the backend last generated recommendations (scheduled scans)
        // NOT when the user last clicked Refresh
        if (historyData.length > 0) {
          const mostRecentCreatedAt = historyData.reduce((latest, rec) => {
            if (!rec.created_at) return latest;
            const recDate = new Date(rec.created_at);
            return recDate > latest ? recDate : latest;
          }, new Date(0));
          setGeneratedAt(mostRecentCreatedAt);
          console.log(`[Notifications] Data freshness: most recent notification at ${mostRecentCreatedAt.toISOString()}`);
        }
        
        // Cache for faster subsequent loads
        try {
          localStorage.setItem('notifications_cache', JSON.stringify({
            recommendations: historyData,
            timestamp: new Date().toISOString()
          }));
          console.log(`[Notifications] ✅ Updated cache with ${historyData.length} notifications`);
        } catch (e) {
          console.warn('Failed to update cache:', e);
        }
      })
      .catch(err => {
        console.error('[Notifications] Failed to fetch from DB on page load:', err);
        // Don't clear existing recommendations if DB fetch fails
        // Keep showing cached data until user manually refreshes
        // The cached data is already displayed from Step 1, so we don't need to do anything
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
      const initialHistory = await fetchHistoryFromDB(notificationMode);
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
          `/api/v1/strategies/options-selling/recommendations?default_premium=60&profit_threshold=0.80&send_notification=true&notification_priority=high&force_refresh=true&_t=${timestamp}`,
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
      const finalHistory = await fetchHistoryFromDB(notificationMode);
      
      // Use history as the single source of truth
      setRecommendations(finalHistory);
      
      // Use the most recent notification's timestamp to show data freshness
      // This reflects when the backend last generated recommendations
      if (finalHistory.length > 0) {
        const mostRecentCreatedAt = finalHistory.reduce((latest, rec) => {
          if (!rec.created_at) return latest;
          const recDate = new Date(rec.created_at);
          return recDate > latest ? recDate : latest;
        }, new Date(0));
        setGeneratedAt(mostRecentCreatedAt);
        console.log(`Displaying ${finalHistory.length} notifications, most recent from ${mostRecentCreatedAt.toISOString()}`);
      } else {
        setGeneratedAt(new Date());
        console.log(`No notifications found`);
      }
      
      // Cache for next page load (instant display)
      try {
        localStorage.setItem('notifications_cache', JSON.stringify({
          recommendations: finalHistory,
          timestamp: new Date().toISOString()
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
  
  // Feedback functions
  const openFeedbackModal = (recId: string) => {
    setFeedbackRecId(recId);
    setFeedbackText('');
    setFeedbackSuccess(null);
    setFeedbackModalOpen(true);
  };
  
  const closeFeedbackModal = () => {
    setFeedbackModalOpen(false);
    setFeedbackRecId(null);
    setFeedbackText('');
    setFeedbackSuccess(null);
  };
  
  const submitFeedback = async () => {
    if (!feedbackRecId || !feedbackText.trim()) return;
    
    setFeedbackSubmitting(true);
    try {
      const params = new URLSearchParams({
        feedback: feedbackText.trim(),
        source: 'web'
      });
      
      const response = await fetch(
        `/api/v1/strategies/notifications/${feedbackRecId}/feedback?${params}`,
        { 
          method: 'POST',
          headers: getAuthHeaders()
        }
      );
      
      if (response.ok) {
        const result = await response.json();
        setFeedbackSuccess(result.parsed?.reason_code || 'Feedback recorded');
        // Auto-close after 2 seconds
        setTimeout(() => {
          closeFeedbackModal();
        }, 2000);
      } else {
        console.error('Failed to submit feedback');
      }
    } catch (err) {
      console.error('Error submitting feedback:', err);
    } finally {
      setFeedbackSubmitting(false);
    }
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
  
  // Group recommendations by time, then by account within each time group
  // This matches the organization shown in Telegram notifications
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
    
    // Log grouping info for debugging
    if (sortedKeys.length > 0) {
      const mostRecentGroup = sortedKeys[0];
      const groupTime = groupLatestTime[mostRecentGroup];
      const groupRecs = groups[mostRecentGroup];
      const timestamps = groupRecs.map(r => r.created_at).filter(Boolean);
      console.log(`[Notifications] Most recent group: ${groupTime.toISOString()} (${groupRecs.length} notifications)`);
      if (timestamps.length > 0) {
        const minTime = new Date(Math.min(...timestamps.map(t => new Date(t).getTime())));
        const maxTime = new Date(Math.max(...timestamps.map(t => new Date(t).getTime())));
        console.log(`[Notifications]   Time range in group: ${minTime.toISOString()} to ${maxTime.toISOString()}`);
      }
    }
    
    // Group by account within each time group, then sort by priority
    // This matches Telegram notification organization
    return sortedKeys.map(groupKey => {
      const recsInGroup = groups[groupKey];
      
      // Group by account
      const byAccount: Record<string, Recommendation[]> = {};
      recsInGroup.forEach(rec => {
        const account = rec.account_name || 'Other';
        if (!byAccount[account]) {
          byAccount[account] = [];
        }
        byAccount[account].push(rec);
      });
      
      // Sort accounts using standard NEO order (Neel's first, then Jaya's, then others)
      const sortedAccounts = Object.keys(byAccount).sort((a, b) => {
        return getAccountSortOrder(a) - getAccountSortOrder(b);
      });
      
      // Create account groups with recommendations sorted by priority
      const accountGroups = sortedAccounts.map(account => ({
        account,
        recommendations: byAccount[account].sort((a, b) => {
          const priorityA = priorityOrder[a.priority] ?? 99;
          const priorityB = priorityOrder[b.priority] ?? 99;
          return priorityA - priorityB;
        })
      }));
      
      return {
        timeKey: groupLatestTime[groupKey].toISOString(), // Display the most recent time
        accountGroups,
        totalCount: recsInGroup.length
      };
    });
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
  
  const getStrategyLabel = (type: string, action?: string) => {
    // If action is WAIT or MONITOR, override the label
    if (action?.toUpperCase() === 'WAIT' || action?.toLowerCase() === 'monitor') {
      return 'Wait';
    }
    
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
                Data from: {(() => {
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
      
      {/* Tab Navigation */}
      <div className={styles.tabBar}>
        <button 
          className={`${styles.tab} ${activeTab === 'recommendations' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          <Bell size={16} />
          Recommendations
          {recommendations.length > 0 && (
            <span className={styles.tabBadge}>{recommendations.length}</span>
          )}
        </button>
        <button 
          className={`${styles.tab} ${activeTab === 'feedback' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('feedback')}
        >
          <History size={16} />
          Feedback History
          {feedbackHistory.length > 0 && (
            <span className={styles.tabBadge}>{feedbackHistory.length}</span>
          )}
        </button>
      </div>
      
      {/* Recommendations Tab Content */}
      {activeTab === 'recommendations' && (
        <>
      {/* Notification Mode Selector - Matches Mobile (Telegram) */}
      <div className={styles.notificationModeBar}>
        <span className={styles.modeLabel}>View Mode:</span>
        <div className={styles.modeToggle}>
          <button
            className={`${styles.modeButton} ${notificationMode === 'verbose' ? styles.modeActive : ''}`}
            onClick={() => {
              setNotificationMode('verbose');
              fetchHistoryFromDB('verbose').then(data => setRecommendations(data));
            }}
            title="Shows all active recommendations (every snapshot)"
          >
            📢 Verbose
          </button>
          <button
            className={`${styles.modeButton} ${notificationMode === 'smart' ? styles.modeActive : ''}`}
            onClick={() => {
              setNotificationMode('smart');
              fetchHistoryFromDB('smart').then(data => setRecommendations(data));
            }}
            title="Shows only new or materially changed recommendations"
          >
            🧠 Smart
          </button>
        </div>
      </div>

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
                      {group.totalCount} notification{group.totalCount !== 1 ? 's' : ''}
                    </span>
                    {formatGroupSummary(group.accountGroups.flatMap(ag => ag.recommendations)).length > 0 && (
                      <span className={styles.priorityBreakdown}>
                        {formatGroupSummary(group.accountGroups.flatMap(ag => ag.recommendations)).map((item, idx) => (
                          <span key={item.priority} className={styles.priorityChip} style={{ color: item.color }}>
                            {idx > 0 && ', '}
                            {item.count} {item.priority}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
                
                {/* Account-grouped notifications - matches Telegram organization */}
                {group.accountGroups.map(accountGroup => (
                  <div key={accountGroup.account} className={styles.accountGroup}>
                    <div className={styles.accountHeader}>
                      <span className={styles.accountName}>{accountGroup.account}</span>
                      <span className={styles.accountCount}>
                        {accountGroup.recommendations.length} recommendation{accountGroup.recommendations.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className={styles.notificationsList}>
                      {accountGroup.recommendations.map(rec => (
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
                            {/* Account badge removed - now shown in accountHeader above */}
                            {rec.symbol && <span className={styles.symbolBadge}>{rec.symbol}</span>}
                            <span className={`${styles.strategyBadge} ${rec.action?.toUpperCase() === 'WAIT' ? styles.waitBadge : ''}`}>
                              {getStrategyLabel(rec.type, rec.action)}
                            </span>
                            {/* V2 Snapshot info */}
                            {rec.snapshot_number && (
                              <span className={styles.snapshotBadge}>
                                #{rec.snapshot_number}
                                {rec.action_changed && <span className={styles.changeIndicator} title="Action changed">⚡</span>}
                                {rec.target_changed && <span className={styles.changeIndicator} title="Target changed">🎯</span>}
                                {rec.priority_changed && <span className={styles.changeIndicator} title="Priority escalated">⬆️</span>}
                              </span>
                            )}
                            {rec.notification_mode && (
                              <span className={`${styles.modeBadge} ${rec.notification_mode === 'verbose' ? styles.verboseMode : styles.smartMode}`}>
                                {rec.notification_mode === 'verbose' ? '📢' : '🧠'}
                              </span>
                            )}
                          </div>
                          <h4 className={styles.notificationTitle}>{rec.title}</h4>
                          <p className={styles.notificationDescription}>{rec.description}</p>
                        </div>
                        
                        <div className={styles.notificationActions}>
                          {/* Premium display - prefer real-time per-contract from context */}
                          {rec.context?.premium_per_contract && rec.context.premium_per_contract > 0 ? (
                            <span className={styles.incomeTag}>
                              <DollarSign size={12} />
                              {rec.context.unsold_contracts > 1 ? (
                                <>
                                  ${rec.context.premium_per_contract.toLocaleString()}/ct
                                  {rec.context.total_premium && (
                                    <span style={{ opacity: 0.7, marginLeft: 4 }}>
                                      (${rec.context.total_premium.toLocaleString()} total)
                                    </span>
                                  )}
                                </>
                              ) : (
                                `$${rec.context.premium_per_contract.toLocaleString()}`
                              )}
                            </span>
                          ) : rec.potential_income && rec.potential_income > 0 ? (
                            <span className={styles.incomeTag}>
                              <TrendingUp size={12} />
                              ${rec.potential_income.toLocaleString()}
                            </span>
                          ) : null}
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
                          
                          {/* V3.4: Decision Rationale (Plain English) */}
                          {rec.decision_rationale && (
                            <div className={styles.rationaleSection}>
                              <h5><Lightbulb size={14} /> Why This Recommendation</h5>
                              <div className={styles.decisionRationale}>
                                {rec.decision_rationale.split('\n\n').map((paragraph, i) => (
                                  <p key={i}>{paragraph}</p>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {/* V3.4: Technical Analysis Summary */}
                          {rec.ta_summary && (
                            <div className={styles.taSummarySection}>
                              <h5><BarChart3 size={14} /> Technical Snapshot</h5>
                              <div className={styles.taSummaryGrid}>
                                <div className={styles.taSummaryItem}>
                                  <span className={styles.taLabel}>Current Price</span>
                                  <span className={styles.taValue}>${rec.ta_summary.current_price?.toFixed(2)}</span>
                                </div>
                                <div className={styles.taSummaryItem}>
                                  <span className={styles.taLabel}>Strike Price</span>
                                  <span className={styles.taValue}>${rec.ta_summary.strike_price?.toFixed(2)} {rec.ta_summary.option_type}</span>
                                </div>
                                <div className={styles.taSummaryItem}>
                                  <span className={styles.taLabel}>Status</span>
                                  <span className={`${styles.taValue} ${rec.ta_summary.is_itm ? styles.taItm : styles.taOtm}`}>
                                    {rec.ta_summary.is_itm 
                                      ? `${rec.ta_summary.itm_pct?.toFixed(1)}% ITM` 
                                      : `${rec.ta_summary.otm_pct?.toFixed(1)}% OTM`}
                                  </span>
                                </div>
                                <div className={styles.taSummaryItem}>
                                  <span className={styles.taLabel}>Days to Expiry</span>
                                  <span className={styles.taValue}>{rec.ta_summary.days_to_expiry} days</span>
                                </div>
                                {rec.ta_summary.bollinger && (
                                  <>
                                    <div className={styles.taSummaryItem}>
                                      <span className={styles.taLabel}>Bollinger Position</span>
                                      <span className={`${styles.taValue} ${
                                        rec.ta_summary.bollinger.position_pct < 30 ? styles.taSupport :
                                        rec.ta_summary.bollinger.position_pct > 70 ? styles.taResistance : ''
                                      }`}>
                                        {rec.ta_summary.bollinger.position_pct?.toFixed(0)}% ({rec.ta_summary.bollinger.position_desc})
                                      </span>
                                    </div>
                                    <div className={styles.taSummaryItem}>
                                      <span className={styles.taLabel}>Bollinger Bands</span>
                                      <span className={styles.taValue} style={{fontSize: '11px'}}>
                                        ${rec.ta_summary.bollinger.lower?.toFixed(0)} / ${rec.ta_summary.bollinger.middle?.toFixed(0)} / ${rec.ta_summary.bollinger.upper?.toFixed(0)}
                                      </span>
                                    </div>
                                  </>
                                )}
                                {rec.ta_summary.rsi && (
                                  <div className={styles.taSummaryItem}>
                                    <span className={styles.taLabel}>RSI (14)</span>
                                    <span className={`${styles.taValue} ${
                                      rec.ta_summary.rsi.value < 30 ? styles.taOversold :
                                      rec.ta_summary.rsi.value > 70 ? styles.taOverbought : ''
                                    }`}>
                                      {rec.ta_summary.rsi.value?.toFixed(1)} ({rec.ta_summary.rsi.status})
                                    </span>
                                  </div>
                                )}
                                {rec.ta_summary.support && (
                                  <div className={styles.taSummaryItem}>
                                    <span className={styles.taLabel}>Support</span>
                                    <span className={styles.taValue}>${rec.ta_summary.support?.toFixed(2)}</span>
                                  </div>
                                )}
                                {rec.ta_summary.resistance && (
                                  <div className={styles.taSummaryItem}>
                                    <span className={styles.taLabel}>Resistance</span>
                                    <span className={styles.taValue}>${rec.ta_summary.resistance?.toFixed(2)}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                          
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
                            <button 
                              className={styles.feedbackButton}
                              onClick={() => openFeedbackModal(rec.id)}
                              title="Give feedback to improve algorithm"
                            >
                              <MessageSquare size={14} />
                              Feedback
                            </button>
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
            ))}
          </div>
        )}
      </div>
        </>
      )}
      
      {/* Feedback History Tab Content */}
      {activeTab === 'feedback' && (
        <div className={styles.feedbackHistoryContainer}>
          {feedbackLoading ? (
            <div className={styles.loading}>
              <RefreshCw size={24} className={styles.spinning} />
              <span>Loading feedback history...</span>
            </div>
          ) : (
            <>
              {/* V4 Insights Section */}
              {feedbackInsights && feedbackInsights.suggestions.length > 0 && (
                <div className={styles.insightsSection}>
                  <h3><Lightbulb size={20} /> V4 Algorithm Insights</h3>
                  <p className={styles.insightsSubtitle}>
                    Based on your {feedbackInsights.total_feedback} feedback items in the last {feedbackInsights.period_days} days
                  </p>
                  
                  <div className={styles.suggestionsList}>
                    {feedbackInsights.suggestions.map((suggestion, idx) => (
                      <div key={idx} className={styles.suggestionCard}>
                        <div className={styles.suggestionFinding}>
                          <BarChart3 size={16} />
                          {suggestion.finding}
                        </div>
                        <div className={styles.suggestionAction}>
                          <ArrowRight size={14} />
                          {suggestion.suggestion}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Patterns Section */}
              {feedbackInsights && feedbackInsights.patterns.length > 0 && (
                <div className={styles.patternsSection}>
                  <h3><TrendingUp size={20} /> Feedback Patterns</h3>
                  <div className={styles.patternsList}>
                    {feedbackInsights.patterns.slice(0, 5).map((pattern, idx) => (
                      <div key={idx} className={styles.patternChip}>
                        <span className={styles.patternLabel}>
                          {pattern.reason_code || pattern.type}
                        </span>
                        <span className={styles.patternCount}>
                          {pattern.count || pattern.skip_count}x
                        </span>
                        {pattern.percentage && (
                          <span className={styles.patternPct}>({pattern.percentage}%)</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Feedback History List */}
              <div className={styles.feedbackListSection}>
                <div className={styles.feedbackListHeader}>
                  <h3><MessageSquare size={20} /> All Feedback</h3>
                  <div className={styles.feedbackActions}>
                    <button 
                      onClick={pollTelegramReplies}
                      className={styles.telegramPollButton}
                      disabled={telegramPolling}
                      title="Check for new Telegram replies"
                    >
                      📱 {telegramPolling ? 'Checking...' : 'Poll Telegram'}
                    </button>
                    <button 
                      onClick={fetchFeedbackHistory}
                      className={styles.refreshSmall}
                      disabled={feedbackLoading}
                    >
                      <RefreshCw size={14} />
                      Refresh
                    </button>
                  </div>
                </div>
                {telegramPollResult && (
                  <div className={styles.pollResult}>
                    {telegramPollResult}
                  </div>
                )}
                
                {feedbackHistory.length === 0 ? (
                  <div className={styles.emptyFeedback}>
                    <MessageSquare size={48} />
                    <p>No feedback yet</p>
                    <span>Click the "Feedback" button on any recommendation to provide feedback</span>
                  </div>
                ) : (
                  <div className={styles.feedbackList}>
                    {feedbackHistory.map(fb => (
                      <div key={fb.id} className={styles.feedbackItem}>
                        <div className={styles.feedbackHeader}>
                          <span className={styles.feedbackSource}>
                            {fb.source === 'web' ? '🖥️ Web' : fb.source === 'telegram' ? '📱 Telegram' : '🔌 API'}
                          </span>
                          <span className={styles.feedbackTime}>
                            {new Date(fb.created_at).toLocaleString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              hour: 'numeric',
                              minute: '2-digit',
                              hour12: true
                            })}
                          </span>
                        </div>
                        
                        <div className={styles.feedbackContent}>
                          <p className={styles.feedbackRaw}>{fb.raw_feedback}</p>
                        </div>
                        
                        <div className={styles.feedbackMeta}>
                          {fb.reason_code && (
                            <span className={styles.reasonBadge}>
                              {fb.reason_code.replace(/_/g, ' ')}
                            </span>
                          )}
                          {fb.threshold_hint && (
                            <span className={styles.thresholdBadge}>
                              💰 ${fb.threshold_hint}
                            </span>
                          )}
                          {fb.symbol && (
                            <span className={styles.symbolBadge}>
                              📈 {fb.symbol}
                            </span>
                          )}
                          {fb.sentiment && fb.sentiment !== 'neutral' && (
                            <span className={`${styles.sentimentBadge} ${
                              fb.sentiment === 'frustrated' ? styles.negative : styles.positive
                            }`}>
                              {fb.sentiment === 'frustrated' ? '😤' : '😊'} {fb.sentiment}
                            </span>
                          )}
                        </div>
                        
                        {fb.actionable_insight && (
                          <div className={styles.actionableInsight}>
                            <Lightbulb size={14} />
                            <span>{fb.actionable_insight}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
      
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
      
      {/* Feedback Modal */}
      {feedbackModalOpen && (
        <div className={styles.feedbackModalOverlay} onClick={closeFeedbackModal}>
          <div className={styles.feedbackModal} onClick={e => e.stopPropagation()}>
            <div className={styles.feedbackModalHeader}>
              <h3><MessageSquare size={20} /> Give Feedback</h3>
              <button onClick={closeFeedbackModal} className={styles.closeButton}>
                <X size={20} />
              </button>
            </div>
            
            {feedbackSuccess ? (
              <div className={styles.feedbackSuccess}>
                <CheckCircle size={32} />
                <p>Thank you! Your feedback helps improve the algorithm.</p>
                <span className={styles.reasonCode}>Detected: {feedbackSuccess}</span>
              </div>
            ) : (
              <>
                <div className={styles.feedbackModalBody}>
                  <p className={styles.feedbackHint}>
                    Tell us why you're skipping this recommendation. Be natural - our AI will understand!
                  </p>
                  <p className={styles.feedbackExamples}>
                    Examples: "premium is too small", "don't want to cap NVDA upside", "market is too volatile today"
                  </p>
                  <textarea
                    className={styles.feedbackTextarea}
                    placeholder="Enter your feedback..."
                    value={feedbackText}
                    onChange={e => setFeedbackText(e.target.value)}
                    rows={4}
                    autoFocus
                  />
                </div>
                <div className={styles.feedbackModalFooter}>
                  <button 
                    onClick={closeFeedbackModal} 
                    className={styles.cancelButton}
                    disabled={feedbackSubmitting}
                  >
                    Cancel
                  </button>
                  <button 
                    onClick={submitFeedback}
                    className={styles.submitButton}
                    disabled={feedbackSubmitting || !feedbackText.trim()}
                  >
                    {feedbackSubmitting ? 'Submitting...' : 'Submit Feedback'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

