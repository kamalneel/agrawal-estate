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
  BarChart3,
  Calendar,
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

interface MonthlyActual {
  year: number;
  month: number;
  month_name: string;
  spending: number;
  income: number;
  options_income: number;
  dividend_income: number;  // Separate dividend income
  interest_income: number;  // Separate interest income (not including dividends)
  rental_income: number;  // Separate rental income
  salary_income: number;  // Salary only (not including rental)
  net_cash_flow: number;
  cumulative_net: number;
  cumulative_spending: number;
  cumulative_income: number;
}

interface ActualsData {
  monthly_data: MonthlyActual[];
  total_spending: number;
  total_income: number;
  total_options_income: number;
  total_interest_income: number;
  total_salary_income: number;
  net_position: number;
  monthly_salary: number;
  year: number;
  is_sustainable: boolean;
  months_of_data: number;
  annualized_spending: number;
  annualized_income: number;
  projected_annual_deficit: number;
}

interface YearSummary {
  year: number;
  total_income: number;
  total_spending: number;
  net_position: number;
  cumulative_gap: number;
  months_of_data: number;
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
  const [actuals, setActuals] = useState<ActualsData | null>(null);
  const [allYearsData, setAllYearsData] = useState<YearSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [actualsLoading, setActualsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'projection' | 'actuals' | 'settings'>('actuals');  // Default to Actuals

  // Year selection for Actuals
  const [selectedYear, setSelectedYear] = useState<number | 'all'>(2025); // Default to 2025, will update when years load
  const [availableYears, setAvailableYears] = useState<number[]>([2025]); // Will be updated from API
  const [isCumulative, setIsCumulative] = useState(true); // Default to cumulative view

  // Spending details modal
  const [showSpendingDetails, setShowSpendingDetails] = useState(false);
  const [spendingDetails, setSpendingDetails] = useState<{
    transactions: Array<{
      date: string;
      account: string;
      amount: number;
      description: string;
      type: string;
    }>;
    total_spending: number;
    transaction_count: number;
  } | null>(null);
  const [spendingDetailsLoading, setSpendingDetailsLoading] = useState(false);

  // Parameters
  const [monthlyBorrowing, setMonthlyBorrowing] = useState(20000);
  const [growthRate, setGrowthRate] = useState(8);
  const [interestRate, setInterestRate] = useState(5.25);

  useEffect(() => {
    fetchProjection();
    fetchAvailableYears();
  }, []);

  useEffect(() => {
    if (selectedYear === 'all') {
      fetchAllYearsData();
    } else {
      fetchActuals(selectedYear);
    }
  }, [selectedYear]);

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

  const fetchActuals = async (year: number) => {
    setActualsLoading(true);
    try {
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/actuals/${year}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setActuals(data);
    } catch (err) {
      console.error('Fetch actuals error:', err);
    } finally {
      setActualsLoading(false);
    }
  };

  const fetchAvailableYears = async () => {
    const currentYear = new Date().getFullYear();
    try {
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/actuals/years`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        const years = data.years || [currentYear];
        setAvailableYears(years);
        // If selected year is not in available years, select the first available
        if (years.length > 0 && !years.includes(selectedYear as number)) {
          setSelectedYear(years[0]);
        }
      }
    } catch (err) {
      console.error('Fetch available years error:', err);
      // Default to current year if API fails
      setAvailableYears([currentYear]);
    }
  };

  const fetchAllYearsData = async () => {
    setActualsLoading(true);
    try {
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/actuals/all-years`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setAllYearsData(data.yearly_summaries);
    } catch (err) {
      console.error('Fetch all years error:', err);
    } finally {
      setActualsLoading(false);
    }
  };

  const fetchSpendingDetails = async (year: number) => {
    setSpendingDetailsLoading(true);
    try {
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/spending-details/${year}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setSpendingDetails(data);
      setShowSpendingDetails(true);
    } catch (err) {
      console.error('Fetch spending details error:', err);
    } finally {
      setSpendingDetailsLoading(false);
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
          className={`${styles.tab} ${activeTab === 'actuals' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('actuals')}
        >
          📈 Actuals
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

        {activeTab === 'actuals' && (
          <>
            {/* Year Selector */}
            <div className={styles.yearSelector}>
              <Calendar size={18} />
              <span className={styles.yearLabel}>Year:</span>
              {availableYears.map(year => (
                <button
                  key={year}
                  className={`${styles.yearButton} ${selectedYear === year ? styles.activeYear : ''}`}
                  onClick={() => setSelectedYear(year)}
                >
                  {year}
                </button>
              ))}
              <button
                className={`${styles.yearButton} ${selectedYear === 'all' ? styles.activeYear : ''}`}
                onClick={() => setSelectedYear('all')}
              >
                All Years
              </button>
            </div>

            {actualsLoading && (
              <div className={styles.loadingState}>
                <RefreshCw size={32} className={styles.spinner} />
                <p>Loading actuals...</p>
              </div>
            )}

            {/* All Years View */}
            {!actualsLoading && selectedYear === 'all' && allYearsData && (
              <>
                <div className={styles.chartCard}>
                  <h3 className={styles.chartTitle}>Year-over-Year Comparison</h3>
                  <div className={styles.tableContainer}>
                    <table className={styles.actualsTable}>
                      <thead>
                        <tr>
                          <th>Year</th>
                          <th>Income</th>
                          <th>Spending</th>
                          <th>Annual Gap</th>
                          <th>Cumulative Gap</th>
                          <th>Months</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allYearsData.map((yearData) => (
                          <tr 
                            key={yearData.year} 
                            className={yearData.net_position >= 0 ? styles.positiveRow : styles.negativeRow}
                            onClick={() => setSelectedYear(yearData.year)}
                            style={{ cursor: 'pointer' }}
                          >
                            <td><strong>{yearData.year}</strong></td>
                            <td className={styles.income}>{formatFullCurrency(yearData.total_income)}</td>
                            <td className={styles.spending}>{formatFullCurrency(yearData.total_spending)}</td>
                            <td className={yearData.net_position >= 0 ? styles.positive : styles.negative}>
                              {yearData.net_position >= 0 ? '+' : ''}{formatFullCurrency(yearData.net_position)}
                            </td>
                            <td className={yearData.cumulative_gap >= 0 ? styles.positive : styles.negative}>
                              {yearData.cumulative_gap >= 0 ? '+' : ''}{formatFullCurrency(yearData.cumulative_gap)}
                            </td>
                            <td>{yearData.months_of_data}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className={styles.chartSubtitle} style={{ marginTop: '12px' }}>
                    Click on a year to see monthly breakdown
                  </p>
                </div>
              </>
            )}

            {/* Single Year View */}
            {!actualsLoading && selectedYear !== 'all' && actuals && (
              <>
                {/* Summary Cards */}
                <div className={styles.summaryGrid}>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Total Income ({selectedYear})</span>
                    <span className={`${styles.summaryValue} ${styles.positive}`}>{formatFullCurrency(actuals.total_income)}</span>
                    <span className={styles.summaryNote}>
                      Salary+Rental: {formatFullCurrency(actuals.total_salary_income)} • Options: {formatFullCurrency(actuals.total_options_income)} • Interest+Div: {formatFullCurrency(actuals.total_interest_income)}
                    </span>
                  </div>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Income from Option + dividend + interest + rental</span>
                    <span className={`${styles.summaryValue} ${styles.positive}`}>
                      {formatFullCurrency(
                        actuals.monthly_data.reduce((sum, m) => 
                          sum + m.options_income + m.dividend_income + m.interest_income + m.rental_income, 0
                        )
                      )}
                    </span>
                    <span className={styles.summaryNote}>
                      Options + Dividends + Interest + Rental (excludes salaries)
                    </span>
                  </div>
                  <div 
                    className={styles.summaryCard}
                    onClick={() => selectedYear !== 'all' && fetchSpendingDetails(selectedYear as number)}
                    style={{ cursor: 'pointer' }}
                    title="Click to see spending details"
                  >
                    <span className={styles.summaryLabel}>Total Spending ({selectedYear}) 🔍</span>
                    <span className={`${styles.summaryValue} ${styles.negative}`}>{formatFullCurrency(actuals.total_spending)}</span>
                    <span className={styles.summaryNote}>Click to see details • From brokerage accounts</span>
                  </div>
                  <div className={`${styles.summaryCard} ${actuals.projected_annual_deficit > 0 ? styles.danger : styles.success}`}>
                    <span className={styles.summaryLabel}>Projected Annual Gap</span>
                    <span className={styles.summaryValue}>
                      {actuals.projected_annual_deficit > 0 ? '-' : '+'}{formatFullCurrency(Math.abs(actuals.projected_annual_deficit))}
                    </span>
                    <span className={styles.summaryNote}>
                      {actuals.projected_annual_deficit > 0 ? 'Deficit if trend continues' : 'Surplus if trend continues'}
                    </span>
                  </div>
                </div>

                {/* Income vs Spending Bar Chart */}
                <div className={styles.chartCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <div>
                      <h3 className={styles.chartTitle}>Income vs Spending by Month</h3>
                      <p className={styles.chartSubtitle}>
                        Green bars = Income • Purple bars = Income from Option + dividend + interest + rental • Red bars = Spending
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button
                        onClick={() => setIsCumulative(false)}
                        style={{
                          padding: '8px 16px',
                          borderRadius: '6px',
                          border: '1px solid var(--color-border)',
                          backgroundColor: !isCumulative ? 'var(--color-accent)' : 'transparent',
                          color: !isCumulative ? 'var(--color-text-inverse)' : 'var(--color-text-secondary)',
                          cursor: 'pointer',
                          fontSize: '14px',
                          fontWeight: !isCumulative ? '600' : '400',
                          transition: 'all 0.2s',
                        }}
                      >
                        Non-Cumulative
                      </button>
                      <button
                        onClick={() => setIsCumulative(true)}
                        style={{
                          padding: '8px 16px',
                          borderRadius: '6px',
                          border: '1px solid var(--color-border)',
                          backgroundColor: isCumulative ? 'var(--color-accent)' : 'transparent',
                          color: isCumulative ? 'var(--color-text-inverse)' : 'var(--color-text-secondary)',
                          cursor: 'pointer',
                          fontSize: '14px',
                          fontWeight: isCumulative ? '600' : '400',
                          transition: 'all 0.2s',
                        }}
                      >
                        Cumulative
                      </button>
                    </div>
                  </div>
                  <div className={styles.chartContainer}>
                    <ResponsiveContainer width="100%" height={400}>
                      <ComposedChart 
                        data={(() => {
                          const filtered = actuals.monthly_data.filter(m => m.income > 0 || m.spending > 0);
                          let cumulativeIncome = 0;
                          let cumulativeIncomeFromOptions = 0;
                          let cumulativeSpending = 0;
                          
                          return filtered.map(m => {
                            // Income from Options + Dividends + Interest + Rental (excluding salaries)
                            const incomeFromOptionsDividendInterestRental = 
                              m.options_income + m.dividend_income + m.interest_income + m.rental_income;
                            
                            if (isCumulative) {
                              cumulativeIncome += m.income;
                              cumulativeIncomeFromOptions += incomeFromOptionsDividendInterestRental;
                              cumulativeSpending += m.spending;
                              
                              return {
                                ...m,
                                income: cumulativeIncome,
                                income_from_options_dividend_interest_rental: cumulativeIncomeFromOptions,
                                spending: cumulativeSpending,
                              };
                            } else {
                              return {
                                ...m,
                                income_from_options_dividend_interest_rental: incomeFromOptionsDividendInterestRental,
                              };
                            }
                          });
                        })()} 
                        margin={{ top: 20, right: 60, left: 20, bottom: 20 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                        <XAxis 
                          dataKey="month_name" 
                          stroke="#888" 
                          tick={{ fontSize: 12 }}
                          tickFormatter={(value) => value.substring(0, 3)}
                        />
                        <YAxis 
                          yAxisId="left"
                          stroke="#888" 
                          tickFormatter={formatCurrency}
                        />
                        <Tooltip 
                          formatter={(value: number, name: string) => [formatFullCurrency(value), name]}
                          labelFormatter={(label) => label}
                          contentStyle={{
                            backgroundColor: 'var(--color-bg-primary)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                          }}
                        />
                        <Legend />
                        <ReferenceLine yAxisId="left" y={0} stroke="#666" strokeDasharray="3 3" />
                        <Area 
                          yAxisId="left"
                          type="monotone" 
                          dataKey="income" 
                          fill="rgba(16, 185, 129, 0.3)" 
                          stroke="#10B981" 
                          strokeWidth={2}
                          name="Income"
                        />
                        <Area 
                          yAxisId="left"
                          type="monotone" 
                          dataKey="income_from_options_dividend_interest_rental" 
                          fill="rgba(168, 85, 247, 0.3)" 
                          stroke="#A855F7" 
                          strokeWidth={2}
                          name="Income from Option + dividend + interest + rental"
                        />
                        <Area 
                          yAxisId="left"
                          type="monotone" 
                          dataKey="spending" 
                          fill="rgba(239, 68, 68, 0.3)" 
                          stroke="#EF4444" 
                          strokeWidth={2}
                          name="Spending"
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Monthly Details Table */}
                <div className={styles.chartCard}>
                  <h3 className={styles.chartTitle}>Monthly Breakdown</h3>
                  <div className={styles.tableContainer}>
                    <table className={styles.actualsTable}>
                      <thead>
                        <tr>
                          <th>Month</th>
                          <th>Spending</th>
                          <th>Options</th>
                          <th>Salary+Rental</th>
                          <th>Int+Div</th>
                          <th>Total Income</th>
                          <th>Net</th>
                          <th>Cumulative</th>
                        </tr>
                      </thead>
                      <tbody>
                        {actuals.monthly_data.filter(m => m.income > 0 || m.spending > 0).map((month) => (
                          <tr key={month.month} className={month.net_cash_flow >= 0 ? styles.positiveRow : styles.negativeRow}>
                            <td>{month.month_name}</td>
                            <td className={styles.spending}>
                              {month.spending > 0 ? formatFullCurrency(month.spending) : '-'}
                            </td>
                            <td>{month.options_income > 0 ? formatFullCurrency(month.options_income) : '-'}</td>
                            <td>{month.salary_income > 0 ? formatFullCurrency(month.salary_income) : '-'}</td>
                            <td>{month.interest_income > 0 ? formatFullCurrency(month.interest_income) : '-'}</td>
                            <td className={styles.income}>{formatFullCurrency(month.income)}</td>
                            <td className={month.net_cash_flow >= 0 ? styles.positive : styles.negative}>
                              {month.net_cash_flow >= 0 ? '+' : ''}{formatFullCurrency(month.net_cash_flow)}
                            </td>
                            <td className={month.cumulative_net >= 0 ? styles.positive : styles.negative}>
                              {month.cumulative_net >= 0 ? '+' : ''}{formatFullCurrency(month.cumulative_net)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Data Source Info */}
                <div className={styles.insightCard}>
                  <Info size={24} className={styles.insightIcon} />
                  <div>
                    <h4 className={styles.insightTitle}>Data Sources</h4>
                    <p className={styles.insightText}>
                      <strong>Income:</strong> Options premiums, dividends, interest, salary, and rental income - 
                      same data as the Income page.<br/>
                      <strong>Spending:</strong> All money leaving brokerage accounts (withdrawals, credit card payments, transfers to spending).
                    </p>
                    <button 
                      className={styles.refreshButton}
                      onClick={fetchActuals}
                      style={{ marginTop: '12px' }}
                    >
                      <RefreshCw size={16} />
                      Refresh Data
                    </button>
                  </div>
                </div>
              </>
            )}
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

      {/* Spending Details Modal */}
      {showSpendingDetails && spendingDetails && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowSpendingDetails(false)}
        >
          <div 
            style={{
              backgroundColor: 'var(--color-bg-secondary)',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '800px',
              width: '90%',
              maxHeight: '80vh',
              overflow: 'auto',
              border: '1px solid var(--color-border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>Spending Details ({selectedYear})</h2>
              <button 
                onClick={() => setShowSpendingDetails(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: 'var(--color-text-secondary)',
                }}
              >
                ×
              </button>
            </div>
            
            <div style={{ marginBottom: '16px', padding: '12px', backgroundColor: 'var(--color-bg-tertiary)', borderRadius: '8px' }}>
              <strong>Total: {formatFullCurrency(spendingDetails.total_spending)}</strong>
              <span style={{ marginLeft: '16px', color: 'var(--color-text-secondary)' }}>
                {spendingDetails.transaction_count} transactions
              </span>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 8px', color: 'var(--color-text-secondary)' }}>Date</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', color: 'var(--color-text-secondary)' }}>Account</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', color: 'var(--color-text-secondary)' }}>Type</th>
                  <th style={{ textAlign: 'right', padding: '12px 8px', color: 'var(--color-text-secondary)' }}>Amount</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', color: 'var(--color-text-secondary)' }}>Description</th>
                </tr>
              </thead>
              <tbody>
                {spendingDetails.transactions.map((txn, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--color-border-light)' }}>
                    <td style={{ padding: '10px 8px' }}>{new Date(txn.date).toLocaleDateString()}</td>
                    <td style={{ padding: '10px 8px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '12px',
                        backgroundColor: txn.account.includes('Neel') ? 'rgba(59, 130, 246, 0.2)' : 'rgba(168, 85, 247, 0.2)',
                        color: txn.account.includes('Neel') ? '#60A5FA' : '#C084FC',
                      }}>
                        {txn.account}
                      </span>
                    </td>
                    <td style={{ padding: '10px 8px', color: 'var(--color-text-secondary)' }}>{txn.type}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: '#EF4444', fontWeight: '500' }}>
                      {formatFullCurrency(txn.amount)}
                    </td>
                    <td style={{ padding: '10px 8px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                      {txn.description.length > 40 ? txn.description.substring(0, 40) + '...' : txn.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Loading overlay for spending details */}
      {spendingDetailsLoading && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <RefreshCw size={32} className={styles.spinner} />
        </div>
      )}
    </div>
  );
}
