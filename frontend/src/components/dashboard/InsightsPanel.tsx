import { useState, useEffect } from 'react'
import {
  Sparkles,
  Trophy,
  TrendingUp,
  TrendingDown,
  Target,
  Flame,
  Crown,
  Shuffle,
  PieChart,
  BarChart2,
  Coins,
  ArrowUpRight,
  ArrowDownRight,
  CalendarCheck,
  CalendarX,
  Loader2,
  RefreshCw,
  Check,
  Archive,
  RotateCcw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { getAuthHeaders } from '../../contexts/AuthContext'
import styles from './InsightsPanel.module.css'
import clsx from 'clsx'

interface Insight {
  id: string
  category: 'record' | 'outlier' | 'trend' | 'milestone' | 'comparison' | 'streak'
  sentiment: 'positive' | 'neutral' | 'negative' | 'celebration'
  title: string
  description: string
  metric_name: string
  metric_value: number | null
  comparison_value: number | null
  change_percent: number | null
  icon: string
  priority: number
  tags: string[]
  timestamp: string
}

interface InsightsResponse {
  insights: Insight[]
  count: number
  archived_count: number
  generated_at: string
  error?: string
}

interface AllInsightsResponse {
  active: Insight[]
  archived: Insight[]
  active_count: number
  archived_count: number
  generated_at: string
  error?: string
}

const ICON_MAP: Record<string, typeof Sparkles> = {
  sparkles: Sparkles,
  trophy: Trophy,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  target: Target,
  flame: Flame,
  crown: Crown,
  shuffle: Shuffle,
  'pie-chart': PieChart,
  'bar-chart-2': BarChart2,
  coins: Coins,
  'arrow-up-right': ArrowUpRight,
  'arrow-down-right': ArrowDownRight,
  'calendar-check': CalendarCheck,
  'calendar-x': CalendarX,
}

function getIconComponent(iconName: string) {
  return ICON_MAP[iconName] || Sparkles
}

interface InsightCardProps {
  insight: Insight
  index: number
  onDismiss?: (id: string) => void
  onRestore?: (id: string) => void
  isArchived?: boolean
  dismissing?: boolean
}

function InsightCard({ insight, index, onDismiss, onRestore, isArchived, dismissing }: InsightCardProps) {
  const Icon = getIconComponent(insight.icon)
  
  const categoryLabels: Record<string, string> = {
    record: '🏆 Record',
    outlier: '📊 Notable',
    trend: '📈 Trend',
    milestone: '🎯 Milestone',
    comparison: '⚖️ Compare',
    streak: '🔥 Streak',
  }
  
  return (
    <div 
      className={clsx(
        styles.insightCard,
        styles[insight.sentiment],
        styles[insight.category],
        isArchived && styles.archived,
        dismissing && styles.dismissing
      )}
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <div className={styles.cardGlow} />
      
      <div className={styles.cardHeader}>
        <div className={clsx(styles.iconWrapper, styles[`icon${insight.sentiment}`])}>
          <Icon size={20} />
        </div>
        <span className={styles.categoryBadge}>
          {categoryLabels[insight.category] || insight.category}
        </span>
        
        {/* Dismiss/Restore button */}
        {(onDismiss || onRestore) && (
          <button
            className={clsx(styles.dismissButton, isArchived && styles.restoreButton)}
            onClick={(e) => {
              e.stopPropagation()
              if (isArchived && onRestore) {
                onRestore(insight.id)
              } else if (onDismiss) {
                onDismiss(insight.id)
              }
            }}
            title={isArchived ? 'Restore insight' : 'Mark as read'}
            disabled={dismissing}
          >
            {isArchived ? <RotateCcw size={14} /> : <Check size={14} />}
          </button>
        )}
      </div>
      
      <h3 className={styles.insightTitle}>{insight.title}</h3>
      <p className={styles.insightDescription}>{insight.description}</p>
      
      {insight.tags.length > 0 && (
        <div className={styles.tags}>
          {insight.tags.slice(0, 3).map((tag, i) => (
            <span key={i} className={styles.tag}>{tag}</span>
          ))}
        </div>
      )}
    </div>
  )
}

export function InsightsPanel() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [archivedInsights, setArchivedInsights] = useState<Insight[]>([])
  const [archivedCount, setArchivedCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [dismissingId, setDismissingId] = useState<string | null>(null)
  const [showArchive, setShowArchive] = useState(false)

  async function fetchInsights(isRefresh = false) {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    
    try {
      const headers = getAuthHeaders()
      const response = await fetch('/api/v1/dashboard/insights?limit=5', { headers })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch insights: ${response.status}`)
      }
      
      const data: InsightsResponse = await response.json()
      setInsights(data.insights || [])
      setArchivedCount(data.archived_count || 0)
      setError(null)
    } catch (err) {
      console.error('Error fetching insights:', err)
      setError(err instanceof Error ? err.message : 'Failed to load insights')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  async function fetchAllInsights() {
    try {
      const headers = getAuthHeaders()
      const response = await fetch('/api/v1/dashboard/insights/all', { headers })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch all insights: ${response.status}`)
      }
      
      const data: AllInsightsResponse = await response.json()
      setInsights(data.active || [])
      setArchivedInsights(data.archived || [])
      setArchivedCount(data.archived_count || 0)
    } catch (err) {
      console.error('Error fetching all insights:', err)
    }
  }

  async function dismissInsight(insightId: string) {
    setDismissingId(insightId)
    
    try {
      const headers = getAuthHeaders()
      const response = await fetch(`/api/v1/dashboard/insights/${insightId}/archive`, {
        method: 'POST',
        headers,
      })
      
      if (!response.ok) {
        throw new Error(`Failed to archive insight: ${response.status}`)
      }
      
      // Animate out and remove from list
      setTimeout(() => {
        setInsights(prev => prev.filter(i => i.id !== insightId))
        setArchivedCount(prev => prev + 1)
        setDismissingId(null)
        
        // Fetch fresh insights to fill the gap
        fetchInsights(true)
      }, 300)
    } catch (err) {
      console.error('Error archiving insight:', err)
      setDismissingId(null)
    }
  }

  async function restoreInsight(insightId: string) {
    try {
      const headers = getAuthHeaders()
      const response = await fetch(`/api/v1/dashboard/insights/${insightId}/unarchive`, {
        method: 'POST',
        headers,
      })
      
      if (!response.ok) {
        throw new Error(`Failed to restore insight: ${response.status}`)
      }
      
      // Refresh the list
      await fetchAllInsights()
    } catch (err) {
      console.error('Error restoring insight:', err)
    }
  }

  async function clearAllArchived() {
    try {
      const headers = getAuthHeaders()
      const response = await fetch('/api/v1/dashboard/insights/clear-archive', {
        method: 'POST',
        headers,
      })
      
      if (!response.ok) {
        throw new Error(`Failed to clear archive: ${response.status}`)
      }
      
      setArchivedInsights([])
      setArchivedCount(0)
      fetchInsights(true)
    } catch (err) {
      console.error('Error clearing archive:', err)
    }
  }

  useEffect(() => {
    fetchInsights()
  }, [])

  useEffect(() => {
    if (showArchive) {
      fetchAllInsights()
    }
  }, [showArchive])

  if (loading) {
    return (
      <section className={styles.insightsSection}>
        <div className={styles.sectionHeader}>
          <div className={styles.headerLeft}>
            <Sparkles className={styles.headerIcon} size={24} />
            <h2>Daily Insights</h2>
          </div>
        </div>
        <div className={styles.loadingState}>
          <Loader2 className={styles.spinner} size={32} />
          <p>Discovering insights...</p>
        </div>
      </section>
    )
  }

  if (error) {
    return (
      <section className={styles.insightsSection}>
        <div className={styles.sectionHeader}>
          <div className={styles.headerLeft}>
            <Sparkles className={styles.headerIcon} size={24} />
            <h2>Daily Insights</h2>
          </div>
        </div>
        <div className={styles.errorState}>
          <p>Could not load insights</p>
          <button onClick={() => fetchInsights()}>Try Again</button>
        </div>
      </section>
    )
  }

  const hasNoInsights = insights.length === 0 && archivedCount === 0

  if (hasNoInsights) {
    return (
      <section className={styles.insightsSection}>
        <div className={styles.sectionHeader}>
          <div className={styles.headerLeft}>
            <Sparkles className={styles.headerIcon} size={24} />
            <h2>Daily Insights</h2>
          </div>
        </div>
        <div className={styles.emptyState}>
          <Sparkles size={48} className={styles.emptyIcon} />
          <p>No insights discovered yet</p>
          <p className={styles.emptySubtext}>
            Insights will appear as patterns emerge in your financial data
          </p>
        </div>
      </section>
    )
  }

  // Split insights: featured (top 2) and the rest
  const featuredInsights = insights.slice(0, 2)
  const otherInsights = insights.slice(2, 5)

  return (
    <section className={styles.insightsSection}>
      <div className={styles.sectionHeader}>
        <div className={styles.headerLeft}>
          <Sparkles className={styles.headerIcon} size={24} />
          <div>
            <h2>Daily Insights</h2>
            <p className={styles.headerSubtitle}>
              Patterns and milestones in your wealth journey
              {archivedCount > 0 && (
                <span className={styles.archivedBadge}>
                  {archivedCount} read
                </span>
              )}
            </p>
          </div>
        </div>
        <div className={styles.headerActions}>
          {archivedCount > 0 && (
            <button 
              className={clsx(styles.archiveToggle, showArchive && styles.active)}
              onClick={() => setShowArchive(!showArchive)}
            >
              <Archive size={16} />
              Archive
              {showArchive ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
          <button 
            className={styles.refreshButton}
            onClick={() => fetchInsights(true)}
            disabled={refreshing}
          >
            <RefreshCw size={16} className={clsx(refreshing && styles.spinning)} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Active Insights */}
      {insights.length > 0 ? (
        <>
          {/* Featured Insights - Larger Cards */}
          <div className={styles.featuredGrid}>
            {featuredInsights.map((insight, index) => (
              <InsightCard 
                key={insight.id} 
                insight={insight} 
                index={index}
                onDismiss={dismissInsight}
                dismissing={dismissingId === insight.id}
              />
            ))}
          </div>

          {/* Other Insights - Smaller Grid */}
          {otherInsights.length > 0 && (
            <div className={styles.insightsGrid}>
              {otherInsights.map((insight, index) => (
                <InsightCard 
                  key={insight.id} 
                  insight={insight} 
                  index={index + 2}
                  onDismiss={dismissInsight}
                  dismissing={dismissingId === insight.id}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <div className={styles.allReadState}>
          <Check size={32} className={styles.allReadIcon} />
          <p>You're all caught up!</p>
          <p className={styles.allReadSubtext}>
            All current insights have been reviewed. Check back later for new patterns.
          </p>
        </div>
      )}

      {/* Archived Insights Section */}
      {showArchive && archivedInsights.length > 0 && (
        <div className={styles.archiveSection}>
          <div className={styles.archiveHeader}>
            <h3>
              <Archive size={18} />
              Archived Insights ({archivedInsights.length})
            </h3>
            <button 
              className={styles.clearArchiveButton}
              onClick={clearAllArchived}
            >
              <RotateCcw size={14} />
              Restore All
            </button>
          </div>
          <div className={styles.archiveGrid}>
            {archivedInsights.map((insight, index) => (
              <InsightCard 
                key={insight.id} 
                insight={insight} 
                index={index}
                onRestore={restoreInsight}
                isArchived
              />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
