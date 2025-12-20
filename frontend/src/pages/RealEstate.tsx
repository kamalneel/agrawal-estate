import { useState, useEffect } from 'react'
import {
  Home,
  MapPin,
  Bed,
  Bath,
  Square,
  Calendar,
  Car,
  Building2,
  TrendingUp,
  DollarSign,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Sparkles,
  RefreshCw,
  ImageIcon,
  Award,
} from 'lucide-react'
import { getAuthHeaders } from '../contexts/AuthContext'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import styles from './RealEstate.module.css'

const API_BASE = '/api/v1'

// Types
interface PropertyImage {
  url: string
  caption: string
  type: string
}

interface Property {
  id: number
  address: string
  city: string
  state: string
  zip_code: string
  full_address: string
  property_type: string
  property_type_display: string
  purchase_date: string
  purchase_year: number
  purchase_price: number
  current_value: number
  current_value_date: string
  valuation_source: string
  zillow_url: string
  bedrooms: number
  bathrooms: number
  square_feet: number
  lot_size: number
  year_built: number
  stories: number
  parking: string
  property_style: string
  has_mortgage: boolean
  mortgage_balance: number
  equity: number
  equity_percent: number
  is_paid_off: boolean
  total_appreciation: number
  appreciation_percent: number
  annual_appreciation_rate: number
  images: PropertyImage[]
  highlights: string[]
  notes: string
}

interface Valuation {
  date: string
  value: number
  source: string
}

interface PropertiesResponse {
  properties: Property[]
  total_value: number
  total_equity: number
  total_mortgage_balance: number
  property_count: number
}

// Helper functions
const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

const formatPercent = (value: number) => {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

// Custom Tooltip for Chart
interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ value: number; payload: Valuation }>
}

function ChartTooltip({ active, payload }: CustomTooltipProps) {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    return (
      <div className={styles.chartTooltip}>
        <div className={styles.tooltipDate}>{data.date}</div>
        <div className={styles.tooltipValue}>{formatCurrency(data.value)}</div>
        <div className={styles.tooltipSource}>{data.source}</div>
      </div>
    )
  }
  return null
}

// Image Gallery Component
interface ImageGalleryProps {
  images: PropertyImage[]
}

function ImageGallery({ images }: ImageGalleryProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [imageErrors, setImageErrors] = useState<Set<number>>(new Set())

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1))
  }

  const handleNext = () => {
    setCurrentIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1))
  }

  const handleImageError = (index: number) => {
    setImageErrors((prev) => new Set(prev).add(index))
  }

  const currentImage = images[currentIndex]
  const hasError = imageErrors.has(currentIndex)

  return (
    <div className={styles.gallery}>
      {!hasError ? (
        <img
          src={currentImage.url}
          alt={currentImage.caption}
          className={styles.mainImage}
          onError={() => handleImageError(currentIndex)}
        />
      ) : (
        <div className={styles.imagePlaceholder}>
          <ImageIcon size={64} />
          <p className={styles.imagePlaceholderText}>
            Property images available. Add photos to:<br />
            <code>public/properties/303-hartstene/</code>
          </p>
        </div>
      )}

      {images.length > 1 && (
        <>
          <button
            className={`${styles.galleryNav} ${styles.galleryNavPrev}`}
            onClick={handlePrev}
            aria-label="Previous image"
          >
            <ChevronLeft size={24} />
          </button>
          <button
            className={`${styles.galleryNav} ${styles.galleryNavNext}`}
            onClick={handleNext}
            aria-label="Next image"
          >
            <ChevronRight size={24} />
          </button>
          <div className={styles.galleryDots}>
            {images.map((_, index) => (
              <button
                key={index}
                className={`${styles.galleryDot} ${index === currentIndex ? styles.active : ''}`}
                onClick={() => setCurrentIndex(index)}
                aria-label={`Go to image ${index + 1}`}
              />
            ))}
          </div>
        </>
      )}

      {!hasError && currentImage.caption && (
        <div className={styles.imageCaption}>{currentImage.caption}</div>
      )}
    </div>
  )
}

// Property Card Component
interface PropertyCardProps {
  property: Property
  valuations: Valuation[]
}

function PropertyCard({ property, valuations }: PropertyCardProps) {
  // Transform valuations for chart
  const chartData = valuations.map((v) => ({
    ...v,
    date: new Date(v.date).toLocaleDateString('en-US', { 
      year: 'numeric',
      month: 'short'
    }),
    value: v.value,
  }))

  return (
    <>
      <div className={styles.propertyCard}>
        <ImageGallery images={property.images} />

        <div className={styles.propertyDetails}>
          {/* Header with address and value */}
          <div className={styles.propertyHeader}>
            <div className={styles.propertyTitle}>
              <h2>{property.address}</h2>
              <div className={styles.propertyAddress}>
                <MapPin size={16} />
                {property.city}, {property.state} {property.zip_code}
              </div>
              <div className={styles.propertyType}>
                <Home size={14} />
                {property.property_type_display}
              </div>
            </div>
            <div className={styles.propertyValue}>
              <div className={styles.propertyValueLabel}>Current Estimate</div>
              <div className={styles.propertyValueAmount}>
                {formatCurrency(property.current_value)}
              </div>
              <a
                href={property.zillow_url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.zillowLink}
              >
                <span>View on Zillow</span>
                <ExternalLink size={12} />
              </a>
            </div>
          </div>

          {/* Property Specs */}
          <div className={styles.specsGrid}>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Bed size={22} />
              </div>
              <div className={styles.specValue}>{property.bedrooms}</div>
              <div className={styles.specLabel}>Bedrooms</div>
            </div>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Bath size={22} />
              </div>
              <div className={styles.specValue}>{property.bathrooms}</div>
              <div className={styles.specLabel}>Bathrooms</div>
            </div>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Square size={22} />
              </div>
              <div className={styles.specValue}>{property.square_feet.toLocaleString()}</div>
              <div className={styles.specLabel}>Sq Ft</div>
            </div>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Building2 size={22} />
              </div>
              <div className={styles.specValue}>{property.stories}</div>
              <div className={styles.specLabel}>Stories</div>
            </div>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Calendar size={22} />
              </div>
              <div className={styles.specValue}>{property.year_built}</div>
              <div className={styles.specLabel}>Year Built</div>
            </div>
            <div className={styles.specItem}>
              <div className={styles.specIcon}>
                <Car size={22} />
              </div>
              <div className={styles.specValue}>2</div>
              <div className={styles.specLabel}>Garage</div>
            </div>
          </div>

          {/* Financial Summary */}
          <div className={styles.financialGrid}>
            <div className={styles.financialCard}>
              <div className={styles.financialCardHeader}>
                <div className={`${styles.financialCardIcon} ${styles.equity}`}>
                  <DollarSign size={20} />
                </div>
                <div className={styles.financialCardTitle}>Total Equity</div>
              </div>
              <div className={`${styles.financialCardValue} ${styles.positive}`}>
                {formatCurrency(property.equity)}
              </div>
              <div className={styles.financialCardSubtext}>
                {property.equity_percent.toFixed(0)}% equity
              </div>
            </div>

            <div className={styles.financialCard}>
              <div className={styles.financialCardHeader}>
                <div className={`${styles.financialCardIcon} ${styles.appreciation}`}>
                  <TrendingUp size={20} />
                </div>
                <div className={styles.financialCardTitle}>Total Appreciation</div>
              </div>
              <div className={`${styles.financialCardValue} ${styles.positive}`}>
                {formatCurrency(property.total_appreciation)}
              </div>
              <div className={styles.financialCardSubtext}>
                {formatPercent(property.appreciation_percent)} since purchase
              </div>
            </div>

            <div className={styles.financialCard}>
              <div className={styles.financialCardHeader}>
                <div className={`${styles.financialCardIcon} ${styles.purchase}`}>
                  <Calendar size={20} />
                </div>
                <div className={styles.financialCardTitle}>Purchase Price</div>
              </div>
              <div className={styles.financialCardValue}>
                {formatCurrency(property.purchase_price)}
              </div>
              <div className={styles.financialCardSubtext}>
                Purchased in {property.purchase_year}
              </div>
            </div>

            <div className={styles.financialCard}>
              <div className={styles.financialCardHeader}>
                <div className={`${styles.financialCardIcon} ${styles.paid}`}>
                  <CheckCircle2 size={20} />
                </div>
                <div className={styles.financialCardTitle}>Mortgage Status</div>
              </div>
              <div className={styles.paidOffBadge}>
                <Award size={16} />
                Fully Paid Off
              </div>
              <div className={styles.financialCardSubtext}>
                No outstanding mortgage balance
              </div>
            </div>
          </div>

          {/* Location Highlights */}
          <div className={styles.highlights}>
            <div className={styles.highlightsTitle}>Location Highlights</div>
            <div className={styles.highlightsList}>
              {property.highlights.map((highlight, index) => (
                <div key={index} className={styles.highlightTag}>
                  <Sparkles size={14} />
                  {highlight}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Valuation History Chart */}
      <div className={styles.chartSection}>
        <div className={styles.chartHeader}>
          <h2>Property Value History</h2>
          <div className={styles.chartLegend}>
            <div className={styles.chartLegendItem}>
              <div className={`${styles.chartLegendDot} ${styles.value}`} />
              <span>Zillow Estimate</span>
            </div>
            <div className={styles.chartLegendItem}>
              <div className={`${styles.chartLegendDot} ${styles.purchase}`} />
              <span>Purchase Price</span>
            </div>
          </div>
        </div>
        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height={350}>
            <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <defs>
                <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00D632" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00D632" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#737373', fontSize: 12 }}
                dy={10}
                interval={2}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#737373', fontSize: 12 }}
                tickFormatter={(v) => `$${(v / 1000000).toFixed(1)}M`}
                dx={-10}
                width={70}
                domain={[500000, 1800000]}
              />
              <ReferenceLine
                y={property.purchase_price}
                stroke="#FFB800"
                strokeDasharray="5 5"
                strokeWidth={2}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#00D632"
                strokeWidth={3}
                fill="url(#valueGradient)"
                animationDuration={1500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  )
}

// Main Real Estate Component
export function RealEstate() {
  const [properties, setProperties] = useState<Property[]>([])
  const [valuations, setValuations] = useState<Valuation[]>([])
  const [totalValue, setTotalValue] = useState(0)
  const [totalEquity, setTotalEquity] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    setError(null)

    try {
      // Fetch properties and valuations in parallel
      const [propertiesRes, valuationsRes] = await Promise.all([
        fetch(`${API_BASE}/real-estate/properties`, {
          headers: getAuthHeaders(),
        }),
        fetch(`${API_BASE}/real-estate/valuations`, {
          headers: getAuthHeaders(),
        }),
      ])

      if (!propertiesRes.ok || !valuationsRes.ok) {
        throw new Error('Failed to fetch real estate data')
      }

      const propertiesData: PropertiesResponse = await propertiesRes.json()
      const valuationsData = await valuationsRes.json()

      setProperties(propertiesData.properties || [])
      setTotalValue(propertiesData.total_value || 0)
      setTotalEquity(propertiesData.total_equity || 0)
      setValuations(valuationsData.valuations || [])
    } catch (err) {
      console.error('Error fetching real estate data:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Loading state
  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={32} className={styles.spinner} />
          <p>Loading real estate portfolio...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>
          <Home size={48} />
          <h3>Error Loading Data</h3>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  // Empty state
  if (properties.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyState}>
          <Home size={48} />
          <h3>No Properties Found</h3>
          <p>Add your real estate holdings to track property values and equity.</p>
        </div>
      </div>
    )
  }

  const property = properties[0]
  const appreciation = property.total_appreciation
  const appreciationPercent = property.appreciation_percent

  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>Total Real Estate Value</div>
          <div className={styles.heroValue}>{formatCurrency(totalValue)}</div>
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Total Equity:</span>
              <span className={`${styles.heroStatValue} ${styles.positive}`}>
                {formatCurrency(totalEquity)}
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Appreciation:</span>
              <span className={`${styles.heroStatValue} ${styles.positive}`}>
                {formatCurrency(appreciation)} ({formatPercent(appreciationPercent)})
              </span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Properties:</span>
              <span className={styles.heroStatValue}>{properties.length}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Property Cards */}
      {properties.map((prop) => (
        <PropertyCard key={prop.id} property={prop} valuations={valuations} />
      ))}
    </div>
  )
}
