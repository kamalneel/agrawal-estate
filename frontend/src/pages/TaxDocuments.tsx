import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  RefreshCw,
  Upload,
  FileText,
  Download,
  Trash2,
  CheckCircle2,
  Clock,
  AlertCircle,
  FolderOpen,
  File,
  X,
  Edit3,
  ExternalLink
} from 'lucide-react';
import styles from './TaxDocuments.module.css';
import { getAuthHeaders } from '../contexts/AuthContext';

interface TaxDocument {
  id: number;
  file_name: string;
  institution_name: string | null;
  institution_ein: string | null;
  file_size: number | null;
  mime_type: string | null;
  upload_date: string | null;
  document_date: string | null;
  status: string;
  notes: string | null;
}

interface DocumentsByType {
  [key: string]: TaxDocument[];
}

interface DocumentStats {
  total: number;
  by_type: { [key: string]: number };
  by_status: { [key: string]: number };
}

interface DocumentsResponse {
  tax_year: number;
  documents: DocumentsByType;
  stats: DocumentStats;
}

interface DocumentField {
  field: string;
  form_line: string;
  label: string;
  required: boolean;
  value: number | null;
}

interface ProcessingDoc {
  id: number;
  file_name: string;
  document_type: string;
  institution_name: string | null;
  status: string;
}

const DOCUMENT_TYPES = [
  { value: '1099-INT', label: '1099-INT (Interest Income)' },
  { value: '1099-DIV', label: '1099-DIV (Dividend Income)' },
  { value: '1099-B', label: '1099-B (Brokerage Transactions)' },
  { value: '1099-R', label: '1099-R (Retirement Distributions)' },
  { value: '1099-MISC', label: '1099-MISC (Miscellaneous Income)' },
  { value: '1099-NEC', label: '1099-NEC (Non-Employee Compensation)' },
  { value: '1099-K', label: '1099-K (Payment Card Transactions)' },
  { value: 'W-2', label: 'W-2 (Wages and Salary)' },
  { value: '1098', label: '1098 (Mortgage Interest)' },
  { value: 'K-1', label: 'K-1 (Partnership Income)' },
  { value: 'PROPERTY-TAX', label: 'Property Tax Bill' },
  { value: 'CHARITABLE', label: 'Charitable Donation Receipt' },
  { value: 'OTHER', label: 'Other Document' },
];

export default function TaxDocuments() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const year = parseInt(searchParams.get('year') || '2025', 10);

  const [documents, setDocuments] = useState<DocumentsByType>({});
  const [stats, setStats] = useState<DocumentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadDocType, setUploadDocType] = useState('1099-INT');
  const [uploadInstitution, setUploadInstitution] = useState('');
  const [uploadNotes, setUploadNotes] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Process document state
  const [showProcess, setShowProcess] = useState(false);
  const [processingDoc, setProcessingDoc] = useState<ProcessingDoc | null>(null);
  const [processFields, setProcessFields] = useState<DocumentField[]>([]);
  const [fieldValues, setFieldValues] = useState<{ [key: string]: string }>({});
  const [processing, setProcessing] = useState(false);
  const [processError, setProcessError] = useState<string | null>(null);
  const [loadingFields, setLoadingFields] = useState(false);

  // Drag and drop state
  const [isDragging, setIsDragging] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/tax/documents/${year}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch documents');
      }

      const data: DocumentsResponse = await response.json();
      setDocuments(data.documents);
      setStats(data.stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
      setShowUpload(true);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setUploadFile(file);
      setShowUpload(true);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleUpload = async () => {
    if (!uploadFile) return;

    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('year', year.toString());
    formData.append('document_type', uploadDocType);
    formData.append('file', uploadFile);
    if (uploadInstitution) {
      formData.append('institution_name', uploadInstitution);
    }
    if (uploadNotes) {
      formData.append('notes', uploadNotes);
    }

    try {
      const response = await fetch('/api/v1/tax/documents/upload', {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      // Reset form and refresh
      setShowUpload(false);
      setUploadFile(null);
      setUploadInstitution('');
      setUploadNotes('');
      fetchDocuments();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (docId: number, fileName: string) => {
    try {
      const response = await fetch(`/api/v1/tax/documents/${year}/${docId}/download`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Download failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
    } catch (err) {
      console.error('Download error:', err);
    }
  };

  const handleDelete = async (docId: number, fileName: string) => {
    if (!confirm(`Delete "${fileName}"?`)) return;

    try {
      const response = await fetch(`/api/v1/tax/documents/${year}/${docId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Delete failed');
      }

      fetchDocuments();
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const handleOpenProcess = async (doc: TaxDocument, docType: string) => {
    setProcessingDoc({
      id: doc.id,
      file_name: doc.file_name,
      document_type: docType,
      institution_name: doc.institution_name,
      status: doc.status
    });
    setShowProcess(true);
    setLoadingFields(true);
    setProcessError(null);
    setFieldValues({});

    try {
      const response = await fetch(`/api/v1/tax/documents/${year}/${doc.id}/fields`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Failed to load document fields');
      }

      const data = await response.json();
      setProcessFields(data.fields);

      // Pre-populate field values
      const values: { [key: string]: string } = {};
      data.fields.forEach((field: DocumentField) => {
        values[field.form_line] = field.value !== null ? field.value.toString() : '';
      });
      setFieldValues(values);
    } catch (err) {
      setProcessError(err instanceof Error ? err.message : 'Failed to load fields');
    } finally {
      setLoadingFields(false);
    }
  };

  const handleProcessSubmit = async () => {
    if (!processingDoc) return;

    setProcessing(true);
    setProcessError(null);

    // Build values array from field values
    const values = processFields
      .filter(field => fieldValues[field.form_line] && fieldValues[field.form_line] !== '')
      .map(field => ({
        form_line: field.form_line,
        amount: parseFloat(fieldValues[field.form_line]),
        description: `${field.label}${processingDoc.institution_name ? ` - ${processingDoc.institution_name}` : ''}`
      }));

    try {
      const response = await fetch(`/api/v1/tax/documents/${year}/${processingDoc.id}/process`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ values }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Processing failed');
      }

      // Close modal and refresh
      setShowProcess(false);
      setProcessingDoc(null);
      setProcessFields([]);
      setFieldValues({});
      fetchDocuments();
    } catch (err) {
      setProcessError(err instanceof Error ? err.message : 'Processing failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleVerify = async (docId: number) => {
    try {
      const response = await fetch(`/api/v1/tax/documents/${year}/${docId}/verify`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error('Verification failed');
      }

      fetchDocuments();
    } catch (err) {
      console.error('Verify error:', err);
    }
  };

  const formatFileSize = (bytes: number | null) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'verified':
        return <CheckCircle2 size={14} className={styles.statusVerified} />;
      case 'processed':
        return <Clock size={14} className={styles.statusProcessed} />;
      default:
        return <AlertCircle size={14} className={styles.statusUploaded} />;
    }
  };

  const getDocTypeLabel = (type: string) => {
    const docType = DOCUMENT_TYPES.find(d => d.value === type);
    return docType?.label || type;
  };

  // Get documents needing review (uploaded but not processed)
  const needsReviewDocs: { doc: TaxDocument; docType: string }[] = [];
  Object.entries(documents).forEach(([docType, docs]) => {
    docs.filter(d => d.status === 'uploaded').forEach(doc => {
      needsReviewDocs.push({ doc, docType });
    });
  });

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <RefreshCw size={40} className={styles.spinner} />
          <p>Loading documents...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <h3>Error Loading Documents</h3>
          <p>{error}</p>
          <button className={styles.refreshButton} onClick={fetchDocuments}>
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
          <h1>{year} Tax Documents</h1>
          <p>Upload and manage your tax documents for {year}</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.refreshBtn} onClick={fetchDocuments}>
            <RefreshCw size={18} />
          </button>
          <button
            className={styles.actualFileBtn}
            onClick={() => navigate(`/tax/actual?year=${year}`)}
          >
            <FileText size={18} />
            View Actual Tax File
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <span className={styles.statValue}>{stats.total}</span>
            <span className={styles.statLabel}>Total Documents</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue}>{Object.keys(stats.by_type).length}</span>
            <span className={styles.statLabel}>Document Types</span>
          </div>
          <div className={styles.statCard}>
            <span className={`${styles.statValue} ${styles.verified}`}>{stats.by_status.verified || 0}</span>
            <span className={styles.statLabel}>Verified</span>
          </div>
          <div className={styles.statCard}>
            <span className={`${styles.statValue} ${styles.pending}`}>{stats.by_status.uploaded || 0}</span>
            <span className={styles.statLabel}>Needs Review</span>
          </div>
        </div>
      )}

      {/* Upload Area */}
      <div
        className={`${styles.uploadArea} ${isDragging ? styles.dragging : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <Upload size={32} />
        <p>Drag and drop a document here, or</p>
        <label className={styles.uploadButton}>
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.doc,.docx"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          Browse Files
        </label>
        <span className={styles.uploadHint}>Supports PDF, images, and documents</span>
      </div>

      {/* Needs Review Section */}
      {needsReviewDocs.length > 0 && (
        <div className={styles.needsReviewSection}>
          <h2>
            <AlertCircle size={20} />
            Documents Needing Review ({needsReviewDocs.length})
          </h2>
          <p className={styles.needsReviewHint}>
            These documents have been uploaded but need to be processed. Click "Process" to enter the values from each document.
          </p>
          <div className={styles.needsReviewList}>
            {needsReviewDocs.map(({ doc, docType }) => (
              <div key={doc.id} className={styles.needsReviewItem}>
                <div className={styles.needsReviewInfo}>
                  <File size={20} />
                  <div>
                    <span className={styles.needsReviewName}>{doc.file_name}</span>
                    <span className={styles.needsReviewType}>{getDocTypeLabel(docType)}</span>
                    {doc.institution_name && (
                      <span className={styles.needsReviewInstitution}>{doc.institution_name}</span>
                    )}
                  </div>
                </div>
                <div className={styles.needsReviewActions}>
                  <button
                    className={styles.downloadBtn}
                    onClick={() => handleDownload(doc.id, doc.file_name)}
                    title="Download to view"
                  >
                    <ExternalLink size={16} />
                    View
                  </button>
                  <button
                    className={styles.processBtn}
                    onClick={() => handleOpenProcess(doc, docType)}
                  >
                    <Edit3 size={16} />
                    Process
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload Modal */}
      {showUpload && (
        <div className={styles.modalOverlay} onClick={() => setShowUpload(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>Upload Document</h3>
              <button className={styles.modalClose} onClick={() => setShowUpload(false)}>
                <X size={20} />
              </button>
            </div>

            <div className={styles.modalBody}>
              {uploadFile && (
                <div className={styles.selectedFile}>
                  <File size={24} />
                  <div>
                    <span className={styles.fileName}>{uploadFile.name}</span>
                    <span className={styles.fileSize}>{formatFileSize(uploadFile.size)}</span>
                  </div>
                </div>
              )}

              <div className={styles.formGroup}>
                <label>Document Type *</label>
                <select
                  value={uploadDocType}
                  onChange={e => setUploadDocType(e.target.value)}
                >
                  {DOCUMENT_TYPES.map(type => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className={styles.formGroup}>
                <label>Institution Name</label>
                <input
                  type="text"
                  value={uploadInstitution}
                  onChange={e => setUploadInstitution(e.target.value)}
                  placeholder="e.g., Chase Bank, Fidelity"
                />
              </div>

              <div className={styles.formGroup}>
                <label>Notes</label>
                <textarea
                  value={uploadNotes}
                  onChange={e => setUploadNotes(e.target.value)}
                  placeholder="Optional notes about this document"
                  rows={3}
                />
              </div>

              {uploadError && (
                <div className={styles.uploadErrorMsg}>
                  <AlertCircle size={16} />
                  {uploadError}
                </div>
              )}
            </div>

            <div className={styles.modalFooter}>
              <button
                className={styles.cancelButton}
                onClick={() => setShowUpload(false)}
                disabled={uploading}
              >
                Cancel
              </button>
              <button
                className={styles.submitButton}
                onClick={handleUpload}
                disabled={uploading || !uploadFile}
              >
                {uploading ? (
                  <>
                    <RefreshCw size={16} className={styles.spinner} />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload size={16} />
                    Upload
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Process Document Modal */}
      {showProcess && processingDoc && (
        <div className={styles.modalOverlay} onClick={() => setShowProcess(false)}>
          <div className={`${styles.modal} ${styles.processModal}`} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>Process Document</h3>
              <button className={styles.modalClose} onClick={() => setShowProcess(false)}>
                <X size={20} />
              </button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.processDocInfo}>
                <div className={styles.processDocHeader}>
                  <FileText size={24} />
                  <div>
                    <span className={styles.processDocName}>{processingDoc.file_name}</span>
                    <span className={styles.processDocType}>{getDocTypeLabel(processingDoc.document_type)}</span>
                    {processingDoc.institution_name && (
                      <span className={styles.processDocInstitution}>{processingDoc.institution_name}</span>
                    )}
                  </div>
                </div>
                <button
                  className={styles.viewDocBtn}
                  onClick={() => handleDownload(processingDoc.id, processingDoc.file_name)}
                >
                  <ExternalLink size={16} />
                  Open Document
                </button>
              </div>

              <div className={styles.processInstructions}>
                <p>Enter the values from the document below. Open the document in another window for reference.</p>
              </div>

              {loadingFields ? (
                <div className={styles.loadingFields}>
                  <RefreshCw size={24} className={styles.spinner} />
                  <span>Loading fields...</span>
                </div>
              ) : (
                <div className={styles.fieldsForm}>
                  {processFields.map(field => (
                    <div key={field.form_line} className={styles.fieldRow}>
                      <label>
                        {field.label}
                        {field.required && <span className={styles.required}>*</span>}
                        <span className={styles.formLine}>{field.form_line}</span>
                      </label>
                      <div className={styles.fieldInput}>
                        <span className={styles.currencySymbol}>$</span>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={fieldValues[field.form_line] || ''}
                          onChange={e => setFieldValues({
                            ...fieldValues,
                            [field.form_line]: e.target.value
                          })}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {processError && (
                <div className={styles.uploadErrorMsg}>
                  <AlertCircle size={16} />
                  {processError}
                </div>
              )}
            </div>

            <div className={styles.modalFooter}>
              <button
                className={styles.cancelButton}
                onClick={() => setShowProcess(false)}
                disabled={processing}
              >
                Cancel
              </button>
              <button
                className={styles.submitButton}
                onClick={handleProcessSubmit}
                disabled={processing || loadingFields}
              >
                {processing ? (
                  <>
                    <RefreshCw size={16} className={styles.spinner} />
                    Saving...
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} />
                    Save & Mark Processed
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Documents List */}
      <div className={styles.documentsSection}>
        <h2>All Documents</h2>

        {Object.keys(documents).length === 0 ? (
          <div className={styles.emptyState}>
            <FolderOpen size={48} />
            <h3>No Documents Yet</h3>
            <p>Upload your first tax document to get started.</p>
          </div>
        ) : (
          <div className={styles.documentGroups}>
            {Object.entries(documents).map(([docType, docs]) => (
              <div key={docType} className={styles.documentGroup}>
                <div className={styles.groupHeader}>
                  <FileText size={18} />
                  <span className={styles.groupTitle}>{getDocTypeLabel(docType)}</span>
                  <span className={styles.groupCount}>{docs.length}</span>
                </div>

                <div className={styles.documentList}>
                  {docs.map(doc => (
                    <div key={doc.id} className={styles.documentItem}>
                      <div className={styles.documentInfo}>
                        <File size={20} />
                        <div className={styles.documentDetails}>
                          <span className={styles.documentName}>{doc.file_name}</span>
                          {doc.institution_name && (
                            <span className={styles.documentInstitution}>
                              {doc.institution_name}
                            </span>
                          )}
                          <div className={styles.documentMeta}>
                            {getStatusIcon(doc.status)}
                            <span className={styles.documentStatus}>{doc.status}</span>
                            <span className={styles.documentSize}>
                              {formatFileSize(doc.file_size)}
                            </span>
                            {doc.upload_date && (
                              <span className={styles.documentDate}>
                                {new Date(doc.upload_date).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className={styles.documentActions}>
                        {doc.status === 'uploaded' && (
                          <button
                            className={`${styles.actionButton} ${styles.processButton}`}
                            onClick={() => handleOpenProcess(doc, docType)}
                            title="Process document"
                          >
                            <Edit3 size={16} />
                          </button>
                        )}
                        {doc.status === 'processed' && (
                          <button
                            className={`${styles.actionButton} ${styles.verifyButton}`}
                            onClick={() => handleVerify(doc.id)}
                            title="Mark as verified"
                          >
                            <CheckCircle2 size={16} />
                          </button>
                        )}
                        <button
                          className={styles.actionButton}
                          onClick={() => handleDownload(doc.id, doc.file_name)}
                          title="Download"
                        >
                          <Download size={16} />
                        </button>
                        <button
                          className={`${styles.actionButton} ${styles.deleteButton}`}
                          onClick={() => handleDelete(doc.id, doc.file_name)}
                          title="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
