import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'

export default function ChannelSettings() {
  const { client, clientId, channelId, channelMeta } = useOutletContext()

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              {
                label: channelMeta?.title || 'Channel',
                to: `/clients/${clientId}/videos/channels/${channelId}`,
              },
              { label: 'Settings' },
            ]}
          />
          <h1>Channel Settings</h1>
          <p>Configure channel-level preferences and features.</p>
        </div>
      </header>

      <div className="settings-stub card">
        <div className="settings-stub-icon">
          <i className="fa-solid fa-sliders" />
        </div>
        <h2>Coming soon</h2>
        <p>
          Deeper channel settings — sync schedules, metadata defaults, and publishing tools — will
          live here. The route is ready for those screens.
        </p>
        <ul className="settings-stub-list">
          <li>
            <i className="fa-solid fa-clock-rotate-left" /> Sync schedule
          </li>
          <li>
            <i className="fa-solid fa-tags" /> Metadata defaults
          </li>
          <li>
            <i className="fa-solid fa-chart-simple" /> Analytics preferences
          </li>
        </ul>
      </div>
    </>
  )
}
