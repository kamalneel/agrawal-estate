import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, 
  TrendingUp, 
  TrendingDown,
  Minus,
  Lightbulb,
  DollarSign,
  Home,
  Heart,
  BarChart3,
  Shield,
  FileText,
  RefreshCw,
  AlertCircle,
  ChevronRight
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import styles from './TaxPlanning.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface TaxAreaAnalysis {
  area: string;
  display_name: string;
  description: string;
  yearly_data: Array<{
    year: number;
    amount?: number;
    income?: number;
    expenses?: number;
    depreciation?: number;
    net?: number;
    short_term?: number;
    long_term?: number;
    loss_carryover?: number;
    niit?: number;
    amt?: number;
    self_employment?: number;
    total?: number;
    itemized_total?: number;
    standard?: number;
    method?: string;
    percent_of_agi?: number;
    agi?: number;
  }>;
  average: number;
  trend: 'up' | 'down' | 'stable';
  insights: string[];
  recommendations: string[];
}

interface TaxPlanningRecommendation {
  category: string;
  title: string;
  description: string;
  potential_savings: number | null;
  priority: 'low' | 'medium' | 'high';
}

interface TaxPlanningAnalysis {
  summary: {
    years_analyzed: number;
    total_taxes_paid: number | string;
    average_effective_rate: number | string;
    areas_analyzed: number;
    total_recommendations: number;
    total_potential_savings: number;
  };
  areas: TaxAreaAnalysis[];
  recommendations: TaxPlanningRecommendation[];
}

const AREA_ICONS: Record<string, React.ReactNode> = {
  retirement: <DollarSign size={20} />,
  rental: <Home size={20} />,
  charitable: <Heart size={20} />,
  capital_gains: <BarChart3 size={20} />,
  additional_taxes: <Shield size={20} />,
  deductions: <FileText size={20} />,
};

const AREA_COLORS: Record<string, string> = {
  retirement: '#00A3FF',
  rental: '#FFB800',
  charitable: '#10B981',
  capital_gains: '#8B5CF6',
  additional_taxes: '#EF4444',
  deductions: '#F59E0B',
};

export default function TaxPlanning() {
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<TaxPlanningAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedArea, setExpandedArea] = useState<string | null>(null);

  useEffect(() => {
    fetchAnalysis();
  }, []);

  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/v1/tax/planning/analysis', {
        headers: getAuthHeaders(),
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch tax planning analysis');
      }
      
      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value: number | string) => {
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(numValue || 0);
  };
  
  const formatRate = (value: number | string) => {
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    return (numValue || 0).toFixed(1);
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp size={16} className={styles.trendUp} />;
      case 'down':
        return <TrendingDown size={16} className={styles.trendDown} />;
      default:
        return <Minus size={16} className={styles.trendStable} />;
    }
  };

  const getPriorityClass = (priority: string) => {
    switch (priority) {
      case 'high':
        return styles.priorityHigh;
      case 'medium':
        return styles.priorityMedium;
      default:
        return styles.priorityLow;
    }
  };

  const getChartDataKey = (area: string) => {
    switch (area) {
      case 'rental':
        return 'net';
      case 'capital_gains':
        return 'net';
      case 'additional_taxes':
        return 'total';
      case 'deductions':
        return 'itemized_total';
      default:
        return 'amount';
    }
  };

  const renderAreaChart = (area: TaxAreaAnalysis) => {
    const dataKey = getChartDataKey(area.area);
    const color = AREA_COLORS[area.area] || '#00A3FF';
    
    return (
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={area.yearly_data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`gradient-${area.area}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis 
            dataKey="year" 
            stroke="#737373"
            tick={{ fill: '#737373', fontSize: 11 }}
          />
          <YAxis 
            stroke="#737373"
            tick={{ fill: '#737373', fontSize: 11 }}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={{
              background: 'rgba(20, 20, 20, 0.95)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '8px',
            }}
            formatter={(value: number) => [formatCurrency(value), area.display_name]}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            fill={`url(#gradient-${area.area})`}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    );
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={40} className={styles.spinner} />
          <p>Analyzing tax patterns...</p>
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
          <button className={styles.retryButton} onClick={fetchAnalysis}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return null;
  }

  return (
    <div className={styles.page}>
      <button className={styles.backButton} onClick={() => navigate('/tax')}>
        <ArrowLeft size={18} />
        Back to Tax Center
      </button>

      {/* Summary Hero */}
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.heroLabel}>Tax Planning Analysis</span>
          <h1 className={styles.heroTitle}>Opportunities & Recommendations</h1>
          <p className={styles.heroSubtitle}>
            Analysis of {analysis.summary.years_analyzed} years of tax data
          </p>
        </div>
        
        <div className={styles.summaryCards}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Total Taxes Paid</span>
            <span className={styles.summaryValue}>
              {formatCurrency(analysis.summary.total_taxes_paid)}
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Avg Effective Rate</span>
            <span className={styles.summaryValue}>
              {formatRate(analysis.summary.average_effective_rate)}%
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Potential Savings</span>
            <span className={`${styles.summaryValue} ${styles.savings}`}>
              {formatCurrency(analysis.summary.total_potential_savings)}
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>Recommendations</span>
            <span className={styles.summaryValue}>
              {analysis.summary.total_recommendations}
            </span>
          </div>
        </div>
      </div>

      {/* Top Recommendations */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          <Lightbulb size={20} />
          Top Recommendations
        </h2>
        <div className={styles.recommendationsGrid}>
          {analysis.recommendations
            .filter(r => r.priority === 'high')
            .slice(0, 4)
            .map((rec, index) => (
              <div key={index} className={styles.recommendationCard}>
                <div className={styles.recommendationHeader}>
                  <span className={`${styles.priorityBadge} ${getPriorityClass(rec.priority)}`}>
                    {rec.priority}
                  </span>
                  <span className={styles.categoryBadge}>{rec.category}</span>
                </div>
                <h3 className={styles.recommendationTitle}>{rec.title}</h3>
                <p className={styles.recommendationDesc}>{rec.description}</p>
                {rec.potential_savings && (
                  <div className={styles.savingsIndicator}>
                    <DollarSign size={14} />
                    Potential savings: {formatCurrency(rec.potential_savings)}
                  </div>
                )}
              </div>
            ))}
        </div>
      </section>

      {/* Analysis Areas */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          <BarChart3 size={20} />
          Analysis by Category
        </h2>
        <div className={styles.areasGrid}>
          {analysis.areas.map((area) => (
            <div 
              key={area.area} 
              className={`${styles.areaCard} ${expandedArea === area.area ? styles.expanded : ''}`}
            >
              <div 
                className={styles.areaHeader}
                onClick={() => setExpandedArea(expandedArea === area.area ? null : area.area)}
              >
                <div className={styles.areaIcon} style={{ color: AREA_COLORS[area.area] }}>
                  {AREA_ICONS[area.area]}
                </div>
                <div className={styles.areaInfo}>
                  <h3 className={styles.areaTitle}>{area.display_name}</h3>
                  <p className={styles.areaDesc}>{area.description}</p>
                </div>
                <div className={styles.areaTrend}>
                  {getTrendIcon(area.trend)}
                  <span className={styles.areaAvg}>
                    Avg: {formatCurrency(area.average)}
                  </span>
                </div>
                <ChevronRight 
                  size={20} 
                  className={`${styles.expandIcon} ${expandedArea === area.area ? styles.rotated : ''}`}
                />
              </div>
              
              {expandedArea === area.area && (
                <div className={styles.areaContent}>
                  <div className={styles.areaChart}>
                    {renderAreaChart(area)}
                  </div>
                  
                  {area.insights.length > 0 && (
                    <div className={styles.areaInsights}>
                      <h4>Insights</h4>
                      <ul>
                        {area.insights.map((insight, i) => (
                          <li key={i}>{insight}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {area.recommendations.length > 0 && (
                    <div className={styles.areaRecommendations}>
                      <h4>Recommendations</h4>
                      <ul>
                        {area.recommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* All Recommendations */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          <FileText size={20} />
          All Recommendations
        </h2>
        <div className={styles.allRecommendations}>
          {analysis.recommendations.map((rec, index) => (
            <div key={index} className={styles.recommendationRow}>
              <span className={`${styles.priorityDot} ${getPriorityClass(rec.priority)}`} />
              <div className={styles.recommendationRowContent}>
                <span className={styles.recommendationRowCategory}>{rec.category}</span>
                <span className={styles.recommendationRowTitle}>{rec.title}</span>
              </div>
              {rec.potential_savings && (
                <span className={styles.recommendationRowSavings}>
                  {formatCurrency(rec.potential_savings)}
                </span>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

