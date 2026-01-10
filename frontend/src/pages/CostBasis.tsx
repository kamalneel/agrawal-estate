import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, DollarSign, FileText, Filter, Download, Upload, RefreshCw } from 'lucide-react';
import styles from './CostBasis.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface CapitalGainsSummary {
  tax_year: number;
  total_short_term_gain: number;
  total_long_term_gain: number;
  total_gain: number;
  total_proceeds: number;
  total_cost_basis: number;
  num_transactions: number;
  by_symbol: {
    [symbol: string]: {
      short_term_gain: number;
      long_term_gain: number;
      total_gain: number;
      proceeds: number;
      cost_basis: number;
      num_sales: number;
    };
  };
}

interface RealizedGain {
  sale_id: number;
  symbol: string;
  sale_date: string;
  purchase_date: string;
  quantity_sold: number;
  proceeds: number;
  proceeds_per_share: number;
  cost_basis: number;
  gain_loss: number;
  holding_period_days: number;
  is_long_term: boolean;
  wash_sale: boolean;
  notes: string | null;
}

interface StockLot {
  lot_id: number;
  symbol: string;
  purchase_date: string;
  quantity: number;
  quantity_remaining: number;
  cost_basis: number;
  cost_per_share: number;
  account_id: string;
  source: string;
  status: string;
  lot_method: string;
  notes: string | null;
}

export default function CostBasis() {
  const navigate = useNavigate();
  const [taxYear, setTaxYear] = useState(2025);
  const [summary, setSummary] = useState<CapitalGainsSummary | null>(null);
  const [realizedGains, setRealizedGains] = useState<RealizedGain[]>([]);
  const [openLots, setOpenLots] = useState<StockLot[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'summary' | 'realized' | 'lots'>('summary');

  // Filters
  const [symbolFilter, setSymbolFilter] = useState('');
  const [termFilter, setTermFilter] = useState<'all' | 'short' | 'long'>('all');
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [taxYear]);

  const syncFromTransactions = async (clearExisting: boolean = false) => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/tax/cost-basis/sync?clear_existing=${clearExisting}`,
        { 
          method: 'POST',
          headers: getAuthHeaders() 
        }
      );
      if (response.ok) {
        const data = await response.json();
        setSyncMessage(`✓ Synced ${data.lots_created} lots and ${data.sales_created} sales`);
        // Reload data after sync
        await loadData();
      } else {
        const error = await response.json();
        setSyncMessage(`✗ Error: ${error.detail || 'Sync failed'}`);
      }
    } catch (error) {
      console.error('Failed to sync:', error);
      setSyncMessage('✗ Failed to sync from transactions');
    } finally {
      setSyncing(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      // Load summary
      const summaryResponse = await fetch(
        `http://localhost:8000/api/v1/tax/cost-basis/${taxYear}`,
        { headers: getAuthHeaders() }
      );
      if (summaryResponse.ok) {
        const summaryData = await summaryResponse.json();
        setSummary(summaryData);
      }

      // Load realized gains
      const realizedResponse = await fetch(
        `http://localhost:8000/api/v1/tax/cost-basis/${taxYear}/realized`,
        { headers: getAuthHeaders() }
      );
      if (realizedResponse.ok) {
        const realizedData = await realizedResponse.json();
        setRealizedGains(realizedData.transactions || []);
      }

      // Load open lots
      const lotsResponse = await fetch(
        `http://localhost:8000/api/v1/tax/cost-basis/lots?status=open`,
        { headers: getAuthHeaders() }
      );
      if (lotsResponse.ok) {
        const lotsData = await lotsResponse.json();
        setOpenLots(lotsData.lots || []);
      }
    } catch (error) {
      console.error('Failed to load cost basis data:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const getFilteredGains = () => {
    let filtered = realizedGains;

    if (symbolFilter) {
      filtered = filtered.filter(g => g.symbol.toLowerCase().includes(symbolFilter.toLowerCase()));
    }

    if (termFilter === 'short') {
      filtered = filtered.filter(g => !g.is_long_term);
    } else if (termFilter === 'long') {
      filtered = filtered.filter(g => g.is_long_term);
    }

    return filtered;
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>
          <div className={styles.spinner}></div>
          <p>Loading cost basis data...</p>
        </div>
      </div>
    );
  }

  const filteredGains = getFilteredGains();

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <button onClick={() => navigate('/tax')} className={styles.backButton}>
          <ArrowLeft size={20} />
          Back to Tax Center
        </button>

        <div className={styles.headerContent}>
          <div className={styles.titleSection}>
            <FileText size={32} className={styles.titleIcon} />
            <div>
              <h1 className={styles.title}>Cost Basis & Capital Gains Tracker</h1>
              <p className={styles.subtitle}>Track realized and unrealized gains for tax reporting</p>
            </div>
          </div>

          <div className={styles.yearSelector}>
            <label>Tax Year:</label>
            <select value={taxYear} onChange={(e) => setTaxYear(Number(e.target.value))}>
              <option value={2025}>2025</option>
              <option value={2024}>2024</option>
              <option value={2023}>2023</option>
            </select>
          </div>

          <button 
            className={styles.syncButton}
            onClick={() => syncFromTransactions(false)}
            disabled={syncing}
          >
            <RefreshCw size={18} className={syncing ? styles.spinning : ''} />
            {syncing ? 'Syncing...' : 'Sync from Transactions'}
          </button>
        </div>
      </div>

      {/* Sync Message */}
      {syncMessage && (
        <div className={`${styles.syncMessage} ${syncMessage.startsWith('✓') ? styles.success : styles.error}`}>
          {syncMessage}
        </div>
      )}

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'summary' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('summary')}
        >
          <DollarSign size={18} />
          Summary
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'realized' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('realized')}
        >
          <TrendingUp size={18} />
          Realized Gains ({filteredGains.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'lots' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('lots')}
        >
          <FileText size={18} />
          Open Lots ({openLots.length})
        </button>
      </div>

      {/* Summary Tab */}
      {activeTab === 'summary' && summary && (
        <div className={styles.tabContent}>
          {/* Summary Cards */}
          <div className={styles.summaryCards}>
            <div className={styles.summaryCard}>
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>Total Realized Gain</span>
                {summary.total_gain >= 0 ? (
                  <TrendingUp className={styles.iconGreen} size={24} />
                ) : (
                  <TrendingDown className={styles.iconRed} size={24} />
                )}
              </div>
              <div className={summary.total_gain >= 0 ? styles.cardValueGreen : styles.cardValueRed}>
                {formatCurrency(summary.total_gain)}
              </div>
              <div className={styles.cardFooter}>
                Short: {formatCurrency(summary.total_short_term_gain)} |
                Long: {formatCurrency(summary.total_long_term_gain)}
              </div>
            </div>

            <div className={styles.summaryCard}>
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>Total Proceeds</span>
                <DollarSign className={styles.iconBlue} size={24} />
              </div>
              <div className={styles.cardValue}>
                {formatCurrency(summary.total_proceeds)}
              </div>
              <div className={styles.cardFooter}>
                From {summary.num_transactions} transactions
              </div>
            </div>

            <div className={styles.summaryCard}>
              <div className={styles.cardHeader}>
                <span className={styles.cardLabel}>Total Cost Basis</span>
                <FileText className={styles.iconGray} size={24} />
              </div>
              <div className={styles.cardValue}>
                {formatCurrency(summary.total_cost_basis)}
              </div>
              <div className={styles.cardFooter}>
                Original investment
              </div>
            </div>
          </div>

          {/* By Symbol Breakdown */}
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Breakdown by Symbol</h2>
            <div className={styles.tableContainer}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Sales</th>
                    <th>Proceeds</th>
                    <th>Cost Basis</th>
                    <th>Short-Term Gain</th>
                    <th>Long-Term Gain</th>
                    <th>Total Gain/Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.by_symbol).map(([symbol, data]) => (
                    <tr key={symbol}>
                      <td className={styles.symbolCell}>{symbol}</td>
                      <td>{data.num_sales}</td>
                      <td>{formatCurrency(data.proceeds)}</td>
                      <td>{formatCurrency(data.cost_basis)}</td>
                      <td className={data.short_term_gain >= 0 ? styles.positive : styles.negative}>
                        {formatCurrency(data.short_term_gain)}
                      </td>
                      <td className={data.long_term_gain >= 0 ? styles.positive : styles.negative}>
                        {formatCurrency(data.long_term_gain)}
                      </td>
                      <td className={data.total_gain >= 0 ? styles.positiveGold : styles.negative}>
                        {formatCurrency(data.total_gain)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Realized Gains Tab */}
      {activeTab === 'realized' && (
        <div className={styles.tabContent}>
          {/* Filters */}
          <div className={styles.filters}>
            <div className={styles.filterGroup}>
              <Filter size={16} />
              <input
                type="text"
                placeholder="Filter by symbol..."
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value)}
                className={styles.filterInput}
              />
            </div>
            <div className={styles.filterGroup}>
              <select value={termFilter} onChange={(e) => setTermFilter(e.target.value as any)} className={styles.filterSelect}>
                <option value="all">All Terms</option>
                <option value="short">Short-Term Only</option>
                <option value="long">Long-Term Only</option>
              </select>
            </div>
            <div className={styles.filterStats}>
              Showing {filteredGains.length} of {realizedGains.length} transactions
            </div>
          </div>

          {/* Realized Gains Table */}
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Sale Date</th>
                  <th>Purchase Date</th>
                  <th>Quantity</th>
                  <th>Proceeds</th>
                  <th>Cost Basis</th>
                  <th>Gain/Loss</th>
                  <th>Days Held</th>
                  <th>Term</th>
                </tr>
              </thead>
              <tbody>
                {filteredGains.length === 0 ? (
                  <tr>
                    <td colSpan={9} className={styles.emptyState}>
                      No realized gains for {taxYear}
                    </td>
                  </tr>
                ) : (
                  filteredGains.map((gain) => (
                    <tr key={gain.sale_id}>
                      <td className={styles.symbolCell}>{gain.symbol}</td>
                      <td>{formatDate(gain.sale_date)}</td>
                      <td>{formatDate(gain.purchase_date)}</td>
                      <td>{gain.quantity_sold}</td>
                      <td>{formatCurrency(gain.proceeds)}</td>
                      <td>{formatCurrency(gain.cost_basis)}</td>
                      <td className={gain.gain_loss >= 0 ? styles.positiveGold : styles.negative}>
                        {formatCurrency(gain.gain_loss)}
                      </td>
                      <td>{gain.holding_period_days}</td>
                      <td>
                        <span className={gain.is_long_term ? styles.badgeLong : styles.badgeShort}>
                          {gain.is_long_term ? 'Long' : 'Short'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Open Lots Tab */}
      {activeTab === 'lots' && (
        <div className={styles.tabContent}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Open Positions</h2>
            <button className={styles.actionButton}>
              <Upload size={16} />
              Import Transactions
            </button>
          </div>

          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Purchase Date</th>
                  <th>Original Qty</th>
                  <th>Remaining Qty</th>
                  <th>Cost/Share</th>
                  <th>Total Cost Basis</th>
                  <th>Account</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {openLots.length === 0 ? (
                  <tr>
                    <td colSpan={8} className={styles.emptyState}>
                      No open lots found. Import your transactions to get started.
                    </td>
                  </tr>
                ) : (
                  openLots.map((lot) => (
                    <tr key={lot.lot_id}>
                      <td className={styles.symbolCell}>{lot.symbol}</td>
                      <td>{formatDate(lot.purchase_date)}</td>
                      <td>{lot.quantity}</td>
                      <td>{lot.quantity_remaining}</td>
                      <td>{formatCurrency(lot.cost_per_share)}</td>
                      <td>{formatCurrency(lot.cost_basis)}</td>
                      <td className={styles.accountCell}>{lot.account_id || lot.source}</td>
                      <td>
                        <span className={
                          lot.status === 'open' ? styles.badgeOpen :
                          lot.status === 'partial' ? styles.badgePartial :
                          styles.badgeClosed
                        }>
                          {lot.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

