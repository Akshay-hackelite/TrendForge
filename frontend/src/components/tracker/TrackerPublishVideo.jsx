import { useMemo, useState } from 'react'
import { apiFetchProgress } from '../../api'
import PublishProgressBusy from '../PublishProgressBusy'
import VideoUrlAttachField from '../VideoUrlAttachField'
import { usePublishProgressStages } from '../../hooks/usePublishProgressStages'
import { hinglishChannel, languageName, publishValidation, videoUploadBody } from '../../publishVideo'
import { localeHasTitle, maybeAdvanceStage } from './trackerUtils'

export default function TrackerPublishVideo({ card, weekContext, onChange }) {
  const { token, clientId, toast, channels = [] } = weekContext
  const locales = card.yt_locales || {}
  const hasMeta = localeHasTitle(locales)
  const [postToYT, setPostToYT] = useState(true)
  const [postToIG, setPostToIG] = useState(false)
  const [postToFB, setPostToFB] = useState(false)
  const [selectedChannelIds, setSelectedChannelIds] = useState(channels[0] ? [channels[0].id] : [])
  const [videoUrlsByChannel, setVideoUrlsByChannel] = useState({})
  const [socialVideoLink, setSocialVideoLink] = useState('')
  const progress = usePublishProgressStages()

  const selectedYtChannels = useMemo(
    () => channels.filter((channel) => selectedChannelIds.includes(channel.id)),
    [channels, selectedChannelIds],
  )
  const hinglish = hinglishChannel(selectedYtChannels)
  const hinglishUrl = hinglish ? (videoUrlsByChannel[hinglish.id] || '').trim() : ''

  async function handlePublish() {
    if (!card.topic_id) {
      toast('Choose a generated script first.', 'error')
      return
    }
    if (!hasMeta) {
      toast('Generate YouTube metadata first.', 'error')
      return
    }
    const problem = publishValidation({
      surface: 'tracker',
      postToYT,
      postToIG,
      postToFB,
      selectedChannels: selectedYtChannels,
      videoUrlsByChannel,
      socialVideoLink,
      locales,
    })
    if (problem) {
      toast(problem, 'error')
      return
    }

    progress.start()
    try {
      const result = await apiFetchProgress('/video.upload', {
        token,
        body: videoUploadBody({
          clientId,
          topicId: card.topic_id,
          postToYT,
          postToIG,
          postToFB,
          selectedChannels: selectedYtChannels,
          videoUrlsByChannel,
          socialVideoLink,
          locales,
          fallbackChannelId: channels[0]?.id || '',
        }),
        onStage: progress.setStage,
      })
      if (result?.errors?.length) {
        toast(result.errors.join(' '), 'error')
      } else {
        toast('Video posted.', 'success')
        setVideoUrlsByChannel({})
        setSocialVideoLink('')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      progress.stop()
    }
    try {
      const reloaded = await weekContext.reloadWeek?.()
      if (!reloaded) {
        onChange(maybeAdvanceStage({ ...card, stage: 'posted' }))
      }
    } catch (err) {
      toast(`Tracker could not refresh (${err.message}). Log in again, then reopen this week.`, 'error')
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
                {channels.map((channel) => {
                  const isSel = selectedChannelIds.includes(channel.id)
                  const language = String(channel.language || '').trim()
                  return (
                    <button
                      type="button"
                      key={channel.id}
                      className={`tracker-channel-row${isSel ? ' is-on' : ''}`}
                      onClick={() => setSelectedChannelIds((prev) => (
                        prev.includes(channel.id) ? prev.filter((id) => id !== channel.id) : [...prev, channel.id]
                      ))}
                    >
                      <input type="checkbox" checked={isSel} readOnly />
                      <span>{channel.title || channel.id}</span>
                      <small>{language ? languageName(language) : 'No language in Settings'}</small>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {postToYT && selectedYtChannels.length > 0 && (
            <div className="tracker-drive-list">
              <strong>Video URL for each channel</strong>
              <p className="tracker-hint">Each selected channel gets its own link, and metadata follows the language in Settings.</p>
              {selectedYtChannels.map((channel) => (
                <div key={channel.id} className="tracker-drive-row">
                  <span>{channel.title || channel.id}</span>
                  <VideoUrlAttachField
                    token={token}
                    clientId={clientId}
                    toast={toast}
                    value={videoUrlsByChannel[channel.id] || ''}
                    onChange={(url) => setVideoUrlsByChannel((prev) => ({ ...prev, [channel.id]: url }))}
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
                placeholder={hinglishUrl ? 'Optional — uses Hinglish channel URL if blank' : 'https://drive.google.com/...'}
                value={socialVideoLink}
                onChange={setSocialVideoLink}
              />
            </div>
          )}

          <button type="button" className="btn btn-primary" disabled={progress.busy} onClick={handlePublish}>
            {progress.busy ? (
              <PublishProgressBusy stage={progress.stage} elapsed={progress.elapsed} />
            ) : (
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
