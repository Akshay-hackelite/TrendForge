import { useEffect, useMemo, useState } from 'react'
import { Outlet, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ChannelLayout() {
  const { channelId } = useParams()
  const { token, patchUser } = useAuth()
  const { toast } = useUI()
  const navigate = useNavigate()
  const parent = useOutletContext()
  const { clientId, channels, loadChannels } = parent

  const [channelMeta, setChannelMeta] = useState(null)
  const [loading, setLoading] = useState(true)

  const channelSummary = useMemo(
    () => (channels || []).find((c) => c.id === channelId) || null,
    [channels, channelId],
  )

  useEffect(() => {
    if (!token || !clientId || !channelId) return
    let cancelled = false

    ;(async () => {
      setLoading(true)
      try {
        // Sync backend active channel
        await api.selectChannel(token, channelId, clientId)
        if (cancelled) return

        const meta = await api.getChannel(token, channelId, clientId)
        if (cancelled) return
        setChannelMeta(meta)
        patchUser({
          active_client_id: clientId,
          active_channel_id: channelId,
        })
      } catch (err) {
        if (!cancelled) {
          toast(`Failed to load channel: ${err.message}`, 'error')
          navigate(`/clients/${clientId}/videos`, { replace: true })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [token, clientId, channelId, patchUser, toast, navigate])

  if (loading && !channelMeta) {
    return (
      <div className="loading-overlay inline-loading">
        <div className="spinner-loader">
          <i className="fa-solid fa-spinner fa-spin" />
          <span>Loading channel…</span>
        </div>
      </div>
    )
  }

  return (
    <Outlet
      context={{
        ...parent,
        channelId,
        channelMeta,
        channelSummary,
        setChannelMeta,
        reloadChannel: async () => {
          const meta = await api.getChannel(token, channelId, clientId)
          setChannelMeta(meta)
          if (loadChannels) await loadChannels()
          return meta
        },
      }}
    />
  )
}
