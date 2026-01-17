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

interface PredictedExpense {
  description: string;
  predicted_date: string;
  predicted_amount: number;
  confidence: number;
  frequency: string;
  historical_occurrences: number;
  amount_range: {
    min: number;
    max: number;
  };
}

interface ForecastedMonth {
  year: number;
  month: number;
  month_name: string;
  predicted_expenses: PredictedExpense[];
  total_predicted: number;
  num_predicted_expenses: number;
}

interface RecurringPattern {
  description: string;
  avg_amount: number;
  frequency: string;
  avg_day_of_month: number;
  confidence: number;
  occurrences: number;
}

interface ExpenseForecast {
  forecast_period: {
    start_month: ForecastedMonth | null;
    end_month: ForecastedMonth | null;
    months_ahead: number;
  };
  forecasted_months: ForecastedMonth[];
  summary: {
    total_recurring_expenses_identified: number;
    avg_monthly_recurring_spending: number;
    historical_years_analyzed: number;
    total_transactions_analyzed: number;
  };
  recurring_patterns: RecurringPattern[];
  error?: string;
  note?: string;
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
  const [forecast, setForecast] = useState<ExpenseForecast | null>(null);
  const [loading, setLoading] = useState(true);
  const [actualsLoading, setActualsLoading] = useState(false);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'projection' | 'actuals' | 'forecast' | 'settings'>('actuals');  // Default to Actuals

  // Year selection for Actuals
  const [selectedYear, setSelectedYear] = useState<number | 'all'>(2025); // Default to 2025, will update when years load
  const [availableYears, setAvailableYears] = useState<number[]>([2025]); // Will be updated from API
  const [isCumulative, setIsCumulative] = useState(true); // Default to cumulative view

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

  const fetchForecast = async (monthsAhead: number = 3, historicalYears: number = 2) => {
    setForecastLoading(true);
    try {
      const response = await fetch(
        `/api/v1/strategies/buy-borrow-die/expense-forecast?months_ahead=${monthsAhead}&historical_years=${historicalYears}`,
        { headers: getAuthHeaders() }
      );

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setForecast(data);
    } catch (err) {
      console.error('Fetch forecast error:', err);
      // Set empty forecast on error
      setForecast({
        forecast_period: { start_month: null, end_month: null, months_ahead: monthsAhead },
        forecasted_months: [],
        summary: {
          total_recurring_expenses_identified: 0,
          avg_monthly_recurring_spending: 0,
          historical_years_analyzed: historicalYears,
          total_transactions_analyzed: 0
        },
        recurring_patterns: [],
        error: 'Failed to load forecast',
        note: 'No expense data available for forecasting.'
      });
    } finally {
      setForecastLoading(false);
    }
  };

  // Fetch forecast when forecast tab is selected
  useEffect(() => {
    if (activeTab === 'forecast' && !forecast) {
      fetchForecast();
    }
  }, [activeTab]);

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
          className={`${styles.tab} ${activeTab === 'forecast' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('forecast')}
        >
          🔮 Forecast
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
                    <span className={styles.summaryLabel}>Total Income (2025)</span>
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
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Total Spending (2025)</span>
                    <span className={`${styles.summaryValue} ${styles.negative}`}>{formatFullCurrency(actuals.total_spending)}</span>
                    <span className={styles.summaryNote}>From brokerage account</span>
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

        {activeTab === 'forecast' && (
          <>
            {forecastLoading && (
              <div className={styles.loadingState}>
                <RefreshCw size={32} className={styles.spinner} />
                <p>Analyzing expense patterns...</p>
              </div>
            )}

            {!forecastLoading && forecast && (
              <>
                {/* Summary Cards */}
                <div className={styles.summaryGrid}>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Recurring Expenses Identified</span>
                    <span className={styles.summaryValue}>{forecast.summary.total_recurring_expenses_identified}</span>
                    <span className={styles.summaryNote}>Based on {forecast.summary.historical_years_analyzed} years of data</span>
                  </div>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Avg Monthly Recurring</span>
                    <span className={`${styles.summaryValue} ${styles.negative}`}>
                      {formatFullCurrency(forecast.summary.avg_monthly_recurring_spending)}
                    </span>
                    <span className={styles.summaryNote}>From {forecast.summary.total_transactions_analyzed} transactions</span>
                  </div>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Forecast Period</span>
                    <span className={styles.summaryValue}>{forecast.forecast_period.months_ahead} months</span>
                    <span className={styles.summaryNote}>
                      {forecast.forecasted_months[0]?.month_name} - {forecast.forecasted_months[forecast.forecasted_months.length - 1]?.month_name}
                    </span>
                  </div>
                </div>

                {/* Forecasted Expenses by Month */}
                <div className={styles.chartCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h3 className={styles.chartTitle}>Forecasted Expenses by Month</h3>
                    <button
                      className={styles.refreshButton}
                      onClick={() => fetchForecast()}
                      style={{ padding: '8px 16px', fontSize: '14px' }}
                    >
                      <RefreshCw size={16} />
                      Refresh Forecast
                    </button>
                  </div>

                  {forecast.forecasted_months.length === 0 ? (
                    <div className={styles.emptyState}>
                      <p>No forecast data available. Import more transaction history to enable forecasting.</p>
                    </div>
                  ) : (
                    <div className={styles.tableContainer}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Month</th>
                            <th>Expense</th>
                            <th>Predicted Date</th>
                            <th>Amount</th>
                            <th>Confidence</th>
                            <th>Frequency</th>
                            <th>Occurrences</th>
                          </tr>
                        </thead>
                        <tbody>
                          {forecast.forecasted_months.map((month) => (
                            month.predicted_expenses.map((expense, idx) => (
                              <tr key={`${month.month}-${idx}`}>
                                {idx === 0 && (
                                  <td rowSpan={month.predicted_expenses.length} style={{
                                    fontWeight: 'bold',
                                    borderRight: '1px solid rgba(255,255,255,0.1)',
                                    verticalAlign: 'top',
                                    paddingTop: '16px'
                                  }}>
                                    <div>
                                      {month.month_name} {month.year}
                                      <div style={{ fontSize: '0.85em', color: '#a3a3a3', marginTop: '4px' }}>
                                        Total: {formatFullCurrency(month.total_predicted)}
                                      </div>
                                    </div>
                                  </td>
                                )}
                                <td style={{ fontSize: '0.9em' }}>{expense.description}</td>
                                <td>{new Date(expense.predicted_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
                                <td className={styles.spending}>
                                  {formatFullCurrency(expense.predicted_amount)}
                                  {expense.amount_range && (
                                    <div style={{ fontSize: '0.75em', color: '#737373' }}>
                                      Range: {formatCurrency(expense.amount_range.min)} - {formatCurrency(expense.amount_range.max)}
                                    </div>
                                  )}
                                </td>
                                <td>
                                  <div style={{
                                    display: 'inline-block',
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.85em',
                                    backgroundColor: expense.confidence >= 70 ? 'rgba(16, 185, 129, 0.2)' :
                                                     expense.confidence >= 50 ? 'rgba(255, 184, 0, 0.2)' :
                                                     'rgba(239, 68, 68, 0.2)',
                                    color: expense.confidence >= 70 ? '#10B981' :
                                           expense.confidence >= 50 ? '#FFB800' :
                                           '#EF4444'
                                  }}>
                                    {expense.confidence.toFixed(0)}%
                                  </div>
                                </td>
                                <td style={{ textTransform: 'capitalize' }}>{expense.frequency}</td>
                                <td style={{ textAlign: 'center' }}>{expense.historical_occurrences}</td>
                              </tr>
                            ))
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Recurring Patterns */}
                {forecast.recurring_patterns.length > 0 && (
                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Identified Recurring Patterns</h3>
                    <p className={styles.chartSubtitle}>
                      These expense patterns were identified from your transaction history
                    </p>
                    <div className={styles.tableContainer}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Description</th>
                            <th>Avg Amount</th>
                            <th>Frequency</th>
                            <th>Avg Day</th>
                            <th>Confidence</th>
                            <th>Occurrences</th>
                          </tr>
                        </thead>
                        <tbody>
                          {forecast.recurring_patterns
                            .sort((a, b) => b.avg_amount - a.avg_amount)
                            .map((pattern, idx) => (
                              <tr key={idx}>
                                <td style={{ fontWeight: '500' }}>{pattern.description}</td>
                                <td className={styles.spending}>{formatFullCurrency(pattern.avg_amount)}</td>
                                <td style={{ textTransform: 'capitalize' }}>{pattern.frequency}</td>
                                <td>Day {pattern.avg_day_of_month}</td>
                                <td>
                                  <div style={{
                                    display: 'inline-block',
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.85em',
                                    backgroundColor: pattern.confidence >= 70 ? 'rgba(16, 185, 129, 0.2)' :
                                                     pattern.confidence >= 50 ? 'rgba(255, 184, 0, 0.2)' :
                                                     'rgba(239, 68, 68, 0.2)',
                                    color: pattern.confidence >= 70 ? '#10B981' :
                                           pattern.confidence >= 50 ? '#FFB800' :
                                           '#EF4444'
                                  }}>
                                    {pattern.confidence.toFixed(0)}%
                                  </div>
                                </td>
                                <td style={{ textAlign: 'center' }}>{pattern.occurrences}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Info Card */}
                <div className={styles.insightCard}>
                  <Info size={24} className={styles.insightIcon} />
                  <div>
                    <h4 className={styles.insightTitle}>How Forecasting Works</h4>
                    <p className={styles.insightText}>
                      The system analyzes your historical Robinhood spending transactions to identify recurring patterns.
                      Expenses with similar descriptions and amounts (within 15% tolerance) are grouped together.
                      <br/><br/>
                      <strong>Confidence Score:</strong> Based on consistency of amounts and timing. Higher scores mean more predictable expenses.
                      <br/>
                      <strong>Frequency:</strong> Determined from the gaps between occurrences (monthly, quarterly, or annual).
                      <br/><br/>
                      {forecast.error && (
                        <span style={{ color: '#EF4444' }}>⚠️ {forecast.error}</span>
                      )}
                      {forecast.note && (
                        <span style={{ color: '#FFB800' }}>💡 {forecast.note}</span>
                      )}
                    </p>
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
    </div>
  );
}
