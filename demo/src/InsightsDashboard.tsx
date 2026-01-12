import { useMemo, useState, useCallback } from 'react'
import './InsightsDashboard.css'

type Transaction = {
  date: string
  description: string
  amount: number
  category?: string
  entity?: string
}

type DirectionFilter = 'both' | 'credit' | 'debit'

interface InsightsDashboardProps {
  transactions: Transaction[]
  loading?: boolean
  onCategoryFilter?: (category: string) => void
  onCounterpartyFilter?: (counterparty: string) => void
  onClearAllData?: () => void
}

const EXPLORER_PAGE_SIZE = 50

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)

const formatCompact = (value: number) =>
  new Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(value)

export default function InsightsDashboard({
  transactions,
  loading = false,
  onCategoryFilter,
  onCounterpartyFilter,
  onClearAllData,
}: InsightsDashboardProps) {
  const [direction, setDirection] = useState<DirectionFilter>('both')
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [explorerPage, setExplorerPage] = useState(0)
  const [sortField, setSortField] = useState<'date' | 'amount'>('date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [hoveredDay, setHoveredDay] = useState<string | null>(null)
  const [selectedDay, setSelectedDay] = useState<string | null>(null)

  // Compute all categories from transactions
  const allCategories = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach((tx) => {
      if (tx.category) set.add(tx.category)
    })
    return Array.from(set).sort()
  }, [transactions])

  // KPI Metrics
  const kpis = useMemo(() => {
    let totalCredit = 0
    let totalDebit = 0
    let creditCount = 0
    let debitCount = 0
    let uncategorizedCount = 0
    const creditCategoryTotals = new Map<string, number>()
    const debitCategoryTotals = new Map<string, number>()

    transactions.forEach((tx) => {
      const cat = (tx.category || '').trim()
      if (!cat || cat === 'Uncategorized') uncategorizedCount++

      if (tx.amount >= 0) {
        totalCredit += tx.amount
        creditCount++
        creditCategoryTotals.set(cat || 'Uncategorized', (creditCategoryTotals.get(cat || 'Uncategorized') || 0) + tx.amount)
      } else {
        totalDebit += Math.abs(tx.amount)
        debitCount++
        debitCategoryTotals.set(cat || 'Uncategorized', (debitCategoryTotals.get(cat || 'Uncategorized') || 0) + Math.abs(tx.amount))
      }
    })

    const topCreditCategory = Array.from(creditCategoryTotals.entries()).sort((a, b) => b[1] - a[1])[0]
    const topDebitCategory = Array.from(debitCategoryTotals.entries()).sort((a, b) => b[1] - a[1])[0]
    const uncategorizedRate = transactions.length > 0 ? (uncategorizedCount / transactions.length) * 100 : 0

    return {
      totalCredit,
      totalDebit,
      net: totalCredit - totalDebit,
      creditCount,
      debitCount,
      totalCount: transactions.length,
      topCreditCategory: topCreditCategory?.[0] || 'N/A',
      topDebitCategory: topDebitCategory?.[0] || 'N/A',
      uncategorizedRate,
    }
  }, [transactions])

  // Date range
  const dateRange = useMemo(() => {
    if (!transactions.length) return { start: '', end: '' }
    const dates = transactions.map((tx) => tx.date).sort()
    return { start: dates[0], end: dates[dates.length - 1] }
  }, [transactions])

  // Daily series for chart
  const dailySeries = useMemo(() => {
    const map = new Map<string, { credit: number; debit: number; creditCount: number; debitCount: number }>()
    transactions.forEach((tx) => {
      const bucket = map.get(tx.date) || { credit: 0, debit: 0, creditCount: 0, debitCount: 0 }
      if (tx.amount >= 0) {
        bucket.credit += tx.amount
        bucket.creditCount++
      } else {
        bucket.debit += Math.abs(tx.amount)
        bucket.debitCount++
      }
      map.set(tx.date, bucket)
    })
    const labels = Array.from(map.keys()).sort()
    return {
      labels,
      data: labels.map((date) => map.get(date)!),
    }
  }, [transactions])

  // Top categories
  const topCategories = useMemo(() => {
    const creditTotals = new Map<string, number>()
    const debitTotals = new Map<string, number>()
    transactions.forEach((tx) => {
      const category = (tx.category || 'Uncategorized').trim() || 'Uncategorized'
      if (tx.amount >= 0) {
        creditTotals.set(category, (creditTotals.get(category) || 0) + tx.amount)
      } else {
        debitTotals.set(category, (debitTotals.get(category) || 0) + Math.abs(tx.amount))
      }
    })
    const toSorted = (map: Map<string, number>) =>
      Array.from(map.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
    return { credit: toSorted(creditTotals), debit: toSorted(debitTotals) }
  }, [transactions])

  // Top counterparties
  const topCounterparties = useMemo(() => {
    const creditTotals = new Map<string, { total: number; count: number }>()
    const debitTotals = new Map<string, { total: number; count: number }>()
    transactions.forEach((tx) => {
      const key = tx.description || 'Unknown'
      if (tx.amount >= 0) {
        const existing = creditTotals.get(key) || { total: 0, count: 0 }
        creditTotals.set(key, { total: existing.total + tx.amount, count: existing.count + 1 })
      } else {
        const existing = debitTotals.get(key) || { total: 0, count: 0 }
        debitTotals.set(key, { total: existing.total + Math.abs(tx.amount), count: existing.count + 1 })
      }
    })
    const toSorted = (map: Map<string, { total: number; count: number }>) =>
      Array.from(map.entries())
        .sort((a, b) => b[1].total - a[1].total)
        .slice(0, 6)
    return { credit: toSorted(creditTotals), debit: toSorted(debitTotals) }
  }, [transactions])

  // Filtered transactions for explorer
  const filteredTransactions = useMemo(() => {
    let result = transactions.filter((tx) => {
      // Direction filter
      if (direction === 'credit' && tx.amount < 0) return false
      if (direction === 'debit' && tx.amount >= 0) return false

      // Category filter
      if (selectedCategory !== 'All') {
        if (tx.category !== selectedCategory) return false
      }

      // Search filter
      if (searchQuery.trim()) {
        const needle = searchQuery.toLowerCase()
        const haystack = `${tx.description} ${tx.category || ''}`.toLowerCase()
        if (!haystack.includes(needle)) return false
      }

      // Day filter
      if (selectedDay && tx.date !== selectedDay) return false

      return true
    })

    // Sort
    result = [...result].sort((a, b) => {
      if (sortField === 'date') {
        return sortDir === 'asc' ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date)
      }
      const aAbs = Math.abs(a.amount)
      const bAbs = Math.abs(b.amount)
      return sortDir === 'asc' ? aAbs - bAbs : bAbs - aAbs
    })

    return result
  }, [transactions, direction, selectedCategory, searchQuery, selectedDay, sortField, sortDir])

  const explorerPageCount = Math.ceil(filteredTransactions.length / EXPLORER_PAGE_SIZE)
  const explorerItems = filteredTransactions.slice(
    explorerPage * EXPLORER_PAGE_SIZE,
    (explorerPage + 1) * EXPLORER_PAGE_SIZE
  )

  const handleCategoryClick = useCallback(
    (category: string) => {
      setSelectedCategory(category)
      setExplorerPage(0)
      onCategoryFilter?.(category)
    },
    [onCategoryFilter]
  )

  const handleCounterpartyClick = useCallback(
    (counterparty: string) => {
      setSearchQuery(counterparty)
      setExplorerPage(0)
      onCounterpartyFilter?.(counterparty)
    },
    [onCounterpartyFilter]
  )

  const handleSort = (field: 'date' | 'amount') => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
    setExplorerPage(0)
  }

  const handleDayClick = (date: string) => {
    setSelectedDay((d) => (d === date ? null : date))
    setExplorerPage(0)
  }

  const clearFilters = () => {
    setDirection('both')
    setSelectedCategory('All')
    setSearchQuery('')
    setSelectedDay(null)
    setExplorerPage(0)
  }

  // Chart dimensions
  const chartWidth = 800
  const chartHeight = 200
  const chartPadding = { top: 20, right: 20, bottom: 30, left: 60 }
  const plotWidth = chartWidth - chartPadding.left - chartPadding.right
  const plotHeight = chartHeight - chartPadding.top - chartPadding.bottom

  // Build chart paths and points
  const chartData = useMemo(() => {
    const { labels, data } = dailySeries
    if (!labels.length) return { creditPath: '', debitPath: '', creditArea: '', debitArea: '', maxValue: 0, points: [] }

    const allValues = data.flatMap((d) => [d.credit, d.debit])
    const maxValue = Math.max(...allValues, 1)
    const xStep = labels.length > 1 ? plotWidth / (labels.length - 1) : plotWidth / 2

    const creditPoints = labels.map((_, i) => ({
      x: chartPadding.left + i * xStep,
      y: chartPadding.top + plotHeight - (data[i].credit / maxValue) * plotHeight,
    }))

    const debitPoints = labels.map((_, i) => ({
      x: chartPadding.left + i * xStep,
      y: chartPadding.top + plotHeight - (data[i].debit / maxValue) * plotHeight,
    }))

    const creditPath = creditPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
    const debitPath = debitPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')

    const baseline = chartPadding.top + plotHeight
    const creditArea = `${creditPath} L${creditPoints[creditPoints.length - 1]?.x || 0},${baseline} L${creditPoints[0]?.x || 0},${baseline} Z`
    const debitArea = `${debitPath} L${debitPoints[debitPoints.length - 1]?.x || 0},${baseline} L${debitPoints[0]?.x || 0},${baseline} Z`

    const points = labels.map((date, i) => ({
      date,
      x: chartPadding.left + i * xStep,
      creditY: creditPoints[i].y,
      debitY: debitPoints[i].y,
      credit: data[i].credit,
      debit: data[i].debit,
      creditCount: data[i].creditCount,
      debitCount: data[i].debitCount,
    }))

    return { creditPath, debitPath, creditArea, debitArea, maxValue, points }
  }, [dailySeries, plotWidth, plotHeight])

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const { maxValue } = chartData
    if (maxValue === 0) return []
    const tickCount = 4
    return Array.from({ length: tickCount + 1 }, (_, i) => {
      const value = (maxValue / tickCount) * i
      const y = chartPadding.top + plotHeight - (value / maxValue) * plotHeight
      return { value, y }
    })
  }, [chartData, plotHeight])

  const hasActiveFilters = direction !== 'both' || selectedCategory !== 'All' || searchQuery || selectedDay

  if (loading) {
    return (
      <div className="insights-empty">
        <div className="insights-loading-spinner"></div>
        <h3>Loading Dashboard</h3>
        <p>Fetching your transaction data...</p>
      </div>
    )
  }

  if (!transactions.length) {
    return (
      <div className="insights-empty">
        <div className="insights-empty-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 3v18h18" />
            <path d="M18 9l-5 5-4-4-3 3" />
          </svg>
        </div>
        <h3>No Data Available</h3>
        <p>Upload transaction files in Upload Data to see your dashboard.</p>
      </div>
    )
  }

  return (
    <div className="insights-dashboard">
      {/* Header */}
      <header className="insights-header">
        <div className="insights-header-title">
          <h2>Financial Insights</h2>
          <span className="insights-date-range">
            {dateRange.start} — {dateRange.end}
          </span>
        </div>
        <div className="insights-header-actions">
          {hasActiveFilters && (
            <button className="insights-clear-btn" onClick={clearFilters}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Clear filters
            </button>
          )}
          {onClearAllData && (
            <button className="insights-clear-btn danger" onClick={onClearAllData}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
              Clear All Data
            </button>
          )}
        </div>
      </header>

      {/* Filter Bar */}
      <section className="insights-filters">
        <div className="insights-direction-toggle">
          {(['both', 'credit', 'debit'] as const).map((d) => (
            <button
              key={d}
              className={`direction-btn ${direction === d ? 'active' : ''} ${d}`}
              onClick={() => {
                setDirection(d)
                setExplorerPage(0)
              }}
            >
              {d === 'both' ? 'All' : d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>

        <div className="insights-filter-field">
          <label>Category</label>
          <select
            value={selectedCategory}
            onChange={(e) => {
              setSelectedCategory(e.target.value)
              setExplorerPage(0)
            }}
          >
            <option value="All">All Categories</option>
            {allCategories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        <div className="insights-filter-field search">
          <label>Search</label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setExplorerPage(0)
            }}
            placeholder="Counterparty or keyword..."
          />
        </div>

        {selectedDay && (
          <div className="insights-day-badge">
            <span>{selectedDay}</span>
            <button onClick={() => setSelectedDay(null)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}
      </section>

      {/* KPI Strip */}
      <section className="insights-kpis">
        <div className="kpi-card kpi-credit">
          <div className="kpi-label">Total Income</div>
          <div className="kpi-value">{formatCurrency(kpis.totalCredit)}</div>
          <div className="kpi-sub">{kpis.creditCount.toLocaleString()} transactions</div>
        </div>
        <div className="kpi-card kpi-debit">
          <div className="kpi-label">Total Expenses</div>
          <div className="kpi-value">{formatCurrency(kpis.totalDebit)}</div>
          <div className="kpi-sub">{kpis.debitCount.toLocaleString()} transactions</div>
        </div>
        <div className="kpi-card kpi-net">
          <div className="kpi-label">Net Balance</div>
          <div className={`kpi-value ${kpis.net >= 0 ? 'positive' : 'negative'}`}>
            {kpis.net >= 0 ? '+' : ''}
            {formatCurrency(kpis.net)}
          </div>
          <div className="kpi-sub">{kpis.totalCount.toLocaleString()} total</div>
        </div>
        <div className="kpi-card kpi-meta">
          <div className="kpi-meta-row">
            <span className="kpi-meta-label">Top Income</span>
            <span className="kpi-meta-value credit">{kpis.topCreditCategory}</span>
          </div>
          <div className="kpi-meta-row">
            <span className="kpi-meta-label">Top Expense</span>
            <span className="kpi-meta-value debit">{kpis.topDebitCategory}</span>
          </div>
          <div className="kpi-meta-row">
            <span className="kpi-meta-label">Uncategorized</span>
            <span className="kpi-meta-value">{kpis.uncategorizedRate.toFixed(1)}%</span>
          </div>
        </div>
      </section>

      {/* Time Series Chart */}
      <section className="insights-chart-section">
        <div className="insights-section-header">
          <h3>Daily Flow</h3>
          <div className="insights-chart-legend">
            <span className="legend-item credit">
              <span className="legend-dot"></span>
              Credit
            </span>
            <span className="legend-item debit">
              <span className="legend-dot"></span>
              Debit
            </span>
          </div>
        </div>
        <div className="insights-chart-container">
          <svg
            className="insights-chart"
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Grid lines */}
            <g className="chart-grid">
              {yTicks.map((tick, i) => (
                <line
                  key={i}
                  x1={chartPadding.left}
                  y1={tick.y}
                  x2={chartWidth - chartPadding.right}
                  y2={tick.y}
                  className="grid-line"
                />
              ))}
            </g>

            {/* Y-axis labels */}
            <g className="chart-y-axis">
              {yTicks.map((tick, i) => (
                <text key={i} x={chartPadding.left - 8} y={tick.y + 4} className="axis-label">
                  {formatCompact(tick.value)}
                </text>
              ))}
            </g>

            {/* Area fills */}
            <path d={chartData.creditArea} className="chart-area credit" />
            <path d={chartData.debitArea} className="chart-area debit" />

            {/* Lines */}
            <path d={chartData.creditPath} className="chart-line credit" />
            <path d={chartData.debitPath} className="chart-line debit" />

            {/* Interactive points */}
            {chartData.points.map((point) => (
              <g
                key={point.date}
                className={`chart-point-group ${hoveredDay === point.date ? 'hovered' : ''} ${selectedDay === point.date ? 'selected' : ''}`}
                onMouseEnter={() => setHoveredDay(point.date)}
                onMouseLeave={() => setHoveredDay(null)}
                onClick={() => handleDayClick(point.date)}
              >
                <line
                  x1={point.x}
                  y1={chartPadding.top}
                  x2={point.x}
                  y2={chartPadding.top + plotHeight}
                  className="point-line"
                />
                <circle cx={point.x} cy={point.creditY} r="5" className="point-circle credit" />
                <circle cx={point.x} cy={point.debitY} r="5" className="point-circle debit" />
              </g>
            ))}
          </svg>

          {/* Tooltip */}
          {hoveredDay && (
            <div
              className="chart-tooltip"
              style={{
                left: chartData.points.find((p) => p.date === hoveredDay)?.x || 0,
              }}
            >
              <div className="tooltip-date">{hoveredDay}</div>
              <div className="tooltip-row credit">
                <span>Credit</span>
                <span>{formatCurrency(chartData.points.find((p) => p.date === hoveredDay)?.credit || 0)}</span>
              </div>
              <div className="tooltip-row debit">
                <span>Debit</span>
                <span>{formatCurrency(chartData.points.find((p) => p.date === hoveredDay)?.debit || 0)}</span>
              </div>
              <div className="tooltip-row net">
                <span>Net</span>
                <span>
                  {formatCurrency(
                    (chartData.points.find((p) => p.date === hoveredDay)?.credit || 0) -
                      (chartData.points.find((p) => p.date === hoveredDay)?.debit || 0)
                  )}
                </span>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Split Panels: Categories & Counterparties */}
      <section className="insights-split-panels">
        {/* Categories Panel */}
        <div className="insights-panel">
          <div className="insights-section-header">
            <h3>Categories</h3>
          </div>
          <div className="insights-split-content">
            {(direction === 'both' || direction === 'credit') && (
              <div className="split-lane credit">
                <div className="lane-header">
                  <span className="lane-indicator"></span>
                  Income Sources
                </div>
                <div className="bar-list">
                  {topCategories.credit.map(([label, value]) => {
                    const maxVal = topCategories.credit[0]?.[1] || 1
                    return (
                      <div
                        key={label}
                        className="bar-item"
                        onClick={() => handleCategoryClick(label)}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="bar-info">
                          <span className="bar-label">{label}</span>
                          <span className="bar-value">{formatCurrency(value)}</span>
                        </div>
                        <div className="bar-track">
                          <div className="bar-fill credit" style={{ width: `${(value / maxVal) * 100}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
            {(direction === 'both' || direction === 'debit') && (
              <div className="split-lane debit">
                <div className="lane-header">
                  <span className="lane-indicator"></span>
                  Expense Categories
                </div>
                <div className="bar-list">
                  {topCategories.debit.map(([label, value]) => {
                    const maxVal = topCategories.debit[0]?.[1] || 1
                    return (
                      <div
                        key={label}
                        className="bar-item"
                        onClick={() => handleCategoryClick(label)}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="bar-info">
                          <span className="bar-label">{label}</span>
                          <span className="bar-value">{formatCurrency(value)}</span>
                        </div>
                        <div className="bar-track">
                          <div className="bar-fill debit" style={{ width: `${(value / maxVal) * 100}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Counterparties Panel */}
        <div className="insights-panel">
          <div className="insights-section-header">
            <h3>Counterparties</h3>
          </div>
          <div className="insights-split-content">
            {(direction === 'both' || direction === 'credit') && (
              <div className="split-lane credit">
                <div className="lane-header">
                  <span className="lane-indicator"></span>
                  Who Pays You
                </div>
                <div className="counterparty-list">
                  {topCounterparties.credit.map(([label, data]) => (
                    <div
                      key={label}
                      className="counterparty-item"
                      onClick={() => handleCounterpartyClick(label)}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="counterparty-name">{label}</div>
                      <div className="counterparty-stats">
                        <span className="counterparty-amount credit">{formatCurrency(data.total)}</span>
                        <span className="counterparty-count">{data.count}x</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(direction === 'both' || direction === 'debit') && (
              <div className="split-lane debit">
                <div className="lane-header">
                  <span className="lane-indicator"></span>
                  Where You Spend
                </div>
                <div className="counterparty-list">
                  {topCounterparties.debit.map(([label, data]) => (
                    <div
                      key={label}
                      className="counterparty-item"
                      onClick={() => handleCounterpartyClick(label)}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="counterparty-name">{label}</div>
                      <div className="counterparty-stats">
                        <span className="counterparty-amount debit">{formatCurrency(data.total)}</span>
                        <span className="counterparty-count">{data.count}x</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Transactions Explorer */}
      <section className="insights-explorer">
        <div className="insights-section-header">
          <h3>Transactions</h3>
          <span className="explorer-count">{filteredTransactions.length.toLocaleString()} records</span>
        </div>

        <div className="explorer-table-container">
          <table className="explorer-table">
            <thead>
              <tr>
                <th className="sortable" onClick={() => handleSort('date')}>
                  Date
                  {sortField === 'date' && <span className="sort-indicator">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                </th>
                <th>Description</th>
                <th>Direction</th>
                <th className="sortable" onClick={() => handleSort('amount')}>
                  Amount
                  {sortField === 'amount' && <span className="sort-indicator">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                </th>
                <th>Category</th>
              </tr>
            </thead>
            <tbody>
              {explorerItems.map((tx, idx) => {
                const isCredit = tx.amount >= 0
                return (
                  <tr key={`${tx.date}-${idx}`} className={isCredit ? 'row-credit' : 'row-debit'}>
                    <td className="cell-date">{tx.date}</td>
                    <td className="cell-desc">{tx.description}</td>
                    <td className="cell-direction">
                      <span className={`direction-badge ${isCredit ? 'credit' : 'debit'}`}>
                        {isCredit ? 'Credit' : 'Debit'}
                      </span>
                    </td>
                    <td className="cell-amount">{formatCurrency(Math.abs(tx.amount))}</td>
                    <td className="cell-category">
                      {tx.category && (
                        <button className="category-chip" onClick={() => handleCategoryClick(tx.category!)}>
                          {tx.category}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {explorerPageCount > 1 && (
          <div className="explorer-pagination">
            <button
              className="pagination-btn"
              onClick={() => setExplorerPage((p) => Math.max(0, p - 1))}
              disabled={explorerPage === 0}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
              Previous
            </button>
            <span className="pagination-info">
              Page {explorerPage + 1} of {explorerPageCount}
            </span>
            <button
              className="pagination-btn"
              onClick={() => setExplorerPage((p) => Math.min(explorerPageCount - 1, p + 1))}
              disabled={explorerPage >= explorerPageCount - 1}
            >
              Next
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
