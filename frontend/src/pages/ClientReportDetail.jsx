import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

function monthLabel(yyyyMm) {
  if (!yyyyMm) return '—'
  const [y, m] = yyyyMm.split('-').map(Number)
  if (!y || !m) return yyyyMm
  return new Date(y, m - 1, 1).toLocaleString(undefined, {
    month: 'long',
    year: 'numeric',
  })
}

function statusChip(status) {
  const key = (status || '').toLowerCase()
  const label = key ? key.charAt(0).toUpperCase() + key.slice(1) : '—'
  return <span className={`report-status-chip ${key}`}>{label}</span>
}

export default function ClientReportDetail() {
  const { reportId } = useParams()
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()
  const navigate = useNavigate()

  const [report, setReport] = useState(null)
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(true)
  const [refining, setRefining] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [refinePrompt, setRefinePrompt] = useState('')

  const load = useCallback(async () => {
    if (!token || !reportId) return
    setLoading(true)
    try {
      const data = await api.getReport(token, reportId)
      setReport(data)
      if (data.status === 'ready') {
        try {
          const text = await api.fetchReportHtml(token, reportId)
          setHtml(text)
        } catch {
          setHtml('')
        }
      } else {
        setHtml('')
      }
    } catch (err) {
      toast(err.message, 'error')
      navigate(`/clients/${clientId}/videos/reports`, { replace: true })
    } finally {
      setLoading(false)
    }
  }, [token, reportId, clientId, toast, navigate])

  useEffect(() => {
    load()
  }, [load])

  async function handleRefine(e) {
    e.preventDefault()
    if (!refinePrompt.trim()) {
      toast('Enter a refinement prompt', 'error')
      return
    }
    setRefining(true)
    try {
      const data = await api.refineReport(token, reportId, refinePrompt.trim())
      setReport(data)
      setRefinePrompt('')
      if (data.status === 'ready') {
        const text = await api.fetchReportHtml(token, reportId)
        setHtml(text)
      }
      toast('Report refined', 'success')
    } catch (err) {
      toast(err.message, 'error')
      await load()
    } finally {
      setRefining(false)
    }
  }

  async function handleDownloadPdf() {
    setDownloading(true)
    try {
      const blob = await api.fetchReportPdfBlob(token, reportId)
      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objectUrl
      a.download = `${report?.report_month || 'report'}-youtube-report.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(objectUrl)
    } catch (err) {
      toast(err.message || 'PDF not available yet', 'error')
    } finally {
      setDownloading(false)
    }
  }

  if (loading) {
    return (
      <div className="page-stack">
        <p className="text-muted">Loading report…</p>
      </div>
    )
  }

  if (!report) return null

  const summary = report.metrics_summary || {}
  const cur = summary.current || {}
  const history = [...(report.refine_history || [])].reverse().slice(0, 3)

  return (
    <div className="page-stack">
      <Breadcrumbs
        items={[
          { label: 'Clients', to: '/clients' },
          { label: client?.name || 'Client', to: `/clients/${clientId}` },
          { label: 'Reports', to: `/clients/${clientId}/videos/reports` },
          { label: monthLabel(report.report_month) },
        ]}
      />

      <header
        style={{
          marginBottom: 18,
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'flex-start',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <h1 style={{ margin: 0 }}>{monthLabel(report.report_month)} report</h1>
            {statusChip(report.status)}
          </div>
          <p className="text-muted" style={{ margin: 0 }}>
            Compared with {monthLabel(report.previous_month)}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="btn btn-secondary" to={`/clients/${clientId}/videos/reports`}>
            All reports
          </Link>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleDownloadPdf}
            disabled={downloading || report.status !== 'ready'}
          >
            {downloading ? 'Downloading…' : 'Download PDF'}
          </button>
        </div>
      </header>

      {report.error && (
        <p style={{ marginBottom: 16, paddingLeft: 12, borderLeft: '3px solid #c53030' }}>{report.error}</p>
      )}

      {summary.current && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
            gap: 0,
            borderTop: '1px solid #e2e8f0',
            borderBottom: '1px solid #e2e8f0',
            marginBottom: 22,
          }}
        >
          {[
            ['Views', Math.round(cur.views || 0).toLocaleString()],
            ['Watch (min)', Math.round(cur.estimatedMinutesWatched || 0).toLocaleString()],
            ['Net subs', Math.round(cur.netSubscribers || 0).toLocaleString()],
            ['Charts', String(summary.chart_count ?? '—')],
          ].map(([label, value], i) => (
            <div
              key={label}
              style={{
                padding: '14px 12px',
                borderRight: i < 3 ? '1px solid #e2e8f0' : 'none',
              }}
            >
              <div className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {label}
              </div>
              <strong style={{ fontSize: 20 }}>{value}</strong>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleRefine} style={{ marginBottom: 22 }}>
        <div className="report-refine-row">
          <textarea
            value={refinePrompt}
            onChange={(e) => setRefinePrompt(e.target.value)}
            rows={2}
            placeholder="Refine this report… e.g. push international channels harder"
            disabled={refining}
          />
          <button type="submit" className="btn btn-primary" disabled={refining || !refinePrompt.trim()}>
            {refining ? (
              <>
                <i className="fa-solid fa-spinner fa-spin" /> Refining…
              </>
            ) : (
              'Refine'
            )}
          </button>
        </div>
        {history.length > 0 && (
          <p className="text-muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
            Recent: {history.map((h) => h.prompt).filter(Boolean).join(' · ')}
          </p>
        )}
      </form>

      {html ? (
        <iframe
          title="Monthly report preview"
          srcDoc={html}
          style={{
            width: '100%',
            minHeight: '78vh',
            border: '1px solid #e2e8f0',
            borderRadius: 4,
            background: '#fff',
          }}
        />
      ) : (
        <p className="text-muted">
          {report.status === 'pending' ? 'Report is still generating…' : 'HTML preview not available.'}
        </p>
      )}
    </div>
  )
}
