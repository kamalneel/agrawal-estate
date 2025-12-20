import { useState, useEffect } from 'react';
import { 
  Banknote,
  TrendingUp,
  ArrowRight,
  DollarSign,
  Shield,
  AlertTriangle,
  CheckCircle2,
  Info,
  RefreshCw,
  Settings,
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
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';
import styles from './BuyBorrowDie.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface YearlyProjection {
  year: number;
  age: number;
  ending_capital: number;
  cumulative_borrowing: number;
  cumulative_interest: number;
  total_debt: number;
  net_worth: number;
  margin_available: number;
  margin_utilization: number;
  is_safe: boolean;
}

interface ProjectionData {
  starting_capital: number;
  projections: YearlyProjection[];
  summary: {
    starting_capital: number;
    final_capital: number;
    capital_growth_multiple: number;
    total_borrowed: number;
    total_interest_paid: number;
    total_debt: number;
    final_net_worth: number;
    strategy_sustainable: boolean;
    final_margin_utilization: number;
  };
}

const formatCurrency = (value: number) => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const formatFullCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
};

export default function BuyBorrowDie() {
  const [projection, setProjection] = useState<ProjectionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'projection' | 'settings'>('projection');

  // Parameters
  const [monthlyBorrowing, setMonthlyBorrowing] = useState(20000);
  const [growthRate, setGrowthRate] = useState(8);
  const [interestRate, setInterestRate] = useState(5.25);

  useEffect(() => {
    fetchProjection();
  }, []);

  const fetchProjection = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/v1/strategies/buy-borrow-die/projection', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          annual_growth_rate: growthRate / 100,
          monthly_borrowing: monthlyBorrowing,
          borrowing_interest_rate: interestRate / 100,
          current_age: 45,
          end_age: 100,
          first_year_months: 11,
          margin_buffer_percent: 0.76,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setProjection(data);
    } catch (err) {
      console.error('Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load projection');
    } finally {
      setLoading(false);
    }
  };

  // Chart data
  const chartData = projection?.projections.map(p => ({
    age: p.age,
    year: p.year,
    'Portfolio': p.ending_capital,
    'Debt': p.total_debt,
    'Net Worth': p.net_worth,
    'Interest': p.cumulative_interest,
    margin: p.margin_utilization,
  })) || [];

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Banknote size={32} />
          </div>
          <div>
            <h1 className={styles.title}>Buy / Borrow / Die Strategy</h1>
            <p className={styles.subtitle}>
              A wealth preservation strategy to minimize lifetime capital gains taxes
            </p>
          </div>
        </div>
      </header>

      {/* Strategy Flow */}
      <div className={styles.strategyFlow}>
        <div className={styles.phaseCard}>
          <div className={styles.phaseIcon}><TrendingUp size={28} /></div>
          <h3 className={styles.phaseTitle}>BUY</h3>
          <p className={styles.phaseSubtitle}>Accumulate Assets</p>
        </div>
        <ArrowRight size={24} className={styles.flowArrow} />
        <div className={`${styles.phaseCard} ${styles.selected}`}>
          <div className={styles.phaseIcon}><Banknote size={28} /></div>
          <h3 className={styles.phaseTitle}>BORROW</h3>
          <p className={styles.phaseSubtitle}>Access Wealth</p>
        </div>
        <ArrowRight size={24} className={styles.flowArrow} />
        <div className={styles.phaseCard}>
          <div className={styles.phaseIcon}><Shield size={28} /></div>
          <h3 className={styles.phaseTitle}>DIE</h3>
          <p className={styles.phaseSubtitle}>Step-Up Basis</p>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'projection' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('projection')}
        >
          📊 Projection
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'settings' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          ⚙️ Settings
        </button>
      </div>

      {/* Main Content */}
      <div className={styles.projectionContent}>
        {loading && (
          <div className={styles.loadingState}>
            <RefreshCw size={32} className={styles.spinner} />
            <p>Calculating projection...</p>
          </div>
        )}

        {error && (
          <div className={styles.errorState}>
            <AlertTriangle size={32} />
            <p>{error}</p>
            <button onClick={fetchProjection}>Retry</button>
          </div>
        )}

        {!loading && !error && projection && activeTab === 'projection' && (
          <>
            {/* Summary Cards */}
            <div className={styles.summaryGrid}>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Starting Capital</span>
                <span className={styles.summaryValue}>{formatFullCurrency(projection.summary.starting_capital)}</span>
                <span className={styles.summaryNote}>Neel's + Jaya's Brokerage</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Final Portfolio (Age 100)</span>
                <span className={styles.summaryValue}>{formatFullCurrency(projection.summary.final_capital)}</span>
                <span className={styles.summaryNote}>{projection.summary.capital_growth_multiple}x growth</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Total Borrowed</span>
                <span className={styles.summaryValue}>{formatFullCurrency(projection.summary.total_borrowed)}</span>
                <span className={styles.summaryNote}>${(monthlyBorrowing / 1000).toFixed(0)}K/month × 55 years</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Total Interest Paid</span>
                <span className={styles.summaryValue}>{formatFullCurrency(projection.summary.total_interest_paid)}</span>
                <span className={styles.summaryNote}>at {interestRate}% rate</span>
              </div>
              <div className={`${styles.summaryCard} ${projection.summary.strategy_sustainable ? styles.success : styles.danger}`}>
                <span className={styles.summaryLabel}>Final Net Worth</span>
                <span className={styles.summaryValue}>{formatFullCurrency(projection.summary.final_net_worth)}</span>
                <span className={styles.summaryNote}>
                  {projection.summary.strategy_sustainable ? '✓ Strategy Sustainable' : '⚠️ Margin Call Risk'}
                </span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Final Margin Utilization</span>
                <span className={styles.summaryValue}>{projection.summary.final_margin_utilization.toFixed(1)}%</span>
                <span className={styles.summaryNote}>of 76% margin buffer</span>
              </div>
            </div>

            {/* Main Chart */}
            <div className={styles.chartCard}>
              <h3 className={styles.chartTitle}>Portfolio Growth vs. Debt Accumulation</h3>
              <p className={styles.chartSubtitle}>
                Age 45 to 100 • {growthRate}% annual growth • ${(monthlyBorrowing/1000).toFixed(0)}K/month borrowing • {interestRate}% interest
              </p>
              <div className={styles.chartContainer}>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="age" stroke="#888" />
                    <YAxis stroke="#888" tickFormatter={formatCurrency} />
                    <Tooltip 
                      formatter={(value: number, name: string) => [formatFullCurrency(value), name]}
                      labelFormatter={(age) => `Age ${age}`}
                    />
                    <Legend />
                    <Area type="monotone" dataKey="Portfolio" fill="rgba(16, 185, 129, 0.2)" stroke="#10B981" strokeWidth={2} />
                    <Line type="monotone" dataKey="Debt" stroke="#EF4444" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="Net Worth" stroke="#3B82F6" strokeWidth={3} dot={false} />
                    <Line type="monotone" dataKey="Interest" stroke="#F59E0B" strokeWidth={2} strokeDasharray="5 5" dot={false} />
                    <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Margin Chart */}
            <div className={styles.chartCard}>
              <h3 className={styles.chartTitle}>Margin Utilization Over Time</h3>
              <div className={styles.chartContainer}>
                <ResponsiveContainer width="100%" height={250}>
                  <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="age" stroke="#888" />
                    <YAxis stroke="#888" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                    <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, 'Margin Used']} />
                    <ReferenceLine y={100} stroke="#EF4444" strokeDasharray="5 5" />
                    <ReferenceLine y={80} stroke="#F59E0B" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="margin" fill="rgba(139, 92, 246, 0.3)" stroke="#8B5CF6" strokeWidth={2} name="Margin %" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Key Insight */}
            <div className={styles.insightCard}>
              <DollarSign size={24} className={styles.insightIcon} />
              <div>
                <h4 className={styles.insightTitle}>Key Tax Insight</h4>
                <p className={styles.insightText}>
                  By borrowing ${(monthlyBorrowing/1000).toFixed(0)}K/month instead of selling assets, you avoid capital gains taxes 
                  on {formatFullCurrency(projection.summary.total_borrowed)} of spending over 55 years. At a ~25% combined 
                  tax rate, that's approximately <strong>{formatFullCurrency(projection.summary.total_borrowed * 0.25)}</strong> in 
                  taxes never paid. When you pass, heirs receive the stepped-up basis and can sell assets 
                  to repay the {formatFullCurrency(projection.summary.total_debt)} debt tax-free.
                </p>
              </div>
            </div>
          </>
        )}

        {!loading && !error && activeTab === 'settings' && (
          <div className={styles.settingsCard}>
            <h3 className={styles.settingsTitle}>
              <Settings size={20} />
              Projection Parameters
            </h3>
            <div className={styles.settingsGrid}>
              <div className={styles.settingItem}>
                <label>Annual Growth Rate</label>
                <div className={styles.inputGroup}>
                  <input
                    type="number"
                    value={growthRate}
                    onChange={(e) => setGrowthRate(parseFloat(e.target.value))}
                    step="0.5"
                    min="0"
                    max="20"
                  />
                  <span>%</span>
                </div>
              </div>
              <div className={styles.settingItem}>
                <label>Monthly Borrowing</label>
                <div className={styles.inputGroup}>
                  <span>$</span>
                  <input
                    type="number"
                    value={monthlyBorrowing}
                    onChange={(e) => setMonthlyBorrowing(parseFloat(e.target.value))}
                    step="1000"
                    min="0"
                  />
                </div>
              </div>
              <div className={styles.settingItem}>
                <label>Interest Rate</label>
                <div className={styles.inputGroup}>
                  <input
                    type="number"
                    value={interestRate}
                    onChange={(e) => setInterestRate(parseFloat(e.target.value))}
                    step="0.25"
                    min="0"
                    max="15"
                  />
                  <span>%</span>
                </div>
              </div>
            </div>
            <button className={styles.applyButton} onClick={fetchProjection}>
              <RefreshCw size={18} />
              Recalculate Projection
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
