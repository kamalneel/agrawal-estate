import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock,
  Copy,
  AlertTriangle,
  Info,
  FileText,
  Phone,
  Mail,
  Globe,
  RotateCcw,
} from 'lucide-react'
import styles from './CompanyDissolution.module.css'
import clsx from 'clsx'

const STORAGE_KEY = 'fanbase-dissolution-progress'

// ---------- Types ----------
interface Contact {
  label: string
  type: 'phone' | 'email' | 'url'
  value: string
}

interface DissolutionStep {
  id: string
  title: string
  deadline?: string
  deadlineUrgency?: 'urgent' | 'normal' | 'far'
  instructions: string[]
  contacts?: Contact[]
  letterTemplate?: { title: string; body: string }
  tip?: string
  warning?: string
}

interface Phase {
  number: number
  title: string
  steps: DissolutionStep[]
}

// ---------- Step Data ----------
const PHASES: Phase[] = [
  {
    number: 1,
    title: 'Urgent — Delaware Franchise Tax',
    steps: [
      {
        id: 'pay-de-franchise-tax',
        title: 'Pay 2025 Delaware Franchise Tax ($450)',
        deadline: 'March 1, 2026',
        deadlineUrgency: 'urgent',
        instructions: [
          'Go to the Delaware Division of Corporations website and look up FanbaseAI, Inc.',
          'File the Annual Report and pay the franchise tax. For a company with no par value shares, the minimum tax is $450 + $50 filing fee = $500 total.',
          'Pay via credit card or ACH from the Mercury business checking account.',
          'Download and save the receipt/confirmation as PDF for records.',
        ],
        contacts: [
          { label: 'DE Div. of Corporations', type: 'url', value: 'https://icis.corp.delaware.gov/ecorp/logintax.aspx' },
          { label: 'Phone', type: 'phone', value: '(302) 739-3073' },
        ],
        warning: 'This must be paid BEFORE filing the Certificate of Dissolution. Delaware will reject the dissolution filing if taxes are unpaid. The deadline is March 1, 2026 — late fees apply after this date.',
      },
    ],
  },
  {
    number: 2,
    title: 'Corporate Resolution',
    steps: [
      {
        id: 'board-resolution',
        title: 'Draft & Sign Board Resolution for Dissolution',
        deadline: 'After Phase 1',
        deadlineUrgency: 'normal',
        instructions: [
          'The Board of Directors must formally resolve to dissolve the corporation.',
          'Since you are the sole director, sign the Board Resolution (template below).',
          'Print, sign, and date the resolution. Keep the original with corporate records.',
          'This resolution authorizes filing the Certificate of Dissolution with Delaware.',
        ],
        letterTemplate: {
          title: 'Board Resolution for Dissolution',
          body: `UNANIMOUS WRITTEN CONSENT OF THE BOARD OF DIRECTORS
OF FANBASEAI, INC.
A Delaware Corporation

The undersigned, being all of the members of the Board of Directors of FanbaseAI, Inc., a Delaware corporation (the "Corporation"), hereby consent to and adopt the following resolutions without a meeting, pursuant to Section 141(f) of the Delaware General Corporation Law:

RESOLUTION TO DISSOLVE

WHEREAS, the Board of Directors has determined that it is advisable and in the best interests of the Corporation and its stockholders to dissolve the Corporation; and

WHEREAS, the Corporation has ceased all business operations and has no remaining assets or liabilities of material value;

NOW, THEREFORE, BE IT RESOLVED, that the dissolution of the Corporation is hereby approved and authorized;

RESOLVED FURTHER, that the officers of the Corporation are hereby authorized and directed to file a Certificate of Dissolution with the Secretary of State of the State of Delaware;

RESOLVED FURTHER, that the officers are authorized to file IRS Form 966 (Corporate Dissolution or Liquidation) with the Internal Revenue Service within 30 days of the adoption of this resolution;

RESOLVED FURTHER, that the officers are authorized to file all final federal and state tax returns, and to take all such actions as may be necessary or appropriate to wind up the affairs of the Corporation;

RESOLVED FURTHER, that the officers are authorized and directed to execute and deliver any and all documents, instruments, and certificates, and to take all such further actions as may be necessary or appropriate to carry out the intent and purposes of the foregoing resolutions.

IN WITNESS WHEREOF, the undersigned has executed this Written Consent as of [DATE].

_________________________________
Neel Agrawal
Sole Director`,
        },
      },
      {
        id: 'shareholder-consent',
        title: 'Draft & Sign Unanimous Shareholder Written Consent',
        deadline: 'Same day as Board Resolution',
        deadlineUrgency: 'normal',
        instructions: [
          'Under Delaware law (DGCL §275), the dissolution must be approved by stockholders holding a majority of outstanding shares.',
          'Since Neel Agrawal holds 7,000,000 shares (70%) and Chetan Rao holds 3,000,000 shares (30%), both should sign the Shareholder Consent.',
          'If Chetan is unavailable, Neel\'s 70% alone constitutes a majority and is sufficient.',
          'Print, sign, date, and retain with corporate records.',
        ],
        letterTemplate: {
          title: 'Unanimous Shareholder Written Consent',
          body: `UNANIMOUS WRITTEN CONSENT OF STOCKHOLDERS
OF FANBASEAI, INC.
A Delaware Corporation

The undersigned, being all of the stockholders of FanbaseAI, Inc., a Delaware corporation (the "Corporation"), holding all of the issued and outstanding shares of capital stock of the Corporation, hereby consent to and adopt the following resolutions without a meeting, pursuant to Section 228 of the Delaware General Corporation Law:

WHEREAS, the Board of Directors of the Corporation has adopted a resolution recommending the dissolution of the Corporation; and

WHEREAS, the undersigned stockholders, holding 100% of the outstanding shares, wish to approve such dissolution;

NOW, THEREFORE, BE IT RESOLVED, that the voluntary dissolution of the Corporation is hereby approved;

RESOLVED FURTHER, that the officers of the Corporation are authorized to take all actions necessary to effectuate the dissolution, including the filing of a Certificate of Dissolution with the Secretary of State of the State of Delaware.

Stockholder Information:
- Total Authorized Shares: 10,000,000 Common Stock
- Total Outstanding Shares: 10,000,000 Common Stock

IN WITNESS WHEREOF, the undersigned have executed this Written Consent as of [DATE].

_________________________________
Neel Agrawal
7,000,000 shares (70%)

_________________________________
Chetan Rao
3,000,000 shares (30%)`,
        },
      },
    ],
  },
  {
    number: 3,
    title: 'State & Federal Filing',
    steps: [
      {
        id: 'confirm-de-tax-balance',
        title: 'Confirm $0 Tax Balance with Delaware',
        deadline: 'Before filing dissolution',
        deadlineUrgency: 'normal',
        instructions: [
          'Call or check online to confirm that all franchise taxes are fully paid and there is no outstanding balance.',
          'Request a Tax Clearance Certificate if available — this proves good standing for the dissolution filing.',
          'Delaware will reject the Certificate of Dissolution if any taxes are owed.',
        ],
        contacts: [
          { label: 'DE Div. of Corporations', type: 'phone', value: '(302) 739-3073' },
          { label: 'Online portal', type: 'url', value: 'https://icis.corp.delaware.gov/ecorp/logintax.aspx' },
        ],
      },
      {
        id: 'file-certificate-of-dissolution',
        title: 'File Certificate of Dissolution with Delaware',
        deadline: 'After tax clearance',
        deadlineUrgency: 'normal',
        instructions: [
          'File a Short Form Certificate of Dissolution if the corporation has no assets and has stopped doing business. Otherwise, use the standard Certificate of Dissolution.',
          'Filing can be done online through the Delaware Division of Corporations website, or by mail.',
          'Filing fee: $204 for online filing. Expedited processing available for additional fees.',
          'After filing, you will receive a stamped copy of the Certificate of Dissolution. Save this — it is the official proof of dissolution.',
        ],
        contacts: [
          { label: 'DE Filing Portal', type: 'url', value: 'https://corp.delaware.gov/howtoform/' },
          { label: 'Phone', type: 'phone', value: '(302) 739-3073' },
        ],
        tip: 'The Short Form dissolution (§274) is faster and simpler. It requires that the corporation has not commenced business, has no assets, and that all franchise taxes are paid. If any capital was ever received or business transacted, use the standard §275 dissolution.',
      },
      {
        id: 'file-irs-form-966',
        title: 'File IRS Form 966 (Corporate Dissolution)',
        deadline: 'Within 30 days of resolution',
        deadlineUrgency: 'normal',
        instructions: [
          'Download IRS Form 966 from the IRS website.',
          'Fill in: Corporation name (FanbaseAI, Inc.), EIN, date of adoption of resolution, and Internal Revenue District where last return was filed.',
          'Attach a certified copy of the Board Resolution authorizing the dissolution.',
          'Mail the completed form to the IRS. There is no online filing option for Form 966.',
          'Keep a copy of the mailed form with proof of mailing (certified mail recommended).',
        ],
        contacts: [
          { label: 'IRS Form 966', type: 'url', value: 'https://www.irs.gov/forms-pubs/about-form-966' },
        ],
        tip: 'Form 966 is informational only — it notifies the IRS that the corporation is dissolving. Failing to file it does not prevent dissolution but may trigger IRS inquiries.',
      },
    ],
  },
  {
    number: 4,
    title: 'Final Tax Returns',
    steps: [
      {
        id: 'file-2025-form-1120',
        title: 'File 2025 Federal Form 1120 (Corporate Tax Return)',
        deadline: 'March 15, 2026 (or extension)',
        deadlineUrgency: 'normal',
        instructions: [
          'This is the regular annual return for the 2025 tax year.',
          'If the corporation had no income, expenses, or activity, file a zero-income return.',
          'Check the box on page 1 indicating this is NOT the final return (2026 will be the final year).',
          'File electronically through your tax preparer or use IRS e-file.',
          'If you need more time, file Form 7004 for an automatic 6-month extension (by March 15).',
        ],
        tip: 'Even if the corporation had no activity in 2025, you must still file Form 1120 to maintain compliance. Failing to file can result in IRS penalties and complicate the dissolution.',
      },
      {
        id: 'file-final-2026-form-1120',
        title: 'File Final 2026 Form 1120 (Short-Year Return)',
        deadline: '3 months after dissolution date',
        deadlineUrgency: 'far',
        instructions: [
          'This is the FINAL tax return. Check the "Final return" box on page 1 of Form 1120.',
          'The tax year runs from January 1, 2026 to the date of dissolution.',
          'Report any final income, deductions, or distributions.',
          'Attach a statement that the corporation has dissolved and this is its final return.',
          'File within 3 months and 15 days after the end of the short tax year (i.e., the dissolution date).',
        ],
      },
    ],
  },
  {
    number: 5,
    title: 'Cleanup & Account Closures',
    steps: [
      {
        id: 'revoke-form-8821',
        title: 'Revoke IRS Form 8821 (Tax Information Authorization)',
        deadline: 'After final return filed',
        deadlineUrgency: 'far',
        instructions: [
          'If you previously filed Form 8821 authorizing a third party (e.g., accountant) to access FanbaseAI\'s tax records, revoke it.',
          'Send a revocation letter (template below) to the IRS.',
          'Mail to the IRS office where the original Form 8821 was filed.',
        ],
        letterTemplate: {
          title: 'Form 8821 Revocation Letter',
          body: `[DATE]

Internal Revenue Service
Centralized Authorization File (CAF) Unit
P.O. Box 33373
Detroit, MI 48232

Re: Revocation of Form 8821 — Tax Information Authorization
Taxpayer: FanbaseAI, Inc.
EIN: [EIN]

Dear Sir/Madam:

I hereby revoke all prior Forms 8821, Tax Information Authorization, filed on behalf of FanbaseAI, Inc. (EIN: [EIN]).

This revocation is effective immediately and applies to all previously designated appointees.

The corporation has been dissolved and all final tax returns have been filed.

Sincerely,

_________________________________
Neel Agrawal
President & Sole Director
FanbaseAI, Inc.`,
        },
      },
      {
        id: 'cancel-ein',
        title: 'Close/Cancel the EIN with the IRS',
        deadline: 'After final return filed',
        deadlineUrgency: 'far',
        instructions: [
          'Send a letter to the IRS requesting that the EIN account be closed (template below).',
          'Include the legal name of the entity, EIN, and reason for closing.',
          'The IRS does not technically "cancel" an EIN (it remains assigned forever), but they will close the business account associated with it.',
        ],
        contacts: [
          { label: 'IRS Business Closures', type: 'url', value: 'https://www.irs.gov/businesses/small-businesses-self-employed/closing-a-business' },
        ],
        letterTemplate: {
          title: 'EIN Cancellation Letter',
          body: `[DATE]

Internal Revenue Service
Cincinnati, OH 45999

Re: Request to Close EIN Account
Entity: FanbaseAI, Inc.
EIN: [EIN]

Dear Sir/Madam:

I am writing to request that you close the Employer Identification Number (EIN) account for FanbaseAI, Inc. (EIN: [EIN]).

The corporation was incorporated in the State of Delaware and has been formally dissolved by filing a Certificate of Dissolution with the Delaware Secretary of State.

All final federal income tax returns have been filed, and the corporation has no remaining assets, liabilities, or ongoing business activities.

Please close this EIN account and update your records accordingly.

Sincerely,

_________________________________
Neel Agrawal
President & Sole Director
FanbaseAI, Inc.

Enclosure: Copy of Certificate of Dissolution`,
        },
      },
      {
        id: 'cancel-registered-agent',
        title: 'Cancel Delaware Registered Agent Service',
        deadline: 'After dissolution filed',
        deadlineUrgency: 'far',
        instructions: [
          'Contact your registered agent service to cancel the service agreement.',
          'Provide them with a copy of the Certificate of Dissolution.',
          'Confirm in writing that the service is terminated so you are not charged for the next renewal period.',
          'Common registered agent services: Harvard Business Services, Northwest Registered Agent, Incorp.',
        ],
        tip: 'Most registered agent services charge annually. Cancel promptly after dissolution to avoid the next billing cycle.',
      },
      {
        id: 'close-mercury-account',
        title: 'Close Mercury Business Checking Account',
        deadline: 'After all payments clear',
        deadlineUrgency: 'far',
        instructions: [
          'Ensure all outstanding payments and checks have cleared.',
          'Transfer any remaining balance to your personal account.',
          'Contact Mercury support to close the business account.',
          'Download all bank statements for the full operating period before closing — you will need these for tax records.',
        ],
        contacts: [
          { label: 'Mercury Support', type: 'url', value: 'https://mercury.com' },
          { label: 'Email', type: 'email', value: 'support@mercury.com' },
        ],
      },
      {
        id: 'retain-records',
        title: 'Organize & Retain Corporate Records (7 years)',
        deadline: 'Before Feb 2027',
        deadlineUrgency: 'far',
        instructions: [
          'Create a permanent archive folder with all corporate documents.',
          'Must retain for at least 7 years: all tax returns (1120), Certificate of Incorporation, Certificate of Dissolution, Board Resolutions, Shareholder Consents, bank statements, and any contracts.',
          'Store digitally (cloud backup) and keep one physical copy.',
          'Label the archive clearly: "FanbaseAI, Inc. — Corporate Records — Retain until [7 years from dissolution]".',
        ],
      },
    ],
  },
  {
    number: 6,
    title: 'Tax Optimization — Capital Loss',
    steps: [
      {
        id: 'download-icici-statements',
        title: 'Download ICICI Bank Wire Transfer Statements',
        deadline: 'April 2027',
        deadlineUrgency: 'far',
        instructions: [
          'Log in to ICICI Bank and download statements showing the wire transfers made as capital contributions to FanbaseAI.',
          'These statements establish the cost basis (amount invested) for the capital loss deduction.',
          'Save as PDF and include in the corporate records archive.',
        ],
      },
      {
        id: 'calculate-basis',
        title: 'Calculate Cost Basis for Section 1244 Loss',
        deadline: 'April 2027',
        deadlineUrgency: 'far',
        instructions: [
          'Total capital invested in FanbaseAI determines the cost basis.',
          'Under Section 1244, up to $50,000 ($100,000 if married filing jointly) of losses on small business stock can be deducted as an ordinary loss (not capital loss).',
          'This is more valuable than a capital loss because ordinary losses offset income at your marginal tax rate.',
          'Verify: total capital contributed, number of shares received, and that the corporation qualifies (total capitalization ≤ $1 million at time of stock issuance).',
        ],
        tip: 'Section 1244 ordinary loss treatment is extremely valuable. A $50,000 ordinary loss at a 37% marginal rate saves $18,500 in taxes, vs. a $50,000 capital loss which may only offset $3,000/year of ordinary income.',
      },
      {
        id: 'report-loss-on-1040',
        title: 'Report Loss on Personal 1040 Tax Return',
        deadline: 'April 2027 (for 2026 tax year)',
        deadlineUrgency: 'far',
        instructions: [
          'Report the Section 1244 ordinary loss on Form 4797 (Sales of Business Property), Part II.',
          'If the loss exceeds the Section 1244 limit, the excess is reported as a capital loss on Schedule D.',
          'Capital losses exceeding capital gains can offset up to $3,000 of ordinary income per year, with the remainder carried forward.',
          'Coordinate with your tax preparer to maximize the deduction in the 2026 tax year.',
        ],
      },
    ],
  },
]

const ALL_STEP_IDS = PHASES.flatMap((p) => p.steps.map((s) => s.id))

// ---------- Helpers ----------
function loadProgress(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const arr = JSON.parse(raw) as string[]
    return new Set(arr.filter((id) => ALL_STEP_IDS.includes(id)))
  } catch {
    return new Set()
  }
}

function saveProgress(completed: Set<string>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...completed]))
}

function findFirstIncompleteId(completed: Set<string>): string | null {
  for (const phase of PHASES) {
    for (const step of phase.steps) {
      if (!completed.has(step.id)) return step.id
    }
  }
  return null
}

// ---------- Components ----------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      className={clsx(styles.copyButton, copied && styles.copySuccess)}
      onClick={handleCopy}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function ContactIcon({ type }: { type: Contact['type'] }) {
  switch (type) {
    case 'phone': return <Phone size={14} />
    case 'email': return <Mail size={14} />
    case 'url': return <Globe size={14} />
  }
}

function contactHref(contact: Contact): string {
  switch (contact.type) {
    case 'phone': return `tel:${contact.value}`
    case 'email': return `mailto:${contact.value}`
    case 'url': return contact.value
  }
}

function StepCard({
  step,
  isComplete,
  isCurrent,
  isExpanded,
  onToggle,
  onMarkComplete,
  onUndo,
}: {
  step: DissolutionStep
  isComplete: boolean
  isCurrent: boolean
  isExpanded: boolean
  onToggle: () => void
  onMarkComplete: () => void
  onUndo: () => void
}) {
  return (
    <div
      className={clsx(
        styles.stepCard,
        isComplete && styles.stepCardComplete,
        isCurrent && !isComplete && step.deadlineUrgency === 'urgent' && styles.stepCardUrgent,
      )}
    >
      {/* Header */}
      <button className={styles.stepHeader} onClick={onToggle}>
        <div
          className={clsx(
            styles.statusIcon,
            isComplete ? styles.statusComplete : isCurrent ? styles.statusCurrent : styles.statusPending,
          )}
        >
          {isComplete ? <Check size={14} /> : isCurrent ? <Clock size={12} /> : <span />}
        </div>

        <span className={clsx(styles.stepTitle, isComplete && styles.stepTitleComplete)}>
          {step.title}
        </span>

        {step.deadline && (
          <span
            className={clsx(
              styles.deadlineBadge,
              step.deadlineUrgency === 'urgent'
                ? styles.deadlineUrgent
                : step.deadlineUrgency === 'normal'
                  ? styles.deadlineNormal
                  : styles.deadlineFar,
            )}
          >
            <Clock size={11} />
            {step.deadline}
          </span>
        )}

        <ChevronRight
          size={16}
          className={clsx(styles.chevron, isExpanded && styles.chevronOpen)}
        />
      </button>

      {/* Body */}
      {isExpanded && (
        <div className={styles.stepBody}>
          {/* Instructions */}
          <div className={styles.instructions}>
            {step.instructions.map((text, i) => (
              <div key={i} className={styles.instructionItem}>
                <span className={styles.instructionNumber}>{i + 1}</span>
                <span
                  className={styles.instructionText}
                  dangerouslySetInnerHTML={{ __html: text }}
                />
              </div>
            ))}
          </div>

          {/* Contacts */}
          {step.contacts && step.contacts.length > 0 && (
            <div className={styles.contacts}>
              <span className={styles.contactsLabel}>Contacts & Links</span>
              {step.contacts.map((c, i) => (
                <div key={i} className={styles.contactItem}>
                  <ContactIcon type={c.type} />
                  <span>{c.label}:</span>
                  <a href={contactHref(c)} target="_blank" rel="noopener noreferrer">
                    {c.value}
                  </a>
                </div>
              ))}
            </div>
          )}

          {/* Warning */}
          {step.warning && (
            <div className={styles.warningBox}>
              <AlertTriangle size={14} />
              <span>{step.warning}</span>
            </div>
          )}

          {/* Tip */}
          {step.tip && (
            <div className={styles.tipBox}>
              <Info size={14} />
              <span>{step.tip}</span>
            </div>
          )}

          {/* Letter Template */}
          {step.letterTemplate && (
            <div className={styles.letterSection}>
              <div className={styles.letterLabel}>
                <FileText size={14} />
                {step.letterTemplate.title}
              </div>
              <div className={styles.letterContainer}>
                <CopyButton text={step.letterTemplate.body} />
                <div className={styles.letterContent}>
                  {step.letterTemplate.body}
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className={styles.stepActions}>
            {isComplete ? (
              <button className={styles.undoButton} onClick={onUndo}>
                <RotateCcw size={14} />
                Mark Incomplete
              </button>
            ) : (
              <button className={styles.markCompleteButton} onClick={onMarkComplete}>
                <Check size={14} />
                Mark Complete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- Main ----------
export default function CompanyDissolution() {
  const navigate = useNavigate()
  const [completed, setCompleted] = useState<Set<string>>(() => loadProgress())
  const [expandedId, setExpandedId] = useState<string | null>(() => findFirstIncompleteId(loadProgress()))

  // Persist on change
  useEffect(() => {
    saveProgress(completed)
  }, [completed])

  const totalSteps = ALL_STEP_IDS.length
  const completedCount = completed.size
  const progressPct = totalSteps > 0 ? (completedCount / totalSteps) * 100 : 0

  const firstIncompleteId = findFirstIncompleteId(completed)

  const handleToggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }, [])

  const handleMarkComplete = useCallback((id: string) => {
    setCompleted((prev) => {
      const next = new Set(prev)
      next.add(id)
      // Auto-expand next incomplete step
      const nextIncomplete = findFirstIncompleteId(next)
      if (nextIncomplete) {
        setExpandedId(nextIncomplete)
      }
      return next
    })
  }, [])

  const handleUndo = useCallback((id: string) => {
    setCompleted((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  return (
    <div className={styles.page}>
      {/* Back */}
      <button className={styles.backButton} onClick={() => navigate('/equity')}>
        <ArrowLeft size={20} />
        Back to Equity
      </button>

      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroLabel}>Dissolution Workflow</div>
          <h1 className={styles.heroTitle}>FanbaseAI, Inc.</h1>
          <div className={styles.progressWrapper}>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
            </div>
            <span className={styles.progressText}>
              {completedCount}/{totalSteps} steps
            </span>
          </div>
        </div>
      </section>

      {/* Phases */}
      {PHASES.map((phase) => {
        const phaseCompletedCount = phase.steps.filter((s) => completed.has(s.id)).length
        return (
          <div key={phase.number} className={styles.phase}>
            <div className={styles.phaseHeader}>
              <span className={styles.phaseNumber}>{phase.number}</span>
              <span className={styles.phaseTitle}>{phase.title}</span>
              <span className={styles.phaseCount}>
                {phaseCompletedCount}/{phase.steps.length}
              </span>
            </div>
            <div className={styles.timeline}>
              {phase.steps.map((step) => {
                const isComplete = completed.has(step.id)
                const isCurrent = step.id === firstIncompleteId
                return (
                  <StepCard
                    key={step.id}
                    step={step}
                    isComplete={isComplete}
                    isCurrent={isCurrent}
                    isExpanded={expandedId === step.id}
                    onToggle={() => handleToggle(step.id)}
                    onMarkComplete={() => handleMarkComplete(step.id)}
                    onUndo={() => handleUndo(step.id)}
                  />
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
