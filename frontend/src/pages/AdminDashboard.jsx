import { useEffect, useState } from 'react'
import api from '../api'
import { useUI } from '../context/UIContext'

const ADMIN_SESSION_KEY = 'admin_password'

export default function AdminDashboard() {
  const { toast, confirm, prompt } = useUI()
  const [adminPassword, setAdminPassword] = useState(() => sessionStorage.getItem(ADMIN_SESSION_KEY) || '')
  const [unlocked, setUnlocked] = useState(false)
  const [unlockInput, setUnlockInput] = useState('')
  const [unlockError, setUnlockError] = useState('')
  const [unlocking, setUnlocking] = useState(false)

  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [creating, setCreating] = useState(false)

  async function loadUsers(password) {
    setLoading(true)
    try {
      const data = await api.adminListUsers(password)
      setUsers(data.users || [])
    } catch (err) {
      sessionStorage.removeItem(ADMIN_SESSION_KEY)
      setUnlocked(false)
      setAdminPassword('')
      throw err
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!adminPassword) return
    ;(async () => {
      try {
        await api.adminUnlock(adminPassword)
        setUnlocked(true)
        await loadUsers(adminPassword)
      } catch {
        sessionStorage.removeItem(ADMIN_SESSION_KEY)
        setAdminPassword('')
        setUnlocked(false)
      }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- restore session once on mount

  async function handleUnlock(e) {
    e.preventDefault()
    setUnlockError('')
    setUnlocking(true)
    try {
      await api.adminUnlock(unlockInput)
      sessionStorage.setItem(ADMIN_SESSION_KEY, unlockInput)
      setAdminPassword(unlockInput)
      setUnlocked(true)
      await loadUsers(unlockInput)
    } catch (err) {
      setUnlockError(err.message || 'Invalid admin password')
    } finally {
      setUnlocking(false)
    }
  }

  function handleLock() {
    sessionStorage.removeItem(ADMIN_SESSION_KEY)
    setAdminPassword('')
    setUnlocked(false)
    setUnlockInput('')
    setUsers([])
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!newUsername.trim() || !newPassword) return
    setCreating(true)
    try {
      const user = await api.adminCreateUser(adminPassword, newUsername.trim(), newPassword)
      setUsers((prev) => [...prev, user].sort((a, b) => a.username.localeCompare(b.username)))
      setNewUsername('')
      setNewPassword('')
      toast(`User "${user.username}" created`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  async function handleResetPassword(username) {
    const password = await prompt({
      title: `Reset password for ${username}`,
      placeholder: 'New password…',
    })
    if (!password) return
    try {
      await api.adminResetPassword(adminPassword, username, password)
      toast(`Password updated for ${username}`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleToggleActive(user) {
    const next = !user.is_active
    const ok = await confirm({
      title: next ? 'Enable user' : 'Disable user',
      message: next
        ? `Enable login for "${user.username}"?`
        : `Disable login for "${user.username}"? They will be locked out immediately.`,
      isDanger: !next,
    })
    if (!ok) return
    try {
      const updated = await api.adminSetActive(adminPassword, user.username, next)
      setUsers((prev) => prev.map((u) => (u.username === updated.username ? updated : u)))
      toast(`${updated.username} is now ${updated.is_active ? 'active' : 'disabled'}`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleDelete(username) {
    const ok = await confirm({
      title: 'Delete user',
      message: `Permanently delete "${username}" and all of their clients/channels? This cannot be undone.`,
      isDanger: true,
    })
    if (!ok) return
    try {
      await api.adminDeleteUser(adminPassword, username)
      setUsers((prev) => prev.filter((u) => u.username !== username))
      toast(`Deleted ${username}`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  if (!unlocked) {
    return (
      <div className="login-page admin-page">
        <div className="card login-box">
          <div className="logo">
            <h2>Admin Dashboard</h2>
          </div>
          <p className="subtitle">Enter the internal admin password to continue</p>
          <form onSubmit={handleUnlock}>
            <div className="input-group">
              <label htmlFor="admin-password">Admin password</label>
              <input
                id="admin-password"
                type="password"
                placeholder="Admin password"
                required
                value={unlockInput}
                onChange={(e) => setUnlockInput(e.target.value)}
                autoFocus
              />
            </div>
            {unlockError && <div className="error-msg">{unlockError}</div>}
            <button type="submit" className="btn btn-primary btn-block" disabled={unlocking}>
              {unlocking ? 'Unlocking…' : 'Unlock'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="admin-dashboard">
      <header className="content-header">
        <div className="greeting">
          <h1>Admin Dashboard</h1>
          <p>Create, disable, and remove application users.</p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-secondary" onClick={() => loadUsers(adminPassword)} disabled={loading}>
            <i className="fa-solid fa-rotate" /> Refresh
          </button>
          <button type="button" className="btn btn-danger" onClick={handleLock}>
            <i className="fa-solid fa-lock" /> Lock
          </button>
        </div>
      </header>

      <section className="card table-section admin-create-card">
        <h2 className="section-title">Create user</h2>
        <form className="admin-create-form" onSubmit={handleCreate}>
          <div className="input-group">
            <label htmlFor="new-username">Username</label>
            <input
              id="new-username"
              type="text"
              placeholder="username"
              required
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
            />
          </div>
          <div className="input-group">
            <label htmlFor="new-password">Password</label>
            <input
              id="new-password"
              type="password"
              placeholder="password"
              required
              minLength={4}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={creating}>
            <i className="fa-solid fa-plus" />
            {creating ? 'Creating…' : 'Create'}
          </button>
        </form>
      </section>

      <section className="card table-section">
        <h2 className="section-title">Users {loading ? '…' : `(${users.length})`}</h2>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Clients</th>
                <th>Channels</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="admin-empty">
                    {loading ? 'Loading…' : 'No users yet.'}
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.username} className="video-row-hover">
                    <td className="view-highlight">{user.username}</td>
                    <td>
                      <span className={`admin-status ${user.is_active ? 'active' : 'disabled'}`}>
                        {user.is_active ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td>{user.client_count}</td>
                    <td>{user.channel_count}</td>
                    <td>
                      <div className="admin-actions">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleResetPassword(user.username)}
                        >
                          Reset password
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleToggleActive(user)}
                        >
                          {user.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDelete(user.username)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
