import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function PocWeeklyTracker() {
  const { token } = useAuth()
  const { toast } = useUI()
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')

  const loadClients = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const result = await api.getTrackerSheetClients(token)
      setClients(result.clients || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, toast])

  useEffect(() => {
    loadClients()
  }, [loadClients])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return clients
    return clients.filter((client) => (client.name || '').toLowerCase().includes(needle))
  }, [clients, query])

  return (
    <div className="weekly-tracker-page tracker-sheet-page">
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs items={[{ label: 'All trackers' }]} />
          <h1>All trackers</h1>
          <p>Pick a client to open their month sheet — default content tracker or custom board.</p>
        </div>
      </header>

      <div className="tracker-poc-search">
        <input
          className="form-control"
          value={query}
          placeholder="Search clients"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {loading ? (
        <p className="text-muted sheet-empty">Loading clients…</p>
      ) : filtered.length === 0 ? (
        <p className="text-muted sheet-empty">
          {clients.length === 0 ? 'No clients on this account yet.' : 'No clients match that search.'}
        </p>
      ) : (
        <div className="sheet-table-wrap">
          <table className="sheet-table sheet-table-index">
            <thead>
              <tr>
                <th>Client</th>
                <th>Sheet</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((client) => (
                <tr key={client.client_id}>
                  <td><strong>{client.name}</strong></td>
                  <td>
                    <Link className="sheet-link-pill" to={`/tracker/${client.client_id}`}>
                      <i className="fa-solid fa-table" />
                      Open sheet
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
