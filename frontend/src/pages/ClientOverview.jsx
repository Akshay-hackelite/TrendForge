import { useCallback, useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import AnalyticsPanel from '../components/AnalyticsPanel'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientOverview() {
  const { token } = useAuth()
  const { toast } = useUI()
  const { client, clientId, channels, loadingChannels, handleLinkChannel } = useOutletContext()

  const [channelMeta, setChannelMeta] = useState(null)
  const [loading, setLoading] = useState(false)

  const buildMeta = useCallback(async () => {
    if (!token || !clientId) return
    if (!channels?.length) {
      setChannelMeta(null)
      return
    }

    setLoading(true)
    try {
      const syntheticMeta = {
        id: 'all',
        title: 'All Channels Consolidated',
        description: `Aggregated data for ${channels.length} YouTube channel(s).`,
        subscriber_count: channels.reduce((sum, ch) => sum + Number(ch.subscriber_count || 0), 0),
        view_count: channels.reduce((sum, ch) => sum + Number(ch.view_count || 0), 0),
        video_count: channels.reduce((sum, ch) => sum + Number(ch.video_count || 0), 0),
      }
      setChannelMeta(syntheticMeta)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, channels, toast])

  useEffect(() => {
    if (!loadingChannels) buildMeta()
  }, [loadingChannels, buildMeta])

  const hasChannels = channels?.length > 0
  const hasProfile =
    client?.specialty ||
    client?.description ||
    client?.website_url

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client' },
            ]}
          />
          <h1>Overview</h1>
          <p>All Channels (Client-Level Consolidated View)</p>
        </div>
        <div className="header-actions">
          <div className="connection-status-pill card">
            <span className={`status-dot ${hasChannels ? 'connected' : 'disconnected'}`} />
            <span>
              {channels?.length || 0} channel{(channels?.length || 0) === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      </header>

      {hasProfile ? (
        <section className="client-profile-card card animate-fade-in">
          <div className="client-profile-header">
            <div>
              <h2>Brand profile</h2>
              {client.specialty && <span className="specialty-badge">{client.specialty}</span>}
            </div>
            <Link to={`/clients/${clientId}/videos/settings`} className="btn btn-secondary btn-sm">
              <i className="fa-solid fa-pen" /> Edit
            </Link>
          </div>
          {client.website_url && (
            <p className="profile-website">
              <i className="fa-solid fa-globe" />{' '}
              <a href={client.website_url} target="_blank" rel="noreferrer">
                {client.website_url.replace(/^https?:\/\//, '')}
              </a>
            </p>
          )}
          {client.description && <p className="profile-description">{client.description}</p>}
        </section>
      ) : (
        <section className="client-profile-empty card animate-fade-in">
          <div>
            <h2>Set up this brand</h2>
            <p>
              Add the website, niche, and description so you can plan content for this
              client. Topic keywords live in Settings.
            </p>
          </div>
          <Link to={`/clients/${clientId}/videos/settings`} className="btn btn-primary">
            <i className="fa-solid fa-user" /> Set up profile
          </Link>
        </section>
      )}

      {(loading || loadingChannels) && (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Analyzing channel stats...</span>
          </div>
        </div>
      )}

      {!loading && !loadingChannels && !hasChannels && (
        <div className="connect-prompt-container card animate-fade-in">
          <div className="prompt-illustration">
            <i className="fa-brands fa-youtube illustration-icon red-icon" />
          </div>
          <h2>No channels linked yet</h2>
          <p>
            Link YouTube channels to client <strong>&quot;{client?.name}&quot;</strong> using Google
            secure sign-in to populate analytics dashboards.
          </p>
          <button type="button" className="btn btn-primary btn-lg" onClick={handleLinkChannel}>
            <i className="fa-brands fa-youtube" /> Link YouTube Channel
          </button>
        </div>
      )}

      {!loading && !loadingChannels && hasChannels && channelMeta && (
        <AnalyticsPanel
          token={token}
          clientId={clientId}
          channelId="all"
          channelMeta={channelMeta}
        />
      )}
    </>
  )
}
