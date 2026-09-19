import { useEffect, useMemo } from 'react'
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import api from '../api'
import { NavItem, NavSection } from '../components/NavSection'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function SocialMediaLayout() {
  const { clientId } = useParams()
  const { token, user, logout, patchUser } = useAuth()
  const { toast } = useUI()
  const navigate = useNavigate()

  const client = useMemo(
    () => (user?.clients || []).find((c) => c.id === clientId) || null,
    [user?.clients, clientId],
  )

  useEffect(() => {
    if (!token || !clientId) return
    let cancelled = false

    ;(async () => {
      try {
        if (user?.active_client_id !== clientId) {
          await api.selectClient(token, clientId)
          if (cancelled) return
        }
        patchUser({
          active_client_id: clientId,
          active_channel_id: null,
        })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync only when client changes
  }, [token, clientId])

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="dashboard">
      <aside className="sidebar card">
        <div className="sidebar-header">
          <div className="brand-logo">
            <i className="fa-brands fa-instagram brand-icon" />
            <h3>Social Media</h3>
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
            <NavItem to={`/clients/${clientId}`} icon={<i className="fa-solid fa-arrow-left" />}>
              Client Home
            </NavItem>
          </NavSection>

          <NavSection title="Social Media">
            <NavLink
              to={`/clients/${clientId}/social/instagram`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-brands fa-instagram" />
              <span>Instagram Connection</span>
            </NavLink>
            <NavLink
              to={`/clients/${clientId}/social/analytics`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-solid fa-chart-line" />
              <span>Instagram Analytics</span>
            </NavLink>
            <NavLink
              to={`/clients/${clientId}/social/facebook`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-brands fa-facebook" />
              <span>Facebook Connection</span>
            </NavLink>
            <NavLink
              to={`/clients/${clientId}/social/generate`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-solid fa-wand-magic-sparkles" />
              <span>Generate Post</span>
            </NavLink>
            <NavLink
              to={`/clients/${clientId}/social/schedule`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-solid fa-calendar-alt" />
              <span>Publishing Schedule</span>
            </NavLink>
            <NavLink
              to={`/clients/${clientId}/social/festivals`}
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <i className="fa-solid fa-gift" />
              <span>Festive Posts</span>
            </NavLink>
          </NavSection>
        </nav>

        <div className="sidebar-footer">
          <button type="button" className="btn btn-danger btn-block" onClick={handleLogout}>
            <i className="fa-solid fa-right-from-bracket" /> Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet context={{ client, clientId }} />
      </main>
    </div>
  )
}
