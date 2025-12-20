import { useState, useEffect } from 'react';
import { 
  TrendingUp,
  DollarSign,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Info,
  Calendar,
  Target,
  Users,
  Baby,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import styles from './RetirementDeductions.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface YearData {
  year: number;
  neel: {
    ira: number;
    roth_ira: number;
    "401k": number;
    hsa: number;
    total: number;
    ira_limit: number;
    roth_ira_limit: number;
    "401k_limit": number;
    ira_remaining: number;
    roth_ira_remaining: number;
    "401k_remaining": number;
  };
  jaya: {
    ira: number;
    roth_ira: number;
    "401k": number;
    hsa: number;
    total: number;
    ira_limit: number;
    roth_ira_limit: number;
    "401k_limit": number;
    ira_remaining: number;
    roth_ira_remaining: number;
    "401k_remaining": number;
  };
  family_total: number;
}

interface Recommendation {
  recommended: number;
  current: number;
  remaining: number;
  priority: 'high' | 'medium' | 'low';
}

interface Recommendations2026 {
  neel: {
    ira: Recommendation;
    roth_ira: Recommendation;
    "401k": Recommendation;
    hsa: Recommendation;
  };
  jaya: {
    ira: Recommendation;
    roth_ira: Recommendation;
    "401k": Recommendation;
    hsa: Recommendation;
  };
  kids: {
    "529_plans": {
      recommended: number;
      note: string;
      priority: 'high' | 'medium' | 'low';
    };
    custodial_ira: {
      recommended: number;
      note: string;
      priority: 'high' | 'medium' | 'low';
    };
  };
}

interface CurrentValues {
  neel: { retirement: number; ira: number; roth_ira: number; hsa: number; total: number };
  jaya: { retirement: number; ira: number; roth_ira: number; hsa: number; total: number };
  family: { hsa: number; total: number };
  as_of_date: string | null;
}

interface AllTimeTotals {
  neel: { contributions: number; current_value: number; growth: number; growth_percent: number };
  jaya: { contributions: number; current_value: number; growth: number; growth_percent: number };
  family: { contributions: number; current_value: number; growth: number; growth_percent: number };
}

interface RetirementData {
  years_data: YearData[];
  max_annual_contributions: {
    neel: {
      ira: number;
      roth_ira: number;
      "401k": number;
      hsa: number;
      total: number;
    };
    jaya: {
      ira: number;
      roth_ira: number;
      "401k": number;
      hsa: number;
      total: number;
    };
    kids: {
      "529_per_child": number;
      custodial_ira: number;
      note: string;
    };
    family_total: number;
  };
  recommendations_2026: Recommendations2026;
  current_values?: CurrentValues;
  all_time_totals?: AllTimeTotals;
  summary: {
    years_analyzed: number;
    earliest_year: number | null;
    latest_year: number | null;
  };
}

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
};

const getPriorityColor = (priority: string) => {
  switch (priority) {
    case 'high':
      return '#EF4444';
    case 'medium':
      return '#F59E0B';
    default:
      return '#6B7280';
  }
};

export default function RetirementDeductions() {
  const [data, setData] = useState<RetirementData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | '2026' | 'max-contributions' | 'all-time'>('overview');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/v1/strategies/retirement-contributions/analysis', {
        headers: getAuthHeaders(),
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch retirement contributions analysis');
      }
      
      const result = await response.json();
      setData(result);
      
      // Auto-select most recent year if available
      if (result.years_data && result.years_data.length > 0) {
        setSelectedYear(result.years_data[0].year);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={40} className={styles.spinner} />
          <p>Analyzing retirement contributions...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <h3>Error Loading Analysis</h3>
          <p>{error}</p>
          <button className={styles.retryButton} onClick={fetchData}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  // Prepare chart data
  const chartData = data.years_data.map(year => ({
    year: year.year,
    'Neel IRA': year.neel.ira,
    'Neel Roth IRA': year.neel.roth_ira,
    'Jaya IRA': year.jaya.ira,
    'Jaya Roth IRA': year.jaya.roth_ira,
    'Neel 401k': year.neel["401k"],
    'Jaya 401k': year.jaya["401k"],
    'Family Total': year.family_total,
  }));

  const selectedYearData = selectedYear 
    ? data.years_data.find(y => y.year === selectedYear)
    : null;

  return (
    <div className={styles.page}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Target size={32} />
          </div>
          <div>
            <h1 className={styles.title}>Retirement Deductions Strategy</h1>
            <p className={styles.subtitle}>
              Maximize retirement account contributions and tax deductions
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
          📊 Overview
        </button>
        <button
          className={`${styles.tab} ${activeTab === '2026' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('2026')}
        >
          🎯 2026 Plan
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'max-contributions' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('max-contributions')}
        >
          💰 Max Contributions
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'all-time' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('all-time')}
        >
          🏆 All-Time Totals
        </button>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {activeTab === 'overview' && (
          <>
            {/* Summary Cards */}
            <div className={styles.summaryGrid}>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Years Analyzed</span>
                <span className={styles.summaryValue}>{data.summary.years_analyzed}</span>
                <span className={styles.summaryNote}>
                  {data.summary.earliest_year} - {data.summary.latest_year}
                </span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Latest Year Total</span>
                <span className={styles.summaryValue}>
                  {formatCurrency(data.years_data[0]?.family_total || 0)}
                </span>
                <span className={styles.summaryNote}>
                  {data.years_data[0]?.year || 'N/A'}
                </span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Max Annual (2026)</span>
                <span className={styles.summaryValue}>
                  {formatCurrency(data.max_annual_contributions.family_total)}
                </span>
                <span className={styles.summaryNote}>Family total</span>
              </div>
            </div>

            {/* Contribution History Chart */}
            <div className={styles.chartCard}>
              <h3 className={styles.chartTitle}>
                <TrendingUp size={20} />
                Retirement Contributions Over Time (from IRS Transcripts)
              </h3>
              <div className={styles.chartContainer}>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="year" 
                      stroke="#888"
                      tick={{ fill: '#888', fontSize: 12 }}
                    />
                    <YAxis 
                      stroke="#888"
                      tick={{ fill: '#888', fontSize: 12 }}
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(20, 20, 20, 0.95)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                      }}
                      formatter={(value: number) => formatCurrency(value)}
                    />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="Neel 401k" 
                      name="Neel 401(k)"
                      stroke="#00D632" 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="Jaya 401k" 
                      name="Jaya 401(k)"
                      stroke="#A855F7" 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="Neel IRA" 
                      stroke="#10B981" 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      strokeDasharray="5 5"
                    />
                    <Line 
                      type="monotone" 
                      dataKey="Jaya IRA" 
                      stroke="#8B5CF6" 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      strokeDasharray="5 5"
                    />
                    <Line 
                      type="monotone" 
                      dataKey="Family Total" 
                      stroke="#3B82F6" 
                      strokeWidth={3}
                      dot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Year Selection */}
            <div className={styles.yearSelector}>
              <h3 className={styles.sectionTitle}>
                <Calendar size={20} />
                Select Year for Details
              </h3>
              <div className={styles.yearButtons}>
                {data.years_data.map((yearData) => (
                  <button
                    key={yearData.year}
                    className={`${styles.yearButton} ${
                      selectedYear === yearData.year ? styles.selected : ''
                    }`}
                    onClick={() => setSelectedYear(yearData.year)}
                  >
                    {yearData.year}
                  </button>
                ))}
              </div>
            </div>

            {/* Selected Year Details */}
            {selectedYearData && (
              <div className={styles.yearDetails}>
                <h3 className={styles.sectionTitle}>
                  {selectedYearData.year} Contribution Details
                </h3>
                <div className={styles.yearDetailsGrid}>
                  {/* Neel's Contributions */}
                  <div className={styles.personCard}>
                    <h4 className={styles.personName}>
                      <Users size={18} />
                      Neel
                    </h4>
                    <div className={styles.contributionList}>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>IRA</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.neel.ira)}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.neel.ira_limit)}
                          </span>
                        </div>
                        {selectedYearData.neel.ira_remaining > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.neel.ira_remaining)} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>Roth IRA</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.neel.roth_ira)}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.neel.roth_ira_limit)}
                          </span>
                        </div>
                        {selectedYearData.neel.roth_ira_remaining > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.neel.roth_ira_remaining)} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>401(k)</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.neel["401k"])}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.neel["401k_limit"])}
                          </span>
                        </div>
                        {selectedYearData.neel["401k_remaining"] > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.neel["401k_remaining"])} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionTotal}>
                        <span>Total: {formatCurrency(selectedYearData.neel.total)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Jaya's Contributions */}
                  <div className={styles.personCard}>
                    <h4 className={styles.personName}>
                      <Users size={18} />
                      Jaya
                    </h4>
                    <div className={styles.contributionList}>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>IRA</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.jaya.ira)}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.jaya.ira_limit)}
                          </span>
                        </div>
                        {selectedYearData.jaya.ira_remaining > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.jaya.ira_remaining)} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>Roth IRA</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.jaya.roth_ira)}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.jaya.roth_ira_limit)}
                          </span>
                        </div>
                        {selectedYearData.jaya.roth_ira_remaining > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.jaya.roth_ira_remaining)} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionItem}>
                        <span className={styles.contributionLabel}>401(k)</span>
                        <div className={styles.contributionValue}>
                          <span>{formatCurrency(selectedYearData.jaya["401k"])}</span>
                          <span className={styles.contributionLimit}>
                            / {formatCurrency(selectedYearData.jaya["401k_limit"])}
                          </span>
                        </div>
                        {selectedYearData.jaya["401k_remaining"] > 0 && (
                          <span className={styles.remaining}>
                            {formatCurrency(selectedYearData.jaya["401k_remaining"])} remaining
                          </span>
                        )}
                      </div>
                      <div className={styles.contributionTotal}>
                        <span>Total: {formatCurrency(selectedYearData.jaya.total)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Optimization Recommendations for Selected Year */}
                <div className={styles.optimizationCard}>
                  <h4 className={styles.optimizationTitle}>
                    <Info size={18} />
                    Optimization Opportunities for {selectedYearData.year}
                  </h4>
                  <ul className={styles.optimizationList}>
                    {selectedYearData.neel.ira_remaining > 0 && (
                      <li>
                        Neel can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.neel.ira_remaining)}</strong> to IRA
                      </li>
                    )}
                    {selectedYearData.neel.roth_ira_remaining > 0 && (
                      <li>
                        Neel can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.neel.roth_ira_remaining)}</strong> to Roth IRA
                      </li>
                    )}
                    {selectedYearData.neel["401k_remaining"] > 0 && (
                      <li>
                        Neel can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.neel["401k_remaining"])}</strong> to 401(k)
                      </li>
                    )}
                    {selectedYearData.jaya.ira_remaining > 0 && (
                      <li>
                        Jaya can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.jaya.ira_remaining)}</strong> to IRA
                      </li>
                    )}
                    {selectedYearData.jaya.roth_ira_remaining > 0 && (
                      <li>
                        Jaya can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.jaya.roth_ira_remaining)}</strong> to Roth IRA
                      </li>
                    )}
                    {selectedYearData.jaya["401k_remaining"] > 0 && (
                      <li>
                        Jaya can contribute an additional{' '}
                        <strong>{formatCurrency(selectedYearData.jaya["401k_remaining"])}</strong> to 401(k)
                      </li>
                    )}
                    {selectedYearData.neel.ira_remaining === 0 &&
                      selectedYearData.neel.roth_ira_remaining === 0 &&
                      selectedYearData.neel["401k_remaining"] === 0 &&
                      selectedYearData.jaya.ira_remaining === 0 &&
                      selectedYearData.jaya.roth_ira_remaining === 0 &&
                      selectedYearData.jaya["401k_remaining"] === 0 && (
                        <li>
                          <CheckCircle2 size={16} className={styles.checkIcon} />
                          All retirement accounts are maxed out for {selectedYearData.year}! Great job!
                        </li>
                      )}
                  </ul>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === '2026' && (
          <div className={styles.plan2026}>
            <h2 className={styles.planTitle}>2026 Retirement Contribution Plan</h2>
            <p className={styles.planSubtitle}>
              Recommended contributions to maximize tax deductions and retirement savings
            </p>

            <div className={styles.recommendationsGrid}>
              {/* Neel's Recommendations */}
              <div className={styles.recommendationCard}>
                <h3 className={styles.recommendationCardTitle}>
                  <Users size={20} />
                  Neel
                </h3>
                <div className={styles.recommendationList}>
                  {Object.entries(data.recommendations_2026.neel).map(([account, rec]) => (
                    <div key={account} className={styles.recommendationItem}>
                      <div className={styles.recommendationHeader}>
                        <span className={styles.recommendationAccount}>
                          {account.toUpperCase()}
                        </span>
                        <span
                          className={styles.priorityBadge}
                          style={{ backgroundColor: getPriorityColor(rec.priority) }}
                        >
                          {rec.priority}
                        </span>
                      </div>
                      <div className={styles.recommendationDetails}>
                        <div className={styles.recommendationRow}>
                          <span>Recommended:</span>
                          <strong>{formatCurrency(rec.recommended)}</strong>
                        </div>
                        {rec.current > 0 && (
                          <div className={styles.recommendationRow}>
                            <span>Current:</span>
                            <span>{formatCurrency(rec.current)}</span>
                          </div>
                        )}
                        <div className={styles.recommendationRow}>
                          <span>Remaining:</span>
                          <strong className={styles.remainingAmount}>
                            {formatCurrency(rec.remaining)}
                          </strong>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Jaya's Recommendations */}
              <div className={styles.recommendationCard}>
                <h3 className={styles.recommendationCardTitle}>
                  <Users size={20} />
                  Jaya
                </h3>
                <div className={styles.recommendationList}>
                  {Object.entries(data.recommendations_2026.jaya).map(([account, rec]) => (
                    <div key={account} className={styles.recommendationItem}>
                      <div className={styles.recommendationHeader}>
                        <span className={styles.recommendationAccount}>
                          {account.toUpperCase()}
                        </span>
                        <span
                          className={styles.priorityBadge}
                          style={{ backgroundColor: getPriorityColor(rec.priority) }}
                        >
                          {rec.priority}
                        </span>
                      </div>
                      <div className={styles.recommendationDetails}>
                        <div className={styles.recommendationRow}>
                          <span>Recommended:</span>
                          <strong>{formatCurrency(rec.recommended)}</strong>
                        </div>
                        {rec.current > 0 && (
                          <div className={styles.recommendationRow}>
                            <span>Current:</span>
                            <span>{formatCurrency(rec.current)}</span>
                          </div>
                        )}
                        <div className={styles.recommendationRow}>
                          <span>Remaining:</span>
                          <strong className={styles.remainingAmount}>
                            {formatCurrency(rec.remaining)}
                          </strong>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Kids' Recommendations */}
              <div className={styles.recommendationCard}>
                <h3 className={styles.recommendationCardTitle}>
                  <Baby size={20} />
                  Kids
                </h3>
                <div className={styles.recommendationList}>
                  <div className={styles.recommendationItem}>
                    <div className={styles.recommendationHeader}>
                      <span className={styles.recommendationAccount}>529 PLAN</span>
                      <span
                        className={styles.priorityBadge}
                        style={{
                          backgroundColor: getPriorityColor(
                            data.recommendations_2026.kids["529_plans"].priority
                          ),
                        }}
                      >
                        {data.recommendations_2026.kids["529_plans"].priority}
                      </span>
                    </div>
                    <div className={styles.recommendationDetails}>
                      <div className={styles.recommendationRow}>
                        <span>Recommended per child:</span>
                        <strong>
                          {formatCurrency(data.recommendations_2026.kids["529_plans"].recommended)}
                        </strong>
                      </div>
                      <div className={styles.recommendationNote}>
                        <Info size={14} />
                        {data.recommendations_2026.kids["529_plans"].note}
                      </div>
                    </div>
                  </div>
                  <div className={styles.recommendationItem}>
                    <div className={styles.recommendationHeader}>
                      <span className={styles.recommendationAccount}>CUSTODIAL IRA</span>
                      <span
                        className={styles.priorityBadge}
                        style={{
                          backgroundColor: getPriorityColor(
                            data.recommendations_2026.kids.custodial_ira.priority
                          ),
                        }}
                      >
                        {data.recommendations_2026.kids.custodial_ira.priority}
                      </span>
                    </div>
                    <div className={styles.recommendationDetails}>
                      <div className={styles.recommendationRow}>
                        <span>Recommended:</span>
                        <strong>
                          {formatCurrency(data.recommendations_2026.kids.custodial_ira.recommended)}
                        </strong>
                      </div>
                      <div className={styles.recommendationNote}>
                        <Info size={14} />
                        {data.recommendations_2026.kids.custodial_ira.note}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'max-contributions' && (
          <div className={styles.maxContributions}>
            <h2 className={styles.planTitle}>Maximum Annual Contributions</h2>
            <p className={styles.planSubtitle}>
              Based on your family situation, here are the maximum annual contributions
              you can make across all retirement and retirement-related accounts
            </p>

            <div className={styles.maxContributionsGrid}>
              <div className={styles.maxContributionCard}>
                <h3 className={styles.maxContributionTitle}>
                  <Users size={20} />
                  Neel
                </h3>
                <div className={styles.maxContributionList}>
                  <div className={styles.maxContributionItem}>
                    <span>IRA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.neel.ira)}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>Roth IRA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.neel.roth_ira)}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>401(k)</span>
                    <strong>{formatCurrency(data.max_annual_contributions.neel["401k"])}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>HSA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.neel.hsa)}</strong>
                  </div>
                  <div className={styles.maxContributionTotal}>
                    <span>Total</span>
                    <strong>{formatCurrency(data.max_annual_contributions.neel.total)}</strong>
                  </div>
                </div>
              </div>

              <div className={styles.maxContributionCard}>
                <h3 className={styles.maxContributionTitle}>
                  <Users size={20} />
                  Jaya
                </h3>
                <div className={styles.maxContributionList}>
                  <div className={styles.maxContributionItem}>
                    <span>IRA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.jaya.ira)}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>Roth IRA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.jaya.roth_ira)}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>401(k)</span>
                    <strong>{formatCurrency(data.max_annual_contributions.jaya["401k"])}</strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>HSA</span>
                    <strong>{formatCurrency(data.max_annual_contributions.jaya.hsa)}</strong>
                  </div>
                  <div className={styles.maxContributionTotal}>
                    <span>Total</span>
                    <strong>{formatCurrency(data.max_annual_contributions.jaya.total)}</strong>
                  </div>
                </div>
              </div>

              <div className={styles.maxContributionCard}>
                <h3 className={styles.maxContributionTitle}>
                  <Baby size={20} />
                  Kids
                </h3>
                <div className={styles.maxContributionList}>
                  <div className={styles.maxContributionItem}>
                    <span>529 Plan (per child)</span>
                    <strong>
                      {formatCurrency(data.max_annual_contributions.kids["529_per_child"])}
                    </strong>
                  </div>
                  <div className={styles.maxContributionItem}>
                    <span>Custodial IRA</span>
                    <strong>
                      {formatCurrency(data.max_annual_contributions.kids.custodial_ira)}
                    </strong>
                  </div>
                  <div className={styles.maxContributionNote}>
                    <Info size={14} />
                    {data.max_annual_contributions.kids.note}
                  </div>
                </div>
              </div>
            </div>

            <div className={styles.familyTotalCard}>
              <h3 className={styles.familyTotalTitle}>Family Total Maximum</h3>
              <div className={styles.familyTotalAmount}>
                {formatCurrency(data.max_annual_contributions.family_total)}
              </div>
              <p className={styles.familyTotalNote}>
                Combined maximum annual contributions across all retirement accounts for the entire family
              </p>
            </div>
          </div>
        )}

        {activeTab === 'all-time' && (
          <div className={styles.allTime}>
            <h2 className={styles.planTitle}>All-Time Retirement Contributions</h2>
            <p className={styles.planSubtitle}>
              Lifetime totals from IRS Wage & Income Transcripts ({data.summary.earliest_year} - {data.summary.latest_year})
            </p>

            {/* All-Time Summary Cards */}
            <div className={styles.allTimeSummaryGrid}>
              {/* Neel's All-Time Card */}
              <div className={styles.allTimeCard}>
                <div className={styles.allTimeCardHeader}>
                  <Users size={28} />
                  <h3>Neel</h3>
                </div>
                <div className={styles.allTimeTotal}>
                  {formatCurrency(
                    data.years_data.reduce((sum, year) => sum + year.neel.total, 0)
                  )}
                </div>
                <p className={styles.allTimeLabel}>Total Contributions</p>
                
                {data.all_time_totals && data.all_time_totals.neel.current_value > 0 && (
                  <div className={styles.growthSection}>
                    <div className={styles.currentValueRow}>
                      <span>Current Value</span>
                      <strong className={styles.currentValue}>
                        {formatCurrency(data.all_time_totals.neel.current_value)}
                      </strong>
                    </div>
                    <div className={styles.growthRow}>
                      <span>Growth</span>
                      <strong className={data.all_time_totals.neel.growth >= 0 ? styles.positiveGrowth : styles.negativeGrowth}>
                        {data.all_time_totals.neel.growth >= 0 ? '+' : ''}{formatCurrency(data.all_time_totals.neel.growth)}
                        <span className={styles.growthPercent}>
                          ({data.all_time_totals.neel.growth >= 0 ? '+' : ''}{data.all_time_totals.neel.growth_percent}%)
                        </span>
                      </strong>
                    </div>
                  </div>
                )}
                
                <div className={styles.allTimeBreakdown}>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>401(k)</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.neel["401k"], 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>Traditional IRA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.neel.ira, 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>Roth IRA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.neel.roth_ira, 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>HSA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.neel.hsa, 0)
                      )}
                    </strong>
                  </div>
                </div>
                
                <div className={styles.allTimeYears}>
                  <Calendar size={14} />
                  <span>{data.summary.years_analyzed} years of data</span>
                </div>
              </div>

              {/* Jaya's All-Time Card */}
              <div className={styles.allTimeCard}>
                <div className={styles.allTimeCardHeader}>
                  <Users size={28} />
                  <h3>Jaya</h3>
                </div>
                <div className={styles.allTimeTotal}>
                  {formatCurrency(
                    data.years_data.reduce((sum, year) => sum + year.jaya.total, 0)
                  )}
                </div>
                <p className={styles.allTimeLabel}>Total Contributions</p>
                
                {data.all_time_totals && data.all_time_totals.jaya.current_value > 0 && (
                  <div className={styles.growthSection}>
                    <div className={styles.currentValueRow}>
                      <span>Current Value</span>
                      <strong className={styles.currentValue}>
                        {formatCurrency(data.all_time_totals.jaya.current_value)}
                      </strong>
                    </div>
                    <div className={styles.growthRow}>
                      <span>Growth</span>
                      <strong className={data.all_time_totals.jaya.growth >= 0 ? styles.positiveGrowth : styles.negativeGrowth}>
                        {data.all_time_totals.jaya.growth >= 0 ? '+' : ''}{formatCurrency(data.all_time_totals.jaya.growth)}
                        <span className={styles.growthPercent}>
                          ({data.all_time_totals.jaya.growth >= 0 ? '+' : ''}{data.all_time_totals.jaya.growth_percent}%)
                        </span>
                      </strong>
                    </div>
                  </div>
                )}
                
                <div className={styles.allTimeBreakdown}>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>401(k)</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.jaya["401k"], 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>Traditional IRA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.jaya.ira, 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>Roth IRA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.jaya.roth_ira, 0)
                      )}
                    </strong>
                  </div>
                  <div className={styles.allTimeBreakdownItem}>
                    <span>HSA</span>
                    <strong>
                      {formatCurrency(
                        data.years_data.reduce((sum, year) => sum + year.jaya.hsa, 0)
                      )}
                    </strong>
                  </div>
                </div>
                
                <div className={styles.allTimeYears}>
                  <Calendar size={14} />
                  <span>{data.summary.years_analyzed} years of data</span>
                </div>
              </div>
            </div>

            {/* Family Grand Total */}
            <div className={styles.familyTotalCard}>
              <h3 className={styles.familyTotalTitle}>Family Grand Total</h3>
              <div className={styles.familyTotalAmount}>
                {formatCurrency(
                  data.years_data.reduce((sum, year) => sum + year.family_total, 0)
                )}
              </div>
              {data.all_time_totals && data.all_time_totals.family.current_value > 0 && (
                <div className={styles.familyGrowthStats}>
                  <div className={styles.familyGrowthItem}>
                    <span>Current Value</span>
                    <strong>{formatCurrency(data.all_time_totals.family.current_value)}</strong>
                  </div>
                  <div className={styles.familyGrowthItem}>
                    <span>Total Growth</span>
                    <strong className={data.all_time_totals.family.growth >= 0 ? styles.positiveGrowth : styles.negativeGrowth}>
                      {data.all_time_totals.family.growth >= 0 ? '+' : ''}{formatCurrency(data.all_time_totals.family.growth)}
                      ({data.all_time_totals.family.growth >= 0 ? '+' : ''}{data.all_time_totals.family.growth_percent}%)
                    </strong>
                  </div>
                </div>
              )}
              <p className={styles.familyTotalNote}>
                Combined lifetime retirement contributions ({data.summary.earliest_year} - {data.summary.latest_year})
              </p>
            </div>

            {/* Year-by-Year Breakdown Table */}
            <div className={styles.allTimeTableCard}>
              <h3 className={styles.chartTitle}>
                <TrendingUp size={20} />
                Year-by-Year Breakdown
              </h3>
              <div className={styles.allTimeTable}>
                <table>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Neel 401(k)</th>
                      <th>Neel IRA</th>
                      <th>Jaya 401(k)</th>
                      <th>Jaya IRA</th>
                      <th>Family Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.years_data.map((year) => (
                      <tr key={year.year}>
                        <td>{year.year}</td>
                        <td>{formatCurrency(year.neel["401k"])}</td>
                        <td>{formatCurrency(year.neel.ira)}</td>
                        <td>{formatCurrency(year.jaya["401k"])}</td>
                        <td>{formatCurrency(year.jaya.ira)}</td>
                        <td className={styles.totalCell}>{formatCurrency(year.family_total)}</td>
                      </tr>
                    ))}
                    <tr className={styles.totalRow}>
                      <td><strong>TOTAL</strong></td>
                      <td><strong>{formatCurrency(data.years_data.reduce((sum, y) => sum + y.neel["401k"], 0))}</strong></td>
                      <td><strong>{formatCurrency(data.years_data.reduce((sum, y) => sum + y.neel.ira, 0))}</strong></td>
                      <td><strong>{formatCurrency(data.years_data.reduce((sum, y) => sum + y.jaya["401k"], 0))}</strong></td>
                      <td><strong>{formatCurrency(data.years_data.reduce((sum, y) => sum + y.jaya.ira, 0))}</strong></td>
                      <td className={styles.totalCell}><strong>{formatCurrency(data.years_data.reduce((sum, y) => sum + y.family_total, 0))}</strong></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


