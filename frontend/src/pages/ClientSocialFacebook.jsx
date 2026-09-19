import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientSocialFacebook() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ app_id: '', app_secret: '' })
  
  const [pagesLoading, setPagesLoading] = useState(false)
  const [pages, setPages] = useState([])
  const [selectingPage, setSelectingPage] = useState(false)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getFacebookConfig(token, clientId)
      setConfig(data)
      setForm({
        app_id: data.app_id || '',
        app_secret: '',
      })
      
      // If connected but no page selected, try to load pages
      if (data?.connection?.connected && !data?.connection?.selected_page_id) {
        loadPages()
      }
    } catch (err) {
      toast(`Failed to load Facebook config: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])
  
  const loadPages = async () => {
    setPagesLoading(true)
    try {
      const { pages } = await api.getFacebookPages(token, clientId)
      setPages(pages || [])
    } catch (err) {
      toast(`Failed to load Facebook pages: ${err.message}`, 'error')
    } finally {
      setPagesLoading(false)
    }
  }

  useEffect(() => {
    if (token && clientId) void loadConfig()
  }, [token, clientId, loadConfig])

  async function handleSave(event) {
    event.preventDefault()
    setSaving(true)
    try {
      const data = await api.saveFacebookConfig(token, clientId, form)
      setConfig(data)
      setForm({ app_id: data.app_id || '', app_secret: '' })
      toast('Facebook app configuration saved.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleConnect() {
    setConnecting(true)
    try {
      const data = await api.createFacebookConnectUrl(token, clientId)
      window.location.href = data.authorization_url
    } catch (err) {
      toast(err.message, 'error')
      setConnecting(false)
    }
  }
  
  async function handleDisconnect() {
    try {
      const data = await api.disconnectFacebook(token, clientId)
      setConfig(data)
      setPages([])
      toast('Facebook disconnected.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }
  
  async function handleSelectPage(page) {
    setSelectingPage(true)
    try {
      const data = await api.selectFacebookPage(
        token, 
        clientId, 
        page.id, 
        page.name, 
        page.access_token
      )
      setConfig(data)
      toast(`Selected page: ${page.name}`, 'success')
    } catch (err) {
      toast(`Failed to select page: ${err.message}`, 'error')
    } finally {
      setSelectingPage(false)
    }
  }

  async function copyCallback() {
    const value = config?.redirect_uri || ''
    if (!value) return
    await navigator.clipboard.writeText(value)
    toast('Callback URL copied.', 'success')
  }

  const connected = !!config?.connection?.connected
  const selectedPageId = config?.connection?.selected_page_id

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
          <h1>Facebook Connection</h1>
          <p>Configure this client&apos;s Facebook app and connect their Facebook Page.</p>
        </div>
        <div className="connection-status-pill">
          <span className={`status-dot ${connected && selectedPageId ? 'connected' : 'disconnected'}`} />
          {connected && selectedPageId ? 'Connected' : 'Not connected'}
        </div>
      </header>

      {loading ? (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading Facebook settings…</span>
          </div>
        </div>
      ) : (
        <div className="social-settings-grid">
          <form className="card profile-form social-card" onSubmit={handleSave}>
            <section className="profile-section">
              <h2>Facebook App Configuration</h2>
              <p className="profile-section-desc">
                Each client uses their own Facebook app credentials (or you can reuse the Instagram ones).
              </p>

              <div className="input-grid">
                <label className="input-group">
                  <span>Facebook App ID</span>
                  <input
                    value={form.app_id}
                    onChange={(event) => setForm((prev) => ({ ...prev, app_id: event.target.value }))}
                    placeholder="1234567890"
                  />
                </label>
                <label className="input-group">
                  <span>Facebook App Secret</span>
                  <input
                    type="password"
                    value={form.app_secret}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, app_secret: event.target.value }))
                    }
                    placeholder={config?.app_id ? 'Saved. Enter only to replace.' : 'App secret'}
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
              <h2>Facebook Page</h2>
              
              {connected && selectedPageId ? (
                <div className="connected-account">
                  <div className="connected-account-icon" style={{background: '#1877f2', color: '#fff'}}>
                    <i className="fa-brands fa-facebook-f" />
                  </div>
                  <div>
                    <h3>{config.connection.selected_page_name}</h3>
                    <p>Page ID: {config.connection.selected_page_id}</p>
                    <p>Connected via: {config.connection.facebook_username}</p>
                  </div>
                </div>
              ) : connected && !selectedPageId ? (
                <div className="connected-account">
                  <div className="connected-account-icon" style={{background: '#1877f2', color: '#fff'}}>
                    <i className="fa-brands fa-facebook-f" />
                  </div>
                  <div style={{flex: 1}}>
                    <h3>Connected as {config.connection.facebook_username}</h3>
                    <p>Please select a Facebook Page below to enable posting.</p>
                    
                    {pagesLoading ? (
                      <p>Loading pages...</p>
                    ) : pages.length > 0 ? (
                      <div className="pages-list" style={{marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                        {pages.map(page => (
                          <div key={page.id} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-tertiary)', padding: '0.5rem 1rem', borderRadius: '4px'}}>
                            <span>{page.name}</span>
                            <button 
                              type="button" 
                              className="btn btn-primary btn-sm"
                              onClick={() => handleSelectPage(page)}
                              disabled={selectingPage}
                            >
                              Select
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p style={{color: 'var(--error-text)', marginTop: '0.5rem'}}>No pages found for this user.</p>
                    )}
                    
                    <button 
                      type="button" 
                      className="btn btn-secondary btn-sm" 
                      style={{marginTop: '1rem'}}
                      onClick={loadPages}
                    >
                      <i className="fa-solid fa-rotate-right" /> Refresh Pages
                    </button>
                  </div>
                </div>
              ) : (
                <p className="profile-section-desc">
                  Save the Facebook app credentials first, then connect the client&apos;s Facebook account to select a Page.
                </p>
              )}
              
              <div className="form-actions" style={{marginTop: '1rem'}}>
                {!connected ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleConnect}
                    disabled={connecting || !config?.app_id}
                  >
                    <i className={`${connecting ? 'fa-solid fa-spinner fa-spin' : 'fa-brands fa-facebook'}`} />
                    Connect Facebook
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={handleDisconnect}
                  >
                    <i className="fa-solid fa-plug-circle-xmark" />
                    Disconnect Facebook
                  </button>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
