import { useOutletContext } from 'react-router-dom'
import AnalyticsPanel from '../components/AnalyticsPanel'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'

export default function ChannelOverview() {
  const { token } = useAuth()
  const { client, clientId, channelId, channelMeta } = useOutletContext()

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: channelMeta?.title || 'Channel' },
            ]}
          />
          <h1>Overview</h1>
          <p>{channelMeta?.title || 'Channel analytics'}</p>
        </div>
        <div className="header-actions">
          <div className="connection-status-pill card">
            <span className="status-dot connected" />
            <span>Channel connected</span>
          </div>
        </div>
      </header>

      {channelMeta && (
        <AnalyticsPanel
          token={token}
          clientId={clientId}
          channelId={channelId}
          channelMeta={channelMeta}
        />
      )}
    </>
  )
}
