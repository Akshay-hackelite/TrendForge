import { useMemo, useState } from 'react'
import { apiFetch } from '../../api'
import VideoUrlAttachField from '../VideoUrlAttachField'
import { localeHasTitle, maybeAdvanceStage } from './trackerUtils'

export default function TrackerPublishVideo({ card, weekContext, onChange }) {
  const { token, clientId, toast, channels = [] } = weekContext
  const locales = card.yt_locales || {}
  const hasMeta = localeHasTitle(locales)
  const meta = locales.hinglish || Object.values(locales).find((loc) => loc?.yt_title) || {}
  const [postToYT, setPostToYT] = useState(true)
  const [postToIG, setPostToIG] = useState(false)
  const [postToFB, setPostToFB] = useState(false)
  const [selectedChannelIds, setSelectedChannelIds] = useState(channels[0] ? [channels[0].id] : [])
  const [videoUrlsByChannel, setVideoUrlsByChannel] = useState({})
  const [socialVideoLink, setSocialVideoLink] = useState('')
  const [busy, setBusy] = useState(false)

  const selectedYtChannels = useMemo(
    () => channels.filter((c) => selectedChannelIds.includes(c.id)),
    [channels, selectedChannelIds],
  )
  const firstSelectedUrl = useMemo(() => {
    const first = selectedYtChannels[0]
    return (first && videoUrlsByChannel[first.id]) || ''
  }, [selectedYtChannels, videoUrlsByChannel])

  async function handlePublish() {
    if (!card.topic_id) {
      toast('Choose a generated script first.', 'error')
      return
    }
    if (!hasMeta) {
      toast('Generate YouTube metadata first.', 'error')
      return
    }
    if (!postToYT && !postToIG && !postToFB) {
      toast('Select at least one platform.', 'error')
      return
    }
    if (postToYT && selectedChannelIds.length === 0) {
      toast('Select at least one YouTube channel.', 'error')
      return
    }
    if (postToYT) {
      for (const ch of selectedYtChannels) {
        if (!(videoUrlsByChannel[ch.id] || '').trim()) {
          toast(`Add a video URL for "${ch.title || ch.id}".`, 'error')
          return
        }
      }
    }
    const socialUrl = (socialVideoLink || firstSelectedUrl || Object.values(videoUrlsByChannel).find(Boolean) || '').trim()
    if ((postToIG || postToFB) && !postToYT && !socialUrl) {
      toast('Please provide a social video URL.', 'error')
      return
    }

    setBusy(true)
    try {
      if (postToYT) {
        const socialChannelId = selectedYtChannels[0]?.id
        for (const ch of selectedYtChannels) {
          const cleanTags = (meta.yt_tags || []).map((t) => String(t).replace(/#/g, ''))
          const attachSocial = (postToIG || postToFB) && ch.id === socialChannelId
          await apiFetch('/video.upload', {
            token,
            body: {
              client_id: clientId,
              channel_id: ch.id,
              drive_link: (videoUrlsByChannel[ch.id] || '').trim(),
              title: meta.yt_title || card.title,
              description: meta.yt_description || '',
              tags: cleanTags,
              thumbnail_url: meta.yt_thumbnail_url,
              post_to_instagram: attachSocial && postToIG,
              post_to_facebook: attachSocial && postToFB,
              topic_id: card.topic_id,
              language: 'hinglish',
              social_source_url: attachSocial ? (socialVideoLink || firstSelectedUrl || '').trim() || undefined : undefined,
            },
          })
        }
      } else {
        const cleanTags = (meta.yt_tags || []).map((t) => String(t).replace(/#/g, ''))
        await apiFetch('/video.upload', {
          token,
          body: {
            client_id: clientId,
            channel_id: channels[0]?.id || '',
            drive_link: socialUrl,
            title: meta.yt_title || card.title,
            description: meta.yt_description || '',
            tags: cleanTags,
            thumbnail_url: meta.yt_thumbnail_url,
            post_to_instagram: postToIG,
            post_to_facebook: postToFB,
            topic_id: card.topic_id,
            language: 'hinglish',
            social_source_url: socialUrl || undefined,
          },
        })
      }
      const result = await weekContext.reloadWeek?.()
      if (!result) {
        onChange(maybeAdvanceStage({ ...card, stage: 'posted' }))
      }
      toast('Video posted.', 'success')
      setVideoUrlsByChannel({})
      setSocialVideoLink('')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="tracker-script-slot tracker-publish">
      <div className="tracker-script-slot-head">
        <span className="tracker-kicker">Publish video</span>
      </div>
      {!hasMeta ? (
        <p className="tracker-hint">Generate YouTube metadata first, then publish from here.</p>
      ) : (
        <>
          <p className="tracker-publish-label">Where do you want to post?</p>
          <div className="tracker-platform-picks">
            <label className={`tracker-platform-pick${postToYT ? ' is-on' : ''}`}>
              <input type="checkbox" checked={postToYT} onChange={(e) => setPostToYT(e.target.checked)} />
              <i className="fa-brands fa-youtube" style={{ color: '#ff0000' }} />
            </label>
            <label className={`tracker-platform-pick${postToIG ? ' is-on' : ''}`}>
              <input type="checkbox" checked={postToIG} onChange={(e) => setPostToIG(e.target.checked)} />
              <i className="fa-brands fa-instagram" style={{ color: '#E1306C' }} />
            </label>
            <label className={`tracker-platform-pick${postToFB ? ' is-on' : ''}`}>
              <input type="checkbox" checked={postToFB} onChange={(e) => setPostToFB(e.target.checked)} />
              <i className="fa-brands fa-facebook" style={{ color: '#1877F2' }} />
            </label>
          </div>

          {postToYT && (
            <div className="tracker-channel-pick">
              <strong>Select YouTube Channels ({selectedChannelIds.length})</strong>
              <div className="tracker-channel-list">
                {channels.map((ch) => {
                  const isSel = selectedChannelIds.includes(ch.id)
                  return (
                    <button
                      type="button"
                      key={ch.id}
                      className={`tracker-channel-row${isSel ? ' is-on' : ''}`}
                      onClick={() => setSelectedChannelIds((prev) => (
                        prev.includes(ch.id) ? prev.filter((id) => id !== ch.id) : [...prev, ch.id]
                      ))}
                    >
                      <input type="checkbox" checked={isSel} readOnly />
                      <span>{ch.title || ch.id}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {postToYT && selectedYtChannels.length > 0 && (
            <div className="tracker-drive-list">
              <strong>Video URL for each channel</strong>
              <p className="tracker-hint">Each selected channel gets its own video URL. The same metadata is used for every channel.</p>
              {selectedYtChannels.map((ch) => (
                <div key={ch.id} className="tracker-drive-row">
                  <span>{ch.title || ch.id}</span>
                  <VideoUrlAttachField
                    token={token}
                    clientId={clientId}
                    toast={toast}
                    value={videoUrlsByChannel[ch.id] || ''}
                    onChange={(url) => setVideoUrlsByChannel((prev) => ({ ...prev, [ch.id]: url }))}
                  />
                </div>
              ))}
            </div>
          )}

          {(postToIG || postToFB) && (
            <div className="tracker-drive-row">
              <span>Social video URL</span>
              <VideoUrlAttachField
                token={token}
                clientId={clientId}
                toast={toast}
                placeholder={firstSelectedUrl ? 'Optional — uses the first channel URL if blank' : 'https://drive.google.com/...'}
                value={socialVideoLink}
                onChange={setSocialVideoLink}
              />
            </div>
          )}

          <button type="button" className="btn btn-primary" disabled={busy} onClick={handlePublish}>
            {busy ? 'Uploading…' : (
              <>
                <i className="fa-solid fa-paper-plane" /> Publish Video
              </>
            )}
          </button>
        </>
      )}
    </section>
  )
}
