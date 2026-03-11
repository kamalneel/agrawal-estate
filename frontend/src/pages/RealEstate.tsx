import { useState, useEffect, useCallback, useRef } from 'react'
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
  Users,
  FileText,
  Upload,
  Download,
  Trash2,
  Plus,
  Save,
  X,
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
import {
  formatCurrency as sharedFormatCurrency,
  GRID_PROPS,
  X_AXIS_PROPS,
  Y_AXIS_PROPS,
  CHART_MARGINS,
  CHART_GREEN,
  ChartTooltip as SharedChartTooltip,
} from '../components/charts'

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

interface RentalAgreement {
  id: number
  property_id: number
  lease_start_date: string
  lease_end_date: string
  tenant_names: string
  monthly_rent: number
  monthly_hoa: number | null
  security_deposit: number | null
  annual_rent: number
  notes: string | null
}

interface RentalExpense {
  id: number
  property_id: number
  tax_year: number
  category: string
  category_display: string
  amount: number
  description: string | null
}

interface RentalSummary {
  property_id: number
  tax_year: number
  annual_income: number
  cost_of_property: number | null
  expenses: RentalExpense[]
  total_expenses: number
  net_income: number
}

interface RentalDocument {
  id: number
  property_id: number
  document_type: string
  tax_year: number | null
  file_name: string
  file_size: number
  mime_type: string
  notes: string | null
  created_at: string
}

// Helper functions — delegate to shared formatters
const formatCurrency = sharedFormatCurrency

const formatCurrencyDecimal = (value: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

const formatPercent = (value: number) => {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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

// ── Rental Agreements Section ────────────────────────────────

interface RentalAgreementsSectionProps {
  propertyId: number
}

function RentalAgreementsSection({ propertyId }: RentalAgreementsSectionProps) {
  const [agreements, setAgreements] = useState<RentalAgreement[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    lease_start_date: '',
    lease_end_date: '',
    tenant_names: '',
    monthly_rent: '',
    monthly_hoa: '',
    security_deposit: '',
    notes: '',
  })

  const fetchAgreements = useCallback(async () => {
    const res = await fetch(
      `${API_BASE}/real-estate/rental-agreements?property_id=${propertyId}`,
      { headers: getAuthHeaders() }
    )
    if (res.ok) {
      const data = await res.json()
      setAgreements(data.agreements || [])
    }
  }, [propertyId])

  useEffect(() => { fetchAgreements() }, [fetchAgreements])

  const handleSubmit = async () => {
    await fetch(`${API_BASE}/real-estate/rental-agreements`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        property_id: propertyId,
        lease_start_date: form.lease_start_date,
        lease_end_date: form.lease_end_date,
        tenant_names: form.tenant_names,
        monthly_rent: parseFloat(form.monthly_rent) || 0,
        monthly_hoa: form.monthly_hoa ? parseFloat(form.monthly_hoa) : null,
        security_deposit: form.security_deposit ? parseFloat(form.security_deposit) : null,
        notes: form.notes || null,
      }),
    })
    setShowForm(false)
    setForm({ lease_start_date: '', lease_end_date: '', tenant_names: '', monthly_rent: '', monthly_hoa: '', security_deposit: '', notes: '' })
    fetchAgreements()
  }

  const isCurrentLease = (a: RentalAgreement) => {
    const today = new Date().toISOString().split('T')[0]
    return a.lease_start_date <= today && a.lease_end_date >= today
  }

  return (
    <div className={styles.rentalSection}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleRow}>
          <Users size={22} />
          <h2>Rental Agreements</h2>
        </div>
        <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>
          {showForm ? <X size={16} /> : <Plus size={16} />}
          {showForm ? 'Cancel' : 'Add Agreement'}
        </button>
      </div>

      {showForm && (
        <div className={styles.formCard}>
          <div className={styles.formGrid}>
            <div className={styles.formField}>
              <label>Lease Start</label>
              <input type="date" value={form.lease_start_date} onChange={e => setForm({ ...form, lease_start_date: e.target.value })} />
            </div>
            <div className={styles.formField}>
              <label>Lease End</label>
              <input type="date" value={form.lease_end_date} onChange={e => setForm({ ...form, lease_end_date: e.target.value })} />
            </div>
            <div className={styles.formField}>
              <label>Tenant Names</label>
              <input type="text" value={form.tenant_names} onChange={e => setForm({ ...form, tenant_names: e.target.value })} placeholder="e.g., John Doe & Jane Doe" />
            </div>
            <div className={styles.formField}>
              <label>Monthly Rent ($)</label>
              <input type="number" value={form.monthly_rent} onChange={e => setForm({ ...form, monthly_rent: e.target.value })} />
            </div>
            <div className={styles.formField}>
              <label>Monthly HOA ($)</label>
              <input type="number" value={form.monthly_hoa} onChange={e => setForm({ ...form, monthly_hoa: e.target.value })} />
            </div>
            <div className={styles.formField}>
              <label>Security Deposit ($)</label>
              <input type="number" value={form.security_deposit} onChange={e => setForm({ ...form, security_deposit: e.target.value })} />
            </div>
          </div>
          <div className={styles.formField} style={{ marginTop: '12px' }}>
            <label>Notes</label>
            <input type="text" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>
          <button className={styles.saveBtn} onClick={handleSubmit}>
            <Save size={16} /> Save Agreement
          </button>
        </div>
      )}

      <div className={styles.tableWrapper}>
        <table className={styles.dataTable}>
          <thead>
            <tr>
              <th>Period</th>
              <th>Tenants</th>
              <th>Monthly Rent</th>
              <th>Monthly HOA</th>
              <th>Annual Rent</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {agreements.map(a => (
              <tr key={a.id} className={isCurrentLease(a) ? styles.currentRow : ''}>
                <td className={styles.monoCell}>
                  {new Date(a.lease_start_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
                  {' - '}
                  {new Date(a.lease_end_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
                </td>
                <td>{a.tenant_names}</td>
                <td className={styles.monoCell}>{formatCurrencyDecimal(a.monthly_rent)}</td>
                <td className={styles.monoCell}>{a.monthly_hoa ? formatCurrencyDecimal(a.monthly_hoa) : '-'}</td>
                <td className={`${styles.monoCell} ${styles.positive}`}>{formatCurrency(a.annual_rent)}</td>
                <td>
                  {isCurrentLease(a) ? (
                    <span className={styles.activeBadge}>Active</span>
                  ) : new Date(a.lease_end_date) < new Date() ? (
                    <span className={styles.expiredBadge}>Expired</span>
                  ) : (
                    <span className={styles.futureBadge}>Upcoming</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Annual Income & Expenses Section ─────────────────────────

interface AnnualExpensesSectionProps {
  propertyId: number
}

const EXPENSE_CATEGORIES = [
  'advertising',
  'auto_and_travel',
  'cleaning_and_maintenance',
  'insurance',
  'legal_and_professional_fee',
  'mortgage_interest',
  'repairs',
  'supplies',
  'property_tax',
  'hoa',
  'maintenance',
]

function AnnualExpensesSection({ propertyId }: AnnualExpensesSectionProps) {
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: currentYear - 2020 }, (_, i) => currentYear - i)
  const [selectedYear, setSelectedYear] = useState(currentYear)
  const [summary, setSummary] = useState<RentalSummary | null>(null)
  const [editingIncome, setEditingIncome] = useState(false)
  const [incomeValue, setIncomeValue] = useState('')
  const [editingExpense, setEditingExpense] = useState<string | null>(null)
  const [expenseValue, setExpenseValue] = useState('')
  const [showAddCustom, setShowAddCustom] = useState(false)
  const [customCategory, setCustomCategory] = useState('')
  const [customAmount, setCustomAmount] = useState('')

  const fetchSummary = useCallback(async () => {
    const res = await fetch(
      `${API_BASE}/real-estate/rental-summary?property_id=${propertyId}&tax_year=${selectedYear}`,
      { headers: getAuthHeaders() }
    )
    if (res.ok) {
      const data: RentalSummary = await res.json()
      setSummary(data)
      setIncomeValue(String(data.annual_income || ''))
    }
  }, [propertyId, selectedYear])

  useEffect(() => { fetchSummary() }, [fetchSummary])

  const saveIncome = async () => {
    await fetch(`${API_BASE}/real-estate/rental-income`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        property_id: propertyId,
        tax_year: selectedYear,
        annual_income: parseFloat(incomeValue) || 0,
      }),
    })
    setEditingIncome(false)
    fetchSummary()
  }

  const saveExpense = async (category: string, amount: string) => {
    await fetch(`${API_BASE}/real-estate/rental-expenses`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        property_id: propertyId,
        tax_year: selectedYear,
        category,
        amount: parseFloat(amount) || 0,
      }),
    })
    setEditingExpense(null)
    fetchSummary()
  }

  const deleteExpense = async (expenseId: number) => {
    await fetch(`${API_BASE}/real-estate/rental-expenses/${expenseId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    fetchSummary()
  }

  const addCustomExpense = async () => {
    if (!customCategory) return
    await fetch(`${API_BASE}/real-estate/rental-expenses`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        property_id: propertyId,
        tax_year: selectedYear,
        category: customCategory.toLowerCase().replace(/\s+/g, '_'),
        amount: parseFloat(customAmount) || 0,
        description: customCategory,
      }),
    })
    setShowAddCustom(false)
    setCustomCategory('')
    setCustomAmount('')
    fetchSummary()
  }

  // Build expense rows: merge existing with standard categories
  const expenseMap = new Map<string, RentalExpense>()
  summary?.expenses.forEach(e => expenseMap.set(e.category, e))

  const allCategories = [...EXPENSE_CATEGORIES]
  summary?.expenses.forEach(e => {
    if (!allCategories.includes(e.category)) allCategories.push(e.category)
  })

  return (
    <div className={styles.rentalSection}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleRow}>
          <DollarSign size={22} />
          <h2>Annual Income & Expenses</h2>
        </div>
        <div className={styles.yearTabs}>
          {years.map(y => (
            <button
              key={y}
              className={`${styles.yearTab} ${y === selectedYear ? styles.activeTab : ''}`}
              onClick={() => setSelectedYear(y)}
            >
              {y}
            </button>
          ))}
        </div>
      </div>

      {summary && (
        <>
          {/* Income row */}
          <div className={styles.incomeRow}>
            <div className={styles.incomeLabel}>Annual Rental Income ({selectedYear})</div>
            {editingIncome ? (
              <div className={styles.inlineEdit}>
                <span className={styles.dollarPrefix}>$</span>
                <input
                  type="number"
                  value={incomeValue}
                  onChange={e => setIncomeValue(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveIncome(); if (e.key === 'Escape') setEditingIncome(false) }}
                  autoFocus
                />
                <button onClick={saveIncome} className={styles.iconBtn}><Save size={14} /></button>
                <button onClick={() => setEditingIncome(false)} className={styles.iconBtn}><X size={14} /></button>
              </div>
            ) : (
              <div
                className={`${styles.incomeValue} ${styles.clickable}`}
                onClick={() => setEditingIncome(true)}
              >
                {summary.annual_income ? formatCurrency(summary.annual_income) : 'Click to enter'}
              </div>
            )}
          </div>

          {/* Expenses table */}
          <div className={styles.tableWrapper}>
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Amount</th>
                  <th style={{ width: 60 }}></th>
                </tr>
              </thead>
              <tbody>
                {allCategories.map(cat => {
                  const existing = expenseMap.get(cat)
                  const amount = existing?.amount ?? 0
                  const isEditing = editingExpense === cat

                  return (
                    <tr key={cat}>
                      <td>{existing?.description || cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</td>
                      <td className={styles.monoCell}>
                        {isEditing ? (
                          <div className={styles.inlineEdit}>
                            <span className={styles.dollarPrefix}>$</span>
                            <input
                              type="number"
                              value={expenseValue}
                              onChange={e => setExpenseValue(e.target.value)}
                              onKeyDown={e => { if (e.key === 'Enter') saveExpense(cat, expenseValue); if (e.key === 'Escape') setEditingExpense(null) }}
                              autoFocus
                            />
                            <button onClick={() => saveExpense(cat, expenseValue)} className={styles.iconBtn}><Save size={14} /></button>
                          </div>
                        ) : (
                          <span
                            className={styles.clickable}
                            onClick={() => { setEditingExpense(cat); setExpenseValue(String(amount)) }}
                          >
                            {formatCurrencyDecimal(amount)}
                          </span>
                        )}
                      </td>
                      <td>
                        {existing && !EXPENSE_CATEGORIES.includes(cat) && (
                          <button className={styles.deleteBtn} onClick={() => deleteExpense(existing.id)}>
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Add custom expense */}
          {showAddCustom ? (
            <div className={styles.customExpenseForm}>
              <input
                type="text"
                placeholder="Category name"
                value={customCategory}
                onChange={e => setCustomCategory(e.target.value)}
              />
              <input
                type="number"
                placeholder="Amount"
                value={customAmount}
                onChange={e => setCustomAmount(e.target.value)}
              />
              <button onClick={addCustomExpense} className={styles.saveBtn}><Save size={14} /> Add</button>
              <button onClick={() => setShowAddCustom(false)} className={styles.iconBtn}><X size={14} /></button>
            </div>
          ) : (
            <button className={styles.addCustomBtn} onClick={() => setShowAddCustom(true)}>
              <Plus size={14} /> Add Custom Expense
            </button>
          )}

          {/* Summary footer */}
          <div className={styles.summaryFooter}>
            <div className={styles.summaryRow}>
              <span>Total Expenses</span>
              <span className={`${styles.monoCell} ${styles.negative}`}>{formatCurrency(summary.total_expenses)}</span>
            </div>
            <div className={styles.summaryRow}>
              <span>Net Income</span>
              <span className={`${styles.monoCell} ${summary.net_income >= 0 ? styles.positive : styles.negative}`}>
                {formatCurrency(summary.net_income)}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Documents Section ────────────────────────────────────────

interface DocumentsSectionProps {
  propertyId: number
}

function DocumentsSection({ propertyId }: DocumentsSectionProps) {
  const [documents, setDocuments] = useState<RentalDocument[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchDocuments = useCallback(async () => {
    const res = await fetch(
      `${API_BASE}/real-estate/rental-documents?property_id=${propertyId}`,
      { headers: getAuthHeaders() }
    )
    if (res.ok) {
      const data = await res.json()
      setDocuments(data.documents || [])
    }
  }, [propertyId])

  useEffect(() => { fetchDocuments() }, [fetchDocuments])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)
    formData.append('document_type', 'other')

    const authHeaders = getAuthHeaders() as Record<string, string>
    // Don't set Content-Type for FormData - browser sets it with boundary
    const headers: Record<string, string> = {}
    if (authHeaders['Authorization']) headers['Authorization'] = authHeaders['Authorization']
    if (authHeaders['X-Auth-Token']) headers['X-Auth-Token'] = authHeaders['X-Auth-Token']

    await fetch(`${API_BASE}/real-estate/rental-documents/${propertyId}`, {
      method: 'POST',
      headers,
      body: formData,
    })
    fetchDocuments()
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDelete = async (docId: number) => {
    await fetch(`${API_BASE}/real-estate/rental-documents/${docId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    fetchDocuments()
  }

  return (
    <div className={styles.rentalSection}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleRow}>
          <FileText size={22} />
          <h2>Rental Documents</h2>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            style={{ display: 'none' }}
            onChange={handleUpload}
            accept=".pdf,.doc,.docx,.jpg,.png"
          />
          <button className={styles.addBtn} onClick={() => fileInputRef.current?.click()}>
            <Upload size={16} /> Upload
          </button>
        </div>
      </div>

      <div className={styles.tableWrapper}>
        <table className={styles.dataTable}>
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Year</th>
              <th>Size</th>
              <th>Notes</th>
              <th style={{ width: 100 }}></th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 ? (
              <tr><td colSpan={6} className={styles.emptyRow}>No documents uploaded</td></tr>
            ) : (
              documents.map(doc => (
                <tr key={doc.id}>
                  <td className={styles.fileNameCell}>{doc.file_name}</td>
                  <td>{doc.document_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</td>
                  <td className={styles.monoCell}>{doc.tax_year || '-'}</td>
                  <td className={styles.monoCell}>{formatFileSize(doc.file_size)}</td>
                  <td>{doc.notes || '-'}</td>
                  <td>
                    <div className={styles.docActions}>
                      <a
                        href={`${API_BASE}/real-estate/rental-documents/${doc.id}/download`}
                        className={styles.iconBtn}
                        title="Download"
                      >
                        <Download size={14} />
                      </a>
                      <button
                        className={styles.deleteBtn}
                        onClick={() => handleDelete(doc.id)}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
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

  const isRental = property.property_type === 'rental'

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
            <AreaChart data={chartData} margin={CHART_MARGINS}>
              <defs>
                <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_GREEN} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={CHART_GREEN} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="date" {...X_AXIS_PROPS} interval={2} />
              <YAxis
                {...Y_AXIS_PROPS}
                tickFormatter={(v) => `$${(v / 1000000).toFixed(1)}M`}
                domain={[500000, 1800000]}
              />
              <ReferenceLine
                y={property.purchase_price}
                stroke="#FFB800"
                strokeDasharray="5 5"
                strokeWidth={2}
              />
              <Tooltip content={<SharedChartTooltip labelKey="date" />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={CHART_GREEN}
                strokeWidth={3}
                fill="url(#valueGradient)"
                animationDuration={1500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Rental Management Sections */}
      {isRental && (
        <>
          <RentalAgreementsSection propertyId={property.id} />
          <AnnualExpensesSection propertyId={property.id} />
          <DocumentsSection propertyId={property.id} />
        </>
      )}
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
