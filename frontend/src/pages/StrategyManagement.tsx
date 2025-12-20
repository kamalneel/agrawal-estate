import { useState, useEffect } from 'react';
import {
  Settings,
  ToggleLeft,
  ToggleRight,
  Edit,
  Eye,
  Play,
  CheckCircle,
  XCircle,
  Info,
  Lightbulb,
  TrendingUp,
  Shield,
  RefreshCw,
  Save,
  X,
} from 'lucide-react';
import styles from './StrategyManagement.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface StrategyParameter {
  key: string;
  label: string;
  type: 'number' | 'percent' | 'text';
  default: any;
  description?: string;
}

interface Strategy {
  strategy_type: string;
  name: string;
  description: string;
  category: 'income_generation' | 'optimization' | 'risk_management';
  enabled: boolean;
  notification_enabled: boolean;
  notification_priority_threshold: 'urgent' | 'high' | 'medium' | 'low';
  parameters: Record<string, any>;
  default_parameters: Record<string, any>;
}

const categoryIcons = {
  income_generation: TrendingUp,
  optimization: Settings,
  risk_management: Shield,
};

const categoryColors = {
  income_generation: '#10B981',
  optimization: '#3B82F6',
  risk_management: '#F59E0B',
};

export default function StrategyManagement() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingStrategy, setEditingStrategy] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<Strategy>>({});
  const [testingStrategy, setTestingStrategy] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<any>(null);

  useEffect(() => {
    fetchStrategies();
  }, []);

  const fetchStrategies = async () => {
    try {
      const response = await fetch('/api/v1/strategies/strategies', {
        headers: getAuthHeaders(),
      });
      const data = await response.json();
      setStrategies(data.strategies || []);
    } catch (error) {
      console.error('Error fetching strategies:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateStrategy = async (strategyType: string, updates: Partial<Strategy>) => {
    try {
      const response = await fetch(`/api/v1/strategies/strategies/${strategyType}`, {
        method: 'PUT',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates),
      });

      if (!response.ok) {
        throw new Error('Failed to update strategy');
      }

      await fetchStrategies();
      setEditingStrategy(null);
    } catch (error) {
      console.error('Error updating strategy:', error);
      alert('Failed to update strategy');
    }
  };

  const toggleEnabled = async (strategy: Strategy) => {
    try {
      await updateStrategy(strategy.strategy_type, {
        enabled: !strategy.enabled,
      });
    } catch (error) {
      console.error('Error toggling strategy enabled state:', error);
    }
  };

  const toggleNotification = async (strategy: Strategy) => {
    try {
      await updateStrategy(strategy.strategy_type, {
        notification_enabled: !strategy.notification_enabled,
      });
    } catch (error) {
      console.error('Error toggling notification state:', error);
    }
  };

  const startEditing = (strategy: Strategy) => {
    setEditingStrategy(strategy.strategy_type);
    setEditForm({
      notification_priority_threshold: strategy.notification_priority_threshold,
      parameters: { ...strategy.parameters },
    });
  };

  const cancelEditing = () => {
    setEditingStrategy(null);
    setEditForm({});
  };

  const saveEdit = async (strategyType: string) => {
    await updateStrategy(strategyType, editForm);
  };

  const testStrategy = async (strategyType: string) => {
    setTestingStrategy(strategyType);
    try {
      const response = await fetch(`/api/v1/strategies/strategies/${strategyType}/test`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      const data = await response.json();
      setTestResults(data);
    } catch (error) {
      console.error('Error testing strategy:', error);
    } finally {
      setTestingStrategy(null);
    }
  };

  const updateParameter = (key: string, value: any) => {
    setEditForm({
      ...editForm,
      parameters: {
        ...editForm.parameters,
        [key]: value,
      },
    });
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading strategies...</div>
      </div>
    );
  }

  const enabledCount = strategies.filter(s => s.enabled).length;
  const notificationEnabledCount = strategies.filter(s => s.notification_enabled).length;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Settings size={24} />
          </div>
          <div>
            <h1 className={styles.title}>Strategy Management</h1>
            <p className={styles.subtitle}>
              Configure and manage recommendation strategies
            </p>
          </div>
        </div>
        <button onClick={fetchStrategies} className={styles.refreshButton}>
          <RefreshCw size={18} />
          Refresh
        </button>
      </div>

      <div className={styles.summary}>
        <div className={styles.summaryCard}>
          <div className={styles.summaryValue}>{strategies.length}</div>
          <div className={styles.summaryLabel}>Total Strategies</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryValue}>{enabledCount}</div>
          <div className={styles.summaryLabel}>Enabled</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryValue}>{notificationEnabledCount}</div>
          <div className={styles.summaryLabel}>Notifications On</div>
        </div>
      </div>

      <div className={styles.strategiesList}>
        {strategies.map((strategy) => {
          const CategoryIcon = categoryIcons[strategy.category];
          const isEditing = editingStrategy === strategy.strategy_type;

          return (
            <div
              key={strategy.strategy_type}
              className={`${styles.strategyCard} ${!strategy.enabled ? styles.disabled : ''}`}
            >
              <div className={styles.strategyHeader}>
                <div className={styles.strategyTitle}>
                  <div
                    className={styles.categoryBadge}
                    style={{ backgroundColor: categoryColors[strategy.category] }}
                  >
                    <CategoryIcon size={16} />
                  </div>
                  <div>
                    <h3 className={styles.strategyName}>{strategy.name}</h3>
                    <p className={styles.strategyDescription}>{strategy.description}</p>
                  </div>
                </div>
                <div className={styles.strategyActions}>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      toggleEnabled(strategy);
                    }}
                    className={styles.toggleButton}
                    title={strategy.enabled ? 'Disable' : 'Enable'}
                    type="button"
                  >
                    {strategy.enabled ? (
                      <ToggleRight size={24} color="#10B981" />
                    ) : (
                      <ToggleLeft size={24} color="#6B7280" />
                    )}
                  </button>
                </div>
              </div>

              <div className={styles.strategyStatus}>
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>Status:</span>
                  <span
                    className={`${styles.statusBadge} ${
                      strategy.enabled ? styles.enabled : styles.disabled
                    }`}
                  >
                    {strategy.enabled ? (
                      <>
                        <CheckCircle size={14} />
                        Enabled
                      </>
                    ) : (
                      <>
                        <XCircle size={14} />
                        Disabled
                      </>
                    )}
                  </span>
                </div>

                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>Notifications:</span>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      toggleNotification(strategy);
                    }}
                    className={`${styles.notificationToggle} ${
                      strategy.notification_enabled ? styles.on : styles.off
                    }`}
                    type="button"
                  >
                    {strategy.notification_enabled ? 'On' : 'Off'}
                  </button>
                </div>
              </div>

              {isEditing ? (
                <div className={styles.editForm}>
                  <div className={styles.formGroup}>
                    <label>Notification Priority Threshold</label>
                    <select
                      value={editForm.notification_priority_threshold || strategy.notification_priority_threshold}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          notification_priority_threshold: e.target.value as any,
                        })
                      }
                    >
                      <option value="urgent">Urgent</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>

                  <div className={styles.formGroup}>
                    <label>Strategy Parameters</label>
                    {Object.entries(strategy.default_parameters || {}).map(([key, defaultValue]) => (
                      <div key={key} className={styles.parameterRow}>
                        <label className={styles.parameterLabel}>
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:
                        </label>
                        <input
                          type="number"
                          step={key.includes('percent') || key.includes('threshold') ? '0.01' : '1'}
                          value={editForm.parameters?.[key] ?? strategy.parameters?.[key] ?? defaultValue}
                          onChange={(e) =>
                            updateParameter(
                              key,
                              key.includes('percent') || key.includes('threshold')
                                ? parseFloat(e.target.value)
                                : parseInt(e.target.value)
                            )
                          }
                          className={styles.parameterInput}
                        />
                      </div>
                    ))}
                  </div>

                  <div className={styles.formActions}>
                    <button
                      onClick={() => saveEdit(strategy.strategy_type)}
                      className={styles.saveButton}
                    >
                      <Save size={16} />
                      Save
                    </button>
                    <button onClick={cancelEditing} className={styles.cancelButton}>
                      <X size={16} />
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className={styles.strategyDetails}>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Notification Threshold:</span>
                    <span className={styles.detailValue}>
                      {strategy.notification_priority_threshold}
                    </span>
                  </div>

                  {Object.keys(strategy.parameters || {}).length > 0 && (
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Parameters:</span>
                      <div className={styles.parametersList}>
                        {Object.entries(strategy.parameters).map(([key, value]) => (
                          <span key={key} className={styles.parameterTag}>
                            {key.replace(/_/g, ' ')}: {value}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className={styles.strategyActions}>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        startEditing(strategy);
                      }}
                      className={styles.actionButton}
                      type="button"
                    >
                      <Edit size={16} />
                      Configure
                    </button>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        testStrategy(strategy.strategy_type);
                      }}
                      className={styles.actionButton}
                      disabled={testingStrategy === strategy.strategy_type}
                      type="button"
                    >
                      {testingStrategy === strategy.strategy_type ? (
                        <RefreshCw size={16} className={styles.spinning} />
                      ) : (
                        <Play size={16} />
                      )}
                      Test
                    </button>
                  </div>
                </div>
              )}

              {testResults && testResults.strategy_type === strategy.strategy_type && (
                <div className={styles.testResults}>
                  <h4>Test Results ({testResults.count} recommendations)</h4>
                  {testResults.recommendations.length > 0 ? (
                    <ul>
                      {testResults.recommendations.slice(0, 5).map((rec: any, idx: number) => (
                        <li key={idx}>
                          <strong>{rec.title}</strong> - {rec.priority} priority
                        </li>
                      ))}
                      {testResults.recommendations.length > 5 && (
                        <li>... and {testResults.recommendations.length - 5} more</li>
                      )}
                    </ul>
                  ) : (
                    <p>No recommendations generated with current settings.</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

