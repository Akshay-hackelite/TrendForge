import { useEffect, useRef } from 'react'
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import { useUI } from './context/UIContext'
import AppShell from './layouts/AppShell'
import ChannelLayout from './layouts/ChannelLayout'
import ClientLayout from './layouts/ClientLayout'
import SocialMediaLayout from './layouts/SocialMediaLayout'
import AdminDashboard from './pages/AdminDashboard'
import ChannelOverview from './pages/ChannelOverview'
import ChannelSettings from './pages/ChannelSettings'
import ChannelVideos from './pages/ChannelVideos'
import ClientHub from './pages/ClientHub'
import ClientOverview from './pages/ClientOverview'
import ClientSettings from './pages/ClientSettings'
import ClientContentPlan from './pages/ClientContentPlan'
import ClientReportDetail from './pages/ClientReportDetail'
import ClientReports from './pages/ClientReports'
import ClientScripts from './pages/ClientScripts'
import ClientPostVideo from './pages/ClientPostVideo'
import ClientSocialGenerate from './pages/ClientSocialGenerate'
import ClientSocialInstagram from './pages/ClientSocialInstagram'
import ClientSocialInstagramAnalytics from './pages/ClientSocialInstagramAnalytics'
import ClientSocialFacebook from './pages/ClientSocialFacebook'
import ClientSocialSchedule from './pages/ClientSocialSchedule'
import ClientSocialFestivals from './pages/ClientSocialFestivals'
import ClientWeeklyTracker from './pages/ClientWeeklyTracker'
import ClientCustomTracker from './pages/ClientCustomTracker'
import PocWeeklyTracker from './pages/PocWeeklyTracker'
import TrackerClientSheet from './pages/TrackerClientSheet'
import ClientVideos from './pages/ClientVideos'
import ClientsIndex from './pages/ClientsIndex'
import AuthPage from './pages/AuthPage'

function RequireAuth({ children }) {
  const { token, user, loading } = useAuth()

  if (loading) {
    return (
      <div className="login-page">
        <p className="text-muted">Loading…</p>
      </div>
    )
  }

  if (!token || !user) {
    return <Navigate to="/login" replace />
  }

  return children
}

function HomeRedirect() {
  const { user } = useAuth()
  if (user?.active_client_id) {
    return <Navigate to={`/clients/${user.active_client_id}`} replace />
  }
  return <Navigate to="/clients" replace />
}

function OAuthSuccessHandler() {
  const { token, refreshUser } = useAuth()
  const { toast } = useUI()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const handled = useRef(false)

  useEffect(() => {
    if (searchParams.get('google_auth') !== 'success' || handled.current) return
    handled.current = true

    ;(async () => {
      const me = token ? await refreshUser() : null
      toast('YouTube channel linked successfully!', 'success')
      setSearchParams({}, { replace: true })
      const clientId = me?.active_client_id
      navigate(clientId ? `/clients/${clientId}/videos` : '/clients', { replace: true })
    })()
  }, [searchParams, token, refreshUser, toast, setSearchParams, navigate])

  return null
}

function ClientIdGuard({ children }) {
  const { clientId } = useParams()
  const { user } = useAuth()
  const exists = (user?.clients || []).some((c) => c.id === clientId)
  if (user?.clients && !exists) {
    return <Navigate to="/clients" replace />
  }
  return children
}

export default function App() {
  return (
    <>
      <OAuthSuccessHandler />
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/register" element={<AuthPage />} />
        <Route path="/admin" element={<AdminDashboard />} />

        <Route
          path="/"
          element={
            <RequireAuth>
              <HomeRedirect />
            </RequireAuth>
          }
        />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/clients" element={<ClientsIndex />} />
          <Route path="/tracker" element={<PocWeeklyTracker />} />
          <Route path="/tracker/:clientId" element={<TrackerClientSheet mode="weekly" />} />
          <Route path="/tracker/:clientId/custom" element={<TrackerClientSheet mode="custom" />} />
        </Route>

        <Route
          path="/clients/:clientId"
          element={
            <RequireAuth>
              <ClientIdGuard>
                <AppShell />
              </ClientIdGuard>
            </RequireAuth>
          }
        >
          <Route index element={<ClientHub />} />
        </Route>

        <Route
          path="/clients/:clientId/videos"
          element={
            <RequireAuth>
              <ClientIdGuard>
                <ClientLayout />
              </ClientIdGuard>
            </RequireAuth>
          }
        >
          <Route index element={<ClientOverview />} />
          <Route path="library" element={<ClientVideos />} />
          <Route path="post" element={<ClientPostVideo />} />
          <Route path="content-plan" element={<ClientContentPlan />} />
          <Route path="tracker" element={<ClientWeeklyTracker />} />
          <Route path="tracker/custom" element={<ClientCustomTracker />} />
          <Route path="reports" element={<ClientReports />} />
          <Route path="reports/:reportId" element={<ClientReportDetail />} />
          <Route path="scripts" element={<ClientScripts />} />
          <Route path="settings" element={<ClientSettings />} />
          <Route path="channels/:channelId" element={<ChannelLayout />}>
            <Route index element={<ChannelOverview />} />
            <Route path="library" element={<ChannelVideos />} />
            <Route path="settings" element={<ChannelSettings />} />
          </Route>
        </Route>

        <Route
          path="/clients/:clientId/social"
          element={
            <RequireAuth>
              <ClientIdGuard>
                <SocialMediaLayout />
              </ClientIdGuard>
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="generate" replace />} />
          <Route path="instagram" element={<ClientSocialInstagram />} />
          <Route path="analytics" element={<ClientSocialInstagramAnalytics />} />
          <Route path="facebook" element={<ClientSocialFacebook />} />
          <Route path="generate" element={<ClientSocialGenerate />} />
          <Route path="schedule" element={<ClientSocialSchedule />} />
          <Route path="festivals" element={<ClientSocialFestivals />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
