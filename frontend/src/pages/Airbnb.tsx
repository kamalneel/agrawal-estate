import { useState, useEffect, useCallback } from 'react';
import {
  Home,
  Plus,
  ArrowLeft,
  Download,
  Trash2,
  ExternalLink,
  Upload,
  Edit2,
  RefreshCw,
  FileText,
  Link2,
} from 'lucide-react';
import styles from './Airbnb.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

/* ─── types ───────────────────────────────────────────────── */

interface BlockMetrics {
  block_id: number;
  block_type: string;
  points: number;
  cost_to_acquire: number;
  annual_cost_rate_pct: number;
  housekeeping_per_week: number;
  weeks: number;
  annual_revenue: number;
  yearly_maintenance: number;
  monthly_maintenance: number;
  housekeeping_total: number;
  gross_profit: number;
  management_fee: number;
  capital_cost: number;
  annual_profit: number;
  five_year_return: number;
}

interface PropertyDoc {
  id: number;
  document_type: string;
  file_name: string;
  file_size: number;
  mime_type: string;
  notes: string | null;
  created_at: string;
}

interface PropertyLink {
  id: number;
  title: string;
  url: string;
  link_type: string;
  notes: string | null;
}

interface PropertySummary {
  id: number;
  name: string;
  property_type: string;
  status: string;
  total_annual_profit: number;
  total_five_year_return: number;
  total_initial_investment: number;
  total_annual_cash_outflow: number;
  total_points: number;
  block_count: number;
}

interface PropertyDetail {
  id: number;
  name: string;
  property_type: string;
  status: string;
  notes: string | null;
  points_per_week: number;
  income_per_week_best: number;
  income_per_week_worst: number;
  housekeeping_per_week: number;
  management_fee_pct: number;
  capital_cost_rate_pct: number;
  blocks: BlockMetrics[];
  total_points: number;
  total_initial_investment: number;
  total_weeks: number;
  total_annual_revenue: number;
  total_yearly_maintenance: number;
  total_housekeeping: number;
  total_gross_profit: number;
  total_management_fee: number;
  total_capital_cost: number;
  total_annual_profit: number;
  total_five_year_return: number;
  total_annual_cash_outflow: number;
  worst_case: {
    total_annual_profit: number;
    total_five_year_return: number;
    total_gross_profit: number;
    blocks: BlockMetrics[];
  };
  documents: PropertyDoc[];
  links: PropertyLink[];
}

/* ─── helpers ─────────────────────────────────────────────── */

const API = '/api/v1/airbnb';

const fmt = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtFull = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v);

const fmtNum = (v: number) =>
  new Intl.NumberFormat('en-US').format(v);

const fmtSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const statusClass = (s: string) => {
  switch (s) {
    case 'active': return styles.statusActive;
    case 'sold': return styles.statusSold;
    default: return styles.statusProspective;
  }
};

/* ─── component ───────────────────────────────────────────── */

export default function Airbnb() {
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PropertyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [scenario, setScenario] = useState<'best' | 'worst'>('best');

  // Modal states
  const [showPropertyModal, setShowPropertyModal] = useState(false);
  const [editingProperty, setEditingProperty] = useState<PropertyDetail | null>(null);
  const [showBlockModal, setShowBlockModal] = useState(false);
  const [showDocModal, setShowDocModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);

  /* ─── data fetching ──────────────────────────────────────── */

  const fetchProperties = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/properties`, { headers: getAuthHeaders() });
      const data = await res.json();
      setProperties(data.properties || []);
    } catch (e) {
      console.error('Failed to fetch properties', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchDetail = useCallback(async (id: number) => {
    try {
      const res = await fetch(`${API}/properties/${id}`, { headers: getAuthHeaders() });
      const data = await res.json();
      setDetail(data);
    } catch (e) {
      console.error('Failed to fetch property detail', e);
    }
  }, []);

  useEffect(() => { fetchProperties(); }, [fetchProperties]);

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
  }, [selectedId, fetchDetail]);

  /* ─── actions ────────────────────────────────────────────── */

  const handleSaveProperty = async (formData: Record<string, any>) => {
    const url = editingProperty
      ? `${API}/properties/${editingProperty.id}`
      : `${API}/properties`;
    const method = editingProperty ? 'PUT' : 'POST';

    const res = await fetch(url, {
      method,
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    if (res.ok) {
      setShowPropertyModal(false);
      setEditingProperty(null);
      fetchProperties();
      if (selectedId) fetchDetail(selectedId);
    }
  };

  const handleDeleteProperty = async (id: number) => {
    if (!confirm('Delete this property and all its data?')) return;
    const res = await fetch(`${API}/properties/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      setSelectedId(null);
      setDetail(null);
      fetchProperties();
    }
  };

  const handleSaveBlock = async (formData: Record<string, any>) => {
    if (!selectedId) return;
    const res = await fetch(`${API}/properties/${selectedId}/blocks`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    if (res.ok) {
      setShowBlockModal(false);
      fetchDetail(selectedId);
      fetchProperties();
    }
  };

  const handleDeleteBlock = async (blockId: number) => {
    if (!confirm('Delete this points block?')) return;
    const res = await fetch(`${API}/blocks/${blockId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (res.ok && selectedId) {
      fetchDetail(selectedId);
      fetchProperties();
    }
  };

  const handleUploadDoc = async (file: File, docType: string, notes: string) => {
    if (!selectedId) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('document_type', docType);
    if (notes) fd.append('notes', notes);

    const headers = getAuthHeaders();
    delete (headers as any)['Content-Type'];

    const res = await fetch(`${API}/properties/${selectedId}/documents`, {
      method: 'POST',
      headers,
      body: fd,
    });
    if (res.ok) {
      setShowDocModal(false);
      fetchDetail(selectedId);
    }
  };

  const handleDeleteDoc = async (docId: number) => {
    if (!confirm('Delete this document?')) return;
    const res = await fetch(`${API}/documents/${docId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (res.ok && selectedId) fetchDetail(selectedId);
  };

  const handleSaveLink = async (formData: Record<string, any>) => {
    if (!selectedId) return;
    const res = await fetch(`${API}/properties/${selectedId}/links`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    if (res.ok) {
      setShowLinkModal(false);
      if (selectedId) fetchDetail(selectedId);
    }
  };

  const handleDeleteLink = async (linkId: number) => {
    if (!confirm('Delete this link?')) return;
    const res = await fetch(`${API}/links/${linkId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (res.ok && selectedId) fetchDetail(selectedId);
  };

  /* ─── metrics for active scenario ───────────────────────── */

  const blocks = detail
    ? scenario === 'best' ? detail.blocks : detail.worst_case.blocks
    : [];

  const totals = detail
    ? scenario === 'best'
      ? detail
      : {
          ...detail,
          total_annual_profit: detail.worst_case.total_annual_profit,
          total_five_year_return: detail.worst_case.total_five_year_return,
          total_gross_profit: detail.worst_case.total_gross_profit,
        }
    : null;

  const incomePerWeek = detail
    ? scenario === 'best' ? detail.income_per_week_best : detail.income_per_week_worst
    : 0;

  /* ─── render: list view ─────────────────────────────────── */

  if (!selectedId) {
    const totalProfit = properties.reduce((s, p) => s + p.total_annual_profit, 0);
    const totalInvestment = properties.reduce((s, p) => s + p.total_initial_investment, 0);
    const totalReturn = properties.reduce((s, p) => s + p.total_five_year_return, 0);
    const totalCashOutflow = properties.reduce((s, p) => s + (p.total_annual_cash_outflow || 0), 0);

    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.headerContent}>
            <div className={styles.headerIcon}><Home size={28} /></div>
            <div>
              <h1 className={styles.title}>Airbnb Investments</h1>
              <p className={styles.subtitle}>
                {totalProfit > 0
                  ? `${fmt(totalProfit)} projected annual profit`
                  : 'Timeshare points-based rental business'}
              </p>
            </div>
            <div className={styles.headerActions}>
              <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={fetchProperties}>
                <RefreshCw size={16} />
              </button>
              <button
                className={`${styles.btn} ${styles.btnPrimary}`}
                onClick={() => { setEditingProperty(null); setShowPropertyModal(true); }}
              >
                <Plus size={16} /> Add Property
              </button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className={styles.loadingState}>
            <RefreshCw size={24} className={styles.spinner} />
            <span>Loading properties...</span>
          </div>
        ) : properties.length === 0 ? (
          <div className={styles.emptyState}>
            <Home size={48} />
            <h3 className={styles.emptyTitle}>No Properties Yet</h3>
            <p className={styles.emptyText}>Add your first Airbnb timeshare property to get started.</p>
            <button
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={() => { setEditingProperty(null); setShowPropertyModal(true); }}
            >
              <Plus size={16} /> Add Property
            </button>
          </div>
        ) : (
          <>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Properties</span>
                <span className={styles.summaryValue}>{properties.length}</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Annual Profit</span>
                <span className={`${styles.summaryValue} ${totalProfit >= 0 ? styles.positive : styles.negative}`}>
                  {fmt(totalProfit)}
                </span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>5-Year Return</span>
                <span className={`${styles.summaryValue} ${totalReturn >= 0 ? styles.positive : styles.negative}`}>
                  {fmt(totalReturn)}
                </span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Investment</span>
                <span className={styles.summaryValue}>{fmt(totalInvestment)}</span>
              </div>
              <div className={styles.summaryCard}>
                <span className={styles.summaryLabel}>Annual Loan Needed</span>
                <span className={styles.summaryValue}>{fmt(totalCashOutflow)}</span>
                <span className={styles.summaryNote}>Maintenance + housekeeping</span>
              </div>
            </div>

            <div className={styles.propertyGrid}>
              {properties.map(p => (
                <div key={p.id} className={styles.propertyCard} onClick={() => setSelectedId(p.id)}>
                  <div className={styles.propertyCardHeader}>
                    <h3 className={styles.propertyName}>{p.name}</h3>
                    <span className={`${styles.statusBadge} ${statusClass(p.status)}`}>
                      {p.status}
                    </span>
                  </div>
                  <div className={styles.propertyType}>{p.property_type || 'Timeshare'}</div>
                  <div className={styles.propertyMetrics}>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>Annual Profit</span>
                      <span className={`${styles.metricValue} ${p.total_annual_profit >= 0 ? styles.positive : styles.negative}`}>
                        {fmt(p.total_annual_profit)}
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>5yr Return</span>
                      <span className={`${styles.metricValue} ${p.total_five_year_return >= 0 ? styles.positive : styles.negative}`}>
                        {fmt(p.total_five_year_return)}
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>Investment</span>
                      <span className={styles.metricValue}>{fmt(p.total_initial_investment)}</span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>Loan Needed</span>
                      <span className={styles.metricValue}>{fmt(p.total_annual_cash_outflow || 0)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {showPropertyModal && (
          <PropertyModal
            property={editingProperty}
            onSave={handleSaveProperty}
            onClose={() => { setShowPropertyModal(false); setEditingProperty(null); }}
          />
        )}
      </div>
    );
  }

  /* ─── render: detail view ───────────────────────────────── */

  if (!detail) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <RefreshCw size={24} className={styles.spinner} />
          <span>Loading property...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <button className={styles.backButton} onClick={() => { setSelectedId(null); setDetail(null); }}>
        <ArrowLeft size={16} /> Back to Properties
      </button>

      <div className={styles.detailHeader}>
        <div className={styles.headerIcon}><Home size={28} /></div>
        <div className={styles.detailHeaderInfo}>
          <h1 className={styles.detailName}>
            {detail.name}
            <span className={`${styles.statusBadge} ${statusClass(detail.status)}`}>{detail.status}</span>
          </h1>
          <div className={styles.detailType}>{detail.property_type || 'Timeshare'}</div>
        </div>
        <div className={styles.headerActions}>
          <button
            className={`${styles.btn} ${styles.btnSecondary}`}
            onClick={() => { setEditingProperty(detail); setShowPropertyModal(true); }}
          >
            <Edit2 size={16} /> Edit
          </button>
          <button
            className={`${styles.btn} ${styles.btnDanger}`}
            onClick={() => handleDeleteProperty(detail.id)}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* Summary Metrics */}
      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Annual Profit</span>
          <span className={`${styles.summaryValue} ${(totals?.total_annual_profit ?? 0) >= 0 ? styles.positive : styles.negative}`}>
            {fmt(totals?.total_annual_profit ?? 0)}
          </span>
          <span className={styles.summaryNote}>{scenario === 'best' ? 'Best case' : 'Worst case'}</span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>5-Year Return</span>
          <span className={`${styles.summaryValue} ${(totals?.total_five_year_return ?? 0) >= 0 ? styles.positive : styles.negative}`}>
            {fmt(totals?.total_five_year_return ?? 0)}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Investment</span>
          <span className={styles.summaryValue}>{fmt(detail.total_initial_investment)}</span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Annual Loan Needed</span>
          <span className={styles.summaryValue}>{fmt(detail.total_annual_cash_outflow || 0)}</span>
          <span className={styles.summaryNote}>Maintenance + housekeeping</span>
        </div>
      </div>

      {/* Points Blocks Table */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Points Blocks</h2>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <div className={styles.scenarioToggle}>
              <button
                className={`${styles.scenarioBtn} ${scenario === 'best' ? styles.scenarioBtnActive : ''}`}
                onClick={() => setScenario('best')}
              >Best</button>
              <button
                className={`${styles.scenarioBtn} ${scenario === 'worst' ? styles.scenarioBtnActive : ''}`}
                onClick={() => setScenario('worst')}
              >Worst</button>
            </div>
            <button
              className={`${styles.btn} ${styles.btnPrimary} ${styles.btnSmall}`}
              onClick={() => setShowBlockModal(true)}
            >
              <Plus size={14} /> Add Block
            </button>
          </div>
        </div>
        <div className={styles.tableContainer}>
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>Type</th>
                <th>Points</th>
                <th>Cost</th>
                <th>Weeks</th>
                <th>Revenue</th>
                <th>Maint.</th>
                <th>Housekeep.</th>
                <th>Gross</th>
                <th>Mgmt Fee</th>
                <th>Cap. Cost</th>
                <th>Profit</th>
                <th>5yr Return</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {blocks.map(b => (
                <tr key={b.block_id}>
                  <td style={{ textTransform: 'capitalize', fontFamily: 'inherit' }}>{b.block_type}</td>
                  <td>{fmtNum(b.points)}</td>
                  <td>{fmt(b.cost_to_acquire)}</td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${fmtNum(b.points)} points ÷ ${fmtNum(detail.points_per_week)} points/week`}>
                      {b.weeks.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${b.weeks.toFixed(1)} weeks × ${fmtFull(incomePerWeek)}/week`}>
                      {fmtFull(b.annual_revenue)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${b.annual_cost_rate_pct}% × ${fmtNum(b.points)} points`}>
                      {fmtFull(b.yearly_maintenance)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${b.weeks.toFixed(1)} weeks × ${fmtFull(b.housekeeping_per_week)}/week`}>
                      {fmtFull(b.housekeeping_total)}
                    </span>
                  </td>
                  <td className={b.gross_profit >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip={`${fmtFull(b.annual_revenue)} revenue − ${fmtFull(b.yearly_maintenance)} maintenance − ${fmtFull(b.housekeeping_total)} housekeeping`}>
                      {fmtFull(b.gross_profit)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${detail.management_fee_pct}% × ${fmtFull(b.gross_profit)} gross profit`}>
                      {fmtFull(b.management_fee)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip={`${detail.capital_cost_rate_pct}% × (${fmtFull(b.yearly_maintenance)} maint + ${fmtFull(b.housekeeping_total)} housekeep)`}>
                      {fmtFull(b.capital_cost)}
                    </span>
                  </td>
                  <td className={b.annual_profit >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip={`${fmtFull(b.gross_profit)} gross − ${fmtFull(b.management_fee)} mgmt fee − ${fmtFull(b.capital_cost)} cap cost`}>
                      {fmtFull(b.annual_profit)}
                    </span>
                  </td>
                  <td className={b.five_year_return >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip={b.block_type === 'accumulated'
                      ? `One-time bonus: ${fmtFull(b.annual_profit)} (not recurring)`
                      : `${fmtFull(b.annual_profit)} profit × 5 years`}>
                      {fmtFull(b.five_year_return)}
                    </span>
                  </td>
                  <td>
                    <button
                      className={`${styles.btnIcon} ${styles.btnIconDanger}`}
                      onClick={() => handleDeleteBlock(b.block_id)}
                      title="Delete block"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {blocks.length > 0 && (
                <tr className={styles.totalsRow}>
                  <td style={{ fontFamily: 'inherit' }}>Total</td>
                  <td>{fmtNum(detail.total_points)}</td>
                  <td>{fmt(detail.total_initial_investment)}</td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block weeks">
                      {detail.total_weeks.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block revenues">
                      {fmtFull(detail.total_annual_revenue)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block maintenance">
                      {fmtFull(detail.total_yearly_maintenance)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block housekeeping">
                      {fmtFull(detail.total_housekeeping)}
                    </span>
                  </td>
                  <td className={(totals?.total_gross_profit ?? 0) >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip="Sum of all block gross profits">
                      {fmtFull(totals?.total_gross_profit ?? 0)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block mgmt fees">
                      {fmtFull(detail.total_management_fee)}
                    </span>
                  </td>
                  <td>
                    <span className={styles.calcTip} data-tip="Sum of all block capital costs">
                      {fmtFull(detail.total_capital_cost)}
                    </span>
                  </td>
                  <td className={(totals?.total_annual_profit ?? 0) >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip="Sum of all block profits">
                      {fmtFull(totals?.total_annual_profit ?? 0)}
                    </span>
                  </td>
                  <td className={(totals?.total_five_year_return ?? 0) >= 0 ? styles.positive : styles.negative}>
                    <span className={styles.calcTip} data-tip="Sum of all block 5yr returns">
                      {fmtFull(totals?.total_five_year_return ?? 0)}
                    </span>
                  </td>
                  <td></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {blocks.length === 0 && (
          <div className={styles.emptyState} style={{ padding: 'var(--space-8)' }}>
            <p className={styles.emptyText}>No points blocks yet. Add owned or borrowed blocks to see projections.</p>
          </div>
        )}
      </div>

      {/* Shared Settings */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle} style={{ marginBottom: 'var(--space-4)' }}>Shared Settings</h2>
        <div className={styles.settingsGrid}>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Points / Week</span>
            <span className={styles.settingValue}>{fmtNum(detail.points_per_week || 0)}</span>
          </div>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Income / Week (Best)</span>
            <span className={styles.settingValue}>{fmtFull(detail.income_per_week_best)}</span>
          </div>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Income / Week (Worst)</span>
            <span className={styles.settingValue}>{fmtFull(detail.income_per_week_worst)}</span>
          </div>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Housekeeping / Week</span>
            <span className={styles.settingValue}>{fmtFull(detail.housekeeping_per_week)}</span>
          </div>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Mgmt Fee %</span>
            <span className={styles.settingValue}>{detail.management_fee_pct}%</span>
          </div>
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>Capital Cost Rate %</span>
            <span className={styles.settingValue}>{detail.capital_cost_rate_pct}%</span>
          </div>
        </div>
      </div>

      {/* Business Plan */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle} style={{ marginBottom: 'var(--space-4)' }}>Business Plan</h2>
        <div className={styles.businessPlan}>
          <h4>How {detail.property_type || 'Timeshare'} Works</h4>
          <p>
            Buy {detail.property_type || 'timeshare'} points on the resale market at a fraction of retail price.
            Points convert to rental weeks at resort properties ({fmtNum(detail.points_per_week || 0)} points = 1 week).
            List weeks on Airbnb, managed by CasaMgmt ({detail.management_fee_pct}% of gross profit).
          </p>
          <ul>
            <li><strong>Owned points:</strong> Purchased upfront with annual maintenance (~10% of points value)</li>
            <li><strong>Accumulated points:</strong> Unused credits carried over from previous owner — no ongoing cost, one-time bonus</li>
            <li><strong>Borrowed points:</strong> Borrow up to 2x owned from next year's allocation at ~6% annual cost</li>
          </ul>
          <p>
            Revenue: {fmtFull(detail.income_per_week_best)}/week (best) to {fmtFull(detail.income_per_week_worst)}/week (worst).
            Costs per week: {fmtFull(detail.housekeeping_per_week)} housekeeping + maintenance + {detail.management_fee_pct}% management + {detail.capital_cost_rate_pct}% capital cost on expenses.
          </p>

          <h4>This Offer: {detail.name}</h4>
          {(() => {
            const accBlock = blocks.find(b => b.block_type === 'accumulated');
            const ownBlock = blocks.find(b => b.block_type === 'owned');
            const borBlock = blocks.find(b => b.block_type === 'borrowed');
            return (
              <>
                <p>
                  Purchase price: {fmt(detail.total_initial_investment)}.
                  {' '}Total {fmtNum(detail.total_points)} points yielding {detail.total_weeks.toFixed(1)} rental weeks.
                </p>
                <table className={styles.dataTable} style={{ marginBottom: 'var(--space-4)' }}>
                  <thead>
                    <tr>
                      <th>Tranche</th>
                      <th>Points</th>
                      <th>Weeks</th>
                      <th>Annual Profit</th>
                      <th>5yr Return</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accBlock && (
                      <tr>
                        <td style={{ fontFamily: 'inherit' }}>Accumulated credits</td>
                        <td>{fmtNum(accBlock.points)}</td>
                        <td>{accBlock.weeks.toFixed(1)}</td>
                        <td className={styles.positive}>{fmtFull(accBlock.annual_profit)}</td>
                        <td className={styles.positive}>{fmtFull(accBlock.five_year_return)}</td>
                        <td style={{ fontFamily: 'inherit', color: 'var(--color-text-tertiary)' }}>One-time bonus, no maintenance</td>
                      </tr>
                    )}
                    {ownBlock && (
                      <tr>
                        <td style={{ fontFamily: 'inherit' }}>Owned (annual)</td>
                        <td>{fmtNum(ownBlock.points)}</td>
                        <td>{ownBlock.weeks.toFixed(1)}</td>
                        <td className={ownBlock.annual_profit >= 0 ? styles.positive : styles.negative}>{fmtFull(ownBlock.annual_profit)}</td>
                        <td className={ownBlock.five_year_return >= 0 ? styles.positive : styles.negative}>{fmtFull(ownBlock.five_year_return)}</td>
                        <td style={{ fontFamily: 'inherit', color: 'var(--color-text-tertiary)' }}>{ownBlock.annual_cost_rate_pct}% annual maintenance</td>
                      </tr>
                    )}
                    {borBlock && (
                      <tr>
                        <td style={{ fontFamily: 'inherit' }}>Borrowed</td>
                        <td>{fmtNum(borBlock.points)}</td>
                        <td>{borBlock.weeks.toFixed(1)}</td>
                        <td className={borBlock.annual_profit >= 0 ? styles.positive : styles.negative}>{fmtFull(borBlock.annual_profit)}</td>
                        <td className={borBlock.five_year_return >= 0 ? styles.positive : styles.negative}>{fmtFull(borBlock.five_year_return)}</td>
                        <td style={{ fontFamily: 'inherit', color: 'var(--color-text-tertiary)' }}>{borBlock.annual_cost_rate_pct}% annual cost</td>
                      </tr>
                    )}
                    {blocks.length > 0 && (
                      <tr className={styles.totalsRow}>
                        <td style={{ fontFamily: 'inherit' }}>Total</td>
                        <td>{fmtNum(detail.total_points)}</td>
                        <td>{detail.total_weeks.toFixed(1)}</td>
                        <td className={(totals?.total_annual_profit ?? 0) >= 0 ? styles.positive : styles.negative}>
                          {fmtFull(totals?.total_annual_profit ?? 0)}
                        </td>
                        <td className={(totals?.total_five_year_return ?? 0) >= 0 ? styles.positive : styles.negative}>
                          {fmtFull(totals?.total_five_year_return ?? 0)}
                        </td>
                        <td></td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </>
            );
          })()}

          <h4>ROI Summary</h4>
          <p>
            Total investment: {fmt(detail.total_initial_investment)}.
            {detail.total_initial_investment > 0 && (
              <> 5-year ROI: {((detail.total_five_year_return / detail.total_initial_investment) * 100).toFixed(0)}% (best case).
              {' '}Payback period: {detail.total_annual_profit > 0
                ? `${(detail.total_initial_investment / detail.total_annual_profit).toFixed(1)} years`
                : 'N/A'}.
              </>
            )}
          </p>
        </div>
      </div>

      {/* Risk Analysis */}
      {detail.notes && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle} style={{ marginBottom: 'var(--space-4)' }}>
            Risk Analysis
          </h2>
          <div className={styles.riskAnalysis}>
            {detail.notes.split('\n').map((line, i) => {
              const trimmed = line.trim();
              if (!trimmed) return <div key={i} style={{ height: '8px' }} />;
              if (trimmed.startsWith('## '))
                return <h3 key={i} className={styles.riskHeading}>{trimmed.replace('## ', '')}</h3>;
              if (trimmed.startsWith('### ')) {
                const text = trimmed.replace('### ', '');
                const level = text.includes('HIGH') ? 'high' : text.includes('MODERATE') ? 'moderate' : text.includes('LOW') ? 'low' : '';
                return <h4 key={i} className={styles.riskSubheading} data-level={level}>{text}</h4>;
              }
              if (trimmed.startsWith('- '))
                return <div key={i} className={styles.riskItem}><span className={styles.riskBullet} /><span>{trimmed.replace('- ', '')}</span></div>;
              return <p key={i} className={styles.riskText}>{trimmed}</p>;
            })}
          </div>
        </div>
      )}

      {/* Documents */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>
            <FileText size={18} style={{ verticalAlign: 'text-bottom', marginRight: '8px' }} />
            Documents ({detail.documents.length})
          </h2>
          <button
            className={`${styles.btn} ${styles.btnSecondary} ${styles.btnSmall}`}
            onClick={() => setShowDocModal(true)}
          >
            <Upload size={14} /> Upload
          </button>
        </div>
        {detail.documents.length > 0 ? (
          <div className={styles.docList}>
            {detail.documents.map(doc => (
              <div key={doc.id} className={styles.docItem}>
                <FileText size={20} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
                <div className={styles.docInfo}>
                  <div className={styles.docName}>{doc.file_name}</div>
                  <div className={styles.docMeta}>
                    {doc.document_type} &middot; {fmtSize(doc.file_size || 0)}
                    {doc.notes && ` &middot; ${doc.notes}`}
                  </div>
                </div>
                <div className={styles.docActions}>
                  <a
                    href={`${API}/documents/${doc.id}/download`}
                    className={styles.btnIcon}
                    title="Download"
                  >
                    <Download size={16} />
                  </a>
                  <button
                    className={`${styles.btnIcon} ${styles.btnIconDanger}`}
                    onClick={() => handleDeleteDoc(doc.id)}
                    title="Delete"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.emptyText} style={{ textAlign: 'center', padding: 'var(--space-4)' }}>
            No documents uploaded yet.
          </p>
        )}
      </div>

      {/* Links */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>
            <Link2 size={18} style={{ verticalAlign: 'text-bottom', marginRight: '8px' }} />
            Links ({detail.links.length})
          </h2>
          <button
            className={`${styles.btn} ${styles.btnSecondary} ${styles.btnSmall}`}
            onClick={() => setShowLinkModal(true)}
          >
            <Plus size={14} /> Add Link
          </button>
        </div>
        {detail.links.length > 0 ? (
          <div className={styles.docList}>
            {detail.links.map(link => (
              <div key={link.id} className={styles.linkItem}>
                <ExternalLink size={18} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
                <div className={styles.linkInfo}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.linkTitle}
                  >
                    {link.title}
                  </a>
                  <div className={styles.linkType}>
                    {link.link_type}{link.notes ? ` — ${link.notes}` : ''}
                  </div>
                </div>
                <button
                  className={`${styles.btnIcon} ${styles.btnIconDanger}`}
                  onClick={() => handleDeleteLink(link.id)}
                  title="Delete"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.emptyText} style={{ textAlign: 'center', padding: 'var(--space-4)' }}>
            No links added yet.
          </p>
        )}
      </div>

      {/* Modals */}
      {showPropertyModal && (
        <PropertyModal
          property={editingProperty}
          onSave={handleSaveProperty}
          onClose={() => { setShowPropertyModal(false); setEditingProperty(null); }}
        />
      )}
      {showBlockModal && (
        <BlockModal
          onSave={handleSaveBlock}
          onClose={() => setShowBlockModal(false)}
        />
      )}
      {showDocModal && (
        <DocModal
          onSave={handleUploadDoc}
          onClose={() => setShowDocModal(false)}
        />
      )}
      {showLinkModal && (
        <LinkModal
          onSave={handleSaveLink}
          onClose={() => setShowLinkModal(false)}
        />
      )}
    </div>
  );
}

/* ─── Modals ──────────────────────────────────────────────── */

function PropertyModal({
  property,
  onSave,
  onClose,
}: {
  property: PropertyDetail | null;
  onSave: (data: Record<string, any>) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(property?.name || '');
  const [propertyType, setPropertyType] = useState(property?.property_type || 'WorldMark');
  const [status, setStatus] = useState(property?.status || 'prospective');
  const [pointsPerWeek, setPointsPerWeek] = useState(property?.points_per_week?.toString() || '');
  const [incomeBest, setIncomeBest] = useState(property?.income_per_week_best?.toString() || '');
  const [incomeWorst, setIncomeWorst] = useState(property?.income_per_week_worst?.toString() || '');
  const [housekeeping, setHousekeeping] = useState(property?.housekeeping_per_week?.toString() || '');
  const [mgmtFee, setMgmtFee] = useState(property?.management_fee_pct?.toString() || '20');
  const [capCost, setCapCost] = useState(property?.capital_cost_rate_pct?.toString() || '8');
  const [notes, setNotes] = useState(property?.notes || '');

  const handleSubmit = () => {
    onSave({
      name,
      property_type: propertyType,
      status,
      points_per_week: pointsPerWeek ? parseInt(pointsPerWeek) : null,
      income_per_week_best: incomeBest ? parseFloat(incomeBest) : null,
      income_per_week_worst: incomeWorst ? parseFloat(incomeWorst) : null,
      housekeeping_per_week: housekeeping ? parseFloat(housekeeping) : null,
      management_fee_pct: mgmtFee ? parseFloat(mgmtFee) : null,
      capital_cost_rate_pct: capCost ? parseFloat(capCost) : null,
      notes: notes || null,
    });
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h3 className={styles.modalTitle}>{property ? 'Edit Property' : 'Add Property'}</h3>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Name *</label>
          <input className={styles.formInput} value={name} onChange={e => setName(e.target.value)} placeholder="e.g., YellowStone" />
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Type</label>
            <input className={styles.formInput} value={propertyType} onChange={e => setPropertyType(e.target.value)} />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Status</label>
            <select className={styles.formSelect} value={status} onChange={e => setStatus(e.target.value)}>
              <option value="prospective">Prospective</option>
              <option value="active">Active</option>
              <option value="sold">Sold</option>
            </select>
          </div>
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Points per Week</label>
            <input className={styles.formInput} type="number" value={pointsPerWeek} onChange={e => setPointsPerWeek(e.target.value)} placeholder="13000" />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Housekeeping / Week ($)</label>
            <input className={styles.formInput} type="number" step="0.01" value={housekeeping} onChange={e => setHousekeeping(e.target.value)} placeholder="300" />
          </div>
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Income / Week Best ($)</label>
            <input className={styles.formInput} type="number" step="0.01" value={incomeBest} onChange={e => setIncomeBest(e.target.value)} placeholder="2000" />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Income / Week Worst ($)</label>
            <input className={styles.formInput} type="number" step="0.01" value={incomeWorst} onChange={e => setIncomeWorst(e.target.value)} placeholder="1500" />
          </div>
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Mgmt Fee %</label>
            <input className={styles.formInput} type="number" step="0.01" value={mgmtFee} onChange={e => setMgmtFee(e.target.value)} />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Capital Cost Rate %</label>
            <input className={styles.formInput} type="number" step="0.01" value={capCost} onChange={e => setCapCost(e.target.value)} />
          </div>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Notes</label>
          <textarea className={styles.formTextarea} value={notes} onChange={e => setNotes(e.target.value)} />
        </div>

        <div className={styles.modalActions}>
          <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={onClose}>Cancel</button>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSubmit} disabled={!name.trim()}>
            {property ? 'Save Changes' : 'Create Property'}
          </button>
        </div>
      </div>
    </div>
  );
}

function BlockModal({
  onSave,
  onClose,
}: {
  onSave: (data: Record<string, any>) => void;
  onClose: () => void;
}) {
  const [blockType, setBlockType] = useState('owned');
  const [points, setPoints] = useState('');
  const [cost, setCost] = useState('');
  const [rate, setRate] = useState('10');
  const [housekeeping, setHousekeeping] = useState('300');

  useEffect(() => {
    if (blockType === 'owned') {
      setRate('10');
      setHousekeeping('300');
    } else if (blockType === 'borrowed') {
      setRate('6');
      setCost('0');
      setHousekeeping('100');
    } else {
      // accumulated
      setRate('0');
      setCost('0');
      setHousekeeping('300');
    }
  }, [blockType]);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h3 className={styles.modalTitle}>Add Points Block</h3>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Type</label>
          <select className={styles.formSelect} value={blockType} onChange={e => setBlockType(e.target.value)}>
            <option value="owned">Owned</option>
            <option value="borrowed">Borrowed</option>
            <option value="accumulated">Accumulated</option>
          </select>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Points</label>
          <input className={styles.formInput} type="number" value={points} onChange={e => setPoints(e.target.value)} placeholder="80000" />
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Cost to Acquire ($)</label>
            <input className={styles.formInput} type="number" step="0.01" value={cost} onChange={e => setCost(e.target.value)} placeholder="1000" />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Annual Cost Rate %</label>
            <input className={styles.formInput} type="number" step="0.01" value={rate} onChange={e => setRate(e.target.value)} />
          </div>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Housekeeping / Week ($)</label>
          <input className={styles.formInput} type="number" step="0.01" value={housekeeping} onChange={e => setHousekeeping(e.target.value)} placeholder="300" />
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)', marginTop: '4px' }}>
            Borrowed blocks get tokens (~$100/wk). Owned/accumulated: ~$300/wk.
          </span>
        </div>

        <div className={styles.modalActions}>
          <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={onClose}>Cancel</button>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => onSave({
              block_type: blockType,
              points: parseInt(points),
              cost_to_acquire: parseFloat(cost || '0'),
              annual_cost_rate_pct: parseFloat(rate),
              housekeeping_per_week: housekeeping ? parseFloat(housekeeping) : null,
            })}
            disabled={!points}
          >
            Add Block
          </button>
        </div>
      </div>
    </div>
  );
}

function DocModal({
  onSave,
  onClose,
}: {
  onSave: (file: File, docType: string, notes: string) => void;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState('contract');
  const [notes, setNotes] = useState('');

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h3 className={styles.modalTitle}>Upload Document</h3>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>File</label>
          <input
            type="file"
            className={styles.formInput}
            onChange={e => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Document Type</label>
          <select className={styles.formSelect} value={docType} onChange={e => setDocType(e.target.value)}>
            <option value="contract">Contract</option>
            <option value="legal">Legal</option>
            <option value="insurance">Insurance</option>
            <option value="tax">Tax</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Notes</label>
          <textarea className={styles.formTextarea} value={notes} onChange={e => setNotes(e.target.value)} />
        </div>

        <div className={styles.modalActions}>
          <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={onClose}>Cancel</button>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => file && onSave(file, docType, notes)}
            disabled={!file}
          >
            Upload
          </button>
        </div>
      </div>
    </div>
  );
}

function LinkModal({
  onSave,
  onClose,
}: {
  onSave: (data: Record<string, any>) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [linkType, setLinkType] = useState('reference');
  const [notes, setNotes] = useState('');

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h3 className={styles.modalTitle}>Add Link</h3>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Title *</label>
          <input className={styles.formInput} value={title} onChange={e => setTitle(e.target.value)} placeholder="Link title" />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>URL *</label>
          <input className={styles.formInput} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Type</label>
          <select className={styles.formSelect} value={linkType} onChange={e => setLinkType(e.target.value)}>
            <option value="listing">Listing</option>
            <option value="legal">Legal</option>
            <option value="reference">Reference</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Notes</label>
          <textarea className={styles.formTextarea} value={notes} onChange={e => setNotes(e.target.value)} />
        </div>

        <div className={styles.modalActions}>
          <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={onClose}>Cancel</button>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => onSave({ title, url, link_type: linkType, notes: notes || null })}
            disabled={!title.trim() || !url.trim()}
          >
            Add Link
          </button>
        </div>
      </div>
    </div>
  );
}
