import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import { NavItem, NavSection } from '../components/NavSection'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientLayout() {
  const { clientId, channelId: activeChannelId } = useParams()
  const { token, user, logout, patchUser } = useAuth()
  const { toast, confirm } = useUI()
  const navigate = useNavigate()
  const location = useLocation()

  const [channels, setChannels] = useState([])
  const [loadingChannels, setLoadingChannels] = useState(true)

  const client = useMemo(
    () => (user?.clients || []).find((c) => c.id === clientId) || null,
    [user?.clients, clientId],
  )

  const activeChannel = useMemo(
    () => channels.find((c) => c.id === activeChannelId) || null,
    [channels, activeChannelId],
  )

  const loadChannels = useCallback(async () => {
    if (!token || !clientId) return []
    setLoadingChannels(true)
    try {
      const data = await api.listChannels(token, clientId)
      const list = data.channels || []
      setChannels(list)
      patchUser({
        channels: list.map((c) => ({ id: c.id, title: c.title })),
        active_client_id: clientId,
        active_channel_id: data.active_channel_id,
      })
      return list
    } catch (err) {
      toast(`Failed to load channels: ${err.message}`, 'error')
      setChannels([])
      return []
    } finally {
      setLoadingChannels(false)
    }
  }, [token, clientId, patchUser, toast])

  // Sync backend active client when URL client changes
  useEffect(() => {
    if (!token || !clientId) return
    let cancelled = false

    ;(async () => {
      try {
        if (user?.active_client_id !== clientId) {
          await api.selectClient(token, clientId)
          if (cancelled) return
        }
        if (!cancelled) await loadChannels()
      } catch (err) {
        if (!cancelled) {
          toast(err.message, 'error')
          navigate('/clients', { replace: true })
        }
      }
    })()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run on client change
  }, [token, clientId])

  async function handleLinkChannel() {
    try {
      const data = await api.googleLogin(token, clientId)
      toast('Redirecting to Google OAuth...', 'info')
      window.location.href = data.authorization_url
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleSyncChannels() {
    if (!channels.length) {
      toast(
        'Link a YouTube channel first, then sync to discover more channels under that account.',
        'info',
      )
      return
    }
    try {
      toast('Discovering channels from linked Google account...', 'info')
      const data = await api.syncChannels(token, clientId)
      const list = data.channels || []
      setChannels(list)
      patchUser({
        channels: list.map((c) => ({ id: c.id, title: c.title })),
        active_channel_id: data.active_channel_id,
      })
      toast(`Discovered and synced ${list.length} channel(s)!`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleDeleteClient() {
    const label = client?.name || clientId
    const isConfirmed = await confirm({
      title: 'Delete Client Account',
      message: `Are you absolutely sure you want to delete client "${label}" and all linked YouTube channels? This cannot be undone.`,
      isDanger: true,
    })
    if (!isConfirmed) return

    try {
      await api.deleteClient(token, clientId)
      const clientData = await api.listClients(token)
      patchUser({
        clients: clientData.clients,
        channels: [],
        has_clients: clientData.clients.length > 0,
        active_client_id: clientData.active_client_id,
        active_channel_id: clientData.active_channel_id,
      })
      toast(`Client "${label}" and its channels deleted.`, 'success')
      navigate('/clients', { replace: true })
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleDisconnectChannel(channelId) {
    const channel = channels.find((c) => c.id === channelId)
    const label = channel?.title || channelId
    const isConfirmed = await confirm({
      title: 'Unlink YouTube Channel',
      message: `Are you sure you want to remove and unlink YouTube channel "${label}" from this client? Stats will be preserved in your database.`,
      isDanger: true,
    })
    if (!isConfirmed) return

    try {
      const data = await api.deleteChannel(token, channelId, clientId)
      const list = data.channels || []
      setChannels(list)
      patchUser({
        channels: list.map((c) => ({ id: c.id, title: c.title })),
        active_channel_id: data.active_channel_id,
      })
      toast(`YouTube channel "${label}" unlinked.`, 'success')
      navigate(`/clients/${clientId}/videos`, { replace: true })
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  if (!client && user?.clients) {
    // Client id not in list — redirect
    return (
      <div className="dashboard">
        <main className="main-content">
          <div className="connect-prompt-container card">
            <h2>Client not found</h2>
            <p>This client account does not exist or you no longer have access.</p>
            <Link to="/clients" className="btn btn-primary">
              Back to Clients
            </Link>
          </div>
        </main>
      </div>
    )
  }

  const clientBase = `/clients/${clientId}`
  const base = `${clientBase}/videos`
  const inChannel = !!activeChannelId
  const trackerOpen = location.pathname.includes('/videos/tracker')

  return (
    <div className="dashboard">
      <aside className="sidebar card">
        <div className="sidebar-header">
          <div className="brand-logo">
            <i className="fa-solid fa-chart-line brand-icon" />
            <h3>Analytics Portal</h3>
          </div>
        </div>

        <div className="user-profile">
          <div className="avatar">
            <i className="fa-solid fa-user" />
          </div>
          <div className="user-info">
            <h4>{user?.username || '—'}</h4>
            <p className="role">{client?.name || 'Client'}</p>
          </div>
        </div>

        <nav className="sidebar-menu">
          <NavSection>
            <NavItem to={clientBase} icon={<i className="fa-solid fa-arrow-left" />}>
              Client Home
            </NavItem>
          </NavSection>

          {!inChannel && (
            <NavSection title="Client">
              <NavItem to={base} end icon={<i className="fa-solid fa-chart-pie" />}>
                Overview
              </NavItem>
              <NavItem to={`${base}/library`} icon={<i className="fa-solid fa-film" />}>
                Videos
              </NavItem>
              <NavItem to={`${base}/post`} icon={<i className="fa-solid fa-upload" />}>
                Post Video
              </NavItem>
              <NavItem to={`${base}/content-plan`} icon={<i className="fa-solid fa-lightbulb" />}>
                Content Plan
              </NavItem>
              <NavItem to={`${base}/tracker`} icon={<i className="fa-solid fa-calendar-week" />}>
                Tracker
              </NavItem>
              {trackerOpen && (
                <div className="menu-sub">
                  <NavItem to={`${base}/tracker`} end icon={<i className="fa-solid fa-layer-group" />}>
                    Content week
                  </NavItem>
                  <NavItem to={`${base}/tracker/custom`} icon={<i className="fa-solid fa-list-check" />}>
                    Custom board
                  </NavItem>
                </div>
              )}
              <NavItem to={`${base}/reports`} icon={<i className="fa-solid fa-file-lines" />}>
                Reports
              </NavItem>
              <NavItem to={`${base}/settings`} icon={<i className="fa-solid fa-gear" />}>
                Settings
              </NavItem>
            </NavSection>
          )}

          {inChannel && activeChannel && (
            <NavSection title="Channel">
              <NavItem
                to={base}
                end
                icon={<i className="fa-solid fa-arrow-left" />}
              >
                Back to Client
              </NavItem>
              <NavItem
                to={`${base}/channels/${activeChannelId}`}
                end
                icon={<i className="fa-solid fa-chart-pie" />}
              >
                Overview
              </NavItem>
              <NavItem
                to={`${base}/channels/${activeChannelId}/library`}
                icon={<i className="fa-solid fa-film" />}
              >
                Videos
              </NavItem>
              <NavItem
                to={`${base}/channels/${activeChannelId}/settings`}
                icon={<i className="fa-solid fa-gear" />}
              >
                Settings
              </NavItem>
            </NavSection>
          )}

          <NavSection title="Channels">
            {loadingChannels && (
              <div className="nav-empty text-muted">Loading…</div>
            )}
            {!loadingChannels && channels.length === 0 && (
              <div className="nav-empty text-muted">No channels linked</div>
            )}
            {channels.map((ch) => (
              <NavLink
                key={ch.id}
                to={`${base}/channels/${ch.id}`}
                className={({ isActive }) =>
                  `menu-item menu-item-channel ${isActive ? 'active' : ''}`
                }
              >
                <i className="fa-brands fa-youtube" />
                <span className="menu-item-label">{ch.title || ch.id}</span>
              </NavLink>
            ))}
          </NavSection>

          <NavSection title="Actions">
            <button type="button" className="menu-item menu-item-btn" onClick={handleLinkChannel}>
              <i className="fa-brands fa-youtube" />
              <span>Link Channel</span>
            </button>
            <button type="button" className="menu-item menu-item-btn" onClick={handleSyncChannels}>
              <i className="fa-solid fa-arrows-rotate" />
              <span>Sync Channels</span>
            </button>
            {inChannel && (
              <button
                type="button"
                className="menu-item menu-item-btn danger-text"
                onClick={() => handleDisconnectChannel(activeChannelId)}
              >
                <i className="fa-solid fa-link-slash" />
                <span>Unlink Channel</span>
              </button>
            )}
            {!inChannel && (
              <button
                type="button"
                className="menu-item menu-item-btn danger-text"
                onClick={handleDeleteClient}
              >
                <i className="fa-solid fa-trash-can" />
                <span>Delete Client</span>
              </button>
            )}
          </NavSection>
        </nav>

        <div className="sidebar-footer">
          <button type="button" className="btn btn-danger btn-block" onClick={handleLogout}>
            <i className="fa-solid fa-right-from-bracket" /> Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet
          context={{
            client,
            clientId,
            channels,
            loadingChannels,
            loadChannels,
            handleLinkChannel,
            handleDisconnectChannel,
          }}
        />
      </main>
    </div>
  )
}
