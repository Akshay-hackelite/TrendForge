import { Link, useParams } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'

export default function ClientHub() {
  const { clientId } = useParams()
  const { user } = useAuth()
  const client = (user?.clients || []).find((c) => c.id === clientId)

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs items={[{ label: 'Clients', to: '/clients' }, { label: client?.name || 'Client' }]} />
          <h1>{client?.name || 'Client'}</h1>
          <p>Choose the workspace you want to manage.</p>
        </div>
      </header>

      <div className="workspace-grid">
        <Link to={`/clients/${clientId}/videos`} className="workspace-card card">
          <div className="workspace-card-icon youtube">
            <i className="fa-brands fa-youtube" />
          </div>
          <div className="workspace-card-body">
            <h2>Videos</h2>
            <p>YouTube analytics, content planning, scripts, reports, and channel management.</p>
          </div>
          <span className="btn btn-primary btn-sm">Open Videos</span>
        </Link>

        <Link to={`/clients/${clientId}/social`} className="workspace-card card">
          <div className="workspace-card-icon instagram">
            <i className="fa-brands fa-instagram" />
          </div>
          <div className="workspace-card-body">
            <h2>Social Media</h2>
            <p>Connect Instagram and generate static posts from scripts or recommended keywords.</p>
          </div>
          <span className="btn btn-primary btn-sm">Open Social Media</span>
        </Link>
      </div>
    </>
  )
}
