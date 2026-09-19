import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import VideosPanel from '../components/VideosPanel'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ChannelVideos() {
  const { token } = useAuth()
  const { toast } = useUI()
  const { client, clientId, channelId, channelMeta, setChannelMeta } = useOutletContext()

  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)

  const loadVideos = useCallback(async () => {
    if (!token || !clientId || !channelId) return
    setLoading(true)
    try {
      const data = await api.listVideos(token, clientId, channelId)
      setVideos(data.videos || [])
    } catch (err) {
      toast(`Failed to load videos: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, channelId, toast])

  useEffect(() => {
    loadVideos()
  }, [loadVideos])

  async function handleSync() {
    const data = await api.syncVideos(token, clientId, channelId)
    setVideos(data.videos || [])
    if (channelMeta && setChannelMeta) {
      setChannelMeta({ ...channelMeta, video_count: data.videos?.length ?? 0 })
    }
    return data.videos?.length ?? 0
  }

  async function handleUpdate(videoId, videoChannelId, notes, metadataFields) {
    try {
      const updatedVideo = await api.updateVideo(
        token,
        videoId,
        clientId,
        videoChannelId || channelId,
        notes,
        metadataFields,
      )
      setVideos((prev) =>
        prev.map((v) =>
          v.id === videoId
            ? {
                ...v,
                notes: updatedVideo.notes,
                metadata_fields: updatedVideo.metadata_fields,
              }
            : v,
        ),
      )
      toast('Video updated successfully!', 'success')
      return updatedVideo
    } catch (err) {
      toast(`Error updating video: ${err.message}`, 'error')
      throw err
    }
  }

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
              { label: 'Videos' },
            ]}
          />
          <h1>Videos Database</h1>
          <p>{channelMeta?.title || 'Channel videos'}</p>
        </div>
      </header>

      {loading ? (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading videos...</span>
          </div>
        </div>
      ) : (
        <VideosPanel videos={videos} onSync={handleSync} onUpdate={handleUpdate} />
      )}
    </>
  )
}
