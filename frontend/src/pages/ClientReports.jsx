import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

function previousMonthValue(today = new Date()) {
  const d = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

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

export default function ClientReports() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()
  const navigate = useNavigate()

  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [reportMonth, setReportMonth] = useState(previousMonthValue())

  const load = useCallback(async () => {
    if (!token || !clientId) return
    setLoading(true)
    try {
      const data = await api.listReports(token, clientId)
      setReports(data.reports || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    load()
  }, [load])

  const sorted = useMemo(
    () => [...reports].sort((a, b) => (b.report_month || '').localeCompare(a.report_month || '')),
    [reports],
  )

  async function handleGenerate(e) {
    e.preventDefault()
    if (!token || !clientId) return
    setGenerating(true)
    try {
      toast(`Generating ${monthLabel(reportMonth)} report…`, 'info')
      const data = await api.generateReport(token, clientId, { reportMonth })
      toast('Report ready', 'success')
      if (data?.id) navigate(`/clients/${clientId}/videos/reports/${data.id}`)
      else await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="page-stack">
      <Breadcrumbs
        items={[
          { label: 'Clients', to: '/clients' },
          { label: client?.name || 'Client', to: `/clients/${clientId}` },
          { label: 'Reports' },
        ]}
      />

      <header className="page-header" style={{ marginBottom: 18 }}>
        <div>
          <h1>Monthly reports</h1>
          <p className="text-muted" style={{ maxWidth: 640 }}>
            Combined-channel YouTube performance for a calendar month, with narrative, charts, and PDF.
          </p>
        </div>
      </header>

      <form
        onSubmit={handleGenerate}
        style={{
          display: 'flex',
          gap: 14,
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          marginBottom: 28,
          paddingBottom: 20,
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        <div className="input-group" style={{ margin: 0, minWidth: 180 }}>
          <label htmlFor="report-month">Report month</label>
          <input
            id="report-month"
            type="month"
            value={reportMonth}
            onChange={(e) => setReportMonth(e.target.value)}
            disabled={generating}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={generating}>
          {generating ? (
            <>
              <i className="fa-solid fa-spinner fa-spin" /> Generating…
            </>
          ) : (
            <>Generate {monthLabel(reportMonth)}</>
          )}
        </button>
      </form>

      <h2 style={{ fontSize: 15, margin: '0 0 12px' }}>Past reports</h2>
      {loading ? (
        <p className="text-muted">Loading…</p>
      ) : sorted.length === 0 ? (
        <p className="text-muted">No reports yet. Generate one for {monthLabel(previousMonthValue())}.</p>
      ) : (
        <table className="data-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Month</th>
              <th>Status</th>
              <th>Updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id}>
                <td>{monthLabel(r.report_month)}</td>
                <td>{statusChip(r.status)}</td>
                <td className="text-muted" style={{ fontSize: 12 }}>
                  {r.updated_at ? new Date(r.updated_at).toLocaleString() : '—'}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <Link className="btn btn-secondary btn-sm" to={`/clients/${clientId}/videos/reports/${r.id}`}>
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
