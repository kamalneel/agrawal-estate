import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { CreditCard, RefreshCw, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import styles from './Spending.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

/* ─── types (mirror backend/app/modules/spending/services.py) ───── */

interface MonthlyPoint {
  month: number; month_name: string;
  total: number; recurring: number; non_monthly: number; count: number;
}
interface CategoryRow {
  category: string; total: number; count: number; refunds: number;
  percent: number; is_monthly: boolean;
}
interface NonMonthlyRow { label: string; type: 'trip' | 'category'; total: number; count: number }
interface MerchantRow { merchant: string; total: number; count: number; category: string }
interface AccountRow { account: string; display: string; total: number; count: number }
interface Summary {
  year: number; month: number | null; period_complete: boolean;
  monarch_through: string | null;
  total_spending: number; recurring_spending: number; non_monthly_spending: number;
  avg_monthly: number; months_with_data: number; transaction_count: number;
  monthly: MonthlyPoint[]; categories: CategoryRow[];
  non_monthly_breakdown: NonMonthlyRow[]; top_merchants: MerchantRow[];
  by_account: AccountRow[];
  flags: {
    uncategorized: { count: number; total: number };
    misfiled_refunds: { count: number; total: number };
    missing_recurring: { month: number; month_name: string; label: string }[];
    holes: { account: string; display: string; from: string; to: string; days: number; typical_gap_days: number }[];
    cancelled_but_charged: { date: string; merchant: string; amount: number }[];
  };
}
interface FreshAccount {
  account: string; display: string; last_date: string | null; days_behind: number | null;
  rows: number; status: 'live' | 'lagging' | 'dead' | 'retired'; note: string | null;
}
interface Freshness {
  monarch_through: string | null; monarch_days_old: number | null;
  data_through: string | null;
  outflows_through: string | null; outflows_days_behind_monarch: number | null;
  outflows_current: boolean; outflows_statement_month: string | null;
  last_complete_month: { year: number; month: number } | null;
  accounts: FreshAccount[]; problems: FreshAccount[];
}
interface OutflowMonth {
  month: string; card_spending: number; cashback: number; bank_out: number;
  card_net: number; total: number; monarch_total: number | null;
}
interface Outflows { as_of: string | null; monarch_through: string | null; months: OutflowMonth[] }
interface Txn {
  id: number; date: string; period: string; merchant: string; category: string;
  raw_category: string | null; account: string; account_display: string;
  original_statement: string; notes: string; amount: number;
  is_refund: boolean; misfiled_refund: boolean; trip: string | null; is_non_monthly: boolean;
}
interface TxnPage { transactions: Txn[]; total: number; total_amount: number; page: number; total_pages: number }
interface Filters { categories: string[]; accounts: { account: string; display: string }[]; merchants: string[] }

/* ─── helpers ──────────────────────────────────────────────── */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const CHART_VARS = [1, 2, 3, 4, 5, 6, 7, 8].map(n => `var(--color-chart-${n})`);
const chartColor = (i: number) => CHART_VARS[i % CHART_VARS.length];

const fmt = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
const fmtFull = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v);
const fmtDate = (iso: string, withYear = false) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-US',
    withYear ? { month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' });

const API = '/api/v1/spending';
const STALE_DAYS = 7;

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: getAuthHeaders() });
    return res.ok ? (await res.json()) as T : null;
  } catch { return null; }
}

const tooltipStyle = {
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: '8px',
  color: 'var(--color-text-primary)',
};

/* ─── component ────────────────────────────────────────────── */

export default function Spending() {
  const [years, setYears] = useState<number[]>([]);
  const [freshness, setFreshness] = useState<Freshness | null>(null);
  const [outflows, setOutflows] = useState<Outflows | null>(null);
  // Period starts undefined until freshness says which month is the last
  // COMPLETE one. Defaulting to the calendar month opened the page on an
  // empty September with a $0 headline and no explanation.
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<number | null>(null);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [yearSummary, setYearSummary] = useState<Summary | null>(null);
  const [filters, setFilters] = useState<Filters | null>(null);
  const [txns, setTxns] = useState<TxnPage | null>(null);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterAccount, setFilterAccount] = useState('');
  const [filterType, setFilterType] = useState<'' | 'recurring' | 'non_monthly'>('');
  const [page, setPage] = useState(1);
  const txnRef = useRef<HTMLDivElement>(null);

  /* ── bootstrap: years + freshness decide the initial period ── */
  useEffect(() => {
    (async () => {
      const [y, f, o] = await Promise.all([
        getJson<{ years: number[] }>(`${API}/years`),
        getJson<Freshness>(`${API}/freshness`),
        getJson<Outflows>(`${API}/outflows`),
      ]);
      const yrs = y?.years ?? [];
      setYears(yrs);
      setFreshness(f);
      setOutflows(o);
      const lcm = f?.last_complete_month;
      if (lcm && yrs.includes(lcm.year)) { setYear(lcm.year); setMonth(lcm.month); }
      else if (yrs.length) { setYear(yrs[0]); setMonth(null); }
    })();
  }, []);

  /* ── period data ── */
  useEffect(() => {
    if (year === null) return;
    setLoading(true);
    const mq = month ? `?month=${month}` : '';
    Promise.all([
      getJson<Summary>(`${API}/summary/${year}${mq}`).then(setSummary),
      getJson<Summary>(`${API}/summary/${year}`).then(setYearSummary),
      getJson<Filters>(`${API}/filters?year=${year}`).then(setFilters),
    ]).finally(() => setLoading(false));
  }, [year, month]);

  useEffect(() => { setPage(1); }, [search, filterCategory, filterAccount, filterType, year, month]);

  const fetchTxns = useCallback(async () => {
    if (year === null) return;
    const p = new URLSearchParams({ year: String(year), page: String(page), page_size: '50' });
    if (month) p.set('month', String(month));
    if (search) p.set('search', search);
    if (filterCategory) p.set('category', filterCategory);
    if (filterAccount) p.set('account', filterAccount);
    if (filterType) p.set('spending_type', filterType);
    setTxns(await getJson<TxnPage>(`${API}/transactions?${p}`));
  }, [year, month, page, search, filterCategory, filterAccount, filterType]);
  useEffect(() => { fetchTxns(); }, [fetchTxns]);

  /* ── derived ── */
  const isMonth = month !== null;
  const periodLabel = year === null ? '' : isMonth ? `${MONTHS[month! - 1]} ${year}` : `${year}`;
  const monarchThrough = freshness?.monarch_through ?? null;
  const dataThrough = freshness?.data_through ?? monarchThrough;

  const monthDisabled = (m: number) =>
    year !== null && dataThrough !== null && `${year}-${String(m).padStart(2, '0')}-01` > dataThrough;

  const monthlyCats = summary?.categories.filter(c => c.is_monthly) ?? [];
  const nonMonthlyCats = summary?.categories.filter(c => !c.is_monthly) ?? [];

  const donut = useMemo(() => {
    const cats = summary?.categories ?? [];
    const top = cats.slice(0, 8).map((c, i) => ({ name: c.category, value: c.total, color: chartColor(i) }));
    const rest = cats.slice(8).reduce((s, c) => s + c.total, 0);
    if (rest > 0) top.push({ name: `Other (${cats.length - 8})`, value: rest, color: 'var(--color-text-tertiary)' });
    return top;
  }, [summary]);

  const outflowPeriod = useMemo(() => {
    if (!outflows || year === null) return null;
    const rows = outflows.months.filter(m => m.month.startsWith(String(year)) &&
      (!isMonth || m.month === `${year}-${String(month).padStart(2, '0')}-01`));
    if (!rows.length) return null;
    return {
      total: rows.reduce((s, m) => s + m.total, 0),
      card: rows.reduce((s, m) => s + m.card_net, 0),
      bank: rows.reduce((s, m) => s + m.bank_out, 0),
    };
  }, [outflows, year, month, isMonth]);

  // Baseline for the month view: this month's recurring vs the year's
  // average recurring month (L2 seed — "is this month normal?").
  const baseline = useMemo(() => {
    if (!isMonth || !summary || !yearSummary || yearSummary.months_with_data < 2) return null;
    const avg = yearSummary.avg_monthly;
    if (!avg) return null;
    return { avg, delta: (summary.recurring_spending - avg) / avg };
  }, [isMonth, summary, yearSummary]);

  // Outflows come from the monthly statement: stale means the last complete
  // month's statement is not in, not that the newest row is a few days old.
  const outflowsStale = freshness != null && !freshness.outflows_current;
  const monarchStale = freshness?.monarch_days_old != null && freshness.monarch_days_old > STALE_DAYS;
  const problemAccounts = freshness?.problems ?? [];

  const pickCategory = (label: string) => {
    setFilterCategory(prev => (prev === label ? '' : label));
    txnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const clearFilters = () => { setSearch(''); setFilterCategory(''); setFilterAccount(''); setFilterType(''); };

  /* ── render ────────────────────────────────────────────── */

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}><CreditCard size={28} /></div>
          <div>
            <h1 className={styles.title}>Spending</h1>
            <p className={styles.subtitle}>What was bought, on what — categorized by Monarch; brokerage outflows as a cross-check</p>
          </div>
        </div>
      </header>

      <div className={styles.content}>
        {/* Period control — the page's only one */}
        <div className={styles.periodRow}>
          <span className={styles.periodLabel}>Year</span>
          {years.map(y => (
            <button key={y} className={`${styles.pill} ${year === y ? styles.active : ''}`}
              onClick={() => setYear(y)}>{y}</button>
          ))}
        </div>
        <div className={styles.periodRow}>
          <span className={styles.periodLabel}>Month</span>
          <button className={`${styles.pill} ${month === null ? styles.active : ''}`} onClick={() => setMonth(null)}>
            Full year
          </button>
          {MONTHS.map((m, i) => (
            <button key={m} disabled={monthDisabled(i + 1)}
              className={`${styles.pill} ${month === i + 1 ? styles.active : ''}`}
              onClick={() => setMonth(i + 1)}>{m}</button>
          ))}
        </div>

        {/* L1 — headline */}
        {summary && (
          <div className={styles.headline}>
            <div>
              <div className={styles.headlineLabel}>
                Total spend — {periodLabel}{!summary.period_complete && ' (partial)'}
              </div>
              <div className={styles.headlineValue}>{fmt(summary.total_spending)}</div>
              <div className={styles.headlineSplit}>
                <span>Recurring <strong>{fmt(summary.recurring_spending)}</strong></span>
                <span>Non-monthly <strong>{fmt(summary.non_monthly_spending)}</strong></span>
                {!isMonth && summary.months_with_data > 0 && (
                  <span>Avg recurring <strong>{fmt(summary.avg_monthly)}</strong>/mo over {summary.months_with_data} months</span>
                )}
                {baseline && (
                  <span>
                    vs {fmt(baseline.avg)} avg recurring month{' '}
                    <strong className={baseline.delta > 0.15 ? styles.negative : baseline.delta < -0.15 ? styles.positive : undefined}>
                      {baseline.delta >= 0 ? '+' : ''}{Math.round(baseline.delta * 100)}%
                    </strong>
                  </span>
                )}
                <span className={styles.muted}>{summary.transaction_count} transactions</span>
              </div>
              {outflowPeriod && (
                <div className={styles.recon}>
                  {isMonth
                    ? `Brokerage funded ${fmt(outflowPeriod.total)} this month`
                    : `Brokerage outflows ${fmt(outflowPeriod.total)} (${fmt(outflowPeriod.card)} card channel, ${fmt(outflowPeriod.bank)} bank) · Δ ${fmt(Math.abs(summary.total_spending - outflowPeriod.total))} vs categorized`}
                </div>
              )}
              {(summary.flags.holes.length > 0 || summary.flags.cancelled_but_charged.length > 0 || summary.flags.missing_recurring.length > 0 || summary.flags.uncategorized.total >= 50 || summary.flags.misfiled_refunds.count > 0) && (
                <div className={styles.flagRow}>
                  {summary.flags.cancelled_but_charged.map(c => (
                    <span key={`${c.merchant}-${c.date}`} className={`${styles.flag} ${styles.flagCritical}`} title="You said this subscription was cancelled; it charged again.">
                      {c.merchant} charged {fmt(c.amount)} on {fmtDate(c.date)} after cancellation
                    </span>
                  ))}
                  {summary.flags.holes.map(h => (
                    <span key={`${h.account}-${h.from}`} className={`${styles.flag} ${styles.flagCritical}`}
                      title={`This account normally has a transaction every ${h.typical_gap_days} day(s); ${h.days} days with none means the feed dropped. Re-export this range from Monarch, or import the Robinhood card CSV.`}>
                      {h.display}: no data {fmtDate(h.from)}–{fmtDate(h.to)} — total is understated
                    </span>
                  ))}
                  {summary.flags.missing_recurring.map(f => (
                    <span key={`${f.month}-${f.label}`} className={`${styles.flag} ${styles.flagCritical}`}>
                      No {f.label} in {f.month_name}
                    </span>
                  ))}
                  {summary.flags.uncategorized.total >= 50 && (
                    <button className={`${styles.flag} ${styles.flagWarn} ${styles.rowClickable}`} onClick={() => pickCategory('Uncategorized')}>
                      {summary.flags.uncategorized.count} uncategorized · {fmt(summary.flags.uncategorized.total)}
                    </button>
                  )}
                  {summary.flags.misfiled_refunds.count > 0 && (
                    <span className={`${styles.flag} ${styles.flagWarn}`} title="Refunds Monarch filed as income; netted here against the charge they reverse. Fix the category in Monarch.">
                      {summary.flags.misfiled_refunds.count} refunds filed as income · {fmt(summary.flags.misfiled_refunds.total)} netted
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className={styles.freshness}>
              <span className={monarchStale ? styles.stale : undefined}>
                Monarch through {monarchThrough ? fmtDate(monarchThrough, true) : '—'}
                {dataThrough && monarchThrough && dataThrough > monarchThrough && ` · Robinhood card through ${fmtDate(dataThrough)}`}
                {monarchStale && ` · ${freshness!.monarch_days_old} days old, export Monarch`}
              </span>
              <span className={outflowsStale ? styles.stale : undefined}>
                {outflowsStale
                  ? `Brokerage outflows: ${freshness?.outflows_statement_month ?? 'last month'} statement not imported`
                  : `Brokerage outflows: ${freshness?.outflows_statement_month ?? ''} statement in, through ${freshness?.outflows_through ? fmtDate(freshness.outflows_through) : '—'}`}
              </span>
              {problemAccounts.map(a => (
                <span key={a.account} className={a.status === 'dead' ? styles.dead : styles.stale}>
                  {a.display}: {a.status} since {a.last_date ? fmtDate(a.last_date) : '—'}
                </span>
              ))}
              {freshness && (
                <details>
                  <summary>All {freshness.accounts.length} accounts</summary>
                  <ul className={styles.freshnessList}>
                    {freshness.accounts.map(a => (
                      <li key={a.account} className={a.status === 'dead' ? styles.dead : a.status === 'lagging' ? styles.stale : a.status === 'retired' ? styles.muted : undefined}>
                        {a.display} · {a.last_date ? fmtDate(a.last_date) : '—'}{a.status === 'retired' ? ' · retired' : ''}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        )}

        {loading && !summary && (
          <div className={styles.loadingState}><RefreshCw size={28} className={styles.spinner} /><p>Loading spending…</p></div>
        )}

        {summary && (
          <>
            {/* L3 — trend (year view) */}
            {!isMonth && summary.monthly.length > 0 && (
              <div className={styles.card}>
                <h3 className={styles.cardTitle}>By month</h3>
                <p className={styles.cardSubtitle}>Click a month to drill in</p>
                <div className={styles.legend}>
                  <span><i className={styles.swatch} style={{ background: 'var(--color-chart-2)' }} />Recurring</span>
                  <span><i className={styles.swatch} style={{ background: 'var(--color-chart-4)' }} />Non-monthly (taxes, insurance, trips, one-time)</span>
                </div>
                <div className={styles.chartContainer}>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={summary.monthly.map(m => ({ ...m, name: MONTHS[m.month - 1] }))}
                      margin={{ top: 8, right: 16, left: 8, bottom: 8 }} style={{ cursor: 'pointer' }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                      <XAxis dataKey="name" stroke="var(--color-text-tertiary)" tick={{ fontSize: 12, fill: 'var(--color-text-tertiary)' }} />
                      <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 12, fill: 'var(--color-text-tertiary)' }} tickFormatter={v => fmt(v)} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--color-bg-hover)' }}
                        formatter={(v: number, n: string) => [fmt(v), n === 'recurring' ? 'Recurring' : 'Non-monthly']} />
                      <Bar dataKey="recurring" stackId="a" fill="var(--color-chart-2)"
                        onClick={(d: MonthlyPoint) => setMonth(d.month)} />
                      <Bar dataKey="non_monthly" stackId="a" fill="var(--color-chart-4)" radius={[4, 4, 0, 0]}
                        onClick={(d: MonthlyPoint) => setMonth(d.month)} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className={styles.chartFooter}>
                  <span>Recurring <strong>{fmt(summary.recurring_spending)}</strong></span>
                  <span>Non-monthly <strong>{fmt(summary.non_monthly_spending)}</strong></span>
                  <span>Total <strong className={styles.negative}>{fmt(summary.total_spending)}</strong></span>
                </div>
              </div>
            )}

            {/* L3 — composition */}
            <div className={styles.twoColumn}>
              <div className={styles.card}>
                <h3 className={styles.cardTitle}>Where it went</h3>
                <p className={styles.cardSubtitle}>Top 8 categories, rest grouped</p>
                <div className={styles.chartContainer}>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie data={donut} dataKey="value" nameKey="name" cx="50%" cy="50%"
                        innerRadius={60} outerRadius={110} paddingAngle={2} stroke="var(--color-bg-secondary)">
                        {donut.map((d, i) => <Cell key={i} fill={d.color} />)}
                      </Pie>
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), 'Spent']} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className={styles.card}>
                <h3 className={styles.cardTitle}>Categories</h3>
                <p className={styles.cardSubtitle}>Every category, ties to the headline · click to see its transactions</p>
                <div className={`${styles.tableContainer} ${styles.scrollY}`}>
                  <table className={styles.table}>
                    <thead>
                      <tr><th className={styles.left}>Category</th><th>Amount</th><th>%</th><th style={{ width: '28%' }}></th></tr>
                    </thead>
                    <tbody>
                      {monthlyCats.map((c, i) => (
                        <CategoryTr key={c.category} c={c} color={chartColor(summary.categories.indexOf(c))} selected={filterCategory === c.category} onClick={() => pickCategory(c.category)} idx={i} />
                      ))}
                      {nonMonthlyCats.length > 0 && (
                        <tr className={styles.groupRow}><td className={styles.left} colSpan={4}>Non-monthly · {fmt(nonMonthlyCats.reduce((s, c) => s + c.total, 0))}</td></tr>
                      )}
                      {nonMonthlyCats.map((c, i) => (
                        <CategoryTr key={c.category} c={c} color={chartColor(summary.categories.indexOf(c))} selected={filterCategory === c.category} onClick={() => pickCategory(c.category)} idx={i} />
                      ))}
                      <tr className={styles.totalRow}>
                        <td className={styles.left}>Total</td>
                        <td className={styles.negative}>{fmt(summary.total_spending)}</td>
                        <td>100%</td><td></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* L4 — merchants and accounts */}
            <div className={styles.twoColumn}>
              <div className={styles.card}>
                <h3 className={styles.cardTitle}>Top merchants</h3>
                <p className={styles.cardSubtitle}>Where the money actually goes</p>
                <div className={styles.tableContainer}>
                  <table className={styles.table}>
                    <thead><tr><th className={styles.left}>Merchant</th><th className={styles.left}>Category</th><th>#</th><th>Amount</th></tr></thead>
                    <tbody>
                      {summary.top_merchants.map(m => (
                        <tr key={m.merchant} className={styles.rowClickable} onClick={() => { setSearch(m.merchant); txnRef.current?.scrollIntoView({ behavior: 'smooth' }); }}>
                          <td className={styles.left}>{m.merchant}</td>
                          <td className={styles.left}><span className={styles.badge}>{m.category}</span></td>
                          <td className={styles.muted}>{m.count}</td>
                          <td className={styles.negative}>{fmt(m.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className={styles.card}>
                <h3 className={styles.cardTitle}>By account</h3>
                <p className={styles.cardSubtitle}>Fixed order, never by amount</p>
                <div className={styles.tableContainer}>
                  <table className={styles.table}>
                    <thead><tr><th className={styles.left}>Account</th><th>#</th><th>Amount</th></tr></thead>
                    <tbody>
                      {summary.by_account.map(a => (
                        <tr key={a.account} className={`${styles.rowClickable} ${filterAccount === a.account ? styles.rowSelected : ''}`}
                          onClick={() => setFilterAccount(prev => prev === a.account ? '' : a.account)}>
                          <td className={styles.left}>{a.display}</td>
                          <td className={styles.muted}>{a.count}</td>
                          <td className={a.total > 0 ? styles.negative : styles.muted}>{a.total > 0 ? fmt(a.total) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {summary.non_monthly_breakdown.length > 0 && (
                  <>
                    <h3 className={styles.cardTitle} style={{ marginTop: 'var(--space-5)' }}>Non-monthly detail</h3>
                    <p className={styles.cardSubtitle}>Trips (all spend inside the dates) and one-off categories</p>
                    <div className={styles.tableContainer}>
                      <table className={styles.table}>
                        <tbody>
                          {summary.non_monthly_breakdown.map(n => (
                            <tr key={n.label}>
                              <td className={styles.left}>{n.label}{n.type === 'trip' && <span className={styles.badge} style={{ marginLeft: 'var(--space-2)' }}>trip</span>}</td>
                              <td className={styles.muted}>{n.count}</td>
                              <td className={styles.negative}>{fmt(n.total)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* L5 — transactions */}
            <div className={styles.card} ref={txnRef}>
              <h3 className={styles.cardTitle}>Transactions — {periodLabel}</h3>
              <p className={styles.cardSubtitle}>
                {txns ? `${txns.total} rows · ${fmt(txns.total_amount)}` : ''}
                {filterCategory && ` · ${filterCategory}`}
                {filterAccount && ` · ${filters?.accounts.find(a => a.account === filterAccount)?.display ?? filterAccount}`}
              </p>
              <div className={styles.filterBar}>
                <div className={styles.searchWrap}>
                  <Search size={16} className={styles.searchIcon} />
                  <input className={styles.input} placeholder="Search merchant, statement, category…" value={search} onChange={e => setSearch(e.target.value)} />
                </div>
                <select className={styles.select} value={filterCategory} onChange={e => setFilterCategory(e.target.value)}>
                  <option value="">All categories</option>
                  {filters?.categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <select className={styles.select} value={filterAccount} onChange={e => setFilterAccount(e.target.value)}>
                  <option value="">All accounts</option>
                  {filters?.accounts.map(a => <option key={a.account} value={a.account}>{a.display}</option>)}
                </select>
                <select className={styles.select} value={filterType} onChange={e => setFilterType(e.target.value as typeof filterType)}>
                  <option value="">Recurring + non-monthly</option>
                  <option value="recurring">Recurring only</option>
                  <option value="non_monthly">Non-monthly only</option>
                </select>
                {(search || filterCategory || filterAccount || filterType) && (
                  <button className={styles.pill} onClick={clearFilters}>Clear</button>
                )}
              </div>
              <div className={styles.tableContainer}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th className={styles.left}>Date</th>
                      <th className={styles.left}>Merchant</th>
                      <th className={styles.left}>Category</th>
                      <th className={styles.left}>Account</th>
                      <th>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {txns?.transactions.map(t => (
                      <tr key={t.id} title={t.original_statement || undefined}>
                        <td className={styles.left} style={{ whiteSpace: 'nowrap' }}>
                          {fmtDate(t.date)}
                          {t.period !== t.date.slice(0, 7) && <span className={`${styles.badge} ${styles.small}`} style={{ marginLeft: 'var(--space-1)' }} title="Paid early; counted in the month it is for">→ {MONTHS[Number(t.period.slice(5)) - 1]}</span>}
                        </td>
                        <td className={styles.left}>{t.merchant}</td>
                        <td className={styles.left}>
                          <span className={styles.badge} title={t.raw_category && t.raw_category !== t.category ? `Monarch: ${t.raw_category}` : undefined}>{t.category}</span>
                          {t.misfiled_refund && <span className={`${styles.badge} ${styles.badgeWarn}`} style={{ marginLeft: 'var(--space-1)' }}>refund filed as income</span>}
                          {t.trip && <span className={styles.badge} style={{ marginLeft: 'var(--space-1)' }}>{t.trip}</span>}
                        </td>
                        <td className={`${styles.left} ${styles.muted} ${styles.small}`}>{t.account_display}</td>
                        <td className={t.amount > 0 ? styles.positive : styles.negative}>
                          {t.amount > 0 ? '+' : ''}{fmtFull(Math.abs(t.amount))}
                        </td>
                      </tr>
                    ))}
                    {txns && txns.transactions.length === 0 && (
                      <tr><td colSpan={5} className={styles.empty}>No transactions match</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              {txns && txns.total_pages > 1 && (
                <div className={styles.pagination}>
                  <button className={styles.pageButton} onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}><ChevronLeft size={16} /></button>
                  <span className={styles.pageInfo}>Page {txns.page} of {txns.total_pages}</span>
                  <button className={styles.pageButton} onClick={() => setPage(p => Math.min(txns.total_pages, p + 1))} disabled={page >= txns.total_pages}><ChevronRight size={16} /></button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CategoryTr({ c, color, selected, onClick, idx }: {
  c: CategoryRow; color: string; selected: boolean; onClick: () => void; idx: number;
}) {
  return (
    <tr className={`${styles.rowClickable} ${selected ? styles.rowSelected : ''}`} onClick={onClick} data-idx={idx}>
      <td className={styles.left}>
        <span className={styles.dot} style={{ background: color }} />
        {c.category}
        {c.refunds > 0 && <span className={`${styles.muted} ${styles.small}`}> · {fmt(c.refunds)} refunded</span>}
      </td>
      <td className={styles.negative}>{fmt(c.total)}</td>
      <td className={styles.muted}>{c.percent}%</td>
      <td><div className={styles.bar}><div className={styles.barFill} style={{ width: `${Math.min(100, c.percent)}%`, background: color }} /></div></td>
    </tr>
  );
}
