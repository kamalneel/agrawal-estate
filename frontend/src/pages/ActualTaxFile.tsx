import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  RefreshCw,
  FileText,
  Plus,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  FileCheck,
  FolderOpen,
  X
} from 'lucide-react';
import styles from './ActualTaxFile.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface ActualTaxSource {
  id: number;
  amount: number;
  document_id: number | null;
  is_manual: boolean;
  notes: string | null;
}

interface ActualTaxLineItem {
  description: string;
  amount: number;
  sources: ActualTaxSource[];
  is_manual: boolean;
}

interface ActualTaxData {
  tax_year: number;
  items: { [line: string]: ActualTaxLineItem };
  total_items: number;
}

interface ComparisonItem {
  description: string;
  actual: number;
  forecast: number;
  difference: number;
  difference_pct: number;
  has_actual: boolean;
  has_forecast: boolean;
}

interface ComparisonData {
  tax_year: number;
  comparison: { [line: string]: ComparisonItem };
  summary: {
    lines_with_actual: number;
    lines_with_forecast: number;
    lines_with_both: number;
    total_actual_difference: number;
  };
}

interface CompletenessItem {
  description: string;
  expected: number;
  received: number;
  complete: boolean;
}

interface CompletenessData {
  tax_year: number;
  completeness: { [type: string]: CompletenessItem };
  missing_required: string[];
  received: string[];
  total_documents: number;
  overall_pct: number;
}

// Form 1040 line descriptions
const FORM_LINES: { [key: string]: string } = {
  '1040:1': 'Wages, salaries, tips',
  '1040:2a': 'Tax-exempt interest',
  '1040:2b': 'Taxable interest',
  '1040:3a': 'Qualified dividends',
  '1040:3b': 'Ordinary dividends',
  '1040:4a': 'IRA distributions',
  '1040:4b': 'Taxable IRA distributions',
  '1040:5a': 'Pensions and annuities',
  '1040:5b': 'Taxable pensions',
  '1040:7': 'Capital gain or loss',
  '1040:8': 'Other income (Schedule 1)',
  '1040:9': 'Total income',
  '1040:11': 'Adjusted Gross Income',
  '1040:12': 'Deductions',
  '1040:14': 'Taxable income',
  '1040:22': 'Total tax',
  '1040:25': 'Federal income tax withheld',
  '1040:33': 'Total payments',
};

export default function ActualTaxFile() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const year = parseInt(searchParams.get('year') || '2025', 10);

  const [activeTab, setActiveTab] = useState<'actual' | 'comparison' | 'completeness'>('actual');
  const [actualData, setActualData] = useState<ActualTaxData | null>(null);
  const [comparisonData, setComparisonData] = useState<ComparisonData | null>(null);
  const [completenessData, setCompletenessData] = useState<CompletenessData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Manual entry modal
  const [showAddItem, setShowAddItem] = useState(false);
  const [newFormLine, setNewFormLine] = useState('1040:1');
  const [newAmount, setNewAmount] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [addingItem, setAddingItem] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [actualRes, comparisonRes, completenessRes] = await Promise.all([
        fetch(`/api/v1/tax/actual/${year}`, { headers: getAuthHeaders() }),
        fetch(`/api/v1/tax/actual/${year}/comparison`, { headers: getAuthHeaders() }),
        fetch(`/api/v1/tax/actual/${year}/completeness`, { headers: getAuthHeaders() }),
      ]);

      if (!actualRes.ok || !comparisonRes.ok || !completenessRes.ok) {
        throw new Error('Failed to fetch tax data');
      }

      const [actual, comparison, completeness] = await Promise.all([
        actualRes.json(),
        comparisonRes.json(),
        completenessRes.json(),
      ]);

      setActualData(actual);
      setComparisonData(comparison);
      setCompletenessData(completeness);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddItem = async () => {
    if (!newAmount) return;

    setAddingItem(true);
    setAddError(null);

    try {
      const response = await fetch(`/api/v1/tax/actual/${year}/items`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          form_line: newFormLine,
          amount: parseFloat(newAmount),
          description: newDescription || undefined,
          notes: newNotes || undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add item');
      }

      // Reset form and refresh
      setShowAddItem(false);
      setNewFormLine('1040:1');
      setNewAmount('');
      setNewDescription('');
      setNewNotes('');
      fetchData();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add item');
    } finally {
      setAddingItem(false);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={40} className={styles.spinner} />
          <p>Loading tax file...</p>
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
          <button className={styles.refreshButton} onClick={fetchData}>
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <button className={styles.backButton} onClick={() => navigate(`/tax`)}>
        <ArrowLeft size={18} />
        Back to Tax Center
      </button>

      <div className={styles.header}>
        <div className={styles.headerContent}>
          <h1>{year} Actual Tax File</h1>
          <p>Tax data extracted from uploaded documents</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.refreshBtn} onClick={fetchData}>
            <RefreshCw size={18} />
          </button>
          <button
            className={styles.documentsBtn}
            onClick={() => navigate(`/tax/documents?year=${year}`)}
          >
            <FileText size={18} />
            View Documents
          </button>
          <button className={styles.addItemBtn} onClick={() => setShowAddItem(true)}>
            <Plus size={18} />
            Add Manual Entry
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}>
          <div className={styles.summaryIcon}>
            <FileCheck size={24} />
          </div>
          <div className={styles.summaryContent}>
            <span className={styles.summaryValue}>{actualData?.total_items || 0}</span>
            <span className={styles.summaryLabel}>Line Items</span>
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryIcon}>
            <FolderOpen size={24} />
          </div>
          <div className={styles.summaryContent}>
            <span className={styles.summaryValue}>{completenessData?.total_documents || 0}</span>
            <span className={styles.summaryLabel}>Documents</span>
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={`${styles.summaryIcon} ${styles.success}`}>
            <CheckCircle2 size={24} />
          </div>
          <div className={styles.summaryContent}>
            <span className={`${styles.summaryValue} ${styles.success}`}>
              {completenessData?.overall_pct || 0}%
            </span>
            <span className={styles.summaryLabel}>Complete</span>
          </div>
        </div>
        {comparisonData && (
          <div className={styles.summaryCard}>
            <div className={`${styles.summaryIcon} ${comparisonData.summary.total_actual_difference >= 0 ? styles.warning : styles.success}`}>
              {comparisonData.summary.total_actual_difference >= 0 ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
            </div>
            <div className={styles.summaryContent}>
              <span className={`${styles.summaryValue} ${comparisonData.summary.total_actual_difference >= 0 ? styles.warning : styles.success}`}>
                {formatCurrency(Math.abs(comparisonData.summary.total_actual_difference))}
              </span>
              <span className={styles.summaryLabel}>
                {comparisonData.summary.total_actual_difference >= 0 ? 'Above' : 'Below'} Forecast
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'actual' ? styles.active : ''}`}
          onClick={() => setActiveTab('actual')}
        >
          Actual Values
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'comparison' ? styles.active : ''}`}
          onClick={() => setActiveTab('comparison')}
        >
          vs Forecast
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'completeness' ? styles.active : ''}`}
          onClick={() => setActiveTab('completeness')}
        >
          Completeness
        </button>
      </div>

      {/* Tab Content */}
      <div className={styles.tabContent}>
        {activeTab === 'actual' && actualData && (
          <div className={styles.actualTab}>
            {Object.keys(actualData.items).length === 0 ? (
              <div className={styles.emptyState}>
                <FileText size={48} />
                <h3>No Tax Items Yet</h3>
                <p>Upload documents or add manual entries to build your actual tax file.</p>
                <button
                  className={styles.addItemBtnLarge}
                  onClick={() => setShowAddItem(true)}
                >
                  <Plus size={18} />
                  Add First Entry
                </button>
              </div>
            ) : (
              <div className={styles.itemsTable}>
                <div className={styles.tableHeader}>
                  <span className={styles.colLine}>Line</span>
                  <span className={styles.colDesc}>Description</span>
                  <span className={styles.colAmount}>Amount</span>
                  <span className={styles.colSource}>Source</span>
                </div>
                {Object.entries(actualData.items)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([line, item]) => (
                    <div key={line} className={styles.tableRow}>
                      <span className={styles.colLine}>{line}</span>
                      <span className={styles.colDesc}>
                        {item.description || FORM_LINES[line] || line}
                      </span>
                      <span className={styles.colAmount}>{formatCurrency(item.amount)}</span>
                      <span className={styles.colSource}>
                        {item.is_manual ? (
                          <span className={styles.manualBadge}>Manual</span>
                        ) : (
                          <span className={styles.documentBadge}>Document</span>
                        )}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'comparison' && comparisonData && (
          <div className={styles.comparisonTab}>
            <div className={styles.itemsTable}>
              <div className={styles.tableHeader}>
                <span className={styles.colLine}>Line</span>
                <span className={styles.colDesc}>Description</span>
                <span className={styles.colAmount}>Actual</span>
                <span className={styles.colAmount}>Forecast</span>
                <span className={styles.colDiff}>Difference</span>
              </div>
              {Object.entries(comparisonData.comparison)
                .filter(([_, item]) => item.has_actual || item.has_forecast)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([line, item]) => (
                  <div
                    key={line}
                    className={`${styles.tableRow} ${!item.has_actual ? styles.missingActual : ''}`}
                  >
                    <span className={styles.colLine}>{line}</span>
                    <span className={styles.colDesc}>
                      {item.description || FORM_LINES[line] || line}
                    </span>
                    <span className={styles.colAmount}>
                      {item.has_actual ? formatCurrency(item.actual) : '-'}
                    </span>
                    <span className={`${styles.colAmount} ${styles.forecast}`}>
                      {item.has_forecast ? formatCurrency(item.forecast) : '-'}
                    </span>
                    <span className={`${styles.colDiff} ${item.difference >= 0 ? styles.positive : styles.negative}`}>
                      {item.has_actual && item.has_forecast ? (
                        <>
                          {formatCurrency(item.difference)}
                          <span className={styles.diffPct}>({formatPercent(item.difference_pct)})</span>
                        </>
                      ) : (
                        '-'
                      )}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}

        {activeTab === 'completeness' && completenessData && (
          <div className={styles.completenessTab}>
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill}
                style={{ width: `${completenessData.overall_pct}%` }}
              />
            </div>
            <p className={styles.progressLabel}>
              {completenessData.overall_pct}% of required documents received
            </p>

            {completenessData.missing_required.length > 0 && (
              <div className={styles.missingSection}>
                <h3>
                  <AlertCircle size={18} />
                  Missing Required Documents
                </h3>
                <div className={styles.missingList}>
                  {completenessData.missing_required.map(type => (
                    <div key={type} className={styles.missingItem}>
                      <span>{type}</span>
                      <span className={styles.missingDesc}>
                        {completenessData.completeness[type]?.description}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className={styles.documentsGrid}>
              {Object.entries(completenessData.completeness).map(([type, item]) => (
                <div
                  key={type}
                  className={`${styles.documentCard} ${item.complete ? styles.complete : styles.incomplete}`}
                >
                  <div className={styles.documentCardHeader}>
                    {item.complete ? (
                      <CheckCircle2 size={18} className={styles.checkIcon} />
                    ) : (
                      <AlertCircle size={18} className={styles.alertIcon} />
                    )}
                    <span className={styles.documentType}>{type}</span>
                  </div>
                  <span className={styles.documentDesc}>{item.description}</span>
                  <div className={styles.documentCount}>
                    <span className={styles.received}>{item.received}</span>
                    <span className={styles.expected}>/ {item.expected === 0 ? 'optional' : item.expected}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Add Item Modal */}
      {showAddItem && (
        <div className={styles.modalOverlay} onClick={() => setShowAddItem(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>Add Manual Entry</h3>
              <button className={styles.modalClose} onClick={() => setShowAddItem(false)}>
                <X size={20} />
              </button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.formGroup}>
                <label>Form Line *</label>
                <select value={newFormLine} onChange={e => setNewFormLine(e.target.value)}>
                  {Object.entries(FORM_LINES).map(([line, desc]) => (
                    <option key={line} value={line}>
                      {line} - {desc}
                    </option>
                  ))}
                  <option value="OTHER">Other</option>
                </select>
              </div>

              <div className={styles.formGroup}>
                <label>Amount *</label>
                <input
                  type="number"
                  value={newAmount}
                  onChange={e => setNewAmount(e.target.value)}
                  placeholder="0.00"
                  step="0.01"
                />
              </div>

              <div className={styles.formGroup}>
                <label>Description</label>
                <input
                  type="text"
                  value={newDescription}
                  onChange={e => setNewDescription(e.target.value)}
                  placeholder="Optional description"
                />
              </div>

              <div className={styles.formGroup}>
                <label>Notes</label>
                <textarea
                  value={newNotes}
                  onChange={e => setNewNotes(e.target.value)}
                  placeholder="Optional notes"
                  rows={3}
                />
              </div>

              {addError && (
                <div className={styles.errorMsg}>
                  <AlertCircle size={16} />
                  {addError}
                </div>
              )}
            </div>

            <div className={styles.modalFooter}>
              <button
                className={styles.cancelButton}
                onClick={() => setShowAddItem(false)}
                disabled={addingItem}
              >
                Cancel
              </button>
              <button
                className={styles.submitButton}
                onClick={handleAddItem}
                disabled={addingItem || !newAmount}
              >
                {addingItem ? (
                  <>
                    <RefreshCw size={16} className={styles.spinner} />
                    Adding...
                  </>
                ) : (
                  <>
                    <Plus size={16} />
                    Add Entry
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
