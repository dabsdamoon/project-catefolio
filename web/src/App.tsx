import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import './App.css'
import InsightsDashboard from './InsightsDashboard'
import { TeamProvider } from './team/TeamContext'
import TeamPage from './team/TeamPage'

const getStoredApiMode = (): 'local' | 'cloud' => {
  // In production, always use cloud (API switcher is hidden)
  if (import.meta.env.PROD) {
    return 'cloud'
  }
  // In development, check localStorage for user preference
  const stored = localStorage.getItem('catefolio_api_mode')
  return stored === 'cloud' ? 'cloud' : 'local'
}

// Parse TSV (tab-separated) with columns as categories and rows as keywords
// Format: First row = category names, following rows = keywords
// Using TSV because category names/keywords may contain commas
type CategoryKeywordsMap = Record<string, string[]>

const parseCategoryTSV = async (file: File): Promise<CategoryKeywordsMap> => {
  const text = await file.text()
  const lines = text.split(/[\r\n]+/).filter(line => line.trim())

  if (lines.length < 1) {
    throw new Error('TSV file is empty')
  }

  // Parse header row to get category names (tab-separated)
  const headers = lines[0].split('\t').map(h => h.trim())

  // Initialize result map
  const result: CategoryKeywordsMap = {}
  headers.forEach(header => {
    if (header) {
      result[header] = []
    }
  })

  // Parse data rows (tab-separated)
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split('\t').map(v => v.trim())
    values.forEach((value, colIndex) => {
      const categoryName = headers[colIndex]
      if (categoryName && value && !result[categoryName].includes(value)) {
        result[categoryName].push(value)
      }
    })
  }

  return result
}
const DATES_PER_PAGE = 6

interface AppProps {
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>
  apiEndpoints: { local: string; cloud: string }
  isDemo: boolean
  userDisplayName?: string
  userPhotoURL?: string | null
  onSignOut?: () => void
}

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

type Category = {
  id: string
  name: string
  keywords: string[]
}

type NavView = 'dashboard' | 'upload' | 'categories' | 'exports' | 'team'

function Spinner() {
  return (
    <div className="spinner" aria-label="Loading">
      <div className="spinner-ring"></div>
    </div>
  )
}

function App({ apiFetch, apiEndpoints, isDemo, userDisplayName, userPhotoURL, onSignOut }: AppProps) {
  const [apiMode, setApiMode] = useState<'local' | 'cloud'>(getStoredApiMode)
  const API_BASE = apiEndpoints[apiMode]

  const handleApiModeChange = (mode: 'local' | 'cloud') => {
    setApiMode(mode)
    localStorage.setItem('catefolio_api_mode', mode)
  }

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
  const [activeView, setActiveView] = useState<NavView>('dashboard')
  const [dashboardTransactions, setDashboardTransactions] = useState<Transaction[]>([])
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [duplicateFound, setDuplicateFound] = useState<{
    jobId: string
    files: File[]
    transactionCount: number
    wasCategorized: boolean
  } | null>(null)
  const [expenseCategories, setExpenseCategories] = useState<Category[]>([])
  const [keywordInputs, setKeywordInputs] = useState<Record<string, string>>({})
  const [keywordArrays, setKeywordArrays] = useState<Record<string, string[]>>({})
  const [categoriesLoading, setCategoriesLoading] = useState(false)
  const [categoriesSaving, setCategoriesSaving] = useState(false)
  const [categoriesMessage, setCategoriesMessage] = useState('')
  const [csvImportPreview, setCsvImportPreview] = useState<CategoryKeywordsMap | null>(null)
  const [csvImportMatches, setCsvImportMatches] = useState<Record<string, string>>({})
  const csvFileInputRef = useRef<HTMLInputElement | null>(null)

  const isUploading = uploadState === 'uploading' || uploadState === 'processing'
  const [dashboardError, setDashboardError] = useState<string | null>(null)

  const loadDashboardTransactions = useCallback(async () => {
    setDashboardLoading(true)
    setDashboardError(null)
    try {
      const response = await apiFetch(`${API_BASE}/transactions`)
      if (response.ok) {
        const data = await response.json()
        setDashboardTransactions(data.transactions || [])
      } else {
        setDashboardError('Failed to load transactions')
      }
    } catch (error) {
      console.error('Failed to load dashboard transactions:', error)
      setDashboardError('Failed to load transactions. Please try again.')
    } finally {
      setDashboardLoading(false)
    }
  }, [API_BASE, apiFetch])

  const handleClearAllData = async () => {
    if (!confirm('Are you sure you want to delete all your transaction data? This cannot be undone.')) {
      return
    }
    setDashboardLoading(true)
    try {
      const response = await apiFetch(`${API_BASE}/jobs`, { method: 'DELETE' })
      if (response.ok) {
        const data = await response.json()
        console.log(`Deleted ${data.deleted_count} jobs`)
        setDashboardTransactions([])
        setSummary(null)
        setTransactions([])
      }
    } catch (error) {
      console.error('Failed to clear data:', error)
    } finally {
      setDashboardLoading(false)
    }
  }

  const loadCategories = useCallback(async () => {
    setCategoriesLoading(true)
    setCategoriesMessage('')
    try {
      const response = await apiFetch(`${API_BASE}/categories`)
      if (response.ok) {
        const data: Category[] = await response.json()
        setExpenseCategories(data)
        const inputs: Record<string, string> = {}
        const arrays: Record<string, string[]> = {}
        data.forEach((cat) => {
          inputs[cat.id] = ''
          arrays[cat.id] = cat.keywords || []
        })
        setKeywordInputs(inputs)
        setKeywordArrays(arrays)
      } else {
        setCategoriesMessage('Failed to load categories')
      }
    } catch (error) {
      console.error('Failed to load categories:', error)
      setCategoriesMessage('Failed to load categories')
    } finally {
      setCategoriesLoading(false)
    }
  }, [API_BASE, apiFetch])

  useEffect(() => {
    if (activeView === 'dashboard') {
      loadDashboardTransactions()
    }
    if (activeView === 'categories') {
      loadCategories()
    }
  }, [activeView, loadDashboardTransactions, loadCategories, apiMode])

  const saveCategories = async () => {
    setCategoriesSaving(true)
    setCategoriesMessage('')
    try {
      const categoriesToSave = expenseCategories.map((cat) => ({
        ...cat,
        keywords: keywordArrays[cat.id] || [],
      }))
      const response = await apiFetch(`${API_BASE}/categories`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(categoriesToSave),
      })
      if (response.ok) {
        setExpenseCategories(categoriesToSave)
        setCategoriesMessage('Categories saved successfully')
      } else {
        setCategoriesMessage('Failed to save categories')
      }
    } catch (error) {
      console.error('Failed to save categories:', error)
      setCategoriesMessage('Failed to save categories')
    } finally {
      setCategoriesSaving(false)
    }
  }

  const updateCategoryName = (id: string, name: string) => {
    setExpenseCategories((prev) =>
      prev.map((cat) => (cat.id === id ? { ...cat, name } : cat))
    )
  }

  const updateKeywordInput = (id: string, value: string) => {
    setKeywordInputs((prev) => ({ ...prev, [id]: value }))
  }

  const addKeyword = useCallback((categoryId: string, keyword: string) => {
    const trimmed = keyword.trim()
    if (!trimmed) return

    setKeywordArrays((prev) => {
      const existing = prev[categoryId] || []
      if (existing.includes(trimmed)) return prev
      return { ...prev, [categoryId]: [...existing, trimmed] }
    })
  }, [])

  const removeKeyword = useCallback((categoryId: string, keyword: string) => {
    setKeywordArrays((prev) => ({
      ...prev,
      [categoryId]: (prev[categoryId] || []).filter((k) => k !== keyword),
    }))
  }, [])

  const handleKeywordInputKeyDown = (categoryId: string, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      const input = keywordInputs[categoryId] || ''
      addKeyword(categoryId, input)
      setKeywordInputs((prev) => ({ ...prev, [categoryId]: '' }))
    }
  }

  const clearAllKeywords = (categoryId: string) => {
    setKeywordArrays((prev) => ({ ...prev, [categoryId]: [] }))
  }

  // TSV Import handlers
  const handleTsvFileSelect = async (file: File) => {
    try {
      const parsed = await parseCategoryTSV(file)
      setCsvImportPreview(parsed)

      // Auto-match CSV columns to existing categories by name
      const matches: Record<string, string> = {}
      Object.keys(parsed).forEach(csvCategory => {
        const match = expenseCategories.find(
          cat => cat.name.toLowerCase() === csvCategory.toLowerCase()
        )
        if (match) {
          matches[csvCategory] = match.id
        }
      })
      setCsvImportMatches(matches)
    } catch (error) {
      console.error('Failed to parse TSV file:', error)
      setCategoriesMessage('Failed to parse TSV file. Please check the format.')
    }
  }

  const handleCsvMatchChange = (csvCategory: string, categoryId: string) => {
    setCsvImportMatches(prev => ({ ...prev, [csvCategory]: categoryId }))
  }

  const applyCSVImport = () => {
    if (!csvImportPreview) return

    const newKeywordArrays = { ...keywordArrays }
    let totalAdded = 0

    Object.entries(csvImportMatches).forEach(([csvCategory, categoryId]) => {
      if (categoryId && csvImportPreview[csvCategory]) {
        const existing = newKeywordArrays[categoryId] || []
        const newKeywords = csvImportPreview[csvCategory].filter(k => !existing.includes(k))
        newKeywordArrays[categoryId] = [...existing, ...newKeywords]
        totalAdded += newKeywords.length
      }
    })

    setKeywordArrays(newKeywordArrays)
    setCsvImportPreview(null)
    setCsvImportMatches({})
    setCategoriesMessage(`Successfully imported ${totalAdded} keywords`)
  }

  const cancelCSVImport = () => {
    setCsvImportPreview(null)
    setCsvImportMatches({})
  }

  const downloadKeywordTemplate = () => {
    // Get all category names and their keywords
    const categories = expenseCategories.map(cat => ({
      name: cat.name,
      keywords: keywordArrays[cat.id] || []
    }))

    // Find max keyword count to determine number of rows
    const maxKeywords = Math.max(...categories.map(c => c.keywords.length), 1)

    // Build TSV content (tab-separated to allow commas in values)
    const rows: string[] = []

    // Header row (category names, tab-separated)
    rows.push(categories.map(c => c.name).join('\t'))

    // Data rows (keywords, tab-separated)
    for (let i = 0; i < maxKeywords; i++) {
      const row = categories.map(c => c.keywords[i] || '')
      rows.push(row.join('\t'))
    }

    // Create and download file
    const tsvContent = rows.join('\n')
    const blob = new Blob([tsvContent], { type: 'text/tab-separated-values;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'keyword_template.tsv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

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


  const handleUpload = async (files: File[], forceReprocess = false) => {
    if (!files.length) return

    // Reset state
    setUploadState('uploading')
    setErrorMessage('')
    setTemplateBlob(null)
    setSelectedTransaction(null)
    if (!forceReprocess) {
      setDuplicateFound(null)
    }

    const fileNames = files.map((file) => file.name).join(', ')
    setUploadProgress(`Uploading ${files.length} file(s): ${fileNames}`)
    setStatus(`Uploading ${files.length} file(s)...`)

    try {
      // Step 1: Upload files
      setUploadProgress('Uploading files to server...')
      const uploadUrl = `${API_BASE}/upload?categorize=${categorize}&force_reprocess=${forceReprocess}`
      const uploadResponse = await apiFetch(uploadUrl, {
        method: 'POST',
        body: buildFormData(files),
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error(errorData.detail || `Upload failed (${uploadResponse.status})`)
      }

      const uploadData = await uploadResponse.json()
      const isDuplicate = uploadData.is_duplicate

      // If duplicate found and not forcing reprocess, show modal to ask user
      if (isDuplicate && !forceReprocess) {
        setDuplicateFound({
          jobId: uploadData.job_id,
          files: files,
          transactionCount: uploadData.files_received,
          wasCategorized: uploadData.was_categorized,
        })
        setUploadState('idle')
        setUploadProgress('')
        setStatus('Duplicate transactions detected.')
        return
      }

      // Step 2: Process results
      setUploadState('processing')
      setUploadProgress(categorize ? 'Processing transactions with AI...' : 'Processing transactions...')
      setStatus(categorize ? 'Processing... AI is categorizing your transactions.' : 'Processing transactions...')

      const resultResponse = await apiFetch(`${API_BASE}/result/${uploadData.job_id}`)
      if (!resultResponse.ok) {
        throw new Error(`Failed to fetch results (${resultResponse.status})`)
      }

      const resultData = await resultResponse.json()
      setSummary(resultData.summary)
      setTransactions(resultData.transactions)
      setWasCategorized(uploadData.was_categorized || resultData.categorized || false)
      setPage(0)

      // Step 3: Generate template (don't force_reprocess - job already exists from step 1)
      setUploadProgress('Generating Excel template...')
      const templateUrl = `${API_BASE}/template/convert?categorize=${categorize}&force_reprocess=false`
      const templateResponse = await apiFetch(templateUrl, {
        method: 'POST',
        body: buildFormData(files),
      })

      if (!templateResponse.ok) {
        throw new Error(`Template export failed (${templateResponse.status})`)
      }

      const blob = await templateResponse.blob()
      setTemplateBlob(blob)

      // Success message
      setUploadState('success')
      setUploadProgress('')
      setDuplicateFound(null)

      const catMsg = categorize ? ' with AI categorization' : ''
      const reprocessMsg = forceReprocess ? ' (re-processed)' : ''
      const dupSkipped = uploadData.duplicates_skipped || 0
      const dupMsg = dupSkipped > 0 ? ` (${dupSkipped} duplicates skipped)` : ''
      setStatus(`Successfully processed ${resultData.transactions.length} transactions${catMsg}${reprocessMsg}${dupMsg}. Template ready for download.`)

    } catch (error) {
      setUploadState('error')
      const message = error instanceof Error ? error.message : 'An unexpected error occurred'
      setErrorMessage(message)
      setStatus('Upload failed. Please check the error message below.')
      setUploadProgress('')
    }
  }

  const handleUsePreviousResult = async () => {
    if (!duplicateFound) return

    setUploadState('processing')
    setUploadProgress('Loading existing results...')

    try {
      const resultResponse = await apiFetch(`${API_BASE}/result/${duplicateFound.jobId}`)
      if (!resultResponse.ok) {
        throw new Error(`Failed to fetch results (${resultResponse.status})`)
      }

      const resultData = await resultResponse.json()
      setSummary(resultData.summary)
      setTransactions(resultData.transactions)
      setWasCategorized(duplicateFound.wasCategorized)
      setPage(0)

      // Generate template from existing data
      setUploadProgress('Generating Excel template...')
      const templateUrl = `${API_BASE}/template/convert?categorize=false`
      const templateResponse = await apiFetch(templateUrl, {
        method: 'POST',
        body: buildFormData(duplicateFound.files),
      })

      if (templateResponse.ok) {
        const blob = await templateResponse.blob()
        setTemplateBlob(blob)
      }

      setUploadState('success')
      setUploadProgress('')
      setDuplicateFound(null)

      const catMsg = duplicateFound.wasCategorized ? ' (previously categorized)' : ''
      setStatus(`Loaded ${resultData.transactions.length} transactions from existing data${catMsg}. Template ready for download.`)
    } catch (error) {
      setUploadState('error')
      const message = error instanceof Error ? error.message : 'An unexpected error occurred'
      setErrorMessage(message)
      setStatus('Failed to load previous results.')
      setUploadProgress('')
    }
  }

  const handleOverwriteAndReprocess = () => {
    if (!duplicateFound) return
    const filesToProcess = duplicateFound.files
    setDuplicateFound(null) // Close modal immediately to show upload progress
    handleUpload(filesToProcess, true)
  }

  const handleCancelDuplicate = () => {
    setDuplicateFound(null)
    setStatus('Upload cancelled.')
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

  const content = (
    <div className="app-root">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-badge">CF</div>
          <div>
            <h1>Catefolio</h1>
            <div className="logo-sub">Transaction Workspace</div>
          </div>
        </div>
        <nav className="nav-group">
          <button
            className={`nav-item ${activeView === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveView('dashboard')}
          >
            Dashboard
          </button>
          <button
            className={`nav-item ${activeView === 'upload' ? 'active' : ''}`}
            onClick={() => setActiveView('upload')}
          >
            Upload Data
          </button>
          <button
            className={`nav-item ${activeView === 'categories' ? 'active' : ''}`}
            onClick={() => setActiveView('categories')}
          >
            Set Transaction Categories
          </button>
          <button
            className={`nav-item ${activeView === 'exports' ? 'active' : ''}`}
            onClick={() => setActiveView('exports')}
          >
            Exports
          </button>
          <button
            className={`nav-item ${activeView === 'team' ? 'active' : ''}`}
            onClick={() => setActiveView('team')}
          >
            Team
          </button>
        </nav>
        {/* API Switcher - only show in development (hidden in production) */}
        {import.meta.env.DEV && (
          <div className="api-switcher">
            <label className="api-switcher-label">API Endpoint</label>
            <div className="api-switcher-options">
              <button
                className={`api-option ${apiMode === 'local' ? 'active' : ''}`}
                onClick={() => handleApiModeChange('local')}
              >
                Local
              </button>
              <button
                className={`api-option ${apiMode === 'cloud' ? 'active' : ''}`}
                onClick={() => handleApiModeChange('cloud')}
              >
                Cloud
              </button>
            </div>
            <div className="api-switcher-url" title={API_BASE}>
              {apiMode === 'local' ? 'localhost:8000' : 'Cloud Run'}
            </div>
          </div>
        )}
        <div className="user-section">
          <div className="user-info">
            {userPhotoURL ? (
              <img src={userPhotoURL} alt="" className="user-avatar" />
            ) : (
              <div className="user-avatar-placeholder">
                {userDisplayName?.charAt(0).toUpperCase() || 'U'}
              </div>
            )}
            <div className="user-details">
              <span className="user-name">{userDisplayName || 'User'}</span>
              {isDemo && <span className="user-badge demo">Demo</span>}
            </div>
          </div>
          {onSignOut ? (
            <button className="sign-out-btn" onClick={onSignOut}>
              Sign Out
            </button>
          ) : isDemo && (
            <Link to="/login" className="sign-in-link">
              Sign in to save your data
            </Link>
          )}
        </div>
      </aside>

      <main className="main">
        {activeView === 'categories' && (
          <>
            <header className="header">
              <div className="workspace-title">
                <h2>Set Transaction Categories</h2>
                <p>Define category names and keywords for AI-powered transaction categorization.</p>
              </div>
            </header>

            <section className="card">
              <div className="section-title">
                <h3>Expense Categories</h3>
                <span>Type keywords manually or use the buttons below to import/export</span>
              </div>

              {categoriesLoading ? (
                <div className="table-empty">Loading categories...</div>
              ) : (
                <div className="categories-list">
                  {expenseCategories.map((cat) => (
                    <div key={cat.id} className="category-row-enhanced">
                      <div className="category-header-row">
                        <div className="category-field name-field">
                          <label>Category Name</label>
                          <input
                            type="text"
                            value={cat.name}
                            onChange={(e) => updateCategoryName(cat.id, e.target.value)}
                            placeholder="Category name"
                          />
                        </div>
                        {(keywordArrays[cat.id]?.length || 0) > 0 && (
                          <button
                            className="btn-clear-keywords"
                            onClick={() => clearAllKeywords(cat.id)}
                            title="Clear all keywords"
                          >
                            Clear All
                          </button>
                        )}
                      </div>

                      <div className="keywords-container">
                        <div className="keywords-tags-area">
                          {(keywordArrays[cat.id] || []).map((keyword, idx) => (
                            <span key={`${cat.id}-${keyword}-${idx}`} className="keyword-tag">
                              {keyword}
                              <button
                                className="keyword-tag-remove"
                                onClick={() => removeKeyword(cat.id, keyword)}
                                aria-label={`Remove ${keyword}`}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                          <input
                            type="text"
                            className="keyword-inline-input"
                            value={keywordInputs[cat.id] || ''}
                            onChange={(e) => updateKeywordInput(cat.id, e.target.value)}
                            onKeyDown={(e) => handleKeywordInputKeyDown(cat.id, e)}
                            placeholder={
                              (keywordArrays[cat.id]?.length || 0) === 0
                                ? 'Type keyword and press Enter...'
                                : 'Add more...'
                            }
                          />
                        </div>
                        {(keywordArrays[cat.id]?.length || 0) > 0 && (
                          <div className="keywords-count">
                            {keywordArrays[cat.id].length} keyword{keywordArrays[cat.id].length !== 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* CSV Import Preview Modal */}
            {csvImportPreview && (
              <div className="upload-overlay" onClick={cancelCSVImport}>
                <div className="csv-import-modal" onClick={(e) => e.stopPropagation()}>
                  <button className="modal-close" onClick={cancelCSVImport}>×</button>
                  <h3>Import Keywords from TSV</h3>
                  <p className="csv-import-desc">
                    Map TSV columns to your categories. Unmatched columns will be skipped.
                  </p>

                  <div className="csv-import-mappings">
                    {Object.entries(csvImportPreview).map(([csvCategory, keywords]) => (
                      <div key={csvCategory} className="csv-mapping-row">
                        <div className="csv-mapping-source">
                          <span className="csv-column-name">{csvCategory}</span>
                          <span className="csv-keyword-count">{keywords.length} keywords</span>
                          <div className="csv-keyword-preview">
                            {keywords.slice(0, 3).join(', ')}
                            {keywords.length > 3 && ` +${keywords.length - 3} more`}
                          </div>
                        </div>
                        <div className="csv-mapping-arrow">→</div>
                        <select
                          className="csv-mapping-select"
                          value={csvImportMatches[csvCategory] || ''}
                          onChange={(e) => handleCsvMatchChange(csvCategory, e.target.value)}
                        >
                          <option value="">Skip this column</option>
                          {expenseCategories.map((cat) => (
                            <option key={cat.id} value={cat.id}>
                              {cat.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>

                  <div className="csv-import-actions">
                    <button className="btn ghost" onClick={cancelCSVImport}>
                      Cancel
                    </button>
                    <button
                      className="btn primary"
                      onClick={applyCSVImport}
                      disabled={Object.values(csvImportMatches).filter(Boolean).length === 0}
                    >
                      Import {Object.values(csvImportMatches).filter(Boolean).length} Categories
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Sticky Save Footer */}
            <div className="sticky-save-footer">
              <div className="sticky-save-content">
                <div className="sticky-footer-left">
                  <button className="btn ghost" onClick={downloadKeywordTemplate}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download Template
                  </button>
                  <label className="btn ghost">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="17 8 12 3 7 8"/>
                      <line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                    Import TSV
                    <input
                      type="file"
                      accept=".tsv,.txt"
                      ref={csvFileInputRef}
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) handleTsvFileSelect(file)
                        e.target.value = ''
                      }}
                      hidden
                    />
                  </label>
                </div>
                <div className="sticky-footer-right">
                  {categoriesMessage && (
                    <span className={`sticky-save-message ${categoriesMessage.includes('success') ? 'success' : 'error'}`}>
                      {categoriesMessage.includes('success') ? '✓' : '✕'} {categoriesMessage}
                    </span>
                  )}
                  <button
                    className="btn primary"
                    onClick={saveCategories}
                    disabled={categoriesSaving}
                  >
                    {categoriesSaving ? (
                      <>
                        <Spinner />
                        <span>Saving...</span>
                      </>
                    ) : (
                      'Save Categories'
                    )}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}

        {activeView === 'upload' && (
          <>
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

        {/* Duplicate Found Modal */}
        {duplicateFound && (
          <div className="upload-overlay">
            <div className="duplicate-modal">
              <div className="duplicate-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <h3>Duplicate Transactions Found</h3>
              <p className="duplicate-desc">
                These transactions have already been processed.
                {duplicateFound.wasCategorized && ' AI categorization was previously applied.'}
              </p>
              <div className="duplicate-info">
                <div className="duplicate-stat">
                  <span className="duplicate-stat-value">{duplicateFound.wasCategorized ? 'Yes' : 'No'}</span>
                  <span className="duplicate-stat-label">AI Categorized</span>
                </div>
              </div>
              <p className="duplicate-question">What would you like to do?</p>
              <div className="duplicate-actions">
                <button className="btn ghost" onClick={handleCancelDuplicate}>
                  Cancel
                </button>
                <button className="btn ghost" onClick={handleUsePreviousResult}>
                  Use Existing Data
                </button>
                <button className="btn primary" onClick={handleOverwriteAndReprocess}>
                  Overwrite & Re-process
                </button>
              </div>
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
          </>
        )}

        {activeView === 'dashboard' && (
          <InsightsDashboard
            transactions={dashboardTransactions}
            loading={dashboardLoading}
            error={dashboardError}
            onClearAllData={handleClearAllData}
          />
        )}

        {activeView === 'exports' && (
          <section className="card">
            <div className="section-title">
              <h3>Exports</h3>
              <span>Coming soon</span>
            </div>
            <div className="table-empty">Exports feature is under development.</div>
          </section>
        )}

        {activeView === 'team' && (
          <TeamPage />
        )}
      </main>
    </div>
  )

  return (
    <TeamProvider apiFetch={apiFetch} apiBaseUrl={API_BASE}>
      {content}
    </TeamProvider>
  )
}

export default App
