import { useState, useEffect } from 'react';
import {
  Brain,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  Edit3,
  XCircle,
  Zap,
  RefreshCw,
  Calendar,
  Target,
  AlertTriangle,
  AlertCircle,
  ChevronRight,
  BarChart3,
  GitBranch,
  Lightbulb,
  ThumbsUp,
  ThumbsDown,
  Clock,
  Filter,
  MessageCircle,
} from 'lucide-react';
import styles from './LearningDashboard.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface Match {
  id: number;
  date: string;
  match_type: string;
  confidence: number;
  recommendation: {
    id: string;
    type: string;
    action: string;
    symbol: string;
    strike: number;
    expiration: string;
    premium: number;
    priority: string;
  } | null;
  execution: {
    id: number;
    date: string;
    action: string;
    symbol: string;
    strike: number;
    expiration: string;
    premium: number;
    contracts: number;
    account: string;
  } | null;
  modification: any;
  hours_to_execution: number;
  user_reason: string;
  week: string;
}

interface WeeklySummary {
  id: number;
  year: number;
  week: number;
  week_label: string;
  date_range: string;
  total_recommendations: number;
  total_executions: number;
  match_breakdown: {
    consent: number;
    modify: number;
    reject: number;
    independent: number;
    no_action: number;
  };
  actual_pnl: number;
  algorithm_pnl: number;
  pnl_delta: number;
  patterns_count: number;
  v4_candidates_count: number;
  review_status: string;
}

interface V4Candidate {
  candidate_id: string;
  change_type: string;
  description: string;
  evidence: string;
  priority: string;
  risk: string;
  decision: string | null;
  first_seen_week: string;
  occurrences: number;
}

interface DivergenceAnalytics {
  period_days: number;
  total_recommendations: number;
  consent: number;
  modify: number;
  reject: number;
  divergence_rate: number;
  consent_rate: number;
  by_week: { week: string; consent: number; modify: number; reject: number }[];
}

const matchTypeConfig = {
  consent: { icon: CheckCircle, color: '#10B981', label: 'Consent', bg: 'rgba(16, 185, 129, 0.1)' },
  modify: { icon: Edit3, color: '#F59E0B', label: 'Modified', bg: 'rgba(245, 158, 11, 0.1)' },
  reject: { icon: XCircle, color: '#EF4444', label: 'Rejected', bg: 'rgba(239, 68, 68, 0.1)' },
  independent: { icon: Zap, color: '#8B5CF6', label: 'Independent', bg: 'rgba(139, 92, 246, 0.1)' },
  no_action: { icon: Clock, color: '#6B7280', label: 'No Action', bg: 'rgba(107, 114, 128, 0.1)' },
};

export default function LearningDashboard() {
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'matches' | 'summaries' | 'candidates'>('overview');
  
  // Data states
  const [matches, setMatches] = useState<Match[]>([]);
  const [weeklySummaries, setWeeklySummaries] = useState<WeeklySummary[]>([]);
  const [v4Candidates, setV4Candidates] = useState<V4Candidate[]>([]);
  const [divergenceAnalytics, setDivergenceAnalytics] = useState<DivergenceAnalytics | null>(null);
  
  // Filter states
  const [matchTypeFilter, setMatchTypeFilter] = useState<string>('all');
  const [daysFilter, setDaysFilter] = useState<number>(30);
  
  // Actions
  const [reconciling, setReconciling] = useState(false);
  const [decidingCandidate, setDecidingCandidate] = useState<string | null>(null);

  useEffect(() => {
    fetchAllData();
  }, [daysFilter]);

  useEffect(() => {
    fetchMatches(matchTypeFilter);
  }, [matchTypeFilter]);

  const fetchAllData = async () => {
    setLoading(true);
    await Promise.all([
      fetchMatches('all'),
      fetchWeeklySummaries(),
      fetchV4Candidates(),
      fetchDivergenceAnalytics(),
    ]);
    setLoading(false);
  };

  const fetchMatches = async (filter: string) => {
    try {
      const url = filter === 'all' 
        ? '/api/v1/strategies/learning/matches?limit=50'
        : `/api/v1/strategies/learning/matches?limit=50&match_type=${filter}`;
      const response = await fetch(url, { headers: getAuthHeaders() });
      const data = await response.json();
      setMatches(data.matches || []);
    } catch (error) {
      console.error('Error fetching matches:', error);
    }
  };

  const fetchWeeklySummaries = async () => {
    try {
      const response = await fetch('/api/v1/strategies/learning/weekly-summaries?limit=12', {
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      setWeeklySummaries(data.summaries || []);
    } catch (error) {
      console.error('Error fetching weekly summaries:', error);
    }
  };

  const fetchV4Candidates = async () => {
    try {
      const response = await fetch('/api/v1/strategies/learning/v4-candidates', {
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      setV4Candidates(data.candidates || []);
    } catch (error) {
      console.error('Error fetching V4 candidates:', error);
    }
  };

  const fetchDivergenceAnalytics = async () => {
    try {
      const response = await fetch(`/api/v1/strategies/learning/analytics/divergence-rate?days=${daysFilter}`, {
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      setDivergenceAnalytics(data);
    } catch (error) {
      console.error('Error fetching divergence analytics:', error);
    }
  };

  const triggerReconciliation = async () => {
    setReconciling(true);
    try {
      const response = await fetch('/api/v1/strategies/learning/reconcile', {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      alert(`Reconciliation complete: ${data.result.matches_saved} matches saved`);
      await fetchAllData();
    } catch (error) {
      console.error('Error triggering reconciliation:', error);
      alert('Failed to trigger reconciliation');
    } finally {
      setReconciling(false);
    }
  };

  const decideOnCandidate = async (candidateId: string, decision: 'implement' | 'defer' | 'reject') => {
    setDecidingCandidate(candidateId);
    try {
      await fetch(`/api/v1/strategies/learning/v4-candidates/${candidateId}/decide?decision=${decision}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      await fetchV4Candidates();
    } catch (error) {
      console.error('Error deciding on candidate:', error);
    } finally {
      setDecidingCandidate(null);
    }
  };

  const submitMatchFeedback = async (matchId: number, reasonCode: string, reasonText?: string) => {
    const params = new URLSearchParams({ reason_code: reasonCode });
    if (reasonText) params.append('reason_text', reasonText);
    
    const response = await fetch(`/api/v1/strategies/learning/matches/${matchId}/reason?${params}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      throw new Error('Failed to save feedback');
    }
    
    // Refresh matches to show updated feedback
    await fetchMatches(matchTypeFilter);
  };

  const skipMatchFeedback = async (matchId: number) => {
    // Mark as "skipped" - user doesn't remember
    const response = await fetch(`/api/v1/strategies/learning/matches/${matchId}/reason?reason_code=skipped`, {
      method: 'PUT',
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      throw new Error('Failed to skip feedback');
    }
    
    await fetchMatches(matchTypeFilter);
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <Brain className={styles.loadingIcon} size={48} />
          <p>Loading learning data...</p>
        </div>
      </div>
    );
  }

  const totalMatches = divergenceAnalytics?.total_recommendations || 0;
  const consentRate = divergenceAnalytics?.consent_rate || 0;
  const divergenceRate = divergenceAnalytics?.divergence_rate || 0;
  const pendingCandidates = v4Candidates.filter(c => !c.decision).length;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Brain size={28} />
          </div>
          <div>
            <h1 className={styles.title}>RLHF Learning Dashboard</h1>
            <p className={styles.subtitle}>
              Track algorithm vs human decisions and improve recommendations
            </p>
          </div>
        </div>
        <button 
          onClick={triggerReconciliation} 
          className={styles.reconcileButton}
          disabled={reconciling}
        >
          <RefreshCw size={18} className={reconciling ? styles.spinning : ''} />
          {reconciling ? 'Reconciling...' : 'Run Reconciliation'}
        </button>
      </div>

      {/* Summary Cards */}
      <div className={styles.summaryCards}>
        <div className={styles.summaryCard}>
          <div className={styles.cardIcon} style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)' }}>
            <BarChart3 size={24} color="#3B82F6" />
          </div>
          <div className={styles.cardContent}>
            <div className={styles.cardValue}>{totalMatches}</div>
            <div className={styles.cardLabel}>Total Recommendations</div>
            <div className={styles.cardSubtext}>Last {daysFilter} days</div>
          </div>
        </div>

        <div className={styles.summaryCard}>
          <div className={styles.cardIcon} style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)' }}>
            <CheckCircle size={24} color="#10B981" />
          </div>
          <div className={styles.cardContent}>
            <div className={styles.cardValue}>{consentRate.toFixed(1)}%</div>
            <div className={styles.cardLabel}>Consent Rate</div>
            <div className={styles.cardSubtext}>Following algorithm</div>
          </div>
        </div>

        <div className={styles.summaryCard}>
          <div className={styles.cardIcon} style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)' }}>
            <GitBranch size={24} color="#F59E0B" />
          </div>
          <div className={styles.cardContent}>
            <div className={styles.cardValue}>{divergenceRate.toFixed(1)}%</div>
            <div className={styles.cardLabel}>Divergence Rate</div>
            <div className={styles.cardSubtext}>Modified or rejected</div>
          </div>
        </div>

        <div className={styles.summaryCard}>
          <div className={styles.cardIcon} style={{ backgroundColor: 'rgba(139, 92, 246, 0.1)' }}>
            <Lightbulb size={24} color="#8B5CF6" />
          </div>
          <div className={styles.cardContent}>
            <div className={styles.cardValue}>{pendingCandidates}</div>
            <div className={styles.cardLabel}>V4 Candidates</div>
            <div className={styles.cardSubtext}>Pending review</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'overview' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <BarChart3 size={18} />
          Overview
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'matches' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('matches')}
        >
          <Target size={18} />
          Matches ({divergenceAnalytics?.total_recommendations || matches.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'summaries' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('summaries')}
        >
          <Calendar size={18} />
          Weekly Summaries
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'candidates' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('candidates')}
        >
          <Lightbulb size={18} />
          V4 Candidates
          {pendingCandidates > 0 && <span className={styles.badge}>{pendingCandidates}</span>}
        </button>
      </div>

      {/* Tab Content */}
      <div className={styles.tabContent}>
        {activeTab === 'overview' && (
          <OverviewTab 
            divergenceAnalytics={divergenceAnalytics}
            weeklySummaries={weeklySummaries}
            daysFilter={daysFilter}
            setDaysFilter={setDaysFilter}
          />
        )}
        
        {activeTab === 'matches' && (
          <MatchesTab 
            matches={matches}
            matchTypeFilter={matchTypeFilter}
            setMatchTypeFilter={setMatchTypeFilter}
            matchCounts={{
              consent: divergenceAnalytics?.consent || 0,
              modify: divergenceAnalytics?.modify || 0,
              reject: divergenceAnalytics?.reject || 0,
              independent: divergenceAnalytics?.independent || 0,
              total: divergenceAnalytics?.total_matches || 0,
            }}
            onFeedbackSubmit={submitMatchFeedback}
            onSkipFeedback={skipMatchFeedback}
          />
        )}
        
        {activeTab === 'summaries' && (
          <SummariesTab summaries={weeklySummaries} />
        )}
        
        {activeTab === 'candidates' && (
          <CandidatesTab 
            candidates={v4Candidates}
            onDecide={decideOnCandidate}
            decidingCandidate={decidingCandidate}
          />
        )}
      </div>
    </div>
  );
}

// Overview Tab Component
function OverviewTab({ 
  divergenceAnalytics, 
  weeklySummaries, 
  daysFilter, 
  setDaysFilter 
}: {
  divergenceAnalytics: DivergenceAnalytics | null;
  weeklySummaries: WeeklySummary[];
  daysFilter: number;
  setDaysFilter: (days: number) => void;
}) {
  if (!divergenceAnalytics || divergenceAnalytics.total_recommendations === 0) {
    return (
      <div className={styles.emptyState}>
        <Brain size={64} strokeWidth={1} />
        <h3>No Learning Data Yet</h3>
        <p>
          The RLHF system starts tracking once you have recommendations and executions.
          Run reconciliation after trading to start building your learning history.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.overviewGrid}>
      {/* Period Selector */}
      <div className={styles.periodSelector}>
        <span>Period:</span>
        {[7, 30, 90].map(days => (
          <button
            key={days}
            className={`${styles.periodButton} ${daysFilter === days ? styles.activePeriod : ''}`}
            onClick={() => setDaysFilter(days)}
          >
            {days}d
          </button>
        ))}
      </div>

      {/* Match Type Distribution */}
      <div className={styles.chartCard}>
        <h3>Match Type Distribution</h3>
        <div className={styles.distributionBars}>
          {Object.entries(matchTypeConfig).map(([type, config]) => {
            const count = divergenceAnalytics[type as keyof DivergenceAnalytics] as number || 0;
            const pct = divergenceAnalytics.total_recommendations > 0 
              ? (count / divergenceAnalytics.total_recommendations) * 100 
              : 0;
            const Icon = config.icon;
            
            return (
              <div key={type} className={styles.distributionRow}>
                <div className={styles.distributionLabel}>
                  <Icon size={16} color={config.color} />
                  <span>{config.label}</span>
                </div>
                <div className={styles.distributionBar}>
                  <div 
                    className={styles.distributionFill}
                    style={{ width: `${pct}%`, backgroundColor: config.color }}
                  />
                </div>
                <div className={styles.distributionValue}>
                  {count} ({pct.toFixed(0)}%)
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Weekly Trend */}
      <div className={styles.chartCard}>
        <h3>Weekly Trend</h3>
        {divergenceAnalytics.by_week && divergenceAnalytics.by_week.length > 0 ? (
          <div className={styles.weeklyTrend}>
            {divergenceAnalytics.by_week.slice(-8).map((week, idx) => {
              const total = week.consent + week.modify + week.reject;
              const consentPct = total > 0 ? (week.consent / total) * 100 : 0;
              
              return (
                <div key={idx} className={styles.weekBar}>
                  <div className={styles.weekBarStack}>
                    <div 
                      className={styles.weekBarSegment}
                      style={{ 
                        height: `${consentPct}%`, 
                        backgroundColor: matchTypeConfig.consent.color 
                      }}
                    />
                    <div 
                      className={styles.weekBarSegment}
                      style={{ 
                        height: `${total > 0 ? (week.modify / total) * 100 : 0}%`, 
                        backgroundColor: matchTypeConfig.modify.color 
                      }}
                    />
                    <div 
                      className={styles.weekBarSegment}
                      style={{ 
                        height: `${total > 0 ? (week.reject / total) * 100 : 0}%`, 
                        backgroundColor: matchTypeConfig.reject.color 
                      }}
                    />
                  </div>
                  <div className={styles.weekLabel}>{week.week.split('-W')[1]}</div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className={styles.noData}>No weekly data available</p>
        )}
      </div>

      {/* Key Insight */}
      <div className={styles.insightCard}>
        <AlertTriangle size={24} color="#F59E0B" />
        <div>
          <h4>Key Insight</h4>
          <p>
            {divergenceAnalytics.divergence_rate > 30 
              ? "You're diverging from the algorithm frequently. Review patterns to understand why."
              : divergenceAnalytics.divergence_rate > 15
              ? "Moderate divergence detected. Some modifications may indicate algorithm improvement opportunities."
              : "High consent rate! The algorithm is well-aligned with your trading preferences."
            }
          </p>
        </div>
      </div>
    </div>
  );
}

// Quick reason buttons - most common first for fast selection
const quickReasons = [
  { code: 'premium_low', label: 'Low Premium', emoji: '💰' },
  { code: 'timing', label: 'Bad Timing', emoji: '⏰' },
  { code: 'risk_too_high', label: 'Too Risky', emoji: '⚠️' },
  { code: 'already_exposed', label: 'Already Have', emoji: '📊' },
  { code: 'better_opportunity', label: 'Better Trade', emoji: '🎯' },
  { code: 'gut_feeling', label: 'Gut Feel', emoji: '🤔' },
  { code: 'iv_low', label: 'Low IV', emoji: '📉' },
  { code: 'earnings_concern', label: 'Earnings', emoji: '📅' },
];

// Helper to check if a date is within N days
const isWithinDays = (dateStr: string, days: number): boolean => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffTime = now.getTime() - date.getTime();
  const diffDays = diffTime / (1000 * 60 * 60 * 24);
  return diffDays <= days;
};

// Convert action abbreviations to full words
const formatAction = (action: string): string => {
  const actionMap: Record<string, string> = {
    'STO': 'Sell to Open',
    'BTO': 'Buy to Open',
    'STC': 'Sell to Close',
    'BTC': 'Buy to Close',
    'SELL_TO_OPEN': 'Sell to Open',
    'BUY_TO_OPEN': 'Buy to Open',
    'SELL_TO_CLOSE': 'Sell to Close',
    'BUY_TO_CLOSE': 'Buy to Close',
    'roll': 'Roll',
    'sell': 'Sell',
    'buy': 'Buy',
  };
  return actionMap[action?.toLowerCase()] || actionMap[action?.toUpperCase()] || action;
};

const formatAccount = (account: string | null | undefined): string => {
  if (!account) return '';
  // Convert snake_case to Title Case
  return account
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
    .replace('Ira', 'IRA')
    .replace(' Roth', "'s Roth");
};

// Helper to format date as MM/DD
const formatDateShort = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')}`;
  } catch {
    return dateStr;
  }
};

const formatDate = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
};

// Parse recommendation ID to extract details
// Format: v3_roll_weekly_PLTR_207.5_Neels_Brokerage
const parseRecommendationId = (id: string): { strike?: number; account?: string } => {
  if (!id) return {};
  
  const parts = id.split('_');
  // Look for a number which is likely the strike
  let strike: number | undefined;
  let account: string | undefined;
  
  for (let i = 0; i < parts.length; i++) {
    const num = parseFloat(parts[i]);
    if (!isNaN(num) && num > 0 && num < 10000) {
      strike = num;
    }
    // Account names often come after the strike
    if (parts[i] === 'Neels' || parts[i] === 'Roth' || parts[i] === 'Traditional') {
      account = parts.slice(i).join(' ').replace('_', ' ');
      break;
    }
  }
  
  return { strike, account };
};

// Matches Tab Component
function MatchesTab({
  matches,
  matchTypeFilter,
  setMatchTypeFilter,
  matchCounts,
  onFeedbackSubmit,
  onSkipFeedback,
}: {
  matches: Match[];
  matchTypeFilter: string;
  setMatchTypeFilter: (filter: string) => void;
  matchCounts: { consent: number; modify: number; reject: number; independent: number; total: number };
  onFeedbackSubmit: (matchId: number, reasonCode: string, reasonText?: string) => Promise<void>;
  onSkipFeedback: (matchId: number) => Promise<void>;
}) {
  // Format helpers for compact display
  const formatDateCompact = (dateStr: string | null | undefined): string => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')}`;
    } catch {
      return dateStr || '';
    }
  };

  // Filter matches based on current filter
  const filteredMatches = matchTypeFilter === 'all' 
    ? matches 
    : matches.filter(m => m.match_type === matchTypeFilter);

  const [submittingId, setSubmittingId] = useState<number | null>(null);

  // Separate matches into "needs feedback" (recent, no feedback) and "historical"
  const FEEDBACK_WINDOW_DAYS = 7;
  
  const needsFeedback = matches.filter(m => 
    (m.match_type === 'reject' || m.match_type === 'independent') &&
    !m.user_reason &&
    isWithinDays(m.date, FEEDBACK_WINDOW_DAYS)
  );
  
  const recentWithFeedback = matches.filter(m =>
    m.user_reason && isWithinDays(m.date, FEEDBACK_WINDOW_DAYS)
  );
  
  const historicalMatches = matches.filter(m =>
    !isWithinDays(m.date, FEEDBACK_WINDOW_DAYS) ||
    (m.match_type === 'consent' && !m.user_reason)
  );

  const handleQuickFeedback = async (matchId: number, reasonCode: string) => {
    setSubmittingId(matchId);
    try {
      await onFeedbackSubmit(matchId, reasonCode);
    } finally {
      setSubmittingId(null);
    }
  };

  const handleSkip = async (matchId: number) => {
    setSubmittingId(matchId);
    try {
      await onSkipFeedback(matchId);
    } finally {
      setSubmittingId(null);
    }
  };

  const filterButtons = [
    { key: 'all', label: 'All', count: matchCounts.total, icon: Target, color: '#60A5FA' },
    { key: 'consent', label: 'Consent', count: matchCounts.consent, icon: CheckCircle, color: '#10B981' },
    { key: 'modify', label: 'Modified', count: matchCounts.modify, icon: Edit3, color: '#F59E0B' },
    { key: 'reject', label: 'Rejected', count: matchCounts.reject, icon: XCircle, color: '#EF4444' },
    { key: 'independent', label: 'Independent', count: matchCounts.independent, icon: Zap, color: '#8B5CF6' },
  ];

  return (
    <div className={styles.matchesContainer}>
      {/* Filter Buttons */}
      <div className={styles.matchTypeFilters}>
        {filterButtons.map(({ key, label, count, icon: Icon, color }) => (
          <button
            key={key}
            className={`${styles.matchTypeButton} ${matchTypeFilter === key ? styles.activeMatchType : ''}`}
            onClick={() => setMatchTypeFilter(key)}
            style={{
              '--filter-color': color,
              '--filter-bg': `${color}20`,
            } as React.CSSProperties}
          >
            <Icon size={16} />
            <span className={styles.matchTypeLabel}>{label}</span>
            <span className={styles.matchTypeCount}>{count}</span>
          </button>
        ))}
      </div>

      {/* Compact Match List - SHOWN FIRST for immediate visibility */}
      <div className={styles.compactMatchList}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: '0.75rem',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          paddingBottom: '0.5rem'
        }}>
          <span style={{ color: '#9CA3AF', fontSize: '0.875rem' }}>
            Showing {filteredMatches.length} {matchTypeFilter === 'all' ? '' : matchTypeFilter} matches
          </span>
        </div>
        
        {filteredMatches.length === 0 ? (
          <p style={{ color: '#6B7280', textAlign: 'center', padding: '2rem' }}>
            No matches found for this filter.
          </p>
        ) : (
          filteredMatches.slice(0, 50).map((m) => {
            const rec = m.recommendation;
            const exec = m.execution;
            const colors: Record<string, string> = { consent: '#10B981', modify: '#F59E0B', reject: '#EF4444', independent: '#8B5CF6' };
            const borderColor = colors[m.match_type] || '#6B7280';
            
            // Build compact recommendation string
            const recStr = rec 
              ? `${formatAction(rec.action)} ${rec.symbol} ${formatDateCompact(m.date)}→${formatDateCompact(rec.expiration)} | $${rec.strike || '?'} | $${rec.premium?.toFixed(2) || '?'}`
              : '—';
            
            // Build compact execution string  
            const execStr = exec
              ? `${formatAction(exec.action)} ${exec.symbol?.split(' ')[0]} ${formatDateCompact(exec.date || m.date)}→${formatDateCompact(exec.expiration)} | $${exec.strike || '?'} | ${exec.contracts}x @ $${(exec.premium && exec.contracts ? exec.premium / exec.contracts : 0).toFixed(2)} | $${exec.premium?.toFixed(2) || '?'}`
              : '—';
            
            return (
              <div 
                key={m.id} 
                className={styles.compactMatchRow}
                style={{ borderLeftColor: borderColor }}
              >
                <div style={{ color: '#93C5FD', fontSize: '0.8125rem', fontFamily: 'monospace' }}>
                  Rec: {recStr}
                </div>
                <div style={{ color: '#86EFAC', fontSize: '0.8125rem', fontFamily: 'monospace' }}>
                  Act: {execStr}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Needs Your Input Section - at bottom */}
      {needsFeedback.length > 0 && (
        <div className={styles.feedbackSection} style={{ marginTop: '2rem' }}>
          <div className={styles.feedbackSectionHeader}>
            <div className={styles.feedbackSectionTitle}>
              <AlertTriangle size={18} color="#F59E0B" />
              <h3>Needs Your Input</h3>
              <span className={styles.feedbackCount}>{needsFeedback.length} items from last {FEEDBACK_WINDOW_DAYS} days</span>
            </div>
            <p className={styles.feedbackHint}>Quick tap a reason, or skip if you don't remember</p>
          </div>
          
          <div className={styles.feedbackCards}>
            {needsFeedback.slice(0, 5).map((match) => {
              const config = matchTypeConfig[match.match_type as keyof typeof matchTypeConfig] || matchTypeConfig.reject;
              const Icon = config.icon;
              const isSubmitting = submittingId === match.id;
              
              return (
                <div key={match.id} className={`${styles.feedbackCard} ${isSubmitting ? styles.submitting : ''}`}>
                  <div className={styles.feedbackCardHeader}>
                    <div 
                      className={styles.matchTypeBadge}
                      style={{ backgroundColor: config.bg, color: config.color }}
                    >
                      <Icon size={14} />
                      {config.label}
                    </div>
                    <span className={styles.matchDate}>{match.date}</span>
                    <button 
                      className={styles.skipButton}
                      onClick={() => handleSkip(match.id)}
                      disabled={isSubmitting}
                      title="Skip - I don't remember"
                    >
                      Skip
                    </button>
                  </div>
                  
                  <div className={styles.feedbackCardBody}>
                    {match.recommendation && (
                      <div className={styles.tradeInfo}>
                        <span className={styles.symbol}>{match.recommendation.symbol}</span>
                        <span className={styles.action}>{formatAction(match.recommendation.action)}</span>
                        {match.recommendation.strike && <span>${match.recommendation.strike}</span>}
                      </div>
                    )}
                    {match.execution && !match.recommendation && (
                      <div className={styles.tradeInfo}>
                        <span className={styles.symbol}>{match.execution.symbol?.split(' ')[0]}</span>
                        <span className={styles.action}>{formatAction(match.execution.action)}</span>
                        {match.execution.contracts && <span>{match.execution.contracts}x</span>}
                      </div>
                    )}
                  </div>
                  
                  <div className={styles.quickReasons}>
                    {quickReasons.slice(0, 6).map(reason => (
                      <button
                        key={reason.code}
                        className={styles.quickReasonButton}
                        onClick={() => handleQuickFeedback(match.id, reason.code)}
                        disabled={isSubmitting}
                        title={reason.label}
                      >
                        <span className={styles.reasonEmoji}>{reason.emoji}</span>
                        <span className={styles.reasonLabel}>{reason.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// Compact Match List Component - Unified format for all match types
function CompactMatchList({ matches }: { matches: Match[] }) {
  if (matches.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Target size={48} strokeWidth={1} color="#6366F1" />
        <h3>No Matches</h3>
        <p>No matches found for this filter.</p>
      </div>
    );
  }

  const matchTypeColors: Record<string, { bg: string; border: string; text: string }> = {
    consent: { bg: '#10B98110', border: '#10B981', text: '#10B981' },
    modify: { bg: '#F59E0B10', border: '#F59E0B', text: '#F59E0B' },
    reject: { bg: '#EF444410', border: '#EF4444', text: '#EF4444' },
    independent: { bg: '#8B5CF610', border: '#8B5CF6', text: '#8B5CF6' },
  };

  const matchTypeLabels: Record<string, string> = {
    consent: '✓',
    modify: '~',
    reject: '✗',
    independent: '⚡',
  };

  // Format recommendation line: "Roll PLTR 01/02→01/09 | $207.5→$196 | $0.49 (~$100)"
  const formatRecommendation = (match: Match): string => {
    if (!match.recommendation) return '—';
    
    const rec = match.recommendation;
    const parts: string[] = [];
    
    // Action + Symbol + Date
    const action = formatAction(rec.action);
    const symbol = rec.symbol || '?';
    const dateStr = match.date || '';
    const expiry = rec.expiration ? formatDateShort(rec.expiration) : '';
    
    if (expiry) {
      parts.push(`${action} ${symbol} ${dateStr}→${expiry}`);
    } else {
      parts.push(`${action} ${symbol} ${dateStr}`);
    }
    
    // Strike
    if (rec.strike) {
      parts.push(`$${rec.strike}`);
    }
    
    // Premium
    if (rec.premium != null) {
      parts.push(`$${rec.premium.toFixed(2)}`);
    }
    
    return parts.join(' | ');
  };

  // Format execution line: "Roll PLTR 01/02→01/09 @ 9:12 AM | $182.5 | 2 contracts @ $0.70 | $139.96"
  const formatExecution = (match: Match): string => {
    if (!match.execution) return '—';
    
    const exec = match.execution;
    const parts: string[] = [];
    
    // Action + Symbol + Date + Time
    const action = formatAction(exec.action);
    const symbol = exec.symbol?.split(' ')[0] || '?';
    const dateStr = match.date || '';
    const expiry = exec.expiration ? formatDateShort(exec.expiration) : '';
    
    if (expiry) {
      parts.push(`${action} ${symbol} ${dateStr}→${expiry}`);
    } else {
      parts.push(`${action} ${symbol} ${dateStr}`);
    }
    
    // Strike
    if (exec.strike) {
      parts.push(`$${exec.strike}`);
    }
    
    // Contracts + Premium per contract
    if (exec.contracts && exec.premium != null) {
      const perContract = exec.premium / exec.contracts;
      parts.push(`${exec.contracts}x @ $${perContract.toFixed(2)}`);
    } else if (exec.contracts) {
      parts.push(`${exec.contracts}x`);
    }
    
    // Total earned
    if (exec.premium != null) {
      parts.push(`$${exec.premium.toFixed(2)}`);
    }
    
    return parts.join(' | ');
  };

  return (
    <div className={styles.compactMatchList}>
      {matches.slice(0, 100).map((match) => {
        const colors = matchTypeColors[match.match_type] || matchTypeColors.consent;
        const typeIcon = matchTypeLabels[match.match_type] || '•';
        
        return (
          <div 
            key={match.id} 
            className={styles.compactMatchRow}
            style={{ 
              borderLeftColor: colors.border,
              backgroundColor: colors.bg 
            }}
          >
            <div className={styles.compactMatchHeader}>
              <span 
                className={styles.compactMatchType}
                style={{ color: colors.text }}
              >
                {typeIcon}
              </span>
              <span className={styles.compactMatchDate}>{match.date}</span>
              <span className={styles.compactMatchConfidence}>{match.confidence?.toFixed(0)}%</span>
            </div>
            
            <div className={styles.compactMatchLines}>
              <div className={styles.compactRecLine}>
                <span className={styles.compactLineLabel}>Rec:</span>
                <span className={styles.compactLineText}>{formatRecommendation(match)}</span>
              </div>
              <div className={styles.compactExecLine}>
                <span className={styles.compactLineLabel}>Act:</span>
                <span className={styles.compactLineText}>{formatExecution(match)}</span>
              </div>
            </div>
            
            {match.user_reason && (
              <div className={styles.compactFeedback}>
                💬 {match.user_reason}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Legacy component - keeping for reference but not used
function ConsentMatchesSectionLegacy({ 
  matches, 
  showHeader 
}: { 
  matches: Match[]; 
  showHeader: boolean;
}) {
  if (matches.length === 0) {
    return (
      <div className={styles.emptyState}>
        <CheckCircle size={48} strokeWidth={1} color="#10B981" />
        <h3>No Consent Matches</h3>
        <p>No recommendations were followed in this period.</p>
      </div>
    );
  }

  return (
    <div className={styles.consentSection}>
      {showHeader && (
        <div className={styles.consentHeader}>
          <CheckCircle size={18} color="#10B981" />
          <h3>Following Algorithm</h3>
          <span className={styles.consentCount}>{matches.length} trades matched recommendations</span>
        </div>
      )}
      
      <div className={styles.consentCards}>
        {matches.slice(0, 50).map((match) => {
          // Parse recommendation ID for additional details
          const parsedRec = match.recommendation?.id ? parseRecommendationId(match.recommendation.id) : {};
          const recStrike = match.recommendation?.strike || parsedRec.strike;
          const recAccount = formatAccount(parsedRec.account);
          const execStrike = match.execution?.strike;
          const execAccount = formatAccount(match.execution?.account);
          const matchConfig = matchTypeConfig[match.match_type as keyof typeof matchTypeConfig] || matchTypeConfig.consent;
          const MatchIcon = matchConfig.icon;
          
          return (
            <div key={match.id} className={styles.matchCardNew}>
              {/* Header with status and date */}
              <div className={styles.matchCardHeader} style={{ background: matchConfig.bg }}>
                <div className={styles.matchStatusBadge} style={{ background: `${matchConfig.color}20`, color: matchConfig.color }}>
                  <MatchIcon size={14} />
                  <span>{matchConfig.label}</span>
                </div>
                <span className={styles.matchDateLarge}>{match.date}</span>
                <span className={styles.matchWeekLabel}>{match.week}</span>
              </div>

              {/* Two Column Layout */}
              <div className={styles.matchTwoColumn}>
                {/* LEFT: Recommendation */}
                <div className={styles.matchColumnLeft}>
                  <div className={styles.matchColumnHeader}>
                    <Target size={16} />
                    <span>RECOMMENDATION</span>
                  </div>
                  {match.recommendation ? (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.matchActionLine}>
                        <span className={styles.matchActionType}>{formatAction(match.recommendation.action)}</span>
                        <span className={styles.matchSymbolBig}>{match.recommendation.symbol}</span>
                      </div>
                      {recAccount && (
                        <div className={styles.matchAccountLine}>
                          <span>in {recAccount}</span>
                        </div>
                      )}
                      
                      {recStrike && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📍</span>
                          <span>Strike: <strong>${recStrike}</strong></span>
                        </div>
                      )}
                      
                      {match.recommendation.expiration && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📅</span>
                          <span>Expiry: <strong>{formatDate(match.recommendation.expiration)}</strong></span>
                        </div>
                      )}
                      
                      {match.recommendation.premium && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>💰</span>
                          <span>Est. Premium: <strong className={styles.premiumGreen}>${match.recommendation.premium.toFixed(2)}</strong></span>
                        </div>
                      )}
                      
                      <div className={styles.matchPriorityLine}>
                        <span className={`${styles.priorityDot} ${styles[`priority${match.recommendation.priority}`]}`}></span>
                        <span>{match.recommendation.priority} priority</span>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.noRecommendation}>
                        <Zap size={18} />
                        <span>Independent Action</span>
                        <p>No recommendation was sent</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* CENTER: Arrow */}
                <div className={styles.matchArrowCenter}>
                  <div className={styles.matchArrowIcon} style={{ background: `${matchConfig.color}15`, color: matchConfig.color }}>
                    <ChevronRight size={28} />
                  </div>
                  {match.hours_to_execution != null && (
                    <span className={styles.matchTimeLabel}>
                      {match.hours_to_execution.toFixed(1)}h
                    </span>
                  )}
                </div>

                {/* RIGHT: Execution */}
                <div className={styles.matchColumnRight}>
                  <div className={styles.matchColumnHeader}>
                    <CheckCircle size={16} />
                    <span>EXECUTED</span>
                  </div>
                  {match.execution && (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.matchActionLine}>
                        <span className={styles.matchActionType}>{formatAction(match.execution.action)}</span>
                        <span className={styles.matchSymbolBig}>{match.execution.symbol?.split(' ')[0]}</span>
                      </div>
                      {execAccount && (
                        <div className={styles.matchAccountLine}>
                          <span>in {execAccount}</span>
                        </div>
                      )}
                      
                      {execStrike && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📍</span>
                          <span>Strike: <strong>${execStrike}</strong></span>
                        </div>
                      )}
                      
                      {match.execution.expiration && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📅</span>
                          <span>Expiry: <strong>{formatDate(match.execution.expiration)}</strong></span>
                        </div>
                      )}
                      
                      {match.execution.contracts && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📊</span>
                          <span>Contracts: <strong>{match.execution.contracts}x</strong></span>
                        </div>
                      )}
                      
                      {match.execution.premium != null && (
                        <div className={styles.matchEarnedLine}>
                          <span className={styles.matchDetailIcon}>💵</span>
                          <span>Earned: </span>
                          <strong className={styles.earnedAmount}>${match.execution.premium.toFixed(2)}</strong>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Footer with confidence */}
              <div className={styles.matchCardFooter}>
                <div className={styles.matchConfidence}>
                  <span>Match Confidence:</span>
                  <div className={styles.confidenceBar}>
                    <div 
                      className={styles.confidenceFill} 
                      style={{ width: `${match.confidence || 0}%` }}
                    />
                  </div>
                  <span className={styles.confidencePercent}>{match.confidence?.toFixed(0)}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Filtered Match Cards Component - for modify/reject/independent matches
function FilteredMatchCards({ 
  matches, 
  matchTypeFilter 
}: { 
  matches: Match[];
  matchTypeFilter: string;
}) {
  if (matches.length === 0) {
    const typeLabels: Record<string, string> = {
      'modify': 'Modified',
      'reject': 'Rejected',
      'independent': 'Independent'
    };
    return (
      <div className={styles.emptyState}>
        <Target size={48} strokeWidth={1} color="#6366F1" />
        <h3>No {typeLabels[matchTypeFilter] || 'Matches'}</h3>
        <p>No matches of this type found in this period.</p>
      </div>
    );
  }

  const matchConfig: Record<string, { color: string; bg: string; icon: typeof CheckCircle; label: string }> = {
    consent: { color: '#10B981', bg: 'linear-gradient(135deg, #065F46, #047857)', icon: CheckCircle, label: 'Consent' },
    modify: { color: '#F59E0B', bg: 'linear-gradient(135deg, #92400E, #B45309)', icon: Edit3, label: 'Modified' },
    reject: { color: '#EF4444', bg: 'linear-gradient(135deg, #991B1B, #DC2626)', icon: XCircle, label: 'Rejected' },
    independent: { color: '#8B5CF6', bg: 'linear-gradient(135deg, #5B21B6, #7C3AED)', icon: Zap, label: 'Independent' },
  };

  const config = matchConfig[matchTypeFilter] || matchConfig.consent;
  const MatchIcon = config.icon;

  return (
    <div className={styles.filteredMatchSection}>
      <div className={styles.filteredMatchCards}>
        {matches.slice(0, 50).map((match) => {
          const parsedRec = match.recommendation?.id ? parseRecommendationId(match.recommendation.id) : {};
          const recStrike = match.recommendation?.strike || parsedRec.strike;
          const recAccount = formatAccount(parsedRec.account);
          const execStrike = match.execution?.strike;
          const execAccount = formatAccount(match.execution?.account);

          return (
            <div key={match.id} className={styles.matchCardNew}>
              {/* Header */}
              <div className={styles.matchCardHeader} style={{ background: config.bg }}>
                <div className={styles.matchStatusBadge} style={{ background: `${config.color}20`, color: config.color }}>
                  <MatchIcon size={14} />
                  <span>{config.label}</span>
                </div>
                <span className={styles.matchDateLarge}>{match.date}</span>
                <span className={styles.matchWeekLabel}>{match.week}</span>
              </div>

              {/* Two Column Layout */}
              <div className={styles.matchTwoColumn}>
                {/* LEFT: Recommendation */}
                <div className={styles.matchColumnLeft}>
                  <div className={styles.matchColumnHeader}>
                    <Target size={16} />
                    <span>RECOMMENDATION</span>
                  </div>
                  {match.recommendation ? (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.matchActionLine}>
                        <span className={styles.matchActionType}>{formatAction(match.recommendation.action)}</span>
                        <span className={styles.matchSymbolBig}>{match.recommendation.symbol}</span>
                      </div>
                      {recAccount && (
                        <div className={styles.matchAccountLine}>
                          <span>in {recAccount}</span>
                        </div>
                      )}
                      {recStrike && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📍</span>
                          <span>Strike: <strong>${recStrike}</strong></span>
                        </div>
                      )}
                      {match.recommendation.expiration && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📅</span>
                          <span>Expiry: <strong>{formatDate(match.recommendation.expiration)}</strong></span>
                        </div>
                      )}
                      {match.recommendation.premium != null && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>💰</span>
                          <span>Target: <strong className={styles.premiumGreen}>${match.recommendation.premium.toFixed(2)}</strong></span>
                        </div>
                      )}
                      <div className={styles.matchPriorityLine}>
                        <span className={`${styles.priorityDot} ${styles[`priority${match.recommendation.priority}`]}`}></span>
                        <span>{match.recommendation.priority} priority</span>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.noRecommendation}>
                        <AlertCircle size={16} />
                        <span>No recommendation</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* CENTER: Arrow */}
                <div className={styles.matchArrowCenter}>
                  {match.recommendation && match.execution && (
                    <>
                      <div className={styles.matchArrowIcon}>
                        <ChevronRight size={28} />
                      </div>
                      {match.hours_to_execution != null && (
                        <span className={styles.matchTimeLabel}>
                          {match.hours_to_execution.toFixed(1)}h
                        </span>
                      )}
                    </>
                  )}
                </div>

                {/* RIGHT: Execution */}
                <div className={styles.matchColumnRight}>
                  <div className={styles.matchColumnHeader}>
                    <CheckCircle size={16} />
                    <span>EXECUTED</span>
                  </div>
                  {match.execution ? (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.matchActionLine}>
                        <span className={styles.matchActionType}>{formatAction(match.execution.action)}</span>
                        <span className={styles.matchSymbolBig}>{match.execution.symbol?.split(' ')[0]}</span>
                      </div>
                      {execAccount && (
                        <div className={styles.matchAccountLine}>
                          <span>in {execAccount}</span>
                        </div>
                      )}
                      {execStrike && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📍</span>
                          <span>Strike: <strong>${execStrike}</strong></span>
                        </div>
                      )}
                      {match.execution.expiration && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📅</span>
                          <span>Expiry: <strong>{formatDate(match.execution.expiration)}</strong></span>
                        </div>
                      )}
                      {match.execution.contracts && (
                        <div className={styles.matchDetailLine}>
                          <span className={styles.matchDetailIcon}>📊</span>
                          <span>Contracts: <strong>{match.execution.contracts}x</strong></span>
                        </div>
                      )}
                      {match.execution.premium != null && (
                        <div className={styles.matchEarnedLine}>
                          <span className={styles.matchDetailIcon}>💵</span>
                          <span>Earned: </span>
                          <strong className={styles.earnedAmount}>${match.execution.premium.toFixed(2)}</strong>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className={styles.matchColumnContent}>
                      <div className={styles.noRecommendation}>
                        <AlertCircle size={16} />
                        <span>No execution data</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className={styles.matchCardFooter}>
                <div className={styles.matchConfidence}>
                  <span>Match Confidence:</span>
                  <div className={styles.confidenceBar}>
                    <div 
                      className={styles.confidenceFill} 
                      style={{ width: `${match.confidence || 0}%`, backgroundColor: config.color }}
                    />
                  </div>
                  <span className={styles.confidencePercent}>{match.confidence?.toFixed(0)}%</span>
                </div>
                {match.user_reason && (
                  <div className={styles.feedbackBadge}>
                    <MessageCircle size={12} />
                    <span>Feedback: {match.user_reason}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Summaries Tab Component
function SummariesTab({ summaries }: { summaries: WeeklySummary[] }) {
  if (summaries.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Calendar size={48} strokeWidth={1} />
        <h3>No Weekly Summaries Yet</h3>
        <p>Weekly summaries are generated every Saturday morning.</p>
      </div>
    );
  }

  return (
    <div className={styles.summariesList}>
      {summaries.map((summary) => (
        <div key={summary.id} className={styles.summaryCard}>
          <div className={styles.summaryHeader}>
            <div className={styles.summaryWeek}>
              <Calendar size={18} />
              <span>{summary.week_label}</span>
            </div>
            <span className={styles.summaryDateRange}>{summary.date_range}</span>
            <span className={`${styles.reviewStatus} ${styles[summary.review_status]}`}>
              {summary.review_status}
            </span>
          </div>
          
          <div className={styles.summaryStats}>
            <div className={styles.statGroup}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{summary.total_recommendations}</span>
                <span className={styles.statLabel}>Recommendations</span>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{summary.total_executions}</span>
                <span className={styles.statLabel}>Executions</span>
              </div>
            </div>
            
            <div className={styles.breakdownBar}>
              {summary.match_breakdown.consent > 0 && (
                <div 
                  className={styles.breakdownSegment}
                  style={{ 
                    flex: summary.match_breakdown.consent,
                    backgroundColor: matchTypeConfig.consent.color 
                  }}
                  title={`Consent: ${summary.match_breakdown.consent}`}
                />
              )}
              {summary.match_breakdown.modify > 0 && (
                <div 
                  className={styles.breakdownSegment}
                  style={{ 
                    flex: summary.match_breakdown.modify,
                    backgroundColor: matchTypeConfig.modify.color 
                  }}
                  title={`Modified: ${summary.match_breakdown.modify}`}
                />
              )}
              {summary.match_breakdown.reject > 0 && (
                <div 
                  className={styles.breakdownSegment}
                  style={{ 
                    flex: summary.match_breakdown.reject,
                    backgroundColor: matchTypeConfig.reject.color 
                  }}
                  title={`Rejected: ${summary.match_breakdown.reject}`}
                />
              )}
            </div>
            
            <div className={styles.summaryMeta}>
              {summary.actual_pnl !== null && (
                <span className={summary.actual_pnl >= 0 ? styles.positive : styles.negative}>
                  P&L: ${summary.actual_pnl?.toFixed(0)}
                </span>
              )}
              {summary.patterns_count > 0 && (
                <span className={styles.patterns}>
                  {summary.patterns_count} patterns
                </span>
              )}
              {summary.v4_candidates_count > 0 && (
                <span className={styles.candidates}>
                  {summary.v4_candidates_count} V4 candidates
                </span>
              )}
            </div>
          </div>
          
          <ChevronRight size={20} className={styles.chevron} />
        </div>
      ))}
    </div>
  );
}

// Candidates Tab Component
function CandidatesTab({ 
  candidates, 
  onDecide,
  decidingCandidate,
}: { 
  candidates: V4Candidate[];
  onDecide: (id: string, decision: 'implement' | 'defer' | 'reject') => void;
  decidingCandidate: string | null;
}) {
  const pending = candidates.filter(c => !c.decision);
  const decided = candidates.filter(c => c.decision);

  if (candidates.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Lightbulb size={48} strokeWidth={1} />
        <h3>No V4 Candidates Yet</h3>
        <p>
          Algorithm improvement candidates are proposed when patterns are detected
          in your divergences from recommendations.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.candidatesContainer}>
      {pending.length > 0 && (
        <div className={styles.candidatesSection}>
          <h3>Pending Review ({pending.length})</h3>
          <div className={styles.candidatesList}>
            {pending.map((candidate) => (
              <div key={candidate.candidate_id} className={styles.candidateCard}>
                <div className={styles.candidateHeader}>
                  <span className={`${styles.priorityBadge} ${styles[candidate.priority]}`}>
                    {candidate.priority}
                  </span>
                  <span className={styles.changeType}>{candidate.change_type}</span>
                </div>
                
                <h4 className={styles.candidateTitle}>{candidate.description}</h4>
                <p className={styles.candidateEvidence}>{candidate.evidence}</p>
                
                <div className={styles.candidateMeta}>
                  <span>First seen: {candidate.first_seen_week}</span>
                  <span>Occurrences: {candidate.occurrences}</span>
                </div>
                
                {candidate.risk && (
                  <div className={styles.candidateRisk}>
                    <AlertTriangle size={14} />
                    Risk: {candidate.risk}
                  </div>
                )}
                
                <div className={styles.candidateActions}>
                  <button
                    onClick={() => onDecide(candidate.candidate_id, 'implement')}
                    className={`${styles.decisionButton} ${styles.implement}`}
                    disabled={decidingCandidate === candidate.candidate_id}
                  >
                    <ThumbsUp size={16} />
                    Implement
                  </button>
                  <button
                    onClick={() => onDecide(candidate.candidate_id, 'defer')}
                    className={`${styles.decisionButton} ${styles.defer}`}
                    disabled={decidingCandidate === candidate.candidate_id}
                  >
                    <Clock size={16} />
                    Defer
                  </button>
                  <button
                    onClick={() => onDecide(candidate.candidate_id, 'reject')}
                    className={`${styles.decisionButton} ${styles.reject}`}
                    disabled={decidingCandidate === candidate.candidate_id}
                  >
                    <ThumbsDown size={16} />
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {decided.length > 0 && (
        <div className={styles.candidatesSection}>
          <h3>Decided ({decided.length})</h3>
          <div className={styles.candidatesList}>
            {decided.map((candidate) => (
              <div key={candidate.candidate_id} className={`${styles.candidateCard} ${styles.decided}`}>
                <div className={styles.candidateHeader}>
                  <span className={`${styles.decisionBadge} ${styles[candidate.decision || '']}`}>
                    {candidate.decision}
                  </span>
                </div>
                <h4 className={styles.candidateTitle}>{candidate.description}</h4>
                <p className={styles.candidateEvidence}>{candidate.evidence}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

