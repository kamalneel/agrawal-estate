import { useState, useEffect, useCallback } from 'react';
import { usePlaidLink } from 'react-plaid-link';
import {
  Link2,
  Building2,
  RefreshCw,
  Trash2,
  ChevronRight,
  CheckCircle,
  AlertCircle,
  Clock,
  DollarSign,
  TrendingUp,
  Wallet,
  Plus,
  Loader2,
  ExternalLink,
} from 'lucide-react';
import styles from './PlaidIntegration.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface PlaidItem {
  id: number;
  item_id: string;
  institution_name: string | null;
  is_active: boolean;
  accounts_count: number;
  last_synced_at: string | null;
  created_at: string;
}

interface PlaidAccount {
  id: number;
  account_id: string;
  name: string;
  official_name: string | null;
  type: string;
  subtype: string | null;
  mask: string | null;
  current_balance: string | null;
  is_active: boolean;
}

interface Transaction {
  id: number;
  date: string;
  ticker: string | null;
  name: string;
  type: string;
  quantity: string | null;
  price: string | null;
  amount: string | null;
  option_type: string | null;
  strike_price: string | null;
  expiration_date: string | null;
}

export default function PlaidIntegration() {
  const [items, setItems] = useState<PlaidItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<PlaidItem | null>(null);
  const [accounts, setAccounts] = useState<PlaidAccount[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch linked items
  const fetchItems = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/plaid/items', {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setItems(data);
      }
    } catch (err) {
      console.error('Failed to fetch items:', err);
    }
  }, []);

  // Fetch link token for Plaid Link
  const fetchLinkToken = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/plaid/link-token', {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setLinkToken(data.link_token);
      } else if (response.status === 503) {
        setError('Plaid is not configured. Please add PLAID_CLIENT_ID and PLAID_SECRET to your .env file.');
      }
    } catch (err) {
      console.error('Failed to fetch link token:', err);
    }
  }, []);

  // Fetch accounts for a specific item
  const fetchAccounts = useCallback(async (itemId: number) => {
    try {
      const response = await fetch(`/api/v1/plaid/items/${itemId}/accounts`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setAccounts(data);
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err);
    }
  }, []);

  // Fetch recent transactions
  const fetchTransactions = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/plaid/transactions?limit=20', {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setTransactions(data.transactions);
      }
    } catch (err) {
      console.error('Failed to fetch transactions:', err);
    }
  }, []);

  // Handle successful Plaid Link connection
  const onSuccess = useCallback(async (publicToken: string) => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/plaid/exchange-token', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ public_token: publicToken }),
      });

      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(`Successfully linked ${data.institution_name || 'account'} with ${data.accounts_count} accounts!`);
        await fetchItems();
        await fetchLinkToken(); // Get new token for next connection
      } else {
        setError('Failed to link account. Please try again.');
      }
    } catch (err) {
      setError('Failed to link account. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [fetchItems, fetchLinkToken]);

  // Plaid Link configuration
  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    onExit: (err) => {
      if (err) {
        console.error('Plaid Link exit error:', err);
      }
    },
  });

  // Sync transactions for an item
  const syncItem = async (itemId: number) => {
    setSyncing(true);
    try {
      const response = await fetch(`/api/v1/plaid/items/${itemId}/sync?days=30`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(`Synced ${data.new_transactions} new transactions`);
        await fetchTransactions();
        await fetchItems();
      }
    } catch (err) {
      setError('Failed to sync transactions');
    } finally {
      setSyncing(false);
    }
  };

  // Sync all items
  const syncAll = async () => {
    setSyncing(true);
    try {
      const response = await fetch('/api/v1/plaid/sync-all?days=30', {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setSuccessMessage(data.message);
        await fetchTransactions();
        await fetchItems();
      }
    } catch (err) {
      setError('Failed to sync transactions');
    } finally {
      setSyncing(false);
    }
  };

  // Remove an item
  const removeItem = async (itemId: number) => {
    if (!confirm('Are you sure you want to disconnect this account?')) return;
    
    try {
      const response = await fetch(`/api/v1/plaid/items/${itemId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        setSuccessMessage('Account disconnected');
        setSelectedItem(null);
        await fetchItems();
      }
    } catch (err) {
      setError('Failed to disconnect account');
    }
  };

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchItems(), fetchLinkToken(), fetchTransactions()]);
      setLoading(false);
    };
    init();
  }, [fetchItems, fetchLinkToken, fetchTransactions]);

  // Load accounts when item is selected
  useEffect(() => {
    if (selectedItem) {
      fetchAccounts(selectedItem.id);
    } else {
      setAccounts([]);
    }
  }, [selectedItem, fetchAccounts]);

  // Clear messages after 5 seconds
  useEffect(() => {
    if (successMessage || error) {
      const timer = setTimeout(() => {
        setSuccessMessage(null);
        setError(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [successMessage, error]);

  if (loading) {
    return (
      <div className={styles.loading}>
        <Loader2 className={styles.loadingIcon} size={48} />
        <p>Loading Plaid integration...</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerIcon}>
            <Link2 size={28} />
          </div>
          <div>
            <h1 className={styles.title}>Plaid Integration</h1>
            <p className={styles.subtitle}>
              Connect your Robinhood accounts to automatically sync investment transactions
            </p>
          </div>
        </div>
        <div className={styles.headerActions}>
          {items.length > 0 && (
            <button
              className={styles.syncAllButton}
              onClick={syncAll}
              disabled={syncing}
            >
              <RefreshCw size={18} className={syncing ? styles.spinning : ''} />
              {syncing ? 'Syncing...' : 'Sync All'}
            </button>
          )}
          <button
            className={styles.connectButton}
            onClick={() => open()}
            disabled={!ready || !linkToken}
          >
            <Plus size={18} />
            Connect Account
          </button>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className={styles.successMessage}>
          <CheckCircle size={18} />
          {successMessage}
        </div>
      )}
      {error && (
        <div className={styles.errorMessage}>
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <div className={styles.mainContent}>
        {/* Connected Accounts */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>
            <Building2 size={20} />
            Connected Institutions
          </h2>
          
          {items.length === 0 ? (
            <div className={styles.emptyState}>
              <Wallet size={48} />
              <h3>No accounts connected</h3>
              <p>Connect your Robinhood account to start syncing transactions</p>
              <button
                className={styles.connectButton}
                onClick={() => open()}
                disabled={!ready || !linkToken}
              >
                <Plus size={18} />
                Connect Your First Account
              </button>
            </div>
          ) : (
            <div className={styles.itemsList}>
              {items.map((item) => (
                <div
                  key={item.id}
                  className={`${styles.itemCard} ${selectedItem?.id === item.id ? styles.selected : ''}`}
                  onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
                >
                  <div className={styles.itemInfo}>
                    <div className={styles.institutionIcon}>
                      <Building2 size={24} />
                    </div>
                    <div>
                      <h3>{item.institution_name || 'Unknown Institution'}</h3>
                      <p>{item.accounts_count} account{item.accounts_count !== 1 ? 's' : ''}</p>
                    </div>
                  </div>
                  <div className={styles.itemMeta}>
                    {item.last_synced_at ? (
                      <span className={styles.syncedTime}>
                        <Clock size={14} />
                        Synced {new Date(item.last_synced_at).toLocaleDateString()}
                      </span>
                    ) : (
                      <span className={styles.notSynced}>Never synced</span>
                    )}
                    <ChevronRight size={20} className={styles.chevron} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Item Details */}
        {selectedItem && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>
                <Wallet size={20} />
                {selectedItem.institution_name} Accounts
              </h2>
              <div className={styles.itemActions}>
                <button
                  className={styles.actionButton}
                  onClick={() => syncItem(selectedItem.id)}
                  disabled={syncing}
                >
                  <RefreshCw size={16} className={syncing ? styles.spinning : ''} />
                  Sync
                </button>
                <button
                  className={`${styles.actionButton} ${styles.danger}`}
                  onClick={() => removeItem(selectedItem.id)}
                >
                  <Trash2 size={16} />
                  Disconnect
                </button>
              </div>
            </div>

            <div className={styles.accountsList}>
              {accounts.map((account) => (
                <div key={account.id} className={styles.accountCard}>
                  <div className={styles.accountInfo}>
                    <div className={styles.accountIcon}>
                      {account.type === 'investment' ? (
                        <TrendingUp size={20} />
                      ) : (
                        <DollarSign size={20} />
                      )}
                    </div>
                    <div>
                      <h4>{account.name}</h4>
                      <p>
                        {account.type} {account.subtype && `• ${account.subtype}`}
                        {account.mask && ` •••${account.mask}`}
                      </p>
                    </div>
                  </div>
                  {account.current_balance && (
                    <div className={styles.accountBalance}>
                      ${parseFloat(account.current_balance).toLocaleString()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Transactions */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>
            <TrendingUp size={20} />
            Recent Investment Transactions
          </h2>

          {transactions.length === 0 ? (
            <div className={styles.emptyTransactions}>
              <p>No transactions synced yet. Connect an account and sync to see your trades.</p>
            </div>
          ) : (
            <div className={styles.transactionsTable}>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((txn) => (
                    <tr key={txn.id}>
                      <td>{txn.date}</td>
                      <td className={styles.ticker}>{txn.ticker || '-'}</td>
                      <td className={styles.description}>
                        {txn.name}
                        {txn.option_type && (
                          <span className={styles.optionBadge}>
                            {txn.option_type} ${txn.strike_price} {txn.expiration_date}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`${styles.typeBadge} ${styles[txn.type] || ''}`}>
                          {txn.type}
                        </span>
                      </td>
                      <td>{txn.quantity || '-'}</td>
                      <td>{txn.price ? `$${parseFloat(txn.price).toFixed(2)}` : '-'}</td>
                      <td className={txn.amount && parseFloat(txn.amount) > 0 ? styles.positive : styles.negative}>
                        {txn.amount ? `$${Math.abs(parseFloat(txn.amount)).toLocaleString()}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Info Box */}
      <div className={styles.infoBox}>
        <h3>How it works</h3>
        <ol>
          <li>Click "Connect Account" to securely link your Robinhood accounts via Plaid</li>
          <li>Plaid will open a secure window where you log in to Robinhood</li>
          <li>Once connected, click "Sync" to import your investment transactions</li>
          <li>Transactions are stored locally and used for RLHF reconciliation</li>
        </ol>
        <p className={styles.disclaimer}>
          <ExternalLink size={14} />
          Plaid is a secure, bank-level connection service used by thousands of financial apps.
          Your credentials are never stored by this application.
        </p>
      </div>
    </div>
  );
}

