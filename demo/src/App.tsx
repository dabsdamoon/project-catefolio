import { Fragment, useMemo, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const DATES_PER_PAGE = 6

type Summary = {
  total_income: number
  total_expenses: number
  net_savings: number
}

type Transaction = {
  date: string
  description: string
  amount: number
  category?: string
  categories?: string[]
  entity?: string
}

type UploadState = 'idle' | 'uploading' | 'processing' | 'success' | 'error'

function Spinner() {
  return (
    <div className="spinner" aria-label="Loading">
      <div className="spinner-ring"></div>
    </div>
  )
}

function App() {
  const [status, setStatus] = useState('Upload files to generate the template-formatted report.')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [templateBlob, setTemplateBlob] = useState<Blob | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [uploadProgress, setUploadProgress] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [page, setPage] = useState(0)
  const [categorize, setCategorize] = useState(false)
  const [wasCategorized, setWasCategorized] = useState(false)
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)

  const isUploading = uploadState === 'uploading' || uploadState === 'processing'

  const grouped = useMemo(() => {
    const bucket: Record<string, { credit: Transaction[]; debit: Transaction[] }> = {}
    transactions.forEach((tx) => {
      const date = tx.date || 'Unknown'
      bucket[date] ||= { credit: [], debit: [] }
      if (tx.amount >= 0) {
        bucket[date].credit.push(tx)
      } else {
        bucket[date].debit.push(tx)
      }
    })
    return bucket
  }, [transactions])

  const dates = useMemo(() => Object.keys(grouped).sort(), [grouped])

  const pageDates = useMemo(() => {
    const start = page * DATES_PER_PAGE
    return dates.slice(start, start + DATES_PER_PAGE)
  }, [dates, page])

  const pageStatus = useMemo(() => {
    if (!dates.length) return 'No dates loaded'
    const start = page * DATES_PER_PAGE + 1
    const end = Math.min(dates.length, (page + 1) * DATES_PER_PAGE)
    return `Showing ${start}-${end} of ${dates.length} dates`
  }, [dates, page])

  const buildFormData = (files: File[]) => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return formData
  }

  const formatCurrency = (value?: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value || 0)

  const handleUpload = async (files: File[]) => {
    if (!files.length) return

    // Reset state
    setUploadState('uploading')
    setErrorMessage('')
    setTemplateBlob(null)
    setSelectedTransaction(null)

    const fileNames = files.map((file) => file.name).join(', ')
    setUploadProgress(`Uploading ${files.length} file(s): ${fileNames}`)
    setStatus(`Uploading ${files.length} file(s)...`)

    try {
      // Step 1: Upload files
      setUploadProgress('Uploading files to server...')
      const uploadUrl = `${API_BASE}/upload?categorize=${categorize}`
      const uploadResponse = await fetch(uploadUrl, {
        method: 'POST',
        body: buildFormData(files),
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error(errorData.detail || `Upload failed (${uploadResponse.status})`)
      }

      const uploadData = await uploadResponse.json()

      // Step 2: Process results
      setUploadState('processing')
      setUploadProgress(categorize ? 'Processing transactions with AI...' : 'Processing transactions...')
      setStatus(categorize ? 'Processing... AI is categorizing your transactions.' : 'Processing transactions...')

      const resultResponse = await fetch(`${API_BASE}/result/${uploadData.job_id}`)
      if (!resultResponse.ok) {
        throw new Error(`Failed to fetch results (${resultResponse.status})`)
      }

      const resultData = await resultResponse.json()
      setSummary(resultData.summary)
      setTransactions(resultData.transactions)
      setWasCategorized(resultData.categorized || false)
      setPage(0)

      // Step 3: Generate template
      setUploadProgress('Generating Excel template...')
      const templateUrl = `${API_BASE}/template/convert?categorize=${categorize}`
      const templateResponse = await fetch(templateUrl, {
        method: 'POST',
        body: buildFormData(files),
      })

      if (!templateResponse.ok) {
        throw new Error(`Template export failed (${templateResponse.status})`)
      }

      const blob = await templateResponse.blob()
      setTemplateBlob(blob)

      // Success
      setUploadState('success')
      setUploadProgress('')
      const catMsg = categorize ? ' with AI categorization' : ''
      setStatus(`Successfully processed ${resultData.transactions.length} transactions${catMsg}. Template ready for download.`)

    } catch (error) {
      setUploadState('error')
      const message = error instanceof Error ? error.message : 'An unexpected error occurred'
      setErrorMessage(message)
      setStatus('Upload failed. Please check the error message below.')
      setUploadProgress('')
    }
  }

  const handleDownload = () => {
    if (!templateBlob) return
    const url = URL.createObjectURL(templateBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'account_template_output.xlsx'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const renderTable = (entriesByDate: Record<string, Transaction[]>, label: string) => {
    if (!pageDates.length) {
      return <div className="table-empty">No {label} entries yet.</div>
    }

    const maxRows = Math.max(...pageDates.map((date) => entriesByDate[date]?.length || 0))

    return (
      <table className="template-table">
        <thead>
          <tr>
            <th>Row</th>
            {pageDates.map((date) => (
              <th key={`${label}-${date}`} colSpan={wasCategorized ? 3 : 2}>
                {date}
              </th>
            ))}
          </tr>
          <tr>
            <th>Item</th>
            {pageDates.map((date) => (
              <Fragment key={`${label}-${date}-header`}>
                <th>Description</th>
                <th>Amount</th>
                {wasCategorized && <th>Category</th>}
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: maxRows }).map((_, rowIndex) => (
            <tr key={`${label}-row-${rowIndex}`}>
              <td>{rowIndex + 1}</td>
              {pageDates.map((date) => {
                const entry = entriesByDate[date]?.[rowIndex]
                return (
                  <Fragment key={`${label}-${date}-${rowIndex}`}>
                    <td
                      className={entry?.categories?.length ? 'clickable' : ''}
                      onClick={() => entry?.categories?.length && setSelectedTransaction(entry)}
                      title={entry?.categories?.length ? 'Click to view categories' : ''}
                    >
                      {entry?.description || ''}
                    </td>
                    <td className="amount">
                      {entry ? Math.abs(entry.amount).toLocaleString() : ''}
                    </td>
                    {wasCategorized && (
                      <td className="category">
                        {entry?.category || ''}
                      </td>
                    )}
                  </Fragment>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  const creditEntries: Record<string, Transaction[]> = {}
  const debitEntries: Record<string, Transaction[]> = {}
  pageDates.forEach((date) => {
    creditEntries[date] = grouped[date]?.credit || []
    debitEntries[date] = grouped[date]?.debit || []
  })

  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-badge">CF</div>
          <div>
            <h1>Catefolio</h1>
            <div className="logo-sub">Transaction Workspace</div>
          </div>
        </div>
        <div className="nav-group">
          <div className="nav-item active">Workspace</div>
          <div className="nav-item">Entities</div>
          <div className="nav-item">Categories</div>
          <div className="nav-item">Insights</div>
          <div className="nav-item">Exports</div>
        </div>
      </aside>

      <main className="main">
        <header className="header">
          <div className="workspace-title">
            <h2>Template Conversion</h2>
            <p>Upload statements, then preview credit/debit tables in template format.</p>
          </div>
          <div className="header-actions">
            <button className="btn ghost" onClick={handleDownload} disabled={!templateBlob}>
              Download Excel
            </button>
            <label className={`btn primary ${isUploading ? 'uploading' : ''}`}>
              {isUploading ? (
                <>
                  <Spinner />
                  <span>Processing...</span>
                </>
              ) : (
                'Upload Files'
              )}
              <input
                type="file"
                multiple
                accept=".csv,.xls,.xlsx"
                onChange={(event) => {
                  handleUpload(Array.from(event.target.files || []))
                  event.target.value = '' // Reset to allow re-uploading same file
                }}
                disabled={isUploading}
                hidden
              />
            </label>
          </div>
        </header>

        {/* Upload Progress Overlay */}
        {isUploading && (
          <div className="upload-overlay">
            <div className="upload-modal">
              <Spinner />
              <h3>{uploadState === 'uploading' ? 'Uploading Files' : 'Processing Transactions'}</h3>
              <p className="upload-progress-text">{uploadProgress}</p>
              <div className="upload-progress-bar">
                <div
                  className="upload-progress-fill"
                  style={{ width: uploadState === 'uploading' ? '40%' : '80%' }}
                />
              </div>
              <p className="upload-hint">
                {categorize
                  ? 'AI categorization enabled - this may take longer...'
                  : 'This may take a moment for large files...'}
              </p>
            </div>
          </div>
        )}

        {/* Transaction Detail Modal */}
        {selectedTransaction && (
          <div className="upload-overlay" onClick={() => setSelectedTransaction(null)}>
            <div className="transaction-modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={() => setSelectedTransaction(null)}>×</button>
              <h3>Transaction Details</h3>
              <div className="transaction-detail">
                <div className="detail-row">
                  <span className="detail-label">Description</span>
                  <span className="detail-value">{selectedTransaction.description}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Amount</span>
                  <span className="detail-value">{formatCurrency(selectedTransaction.amount)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Date</span>
                  <span className="detail-value">{selectedTransaction.date}</span>
                </div>
                {selectedTransaction.entity && (
                  <div className="detail-row">
                    <span className="detail-label">Entity</span>
                    <span className="detail-value">{selectedTransaction.entity}</span>
                  </div>
                )}
              </div>
              {selectedTransaction.categories && selectedTransaction.categories.length > 0 && (
                <div className="categories-section">
                  <h4>AI Categories</h4>
                  <div className="category-tags">
                    {selectedTransaction.categories.map((cat, idx) => (
                      <span key={idx} className={`category-tag ${idx === 0 ? 'primary' : ''}`}>
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <section className="card summary">
          <div className="section-title">
            <h3>Batch Summary</h3>
            <span>{dates.length ? `${dates[0]} to ${dates[dates.length - 1]}` : 'Awaiting upload'}</span>
          </div>
          <div className="stat-grid">
            <div className="stat">
              <p>Total Income</p>
              <h3>{formatCurrency(summary?.total_income)}</h3>
            </div>
            <div className="stat">
              <p>Total Expenses</p>
              <h3>{formatCurrency(summary?.total_expenses)}</h3>
            </div>
            <div className="stat">
              <p>Net Savings</p>
              <h3>{formatCurrency(summary?.net_savings)}</h3>
            </div>
          </div>

          {/* Categorization Toggle */}
          <div className="options-row">
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={categorize}
                onChange={(e) => setCategorize(e.target.checked)}
                disabled={isUploading}
              />
              <span className="toggle-switch"></span>
              <span className="toggle-text">
                AI Categorization
                <span className="toggle-badge">Beta</span>
              </span>
            </label>
            {wasCategorized && (
              <span className="categorized-badge">
                <span className="badge-icon">✓</span>
                Categorized
              </span>
            )}
          </div>

          {/* Status with state indicator */}
          <div className={`status-container ${uploadState}`}>
            {uploadState === 'success' && <span className="status-icon success">✓</span>}
            {uploadState === 'error' && <span className="status-icon error">✕</span>}
            <p className="status">{status}</p>
          </div>

          {/* Error message */}
          {errorMessage && (
            <div className="error-banner">
              <strong>Error:</strong> {errorMessage}
            </div>
          )}
        </section>

        <section className="card template">
          <div className="section-title">
            <h3>Template Preview</h3>
            <span>
              Credit and debit tables grouped by date
              {wasCategorized && ' • Click transaction to view categories'}
            </span>
          </div>
          <div className="template-controls">
            <div className="pager">
              <button
                className="btn ghost"
                onClick={() => setPage((prev) => Math.max(prev - 1, 0))}
                disabled={page === 0}
              >
                Prev
              </button>
              <button
                className="btn ghost"
                onClick={() =>
                  setPage((prev) => Math.min(prev + 1, Math.max(0, Math.ceil(dates.length / DATES_PER_PAGE) - 1)))
                }
                disabled={page >= Math.max(0, Math.ceil(dates.length / DATES_PER_PAGE) - 1)}
              >
                Next
              </button>
            </div>
            <span className="pager-status">{pageStatus}</span>
          </div>
          <div className="template-section">
            <div className="template-label">Credit</div>
            <div className="template-scroll">{renderTable(creditEntries, 'credit')}</div>
          </div>
          <div className="template-section">
            <div className="template-label">Debit</div>
            <div className="template-scroll">{renderTable(debitEntries, 'debit')}</div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
