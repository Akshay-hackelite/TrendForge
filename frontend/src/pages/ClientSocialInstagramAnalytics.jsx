import { useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useUI } from '../context/UIContext'
import { useAuth } from '../context/AuthContext'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Filler,
  Legend,
)

const CARD = {
  background: '#fff',
  border: '1px solid #f1f5f9',
  borderRadius: 16,
  padding: 24,
  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -2px rgba(0,0,0,0.02)',
}

const CONTENT_TYPES = [
  { id: 'posts', label: 'Posts' },
  { id: 'reels', label: 'Reels' },
  { id: 'stories', label: 'Stories' },
]

function fmtNum(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString()
}

function fmtPct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(1)}%`
}

function fmtWatch(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—'
  const n = Number(seconds)
  if (n >= 60) {
    const m = Math.floor(n / 60)
    const s = Math.round(n % 60)
    return `${m}m ${s}s`
  }
  return `${n % 1 === 0 ? n : n.toFixed(1)}s`
}

function shareOf(part, total) {
  const t = Number(total) || 0
  if (t <= 0) return null
  return ((Number(part) || 0) / t) * 100
}

function skipColor(rate) {
  if (rate == null) return '#64748b'
  if (rate >= 50) return '#ef4444'
  if (rate >= 35) return '#d97706'
  return '#10b981'
}

function captionLabel(reel) {
  const text = (reel?.caption || '').replace(/\s+/g, ' ').trim()
  if (text) return text.length > 42 ? `${text.slice(0, 42)}…` : text
  const d = reel?.timestamp ? new Date(reel.timestamp) : null
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
    : 'Reel'
}

function ContentMixBars({ data, total }) {
  if (!data) return null
  const sum = Number(total) || CONTENT_TYPES.reduce((acc, t) => acc + (Number(data[t.id]) || 0), 0)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 2 }}>
      {CONTENT_TYPES.map((t) => {
        const value = Number(data[t.id]) || 0
        const pct = shareOf(value, sum)
        return (
          <div key={t.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
              <span style={{ color: '#64748b' }}>{t.label}</span>
              <span style={{ fontWeight: 600, color: '#0f172a' }}>
                {fmtNum(value)}{pct == null ? '' : ` · ${pct.toFixed(1)}%`}
              </span>
            </div>
            <div style={{ height: 6, background: '#f1f5f9', borderRadius: 99, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, pct || 0)}%`,
                  height: '100%',
                  background: t.id === 'reels' ? '#6366f1' : t.id === 'posts' ? '#f59e0b' : '#10b981',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function RateRow({ label, value, warn }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '6px 0' }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ fontWeight: 600, color: warn ? skipColor(value) : '#0f172a' }}>{fmtPct(value)}</span>
    </div>
  )
}

function IconChip({ bg, color, icon }) {
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 8, background: bg, color,
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <i className={icon} />
    </div>
  )
}

function StackedStat({ title, value, caption, icon, iconBg, iconColor }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.05em', marginBottom: 12, textTransform: 'uppercase' }}>{title}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <h2 style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', margin: 0 }}>{value}</h2>
        <IconChip bg={iconBg} color={iconColor} icon={icon} />
      </div>
      {caption ? <div style={{ marginTop: 12, fontSize: 13, color: '#64748b', lineHeight: 1.45 }}>{caption}</div> : null}
    </div>
  )
}

function MetricBox({ icon, label, value, valueColor }) {
  return (
    <div style={{ background: '#f8fafc', borderRadius: 10, padding: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>{label}</div>
        <i className={icon} style={{ color: '#94a3b8', fontSize: 12 }} />
      </div>
      <div style={{ fontSize: 18, fontWeight: 800, color: valueColor || '#0f172a' }}>{value}</div>
    </div>
  )
}

export default function ClientSocialInstagramAnalytics() {
  const { clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()
  const [metrics, setMetrics] = useState(null)
  const [timeSeries, setTimeSeries] = useState(null)
  const [viewsByFollowType, setViewsByFollowType] = useState(null)
  const [viewsByContentType, setViewsByContentType] = useState(null)
  const [interactionsByContentType, setInteractionsByContentType] = useState(null)
  const [reels, setReels] = useState([])
  const [reelSummary, setReelSummary] = useState(null)
  const [openReelId, setOpenReelId] = useState(null)
  const [dailyOpen, setDailyOpen] = useState(true)
  const [loadingAnalytics, setLoadingAnalytics] = useState(false)
  const [showDatePicker, setShowDatePicker] = useState(false)
  const [activeChart, setActiveChart] = useState('reach')
  const [connected, setConnected] = useState(false)
  const [checkedConnection, setCheckedConnection] = useState(false)

  const fmtDate = (d) => d.toISOString().slice(0, 10)
  const today = new Date()
  const [sinceDate, setSinceDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return fmtDate(d)
  })
  const [untilDate, setUntilDate] = useState(() => fmtDate(today))
  const [activePreset, setActivePreset] = useState(7)

  function setPreset(preset) {
    let end = new Date()
    let start = new Date()

    if (typeof preset === 'number') {
      start.setDate(start.getDate() - preset)
    } else if (preset === 'this_month') {
      start = new Date(end.getFullYear(), end.getMonth(), 1)
    } else if (preset === 'last_month') {
      start = new Date(end.getFullYear(), end.getMonth() - 1, 1)
      end = new Date(end.getFullYear(), end.getMonth(), 0)
    }
    setSinceDate(fmtDate(start))
    setUntilDate(fmtDate(end))
    setActivePreset(preset)
  }

  useEffect(() => {
    if (!token || !clientId) return
    let cancelled = false
    setLoadingAnalytics(true)
    ;(async () => {
      try {
        const data = await api.getInstagramAnalytics(token, clientId, { since: sinceDate, until: untilDate })
        if (!cancelled) {
          setConnected(Boolean(data.instagram_connected))
          setCheckedConnection(true)
          setMetrics(data.metrics || null)
          setTimeSeries(data.time_series || null)
          setViewsByFollowType(data.views_by_follow_type || null)
          setViewsByContentType(data.views_by_content_type || null)
          setInteractionsByContentType(data.interactions_by_content_type || null)
          setReels(Array.isArray(data.reels) ? data.reels : [])
          setReelSummary(data.reel_summary || null)
          setOpenReelId((data.reels || [])[0]?.id || null)
        }
      } catch (err) {
        if (!cancelled) {
          setCheckedConnection(true)
          toast(err.message || 'Failed to load Instagram analytics', 'error')
        }
      } finally {
        if (!cancelled) setLoadingAnalytics(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, clientId, sinceDate, untilDate, toast])

  const reachTs = timeSeries?.reach || []
  const followerTs = timeSeries?.follower_count || []
  const netFollowers = followerTs.reduce((acc, cur) => acc + (Number(cur.value) || 0), 0)

  const chartLabels = reachTs.map((v) => {
    if (!v.end_time) return ''
    const d = new Date(v.end_time)
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  })

  let currentData = []
  let activeColor = '#6366f1'
  let fillColor = 'rgba(99, 102, 241, 0.15)'

  if (activeChart === 'reach') {
    currentData = reachTs.map((v) => v.value)
    activeColor = '#6366f1'
    fillColor = 'rgba(99, 102, 241, 0.15)'
  } else {
    currentData = followerTs.map((v) => v.value)
    activeColor = '#8b5cf6'
    fillColor = 'rgba(139, 92, 246, 0.15)'
  }

  const chartData = {
    labels: chartLabels.length ? chartLabels : ['No data'],
    datasets: [{
      label: activeChart === 'reach' ? 'Reach' : 'New Followers',
      data: currentData,
      borderColor: activeColor,
      backgroundColor: (context) => {
        const ctx = context.chart.ctx
        const gradient = ctx.createLinearGradient(0, 0, 0, 300)
        gradient.addColorStop(0, fillColor)
        gradient.addColorStop(1, `${activeColor}00`)
        return gradient
      },
      fill: true,
      tension: 0.4,
      pointBackgroundColor: '#fff',
      pointBorderColor: activeColor,
      pointBorderWidth: 2,
      pointRadius: chartLabels.length > 40 ? 0 : 4,
      pointHoverRadius: 6,
    }],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1e293b',
        padding: 12,
        titleFont: { size: 13, family: 'Inter' },
        bodyFont: { size: 14, weight: 'bold', family: 'Inter' },
        displayColors: false,
        cornerRadius: 8,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          color: '#64748b',
          font: { family: 'Inter', size: 12 },
          maxTicksLimit: chartLabels.length > 40 ? 10 : 14,
          maxRotation: chartLabels.length > 60 ? 40 : 0,
        },
        border: { display: false },
      },
      y: { grid: { color: '#f1f5f9' }, ticks: { color: '#94a3b8', font: { family: 'Inter', size: 12 }, maxTicksLimit: 6 }, border: { display: false } },
    },
    interaction: { intersect: false, mode: 'index' },
  }

  const dailyRows = useMemo(() => {
    return reachTs.map((point, i) => {
      const end = point.end_time || ''
      const d = end ? new Date(end) : null
      const valid = d && !Number.isNaN(d.getTime())
      return {
        key: end || String(i),
        date: valid
          ? d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
          : '',
        reach: Number(point.value) || 0,
        followers: Number(followerTs[i]?.value) || 0,
      }
    }).reverse()
  }, [reachTs, followerTs])

  const netReach = dailyRows.reduce((acc, row) => acc + (Number(row.reach) || 0), 0)
  const avgDailyReach = dailyRows.length ? Math.round(netReach / dailyRows.length) : 0

  const reelBarData = useMemo(() => {
    const top = (reels || []).slice(0, 8)
    if (!top.length) return null
    return {
      labels: top.map(captionLabel),
      datasets: [{
        label: 'Views',
        data: top.map((r) => Number(r.views) || 0),
        backgroundColor: 'rgba(99, 102, 241, 0.75)',
        borderRadius: 6,
      }],
    }
  }, [reels])

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1e293b',
        padding: 12,
        displayColors: false,
        cornerRadius: 8,
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#64748b', font: { family: 'Inter', size: 11 }, maxRotation: 40 } },
      y: { grid: { color: '#f1f5f9' }, ticks: { color: '#94a3b8' }, border: { display: false } },
    },
  }

  if (!checkedConnection) {
    return (
      <div className="animate-fade-in" style={{ padding: 24 }}>
        <p className="text-muted">Loading Instagram analytics…</p>
      </div>
    )
  }

  if (!connected) {
    return (
      <div className="animate-fade-in" style={{ padding: 24, maxWidth: 720 }}>
        <header className="content-header" style={{ marginBottom: 24 }}>
          <div className="greeting">
            <Breadcrumbs
              items={[
                { label: 'Clients', to: '/clients' },
                { label: 'Social', to: `/clients/${clientId}/social` },
                { label: 'Instagram Analytics' },
              ]}
            />
            <h1>Instagram Analytics</h1>
            <p className="text-muted">Connect Instagram to unlock reach, engagement, and reel insights.</p>
          </div>
        </header>
        <div className="card" style={{ padding: 32, textAlign: 'center' }}>
          <i className="fa-brands fa-instagram" style={{ fontSize: 40, color: '#e1306c' }} />
          <h2 style={{ marginTop: 16 }}>Instagram is not connected</h2>
          <p className="text-muted">
            Use the Instagram Connection page to add your Meta App and authorize insights.
          </p>
          <Link className="btn btn-primary" to={`/clients/${clientId}/social/instagram`}>
            Open Instagram Connection
          </Link>
        </div>
      </div>
    )
  }

  const loadingOverlay = loadingAnalytics
    ? { position: 'relative', pointerEvents: 'none', opacity: 0.6, transition: 'opacity 0.2s' }
    : { transition: 'opacity 0.2s' }

  const PRESETS = [
    { id: 7, label: 'Last 7 Days' },
    { id: 14, label: 'Last 14 Days' },
    { id: 30, label: 'Last 30 Days' },
    { id: 90, label: 'Last 90 Days' },
    { id: 'this_month', label: 'This Month' },
    { id: 'last_month', label: 'Last Month' },
  ]
  const activeObj = PRESETS.find((p) => p.id === activePreset)
  const periodLabel = activeObj ? activeObj.label : 'Custom Range'

  const viewsTotal = Number(metrics?.views) || 0
  const followerViews = Number(viewsByFollowType?.follower) || 0
  const nonFollowerViews = Number(viewsByFollowType?.non_follower) || 0
  const unknownViews = Number(viewsByFollowType?.unknown) || 0
  const followDenom = followerViews + nonFollowerViews + unknownViews || viewsTotal

  return (
    <div className="animate-fade-in" style={{ padding: '0 24px 48px', maxWidth: 1200, margin: '0 auto', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, paddingTop: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: '#0f172a', margin: '0 0 4px 0' }}>Instagram Analytics</h1>
          <p style={{ margin: 0, color: '#64748b', fontSize: 14 }}>Overview of your Instagram performance</p>
        </div>
        <Link
          to={`/clients/${clientId}/social/instagram`}
          className="btn btn-secondary"
          style={{ background: '#fff', border: '1px solid #e2e8f0', color: '#64748b', borderRadius: 8, padding: '8px 16px', fontWeight: 500 }}
        >
          <i className="fa-brands fa-instagram" style={{ marginRight: 8, color: '#e1306c' }} />
          Connection
        </Link>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, position: 'relative' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.05em', marginBottom: 6, textTransform: 'uppercase' }}>Range Filter</div>
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowDatePicker(!showDatePicker)}
              disabled={loadingAnalytics}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, background: '#fff', border: '1px solid #cbd5e1',
                padding: '8px 16px', borderRadius: 8, cursor: 'pointer', color: '#334155', fontWeight: 500, fontSize: 14,
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)', minWidth: 160, justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <i className="fa-regular fa-calendar" style={{ color: '#6366f1' }} />
                {periodLabel}
              </div>
              <i className={`fa-solid fa-chevron-${showDatePicker ? 'up' : 'down'}`} style={{ fontSize: 10, color: '#94a3b8' }} />
            </button>
            {showDatePicker && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, marginTop: 8, background: '#fff',
                border: '1px solid #e2e8f0', borderRadius: 12, padding: 8, boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)',
                zIndex: 100, width: 280, display: 'flex', flexDirection: 'column', gap: 4,
              }}>
                {PRESETS.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => { setPreset(p.id); setShowDatePicker(false) }}
                    style={{
                      padding: '10px 16px', background: activePreset === p.id ? '#f8fafc' : 'transparent', border: 'none',
                      borderRadius: 8, textAlign: 'left', cursor: 'pointer', fontSize: 13, color: activePreset === p.id ? '#6366f1' : '#475569',
                      fontWeight: activePreset === p.id ? 600 : 500, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}
                  >
                    {p.label}
                    {activePreset === p.id && <i className="fa-solid fa-check" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fff', padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, color: '#64748b' }}>
          <i className="fa-solid fa-clock-rotate-left" style={{ color: '#94a3b8' }} />
          {sinceDate} to {untilDate}
        </div>
      </div>

      {loadingAnalytics && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12, background: '#eff6ff', color: '#3b82f6', borderRadius: 8, marginBottom: 24, fontSize: 14, fontWeight: 500 }}>
          <i className="fa-solid fa-circle-notch fa-spin" style={{ marginRight: 8 }} /> Refreshing data...
        </div>
      )}

      <div style={loadingOverlay}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20, marginBottom: 24 }}>
          <div style={{ ...CARD, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Views</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <h2 style={{ fontSize: 32, fontWeight: 800, color: '#0f172a', margin: 0 }}>{fmtNum(metrics?.views)}</h2>
              <IconChip bg="#e0e7ff" color="#4f46e5" icon="fa-solid fa-play" />
            </div>
            <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.45 }}>Times content was played or shown</div>
            {viewsByFollowType && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#64748b' }}>Followers</span>
                  <span style={{ fontWeight: 600 }}>{fmtNum(followerViews)} · {fmtPct(shareOf(followerViews, followDenom))}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#64748b' }}>Non-followers</span>
                  <span style={{ fontWeight: 600 }}>{fmtNum(nonFollowerViews)} · {fmtPct(shareOf(nonFollowerViews, followDenom))}</span>
                </div>
                {unknownViews > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Unknown</span>
                    <span style={{ fontWeight: 600 }}>{fmtNum(unknownViews)} · {fmtPct(shareOf(unknownViews, followDenom))}</span>
                  </div>
                )}
              </div>
            )}
            {viewsByContentType && <ContentMixBars data={viewsByContentType} total={viewsTotal} />}
          </div>

          <div style={{ ...CARD, display: 'flex', flexDirection: 'column', gap: 20 }} title="Unique accounts who saw your content. Instagram’s Viewers number on the Views tab is a different metric.">
            <StackedStat
              title="Accounts Reached"
              value={fmtNum(metrics?.reach)}
              caption="Unique accounts in range"
              icon="fa-solid fa-users"
              iconBg="#e0e7ff"
              iconColor="#4f46e5"
            />
            <div style={{ height: 1, background: '#f1f5f9' }} />
            <StackedStat
              title="Accounts Engaged"
              value={fmtNum(metrics?.accounts_engaged)}
              caption="Unique people who interacted"
              icon="fa-solid fa-handshake"
              iconBg="#fae8ff"
              iconColor="#a21caf"
            />
          </div>

          <div style={{ ...CARD, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Total Interactions</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <h2 style={{ fontSize: 32, fontWeight: 800, color: '#0f172a', margin: 0 }}>{fmtNum(metrics?.total_interactions)}</h2>
              <IconChip bg="#fef3c7" color="#d97706" icon="fa-solid fa-heart" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Likes</span>
                <span style={{ fontWeight: 600, color: '#0f172a' }}>{fmtNum(metrics?.likes)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Comments</span>
                <span style={{ fontWeight: 600, color: '#0f172a' }}>{fmtNum(metrics?.comments)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Shares</span>
                <span style={{ fontWeight: 600, color: '#0f172a' }}>{fmtNum(metrics?.shares)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Saves</span>
                <span style={{ fontWeight: 600, color: '#0f172a' }}>{fmtNum(metrics?.saves)}</span>
              </div>
            </div>
            {interactionsByContentType && (
              <ContentMixBars data={interactionsByContentType} total={metrics?.total_interactions} />
            )}
          </div>

          <div style={{ ...CARD, display: 'flex', flexDirection: 'column', gap: 20 }}>
            <StackedStat
              title="Profile Views"
              value={fmtNum(metrics?.profile_views)}
              caption="Profile page visits"
              icon="fa-regular fa-eye"
              iconBg="#d1fae5"
              iconColor="#059669"
            />
            <div style={{ height: 1, background: '#f1f5f9' }} />
            <StackedStat
              title="Net Follows"
              value={netFollowers.toLocaleString()}
              caption="Total new followers in range"
              icon="fa-solid fa-user-plus"
              iconBg="#fce7f3"
              iconColor="#db2777"
            />
          </div>
        </div>

        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: '24px 24px 32px', marginBottom: 24, boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32 }}>
            <div>
              <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Performance over Time</h3>
              <p style={{ margin: 0, fontSize: 13, color: '#64748b' }}>Daily reach and new followers. Meta does not provide a daily views line.</p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {[
                { id: 'reach', label: 'Reach', icon: 'fa-users' },
                { id: 'followers', label: 'Followers', icon: 'fa-user-plus' },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveChart(t.id)}
                  style={{
                    border: 'none', background: activeChart === t.id ? '#fff' : 'transparent',
                    boxShadow: activeChart === t.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    color: activeChart === t.id ? '#0f172a' : '#64748b',
                    fontWeight: activeChart === t.id ? 600 : 500,
                    padding: '6px 14px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <i className={`fa-solid ${t.icon}`} style={{ color: activeChart === t.id ? activeColor : '#94a3b8' }} />
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ height: 350, width: '100%' }}>
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>

        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 24, boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)', marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: dailyOpen ? 20 : 0, flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Daily Metrics breakdown</h3>
              <p style={{ margin: 0, fontSize: 13, color: '#64748b' }}>
                Daily reach and new followers. Meta does not provide a daily views breakdown.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(120px, 140px))', gap: 10 }}>
                {[
                  { label: 'Days', value: fmtNum(dailyRows.length) },
                  { label: 'Avg daily reach', value: fmtNum(avgDailyReach) },
                  { label: 'Net follows', value: `${netFollowers > 0 ? '+' : ''}${netFollowers.toLocaleString()}` },
                ].map((item) => (
                  <div key={item.label} style={{ background: '#f8fafc', borderRadius: 12, padding: '12px 14px', minWidth: 120 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{item.label}</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', marginTop: 6 }}>{item.value}</div>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setDailyOpen((open) => !open)}
                aria-expanded={dailyOpen}
                aria-label={dailyOpen ? 'Collapse daily metrics' : 'Expand daily metrics'}
                style={{
                  width: 36, height: 36, border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff',
                  cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <i className={`fa-solid fa-chevron-${dailyOpen ? 'up' : 'down'}`} />
              </button>
            </div>
          </div>
          {dailyOpen && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 600 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                    <th style={{ padding: '12px 16px', fontSize: 11, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Date</th>
                    <th style={{ padding: '12px 16px', fontSize: 11, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Reach</th>
                    <th style={{ padding: '12px 16px', fontSize: 11, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>New Followers</th>
                  </tr>
                </thead>
                <tbody>
                  {dailyRows.length === 0 ? (
                    <tr><td colSpan="3" style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>No data available in this range</td></tr>
                  ) : dailyRows.map((row, i) => (
                    <tr key={row.key} style={{ borderBottom: '1px solid #f8fafc', background: i % 2 === 0 ? '#fff' : '#f8fafc' }}>
                      <td style={{ padding: '14px 16px', fontSize: 13, fontWeight: 600, color: '#334155' }}>{row.date}</td>
                      <td style={{ padding: '14px 16px', fontSize: 14, color: '#0f172a', fontWeight: 500 }}>{row.reach.toLocaleString()}</td>
                      <td style={{ padding: '14px 16px', fontSize: 14, fontWeight: 600, color: row.followers > 0 ? '#10b981' : row.followers < 0 ? '#ef4444' : '#64748b' }}>
                        {row.followers > 0 ? '+' : ''}{row.followers.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 24, boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)' }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Reels</h3>
          <p style={{ margin: '0 0 20px', fontSize: 13, color: '#64748b' }}>
            Reels posted in this date range. Numbers are lifetime totals for each reel, not views on that day.
            Watch time and skip rate are the closest retention metrics Meta provides. Follows-from-this-reel is not available for Reels on this API.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
            {[
              { label: 'Reels posted', value: fmtNum(reelSummary?.count) },
              { label: 'Total views', value: fmtNum(reelSummary?.total_views) },
              { label: 'Median watch time', value: fmtWatch(reelSummary?.median_avg_watch_seconds) },
              { label: 'Median skip rate', value: fmtPct(reelSummary?.median_skip_rate) },
            ].map((item) => (
              <div key={item.label} style={{ background: '#f8fafc', borderRadius: 12, padding: '14px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{item.label}</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', marginTop: 6 }}>{item.value}</div>
              </div>
            ))}
          </div>

          {reelBarData && (
            <div style={{ height: 260, marginBottom: 24 }}>
              <Bar data={reelBarData} options={barOptions} />
            </div>
          )}

          {reels.length === 0 ? (
            <p style={{ color: '#94a3b8', textAlign: 'center', padding: 24 }}>No reels posted in this range.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {reels.map((reel) => {
                const open = openReelId === reel.id
                const posted = reel.timestamp
                  ? new Date(reel.timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
                  : ''
                return (
                  <article key={reel.id} style={{ border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
                    <button
                      type="button"
                      onClick={() => setOpenReelId(open ? null : reel.id)}
                      style={{
                        width: '100%', display: 'flex', gap: 12, alignItems: 'center', padding: 12,
                        border: 'none', background: '#fff', cursor: 'pointer', textAlign: 'left',
                      }}
                    >
                      {reel.thumbnail_url ? (
                        <img src={reel.thumbnail_url} alt="" style={{ width: 56, height: 72, objectFit: 'cover', borderRadius: 8, background: '#f1f5f9' }} />
                      ) : (
                        <div style={{ width: 56, height: 72, borderRadius: 8, background: '#f1f5f9' }} />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, color: '#0f172a', fontSize: 14 }}>{captionLabel(reel)}</div>
                        <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{posted}</div>
                        <div style={{ fontSize: 12, color: '#334155', marginTop: 6 }}>
                          {fmtNum(reel.views)} views · {fmtWatch(reel.avg_watch_seconds)} avg watch · skip {fmtPct(reel.skip_rate)}
                        </div>
                      </div>
                      <i className={`fa-solid fa-chevron-${open ? 'up' : 'down'}`} style={{ color: '#94a3b8' }} />
                    </button>
                    {open && (
                      <div style={{ padding: '0 16px 16px', borderTop: '1px solid #f1f5f9' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginTop: 14 }}>
                          <MetricBox icon="fa-solid fa-play" label="Views" value={fmtNum(reel.views)} />
                          <MetricBox icon="fa-solid fa-users" label="Accounts reached" value={fmtNum(reel.reach)} />
                          <MetricBox icon="fa-regular fa-clock" label="Average watch time" value={fmtWatch(reel.avg_watch_seconds)} />
                          <MetricBox icon="fa-solid fa-forward" label="Skip rate" value={fmtPct(reel.skip_rate)} valueColor={skipColor(reel.skip_rate)} />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginTop: 10 }}>
                          <MetricBox icon="fa-solid fa-heart" label="Likes" value={fmtNum(reel.likes)} />
                          <MetricBox icon="fa-solid fa-comment" label="Comments" value={fmtNum(reel.comments)} />
                          <MetricBox icon="fa-solid fa-share" label="Shares" value={fmtNum(reel.shares)} />
                          <MetricBox icon="fa-solid fa-bookmark" label="Saves" value={fmtNum(reel.saved)} />
                        </div>
                        <div style={{ marginTop: 16 }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 4 }}>What affects views</div>
                          <p style={{ margin: '0 0 8px', fontSize: 12, color: '#94a3b8' }}>Rates vs views, listed like Instagram (skip first).</p>
                          <RateRow label="Skip rate" value={reel.skip_rate} warn />
                          <RateRow label="Share rate" value={reel.share_rate} />
                          <RateRow label="Like rate" value={reel.like_rate} />
                          <RateRow label="Save rate" value={reel.save_rate} />
                          <RateRow label="Comment rate" value={reel.comment_rate} />
                        </div>
                        {reel.permalink && (
                          <a href={reel.permalink} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 12, fontSize: 13, color: '#6366f1', fontWeight: 600 }}>
                            Open on Instagram
                          </a>
                        )}
                      </div>
                    )}
                  </article>
                )
              })}
            </div>
          )}

          {reels.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <h4 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#0f172a' }}>Reel-by-reel performance</h4>
              <p style={{ margin: '0 0 16px', fontSize: 13, color: '#64748b' }}>
                Lifetime totals for each reel posted in this range, not views on a single day.
              </p>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720, textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                    {['Reel', 'Views', 'Reach', 'Avg watch', 'Skip', 'Likes', 'Comments', 'Shares', 'Saves'].map((h) => (
                      <th key={h} style={{ padding: '10px 12px', fontSize: 11, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reels.map((reel, i) => (
                    <tr key={reel.id} style={{ background: i % 2 === 0 ? '#fff' : '#f8fafc', borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '10px 12px', fontSize: 13, fontWeight: 600, maxWidth: 220 }}>{captionLabel(reel)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.views)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.reach)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtWatch(reel.avg_watch_seconds)}</td>
                      <td style={{ padding: '10px 12px', color: skipColor(reel.skip_rate), fontWeight: 600 }}>{fmtPct(reel.skip_rate)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.likes)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.comments)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.shares)}</td>
                      <td style={{ padding: '10px 12px' }}>{fmtNum(reel.saved)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
