import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ComposedChart,
} from 'recharts';
import styles from './BuyBorrowDie.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

/**
 * "vs. QQQ buy-and-hold" — docs/BBD-BENCHMARK-SPEC.md.
 * A twin portfolio buys the index with the brokerages' starting value and
 * receives every real deposit and withdrawal on the same day. Same money in,
 * same money out; the dollar difference at the end is the verdict.
 */

interface BenchmarkPoint {
  date: string; label: string; actual: number; twin_sell: number; twin_borrow: number;
  twin_loan: number; price: number; flows: number;
}
interface BenchmarkYear {
  year: string; from: string; to: string;
  actual_twr_pct: number | null; index_twr_pct: number | null;
  growth_pct: number | null; income_pct: number | null;
  actual_end: number; twin_sell_end: number | null; twin_borrow_end: number | null;
}
interface BenchmarkResponse {
  error?: string;
  symbol: string;
  start: { date: string; value: number; price: number };
  end: { date: string; actual: number; twin_sell: number; twin_borrow: number; twin_loan: number; price: number };
  gap_vs_sell: number; gap_vs_sell_pct_of_start: number;
  gap_vs_borrow: number; gap_vs_borrow_pct_of_start: number;
  index_return_pct: number;
  flows: { count: number; net: number; deposits: number; withdrawals: number };
  series: BenchmarkPoint[];
  years: BenchmarkYear[];
  assumptions: { margin_rate_pct: number; pre_tax: boolean; index_dividends: string; price_source: string; note: string };
}

const usd = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
const usdShort = (v: number) => (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${(v / 1e3).toFixed(0)}K`);
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? '—' : `${v.toFixed(d)}%`);
const signed = (v: number) => `${v >= 0 ? '+' : '−'}${usd(Math.abs(v))}`;
const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

export default function BbdBenchmark() {
  const [symbol, setSymbol] = useState<'QQQ' | 'SPY'>('QQQ');
  const [data, setData] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/v1/strategies/buy-borrow-die/benchmark?symbol=${symbol}`, { headers: getAuthHeaders() })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d: BenchmarkResponse = await r.json();
        if (cancelled) return;
        if (d.error) setError(d.error); else setData(d);
      })
      .catch((e) => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  const ahead = data ? data.gap_vs_sell >= 0 : false;

  return (
    <div className={styles.section}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
        <div>
          <h2 className={styles.sectionHeader}>Did the strategy beat buying {symbol}?</h2>
          <p className={styles.sectionSubtitle}>
            A twin portfolio buys {symbol} with the brokerages' value on day one and gets every real deposit and
            withdrawal on the same day. Same money in, same money out. The dollar gap at the end is the answer.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {(['QQQ', 'SPY'] as const).map((s) => (
            <button key={s} className={`${styles.yearButton} ${symbol === s ? styles.activeYear : ''}`} onClick={() => setSymbol(s)}>
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className={styles.loadingState}><AlertTriangle size={32} /><p>{error}</p></div>
      )}
      {loading && !data && <div className={styles.loadingState}><p>Running the twin…</p></div>}

      {data && (
        <>
          {/* Verdict */}
          <p style={{ fontSize: 'var(--text-lg)', color: 'var(--color-text-primary)', margin: '0 0 var(--space-5) 0', maxWidth: '72ch' }}>
            Since {longDate(data.start.date)}, with the same money in and out, your brokerages are worth{' '}
            <strong>{usd(data.end.actual)}</strong>. A {symbol} twin that sold shares to fund the withdrawals would be{' '}
            <strong>{usd(data.end.twin_sell)}</strong>. You are{' '}
            <strong className={ahead ? styles.positive : styles.negative}>
              {usd(Math.abs(data.gap_vs_sell))} {ahead ? 'ahead' : 'behind'}
            </strong>{' '}
            ({pct(Math.abs(data.gap_vs_sell_pct_of_start))} of the starting value). A twin that borrowed instead, like you do,
            would be <strong>{usd(data.end.twin_borrow)}</strong> after its loan.
          </p>

          {/* Cards */}
          <div className={styles.summaryGrid}>
            <div className={styles.summaryCard}>
              <span className={styles.summaryLabel}>Your brokerages</span>
              <span className={styles.summaryValue}>{usd(data.end.actual)}</span>
              <span className={styles.summaryNote}>{longDate(data.end.date)} · started {usd(data.start.value)}</span>
            </div>
            <div className={styles.summaryCard}>
              <span className={styles.summaryLabel}>{symbol} twin, sells to spend</span>
              <span className={styles.summaryValue}>{usd(data.end.twin_sell)}</span>
              <span className={styles.summaryNote}>{symbol} price {pct(data.index_return_pct)} over the window</span>
            </div>
            <div className={styles.summaryCard}>
              <span className={styles.summaryLabel}>{symbol} twin, borrows to spend</span>
              <span className={styles.summaryValue}>{usd(data.end.twin_borrow)}</span>
              <span className={styles.summaryNote}>after a {usd(data.end.twin_loan)} loan at {data.assumptions.margin_rate_pct.toFixed(0)}%</span>
            </div>
            <div className={`${styles.summaryCard} ${ahead ? styles.success : styles.danger}`}>
              <span className={styles.summaryLabel}>Gap vs sell twin</span>
              <span className={`${styles.summaryValue} ${ahead ? styles.positive : styles.negative}`}>{signed(data.gap_vs_sell)}</span>
              <span className={styles.summaryNote}>vs borrow twin {signed(data.gap_vs_borrow)}</span>
            </div>
          </div>

          {/* Chart */}
          <div className={styles.chartCard}>
            <h3 className={styles.chartTitle}>Your brokerages vs the {symbol} twins</h3>
            <p className={styles.chartSubtitle}>
              Net liquidation value at each month-end and today. All three lines saw the same {data.flows.count} deposits and
              withdrawals (net {signed(data.flows.net)}), so the space between them is the strategy, not the spending.
            </p>
            <div className={styles.chartContainer}>
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={data.series} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="label" stroke="#888" tick={{ fontSize: 12 }} />
                  <YAxis stroke="#888" tickFormatter={usdShort} domain={['auto', 'auto']} width={80} />
                  <Tooltip
                    formatter={(value: number, name: string) => [usd(value), name]}
                    contentStyle={{ backgroundColor: 'var(--color-bg-primary)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="actual" name="Your brokerages" stroke="#10B981" strokeWidth={3} dot={false} />
                  <Line type="monotone" dataKey="twin_sell" name={`${symbol} twin, sells`} stroke="#F59E0B" strokeWidth={2} strokeDasharray="6 3" dot={false} />
                  <Line type="monotone" dataKey="twin_borrow" name={`${symbol} twin, borrows`} stroke="#8B5CF6" strokeWidth={2} strokeDasharray="2 3" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Per-year table */}
          <div className={styles.tableContainer}>
            <table className={styles.actualsTable}>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Window</th>
                  <th>Your value</th>
                  <th>{symbol} twin, sells</th>
                  <th>Gap</th>
                  <th title="Combined Modified Dietz return of the two brokerages (the Growth + Income metric)">Your return</th>
                  <th title={`${symbol} price change over the same window, dividends excluded`}>{symbol} return</th>
                  <th title="Your return with all investment income stripped out: what the holdings themselves did">of which growth</th>
                  <th title="Options + dividends + interest as a share of the portfolio">of which income</th>
                </tr>
              </thead>
              <tbody>
                {data.years.map((y) => {
                  const gap = y.twin_sell_end === null ? null : y.actual_end - y.twin_sell_end;
                  const good = gap !== null && gap >= 0;
                  return (
                    <tr key={y.year} className={good ? styles.positiveRow : styles.negativeRow}>
                      <td><strong>{y.year}</strong></td>
                      <td>{longDate(y.from)} → {longDate(y.to)}</td>
                      <td>{usd(y.actual_end)}</td>
                      <td>{y.twin_sell_end === null ? '—' : usd(y.twin_sell_end)}</td>
                      <td className={good ? styles.positive : styles.negative}>{gap === null ? '—' : signed(gap)}</td>
                      <td className={(y.actual_twr_pct ?? 0) >= (y.index_twr_pct ?? 0) ? styles.positive : styles.negative}>{pct(y.actual_twr_pct)}</td>
                      <td>{pct(y.index_twr_pct)}</td>
                      <td>{pct(y.growth_pct)}</td>
                      <td>{pct(y.income_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Where the gap comes from */}
          <div className={styles.summaryGrid} style={{ marginTop: 'var(--space-5)' }}>
            {data.years.map((y) => {
              const lag = (y.actual_twr_pct ?? 0) - (y.index_twr_pct ?? 0);
              const growthLag = (y.growth_pct ?? 0) - (y.index_twr_pct ?? 0);
              return (
                <div key={`why-${y.year}`} className={styles.summaryCard} style={{ gridColumn: 'span 2' }}>
                  <span className={styles.summaryLabel}>{y.year}: where the {lag >= 0 ? 'lead' : 'lag'} comes from</span>
                  <span className={styles.summaryNote} style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
                    Your holdings grew {pct(y.growth_pct)} while {symbol} did {pct(y.index_twr_pct)}: that is{' '}
                    <strong className={growthLag >= 0 ? styles.positive : styles.negative}>{growthLag >= 0 ? '+' : ''}{growthLag.toFixed(1)} pts</strong> from the names
                    and the caps on them. Income added <strong>{pct(y.income_pct)}</strong> on top, which{' '}
                    {lag >= 0 ? 'was enough to finish ahead' : 'closed part of it'}: net <strong className={lag >= 0 ? styles.positive : styles.negative}>{lag >= 0 ? '+' : ''}{lag.toFixed(1)} pts</strong> against {symbol}.
                  </span>
                </div>
              );
            })}
          </div>

          {/* Assumptions strip */}
          <p className={styles.summaryNote} style={{ marginTop: 'var(--space-4)', maxWidth: '90ch' }}>
            Start {longDate(data.start.date)} at {usd(data.start.value)} ({symbol} {data.start.price.toFixed(2)}). {data.flows.count} flows replayed:
            deposits {usd(data.flows.deposits)}, withdrawals {usd(Math.abs(data.flows.withdrawals))}. Borrow twin pays {data.assumptions.margin_rate_pct.toFixed(0)}%/yr,
            compounding monthly. Pre-tax on both sides. {symbol} dividends (~0.5%/yr) not counted, which flatters your side slightly.
            Prices: Robinhood daily closes.
          </p>
        </>
      )}
    </div>
  );
}
