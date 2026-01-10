import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, FileText, AlertCircle, CheckCircle } from 'lucide-react';
import styles from './TaxForms.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface Form1040 {
  tax_year: number;
  filing_status: string;
  taxpayer_name: string;
  spouse_name: string | null;

  // Income (Lines 1-9)
  line_1z: number;
  line_2b: number;
  line_3b: number;
  line_7: number;
  line_8: number;
  line_9: number;

  // Adjustments (Lines 10-11)
  line_10: number;
  line_11: number;

  // Deductions (Lines 12-15)
  line_12: number;
  line_12_type: string;
  line_15: number;

  // Tax (Lines 16-24)
  line_16: number;
  line_17: number;
  line_24: number;

  // Payments (Lines 25-33)
  line_25d: number;
  line_32: number;
  line_33: number;
  line_34: number;
  line_36: number;
}

interface Schedule1 {
  line_5: number;
  line_8: number;
  line_10: number;
  line_13: number;
  line_20: number;
  line_26: number;
}

interface ScheduleE {
  property_address: string;
  line_3: number;
  line_18: number;
  line_20: number;
  line_21: number;
  line_26: number;
}

interface ScheduleD {
  line_7: number;
  line_15: number;
  line_16: number;
  line_20: number;
  line_21: number;
}

interface CaliforniaForm540 {
  tax_year: number;
  filing_status: string;
  line_11: number;
  line_12: number;
  line_13: number;
  line_16: number;
  line_17: number;
  line_19: number;  // Other income (options, etc.)
  line_20: number;
  line_22: number;
  line_23: number;
  line_25: number;
  line_31: number;
  line_33: number;
  line_34: number;
  line_41: number;
  line_44: number;
  line_46: number;
  line_49: number;
}

interface TaxFormPackage {
  form_1040: Form1040;
  schedule_1: Schedule1 | null;
  schedule_e: ScheduleE | null;
  schedule_d: ScheduleD | null;
  california_540: CaliforniaForm540 | null;
  is_forecast: boolean;
  generation_date: string;
  notes: string[];
}

export default function TaxForms() {
  const navigate = useNavigate();
  const [taxYear, setTaxYear] = useState(2025);
  const [forms, setForms] = useState<TaxFormPackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'1040' | 'schedule1' | 'scheduleE' | 'scheduleD' | 'ca540'>('1040');

  useEffect(() => {
    loadTaxForms();
  }, [taxYear]);

  const loadTaxForms = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/tax/forms/${taxYear}`,
        { headers: getAuthHeaders() }
      );

      if (!response.ok) {
        throw new Error(`Failed to load tax forms: ${response.statusText}`);
      }

      const data = await response.json();
      setForms(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tax forms');
    } finally {
      setLoading(false);
    }
  };

  const downloadPDF = async () => {
    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/tax/forms/${taxYear}/pdf`,
        { headers: getAuthHeaders() }
      );

      if (!response.ok) {
        throw new Error('Failed to download PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tax_forms_${taxYear}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      alert('Failed to download PDF. This feature may not be available yet.');
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

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <div className={styles.spinner}></div>
          <p>Generating tax forms for {taxYear}...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <AlertCircle size={48} />
          <h2>Error Loading Tax Forms</h2>
          <p>{error}</p>
          <button onClick={loadTaxForms} className={styles.retryButton}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!forms) {
    return null;
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <button onClick={() => navigate('/tax')} className={styles.backButton}>
          <ArrowLeft size={20} />
          Back to Tax Center
        </button>

        <div className={styles.headerTitle}>
          <FileText size={32} />
          <div>
            <h1>Tax Forms - {taxYear}</h1>
            <p className={styles.subtitle}>
              {forms.is_forecast ? 'Tax Forecast' : 'Filed Tax Return'} •
              Generated {new Date(forms.generation_date).toLocaleDateString()}
            </p>
          </div>
        </div>

        <button onClick={downloadPDF} className={styles.downloadButton}>
          <Download size={20} />
          Download PDF
        </button>
      </div>

      {/* Warnings/Notes */}
      {forms.notes && forms.notes.length > 0 && (
        <div className={styles.notesSection}>
          {forms.notes.map((note, index) => (
            <div key={index} className={styles.note}>
              <AlertCircle size={16} />
              <span>{note}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tab Navigation */}
      <div className={styles.tabs}>
        <button
          className={activeTab === '1040' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('1040')}
        >
          Form 1040
        </button>
        {forms.schedule_1 && (
          <button
            className={activeTab === 'schedule1' ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab('schedule1')}
          >
            Schedule 1
          </button>
        )}
        {forms.schedule_e && (
          <button
            className={activeTab === 'scheduleE' ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab('scheduleE')}
          >
            Schedule E
          </button>
        )}
        {forms.schedule_d && (
          <button
            className={activeTab === 'scheduleD' ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab('scheduleD')}
          >
            Schedule D
          </button>
        )}
        {forms.california_540 && (
          <button
            className={activeTab === 'ca540' ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab('ca540')}
          >
            CA Form 540
          </button>
        )}
      </div>

      {/* Form Content */}
      <div className={styles.formContent}>
        {activeTab === '1040' && <Form1040View form={forms.form_1040} formatCurrency={formatCurrency} />}
        {activeTab === 'schedule1' && forms.schedule_1 && (
          <Schedule1View schedule={forms.schedule_1} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'scheduleE' && forms.schedule_e && (
          <ScheduleEView schedule={forms.schedule_e} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'scheduleD' && forms.schedule_d && (
          <ScheduleDView schedule={forms.schedule_d} formatCurrency={formatCurrency} />
        )}
        {activeTab === 'ca540' && forms.california_540 && (
          <California540View form={forms.california_540} formatCurrency={formatCurrency} />
        )}
      </div>
    </div>
  );
}

// Form 1040 Component
function Form1040View({ form, formatCurrency }: { form: Form1040; formatCurrency: (n: number) => string }) {
  return (
    <div className={styles.form}>
      <div className={styles.formHeader}>
        <h2>Form 1040</h2>
        <p>U.S. Individual Income Tax Return</p>
        <p className={styles.taxYear}>Tax Year {form.tax_year}</p>
      </div>

      <div className={styles.formSection}>
        <h3>Filing Status</h3>
        <div className={styles.formRow}>
          <span className={styles.label}>{form.filing_status}</span>
          <CheckCircle size={16} className={styles.checkmark} />
        </div>
        <div className={styles.formRow}>
          <span className={styles.label}>Taxpayer:</span>
          <span className={styles.value}>{form.taxpayer_name}</span>
        </div>
        {form.spouse_name && (
          <div className={styles.formRow}>
            <span className={styles.label}>Spouse:</span>
            <span className={styles.value}>{form.spouse_name}</span>
          </div>
        )}
      </div>

      <div className={styles.formSection}>
        <h3>Income</h3>
        <FormLine line="1z" description="Wages, salaries, tips, etc." amount={form.line_1z} format={formatCurrency} />
        <FormLine line="2b" description="Taxable interest" amount={form.line_2b} format={formatCurrency} />
        <FormLine line="3b" description="Ordinary dividends" amount={form.line_3b} format={formatCurrency} />
        <FormLine line="7" description="Capital gain or (loss)" amount={form.line_7} format={formatCurrency} />
        <FormLine line="8" description="Additional income from Schedule 1" amount={form.line_8} format={formatCurrency} />
        <FormLine line="9" description="Total income" amount={form.line_9} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Adjusted Gross Income</h3>
        <FormLine line="10" description="Adjustments to income from Schedule 1" amount={form.line_10} format={formatCurrency} />
        <FormLine line="11" description="Adjusted Gross Income (AGI)" amount={form.line_11} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Tax and Credits</h3>
        <FormLine line="12" description={`${form.line_12_type === 'standard' ? 'Standard' : 'Itemized'} deduction`} amount={form.line_12} format={formatCurrency} />
        <FormLine line="15" description="Taxable income" amount={form.line_15} format={formatCurrency} highlight />
        <FormLine line="16" description="Tax" amount={form.line_16} format={formatCurrency} />
        <FormLine line="17" description="Amount from Schedule 2" amount={form.line_17} format={formatCurrency} />
        <FormLine line="24" description="Total tax" amount={form.line_24} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Payments</h3>
        <FormLine line="25d" description="Federal income tax withheld" amount={form.line_25d} format={formatCurrency} />
        <FormLine line="32" description="Total payments" amount={form.line_32} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Refund or Amount You Owe</h3>
        {form.line_33 > 0 ? (
          <>
            <FormLine line="33" description="Overpayment" amount={form.line_33} format={formatCurrency} highlight success />
            <FormLine line="34" description="Amount you want refunded" amount={form.line_34} format={formatCurrency} success />
          </>
        ) : (
          <>
            <FormLine line="36" description="Amount you owe" amount={form.line_36} format={formatCurrency} highlight warning />
          </>
        )}
      </div>
    </div>
  );
}

// Schedule 1 Component
function Schedule1View({ schedule, formatCurrency }: { schedule: Schedule1; formatCurrency: (n: number) => string }) {
  return (
    <div className={styles.form}>
      <div className={styles.formHeader}>
        <h2>Schedule 1</h2>
        <p>Additional Income and Adjustments to Income</p>
      </div>

      <div className={styles.formSection}>
        <h3>Part I: Additional Income</h3>
        <FormLine line="5" description="Rental real estate, royalties, partnerships, etc." amount={schedule.line_5} format={formatCurrency} />
        <FormLine line="8" description="Other income" amount={schedule.line_8} format={formatCurrency} />
        <FormLine line="10" description="Total additional income" amount={schedule.line_10} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Part II: Adjustments to Income</h3>
        <FormLine line="13" description="Health savings account deduction" amount={schedule.line_13} format={formatCurrency} />
        <FormLine line="20" description="IRA deduction" amount={schedule.line_20} format={formatCurrency} />
        <FormLine line="26" description="Total adjustments to income" amount={schedule.line_26} format={formatCurrency} highlight />
      </div>
    </div>
  );
}

// Schedule E Component
function ScheduleEView({ schedule, formatCurrency }: { schedule: ScheduleE; formatCurrency: (n: number) => string }) {
  return (
    <div className={styles.form}>
      <div className={styles.formHeader}>
        <h2>Schedule E</h2>
        <p>Supplemental Income and Loss</p>
      </div>

      <div className={styles.formSection}>
        <h3>Part I: Income or Loss From Rental Real Estate</h3>
        <div className={styles.formRow}>
          <span className={styles.label}>Property Address:</span>
          <span className={styles.value}>{schedule.property_address}</span>
        </div>
      </div>

      <div className={styles.formSection}>
        <h3>Income and Expenses</h3>
        <FormLine line="3" description="Rents received" amount={schedule.line_3} format={formatCurrency} />
        <FormLine line="18" description="Depreciation" amount={schedule.line_18} format={formatCurrency} />
        <FormLine line="20" description="Total expenses" amount={schedule.line_20} format={formatCurrency} />
        <FormLine line="21" description="Income or (loss) from rental real estate" amount={schedule.line_21} format={formatCurrency} highlight />
        <FormLine line="26" description="Total rental real estate income" amount={schedule.line_26} format={formatCurrency} highlight />
      </div>
    </div>
  );
}

// Schedule D Component
function ScheduleDView({ schedule, formatCurrency }: { schedule: ScheduleD; formatCurrency: (n: number) => string }) {
  return (
    <div className={styles.form}>
      <div className={styles.formHeader}>
        <h2>Schedule D</h2>
        <p>Capital Gains and Losses</p>
      </div>

      <div className={styles.formSection}>
        <h3>Part I: Short-Term Capital Gains and Losses</h3>
        <FormLine line="7" description="Net short-term capital gain or (loss)" amount={schedule.line_7} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Part II: Long-Term Capital Gains and Losses</h3>
        <FormLine line="15" description="Net long-term capital gain or (loss)" amount={schedule.line_15} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Part III: Summary</h3>
        <FormLine line="16" description="Combine lines 7 and 15" amount={schedule.line_16} format={formatCurrency} highlight />
        {schedule.line_20 > 0 && (
          <FormLine line="20" description="Net capital gain" amount={schedule.line_20} format={formatCurrency} success />
        )}
        {schedule.line_21 > 0 && (
          <FormLine line="21" description="Net capital loss" amount={schedule.line_21} format={formatCurrency} warning />
        )}
      </div>
    </div>
  );
}

// California 540 Component
function California540View({ form, formatCurrency }: { form: CaliforniaForm540; formatCurrency: (n: number) => string }) {
  return (
    <div className={styles.form}>
      <div className={styles.formHeader}>
        <h2>California Form 540</h2>
        <p>Resident Income Tax Return</p>
        <p className={styles.taxYear}>Tax Year {form.tax_year}</p>
      </div>

      <div className={styles.formSection}>
        <h3>Filing Status</h3>
        <div className={styles.formRow}>
          <span className={styles.label}>{form.filing_status}</span>
          <CheckCircle size={16} className={styles.checkmark} />
        </div>
      </div>

      <div className={styles.formSection}>
        <h3>Income</h3>
        <FormLine line="11" description="Wages, salaries, tips" amount={form.line_11} format={formatCurrency} />
        <FormLine line="12" description="Interest income" amount={form.line_12} format={formatCurrency} />
        <FormLine line="13" description="Dividends" amount={form.line_13} format={formatCurrency} />
        <FormLine line="16" description="Capital gain or (loss)" amount={form.line_16} format={formatCurrency} />
        <FormLine line="17" description="Rental, partnerships, etc." amount={form.line_17} format={formatCurrency} />
        <FormLine line="19" description="Other income (options, etc.)" amount={form.line_19} format={formatCurrency} />
        <FormLine line="20" description="Total income" amount={form.line_20} format={formatCurrency} highlight />
        <FormLine line="22" description="California AGI" amount={form.line_22} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Tax</h3>
        <FormLine line="23" description="Standard deduction or itemized deductions" amount={form.line_23} format={formatCurrency} />
        <FormLine line="25" description="Taxable income" amount={form.line_25} format={formatCurrency} highlight />
        <FormLine line="31" description="Tax" amount={form.line_31} format={formatCurrency} />
        {form.line_33 > 0 && (
          <FormLine line="33" description="Mental Health Services Tax (1%)" amount={form.line_33} format={formatCurrency} />
        )}
        <FormLine line="34" description="Total tax" amount={form.line_34} format={formatCurrency} highlight />
      </div>

      <div className={styles.formSection}>
        <h3>Payments and Refund</h3>
        <FormLine line="41" description="CA income tax withheld" amount={form.line_41} format={formatCurrency} />
        <FormLine line="44" description="Total payments" amount={form.line_44} format={formatCurrency} highlight />
        {form.line_46 > 0 ? (
          <FormLine line="46" description="Amount to be refunded" amount={form.line_46} format={formatCurrency} highlight success />
        ) : (
          <FormLine line="49" description="Amount you owe" amount={form.line_49} format={formatCurrency} highlight warning />
        )}
      </div>
    </div>
  );
}

// Reusable Form Line Component
function FormLine({
  line,
  description,
  amount,
  format,
  highlight = false,
  success = false,
  warning = false,
}: {
  line: string;
  description: string;
  amount: number;
  format: (n: number) => string;
  highlight?: boolean;
  success?: boolean;
  warning?: boolean;
}) {
  const className = `${styles.formLine} ${highlight ? styles.highlight : ''} ${success ? styles.success : ''} ${warning ? styles.warning : ''}`;

  return (
    <div className={className}>
      <span className={styles.lineNumber}>{line}</span>
      <span className={styles.lineDescription}>{description}</span>
      <span className={styles.lineAmount}>{format(amount)}</span>
    </div>
  );
}
