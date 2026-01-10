import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, 
  RefreshCw, 
  ChevronRight,
  AlertCircle,
  FileText,
  DollarSign,
  Building2,
  Users,
  TrendingUp,
  Briefcase,
  Home,
  Wallet,
  PiggyBank,
  Banknote,
  Calendar,
  Clock,
  CheckCircle2,
  AlertTriangle
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
import styles from './Tax.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface TaxYear {
  year: number;
  agi: number;
  federal_tax: number;
  state_tax: number;
  other_tax: number;
  total_tax: number;
  effective_rate: number | null;
  federal_rate: number | null;
  state_rate: number | null;
  other_rate: number | null;
}

interface TaxHistory {
  years: TaxYear[];
  total_federal: number;
  total_state: number;
  total_other: number;
  total_taxes: number;
  average_effective_rate: number;
}

interface AccountBreakdown {
  account_name: string;
  account_id: string;
  source: string;
  owner: string;
  amount: number;
}

interface QuarterlyPayment {
  quarter: number;
  period: string;
  due_date: string;
  income_for_period: number;
  cumulative_income: number;
  estimated_payment: number;
  federal_payment: number;
  state_payment: number;
  cumulative_paid: number;
  cumulative_federal_paid?: number;
  cumulative_state_paid?: number;
  status: 'past_due' | 'due_soon' | 'upcoming' | 'not_required';
  note?: string;
}

interface TaxDetails {
  year: number;
  agi: number;
  federal_tax: number;
  federal_withheld: number | null;
  federal_owed: number | null;
  federal_refund: number | null;
  state_tax: number;
  state_withheld: number | null;
  state_owed: number | null;
  state_refund: number | null;
  other_tax: number;
  total_tax: number;
  effective_rate: number;
  filing_status: string | null;
  is_forecast?: boolean;
  // Payment schedule fields for forecasts
  payment_schedule?: QuarterlyPayment[];
  w2_withholding?: {
    federal: number;
    state: number;
    total: number;
  };
  estimated_tax_needed?: number;
  safe_harbor?: {
    prior_year_110: number;
    current_year_90: number;
    recommended: number;
  };
  details: {
    income_sources?: Array<{ source: string; amount: number }>;
    w2_breakdown?: Array<{
      employer: string;
      wages: number;
      federal_withheld: number;
      state_withheld: number;
    }>;
    deductions?: {
      standard?: number;
      itemized_total?: number;
      mortgage_interest?: number;
      salt?: number;
      charitable?: number;
    };
    payroll_taxes?: Array<{
      employer: string;
      social_security: number;
      medicare: number;
      sdi?: number;
    }>;
    capital_gains?: {
      short_term?: number;
      long_term?: number;
      loss_carryover?: number;
    };
    rental_properties?: Array<{
      address: string;
      income: number;
      expenses: number;
      depreciation: number;
    }>;
    additional_taxes?: {
      niit?: number;
      amt?: number;
      self_employment?: number;
    };
    // Account-level breakdowns for investment income
    options_by_account?: AccountBreakdown[];
    dividends_by_account?: AccountBreakdown[];
    interest_by_account?: AccountBreakdown[];
  };
}

export default function Tax() {
  const navigate = useNavigate();
  const [taxHistory, setTaxHistory] = useState<TaxHistory | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [yearDetails, setYearDetails] = useState<TaxDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTaxHistory();
  }, []);

  useEffect(() => {
    if (selectedYear) {
      fetchYearDetails(selectedYear);
    } else {
      setYearDetails(null);
    }
  }, [selectedYear]);

  const fetchTaxHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/v1/tax/returns', {
        headers: getAuthHeaders(),
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch tax history');
      }
      
      const data = await response.json();
      setTaxHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const fetchYearDetails = async (year: number) => {
    setDetailLoading(true);
    try {
      // First try to get actual tax return, if not found use forecast
      // Years 2025 and later are forecasts until a real tax return is filed
      const currentYear = new Date().getFullYear();
      
      // For years >= currentYear-1 (e.g., 2025 when it's 2026), we likely need forecast
      // because tax returns aren't filed until April of the following year
      const likelyForecast = year >= currentYear - 1;
      
      // Try returns first for past years, forecast for recent/future years
      let endpoint = likelyForecast 
        ? `/api/v1/tax/forecast/${year}?base_year=2024`
        : `/api/v1/tax/returns/${year}`;
      
      let response = await fetch(endpoint, {
        headers: getAuthHeaders(),
      });
      
      // If returns 404 for a past year, try forecast
      if (!response.ok && !likelyForecast) {
        endpoint = `/api/v1/tax/forecast/${year}?base_year=2024`;
        response = await fetch(endpoint, {
          headers: getAuthHeaders(),
        });
      }
      
      if (!response.ok) {
        throw new Error(`Failed to fetch details for ${year}`);
      }
      
      const data = await response.json();
      setYearDetails(data);
    } catch (err) {
      console.error('Error fetching year details:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatPercent = (value: number | null) => {
    if (value === null) return '-';
    return `${value.toFixed(1)}%`;
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className={styles.chartTooltip}>
          <p className={styles.tooltipYear}>{label}</p>
          {payload.map((entry: any, index: number) => (
            <div key={index} className={styles.tooltipRow}>
              <span className={styles.tooltipLabel}>{entry.name}:</span>
              <span className={`${styles.tooltipValue} ${styles[entry.dataKey]}`}>
                {formatCurrency(entry.value)}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={40} className={styles.spinner} />
          <p>Loading tax history...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <h3>Error Loading Tax Data</h3>
          <p>{error}</p>
          <button className={styles.refreshButton} onClick={fetchTaxHistory}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!taxHistory || taxHistory.years.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>
          <FileText size={48} />
          <h3>No Tax Data Found</h3>
          <p>Upload your tax returns in the Data Ingestion page to see your tax history.</p>
          <button 
            className={styles.refreshButton} 
            onClick={() => navigate('/data-ingestion')}
          >
            Go to Data Ingestion
          </button>
        </div>
      </div>
    );
  }

  // If a year is selected, show the detail view
  if (selectedYear && yearDetails) {
    return (
      <div className={styles.page}>
        <button className={styles.backButton} onClick={() => setSelectedYear(null)}>
          <ArrowLeft size={18} />
          Back to Overview
        </button>

        <div className={styles.detailHeader}>
          <div className={styles.detailHeaderTop}>
            <h1 className={styles.detailYear}>
              {yearDetails.year} <span>Tax Return</span>
              {yearDetails.is_forecast && (
                <span style={{ 
                  marginLeft: '12px', 
                  fontSize: '14px', 
                  fontWeight: 'normal',
                  color: '#FFB800',
                  background: 'rgba(255, 184, 0, 0.1)',
                  padding: '4px 12px',
                  borderRadius: '12px'
                }}>
                  Forecast
                </span>
              )}
            </h1>
            <div className={styles.detailTotalTax}>
              <span className={styles.detailTotalLabel}>Total Tax</span>
              <span className={styles.detailTotalValue}>
                {formatCurrency(yearDetails.total_tax)}
              </span>
            </div>
          </div>

          <div className={styles.taxBreakdown}>
            <div className={styles.breakdownBar}>
              <div 
                className={styles.breakdownBarFederal}
                style={{ width: `${yearDetails.total_tax > 0 ? (yearDetails.federal_tax / yearDetails.total_tax) * 100 : 0}%` }}
              >
                {yearDetails.total_tax > 0 ? ((yearDetails.federal_tax / yearDetails.total_tax) * 100).toFixed(0) : 0}%
              </div>
              <div 
                className={styles.breakdownBarState}
                style={{ width: `${yearDetails.total_tax > 0 ? (yearDetails.state_tax / yearDetails.total_tax) * 100 : 0}%` }}
              >
                {yearDetails.total_tax > 0 ? ((yearDetails.state_tax / yearDetails.total_tax) * 100).toFixed(0) : 0}%
              </div>
            </div>
            <div className={styles.breakdownLabels}>
              <span className={styles.breakdownLabelItem}>
                <span className={`${styles.dot} ${styles.federal}`}></span>
                Federal: {formatCurrency(yearDetails.federal_tax)}
              </span>
              <span className={styles.breakdownLabelItem}>
                <span className={`${styles.dot} ${styles.state}`}></span>
                State: {formatCurrency(yearDetails.state_tax)}
              </span>
            </div>
          </div>

          <div className={styles.detailStatsGrid}>
            <div className={styles.detailStat}>
              <span className={styles.detailStatLabel}>AGI</span>
              <span className={styles.detailStatValue}>{formatCurrency(yearDetails.agi)}</span>
            </div>
            <div className={styles.detailStat}>
              <span className={styles.detailStatLabel}>Effective Rate</span>
              <span className={styles.detailStatValue}>{yearDetails.effective_rate}%</span>
            </div>
            <div className={styles.detailStat}>
              <span className={styles.detailStatLabel}>Filing Status</span>
              <span className={styles.detailStatValue}>{yearDetails.filing_status || 'MFJ'}</span>
            </div>
          </div>
        </div>

        {/* Quarterly Payment Schedule */}
        {yearDetails.is_forecast && yearDetails.payment_schedule && yearDetails.payment_schedule.length > 0 && (
          <section className={styles.detailSection}>
            <h3><Calendar size={18} /> Quarterly Estimated Tax Payments</h3>
            
            {/* Withholding Summary */}
            {yearDetails.w2_withholding && (
              <div className={styles.detailGrid} style={{ marginBottom: '1.5rem' }}>
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>W-2 Withholding (Total)</span>
                  <span className={styles.detailItemValue}>{formatCurrency(yearDetails.w2_withholding.total)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>↳ Federal Withheld</span>
                  <span className={styles.detailItemValue} style={{ fontSize: '0.9rem' }}>{formatCurrency(yearDetails.w2_withholding.federal)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>↳ State Withheld</span>
                  <span className={styles.detailItemValue} style={{ fontSize: '0.9rem' }}>{formatCurrency(yearDetails.w2_withholding.state)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Estimated Tax Needed</span>
                  <span className={`${styles.detailItemValue} ${(yearDetails.estimated_tax_needed || 0) > 0 ? styles.negative : styles.positive}`}>
                    {formatCurrency(yearDetails.estimated_tax_needed || 0)}
                  </span>
                </div>
                {yearDetails.safe_harbor && (
                  <div className={styles.detailItem}>
                    <span className={styles.detailItemLabel}>Safe Harbor Amount</span>
                    <span className={styles.detailItemValue}>{formatCurrency(yearDetails.safe_harbor.recommended)}</span>
                  </div>
                )}
              </div>
            )}

            {/* Payment Schedule Table */}
            <div className={`${styles.employerTable} ${styles.paymentScheduleTable}`}>
              <div className={styles.employerHeader}>
                <span>Quarter</span>
                <span>Period</span>
                <span>Due Date</span>
                <span>Federal (IRS)</span>
                <span>State (FTB)</span>
                <span>Total Due</span>
                <span>Status</span>
              </div>
              {yearDetails.payment_schedule.map((payment, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>Q{payment.quarter}</span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{payment.period}</span>
                  <span style={{ fontWeight: 500 }}>
                    {new Date(payment.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                  <span className={payment.federal_payment > 0 ? styles.negative : styles.positive}>
                    {formatCurrency(payment.federal_payment || 0)}
                  </span>
                  <span className={payment.state_payment > 0 ? styles.negative : styles.positive}>
                    {formatCurrency(payment.state_payment || 0)}
                  </span>
                  <span className={payment.estimated_payment > 0 ? styles.negative : styles.positive} style={{ fontWeight: 600 }}>
                    {formatCurrency(payment.estimated_payment)}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {payment.status === 'past_due' && (
                      <>
                        <AlertTriangle size={14} style={{ color: '#ef4444' }} />
                        <span style={{ color: '#ef4444', fontSize: '0.85rem' }}>Past Due</span>
                      </>
                    )}
                    {payment.status === 'due_soon' && (
                      <>
                        <Clock size={14} style={{ color: '#f59e0b' }} />
                        <span style={{ color: '#f59e0b', fontSize: '0.85rem' }}>Due Soon</span>
                      </>
                    )}
                    {payment.status === 'upcoming' && (
                      <>
                        <Calendar size={14} style={{ color: '#10b981' }} />
                        <span style={{ color: '#10b981', fontSize: '0.85rem' }}>Upcoming</span>
                      </>
                    )}
                    {payment.status === 'not_required' && (
                      <>
                        <CheckCircle2 size={14} style={{ color: '#6b7280' }} />
                        <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>N/A</span>
                      </>
                    )}
                  </span>
                </div>
              ))}
            </div>

            {/* Safe Harbor Note */}
            {yearDetails.safe_harbor && (yearDetails.estimated_tax_needed || 0) > 0 && (
              <div style={{ 
                marginTop: '1rem', 
                padding: '0.75rem 1rem', 
                background: 'rgba(16, 185, 129, 0.1)', 
                borderRadius: '8px',
                fontSize: '0.875rem',
                color: 'var(--text-secondary)'
              }}>
                <strong>💡 Safe Harbor Tip:</strong> To avoid underpayment penalties, pay at least {formatCurrency(yearDetails.safe_harbor.recommended)} in total 
                (either 110% of prior year tax or 90% of current year tax, whichever is less).
              </div>
            )}
          </section>
        )}

        {/* Income Sources */}
        {yearDetails.details.income_sources && yearDetails.details.income_sources.length > 0 && (
          <section className={styles.detailSection}>
            <h3><DollarSign size={18} /> Income Sources</h3>
            <div className={styles.detailGrid}>
              {yearDetails.details.income_sources.map((source, i) => (
                <div key={i} className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>{source.source}</span>
                  <span className={styles.detailItemValue}>{formatCurrency(source.amount)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* W-2 Breakdown */}
        {yearDetails.details.w2_breakdown && yearDetails.details.w2_breakdown.length > 0 && (
          <section className={styles.detailSection}>
            <h3><Briefcase size={18} /> W-2 Income by Employer</h3>
            <div className={styles.employerTable}>
              <div className={styles.employerHeader}>
                <span>Employer</span>
                <span>Wages</span>
                <span>Federal Withheld</span>
                <span>State Withheld</span>
              </div>
              {yearDetails.details.w2_breakdown.map((w2, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>{w2.employer}</span>
                  <span>{formatCurrency(w2.wages)}</span>
                  <span className={styles.federal}>{formatCurrency(w2.federal_withheld)}</span>
                  <span className={styles.state}>{formatCurrency(w2.state_withheld)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Options Income by Account */}
        {yearDetails.details.options_by_account && yearDetails.details.options_by_account.length > 0 && (
          <section className={styles.detailSection}>
            <h3><TrendingUp size={18} /> Options Income by Account</h3>
            <div className={styles.employerTable}>
              <div className={styles.employerHeader}>
                <span>Account</span>
                <span>Source</span>
                <span>Amount</span>
              </div>
              {yearDetails.details.options_by_account.map((acct, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>{acct.account_name}</span>
                  <span>{acct.source}</span>
                  <span className={styles.positive}>{formatCurrency(acct.amount)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Dividends by Account */}
        {yearDetails.details.dividends_by_account && yearDetails.details.dividends_by_account.length > 0 && (
          <section className={styles.detailSection}>
            <h3><PiggyBank size={18} /> Dividend Income by Account</h3>
            <div className={styles.employerTable}>
              <div className={styles.employerHeader}>
                <span>Account</span>
                <span>Source</span>
                <span>Amount</span>
              </div>
              {yearDetails.details.dividends_by_account.map((acct, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>{acct.account_name}</span>
                  <span>{acct.source}</span>
                  <span className={styles.positive}>{formatCurrency(acct.amount)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Interest by Account */}
        {yearDetails.details.interest_by_account && yearDetails.details.interest_by_account.length > 0 && (
          <section className={styles.detailSection}>
            <h3><Banknote size={18} /> Interest Income by Account</h3>
            <div className={styles.employerTable}>
              <div className={styles.employerHeader}>
                <span>Account</span>
                <span>Source</span>
                <span>Amount</span>
              </div>
              {yearDetails.details.interest_by_account.map((acct, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>{acct.account_name}</span>
                  <span>{acct.source}</span>
                  <span className={styles.positive}>{formatCurrency(acct.amount)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Payroll Taxes */}
        {yearDetails.details.payroll_taxes && yearDetails.details.payroll_taxes.length > 0 && (
          <section className={styles.detailSection}>
            <h3><Users size={18} /> Payroll Taxes</h3>
            <div className={styles.employerTable}>
              <div className={styles.employerHeader}>
                <span>Employer</span>
                <span>Social Security</span>
                <span>Medicare</span>
                <span>SDI</span>
              </div>
              {yearDetails.details.payroll_taxes.map((pt, i) => (
                <div key={i} className={styles.employerRow}>
                  <span className={styles.employerName}>{pt.employer}</span>
                  <span>{formatCurrency(pt.social_security)}</span>
                  <span>{formatCurrency(pt.medicare)}</span>
                  <span>{formatCurrency(pt.sdi || 0)}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Stock Sales */}
        {yearDetails.details.capital_gains && (
          <section className={styles.detailSection}>
            <h3><TrendingUp size={18} /> Stock Sales</h3>
            <div className={styles.detailGrid}>
              {yearDetails.details.capital_gains.short_term !== undefined && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Short-Term (held ≤1 year)</span>
                  <span className={`${styles.detailItemValue} ${yearDetails.details.capital_gains.short_term >= 0 ? styles.positive : styles.negative}`}>
                    {formatCurrency(yearDetails.details.capital_gains.short_term)}
                  </span>
                </div>
              )}
              {yearDetails.details.capital_gains.long_term !== undefined && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Long-Term (held &gt;1 year)</span>
                  <span className={`${styles.detailItemValue} ${yearDetails.details.capital_gains.long_term >= 0 ? styles.positive : styles.negative}`}>
                    {formatCurrency(yearDetails.details.capital_gains.long_term)}
                  </span>
                </div>
              )}
              {yearDetails.details.capital_gains.loss_carryover !== undefined && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Loss Carryover</span>
                  <span className={`${styles.detailItemValue} ${styles.negative}`}>
                    {formatCurrency(yearDetails.details.capital_gains.loss_carryover)}
                  </span>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Rental Properties */}
        {yearDetails.details.rental_properties && yearDetails.details.rental_properties.length > 0 && (
          <section className={styles.detailSection}>
            <h3><Home size={18} /> Rental Properties</h3>
            {yearDetails.details.rental_properties.map((rental, i) => (
              <div key={i} className={styles.propertyCard}>
                <div className={styles.propertyAddress}>{rental.address}</div>
                <div className={styles.detailGrid}>
                  <div className={styles.detailItem}>
                    <span className={styles.detailItemLabel}>Rental Income</span>
                    <span className={`${styles.detailItemValue} ${styles.positive}`}>
                      {formatCurrency(rental.income)}
                    </span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailItemLabel}>Expenses</span>
                    <span className={`${styles.detailItemValue} ${styles.negative}`}>
                      {formatCurrency(rental.expenses)}
                    </span>
                  </div>
                  <div className={styles.detailItem}>
                    <span className={styles.detailItemLabel}>Depreciation</span>
                    <span className={`${styles.detailItemValue} ${styles.negative}`}>
                      {formatCurrency(rental.depreciation)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </section>
        )}

        {/* Additional Taxes */}
        {yearDetails.details.additional_taxes && (
          <section className={styles.detailSection}>
            <h3><AlertCircle size={18} /> Additional Taxes</h3>
            <div className={styles.detailGrid}>
              {yearDetails.details.additional_taxes.niit !== undefined && yearDetails.details.additional_taxes.niit > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>NIIT (Net Investment Income Tax)</span>
                  <span className={`${styles.detailItemValue} ${styles.negative}`}>
                    {formatCurrency(yearDetails.details.additional_taxes.niit)}
                  </span>
                </div>
              )}
              {yearDetails.details.additional_taxes.amt !== undefined && yearDetails.details.additional_taxes.amt > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>AMT (Alternative Minimum Tax)</span>
                  <span className={`${styles.detailItemValue} ${styles.negative}`}>
                    {formatCurrency(yearDetails.details.additional_taxes.amt)}
                  </span>
                </div>
              )}
              {yearDetails.details.additional_taxes.self_employment !== undefined && yearDetails.details.additional_taxes.self_employment > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Self-Employment Tax</span>
                  <span className={`${styles.detailItemValue} ${styles.negative}`}>
                    {formatCurrency(yearDetails.details.additional_taxes.self_employment)}
                  </span>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Deductions */}
        {yearDetails.details.deductions && (
          <section className={styles.detailSection}>
            <h3><FileText size={18} /> Deductions</h3>
            <div className={styles.detailGrid}>
              {yearDetails.details.deductions.standard !== undefined && yearDetails.details.deductions.standard > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Standard Deduction</span>
                  <span className={styles.detailItemValue}>
                    {formatCurrency(yearDetails.details.deductions.standard)}
                  </span>
                </div>
              )}
              {yearDetails.details.deductions.itemized_total !== undefined && yearDetails.details.deductions.itemized_total > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Itemized Deductions</span>
                  <span className={styles.detailItemValue}>
                    {formatCurrency(yearDetails.details.deductions.itemized_total)}
                  </span>
                </div>
              )}
              {yearDetails.details.deductions.mortgage_interest !== undefined && yearDetails.details.deductions.mortgage_interest > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Mortgage Interest</span>
                  <span className={styles.detailItemValue}>
                    {formatCurrency(yearDetails.details.deductions.mortgage_interest)}
                  </span>
                </div>
              )}
              {yearDetails.details.deductions.salt !== undefined && yearDetails.details.deductions.salt > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>SALT (State & Local Taxes)</span>
                  <span className={styles.detailItemValue}>
                    {formatCurrency(yearDetails.details.deductions.salt)}
                  </span>
                </div>
              )}
              {yearDetails.details.deductions.charitable !== undefined && yearDetails.details.deductions.charitable > 0 && (
                <div className={styles.detailItem}>
                  <span className={styles.detailItemLabel}>Charitable Contributions</span>
                  <span className={styles.detailItemValue}>
                    {formatCurrency(yearDetails.details.deductions.charitable)}
                  </span>
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    );
  }

  // Chart data - reverse to show oldest first
  const chartData = [...taxHistory.years].reverse().map(year => ({
    year: year.year,
    federal: year.federal_tax,
    state: year.state_tax,
    other: year.other_tax,
  }));

  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.heroLabel}>Tax Center</span>
          <h1 className={styles.heroValue}>{formatCurrency(taxHistory.total_taxes)}</h1>
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Federal</span>
              <span className={`${styles.heroStatValue} ${styles.federal}`}>
                {formatCurrency(taxHistory.total_federal)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>State</span>
              <span className={`${styles.heroStatValue} ${styles.state}`}>
                {formatCurrency(taxHistory.total_state)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Other</span>
              <span className={`${styles.heroStatValue} ${styles.other}`}>
                {formatCurrency(taxHistory.total_other)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Avg Rate</span>
              <span className={styles.heroStatValue}>
                {taxHistory.average_effective_rate}%
              </span>
            </div>
          </div>
        </div>
        <div className={styles.heroButtons}>
          <button className={styles.heroButton} onClick={() => navigate('/tax/forms')}>
            <FileText size={18} />
            View Tax Forms
          </button>
          <button className={styles.heroButton} onClick={() => navigate('/tax/cost-basis')}>
            <TrendingUp size={18} />
            Cost Basis Tracker
          </button>
          <button className={styles.heroRefresh} onClick={fetchTaxHistory}>
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      {/* Chart Section */}
      <div className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Tax History</h2>
          <div className={styles.chartLegend}>
            <span className={styles.legendItem}>
              <span className={`${styles.legendDot} ${styles.federal}`}></span>
              Federal
            </span>
            <span className={styles.legendItem}>
              <span className={`${styles.legendDot} ${styles.state}`}></span>
              State
            </span>
            <span className={styles.legendItem}>
              <span className={`${styles.legendDot} ${styles.other}`}></span>
              Other
            </span>
          </div>
        </div>
        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="federalGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00A3FF" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00A3FF" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="stateGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#FFB800" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#FFB800" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="otherGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis 
                dataKey="year" 
                stroke="#737373"
                tick={{ fill: '#737373', fontSize: 12 }}
              />
              <YAxis 
                stroke="#737373"
                tick={{ fill: '#737373', fontSize: 12 }}
                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="federal"
                name="Federal"
                stackId="1"
                stroke="#00A3FF"
                fill="url(#federalGradient)"
              />
              <Area
                type="monotone"
                dataKey="state"
                name="State"
                stackId="1"
                stroke="#FFB800"
                fill="url(#stateGradient)"
              />
              <Area
                type="monotone"
                dataKey="other"
                name="Other"
                stackId="1"
                stroke="#10B981"
                fill="url(#otherGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Years Grid */}
      <div className={styles.yearsSection}>
        <h2>Tax Returns by Year</h2>
        <div className={styles.yearsGrid}>
          {taxHistory.years.map((year, index) => {
            // Years >= currentYear-1 are likely forecasts (2025 when it's 2026)
            const currentYear = new Date().getFullYear();
            const isForecast = year.year >= currentYear - 1;
            return (
            <button
              key={year.year}
              className={`${styles.yearCard} ${selectedYear === year.year ? styles.selected : ''}`}
              onClick={() => setSelectedYear(year.year)}
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              <div className={styles.yearCardHeader}>
                <span className={styles.yearLabel}>
                  {year.year}
                  {isForecast && (
                    <span style={{ 
                      marginLeft: '8px', 
                      fontSize: '11px', 
                      color: '#FFB800',
                      fontWeight: 'normal'
                    }}>
                      (Forecast)
                    </span>
                  )}
                </span>
                <span className={styles.yearBadge}>{year.effective_rate}%</span>
              </div>
              <div className={styles.yearAgi}>
                <span className={styles.agiLabel}>AGI</span>
                <span className={styles.agiValue}>{formatCurrency(year.agi)}</span>
              </div>
              <div className={styles.yearTotalTax}>{formatCurrency(year.total_tax)}</div>
              <div className={styles.yearBreakdown}>
                <div className={styles.breakdownRow}>
                  <span className={styles.breakdownLabel}>Federal</span>
                  <span className={`${styles.breakdownValue} ${styles.federal}`}>
                    {formatCurrency(year.federal_tax)}
                  </span>
                  <span className={styles.breakdownRate}>{formatPercent(year.federal_rate)}</span>
                </div>
                <div className={styles.breakdownRow}>
                  <span className={styles.breakdownLabel}>State</span>
                  <span className={`${styles.breakdownValue} ${styles.state}`}>
                    {formatCurrency(year.state_tax)}
                  </span>
                  <span className={styles.breakdownRate}>{formatPercent(year.state_rate)}</span>
                </div>
                <div className={styles.breakdownRow}>
                  <span className={styles.breakdownLabel}>Other</span>
                  <span className={`${styles.breakdownValue} ${styles.other}`}>
                    {formatCurrency(year.other_tax)}
                  </span>
                  <span className={styles.breakdownRate}>{formatPercent(year.other_rate)}</span>
                </div>
              </div>
              <div className={styles.viewDetails}>
                View Details <ChevronRight size={14} />
              </div>
            </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
