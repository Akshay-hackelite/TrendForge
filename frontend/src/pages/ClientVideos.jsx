import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import VideosPanel from '../components/VideosPanel'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientVideos() {
  const { token } = useAuth()
  const { toast } = useUI()
  const { client, clientId, channels, loadingChannels, handleLinkChannel } = useOutletContext()

  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(false)

  const loadVideos = useCallback(async () => {
    if (!token || !clientId || !channels?.length) {
      setVideos([])
      return
    }
    setLoading(true)
    try {
      const videosPromises = channels.map((ch) =>
        api.listVideos(token, clientId, ch.id).catch(() => ({ videos: [] })),
      )
      const allVideosResponses = await Promise.all(videosPromises)
      const combinedVideos = []
      allVideosResponses.forEach((res, index) => {
        const ch = channels[index]
        ;(res.videos || []).forEach((v) => {
          combinedVideos.push({
            ...v,
            channelId: ch.id,
            channelTitle: ch.title,
          })
        })
      })
      setVideos(combinedVideos)
    } catch (err) {
      toast(`Failed to load videos: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, channels, toast])

  useEffect(() => {
    if (!loadingChannels) loadVideos()
  }, [loadingChannels, loadVideos])

  async function handleSync() {
    toast('Syncing all channels in parallel...', 'info')
    const syncPromises = channels.map((ch) =>
      api.syncVideos(token, clientId, ch.id).catch((err) => {
        console.error(`Error syncing ${ch.title}:`, err)
        return { videos: [] }
      }),
    )
    const syncResponses = await Promise.all(syncPromises)
    const combinedVideos = []
    syncResponses.forEach((res, index) => {
      const ch = channels[index]
      ;(res.videos || []).forEach((v) => {
        combinedVideos.push({
          ...v,
          channelId: ch.id,
          channelTitle: ch.title,
        })
      })
    })
    setVideos(combinedVideos)
    return combinedVideos.length
  }

  async function handleUpdate(videoId, videoChannelId, notes, metadataFields) {
    try {
      const updatedVideo = await api.updateVideo(
        token,
        videoId,
        clientId,
        videoChannelId,
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

  const hasChannels = channels?.length > 0

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: 'Videos' },
            ]}
          />
          <h1>Videos Database</h1>
          <p>Consolidated videos across all channels</p>
        </div>
      </header>

      {(loading || loadingChannels) && (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading videos...</span>
          </div>
        </div>
      )}

      {!loading && !loadingChannels && !hasChannels && (
        <div className="connect-prompt-container card animate-fade-in">
          <div className="prompt-illustration">
            <i className="fa-brands fa-youtube illustration-icon red-icon" />
          </div>
          <h2>No channels linked yet</h2>
          <p>Link a YouTube channel to start syncing videos.</p>
          <button type="button" className="btn btn-primary btn-lg" onClick={handleLinkChannel}>
            <i className="fa-brands fa-youtube" /> Link YouTube Channel
          </button>
        </div>
      )}

      {!loading && !loadingChannels && hasChannels && (
        <VideosPanel
          videos={videos}
          onSync={handleSync}
          onUpdate={handleUpdate}
          isClientLevel
        />
      )}
    </>
  )
}
