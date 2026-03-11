import { useState, useEffect } from 'react';
import {
  Banknote,
  TrendingUp,
  ArrowRight,
  DollarSign,
  Shield,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import {
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

interface TimelineDataPoint {
  month: string;
  label: string;
  total_capital: number | null;
  margin_available: number | null;
  cumulative_debt: number | null;
  net_worth: number | null;
  proj_total_capital?: number | null;
  proj_margin_available?: number | null;
  proj_cumulative_debt?: number | null;
  proj_net_worth?: number | null;
  proj_monthly_income?: number | null;
  is_actual: boolean;
}

interface IncomeBreakdownRow {
  month: string;
  label: string;
  spending: number;
  options: number;
  dividends: number;
  interest: number;
  rental: number;
  salary: number;
  total_income: number;
  net: number;
}

interface TimelineResponse {
  data_points: TimelineDataPoint[];
  last_actual_month: string | null;
  time_range: string;
  assumptions: {
    annual_growth_rate_pct: number;
    annual_interest_rate_pct: number;
    avg_monthly_spending: number;
    margin_ltv_pct: number;
    income_offset: boolean;
    options_yield_pct: number;
    avg_fixed_income: number;
    fixed_income_breakdown: {
      interest: number;
      dividends: number;
      rental: number;
      salary: number;
    };
  };
  summary: {
    current_total_capital: number;
    current_margin_available: number;
    current_cumulative_debt: number;
    current_net_worth: number;
    current_utilization_pct: number;
    capital_account_breakdown: { name: string; value: number }[];
    final_total_capital: number;
    final_margin_available: number;
    final_cumulative_debt: number;
    final_net_worth: number;
  };
  income_breakdown: IncomeBreakdownRow[];
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
  // Timeline chart state
  const [timelineData, setTimelineData] = useState<TimelineResponse | null>(null);
  const [timelineRange, setTimelineRange] = useState<'data' | '5y' | '10y' | '20y' | '30y' | 'all'>('data');
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [incomeOffset, setIncomeOffset] = useState(false);

  // Configurable assumptions (displayed as percentages, sent as decimals)
  const [growthRatePct, setGrowthRatePct] = useState(8);
  const [marginRatePct, setMarginRatePct] = useState(5);
  const [marginLtvPct, setMarginLtvPct] = useState(70);
  const [optionsYieldPct, setOptionsYieldPct] = useState(1);

  // Assumptions vs Reality state — separate drill-down for each chart
  const [growthPeriod, setGrowthPeriod] = useState<'year' | 'month' | 'week'>('month');
  const [growthDrillYear, setGrowthDrillYear] = useState<number | undefined>();
  const [growthDrillMonth, setGrowthDrillMonth] = useState<number | undefined>();
  const [growthMetrics, setGrowthMetrics] = useState<any[] | null>(null);

  const [yieldPeriod, setYieldPeriod] = useState<'year' | 'month' | 'week'>('month');
  const [yieldDrillYear, setYieldDrillYear] = useState<number | undefined>();
  const [yieldDrillMonth, setYieldDrillMonth] = useState<number | undefined>();
  const [yieldMetrics, setYieldMetrics] = useState<any[] | null>(null);

  const [borrowPeriod, setBorrowPeriod] = useState<'year' | 'month'>('month');
  const [borrowDrillYear, setBorrowDrillYear] = useState<number | undefined>();
  const [borrowMetrics, setBorrowMetrics] = useState<any[] | null>(null);

  const [assumptionSummary, setAssumptionSummary] = useState<any | null>(null);
  const [, setAssumptionLoading] = useState(false);
  const [assumptionComputing, setAssumptionComputing] = useState(false);

  useEffect(() => {
    fetchTimeline();
    fetchMetricsFor('portfolio_growth', growthPeriod, growthDrillYear, growthDrillMonth, setGrowthMetrics);
    fetchMetricsFor('options_yield', yieldPeriod, yieldDrillYear, yieldDrillMonth, setYieldMetrics);
    fetchMetricsFor('margin_borrowing', borrowPeriod, borrowDrillYear, undefined, setBorrowMetrics);
    fetchAssumptionSummary();
  }, []);

  const fetchTimeline = async (range?: 'data' | '5y' | '10y' | '20y' | '30y' | 'all', offset?: boolean) => {
    const r = range ?? timelineRange;
    const io = offset ?? incomeOffset;
    setTimelineLoading(true);
    try {
      const params = new URLSearchParams({
        time_range: r,
        income_offset: String(io),
        growth_rate: String(growthRatePct / 100),
        margin_rate: String(marginRatePct / 100),
        margin_ltv: String(marginLtvPct / 100),
        options_yield: String(optionsYieldPct / 100),
      });
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/timeline?${params}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) throw new Error(`API error: ${response.status}`);
      const data = await response.json();
      setTimelineData(data);
    } catch (err) {
      console.error('Timeline fetch error:', err);
    } finally {
      setTimelineLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTimeline(timelineRange, incomeOffset);
    }, 400);
    return () => clearTimeout(timer);
  }, [timelineRange, incomeOffset, growthRatePct, marginRatePct, marginLtvPct, optionsYieldPct]);

  // Refresh assumptions data when drill-down changes
  useEffect(() => {
    fetchMetricsFor('portfolio_growth', growthPeriod, growthDrillYear, growthDrillMonth, setGrowthMetrics);
  }, [growthPeriod, growthDrillYear, growthDrillMonth]);

  useEffect(() => {
    fetchMetricsFor('options_yield', yieldPeriod, yieldDrillYear, yieldDrillMonth, setYieldMetrics);
  }, [yieldPeriod, yieldDrillYear, yieldDrillMonth]);

  useEffect(() => {
    fetchMetricsFor('margin_borrowing', borrowPeriod, borrowDrillYear, undefined, setBorrowMetrics);
  }, [borrowPeriod, borrowDrillYear]);

  const fetchMetricsFor = async (
    metricType: string, periodType: string, year: number | undefined, month: number | undefined,
    setter: (data: any[]) => void,
  ) => {
    setAssumptionLoading(true);
    try {
      const params = new URLSearchParams({ metric_type: metricType, period_type: periodType });
      if (year) params.set('year', String(year));
      if (month) params.set('month', String(month));
      const response = await fetch(`/api/v1/strategies/buy-borrow-die/assumptions/metrics?${params}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) throw new Error('Failed to load metrics');
      const data = await response.json();
      setter(data.metrics);
    } catch (err) {
      console.error('Assumptions fetch error:', err);
      setter([]);
    } finally {
      setAssumptionLoading(false);
    }
  };

  const fetchAssumptionSummary = async () => {
    try {
      const response = await fetch('/api/v1/strategies/buy-borrow-die/assumptions/summary', {
        headers: getAuthHeaders(),
      });
      if (!response.ok) throw new Error('Failed to load summary');
      setAssumptionSummary(await response.json());
    } catch (err) {
      console.error('Summary fetch error:', err);
    }
  };

  const computeAssumptions = async () => {
    setAssumptionComputing(true);
    try {
      const response = await fetch('/api/v1/strategies/buy-borrow-die/assumptions/compute?force=true', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      });
      if (!response.ok) throw new Error('Compute failed');
      // Refresh all charts + summary
      await Promise.all([
        fetchMetricsFor('portfolio_growth', growthPeriod, growthDrillYear, growthDrillMonth, setGrowthMetrics),
        fetchMetricsFor('options_yield', yieldPeriod, yieldDrillYear, yieldDrillMonth, setYieldMetrics),
        fetchMetricsFor('margin_borrowing', borrowPeriod, borrowDrillYear, undefined, setBorrowMetrics),
        fetchAssumptionSummary(),
      ]);
    } catch (err) {
      console.error('Compute error:', err);
    } finally {
      setAssumptionComputing(false);
    }
  };

  const handleDrillDown = (
    entry: any, periodType: string,
    setDrillYear: (v: number | undefined) => void,
    setDrillMonth: (v: number | undefined) => void,
    setPeriod: (v: 'year' | 'month' | 'week') => void,
  ) => {
    if (periodType === 'year' && entry?.period_start) {
      setDrillYear(parseInt(entry.period_start.substring(0, 4)));
      setDrillMonth(undefined);
      setPeriod('month');
    } else if (periodType === 'month' && entry?.period_start) {
      setDrillYear(parseInt(entry.period_start.substring(0, 4)));
      setDrillMonth(parseInt(entry.period_start.substring(5, 7)));
      setPeriod('week');
    }
  };

  const handleBreadcrumb = (
    level: 'year' | 'month',
    setPeriod: (v: 'year' | 'month' | 'week') => void,
    setDrillYear: (v: number | undefined) => void,
    setDrillMonth: (v: number | undefined) => void,
  ) => {
    if (level === 'year') {
      setPeriod('year');
      setDrillYear(undefined);
      setDrillMonth(undefined);
    } else {
      setPeriod('month');
      setDrillMonth(undefined);
    }
  };

  // Determine x-axis interval: show yearly ticks for projections, every month for actuals-only
  const timelineXInterval = timelineRange === 'all' ? 23 : (timelineRange === '30y' || timelineRange === '20y') ? 23 : timelineRange !== 'data' ? 11 : 0;
  const useLogScale = timelineRange === 'all';
  const logTicks = [10000, 100000, 1000000, 10000000, 100000000];

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

      {/* Main Content */}
      <div className={styles.projectionContent}>

        {/* ═══════════════ Section 1: BBD Timeline ═══════════════ */}
        <div className={styles.section}>
          <h2 className={styles.sectionHeader}>Buy, Borrow, Die — Timeline</h2>
          <p className={styles.sectionSubtitle}>Capital, margin, and debt over time</p>

          {/* Time Range Selector + Income Toggle */}
          <div className={styles.timelineControls}>
            <div className={styles.yearSelector}>
              {([['data', 'Actuals Only'], ['5y', 'Next 5 Years'], ['10y', 'Next 10 Years'], ['20y', 'Next 20 Years'], ['30y', 'Next 30 Years'], ['all', 'To Age 100']] as const).map(([key, label]) => (
                <button
                  key={key}
                  className={`${styles.yearButton} ${timelineRange === key ? styles.activeYear : ''}`}
                  onClick={() => setTimelineRange(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className={styles.incomeToggle}>
              <span>Offset by Income</span>
              <button
                className={`${styles.yearButton} ${incomeOffset ? styles.activeYear : ''}`}
                onClick={() => setIncomeOffset(!incomeOffset)}
              >
                {incomeOffset ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

          {/* Assumptions Settings */}
          {timelineRange !== 'data' && (
            <div className={styles.inlineSettingsRow}>
              <div className={styles.inlineSettingItem}>
                <label>Growth Rate</label>
                <div className={styles.inlineSettingInput}>
                  <input
                    type="number"
                    value={growthRatePct}
                    onChange={(e) => setGrowthRatePct(Number(e.target.value))}
                    step={0.5}
                    min={0}
                    max={20}
                  />
                  <span>%/yr</span>
                </div>
              </div>
              <div className={styles.inlineSettingItem}>
                <label>Margin Interest</label>
                <div className={styles.inlineSettingInput}>
                  <input
                    type="number"
                    value={marginRatePct}
                    onChange={(e) => setMarginRatePct(Number(e.target.value))}
                    step={0.5}
                    min={0}
                    max={20}
                  />
                  <span>%/yr</span>
                </div>
              </div>
              <div className={styles.inlineSettingItem}>
                <label>Margin LTV</label>
                <div className={styles.inlineSettingInput}>
                  <input
                    type="number"
                    value={marginLtvPct}
                    onChange={(e) => setMarginLtvPct(Number(e.target.value))}
                    step={5}
                    min={10}
                    max={90}
                  />
                  <span>%</span>
                </div>
              </div>
              {incomeOffset && (
                <div className={styles.inlineSettingItem}>
                  <label>Options Yield</label>
                  <div className={styles.inlineSettingInput}>
                    <input
                      type="number"
                      value={optionsYieldPct}
                      onChange={(e) => setOptionsYieldPct(Number(e.target.value))}
                      step={0.1}
                      min={0}
                      max={5}
                    />
                    <span>%/mo</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {timelineLoading && (
            <div className={styles.loadingState}>
              <RefreshCw size={32} className={styles.spinner} />
              <p>Loading timeline...</p>
            </div>
          )}

          {!timelineLoading && timelineData && timelineData.data_points.length > 0 && (
            <>
              {/* Summary Cards */}
              <div className={styles.summaryGrid}>
                <div className={styles.summaryCard} title={timelineData.summary.capital_account_breakdown.map(a => `${a.name}: ${formatFullCurrency(a.value)}`).join('\n')}>
                  <span className={styles.summaryLabel}>Total Capital</span>
                  <span className={styles.summaryValue}>{formatFullCurrency(timelineData.summary.current_total_capital)}</span>
                  <span className={styles.summaryNote}>Taxable accounts only</span>
                </div>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryLabel}>Margin Available</span>
                  <span className={styles.summaryValue}>{formatFullCurrency(timelineData.summary.current_margin_available)}</span>
                  <span className={styles.summaryNote}>{timelineData.assumptions.margin_ltv_pct}% LTV</span>
                </div>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryLabel}>Cumulative Debt</span>
                  <span className={styles.summaryValue}>{formatFullCurrency(timelineData.summary.current_cumulative_debt)}</span>
                  <span className={styles.summaryNote}>{timelineData.summary.current_utilization_pct.toFixed(1)}% utilization</span>
                </div>
                {timelineRange !== 'data' && (
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Projected Final Net Worth</span>
                    <span className={styles.summaryValue}>{formatFullCurrency(timelineData.summary.final_net_worth)}</span>
                    <span className={styles.summaryNote}>
                      {timelineData.assumptions.annual_growth_rate_pct}% growth, {timelineData.assumptions.annual_interest_rate_pct}% interest
                    </span>
                  </div>
                )}
              </div>

              {/* Timeline Chart */}
              <div className={styles.chartCard}>
                <h3 className={styles.chartTitle}>Capital, Margin & Debt Timeline</h3>
                <p className={styles.chartSubtitle}>
                  {timelineRange === 'data'
                    ? 'Showing actual data only'
                    : `Solid = actual, dashed = projected (${timelineData.assumptions.annual_growth_rate_pct}% growth, ${formatCurrency(timelineData.assumptions.avg_monthly_spending)}/mo spending, ${timelineData.assumptions.annual_interest_rate_pct}% interest${timelineData.assumptions.income_offset ? `, income = ${timelineData.assumptions.options_yield_pct}%/mo yield + ${formatCurrency(timelineData.assumptions.fixed_income_breakdown?.interest ?? 0)} int + ${formatCurrency(timelineData.assumptions.fixed_income_breakdown?.dividends ?? 0)} div + ${formatCurrency(timelineData.assumptions.fixed_income_breakdown?.rental ?? 0)} rental + ${formatCurrency(timelineData.assumptions.fixed_income_breakdown?.salary ?? 0)} salary` : ''})`
                  }
                </p>
                <div className={styles.chartContainer}>
                  <ResponsiveContainer width="100%" height={400}>
                    <ComposedChart data={timelineData.data_points} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis
                        dataKey="label"
                        stroke="#888"
                        interval={timelineXInterval}
                        tickFormatter={(label: string) => {
                          // For projection ranges, show just the year (e.g. "2030")
                          if (timelineRange !== 'data') {
                            const parts = label.split(' ');
                            return parts.length > 1 ? parts[1] : label;
                          }
                          return label;
                        }}
                        angle={0}
                        textAnchor="middle"
                        height={30}
                        fontSize={12}
                      />
                      <YAxis
                        stroke="#888"
                        tickFormatter={formatCurrency}
                        scale={useLogScale ? 'log' : 'linear'}
                        domain={useLogScale ? [10000, 'auto'] : [0, 'auto']}
                        ticks={useLogScale ? logTicks : undefined}
                        allowDataOverflow={useLogScale}
                      />
                      <Tooltip
                        content={({ active, payload, label }: any) => {
                          if (!active || !payload?.length) return null;
                          const point = payload[0]?.payload;
                          const yr = parseInt(point?.month?.substring(0, 4) || '0');
                          const birthYear = new Date().getFullYear() - 45;
                          const age = yr - birthYear;
                          const nameMap: Record<string, string> = {
                            total_capital: 'Total Capital',
                            margin_available: 'Margin Available',
                            cumulative_debt: 'Cumulative Debt',
                            net_worth: 'Net Worth',
                            proj_total_capital: 'Total Capital (proj)',
                            proj_margin_available: 'Margin Available (proj)',
                            proj_cumulative_debt: 'Cumulative Debt (proj)',
                            proj_net_worth: 'Net Worth (proj)',
                          };
                          const colorMap: Record<string, string> = {
                            total_capital: '#10B981', proj_total_capital: '#10B981',
                            margin_available: '#3B82F6', proj_margin_available: '#3B82F6',
                            cumulative_debt: '#EF4444', proj_cumulative_debt: '#EF4444',
                            net_worth: '#F59E0B', proj_net_worth: '#F59E0B',
                          };
                          const assumptions = timelineData?.assumptions;
                          const isProjected = !point?.is_actual;
                          const projIncome = point?.proj_monthly_income;
                          const actualIncome = point?.actual_monthly_income;
                          const cumulativeIncome = point?.cumulative_income;
                          return (
                            <div className={styles.customTooltip}>
                              <p className={styles.tooltipTitle}>{label} — Age {age}</p>
                              <div className={styles.tooltipContent}>
                                {payload.filter((p: any) => {
                                  if (p.value == null) return false;
                                  // On the bridge point (actual month with projected fields),
                                  // skip proj_ keys to avoid duplicate rows
                                  if (point?.is_actual && p.dataKey.startsWith('proj_')) return false;
                                  return true;
                                }).map((p: any, i: number) => (
                                  <p key={i} style={{ color: colorMap[p.dataKey] || '#ccc' }}>
                                    {nameMap[p.dataKey] || p.dataKey}: {formatCurrency(p.value)}
                                  </p>
                                ))}
                                {/* Actual month spending & income info */}
                                {!isProjected && (
                                  <div style={{ borderTop: '1px solid var(--color-border)', marginTop: '6px', paddingTop: '6px' }}>
                                    {point?.actual_monthly_spending != null && point.actual_monthly_spending > 0 && (
                                      <p style={{ color: '#EF4444', fontSize: '11px' }}>
                                        Spending this month: {formatFullCurrency(point.actual_monthly_spending)}
                                      </p>
                                    )}
                                    {assumptions?.income_offset && actualIncome != null && (
                                      <p style={{ color: '#10B981', fontSize: '11px' }}>
                                        Income this month: {formatFullCurrency(actualIncome)}
                                      </p>
                                    )}
                                  </div>
                                )}
                                {/* Projected month income info */}
                                {isProjected && assumptions && (
                                  <>
                                    <p style={{ borderTop: '1px solid var(--color-border)', marginTop: '6px', paddingTop: '6px', color: '#888', fontSize: '11px' }}>
                                      Spending: {formatCurrency(assumptions.avg_monthly_spending)}/mo
                                    </p>
                                    {assumptions.income_offset && projIncome != null && (
                                      <p style={{ color: '#10B981', fontSize: '11px' }}>
                                        Income: {formatCurrency(projIncome)}/mo ({assumptions.options_yield_pct}% yield + {formatCurrency(assumptions.fixed_income_breakdown?.interest ?? 0)} int + {formatCurrency(assumptions.fixed_income_breakdown?.dividends ?? 0)} div + {formatCurrency(assumptions.fixed_income_breakdown?.rental ?? 0)} rental + {formatCurrency(assumptions.fixed_income_breakdown?.salary ?? 0)} salary)
                                      </p>
                                    )}
                                    {assumptions.income_offset && projIncome != null && (
                                      <p style={{ color: '#ccc', fontSize: '11px', fontWeight: 600 }}>
                                        Net borrowing: {formatCurrency(Math.max(0, assumptions.avg_monthly_spending - projIncome))}/mo
                                      </p>
                                    )}
                                  </>
                                )}
                              </div>
                            </div>
                          );
                        }}
                      />
                      <Legend
                        formatter={(value: string) => {
                          const nameMap: Record<string, string> = {
                            total_capital: 'Total Capital',
                            margin_available: 'Margin Available',
                            cumulative_debt: 'Cumulative Debt',
                            net_worth: 'Net Worth',
                          };
                          return nameMap[value] || value;
                        }}
                      />
                      {/* Actual lines (solid) */}
                      <Line type="monotone" dataKey="total_capital" stroke="#10B981" strokeWidth={2} dot={false} connectNulls={false} />
                      <Line type="monotone" dataKey="margin_available" stroke="#3B82F6" strokeWidth={2} dot={false} connectNulls={false} />
                      <Line type="monotone" dataKey="cumulative_debt" stroke="#EF4444" strokeWidth={2} dot={false} connectNulls={false} />
                      <Line type="monotone" dataKey="net_worth" stroke="#F59E0B" strokeWidth={2} dot={false} connectNulls={false} />
                      {/* Projected lines (dashed, same colors) */}
                      {timelineRange !== 'data' && (
                        <>
                          <Line type="monotone" dataKey="proj_total_capital" stroke="#10B981" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} legendType="none" />
                          <Line type="monotone" dataKey="proj_margin_available" stroke="#3B82F6" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} legendType="none" />
                          <Line type="monotone" dataKey="proj_cumulative_debt" stroke="#EF4444" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} legendType="none" />
                          <Line type="monotone" dataKey="proj_net_worth" stroke="#F59E0B" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} legendType="none" />
                        </>
                      )}
                      {/* "Now" reference line at actual→projected transition */}
                      {timelineRange !== 'data' && timelineData.last_actual_month && (
                        <ReferenceLine
                          x={timelineData.data_points.find(d => d.month === timelineData.last_actual_month)?.label}
                          stroke="#888"
                          strokeDasharray="3 3"
                          label={{ value: 'Now', position: 'top', fill: '#888', fontSize: 12 }}
                        />
                      )}
                      <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Monthly Income Breakdown Table */}
              {incomeOffset && timelineData.income_breakdown && timelineData.income_breakdown.length > 0 && (
                <div className={styles.tableContainer}>
                  <h4 style={{ marginBottom: '0.5rem', color: 'var(--color-text-secondary)' }}>Monthly Income Breakdown</h4>
                  <table className={styles.actualsTable}>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th>Spending</th>
                        <th>Options</th>
                        <th>Dividends</th>
                        <th>Interest</th>
                        <th>Rental</th>
                        <th>Salary</th>
                        <th>Total Income</th>
                        <th>Net</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timelineData.income_breakdown.map((row) => (
                        <tr key={row.month} className={row.net >= 0 ? styles.positiveRow : styles.negativeRow}>
                          <td>{row.label}</td>
                          <td className={styles.spending}>{formatFullCurrency(row.spending)}</td>
                          <td>{formatFullCurrency(row.options)}</td>
                          <td>{formatFullCurrency(row.dividends)}</td>
                          <td>{formatFullCurrency(row.interest)}</td>
                          <td>{formatFullCurrency(row.rental)}</td>
                          <td>{formatFullCurrency(row.salary)}</td>
                          <td className={styles.income}>{formatFullCurrency(row.total_income)}</td>
                          <td className={row.net >= 0 ? styles.income : styles.spending}>
                            {formatFullCurrency(row.net)}
                          </td>
                        </tr>
                      ))}
                      {/* Totals row */}
                      <tr style={{ fontWeight: 'bold', borderTop: '2px solid var(--color-border)' }}>
                        <td>Total</td>
                        <td className={styles.spending}>
                          {formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.spending, 0))}
                        </td>
                        <td>{formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.options, 0))}</td>
                        <td>{formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.dividends, 0))}</td>
                        <td>{formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.interest, 0))}</td>
                        <td>{formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.rental, 0))}</td>
                        <td>{formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.salary, 0))}</td>
                        <td className={styles.income}>
                          {formatFullCurrency(timelineData.income_breakdown.reduce((s, r) => s + r.total_income, 0))}
                        </td>
                        {(() => {
                          const totalNet = timelineData.income_breakdown.reduce((s, r) => s + r.net, 0);
                          return (
                            <td className={totalNet >= 0 ? styles.income : styles.spending}>
                              {formatFullCurrency(totalNet)}
                            </td>
                          );
                        })()}
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {/* Key Insight */}
              <div className={styles.insightCard}>
                <DollarSign size={24} className={styles.insightIcon} />
                <div>
                  <h4 className={styles.insightTitle}>Key Tax Insight</h4>
                  <p className={styles.insightText}>
                    By borrowing against your portfolio instead of selling assets, you avoid capital gains taxes
                    on all spending. At a ~25% combined tax rate, every $100K borrowed instead of sold saves
                    approximately <strong>$25,000</strong> in taxes. When you pass, heirs receive the stepped-up
                    basis and can sell assets to repay the debt tax-free.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ═══════════════ Section 2: Growth ═══════════════ */}
        <div className={styles.section}>
          <div className={styles.pageHeaderRow}>
            <div>
              <h2 className={styles.sectionHeader}>Growth</h2>
              <p className={styles.sectionSubtitle}>Portfolio value change — assumed 8%/yr</p>
            </div>
            <button
              className={styles.refreshButton}
              onClick={computeAssumptions}
              disabled={assumptionComputing}
            >
              <RefreshCw size={16} className={assumptionComputing ? styles.spinner : ''} />
              {assumptionComputing ? 'Refreshing...' : 'Refresh Data'}
            </button>
          </div>

          {(() => {
            const s = assumptionSummary;
            const years = s ? Object.keys(s.annual_growth || {}).sort() : [];
            const fmtPctAmt = (pct: number | null, amt: number | null) => {
              const pctStr = pct !== null && pct !== undefined ? `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%` : 'N/A';
              const amtStr = amt !== null && amt !== undefined ? formatFullCurrency(amt) : '';
              return { pctStr, amtStr };
            };

            const growthCards = s ? (
              <div className={styles.summaryGrid}>
                {(() => { const v = fmtPctAmt(s.avg_monthly_growth_pct, s.avg_monthly_growth_amt); return (
                  <div className={`${styles.summaryCard} ${s.avg_monthly_growth_pct !== null && s.avg_monthly_growth_pct >= s.expected_monthly_growth_pct ? styles.success : styles.danger}`}>
                    <span className={styles.summaryLabel}>Avg Monthly Growth</span>
                    <span className={styles.summaryValue}>{v.pctStr}</span>
                    <span className={styles.summaryNote}>{v.amtStr} / mo</span>
                    <span className={styles.summaryNote}>Target: {s.expected_monthly_growth_pct?.toFixed(2)}%/mo (8%/yr)</span>
                  </div>
                ); })()}
                {(() => { const v = fmtPctAmt(s.cumulative_growth_pct, s.cumulative_growth_amt); return (
                  <div className={`${styles.summaryCard} ${s.cumulative_growth_pct !== null && s.cumulative_growth_pct > 0 ? styles.success : styles.danger}`}>
                    <span className={styles.summaryLabel}>Cumulative Growth</span>
                    <span className={styles.summaryValue}>{v.pctStr}</span>
                    <span className={styles.summaryNote}>{v.amtStr}</span>
                    <span className={styles.summaryNote}>Since Jan 2025</span>
                  </div>
                ); })()}
                {years.map(yr => {
                  const g = s.annual_growth?.[yr];
                  const gv = fmtPctAmt(g?.percent, g?.amount);
                  return (
                    <div key={`growth-${yr}`} className={`${styles.summaryCard} ${g?.percent !== null && g?.percent !== undefined && g?.percent >= s.expected_annual_growth_pct ? styles.success : styles.danger}`}>
                      <span className={styles.summaryLabel}>{yr} Growth</span>
                      <span className={styles.summaryValue}>{gv.pctStr}</span>
                      <span className={styles.summaryNote}>{gv.amtStr}</span>
                      <span className={styles.summaryNote}>Target: {s.expected_annual_growth_pct}%/yr</span>
                    </div>
                  );
                })}
              </div>
            ) : null;

            return (
              <div>
                {growthCards}

                <div className={styles.chartCard}>
                  {/* Breadcrumb */}
                  <div className={styles.breadcrumb}>
                    <button
                      className={styles.breadcrumbItem}
                      onClick={() => handleBreadcrumb('year', setGrowthPeriod, setGrowthDrillYear, setGrowthDrillMonth)}
                      style={{ fontWeight: growthPeriod === 'year' ? '700' : '400' }}
                    >
                      All Years
                    </button>
                    {growthDrillYear && (
                      <>
                        <span className={styles.breadcrumbSep}>/</span>
                        <button
                          className={styles.breadcrumbItem}
                          onClick={() => handleBreadcrumb('month', setGrowthPeriod, setGrowthDrillYear, setGrowthDrillMonth)}
                          style={{ fontWeight: growthPeriod === 'month' ? '700' : '400' }}
                        >
                          {growthDrillYear}
                        </button>
                      </>
                    )}
                    {growthDrillMonth && (
                      <>
                        <span className={styles.breadcrumbSep}>/</span>
                        <span className={styles.breadcrumbItem} style={{ fontWeight: '700' }}>
                          {new Date(2000, growthDrillMonth - 1).toLocaleString('default', { month: 'long' })}
                        </span>
                      </>
                    )}
                  </div>

                  <h3 className={styles.chartTitle}>Growth — Actual vs Assumed (8%/yr)</h3>
                  <p className={styles.chartSubtitle}>
                    Portfolio value change — assumed ~0.64%/mo {growthPeriod !== 'week' ? ' — click a bar to drill down' : ''}
                  </p>

                  {growthMetrics && growthMetrics.length > 0 && (
                    <div className={styles.chartContainer}>
                      <ResponsiveContainer width="100%" height={350}>
                        <ComposedChart
                          data={growthMetrics}
                          margin={{ top: 20, right: 60, left: 20, bottom: 20 }}
                          onClick={(e: any) => {
                            if (e && e.activePayload && e.activePayload[0]) {
                              handleDrillDown(e.activePayload[0].payload, growthPeriod, setGrowthDrillYear, setGrowthDrillMonth, setGrowthPeriod);
                            }
                          }}
                          style={{ cursor: growthPeriod !== 'week' ? 'pointer' : 'default' }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                          <XAxis dataKey="period_label" stroke="#888" tick={{ fontSize: 12 }} />
                          <YAxis stroke="#888" tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
                          <Tooltip
                            formatter={(value: number, name: string) => [`${value.toFixed(3)}%`, name]}
                            contentStyle={{ backgroundColor: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
                          />
                          <Legend />
                          <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                          <Area type="monotone" dataKey="actual_percent" name="Actual %" fill="rgba(16, 185, 129, 0.2)" stroke="#10B981" strokeWidth={2} />
                          <Line type="monotone" dataKey="expected_percent" name="Assumed %" stroke="#F59E0B" strokeWidth={2} strokeDasharray="8 4" dot={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {growthMetrics && growthMetrics.length === 0 && (
                    <div className={styles.loadingState}>
                      <AlertTriangle size={32} />
                      <p>No data. Click "Refresh Data" above.</p>
                    </div>
                  )}

                  {/* Table */}
                  {growthMetrics && growthMetrics.length > 0 && (
                    <div className={styles.tableContainer} style={{ marginTop: '16px' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Period</th>
                            <th>Baseline</th>
                            <th>Actual</th>
                            <th>Expected</th>
                            <th>Actual %</th>
                            <th>Expected %</th>
                            <th>Variance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {growthMetrics.map((m: any, idx: number) => (
                            <tr
                              key={idx}
                              className={(m.variance_percent || 0) >= 0 ? styles.positiveRow : styles.negativeRow}
                              onClick={() => handleDrillDown(m, growthPeriod, setGrowthDrillYear, setGrowthDrillMonth, setGrowthPeriod)}
                              style={{ cursor: growthPeriod !== 'week' ? 'pointer' : 'default' }}
                            >
                              <td><strong>{m.period_label}</strong></td>
                              <td>{m.baseline_value !== null ? formatFullCurrency(m.baseline_value) : '-'}</td>
                              <td>{m.actual_value !== null ? formatFullCurrency(m.actual_value) : '-'}</td>
                              <td>{m.expected_value !== null ? formatFullCurrency(m.expected_value) : '-'}</td>
                              <td className={m.actual_percent >= (m.expected_percent || 0) ? styles.positive : styles.negative}>
                                {m.actual_percent !== null ? `${m.actual_percent.toFixed(2)}%` : '-'}
                              </td>
                              <td>{m.expected_percent !== null ? `${m.expected_percent.toFixed(2)}%` : '-'}</td>
                              <td className={(m.variance_percent || 0) >= 0 ? styles.positive : styles.negative}>
                                {m.variance_percent !== null ? `${m.variance_percent >= 0 ? '+' : ''}${m.variance_percent.toFixed(2)}%` : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>

        {/* ═══════════════ Section 3: Earnings ═══════════════ */}
        <div className={styles.section}>
          <h2 className={styles.sectionHeader}>Earnings</h2>
          <p className={styles.sectionSubtitle}>Options income — assumed 12%/yr</p>

          {(() => {
            const s = assumptionSummary;
            const years = s ? Object.keys(s.annual_earnings || {}).sort() : [];
            const fmtPctAmt = (pct: number | null, amt: number | null) => {
              const pctStr = pct !== null && pct !== undefined ? `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%` : 'N/A';
              const amtStr = amt !== null && amt !== undefined ? formatFullCurrency(amt) : '';
              return { pctStr, amtStr };
            };

            const earningsCards = s ? (
              <div className={styles.summaryGrid}>
                {(() => { const v = fmtPctAmt(s.avg_monthly_earnings_pct, s.avg_monthly_earnings_amt); return (
                  <div className={`${styles.summaryCard} ${s.avg_monthly_earnings_pct !== null && s.avg_monthly_earnings_pct >= s.expected_monthly_earnings_pct ? styles.success : styles.danger}`}>
                    <span className={styles.summaryLabel}>Avg Monthly Earnings</span>
                    <span className={styles.summaryValue}>{v.pctStr}</span>
                    <span className={styles.summaryNote}>{v.amtStr} / mo</span>
                    <span className={styles.summaryNote}>Target: {s.expected_monthly_earnings_pct}%/mo (12%/yr)</span>
                  </div>
                ); })()}
                {(() => { const v = fmtPctAmt(s.cumulative_earnings_pct, s.cumulative_earnings_amt); return (
                  <div className={`${styles.summaryCard} ${s.cumulative_earnings_pct !== null && s.cumulative_earnings_pct >= 0 ? styles.success : styles.danger}`}>
                    <span className={styles.summaryLabel}>Cumulative Earnings</span>
                    <span className={styles.summaryValue}>{v.pctStr}</span>
                    <span className={styles.summaryNote}>{v.amtStr}</span>
                    <span className={styles.summaryNote}>Since Jan 2025</span>
                  </div>
                ); })()}
                {years.map(yr => {
                  const e = s.annual_earnings?.[yr];
                  const ev = fmtPctAmt(e?.percent, e?.amount);
                  return (
                    <div key={`earn-${yr}`} className={`${styles.summaryCard} ${e?.percent !== null && e?.percent !== undefined && e?.percent >= s.expected_annual_earnings_pct ? styles.success : styles.danger}`}>
                      <span className={styles.summaryLabel}>{yr} Earnings</span>
                      <span className={styles.summaryValue}>{ev.pctStr}</span>
                      <span className={styles.summaryNote}>{ev.amtStr}</span>
                      <span className={styles.summaryNote}>Target: {s.expected_annual_earnings_pct}%/yr</span>
                    </div>
                  );
                })}
              </div>
            ) : null;

            return (
              <div>
                {earningsCards}

                <div className={styles.chartCard}>
                  {/* Breadcrumb */}
                  <div className={styles.breadcrumb}>
                    <button
                      className={styles.breadcrumbItem}
                      onClick={() => handleBreadcrumb('year', setYieldPeriod, setYieldDrillYear, setYieldDrillMonth)}
                      style={{ fontWeight: yieldPeriod === 'year' ? '700' : '400' }}
                    >
                      All Years
                    </button>
                    {yieldDrillYear && (
                      <>
                        <span className={styles.breadcrumbSep}>/</span>
                        <button
                          className={styles.breadcrumbItem}
                          onClick={() => handleBreadcrumb('month', setYieldPeriod, setYieldDrillYear, setYieldDrillMonth)}
                          style={{ fontWeight: yieldPeriod === 'month' ? '700' : '400' }}
                        >
                          {yieldDrillYear}
                        </button>
                      </>
                    )}
                    {yieldDrillMonth && (
                      <>
                        <span className={styles.breadcrumbSep}>/</span>
                        <span className={styles.breadcrumbItem} style={{ fontWeight: '700' }}>
                          {new Date(2000, yieldDrillMonth - 1).toLocaleString('default', { month: 'long' })}
                        </span>
                      </>
                    )}
                  </div>

                  <h3 className={styles.chartTitle}>Earnings — Actual vs Assumed (12%/yr)</h3>
                  <p className={styles.chartSubtitle}>
                    Options income as % of portfolio value {yieldPeriod !== 'week' ? ' — click a bar to drill down' : ''}
                  </p>

                  {yieldMetrics && yieldMetrics.length > 0 && (
                    <div className={styles.chartContainer}>
                      <ResponsiveContainer width="100%" height={350}>
                        <ComposedChart
                          data={yieldMetrics}
                          margin={{ top: 20, right: 60, left: 20, bottom: 20 }}
                          onClick={(e: any) => {
                            if (e && e.activePayload && e.activePayload[0]) {
                              handleDrillDown(e.activePayload[0].payload, yieldPeriod, setYieldDrillYear, setYieldDrillMonth, setYieldPeriod);
                            }
                          }}
                          style={{ cursor: yieldPeriod !== 'week' ? 'pointer' : 'default' }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                          <XAxis dataKey="period_label" stroke="#888" tick={{ fontSize: 12 }} />
                          <YAxis stroke="#888" tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
                          <Tooltip
                            formatter={(value: number, name: string) => [`${value.toFixed(3)}%`, name]}
                            contentStyle={{ backgroundColor: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
                          />
                          <Legend />
                          <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                          <Area type="monotone" dataKey="actual_percent" name="Actual %" fill="rgba(139, 92, 246, 0.2)" stroke="#8B5CF6" strokeWidth={2} />
                          <Line type="monotone" dataKey="expected_percent" name="Assumed %" stroke="#F59E0B" strokeWidth={2} strokeDasharray="8 4" dot={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {yieldMetrics && yieldMetrics.length === 0 && (
                    <div className={styles.loadingState}>
                      <AlertTriangle size={32} />
                      <p>No data. Click "Refresh Data" above.</p>
                    </div>
                  )}

                  {/* Table */}
                  {yieldMetrics && yieldMetrics.length > 0 && (
                    <div className={styles.tableContainer} style={{ marginTop: '16px' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Period</th>
                            <th>Baseline</th>
                            <th>Actual</th>
                            <th>Expected</th>
                            <th>Actual %</th>
                            <th>Expected %</th>
                            <th>Variance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {yieldMetrics.map((m: any, idx: number) => (
                            <tr
                              key={idx}
                              className={(m.variance_percent || 0) >= 0 ? styles.positiveRow : styles.negativeRow}
                              onClick={() => handleDrillDown(m, yieldPeriod, setYieldDrillYear, setYieldDrillMonth, setYieldPeriod)}
                              style={{ cursor: yieldPeriod !== 'week' ? 'pointer' : 'default' }}
                            >
                              <td><strong>{m.period_label}</strong></td>
                              <td>{m.baseline_value !== null ? formatFullCurrency(m.baseline_value) : '-'}</td>
                              <td>{m.actual_value !== null ? formatFullCurrency(m.actual_value) : '-'}</td>
                              <td>{m.expected_value !== null ? formatFullCurrency(m.expected_value) : '-'}</td>
                              <td className={m.actual_percent >= (m.expected_percent || 0) ? styles.positive : styles.negative}>
                                {m.actual_percent !== null ? `${m.actual_percent.toFixed(2)}%` : '-'}
                              </td>
                              <td>{m.expected_percent !== null ? `${m.expected_percent.toFixed(2)}%` : '-'}</td>
                              <td className={(m.variance_percent || 0) >= 0 ? styles.positive : styles.negative}>
                                {m.variance_percent !== null ? `${m.variance_percent >= 0 ? '+' : ''}${m.variance_percent.toFixed(2)}%` : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>

        {/* ═══════════════ Section 4: Borrow ═══════════════ */}
        <div className={styles.section}>
          <h2 className={styles.sectionHeader}>Borrow</h2>
          <p className={styles.sectionSubtitle}>Simulated margin borrowing — 5% annual interest on cumulative spending</p>

          {(() => {
            const s = assumptionSummary;

            const borrowCards = s && s.margin_available !== null ? (
              <div className={styles.summaryGrid}>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryLabel}>Margin Available</span>
                  <span className={styles.summaryValue}>{s.margin_available !== null ? formatFullCurrency(s.margin_available) : 'N/A'}</span>
                  <span className={styles.summaryNote}>70% of Neel + Jaya brokerage</span>
                </div>
                <div className={`${styles.summaryCard} ${s.current_margin_utilization_pct !== null && s.current_margin_utilization_pct <= 30 ? styles.success : styles.danger}`}>
                  <span className={styles.summaryLabel}>Margin Used</span>
                  <span className={styles.summaryValue}>{s.current_margin_balance !== null ? formatFullCurrency(s.current_margin_balance) : 'N/A'}</span>
                  <span className={styles.summaryNote}>
                    {s.current_margin_utilization_pct !== null ? `${s.current_margin_utilization_pct.toFixed(1)}% utilization` : ''}
                    {s.total_interest_accrued ? ` (incl. ${formatFullCurrency(s.total_interest_accrued)} interest)` : ''}
                  </span>
                </div>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryLabel}>2025 Expenses</span>
                  <span className={styles.summaryValue}>{s.annual_spending?.['2025'] ? formatFullCurrency(s.annual_spending['2025']) : 'N/A'}</span>
                  <span className={styles.summaryNote}>Total annual spending</span>
                </div>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryLabel}>Avg Monthly Spending</span>
                  <span className={styles.summaryValue}>{s.avg_monthly_borrowing_amt !== null ? `${formatFullCurrency(s.avg_monthly_borrowing_amt)}/mo` : 'N/A'}</span>
                  <span className={styles.summaryNote}>Averaged across all months</span>
                </div>
              </div>
            ) : null;

            // Borrow drill-down: year → month only (no weekly)
            const handleBorrowDrillDown = (entry: any) => {
              if (borrowPeriod === 'year' && entry?.period_start) {
                setBorrowDrillYear(parseInt(entry.period_start.substring(0, 4)));
                setBorrowPeriod('month');
              }
            };

            const handleBorrowBreadcrumb = () => {
              setBorrowPeriod('year');
              setBorrowDrillYear(undefined);
            };

            return (
              <div>
                {borrowCards}

                <div className={styles.chartCard}>
                  {/* Breadcrumb */}
                  <div className={styles.breadcrumb}>
                    <button
                      className={styles.breadcrumbItem}
                      onClick={handleBorrowBreadcrumb}
                      style={{ fontWeight: borrowPeriod === 'year' ? '700' : '400' }}
                    >
                      All Years
                    </button>
                    {borrowDrillYear && (
                      <>
                        <span className={styles.breadcrumbSep}>/</span>
                        <span className={styles.breadcrumbItem} style={{ fontWeight: '700' }}>
                          {borrowDrillYear}
                        </span>
                      </>
                    )}
                  </div>

                  <h3 className={styles.chartTitle}>Cumulative Margin Balance — Actual vs Average Spending</h3>
                  <p className={styles.chartSubtitle}>
                    Net withdrawals with 5% simulated interest {borrowPeriod === 'year' ? ' — click a bar to drill down' : ''}
                  </p>

                  {borrowMetrics && borrowMetrics.length > 0 && (
                    <div className={styles.chartContainer}>
                      <ResponsiveContainer width="100%" height={350}>
                        <ComposedChart
                          data={borrowMetrics}
                          margin={{ top: 20, right: 60, left: 20, bottom: 20 }}
                          onClick={(e: any) => {
                            if (e && e.activePayload && e.activePayload[0]) {
                              handleBorrowDrillDown(e.activePayload[0].payload);
                            }
                          }}
                          style={{ cursor: borrowPeriod === 'year' ? 'pointer' : 'default' }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                          <XAxis dataKey="period_label" stroke="#888" tick={{ fontSize: 12 }} />
                          <YAxis stroke="#888" tickFormatter={(v: number) => formatCurrency(v)} />
                          <Tooltip
                            formatter={(value: number, name: string) => [formatFullCurrency(value), name]}
                            contentStyle={{ backgroundColor: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
                          />
                          <Legend />
                          <Area type="monotone" dataKey="actual_value" name="Margin Balance" fill="rgba(245, 158, 11, 0.2)" stroke="#F59E0B" strokeWidth={2} />
                          <Line type="monotone" dataKey="expected_value" name="Expected (avg)" stroke="#EF4444" strokeWidth={2} strokeDasharray="8 4" dot={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {borrowMetrics && borrowMetrics.length === 0 && (
                    <div className={styles.loadingState}>
                      <AlertTriangle size={32} />
                      <p>No data. Click "Refresh Data" above.</p>
                    </div>
                  )}

                  {/* Table */}
                  {borrowMetrics && borrowMetrics.length > 0 && (
                    <div className={styles.tableContainer} style={{ marginTop: '16px' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Period</th>
                            <th>Margin Avail (70%)</th>
                            <th>Margin Balance</th>
                            <th>Expected</th>
                            <th>Utilization %</th>
                            <th>Expected Util.</th>
                            <th>Variance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {borrowMetrics.map((m: any, idx: number) => (
                            <tr
                              key={idx}
                              className={(m.variance_percent || 0) <= 0 ? styles.positiveRow : styles.negativeRow}
                              onClick={() => handleBorrowDrillDown(m)}
                              style={{ cursor: borrowPeriod === 'year' ? 'pointer' : 'default' }}
                            >
                              <td><strong>{m.period_label}</strong></td>
                              <td>{m.baseline_value !== null ? formatFullCurrency(m.baseline_value) : '-'}</td>
                              <td>{m.actual_value !== null ? formatFullCurrency(m.actual_value) : '-'}</td>
                              <td>{m.expected_value !== null ? formatFullCurrency(m.expected_value) : '-'}</td>
                              <td className={m.actual_percent <= (m.expected_percent || 0) ? styles.positive : styles.negative}>
                                {m.actual_percent !== null ? `${m.actual_percent.toFixed(1)}%` : '-'}
                              </td>
                              <td>{m.expected_percent !== null ? `${m.expected_percent.toFixed(1)}%` : '-'}</td>
                              <td className={(m.variance_percent || 0) <= 0 ? styles.positive : styles.negative}>
                                {m.variance_percent !== null ? `${m.variance_percent >= 0 ? '+' : ''}${m.variance_percent.toFixed(1)}%` : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>

      </div>
    </div>
  );
}
