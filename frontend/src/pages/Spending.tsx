import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  CreditCard,
  RefreshCw,
  Calendar,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import styles from './Spending.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

/* ─── types ───────────────────────────────────────────────── */

interface MonthlySummary {
  month: number;
  month_name: string;
  total: number;
  count: number;
}

interface CategorySummary {
  category: string;
  total: number;
  count: number;
  percent: number;
  is_monthly: boolean;
}

interface AnnualExpense {
  label: string;
  type: 'trip' | 'category';
  total: number;
}

interface SpendingSummary {
  year: number;
  total_spending: number;
  recurring_spending: number;
  non_monthly_spending: number;
  avg_monthly: number;
  months_with_data: number;
  monthly: MonthlySummary[];
  categories: CategorySummary[];
  annual_expenses: AnnualExpense[];
}

interface Transaction {
  id: number;
  date: string;
  merchant: string;
  category: string;
  account: string;
  original_statement: string;
  notes: string;
  amount: number;
  tags: string;
  owner: string;
}

interface TransactionsResponse {
  transactions: Transaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface Filters {
  categories: string[];
  accounts: string[];
  merchants: string[];
}

interface CashFlowTransaction {
  date: string;
  account: string;
  amount: number;
  description: string;
  type: string;
  direction: 'in' | 'out';
}

interface ExpectedExpense {
  description: string;
  amount: number;
  day_of_month: number;
  category: string;
}

interface CashFlowSummaryMonth {
  month: number;
  month_name: string;
  total: number;
  outflow: number;
  inflow: number;
}

interface CashFlowSummary {
  year: number;
  monthly: CashFlowSummaryMonth[];
  total: number;
  avg_monthly: number;
  outflow_total: number;
  inflow_total: number;
  recurring_total: number;
  one_time_total: number;
  one_time_expenses: CashFlowTransaction[];
  expected_annual: number;
  months_with_data: number;
}

interface CashFlowMonth {
  year: number;
  month: number;
  transactions: CashFlowTransaction[];
  outflow_total: number;
  inflow_total: number;
  net_total: number;
  recurring_total: number;
  expected_total: number;
  expected_expenses: ExpectedExpense[];
  one_time_expenses: CashFlowTransaction[];
  one_time_total: number;
}

/* ─── colors ──────────────────────────────────────────────── */

const CATEGORY_COLORS = [
  '#8B5CF6', '#EF4444', '#F59E0B', '#10B981', '#3B82F6',
  '#EC4899', '#14B8A6', '#F97316', '#6366F1', '#84CC16',
  '#06B6D4', '#D946EF', '#FB923C', '#22D3EE', '#A855F7',
  '#FBBF24', '#34D399', '#F472B6', '#60A5FA', '#A3E635',
];

const MONTH_NAMES_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/* ─── helpers ─────────────────────────────────────────────── */

const fmt = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtFull = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v);

const API = '/api/v1/spending';

/* ─── component ───────────────────────────────────────────── */

export default function Spending() {
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear());
  const [selectedMonth, setSelectedMonth] = useState<number | null>(new Date().getMonth() + 1);
  const [summary, setSummary] = useState<SpendingSummary | null>(null);
  const [cashFlowMonth, setCashFlowMonth] = useState<CashFlowMonth | null>(null);
  const [cashFlowYear, setCashFlowYear] = useState<CashFlowSummary | null>(null);
  const [recurringTxn, setRecurringTxn] = useState<TransactionsResponse | null>(null);
  const [nonMonthlyTxn, setNonMonthlyTxn] = useState<TransactionsResponse | null>(null);
  const [filters, setFilters] = useState<Filters | null>(null);
  const [loading, setLoading] = useState(true);

  // Filter state
  const [search, setSearch] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterAccount, setFilterAccount] = useState('');
  const [recurringPage, setRecurringPage] = useState(1);
  const [nonMonthlyPage, setNonMonthlyPage] = useState(1);

  const [outflows, setOutflows] = useState<{
    as_of: string | null; monarch_through: string | null;
    months: { month: string; card_spending: number; cashback: number; bank_out: number;
              card_net: number; total: number; monarch_total: number | null;
              by_account: Record<string, number> }[];
  } | null>(null);
  const [sortCol, setSortCol] = useState<'description' | 'account' | 'date' | 'amount'>('date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const isMonthView = selectedMonth !== null;

  /* ── data fetching ── */

  const fetchYears = useCallback(async () => {
    try {
      const res = await fetch(`${API}/years`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      const yrs: number[] = data.years ?? [];
      setYears(yrs);
      if (yrs.length && !yrs.includes(selectedYear)) setSelectedYear(yrs[0]);
    } catch { /* ignore */ }
  }, []);

  // selectedMonth MUST stay in the dep list — with an empty array the closure
  // captures the month at mount (null) and every summary fetch silently asks
  // for the whole year, which is what made Categories show year-to-date
  // totals beside June's transactions.
  const fetchSummary = useCallback(async (yr: number) => {
    try {
      const mq = selectedMonth ? `?month=${selectedMonth}` : '';
      const res = await fetch(`${API}/summary/${yr}${mq}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setSummary(await res.json());
    } catch { /* ignore */ }
  }, [selectedMonth]);

  const fetchFilters = useCallback(async (yr: number) => {
    try {
      const res = await fetch(`${API}/filters?year=${yr}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setFilters(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchCashFlowYear = useCallback(async (yr: number) => {
    try {
      const res = await fetch(`${API}/cash-flow/${yr}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setCashFlowYear(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchCashFlowMonth = useCallback(async (yr: number, mo: number) => {
    try {
      const res = await fetch(`${API}/cash-flow/${yr}/${mo}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setCashFlowMonth(await res.json());
    } catch { /* ignore */ }
  }, []);

  const buildParams = useCallback((spendingType: string, pg: number) => {
    const params = new URLSearchParams();
    params.set('year', String(selectedYear));
    params.set('page', String(pg));
    params.set('page_size', '50');
    params.set('spending_type', spendingType);
    if (search) params.set('search', search);
    if (filterCategory) params.set('category', filterCategory);
    if (filterAccount) params.set('account', filterAccount);
    if (selectedMonth !== null) params.set('month', String(selectedMonth));
    return params;
  }, [selectedYear, search, filterCategory, filterAccount, selectedMonth]);

  const fetchRecurring = useCallback(async () => {
    try {
      const res = await fetch(`${API}/transactions?${buildParams('recurring', recurringPage)}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setRecurringTxn(await res.json());
    } catch { /* ignore */ }
  }, [buildParams, recurringPage]);

  const fetchNonMonthly = useCallback(async () => {
    try {
      const res = await fetch(`${API}/transactions?${buildParams('non_monthly', nonMonthlyPage)}`, { headers: getAuthHeaders() });
      if (!res.ok) return;
      setNonMonthlyTxn(await res.json());
    } catch { /* ignore */ }
  }, [buildParams, nonMonthlyPage]);

  /* ── effects ── */

  useEffect(() => {
    fetch(`${API}/outflows`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setOutflows(d))
      .catch(() => {});
  }, []);

  useEffect(() => { fetchYears(); }, [fetchYears]);

  useEffect(() => {
    setLoading(true);
    const fetches: Promise<void>[] = [fetchSummary(selectedYear), fetchFilters(selectedYear), fetchRecurring()];
    if (isMonthView) {
      fetches.push(fetchCashFlowMonth(selectedYear, selectedMonth!));
    } else {
      fetches.push(fetchNonMonthly(), fetchCashFlowYear(selectedYear));
    }
    Promise.all(fetches).finally(() => setLoading(false));
  }, [selectedYear, selectedMonth, fetchSummary, fetchFilters, fetchRecurring, fetchNonMonthly, fetchCashFlowMonth, fetchCashFlowYear, isMonthView]);

  // Reset pages when filters change
  useEffect(() => { setRecurringPage(1); setNonMonthlyPage(1); }, [search, filterCategory, filterAccount, selectedMonth, selectedYear]);

  // Refetch when pages change
  useEffect(() => { fetchRecurring(); }, [recurringPage, fetchRecurring]);
  useEffect(() => { if (!isMonthView) fetchNonMonthly(); }, [nonMonthlyPage, fetchNonMonthly, isMonthView]);

  /* ── derived data ── */

  // For month view: filter categories to recurring only
  const monthCategories = isMonthView
    ? (summary?.categories.filter(c => c.is_monthly) ?? [])
    : (summary?.categories ?? []);

  const donutData = monthCategories.slice(0, 10).map((c, i) => ({
    name: c.category,
    value: c.total,
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));

  // Bar chart uses Robinhood cash flow data when available, falls back to Monarch
  const barData = (cashFlowYear?.monthly ?? summary?.monthly ?? []).map(m => ({
    name: m.month_name.substring(0, 3),
    month: m.month,
    total: m.total,
    outflow: 'outflow' in m ? (m as CashFlowSummaryMonth).outflow : m.total,
    inflow: 'inflow' in m ? (m as CashFlowSummaryMonth).inflow : 0,
  }));

  const handleBarClick = (data: { month: number }) => {
    setSelectedMonth(prev => prev === data.month ? null : data.month);
  };

  const toggleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(col === 'amount' ? 'desc' : 'asc'); }
  };

  // Set of one-time expense keys for fast lookup
  const oneTimeKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const e of cashFlowMonth?.one_time_expenses ?? []) {
      keys.add(`${e.date}|${e.amount}|${e.description}`);
    }
    return keys;
  }, [cashFlowMonth?.one_time_expenses]);

  const getTxnColor = (t: CashFlowTransaction): string => {
    if (t.direction === 'in') return '#10B981';   // green — transfer in
    if (oneTimeKeys.has(`${t.date}|${t.amount}|${t.description}`)) return '#3B82F6'; // blue — one-time
    return '#EF4444'; // red — recurring outflow
  };

  const sortedActualTxns = useMemo(() => {
    const txns = [...(cashFlowMonth?.transactions ?? [])];
    const dir = sortDir === 'asc' ? 1 : -1;
    txns.sort((a, b) => {
      switch (sortCol) {
        case 'description': return dir * a.description.localeCompare(b.description);
        case 'account': {
          const aa = a.account.includes('Neel') ? 'Neel' : 'Jaya';
          const bb = b.account.includes('Neel') ? 'Neel' : 'Jaya';
          return dir * aa.localeCompare(bb);
        }
        case 'date': return dir * a.date.localeCompare(b.date);
        case 'amount': return dir * (a.amount - b.amount);
        default: return 0;
      }
    });
    return txns;
  }, [cashFlowMonth?.transactions, sortCol, sortDir]);

  const SortIcon = ({ col }: { col: typeof sortCol }) => {
    if (sortCol !== col) return null;
    return sortDir === 'asc' ? <ChevronUp size={14} style={{ marginLeft: 4, verticalAlign: 'middle' }} /> : <ChevronDown size={14} style={{ marginLeft: 4, verticalAlign: 'middle' }} />;
  };

  /* ── render ─────────────────────────────────────────────── */

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <CreditCard size={32} />
          </div>
          <div>
            <h1 className={styles.title}>Spending</h1>
            <p className={styles.subtitle}>
              Cash flow from Robinhood + categorized breakdown from Monarch Money
            </p>
          </div>
        </div>
      </header>

      <div className={styles.content}>
        {/* Year Selector */}
        <div className={styles.yearSelector}>
          <Calendar size={18} />
          <span className={styles.yearLabel}>Year:</span>
          {years.map(yr => (
            <button
              key={yr}
              className={`${styles.yearButton} ${selectedYear === yr ? styles.activeYear : ''}`}
              onClick={() => setSelectedYear(yr)}
            >
              {yr}
            </button>
          ))}
        </div>

        {/* Month Pill Selector */}
        <div className={styles.monthSelectorRow}>
          <button
            className={`${styles.monthPill} ${selectedMonth === null ? styles.active : ''}`}
            onClick={() => setSelectedMonth(null)}
          >
            Full Year
          </button>
          {MONTH_NAMES_SHORT.map((m, i) => (
            <button
              key={i + 1}
              className={`${styles.monthPill} ${selectedMonth === i + 1 ? styles.active : ''}`}
              onClick={() => setSelectedMonth(i + 1)}
            >
              {m}
            </button>
          ))}
        </div>

        {/* L1 — total spend from investment-account outflows (fresh via
            sync; Monarch below is composition only). Definition per Neel:
            money leaving Neel's/Jaya's brokerage toward spending channels. */}
        {outflows && (() => {
          const inYear = outflows.months.filter(m => m.month.startsWith(String(selectedYear)));
          const rows = selectedMonth === null
            ? inYear
            : inYear.filter(m => m.month === `${selectedYear}-${String(selectedMonth).padStart(2, '0')}-01`);
          const cardNet = rows.reduce((s, m) => s + m.card_net, 0);
          const bankOut = rows.reduce((s, m) => s + m.bank_out, 0);
          const total = rows.reduce((s, m) => s + m.total, 0);
          const monarchCovered = rows.filter(m => m.monarch_total != null);
          const monarchTotal = monarchCovered.reduce((s, m) => s + (m.monarch_total || 0), 0);
          const periodLabel = selectedMonth === null
            ? `${selectedYear}` : `${MONTH_NAMES_SHORT[selectedMonth - 1]} ${selectedYear}`;
          return (
            <div className={styles.outflowBand}>
              <div>
                {/* Headline is REAL SPENDING from Monarch — what was actually
                    bought. Brokerage outflows measure money leaving the
                    brokerage, which is lumpy pre-funding, not spend; they stay
                    below as a reconciliation line. Putting the outflow number
                    here is what made June read $1,777 against $17,750 spent. */}
                <div className={styles.outflowLabel}>Total spend — {periodLabel}</div>
                <div className={styles.outflowValue}>
                  {fmt(summary?.total_spending ?? monarchTotal)}
                </div>
                <div className={styles.outflowSplit}>
                  <span className={styles.outflowRecon}>
                    brokerage outflows: {fmt(total)} ({fmt(cardNet)} card, {fmt(bankOut)} bank)
                  </span>
                  {summary && total > 0 && (
                    <span className={styles.outflowRecon}>
                      {Math.abs(summary.total_spending - total) / total < 0.05
                        ? 'reconciles'
                        : `Δ ${fmt(Math.abs(summary.total_spending - total))} — outflows are funding, not spend`}
                    </span>
                  )}
                </div>
              </div>
              <div className={styles.outflowFreshness}>
                <span>outflows through {outflows.as_of ? new Date(outflows.as_of + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</span>
                <span className={outflows.monarch_through && outflows.as_of && outflows.monarch_through < outflows.as_of ? styles.staleWarn : undefined}>
                  categorized through {outflows.monarch_through ? new Date(outflows.monarch_through + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                </span>
              </div>
            </div>
          );
        })()}

        {loading && (
          <div className={styles.loadingState}>
            <RefreshCw size={32} className={styles.spinner} />
            <p>Loading spending data...</p>
          </div>
        )}


        {!loading && summary && (
          <>
            {/* ───── MONTH VIEW ───────────────────────────────────── */}
            {isMonthView && (
              <>

                {/* Actual transactions — full width now that Expected is gone. */}
                <div className={styles.twoColumn} style={{ gridTemplateColumns: '1fr' }}>
                  {/* Actual Cash Flow Transactions — Robinhood */}
                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Actual</h3>
                    <p className={styles.chartSubtitle}>
                      {/* No net here — the total is already the headline. */}
                      {cashFlowMonth ? `${cashFlowMonth.transactions.length} transactions` : ''}
                    </p>
                    <div className={styles.tableContainer}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => toggleSort('description')}>
                              Description<SortIcon col="description" />
                            </th>
                            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('account')}>
                              Who<SortIcon col="account" />
                            </th>
                            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>
                              Date<SortIcon col="date" />
                            </th>
                            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>
                              Amount<SortIcon col="amount" />
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedActualTxns.map((t, i) => {
                            const color = getTxnColor(t);
                            const sign = t.direction === 'in' ? '+' : '-';
                            return (
                              <tr key={i} className={styles.transactionRow}>
                                <td style={{ textAlign: 'left', fontFamily: 'inherit', fontWeight: 500, color }}>{t.description}</td>
                                <td style={{ fontFamily: 'inherit', fontSize: '0.85em', color: 'var(--color-text-tertiary)' }}>
                                  {t.account.includes('Neel') ? 'Neel' : 'Jaya'}
                                </td>
                                <td style={{ whiteSpace: 'nowrap' }}>
                                  {new Date(t.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </td>
                                <td style={{ color, fontWeight: 500 }}>{sign}{fmtFull(t.amount)}</td>
                              </tr>
                            );
                          })}
                          {cashFlowMonth && cashFlowMonth.transactions.length === 0 && (
                            <tr>
                              <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-tertiary)', fontFamily: 'inherit' }}>
                                No cash flow transactions for this month
                              </td>
                            </tr>
                          )}
                          {cashFlowMonth && cashFlowMonth.transactions.length > 0 && (
                            <tr style={{ borderTop: '1px solid var(--color-border)' }}>
                              <td colSpan={3} style={{ textAlign: 'left', fontFamily: 'inherit', fontWeight: 700 }}>Net</td>
                              <td style={{ fontWeight: 700, color: cashFlowMonth.net_total > 0 ? '#EF4444' : '#10B981' }}>
                                {cashFlowMonth.net_total > 0 ? '-' : '+'}{fmtFull(Math.abs(cashFlowMonth.net_total))}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* Category Breakdown — Monarch (month view: recurring only) */}
                {donutData.length > 0 && (
                  <div className={styles.twoColumn}>
                    <div className={styles.chartCard}>
                      <h3 className={styles.chartTitle}>Category Breakdown &mdash; Monarch</h3>
                      <div className={styles.chartContainer}>
                        <ResponsiveContainer width="100%" height={300}>
                          <PieChart>
                            <Pie
                              data={donutData}
                              dataKey="value"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={110}
                              paddingAngle={2}
                            >
                              {donutData.map((entry, i) => (
                                <Cell key={i} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip
                              formatter={(value: number) => [fmt(value), 'Spent']}
                              contentStyle={{
                                backgroundColor: 'var(--color-bg-primary)',
                                border: '1px solid var(--color-border)',
                                borderRadius: '8px',
                              }}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    <div className={styles.chartCard}>
                      <h3 className={styles.chartTitle}>Categories</h3>
                      <div className={styles.tableContainer} style={{ maxHeight: 340, overflowY: 'auto' }}>
                        <table className={styles.actualsTable}>
                          <thead>
                            <tr>
                              <th>Category</th>
                              <th>Amount</th>
                              <th>%</th>
                              <th style={{ width: '30%' }}></th>
                            </tr>
                          </thead>
                          <tbody>
                            {monthCategories.map((c, i) => (
                              <tr
                                key={c.category}
                                className={styles.transactionRow}
                                style={{ cursor: 'pointer' }}
                                onClick={() => {
                                  setFilterCategory(c.category);
                                  setRecurringPage(1);
                                }}
                              >
                                <td style={{ fontFamily: 'inherit', fontWeight: 500 }}>
                                  <span
                                    style={{
                                      display: 'inline-block',
                                      width: 10, height: 10,
                                      borderRadius: '50%',
                                      backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                                      marginRight: 8,
                                    }}
                                  />
                                  {c.category}
                                </td>
                                <td className={styles.negative}>{fmt(c.total)}</td>
                                <td>{c.percent}%</td>
                                <td>
                                  <div className={styles.categoryBar}>
                                    <div
                                      className={styles.categoryBarFill}
                                      style={{
                                        width: `${c.percent}%`,
                                        backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                                      }}
                                    />
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {/* Monthly Recurring Expenses — Monarch (filtered to month) */}
                <div className={styles.chartCard}>
                  <h3 className={styles.chartTitle}>Monthly Recurring Expenses &mdash; Monarch</h3>
                  <p className={styles.chartSubtitle}>
                    {recurringTxn ? `${recurringTxn.total} transactions` : ''}
                  </p>

                  {/* Filter Bar (inline) */}
                  <div className={styles.filterBar}>
                    <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                      <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-tertiary)' }} />
                      <input
                        type="text"
                        placeholder="Search merchant, statement, category..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className={styles.searchInput}
                        style={{ paddingLeft: 32 }}
                      />
                    </div>
                    <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className={styles.filterSelect}>
                      <option value="">All Categories</option>
                      {filters?.categories.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <select value={filterAccount} onChange={e => setFilterAccount(e.target.value)} className={styles.filterSelect}>
                      <option value="">All Accounts</option>
                      {filters?.accounts.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    {(search || filterCategory || filterAccount) && (
                      <button className={styles.yearButton} onClick={() => { setSearch(''); setFilterCategory(''); setFilterAccount(''); }}>
                        Clear
                      </button>
                    )}
                  </div>

                  <div className={styles.tableContainer}>
                    <table className={styles.actualsTable}>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th style={{ textAlign: 'left' }}>Merchant</th>
                          <th style={{ textAlign: 'left' }}>Category</th>
                          <th style={{ textAlign: 'left' }}>Account</th>
                          <th>Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recurringTxn?.transactions.map(t => (
                          <tr key={t.id} className={styles.transactionRow}>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              {new Date(t.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                            </td>
                            <td style={{ textAlign: 'left', fontFamily: 'inherit', fontWeight: 500 }}>{t.merchant}</td>
                            <td style={{ textAlign: 'left', fontFamily: 'inherit' }}>
                              <span className={styles.categoryBadge}>{t.category}</span>
                            </td>
                            <td style={{ textAlign: 'left', fontFamily: 'inherit', fontSize: '0.85em', color: 'var(--color-text-tertiary)' }}>{t.account}</td>
                            <td className={styles.negative}>{fmtFull(Math.abs(t.amount))}</td>
                          </tr>
                        ))}
                        {recurringTxn && recurringTxn.transactions.length === 0 && (
                          <tr>
                            <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-tertiary)', fontFamily: 'inherit' }}>
                              No transactions found
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {recurringTxn && recurringTxn.total_pages > 1 && (
                    <div className={styles.pagination}>
                      <button className={styles.pageButton} onClick={() => setRecurringPage(p => Math.max(1, p - 1))} disabled={recurringPage <= 1}>
                        <ChevronLeft size={16} />
                      </button>
                      <span className={styles.pageInfo}>Page {recurringTxn.page} of {recurringTxn.total_pages}</span>
                      <button className={styles.pageButton} onClick={() => setRecurringPage(p => Math.min(recurringTxn.total_pages, p + 1))} disabled={recurringPage >= recurringTxn.total_pages}>
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ───── FULL YEAR VIEW ───────────────────────────────── */}
            {!isMonthView && (
              <>
                {/* Summary Cards — 3 cards matching month view */}
                <div className={styles.summaryGrid} style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Recurring Outflows</span>
                    <span className={`${styles.summaryValue}`} style={{ color: '#EF4444' }}>
                      {fmt(cashFlowYear?.recurring_total ?? 0)}
                    </span>
                    <span className={styles.summaryNote}>
                      {cashFlowYear?.months_with_data ?? 0} months &mdash; Avg {fmt((cashFlowYear?.recurring_total ?? 0) / (cashFlowYear?.months_with_data || 1))}/mo
                    </span>
                  </div>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>Transfers In</span>
                    <span className={`${styles.summaryValue}`} style={{ color: '#10B981' }}>
                      +{fmt(cashFlowYear?.inflow_total ?? 0)}
                    </span>
                    <span className={styles.summaryNote}>Deposits back into brokerage</span>
                  </div>
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>One-Time Expenses</span>
                    {cashFlowYear && cashFlowYear.one_time_expenses.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                        {cashFlowYear.one_time_expenses.map((e, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                            <span style={{ fontSize: 'var(--text-sm)', color: '#3B82F6', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                              {e.description}
                            </span>
                            <span className={styles.summaryValue} style={{ fontSize: 'var(--text-lg)', flexShrink: 0, color: '#3B82F6' }}>
                              {fmt(e.amount)}
                            </span>
                          </div>
                        ))}
                        {cashFlowYear.one_time_expenses.length > 1 && (
                          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-1)', display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Total</span>
                            <span className={styles.summaryValue} style={{ fontSize: 'var(--text-lg)', color: '#3B82F6' }}>
                              {fmt(cashFlowYear.one_time_total)}
                            </span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <>
                        <span className={styles.summaryValue} style={{ color: 'var(--color-text-tertiary)' }}>{fmt(0)}</span>
                        <span className={styles.summaryNote}>No one-time expenses</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Monthly Cash Flow bar chart */}
                <div className={styles.chartCard}>
                  <h3 className={styles.chartTitle}>Monthly Cash Flow</h3>
                  <p className={styles.chartSubtitle}>Click a bar to drill into that month</p>
                  <div style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-3)', fontSize: 'var(--text-xs)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#EF4444', display: 'inline-block' }} /> Outflows
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} /> Inflows
                    </span>
                  </div>
                  <div className={styles.chartContainer}>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={barData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }} style={{ cursor: 'pointer' }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                        <XAxis dataKey="name" stroke="#888" tick={{ fontSize: 12 }} />
                        <YAxis stroke="#888" tickFormatter={(v) => fmt(v)} />
                        <Tooltip
                          formatter={(value: number, name: string) => [fmt(value), name === 'outflow' ? 'Outflows' : name === 'inflow' ? 'Inflows' : 'Net']}
                          contentStyle={{
                            backgroundColor: 'var(--color-bg-primary)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                          }}
                        />
                        <Bar dataKey="outflow" fill="#EF4444" radius={[4, 4, 0, 0]} onClick={(_d, idx) => handleBarClick(barData[idx])} />
                        <Bar dataKey="inflow" fill="#10B981" radius={[4, 4, 0, 0]} onClick={(_d, idx) => handleBarClick(barData[idx])} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  {/* Year totals footer */}
                  {cashFlowYear && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-6)', paddingTop: 'var(--space-3)', borderTop: '1px solid var(--color-border)', marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)' }}>
                      <span style={{ color: '#EF4444', fontWeight: 600 }}>Recurring: -{fmt(cashFlowYear.recurring_total)}</span>
                      {cashFlowYear.one_time_total > 0 && (
                        <span style={{ color: '#3B82F6', fontWeight: 600 }}>One-Time: -{fmt(cashFlowYear.one_time_total)}</span>
                      )}
                      {cashFlowYear.inflow_total > 0 && (
                        <span style={{ color: '#10B981', fontWeight: 600 }}>In: +{fmt(cashFlowYear.inflow_total)}</span>
                      )}
                      <span style={{ fontWeight: 700, color: 'var(--color-text-primary)' }}>Net: {fmt(cashFlowYear.total)}</span>
                    </div>
                  )}
                </div>

                {/* Category Breakdown — Monarch */}
                <div className={styles.twoColumn}>
                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Category Breakdown &mdash; Monarch</h3>
                    <div className={styles.chartContainer}>
                      <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                          <Pie
                            data={donutData}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={110}
                            paddingAngle={2}
                          >
                            {donutData.map((entry, i) => (
                              <Cell key={i} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip
                            formatter={(value: number) => [fmt(value), 'Spent']}
                            contentStyle={{
                              backgroundColor: 'var(--color-bg-primary)',
                              border: '1px solid var(--color-border)',
                              borderRadius: '8px',
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Categories</h3>
                    <div className={styles.tableContainer} style={{ maxHeight: 340, overflowY: 'auto' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Category</th>
                            <th>Amount</th>
                            <th>%</th>
                            <th style={{ width: '30%' }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {summary.categories.map((c, i) => (
                            <tr
                              key={c.category}
                              className={styles.transactionRow}
                              style={{ cursor: 'pointer' }}
                              onClick={() => {
                                setFilterCategory(c.category);
                                setRecurringPage(1);
                                setNonMonthlyPage(1);
                              }}
                            >
                              <td style={{ fontFamily: 'inherit', fontWeight: 500 }}>
                                <span
                                  style={{
                                    display: 'inline-block',
                                    width: 10, height: 10,
                                    borderRadius: '50%',
                                    backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                                    marginRight: 8,
                                  }}
                                />
                                {c.category}
                              </td>
                              <td className={styles.negative}>{fmt(c.total)}</td>
                              <td>{c.percent}%</td>
                              <td>
                                <div className={styles.categoryBar}>
                                  <div
                                    className={styles.categoryBarFill}
                                    style={{
                                      width: `${c.percent}%`,
                                      backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                                    }}
                                  />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* Monarch Transaction Tables */}
                <div className={styles.chartCard} style={{ paddingBottom: 'var(--space-3)' }}>
                  <h3 className={styles.chartTitle}>Monarch Transactions</h3>
                  <div className={styles.filterBar} style={{ marginTop: 'var(--space-3)' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                      <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-tertiary)' }} />
                      <input
                        type="text"
                        placeholder="Search merchant, statement, category..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className={styles.searchInput}
                        style={{ paddingLeft: 32 }}
                      />
                    </div>
                    <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className={styles.filterSelect}>
                      <option value="">All Categories</option>
                      {filters?.categories.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <select value={filterAccount} onChange={e => setFilterAccount(e.target.value)} className={styles.filterSelect}>
                      <option value="">All Accounts</option>
                      {filters?.accounts.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    {(search || filterCategory || filterAccount) && (
                      <button className={styles.yearButton} onClick={() => { setSearch(''); setFilterCategory(''); setFilterAccount(''); }}>
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                <div className={styles.twoColumn} style={{ gridTemplateColumns: '1fr 1fr' }}>
                  {/* Recurring */}
                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Recurring</h3>
                    <p className={styles.chartSubtitle}>{recurringTxn ? `${recurringTxn.total} transactions` : ''}</p>
                    <div className={styles.tableContainer} style={{ maxHeight: 500, overflowY: 'auto' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th style={{ textAlign: 'left' }}>Merchant</th>
                            <th style={{ textAlign: 'left' }}>Category</th>
                            <th>Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {recurringTxn?.transactions.map(t => (
                            <tr key={t.id} className={styles.transactionRow}>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                {new Date(t.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                              </td>
                              <td style={{ textAlign: 'left', fontFamily: 'inherit', fontWeight: 500 }}>{t.merchant}</td>
                              <td style={{ textAlign: 'left', fontFamily: 'inherit' }}>
                                <span className={styles.categoryBadge}>{t.category}</span>
                              </td>
                              <td className={styles.negative}>{fmtFull(Math.abs(t.amount))}</td>
                            </tr>
                          ))}
                          {recurringTxn && recurringTxn.transactions.length === 0 && (
                            <tr>
                              <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-tertiary)', fontFamily: 'inherit' }}>
                                No transactions found
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {recurringTxn && recurringTxn.total_pages > 1 && (
                      <div className={styles.pagination}>
                        <button className={styles.pageButton} onClick={() => setRecurringPage(p => Math.max(1, p - 1))} disabled={recurringPage <= 1}>
                          <ChevronLeft size={16} />
                        </button>
                        <span className={styles.pageInfo}>Page {recurringTxn.page} of {recurringTxn.total_pages}</span>
                        <button className={styles.pageButton} onClick={() => setRecurringPage(p => Math.min(recurringTxn.total_pages, p + 1))} disabled={recurringPage >= recurringTxn.total_pages}>
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Non-Monthly */}
                  <div className={styles.chartCard}>
                    <h3 className={styles.chartTitle}>Non-Monthly</h3>
                    <p className={styles.chartSubtitle}>Taxes, insurance, trips &mdash; {nonMonthlyTxn ? `${nonMonthlyTxn.total} transactions` : ''}</p>
                    <div className={styles.tableContainer} style={{ maxHeight: 500, overflowY: 'auto' }}>
                      <table className={styles.actualsTable}>
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th style={{ textAlign: 'left' }}>Merchant</th>
                            <th style={{ textAlign: 'left' }}>Category</th>
                            <th>Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {nonMonthlyTxn?.transactions.map(t => (
                            <tr key={t.id} className={styles.transactionRow}>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                {new Date(t.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                              </td>
                              <td style={{ textAlign: 'left', fontFamily: 'inherit', fontWeight: 500 }}>{t.merchant}</td>
                              <td style={{ textAlign: 'left', fontFamily: 'inherit' }}>
                                <span className={styles.categoryBadge}>{t.category}</span>
                              </td>
                              <td className={styles.negative}>{fmtFull(Math.abs(t.amount))}</td>
                            </tr>
                          ))}
                          {nonMonthlyTxn && nonMonthlyTxn.transactions.length === 0 && (
                            <tr>
                              <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-tertiary)', fontFamily: 'inherit' }}>
                                No non-monthly transactions found
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {nonMonthlyTxn && nonMonthlyTxn.total_pages > 1 && (
                      <div className={styles.pagination}>
                        <button className={styles.pageButton} onClick={() => setNonMonthlyPage(p => Math.max(1, p - 1))} disabled={nonMonthlyPage <= 1}>
                          <ChevronLeft size={16} />
                        </button>
                        <span className={styles.pageInfo}>Page {nonMonthlyTxn.page} of {nonMonthlyTxn.total_pages}</span>
                        <button className={styles.pageButton} onClick={() => setNonMonthlyPage(p => Math.min(nonMonthlyTxn.total_pages, p + 1))} disabled={nonMonthlyPage >= nonMonthlyTxn.total_pages}>
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
