import { useEffect, useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  BarElement,
  BarController,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js'
import { Chart, Line } from 'react-chartjs-2'
import api from '../api'
import CustomSelect from './CustomSelect'
import { useUI } from '../context/UIContext'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  BarElement,
  BarController,
  Tooltip,
  Filler,
  Legend,
)

function getDateRange(rangeType) {
  const today = new Date()
  let start = new Date()
  let end = new Date()
  
  // Set end date to yesterday (since YouTube analytics data has a 1-2 day delay)
  end.setDate(today.getDate() - 1)

  if (rangeType === '7days') {
    start.setDate(end.getDate() - 7)
  } else if (rangeType === '30days') {
    start.setDate(end.getDate() - 30)
  } else if (rangeType === 'current_month') {
    start = new Date(end.getFullYear(), end.getMonth(), 1)
  } else if (rangeType === 'last_month') {
    start = new Date(today.getFullYear(), today.getMonth() - 1, 1)
    end = new Date(today.getFullYear(), today.getMonth(), 0)
  } else if (rangeType === 'this_year') {
    start = new Date(end.getFullYear(), 0, 1)
  }

  const formatDate = (d) => {
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${d.getFullYear()}-${month}-${day}`
  }

  return { startDate: formatDate(start), endDate: formatDate(end) }
}

export default function AnalyticsPanel({ token, clientId, channelId, channelMeta }) {
  const [range, setRange] = useState('7days')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeChartTab, setActiveChartTab] = useState('views')
  const { toast } = useUI()
  
  const dates = useMemo(() => getDateRange(range), [range])

  useEffect(() => {
    if (!token || !channelId || !clientId) return
    let cancelled = false
    setLoading(true)

    ;(async () => {
      try {
        if (channelId === 'all') {
          // Fetch all channels under this client first
          const channelsRes = await api.listChannels(token, clientId)
          const channels = channelsRes.channels || []
          
          if (channels.length === 0) {
            if (!cancelled) {
              setData({ column_headers: ['day', 'views', 'likes', 'comments', 'estimatedMinutesWatched', 'averageViewDuration', 'subscribersGained', 'subscribersLost'], rows: [] })
              setLoading(false)
            }
            return
          }

          // Query analytics for all channels in parallel
          const analyticsPromises = channels.map((ch) =>
            api.analytics(token, {
              start_date: dates.startDate,
              end_date: dates.endDate,
              client_id: clientId,
              channel_id: ch.id,
            }).catch((err) => {
              console.warn(`Error loading analytics for channel ${ch.title}:`, err)
              return null // Return null so we can filter failed requests
            })
          )

          const results = await Promise.all(analyticsPromises)
          
          if (cancelled) return

          // Filter out failed or null results
          const validResults = results.filter((r) => r !== null)

          if (validResults.length === 0) {
            toast('Failed to load analytics for any linked channels.', 'error')
            setData({ column_headers: ['day', 'views', 'likes', 'comments', 'estimatedMinutesWatched', 'averageViewDuration', 'subscribersGained', 'subscribersLost'], rows: [] })
            setLoading(false)
            return
          }

          // Deep merge the analytics reports
          const mergedDict = {}
          
          validResults.forEach((report) => {
            const headers = report.column_headers || []
            const rows = report.rows || []
            
            const dayIdx = headers.indexOf('day')
            const viewsIdx = headers.indexOf('views')
            const likesIdx = headers.indexOf('likes')
            const commentsIdx = headers.indexOf('comments')
            const watchIdx = headers.indexOf('estimatedMinutesWatched')
            const avgDurationIdx = headers.indexOf('averageViewDuration')
            const subsGainedIdx = headers.indexOf('subscribersGained')
            const subsLostIdx = headers.indexOf('subscribersLost')

            rows.forEach((row) => {
              const dayVal = row[dayIdx]
              const viewsVal = Number(row[viewsIdx] || 0)
              const likesVal = Number(row[likesIdx] || 0)
              const commentsVal = Number(row[commentsIdx] || 0)
              const watchVal = Number(row[watchIdx] || 0)
              const avgDurationVal = Number(row[avgDurationIdx] || 0)
              const subsGainedVal = subsGainedIdx !== -1 ? Number(row[subsGainedIdx] || 0) : 0
              const subsLostVal = subsLostIdx !== -1 ? Number(row[subsLostIdx] || 0) : 0

              if (!mergedDict[dayVal]) {
                mergedDict[dayVal] = {
                  day: dayVal,
                  views: viewsVal,
                  likes: likesVal,
                  comments: commentsVal,
                  estimatedMinutesWatched: watchVal,
                  averageViewDurationTotalWeight: avgDurationVal * viewsVal,
                  viewsForWeight: viewsVal,
                  subscribersGained: subsGainedVal,
                  subscribersLost: subsLostVal,
                }
              } else {
                mergedDict[dayVal].views += viewsVal
                mergedDict[dayVal].likes += likesVal
                mergedDict[dayVal].comments += commentsVal
                mergedDict[dayVal].estimatedMinutesWatched += watchVal
                mergedDict[dayVal].averageViewDurationTotalWeight += avgDurationVal * viewsVal
                mergedDict[dayVal].viewsForWeight += viewsVal
                mergedDict[dayVal].subscribersGained += subsGainedVal
                mergedDict[dayVal].subscribersLost += subsLostVal
              }
            })
          })

          // Build merged rows and columns
          const finalRows = Object.values(mergedDict).map((item) => {
            const avgDuration = item.viewsForWeight > 0 
              ? Math.round(item.averageViewDurationTotalWeight / item.viewsForWeight) 
              : 0
            return [
              item.day,
              item.views,
              item.comments,
              item.likes,
              0, // placeholder for dislikes if exists
              0, // placeholder for shares
              item.estimatedMinutesWatched,
              avgDuration,
              item.subscribersGained,
              item.subscribersLost,
            ]
          })

          // Sort chronologically by date
          finalRows.sort((a, b) => String(a[0]).localeCompare(String(b[0])))

          const columnHeaders = [
            'day',
            'views',
            'comments',
            'likes',
            'dislikes',
            'shares',
            'estimatedMinutesWatched',
            'averageViewDuration',
            'subscribersGained',
            'subscribersLost',
          ]

          setData({ column_headers: columnHeaders, rows: finalRows })
        } else {
          // Fetch analytics for a single channel
          const result = await api.analytics(token, {
            start_date: dates.startDate,
            end_date: dates.endDate,
            client_id: clientId,
            channel_id: channelId,
          })
          if (!cancelled) setData(result)
        }
      } catch (err) {
        console.error(err)
        toast(`Analytics Error: ${err.message}`, 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [token, clientId, channelId, dates.startDate, dates.endDate, toast])

  const headers = data?.column_headers || []
  const rows = data?.rows || []
  const dayIdx = headers.indexOf('day')
  const viewsIdx = headers.indexOf('views')
  const likesIdx = headers.indexOf('likes')
  const commentsIdx = headers.indexOf('comments')
  const watchIdx = headers.indexOf('estimatedMinutesWatched')
  const avgDurationIdx = headers.indexOf('averageViewDuration')
  const subsGainedIdx = headers.indexOf('subscribersGained')
  const subsLostIdx = headers.indexOf('subscribersLost')

  let totalViews = 0
  let totalWatchTime = 0
  rows.forEach((row) => {
    totalViews += Number(row[viewsIdx] || 0)
    totalWatchTime += Number(row[watchIdx] || 0)
  })

  const chronological = useMemo(() => {
    return [...rows].sort((a, b) => String(a[dayIdx]).localeCompare(String(b[dayIdx])))
  }, [rows, dayIdx])

  const processedSubscriberData = useMemo(() => {
    if (chronological.length === 0) return { subsHistory: [], totalDiff: 0 }

    const currentSubs = Number(channelMeta?.subscriber_count || 0)
    let runningSubs = currentSubs
    const subsHistory = new Array(chronological.length)

    for (let i = chronological.length - 1; i >= 0; i--) {
      const row = chronological[i]
      const dayVal = row[dayIdx]
      const gained = subsGainedIdx !== -1 ? Number(row[subsGainedIdx] || 0) : 0
      const lost = subsLostIdx !== -1 ? Number(row[subsLostIdx] || 0) : 0
      const diff = gained - lost

      subsHistory[i] = {
        day: dayVal,
        diff: diff,
        subs: runningSubs,
      }

      runningSubs = runningSubs - diff
    }

    const totalDiff = subsHistory.reduce((sum, item) => sum + item.diff, 0)
    return { subsHistory, totalDiff }
  }, [chronological, dayIdx, subsGainedIdx, subsLostIdx, channelMeta?.subscriber_count])

  const chartData = useMemo(() => {
    if (activeChartTab === 'subscribers') {
      const subCounts = processedSubscriberData.subsHistory.map((h) => h.subs)
      const dailyDiffs = processedSubscriberData.subsHistory.map((h) => h.diff)
      return {
        labels: chronological.map((r) => r[dayIdx]),
        datasets: [
          {
            type: 'line',
            label: 'Total subscribers',
            data: subCounts,
            borderColor: '#0ea5e9',
            backgroundColor: 'rgba(14, 165, 233, 0.05)',
            borderWidth: 3,
            pointBackgroundColor: '#0ea5e9',
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            fill: true,
            tension: 0.35,
            yAxisID: 'y',
            order: 1,
          },
          {
            type: 'bar',
            label: 'Daily net change',
            data: dailyDiffs,
            backgroundColor: dailyDiffs.map((d) =>
              d >= 0 ? 'rgba(16, 185, 129, 0.55)' : 'rgba(239, 68, 68, 0.55)',
            ),
            borderColor: dailyDiffs.map((d) => (d >= 0 ? '#10b981' : '#ef4444')),
            borderWidth: 1,
            borderRadius: 4,
            yAxisID: 'y1',
            order: 2,
          },
        ],
      }
    }

    return {
      labels: chronological.map((r) => r[dayIdx]),
      datasets: [
        {
          label: 'Views',
          data: chronological.map((r) => Number(r[viewsIdx] || 0)),
          borderColor: '#4f46e5',
          backgroundColor: 'rgba(79, 70, 229, 0.05)',
          borderWidth: 3,
          pointBackgroundColor: '#4f46e5',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          fill: true,
          tension: 0.35,
        },
      ],
    }
  }, [chronological, dayIdx, viewsIdx, activeChartTab, processedSubscriberData.subsHistory])

  const chartOptions = useMemo(() => {
    const isSubs = activeChartTab === 'subscribers'
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: isSubs,
          position: 'top',
          align: 'end',
          labels: {
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            pointStyle: 'rectRounded',
            color: '#64748b',
            font: { family: 'Inter', size: 12, weight: '600' },
          },
        },
        tooltip: {
          backgroundColor: '#1e293b',
          titleFont: { family: 'Inter', size: 12, weight: '600' },
          bodyFont: { family: 'Inter', size: 13 },
          padding: 12,
          borderRadius: 8,
          displayColors: isSubs,
          callbacks: {
            label: function (context) {
              if (!isSubs) {
                return `Views: ${context.parsed.y.toLocaleString()}`
              }
              const value = context.parsed.y
              if (context.dataset.label === 'Daily net change') {
                const sign = value > 0 ? '+' : ''
                return `Daily change: ${sign}${value.toLocaleString()}`
              }
              return `Subscribers: ${value.toLocaleString()}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(226, 232, 240, 0.6)', drawBorder: false },
          ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
          title: isSubs
            ? {
                display: true,
                text: 'Total subscribers',
                color: '#94a3b8',
                font: { family: 'Inter', size: 11, weight: '600' },
              }
            : undefined,
        },
        ...(isSubs
          ? {
              y1: {
                position: 'right',
                grid: { drawOnChartArea: false },
                ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
                title: {
                  display: true,
                  text: 'Daily net change',
                  color: '#94a3b8',
                  font: { family: 'Inter', size: 11, weight: '600' },
                },
              },
            }
          : {}),
      },
    }
  }, [activeChartTab])

  const rangeOptions = [
    { value: '7days', label: 'Last 7 Days', icon: <i className="fa-solid fa-calendar-day" /> },
    { value: '30days', label: 'Last 30 Days', icon: <i className="fa-solid fa-calendar-days" /> },
    { value: 'current_month', label: 'This Month', icon: <i className="fa-solid fa-calendar-check" /> },
    { value: 'last_month', label: 'Last Month', icon: <i className="fa-solid fa-calendar" /> },
    { value: 'this_year', label: 'This Year', icon: <i className="fa-solid fa-calendar-minus" /> },
  ]

  return (
    <div className="analytics-panel animate-fade-in">
      <div className="range-selector-row">
        <div className="range-dropdown-wrapper">
          <span className="control-label">Range Filter</span>
          <CustomSelect
            options={rangeOptions}
            value={range}
            onChange={setRange}
            placeholder="Select Range"
            icon={<i className="fa-solid fa-calendar-days" />}
            className="range-select"
          />
        </div>
        <div className="date-display-badge">
          <i className="fa-solid fa-clock-rotate-left" />
          <span>{dates.startDate} to {dates.endDate}</span>
        </div>
      </div>

      {loading ? (
        <div className="analytics-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Calculating analytics report...</span>
          </div>
        </div>
      ) : (
        <>
          <div className="stats-grid">
            <div className="stat-card card">
              <div className="stat-card-header">
                <span className="stat-label">Total Views</span>
                <span className="stat-icon-wrapper views"><i className="fa-solid fa-eye" /></span>
              </div>
              <div className="stat-value">{totalViews.toLocaleString()}</div>
              <div className="stat-meta">Across selected date range</div>
            </div>
            
            <div className="stat-card card">
              <div className="stat-card-header">
                <span className="stat-label">Subscribers</span>
                <span className="stat-icon-wrapper sub"><i className="fa-solid fa-users" /></span>
              </div>
              <div className="stat-value">
                {channelMeta ? Number(channelMeta.subscriber_count).toLocaleString() : '—'}
              </div>
              <div className="stat-meta">
                {processedSubscriberData.totalDiff > 0 ? (
                  <span style={{ color: '#10b981', fontWeight: 600 }}>
                    +{processedSubscriberData.totalDiff.toLocaleString()} in range
                  </span>
                ) : processedSubscriberData.totalDiff < 0 ? (
                  <span style={{ color: '#ef4444', fontWeight: 600 }}>
                    {processedSubscriberData.totalDiff.toLocaleString()} in range
                  </span>
                ) : (
                  <span>{channelId === 'all' ? 'All channels combined' : 'Lifetime total'}</span>
                )}
              </div>
            </div>
            
            <div className="stat-card card">
              <div className="stat-card-header">
                <span className="stat-label">Watch Time</span>
                <span className="stat-icon-wrapper watch"><i className="fa-solid fa-clock" /></span>
              </div>
              <div className="stat-value">{totalWatchTime.toLocaleString()}</div>
              <div className="stat-meta">Minutes in selected range</div>
            </div>
            
            <div className="stat-card card">
              <div className="stat-card-header">
                <span className="stat-label">Videos Library</span>
                <span className="stat-icon-wrapper videos"><i className="fa-solid fa-video" /></span>
              </div>
              <div className="stat-value">
                {channelMeta ? Number(channelMeta.video_count).toLocaleString() : '—'}
              </div>
              <div className="stat-meta">
                {channelId === 'all' ? 'Total videos across channels' : 'Lifetime total'}
              </div>
            </div>
          </div>

          <div className="chart-section card">
            <div className="chart-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
              <div className="chart-header" style={{ marginBottom: 0 }}>
                <h2 className="section-title">
                  {activeChartTab === 'views' ? 'Views Performance over Time' : 'Subscribers Growth over Time'}
                </h2>
                <span className="chart-subtitle">
                  {activeChartTab === 'views'
                    ? 'Aggregated daily view metrics'
                    : 'Total subscribers plus day-wise net change'}
                </span>
              </div>
              <div className="chart-toggle-tabs" style={{ display: 'flex', background: '#f1f5f9', padding: '4px', borderRadius: '8px' }}>
                <button
                  type="button"
                  onClick={() => setActiveChartTab('views')}
                  style={{
                    padding: '6px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    fontWeight: '600',
                    fontSize: '13px',
                    cursor: 'pointer',
                    background: activeChartTab === 'views' ? '#ffffff' : 'transparent',
                    color: activeChartTab === 'views' ? '#4f46e5' : '#64748b',
                    boxShadow: activeChartTab === 'views' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    transition: 'all 0.2s',
                  }}
                >
                  <i className="fa-solid fa-eye" style={{ marginRight: '6px' }} /> Views
                </button>
                <button
                  type="button"
                  onClick={() => setActiveChartTab('subscribers')}
                  style={{
                    padding: '6px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    fontWeight: '600',
                    fontSize: '13px',
                    cursor: 'pointer',
                    background: activeChartTab === 'subscribers' ? '#ffffff' : 'transparent',
                    color: activeChartTab === 'subscribers' ? '#0ea5e9' : '#64748b',
                    boxShadow: activeChartTab === 'subscribers' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    transition: 'all 0.2s',
                  }}
                >
                  <i className="fa-solid fa-users" style={{ marginRight: '6px' }} /> Subscribers
                </button>
              </div>
            </div>
            <div className="chart-container">
              {chronological.length === 0 ? (
                <div className="no-chart-data text-muted">
                  <i className="fa-solid fa-chart-line" />
                  <p>No viewer data available for the selected dates.</p>
                </div>
              ) : activeChartTab === 'subscribers' ? (
                <Chart type="bar" data={chartData} options={chartOptions} />
              ) : (
                <Line data={chartData} options={chartOptions} />
              )}
            </div>
          </div>

          <div className="table-section card">
            <h2 className="section-title">Daily Metrics breakdown</h2>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Views</th>
                    <th>Likes</th>
                    <th>Comments</th>
                    <th>Watch Time (Min)</th>
                    <th>Avg Duration</th>
                    <th>Subscribers</th>
                    <th>Gained</th>
                    <th>Lost</th>
                    <th>Net Change</th>
                  </tr>
                </thead>
                <tbody>
                  {chronological.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="text-center text-muted py-8">
                        <i className="fa-solid fa-database block mb-2" style={{ fontSize: '20px', opacity: 0.5 }} />
                        No stats record found.
                      </td>
                    </tr>
                  ) : (
                    chronological.map((row, index) => {
                      const subData = processedSubscriberData.subsHistory[index] || { subs: '—', diff: 0 }
                      const gained = subsGainedIdx !== -1 ? Number(row[subsGainedIdx] || 0) : 0
                      const lost = subsLostIdx !== -1 ? Number(row[subsLostIdx] || 0) : 0
                      return (
                        <tr key={row[dayIdx]}>
                          <td>
                            <span className="table-date-badge">{row[dayIdx]}</span>
                          </td>
                          <td>
                            <strong>{Number(row[viewsIdx] || 0).toLocaleString()}</strong>
                          </td>
                          <td>{Number(row[likesIdx] || 0).toLocaleString()}</td>
                          <td>{Number(row[commentsIdx] || 0).toLocaleString()}</td>
                          <td>{Number(row[watchIdx] || 0).toLocaleString()} min</td>
                          <td>{Number(row[avgDurationIdx] || 0).toLocaleString()}s</td>
                          <td>
                            <strong>{typeof subData.subs === 'number' ? subData.subs.toLocaleString() : subData.subs}</strong>
                          </td>
                          <td>
                            {gained > 0 ? (
                              <span style={{ color: '#10b981', fontWeight: 600 }}>+{gained.toLocaleString()}</span>
                            ) : (
                              <span className="text-muted">0</span>
                            )}
                          </td>
                          <td>
                            {lost > 0 ? (
                              <span style={{ color: '#ef4444', fontWeight: 600 }}>-{lost.toLocaleString()}</span>
                            ) : (
                              <span className="text-muted">0</span>
                            )}
                          </td>
                          <td>
                            {subData.diff > 0 ? (
                              <span style={{ color: '#10b981', fontWeight: 'bold', display: 'inline-flex', alignItems: 'center' }}>
                                <i className="fa-solid fa-arrow-trend-up" style={{ marginRight: '4px' }} />
                                +{subData.diff.toLocaleString()}
                              </span>
                            ) : subData.diff < 0 ? (
                              <span style={{ color: '#ef4444', fontWeight: 'bold', display: 'inline-flex', alignItems: 'center' }}>
                                <i className="fa-solid fa-arrow-trend-down" style={{ marginRight: '4px' }} />
                                {subData.diff.toLocaleString()}
                              </span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
