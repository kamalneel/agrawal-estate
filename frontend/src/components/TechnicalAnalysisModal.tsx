import { useState, useEffect } from 'react';
import {
  X,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  Target,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  BarChart2,
} from 'lucide-react';
import { getAuthHeaders } from '../contexts/AuthContext';
import styles from './TechnicalAnalysisModal.module.css';

interface TechnicalIndicators {
  symbol: string;
  current_price: number;
  year_high: number;
  year_low: number;
  ma_50: number | null;
  ma_200: number | null;
  daily_volatility: number;
  weekly_volatility: number;
  annualized_volatility: number;
  rsi_14: number;
  rsi_status: string;
  bb_upper: number;
  bb_middle: number;
  bb_lower: number;
  bb_position: string;
  resistance_levels: number[];
  support_levels: number[];
  nearest_resistance: number | null;
  nearest_support: number | null;
  prob_68_low: number;
  prob_68_high: number;
  prob_90_low: number;
  prob_90_high: number;
  prob_95_low: number;
  prob_95_high: number;
  trend: string;
  earnings_date: string | null;
  earnings_within_week: boolean;
  analyzed_at: string;
}

interface TechnicalAnalysisModalProps {
  symbol: string;
  isOpen: boolean;
  onClose: () => void;
  // Optional: pre-loaded analysis from recommendation context
  preloadedAnalysis?: any;
}

export default function TechnicalAnalysisModal({
  symbol,
  isOpen,
  onClose,
  preloadedAnalysis,
}: TechnicalAnalysisModalProps) {
  const [indicators, setIndicators] = useState<TechnicalIndicators | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && symbol) {
      if (preloadedAnalysis) {
        // Use preloaded analysis from recommendation context
        setIndicators(preloadedAnalysis);
      } else {
        // Fetch fresh analysis
        fetchAnalysis();
      }
    }
  }, [isOpen, symbol, preloadedAnalysis]);

  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/strategies/technical-analysis/${symbol}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error('Failed to fetch technical analysis');
      }
      const data = await response.json();
      setIndicators(data.indicators);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analysis');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'bullish':
        return <TrendingUp className={styles.bullish} />;
      case 'bearish':
        return <TrendingDown className={styles.bearish} />;
      default:
        return <Minus className={styles.neutral} />;
    }
  };

  const getRsiClass = (status: string) => {
    switch (status) {
      case 'overbought':
        return styles.overbought;
      case 'oversold':
        return styles.oversold;
      default:
        return styles.neutral;
    }
  };

  const formatPercent = (value: number) => `${(value * 100).toFixed(2)}%`;
  const formatPrice = (value: number) => `$${value.toFixed(2)}`;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <BarChart2 size={20} />
            <h2>Technical Analysis: {symbol}</h2>
          </div>
          <button className={styles.closeButton} onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className={styles.content}>
          {loading && (
            <div className={styles.loading}>
              <RefreshCw className={styles.spinner} size={24} />
              <span>Loading analysis...</span>
            </div>
          )}

          {error && (
            <div className={styles.error}>
              <AlertTriangle size={20} />
              <span>{error}</span>
              <button onClick={fetchAnalysis}>Retry</button>
            </div>
          )}

          {indicators && !loading && (
            <>
              {/* Price & Trend */}
              <div className={styles.section}>
                <h3>Price & Trend</h3>
                <div className={styles.grid}>
                  <div className={styles.metric}>
                    <span className={styles.label}>Current Price</span>
                    <span className={styles.value}>{formatPrice(indicators.current_price)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>52-Week Range</span>
                    <span className={styles.value}>
                      {formatPrice(indicators.year_low)} - {formatPrice(indicators.year_high)}
                    </span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>Trend</span>
                    <span className={`${styles.value} ${styles.trend}`}>
                      {getTrendIcon(indicators.trend)}
                      {indicators.trend.charAt(0).toUpperCase() + indicators.trend.slice(1)}
                    </span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>50-Day MA</span>
                    <span className={styles.value}>
                      {indicators.ma_50 ? formatPrice(indicators.ma_50) : 'N/A'}
                    </span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>200-Day MA</span>
                    <span className={styles.value}>
                      {indicators.ma_200 ? formatPrice(indicators.ma_200) : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* RSI & Momentum */}
              <div className={styles.section}>
                <h3>RSI & Momentum</h3>
                <div className={styles.rsiContainer}>
                  <div className={styles.rsiBar}>
                    <div 
                      className={styles.rsiIndicator} 
                      style={{ left: `${indicators.rsi_14}%` }}
                    />
                    <div className={styles.rsiZones}>
                      <span className={styles.oversoldZone}>Oversold</span>
                      <span className={styles.neutralZone}>Neutral</span>
                      <span className={styles.overboughtZone}>Overbought</span>
                    </div>
                  </div>
                  <div className={styles.rsiValue}>
                    <span className={`${styles.rsiNumber} ${getRsiClass(indicators.rsi_status)}`}>
                      RSI: {indicators.rsi_14.toFixed(1)}
                    </span>
                    <span className={getRsiClass(indicators.rsi_status)}>
                      ({indicators.rsi_status})
                    </span>
                  </div>
                </div>
              </div>

              {/* Bollinger Bands */}
              <div className={styles.section}>
                <h3>Bollinger Bands (20-day, 2σ)</h3>
                <div className={styles.bollingerContainer}>
                  <div className={styles.bollingerBand}>
                    <span className={styles.bandLabel}>Upper</span>
                    <span className={styles.bandValue}>{formatPrice(indicators.bb_upper)}</span>
                  </div>
                  <div className={`${styles.bollingerBand} ${styles.middle}`}>
                    <span className={styles.bandLabel}>Middle</span>
                    <span className={styles.bandValue}>{formatPrice(indicators.bb_middle)}</span>
                  </div>
                  <div className={styles.bollingerBand}>
                    <span className={styles.bandLabel}>Lower</span>
                    <span className={styles.bandValue}>{formatPrice(indicators.bb_lower)}</span>
                  </div>
                  <div className={styles.bbPosition}>
                    Position: <strong>{indicators.bb_position.replace(/_/g, ' ')}</strong>
                  </div>
                </div>
              </div>

              {/* Volatility */}
              <div className={styles.section}>
                <h3>Volatility</h3>
                <div className={styles.grid}>
                  <div className={styles.metric}>
                    <span className={styles.label}>Daily</span>
                    <span className={styles.value}>{formatPercent(indicators.daily_volatility)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>Weekly</span>
                    <span className={styles.value}>{formatPercent(indicators.weekly_volatility)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.label}>Annualized</span>
                    <span className={styles.value}>{formatPercent(indicators.annualized_volatility)}</span>
                  </div>
                </div>
              </div>

              {/* Probability Ranges (1-Week) */}
              <div className={styles.section}>
                <h3>1-Week Probability Ranges</h3>
                <div className={styles.probabilityContainer}>
                  <div className={styles.probabilityRow}>
                    <span className={styles.probLabel}>68% (1σ)</span>
                    <span className={styles.probRange}>
                      {formatPrice(indicators.prob_68_low)} - {formatPrice(indicators.prob_68_high)}
                    </span>
                  </div>
                  <div className={styles.probabilityRow}>
                    <span className={styles.probLabel}>90%</span>
                    <span className={styles.probRange}>
                      {formatPrice(indicators.prob_90_low)} - {formatPrice(indicators.prob_90_high)}
                    </span>
                  </div>
                  <div className={styles.probabilityRow}>
                    <span className={styles.probLabel}>95% (2σ)</span>
                    <span className={styles.probRange}>
                      {formatPrice(indicators.prob_95_low)} - {formatPrice(indicators.prob_95_high)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Support & Resistance */}
              <div className={styles.section}>
                <h3>Support & Resistance</h3>
                <div className={styles.levelsContainer}>
                  <div className={styles.levelGroup}>
                    <h4>Resistance</h4>
                    {indicators.resistance_levels.slice(0, 3).map((level, i) => (
                      <div key={`r-${i}`} className={styles.level}>
                        <span>R{i + 1}</span>
                        <span>{formatPrice(level)}</span>
                        <span className={styles.pctAway}>
                          +{(((level - indicators.current_price) / indicators.current_price) * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                    {indicators.resistance_levels.length === 0 && (
                      <span className={styles.noLevels}>None nearby</span>
                    )}
                  </div>
                  <div className={styles.levelGroup}>
                    <h4>Support</h4>
                    {indicators.support_levels.slice(0, 3).reverse().map((level, i) => (
                      <div key={`s-${i}`} className={styles.level}>
                        <span>S{indicators.support_levels.length - i}</span>
                        <span>{formatPrice(level)}</span>
                        <span className={styles.pctAway}>
                          {(((level - indicators.current_price) / indicators.current_price) * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                    {indicators.support_levels.length === 0 && (
                      <span className={styles.noLevels}>None nearby</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Earnings Alert */}
              {indicators.earnings_date && (
                <div className={`${styles.section} ${indicators.earnings_within_week ? styles.warning : ''}`}>
                  <h3>
                    {indicators.earnings_within_week ? (
                      <AlertTriangle className={styles.warningIcon} size={18} />
                    ) : (
                      <CheckCircle size={18} />
                    )}
                    Earnings Date
                  </h3>
                  <p className={indicators.earnings_within_week ? styles.warningText : ''}>
                    {indicators.earnings_date}
                    {indicators.earnings_within_week && ' (within next week - high volatility risk!)'}
                  </p>
                </div>
              )}

              {/* Analysis Timestamp */}
              <div className={styles.footer}>
                <span className={styles.timestamp}>
                  Analyzed: {new Date(indicators.analyzed_at).toLocaleString()}
                </span>
                <button className={styles.refreshButton} onClick={fetchAnalysis}>
                  <RefreshCw size={14} />
                  Refresh
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}


