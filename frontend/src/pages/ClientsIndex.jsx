import { Link, useNavigate } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientsIndex() {
  const { token, user, patchUser } = useAuth()
  const { toast, prompt } = useUI()
  const navigate = useNavigate()

  const clients = user?.clients || []

  async function handleCreateClient() {
    const name = await prompt({
      title: 'Create Client Account',
      placeholder: 'Enter client name...',
    })
    if (!name?.trim()) return

    try {
      const data = await api.createClient(token, name.trim())
      patchUser({
        clients: data.clients,
        channels: [],
        has_clients: data.clients.length > 0,
        active_client_id: data.active_client_id,
        active_channel_id: data.active_channel_id,
      })
      toast(`Client "${name.trim()}" created successfully!`, 'success')
      if (data.active_client_id) {
        navigate(`/clients/${data.active_client_id}`)
      }
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs items={[{ label: 'Clients' }]} />
          <h1>Clients</h1>
          <p>Select a client account or create a new one to manage YouTube channels.</p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-primary" onClick={handleCreateClient}>
            <i className="fa-solid fa-plus" /> New Client
          </button>
        </div>
      </header>

      {clients.length === 0 ? (
        <div className="connect-prompt-container card animate-fade-in">
          <div className="prompt-illustration">
            <i className="fa-solid fa-folder-open illustration-icon" />
          </div>
          <h2>Welcome to Gravity</h2>
          <p>
            To get started, create a client account. You can then link YouTube channels, plan videos,
            and run social posting from one place.
          </p>
          <button type="button" className="btn btn-primary btn-lg" onClick={handleCreateClient}>
            <i className="fa-solid fa-plus" /> Create Client Account
          </button>
        </div>
      ) : (
        <div className="clients-grid">
          {clients.map((client) => (
            <Link
              key={client.id}
              to={`/clients/${client.id}`}
              className="client-card card"
            >
              <div className="client-card-icon">
                <i className="fa-solid fa-circle-user" />
              </div>
              <div className="client-card-body">
                <h3>{client.name}</h3>
                <p>
                  {client.specialty
                    ? client.specialty
                    : client.channel_count > 0
                      ? `${client.channel_count} channel${client.channel_count === 1 ? '' : 's'}`
                      : 'No channels linked'}
                </p>
                {client.specialty && client.channel_count > 0 && (
                  <p className="client-card-meta">
                    {client.channel_count} channel{client.channel_count === 1 ? '' : 's'}
                  </p>
                )}
              </div>
              <i className="fa-solid fa-chevron-right client-card-arrow" />
            </Link>
          ))}
        </div>
      )}
    </>
  )
}
