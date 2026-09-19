import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientSocialInstagram() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ app_id: '', app_secret: '' })

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getInstagramConfig(token, clientId)
      setConfig(data)
      setForm({
        app_id: data.app_id || '',
        app_secret: '',
      })
    } catch (err) {
      toast(`Failed to load Instagram config: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    if (token && clientId) void loadConfig()
  }, [token, clientId, loadConfig])

  async function handleSave(event) {
    event.preventDefault()
    setSaving(true)
    try {
      const data = await api.saveInstagramConfig(token, clientId, form)
      setConfig(data)
      setForm({ app_id: data.app_id || '', app_secret: '' })
      toast('Instagram app configuration saved.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleConnect() {
    setConnecting(true)
    try {
      const data = await api.createInstagramConnectUrl(token, clientId)
      window.location.href = data.authorization_url
    } catch (err) {
      toast(err.message, 'error')
      setConnecting(false)
    }
  }

  async function copyCallback() {
    const value = config?.redirect_uri || ''
    if (!value) return
    await navigator.clipboard.writeText(value)
    toast('Callback URL copied.', 'success')
  }

  const connected = !!config?.connection?.connected

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: 'Social Media' },
            ]}
          />
          <h1>Instagram Connection</h1>
          <p>Configure this client&apos;s Instagram app and connect their Instagram account.</p>
        </div>
        <div className="connection-status-pill">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          {connected ? 'Connected' : 'Not connected'}
        </div>
      </header>

      {loading ? (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading Instagram settings…</span>
          </div>
        </div>
      ) : (
        <div className="social-settings-grid">
          <form className="card profile-form social-card" onSubmit={handleSave}>
            <section className="profile-section">
              <h2>Instagram App Configuration</h2>
              <p className="profile-section-desc">
                Each client uses their own Instagram app credentials. The app secret is saved server-side
                and is never returned after saving.
              </p>

              <div className="input-grid">
                <label className="input-group">
                  <span>Instagram App ID</span>
                  <input
                    value={form.app_id}
                    onChange={(event) => setForm((prev) => ({ ...prev, app_id: event.target.value }))}
                    placeholder="1234567890"
                  />
                </label>
                <label className="input-group">
                  <span>Instagram App Secret</span>
                  <input
                    type="password"
                    value={form.app_secret}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, app_secret: event.target.value }))
                    }
                    placeholder={config?.has_app_secret ? 'Saved. Enter only to replace.' : 'App secret'}
                  />
                </label>
              </div>

              <div className="callback-box">
                <div>
                  <span>OAuth Callback URL</span>
                  <strong>{config?.redirect_uri}</strong>
                </div>
                <button type="button" className="btn btn-secondary btn-sm" onClick={copyCallback}>
                  <i className="fa-solid fa-copy" /> Copy
                </button>
              </div>

              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  <i className={`fa-solid ${saving ? 'fa-spinner fa-spin' : 'fa-floppy-disk'}`} />
                  {saving ? 'Saving…' : 'Save Configuration'}
                </button>
              </div>
            </section>
          </form>

          <section className="card profile-form social-card">
            <div className="profile-section">
              <h2>Instagram Account</h2>
              {connected ? (
                <div className="connected-account">
                  <div className="connected-account-icon">
                    <i className="fa-brands fa-instagram" />
                  </div>
                  <div>
                    <h3>@{config.connection.instagram_username || 'instagram'}</h3>
                    <p>Instagram User ID: {config.connection.instagram_user_id}</p>
                    {config.connection.token_expires_at && (
                      <p>Token expires: {new Date(config.connection.token_expires_at).toLocaleString()}</p>
                    )}
                  </div>
                </div>
              ) : (
                <p className="profile-section-desc">
                  Save the Instagram app credentials first, then connect the client&apos;s Instagram
                  Business or Creator account.
                </p>
              )}
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleConnect}
                disabled={connecting || !config?.app_id || !config?.has_app_secret}
              >
                <i className={`${connecting ? 'fa-solid fa-spinner fa-spin' : 'fa-brands fa-instagram'}`} />
                {connected ? 'Reconnect Instagram' : 'Connect Instagram'}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
