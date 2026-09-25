import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useOutletContext, useSearchParams } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import TrackerWeekPicker from '../components/tracker/TrackerWeekPicker'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import api, { createStreamingMp3Player } from '../api'

const PLAYBACK_SPEEDS = [1, 1.25, 1.5, 2]

function formatAudioTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function assetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return `${base}${path}`
}

function buildCombinedScript(items) {
  return items
    .filter((i) => i.script)
    .map((item, idx) => {
      const title = item.title_hinglish || item.title_en || item.topic_text || `Video ${idx + 1}`
      const meta = [
        item.format,
        item.video_type,
        item.script_target_duration,
      ]
        .filter(Boolean)
        .join(' · ')
      return `——— ${idx + 1}. ${title} ———\n${meta}\n\n${item.script}`
    })
    .join('\n\n\n')
}

export default function ClientScripts() {
  const { token } = useAuth()
  const { toast } = useUI()
  const { client, clientId } = useOutletContext()
  const [searchParams] = useSearchParams()
  const focusItemId = searchParams.get('item')

  const [suggestions, setSuggestions] = useState(null)
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('list') // list | combined
  const [expandedId, setExpandedId] = useState(focusItemId || null)
  const [scriptEditPrompts, setScriptEditPrompts] = useState({})
  const [metadataEditPrompts, setMetadataEditPrompts] = useState({})
  const [scriptBusyId, setScriptBusyId] = useState(null)
  const [metadataBusyId, setMetadataBusyId] = useState(null)
  const [cardTab, setCardTab] = useState({}) // itemId -> 'script' | 'metadata'
  const [showYTModal, setShowYTModal] = useState(false)
  const [activeYTModalItem, setActiveYTModalItem] = useState(null)
  const [ytChannels, setYtChannels] = useState([])
  const [selectedYTChannelId, setSelectedYTChannelId] = useState('')
  const [ytVideos, setYtVideos] = useState([])
  const [selectedYTVideos, setSelectedYTVideos] = useState([])
  const [ytVideosPage, setYtVideosPage] = useState(1)

  // Upload UI state
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadItem, setUploadItem] = useState(null)
  const [uploadDriveLink, setUploadDriveLink] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [pickerItemId, setPickerItemId] = useState(null)
  const [attachBusyId, setAttachBusyId] = useState(null)

  const YT_PAGE_SIZE = 9
  const [narrateBusyKey, setNarrateBusyKey] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [audioFromCache, setAudioFromCache] = useState(false)
  const [audioStreaming, setAudioStreaming] = useState(false)
  const [audioPlaying, setAudioPlaying] = useState(false)
  const [audioCurrent, setAudioCurrent] = useState(0)
  const [audioDuration, setAudioDuration] = useState(0)
  const [audioBuffered, setAudioBuffered] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [lastNarrateArgs, setLastNarrateArgs] = useState(null)
  const audioUrlRef = useRef(null)
  const downloadUrlRef = useRef(null)
  const audioElRef = useRef(null)
  const audioBarRef = useRef(null)
  const streamPlayerRef = useRef(null)
  const playbackRateRef = useRef(1)
  // When swapping src (e.g. MSE → blob fallback), seek+play without restarting at 0.
  const resumeAfterSrcChangeRef = useRef(null)

  const load = useCallback(async () => {
    if (!token || !clientId) return
    setLoading(true)
    try {
      const data = await api.getContentPlan(token, clientId)
      setSuggestions(data.suggestions || null)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (focusItemId) setExpandedId(focusItemId)
  }, [focusItemId])

  // Intentionally do not revoke blob URLs on unmount: React Strict Mode
  // remounts in development and would invalidate the active audio src.
  // Previous URLs are revoked (delayed) when a new narration replaces them.

  // Keep custom player state in sync with the hidden <audio> element.
  useEffect(() => {
    const el = audioElRef.current
    if (!el) return

    const syncTime = () => {
      setAudioCurrent(el.currentTime || 0)
      const d = el.duration
      setAudioDuration(Number.isFinite(d) && d > 0 ? d : 0)
      try {
        if (el.buffered?.length) {
          setAudioBuffered(el.buffered.end(el.buffered.length - 1))
        }
      } catch {
        /* ignore InvalidStateError while MediaSource is opening */
      }
    }
    const onPlay = () => setAudioPlaying(true)
    const onPause = () => setAudioPlaying(false)
    const onEnded = () => {
      setAudioPlaying(false)
      syncTime()
    }

    el.addEventListener('timeupdate', syncTime)
    el.addEventListener('durationchange', syncTime)
    el.addEventListener('loadedmetadata', syncTime)
    el.addEventListener('progress', syncTime)
    el.addEventListener('play', onPlay)
    el.addEventListener('pause', onPause)
    el.addEventListener('ended', onEnded)
    // Re-apply preferred speed whenever the media element resets it (e.g. new src).
    el.playbackRate = playbackRateRef.current
    syncTime()

    return () => {
      el.removeEventListener('timeupdate', syncTime)
      el.removeEventListener('durationchange', syncTime)
      el.removeEventListener('loadedmetadata', syncTime)
      el.removeEventListener('progress', syncTime)
      el.removeEventListener('play', onPlay)
      el.removeEventListener('pause', onPause)
      el.removeEventListener('ended', onEnded)
    }
  }, [audioUrl])

  // Play once the <audio> has committed with the new src (blob or MediaSource).
  useEffect(() => {
    if (!audioUrl) return
    const el = audioElRef.current
    if (!el) return

    const resume = resumeAfterSrcChangeRef.current
    resumeAfterSrcChangeRef.current = null

    let cancelled = false
    const playWhenReady = () => {
      if (cancelled) return
      if (resume?.at > 0.25) {
        try {
          el.currentTime = resume.at
        } catch {
          /* ignore seek until metadata is ready */
        }
      }
      if (resume && resume.play === false) return
      el.playbackRate = playbackRateRef.current
      el.play().catch((err) => {
        console.warn('[narrate] play failed', err)
        toast('Narration ready — press play on the audio bar', 'info')
      })
    }

    if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      playWhenReady()
    } else {
      el.addEventListener('canplay', playWhenReady, { once: true })
    }

    return () => {
      cancelled = true
      el.removeEventListener('canplay', playWhenReady)
    }
  }, [audioUrl, toast])

  function toggleAudioPlayback() {
    const el = audioElRef.current
    if (!el || !audioUrl) return
    if (el.paused) {
      el.playbackRate = playbackRateRef.current
      el.play().catch((err) => {
        console.warn('[narrate] play failed', err, el.error)
        // MEDIA_ERR_SRC_NOT_SUPPORTED / decode — offer regenerate path
        if (el.error || el.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) {
          toast('Audio failed to load — try Regenerate', 'error')
        } else {
          toast('Could not play narration — press play again', 'error')
        }
      })
    } else {
      el.pause()
    }
  }

  function seekAudio(nextSeconds) {
    const el = audioElRef.current
    if (!el || !audioUrl || audioStreaming) return
    const d = el.duration
    if (!Number.isFinite(d) || d <= 0) return
    el.currentTime = Math.min(Math.max(0, nextSeconds), d)
    setAudioCurrent(el.currentTime)
  }

  function changePlaybackRate(rate) {
    playbackRateRef.current = rate
    setPlaybackRate(rate)
    const el = audioElRef.current
    if (el) el.playbackRate = rate
  }

  const items = suggestions?.items || []
  const scripted = useMemo(() => items.filter((i) => i.script || i.yt_title || i.yt_thumbnail_url), [items])
  const combinedText = useMemo(() => buildCombinedScript(scripted), [scripted])
  const anyBusy = Boolean(scriptBusyId || metadataBusyId || narrateBusyKey || attachBusyId)

  async function handleRefineScript(item) {
    if (!token || !clientId || !item?.id) return
    const prompt = (scriptEditPrompts[item.id] || '').trim()
    if (!prompt) {
      toast('Add an edit instruction for this script', 'error')
      return
    }
    setScriptBusyId(item.id)
    try {
      toast('Refining this script…', 'info')
      const data = await api.refineContentScript(token, clientId, {
        itemId: item.id,
        userPrompt: prompt,
      })
      setSuggestions(data.suggestions || null)
      setScriptEditPrompts((prev) => ({ ...prev, [item.id]: '' }))
      toast('Script updated', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setScriptBusyId(null)
    }
  }

  async function handleRefineMetadata(item) {
    if (!token || !clientId || !item?.id) return
    const prompt = (metadataEditPrompts[item.id] || '').trim()
    if (!prompt) {
      toast('Add an edit instruction for this metadata', 'error')
      return
    }
    setMetadataBusyId(item.id)
    try {
      toast('Refining YouTube metadata…', 'info')
      const data = await api.refineYouTubeMetadata(token, clientId, {
        itemId: item.id,
        userPrompt: prompt,
      })
      setSuggestions(data.suggestions || null)
      setMetadataEditPrompts((prev) => ({ ...prev, [item.id]: '' }))
      toast('Metadata updated', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setMetadataBusyId(null)
    }
  }

  async function handleOpenYTModal(e, item) {
    e.stopPropagation()
    setActiveYTModalItem(item)
    setShowYTModal(true)
    
    // Fetch channels if empty
    let currentChannels = ytChannels
    if (currentChannels.length === 0) {
      try {
        const cdata = await api.listChannels(token, clientId)
        currentChannels = cdata.channels || []
        setYtChannels(currentChannels)
        if (currentChannels.length > 0) {
          setSelectedYTChannelId(currentChannels[0].id)
        }
      } catch (err) {
        toast(err.message, 'error')
      }
    }
    
    const activeChannel = currentChannels.length > 0 ? currentChannels[0].id : null
    
    if (activeChannel) {
      try {
        const data = await api.listVideos(token, clientId, activeChannel)
        setYtVideos(data.videos || [])
      } catch (err) {
        toast(err.message, 'error')
      }
    }
  }

  async function handleChannelChange(e) {
    const chId = e.target.value
    setSelectedYTChannelId(chId)
    setYtVideos([])
    setYtVideosPage(1)
    try {
      const data = await api.listVideos(token, clientId, chId)
      setYtVideos(data.videos || [])
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleGenerateMetadataForCard(item) {
    if (!token || !clientId || !item?.id) return
    setMetadataBusyId(item.id)
    setShowYTModal(false)
    try {
      toast('Generating YouTube metadata…', 'info')
      const data = await api.generateYouTubeMetadata(token, clientId, {
        itemIds: [item.id],
        userPrompt: '',
        referenceVideoIds: selectedYTVideos,
      })
      setSuggestions(data.suggestions || null)
      setCardTab((prev) => ({ ...prev, [item.id]: 'metadata' }))
      toast('YouTube metadata generated!', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setMetadataBusyId(null)
    }
  }

  async function handleAttachToTracker(item, { year, month, week }) {
    if (!token || !clientId || !item?.id) return
    setAttachBusyId(item.id)
    try {
      const data = await api.attachTrackerScript(token, clientId, {
        itemId: item.id,
        year,
        month,
        week,
      })
      setPickerItemId(null)
      await load()
      if (data.status === 'already') {
        toast(`Already on Week ${week}`, 'info')
      } else {
        toast(`Added to Week ${week}`, 'success')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setAttachBusyId(null)
    }
  }

  function handleOpenUploadModal(e, item) {
    e.stopPropagation()
    // Fetch channels if not already fetched
    if (ytChannels.length === 0) {
      api.listChannels(token, clientId).then(cdata => {
        const channels = cdata.channels || []
        setYtChannels(channels)
        if (channels.length > 0) {
          setSelectedYTChannelId(channels[0].id)
        }
      }).catch(err => {
        toast(err.message, 'error')
      })
    } else if (!selectedYTChannelId && ytChannels.length > 0) {
      setSelectedYTChannelId(ytChannels[0].id)
    }
    
    setUploadItem(item)
    setShowUploadModal(true)
  }

  async function handleUploadSubmit(e) {
    e.preventDefault()
    if (!uploadDriveLink.trim()) {
      toast('Please enter a Google Drive link', 'error')
      return
    }
    if (!selectedYTChannelId) {
      toast('Please select a YouTube channel', 'error')
      return
    }

    setIsUploading(true)
    toast('Uploading to YouTube (this may take a minute)...', 'info')
    try {
      await api.uploadToYouTube(
        token, 
        clientId, 
        selectedYTChannelId,
        uploadDriveLink,
        uploadItem.yt_title || '',
        uploadItem.yt_description || '',
        uploadItem.yt_tags || [],
        uploadItem.yt_thumbnail_url || null
      )
      toast('Video uploaded to YouTube successfully!', 'success')
      setShowUploadModal(false)
      setUploadDriveLink('')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setIsUploading(false)
    }
  }


  async function handleNarrate({ itemId = null, combined = false, force = false } = {}) {
    if (!token || !clientId) return
    const key = combined ? 'combined' : itemId || 'combined'
    setNarrateBusyKey(key)
    setLastNarrateArgs({ itemId, combined })
    setAudioStreaming(false)
    setAudioPlaying(false)
    setAudioCurrent(0)
    setAudioDuration(0)
    setAudioBuffered(0)

    streamPlayerRef.current?.destroy()
    streamPlayerRef.current = null

    try {
      toast(
        force
          ? 'Regenerating narration…'
          : combined
            ? 'Streaming combined narration…'
            : 'Streaming narration…',
        'info',
      )

      let streamPlayer = null

      const { blob, cached } = await api.narrateContentScript(token, clientId, {
        itemId,
        combined,
        force,
        onStart: ({ cached: isCached }) => {
          setAudioFromCache(Boolean(isCached))
          // Fresh TTS: attach MediaSource early so playback can start mid-stream.
          if (!isCached && audioElRef.current) {
            streamPlayer = createStreamingMp3Player(audioElRef.current)
            streamPlayerRef.current = streamPlayer
            if (streamPlayer.supported && streamPlayer.objectUrl) {
              const prevUrl = audioUrlRef.current
              audioUrlRef.current = streamPlayer.objectUrl
              setAudioUrl(streamPlayer.objectUrl)
              setAudioStreaming(true)
              setAudioFromCache(false)
              if (prevUrl && prevUrl !== streamPlayer.objectUrl) {
                window.setTimeout(() => URL.revokeObjectURL(prevUrl), 30_000)
              }
              queueMicrotask(() => {
                audioBarRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
              })
              toast('Playing while audio generates…', 'info')
            }
          }
        },
        onChunk: (chunk) => {
          streamPlayer?.append(chunk)
        },
      })

      if (!blob || blob.size < 256) {
        throw new Error('Narration audio was empty')
      }

      const nextDownload = URL.createObjectURL(blob)
      const prevDownload = downloadUrlRef.current
      downloadUrlRef.current = nextDownload
      setDownloadUrl(nextDownload)
      if (prevDownload) {
        window.setTimeout(() => URL.revokeObjectURL(prevDownload), 30_000)
      }

      // Prefer keeping the MediaSource src so playback does not restart when
      // the download finishes. Only fall back to a blob URL if MSE failed.
      if (streamPlayer?.supported) {
        await streamPlayer.end().catch(() => {})
      }

      const el = audioElRef.current
      const mseOk =
        Boolean(streamPlayer?.supported) &&
        !streamPlayer?.failed &&
        Boolean(el) &&
        !el.error &&
        audioUrlRef.current === streamPlayer.objectUrl

      if (mseOk) {
        setAudioStreaming(false)
        // Leave streamPlayerRef attached until the next narrate/replace.
      } else {
        const resumeAt = el && Number.isFinite(el.currentTime) ? el.currentTime : 0
        const wasPlaying = Boolean(el && !el.paused)
        const nextUrl = URL.createObjectURL(blob)
        const prevUrl = audioUrlRef.current
        audioUrlRef.current = nextUrl
        resumeAfterSrcChangeRef.current = {
          at: resumeAt,
          // Fresh attach (or still near start): autoplay. Mid-handoff: only if already playing.
          play: resumeAt < 0.25 || wasPlaying,
        }
        setAudioUrl(nextUrl)
        setAudioStreaming(false)

        streamPlayerRef.current = null
        if (streamPlayer) {
          window.setTimeout(() => streamPlayer.destroy(), 0)
        }
        if (prevUrl && prevUrl !== nextUrl && prevUrl !== streamPlayer?.objectUrl) {
          window.setTimeout(() => URL.revokeObjectURL(prevUrl), 30_000)
        }
      }

      queueMicrotask(() => {
        audioBarRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })

      setAudioFromCache(Boolean(cached))
      if (cached) {
        toast(`Playing saved narration (${Math.round(blob.size / 1024)} KB)`, 'success')
      } else {
        toast(`Narration saved (${Math.round(blob.size / 1024)} KB)`, 'success')
      }
    } catch (err) {
      streamPlayerRef.current?.destroy()
      streamPlayerRef.current = null
      setAudioStreaming(false)
      toast(err.message, 'error')
    } finally {
      setNarrateBusyKey(null)
    }
  }

  async function copyText(text, label = 'Copied') {
    try {
      await navigator.clipboard.writeText(text)
      toast(label, 'success')
    } catch {
      toast('Could not copy', 'error')
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
              { label: 'Content Plan', to: `/clients/${clientId}/videos/content-plan` },
              { label: 'Scripts' },
            ]}
          />
          <h1>Scripts</h1>
          <p>Review generated scripts, combined read-through, and AI narration</p>
        </div>
        <div className="header-actions plan-header-actions">
          <Link to={`/clients/${clientId}/videos/content-plan`} className="btn btn-secondary">
            <i className="fa-solid fa-lightbulb" />
            Content Plan
          </Link>
          <button
            type="button"
            className={`btn ${view === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            disabled={loading}
            onClick={() => setView('list')}
          >
            By video
          </button>
          <button
            type="button"
            className={`btn ${view === 'combined' ? 'btn-primary' : 'btn-secondary'}`}
            disabled={loading || scripted.length === 0}
            onClick={() => setView('combined')}
          >
            Combined
          </button>
        </div>
      </header>

      <section
        ref={audioBarRef}
        className={`card scripts-audio-bar animate-fade-in${audioUrl ? '' : ' is-hidden'}`}
        hidden={!audioUrl}
      >
        <div className="scripts-audio-top">
          <div className="scripts-audio-heading">
            <span className="plan-script-label">AI narration</span>
            {audioStreaming && (
              <span className="scripts-audio-live">
                <span className="scripts-audio-live-dot" aria-hidden />
                Live
              </span>
            )}
            <p className="text-muted">
              {audioStreaming
                ? 'Streaming live from AI…'
                : audioFromCache
                  ? 'Playing saved audio (reused until the script changes)'
                  : 'Hindi/Hinglish TTS — saved for replay'}
            </p>
          </div>
          <div className="scripts-audio-actions">
            {audioUrl && (
              <>
                <a
                  className="btn btn-secondary btn-sm"
                  href={downloadUrl || audioUrl}
                  download="script-narration.mp3"
                >
                  <i className="fa-solid fa-download" />
                  Download MP3
                </a>
                {lastNarrateArgs && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={anyBusy}
                    title="Call OpenAI again and replace the saved file"
                    onClick={() =>
                      handleNarrate({
                        ...lastNarrateArgs,
                        force: true,
                      })
                    }
                  >
                    <i className="fa-solid fa-arrows-rotate" />
                    Regenerate
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        <audio
          ref={audioElRef}
          preload="auto"
          src={audioUrl || undefined}
          className="scripts-audio-element"
          onError={() => {
            // Ignore mid-stream MediaSource decode errors; we swap to a blob URL after download.
            if (audioUrl && !audioStreaming) {
              toast('Audio player failed to load the narration', 'error')
            }
          }}
        />

        {audioUrl && (
          <div className="scripts-audio-player">
            <button
              type="button"
              className="btn btn-primary btn-sm scripts-audio-play"
              onClick={toggleAudioPlayback}
              aria-label={audioPlaying ? 'Pause narration' : 'Play narration'}
            >
              <i className={`fa-solid ${audioPlaying ? 'fa-pause' : 'fa-play'}`} />
            </button>

            <div className="scripts-audio-timeline">
              <div className="scripts-audio-track">
                {audioStreaming && (
                  <div
                    className="scripts-audio-buffer"
                    style={{
                      width: `${
                        audioBuffered > 0
                          ? Math.min(100, (audioCurrent / Math.max(audioBuffered, audioCurrent, 0.01)) * 100)
                          : 8
                      }%`,
                    }}
                  />
                )}
                <input
                  type="range"
                  className="scripts-audio-seek"
                  min={0}
                  max={
                    audioStreaming
                      ? Math.max(audioBuffered, audioCurrent, 1)
                      : audioDuration > 0
                        ? audioDuration
                        : Math.max(audioCurrent, 1)
                  }
                  step={0.1}
                  value={Math.min(
                    audioCurrent,
                    audioStreaming
                      ? Math.max(audioBuffered, audioCurrent, 1)
                      : audioDuration > 0
                        ? audioDuration
                        : audioCurrent,
                  )}
                  disabled={audioStreaming || audioDuration <= 0}
                  aria-label="Seek narration"
                  onChange={(e) => seekAudio(Number(e.target.value))}
                />
              </div>
              <div className="scripts-audio-times">
                <span>{formatAudioTime(audioCurrent)}</span>
                <span>
                  {audioStreaming
                    ? 'streaming…'
                    : audioDuration > 0
                      ? formatAudioTime(audioDuration)
                      : '—:—'}
                </span>
              </div>
            </div>

            <div
              className="scripts-audio-speeds"
              role="group"
              aria-label="Playback speed"
            >
              {PLAYBACK_SPEEDS.map((rate) => (
                <button
                  key={rate}
                  type="button"
                  className={`scripts-audio-speed${playbackRate === rate ? ' is-active' : ''}`}
                  onClick={() => changePlaybackRate(rate)}
                >
                  {rate === 1 ? '1x' : `${rate}x`}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {loading && (
        <div className="inline-loading">
          <p className="text-muted">Loading scripts…</p>
        </div>
      )}

      {!loading && scripted.length === 0 && (
        <section className="client-profile-empty card">
          <div>
            <h2>No scripts yet</h2>
            <p>
              Generate titles on Content Plan, then run <strong>3. Generate scripts</strong>.
            </p>
          </div>
          <Link to={`/clients/${clientId}/videos/content-plan`} className="btn btn-primary">
            Go to Content Plan
          </Link>
        </section>
      )}

      {!loading && view === 'combined' && scripted.length > 0 && (
        <section className="card scripts-combined animate-fade-in">
          <div className="scripts-combined-header">
            <div>
              <h2>Combined script</h2>
              <p className="text-muted">
                {scripted.length} videos · read-through order matches the content plan
              </p>
            </div>
            <div className="scripts-combined-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={anyBusy}
                onClick={() => copyText(combinedText, 'Combined script copied')}
              >
                <i className="fa-solid fa-copy" />
                Copy all
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={anyBusy}
                onClick={() => handleNarrate({ combined: true })}
                title="Long combined text may be truncated for TTS"
              >
                <i
                  className={`fa-solid ${
                    narrateBusyKey === 'combined' ? 'fa-spinner fa-spin' : 'fa-volume-high'
                  }`}
                />
                Narrate with AI
              </button>
            </div>
          </div>
          <pre className="plan-script-body scripts-combined-body">{combinedText}</pre>
        </section>
      )}

      {!loading && view === 'list' && scripted.length > 0 && (
        <ol className="plan-list">
          {scripted.map((item, idx) => {
            const itemKey = item.id || String(idx)
            const isOpen = expandedId === itemKey
            const isScriptBusy = scriptBusyId === item.id
            const isMetadataBusy = metadataBusyId === item.id
            const isNarrating = narrateBusyKey === item.id
            return (
              <li
                key={itemKey}
                className={`plan-item card animate-fade-in ${isOpen ? 'is-open' : ''}`}
              >
                <button
                  type="button"
                  className="plan-item-summary"
                  disabled={anyBusy && !isScriptBusy && !isNarrating && !isMetadataBusy}
                  onClick={() => setExpandedId((cur) => (cur === itemKey ? null : itemKey))}
                  aria-expanded={isOpen}
                >
                  <div className="plan-item-rank">{idx + 1}</div>
                  <div className="plan-item-body">
                    <div className="plan-item-meta">
                      <span
                        className={`plan-format ${item.format === 'Short' ? 'is-short' : 'is-long'}`}
                      >
                        {item.format}
                      </span>
                      <span className="plan-theme">{item.video_type}</span>
                      {item.script_target_duration && (
                        <span className="plan-script-duration">{item.script_target_duration}</span>
                      )}
                    </div>
                    <h2 className="plan-title">{item.title_hinglish || item.working_title}</h2>
                    {(item.title_en || item.working_title) && (
                      <p className="plan-title-en">{item.title_en || item.working_title}</p>
                    )}
                    <p className="plan-keyword">
                      Keyword <strong>{item.topic_text}</strong>
                    </p>
                  </div>
                  <i
                    className={`fa-solid fa-chevron-${isOpen ? 'up' : 'down'} plan-item-chevron`}
                    aria-hidden
                  />
                </button>

                {isOpen && (
                  <div className="plan-item-nest">
                    {/* Tab Switcher */}
                    {(item.script || item.yt_title || item.yt_thumbnail_url) && (
                      <div className="card-tab-bar">
                        <div className={`card-tab-toggle${!item.script || !(item.yt_title || item.yt_thumbnail_url) ? ' single' : ''}`}>
                          {item.script && (
                            <button
                              type="button"
                              className={`card-tab-option${(cardTab[item.id] || 'script') === 'script' ? ' is-active' : ''}`}
                              onClick={() => setCardTab(p => ({ ...p, [item.id]: 'script' }))}
                            >
                              <i className="fa-solid fa-file-lines" />
                              Script
                            </button>
                          )}
                          {(item.yt_title || item.yt_thumbnail_url) && (
                            <button
                              type="button"
                              className={`card-tab-option${cardTab[item.id] === 'metadata' ? ' is-active' : ''}`}
                              onClick={() => setCardTab(p => ({ ...p, [item.id]: 'metadata' }))}
                            >
                              <i className="fa-brands fa-youtube" />
                              YT Metadata
                            </button>
                          )}
                          <div className="card-tab-slider" style={{ transform: cardTab[item.id] === 'metadata' ? 'translateX(100%)' : 'translateX(0)' }} />
                        </div>
                        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={(e) => handleOpenYTModal(e, item)}
                            title="Select YouTube Reference Images"
                          >
                            <i className="fa-regular fa-image" />
                            Select References
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={anyBusy}
                            onClick={(e) => { e.stopPropagation(); handleGenerateMetadataForCard(item) }}
                            title="Generate YouTube metadata for this card"
                          >
                            <i className={`fa-brands ${isMetadataBusy ? 'fa-spinner fa-spin' : 'fa-youtube'}`} />
                            {isMetadataBusy ? 'Generating…' : (item.yt_title ? 'Regen YT Metadata' : 'Generate YT Metadata')}
                          </button>
                          {item.script && (
                            (item.tracker_placements || []).length > 0 ? (
                              <>
                                <span className="tracker-added-label">Already added to tracker</span>
                                <div className="tracker-attach-wrap">
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    disabled={anyBusy}
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setPickerItemId((cur) => (cur === item.id ? null : item.id))
                                    }}
                                  >
                                    Add to another week
                                  </button>
                                  {pickerItemId === item.id && (
                                    <TrackerWeekPicker
                                      busy={attachBusyId === item.id}
                                      onConfirm={(when) => handleAttachToTracker(item, when)}
                                      onCancel={() => setPickerItemId(null)}
                                    />
                                  )}
                                </div>
                              </>
                            ) : (
                              <div className="tracker-attach-wrap">
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  disabled={anyBusy}
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setPickerItemId((cur) => (cur === item.id ? null : item.id))
                                  }}
                                >
                                  <i className="fa-solid fa-calendar-plus" />
                                  Add script to tracker
                                </button>
                                {pickerItemId === item.id && (
                                  <TrackerWeekPicker
                                    busy={attachBusyId === item.id}
                                    onConfirm={(when) => handleAttachToTracker(item, when)}
                                    onCancel={() => setPickerItemId(null)}
                                  />
                                )}
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}

                    {/* Script Tab */}
                    {item.script && (cardTab[item.id] || 'script') === 'script' && (
                      <div className="plan-script">
                        <div className="plan-script-meta">
                          <span className="plan-script-label">Script</span>
                          {item.script_hook_used && (
                            <span className="plan-script-hook">Hook · {item.script_hook_used}</span>
                          )}
                          {item.script_checklist_passed != null && (
                            <span
                              className={`plan-script-check ${
                                item.script_checklist_passed ? 'is-pass' : 'is-fail'
                              }`}
                            >
                              {item.script_checklist_passed ? 'Checklist pass' : 'Checklist review'}
                            </span>
                          )}
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={anyBusy}
                            onClick={(e) => {
                              e.stopPropagation()
                              copyText(item.script, 'Script copied')
                            }}
                          >
                            <i className="fa-solid fa-copy" />
                            Copy
                          </button>
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            disabled={anyBusy}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleNarrate({ itemId: item.id })
                            }}
                          >
                            <i
                              className={`fa-solid ${
                                isNarrating ? 'fa-spinner fa-spin' : 'fa-volume-high'
                              }`}
                            />
                            Narrate with AI
                          </button>
                        </div>
                        <pre className="plan-script-body">{item.script}</pre>
                        {item.script_cta && (
                          <p className="plan-script-cta">
                            CTA <strong>{item.script_cta}</strong>
                          </p>
                        )}

                        <div className="plan-script-edit">
                          <h3>Edit with AI</h3>
                          <p className="text-muted">
                            Only this script is sent — plus format metadata and your instruction.
                          </p>
                          <textarea
                            className="plan-regen-input"
                            rows={3}
                            placeholder="e.g. Softer host tone; complete intro sentence…"
                            value={scriptEditPrompts[item.id] || ''}
                            onChange={(e) =>
                              setScriptEditPrompts({ ...scriptEditPrompts, [item.id]: e.target.value })
                            }
                            onClick={(e) => e.stopPropagation()}
                          />
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={isScriptBusy || !(scriptEditPrompts[item.id] || '').trim()}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRefineScript(item)
                            }}
                          >
                            <i className={`fa-solid ${isScriptBusy ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}`} />
                            {isScriptBusy ? 'Refining…' : 'Refine script'}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* YT Metadata Tab */}
                    {(item.yt_title || item.yt_thumbnail_url) && cardTab[item.id] === 'metadata' && (
                      <div className="plan-script">
                        <div className="plan-script-meta">
                          <span className="plan-script-label">YouTube Metadata</span>
                        </div>
                        <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                          {item.yt_thumbnail_url && (
                            <img src={assetUrl(item.yt_thumbnail_url)} alt="Thumbnail" style={{ width: 240, height: 135, objectFit: 'cover', borderRadius: 8, flexShrink: 0, border: '1px solid var(--border)' }} />
                          )}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <label style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: 4, display: 'block' }}>Title</label>
                            <h4 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>{item.yt_title}</h4>
                            <label style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: 4, display: 'block' }}>Description</label>
                            <p style={{ whiteSpace: 'pre-wrap', margin: '0 0 0.75rem', fontSize: '0.9rem', lineHeight: 1.5 }}>{item.yt_description}</p>
                            {item.yt_tags && (
                              <>
                                <label style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: 6, display: 'block' }}>Tags</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                  {(Array.isArray(item.yt_tags) ? item.yt_tags : String(item.yt_tags).split(',')).map((tag, i) => {
                                    const t = String(tag).trim()
                                    if (!t) return null
                                    return <span key={i} style={{ display: 'inline-block', padding: '3px 10px', borderRadius: 6, background: 'var(--primary-light)', fontSize: '0.8rem', color: 'var(--primary-hover)', fontWeight: 500 }}>{t.replace(/^#/, '')}</span>
                                  })}
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                        
                        <div className="plan-script-edit">
                          <h3>Edit with AI</h3>
                          <p className="text-muted">
                            Update the title, description, tags, or thumbnail. Image and text changes are handled separately.
                          </p>
                          <textarea
                            className="plan-regen-input"
                            rows={3}
                            value={metadataEditPrompts[item.id] || ''}
                            disabled={anyBusy}
                            placeholder="e.g. Make the title more clickbait, or change the thumbnail background to blue"
                            onChange={(e) => setMetadataEditPrompts(p => ({...p, [item.id]: e.target.value}))}
                          />
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            disabled={anyBusy || !(metadataEditPrompts[item.id] || '').trim()}
                            onClick={() => handleRefineMetadata(item)}
                          >
                            <i className={`fa-solid ${isMetadataBusy ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}`} />
                            {isMetadataBusy ? 'Refining…' : 'Refine Metadata'}
                          </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ marginLeft: '10px' }}
                              onClick={(e) => handleOpenUploadModal(e, item)}
                              disabled={anyBusy}
                            >
                              <i className="fa-brands fa-youtube" /> Upload to YouTube
                            </button>
                        </div>
                      </div>
                    )}

                    {/* No script yet: show generate button inline */}
                    {!item.script && !item.yt_title && !item.yt_thumbnail_url && (
                      <div className="plan-script-edit" style={{ marginTop: '1rem' }}>
                        <p className="text-muted">No script or metadata yet.</p>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={anyBusy}
                          onClick={(e) => { e.stopPropagation(); handleGenerateMetadataForCard(item) }}
                        >
                          <i className={`fa-brands ${isMetadataBusy ? 'fa-spinner fa-spin' : 'fa-youtube'}`} />
                          {isMetadataBusy ? 'Generating…' : 'Generate YT Metadata'}
                        </button>
                      </div>
                    )}

                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {showYTModal && (
        <div className="modal-backdrop" onClick={() => setShowYTModal(false)}>
          <div className="modal-content yt-ref-modal" onClick={(e) => e.stopPropagation()} style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 8px 48px rgba(0,0,0,0.45)', borderRadius: 12, maxWidth: 720, width: '95vw' }}>
            <header className="modal-header" style={{ borderBottom: '1px solid var(--border)', padding: '1.25rem 1.5rem' }}>
              <div>
                <h2 style={{ margin: 0 }}>Reference YouTube Thumbnails</h2>
                <p className="text-muted" style={{ margin: '0.25rem 0 0', fontSize: '0.85rem' }}>Select thumbnails as style references. Default: 3 most recent.</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <select
                  className="input"
                  style={{ width: 'auto', minWidth: '150px' }}
                  value={selectedYTChannelId}
                  onChange={handleChannelChange}
                >
                  <option value="" disabled>Select Channel</option>
                  {ytChannels.map(ch => (
                    <option key={ch.id} value={ch.id}>{ch.title}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn-close"
                  onClick={() => setShowYTModal(false)}
                  aria-label="Close"
                >
                  <i className="fa-solid fa-xmark" />
                </button>
              </div>
            </header>
            <div className="modal-body" style={{ maxHeight: '55vh', overflowY: 'auto', padding: '1.25rem 1.5rem', background: 'var(--surface)' }}>
              {ytVideos.length === 0 && (
                <p className="text-muted">Loading thumbnails…</p>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                {ytVideos.slice(0, ytVideosPage * YT_PAGE_SIZE).map(v => {
                  const thumb = v.thumbnail_url
                  const isSelected = selectedYTVideos.includes(v.id)
                  if (!thumb) return null
                  return (
                    <div 
                      key={v.id} 
                      onClick={() => {
                        setSelectedYTVideos(prev => 
                          prev.includes(v.id) ? prev.filter(id => id !== v.id) : [...prev, v.id]
                        )
                      }}
                      style={{ 
                        cursor: 'pointer', 
                        border: isSelected ? '3px solid var(--accent)' : '3px solid var(--border)',
                        borderRadius: 8,
                        overflow: 'hidden',
                        position: 'relative',
                        background: 'var(--bg)',
                        transition: 'border-color 0.15s, box-shadow 0.15s',
                        boxShadow: isSelected ? '0 0 0 2px var(--accent)' : 'none',
                      }}
                    >
                      <img src={thumb} alt={v.title} style={{ width: '100%', height: 'auto', display: 'block', aspectRatio: '16/9', objectFit: 'cover' }} />
                      {isSelected && (
                        <div style={{ position: 'absolute', top: 6, right: 6, background: 'var(--accent)', borderRadius: '50%', width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <i className="fa-solid fa-check" style={{ fontSize: 11, color: '#fff' }} />
                        </div>
                      )}
                      <p style={{ margin: 0, padding: '0.35rem 0.5rem', fontSize: '0.75rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', background: 'var(--surface)', color: 'var(--text-muted)' }}>{v.title}</p>
                    </div>
                  )
                })}
              </div>
              {ytVideos.length > ytVideosPage * YT_PAGE_SIZE && (
                <div style={{ textAlign: 'center', marginTop: '1rem' }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setYtVideosPage(p => p + 1)}
                  >
                    <i className="fa-solid fa-chevron-down" />
                    Load More ({ytVideos.length - ytVideosPage * YT_PAGE_SIZE} remaining)
                  </button>
                </div>
              )}
            </div>
            <footer className="modal-footer" style={{ borderTop: '1px solid var(--border)', padding: '1rem 1.5rem', background: 'var(--surface)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderBottomLeftRadius: 12, borderBottomRightRadius: 12 }}>
              {selectedYTVideos.length > 0 && (
                <span className="text-muted" style={{ flex: 1, lineHeight: '36px', fontSize: '0.85rem' }}>
                  {selectedYTVideos.length} selected
                </span>
              )}
              <button className="btn btn-secondary" onClick={() => setShowYTModal(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={() => handleGenerateMetadataForCard(activeYTModalItem)}
              >
                <i className="fa-brands fa-youtube" />
                Generate YT Metadata
              </button>
            </footer>
          </div>
        </div>
      )}

      {showUploadModal && (
        <div className="modal-backdrop" onClick={() => setShowUploadModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, maxWidth: 500, width: '90vw' }}>
            <form onSubmit={handleUploadSubmit}>
              <header className="modal-header" style={{ borderBottom: '1px solid var(--border)', padding: '1.25rem 1.5rem' }}>
                <h2 style={{ margin: 0 }}>Upload to YouTube</h2>
                <button type="button" className="btn-close" onClick={() => setShowUploadModal(false)}><i className="fa-solid fa-xmark" /></button>
              </header>
              <div className="modal-body" style={{ padding: '1.25rem 1.5rem', background: 'var(--surface)' }}>
                <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                    YouTube Channel
                  </label>
                  <select
                    className="input"
                    value={selectedYTChannelId}
                    onChange={handleChannelChange}
                    required
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px' }}
                  >
                    <option value="" disabled>Select Channel</option>
                    {ytChannels.map(ch => (
                      <option key={ch.id} value={ch.id}>{ch.title}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-main)' }}>
                    Google Drive Link (Video File)
                  </label>
                  <input
                    type="url"
                    className="input"
                    placeholder="https://drive.google.com/file/d/..."
                    value={uploadDriveLink}
                    onChange={(e) => setUploadDriveLink(e.target.value)}
                    required
                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px' }}
                  />
                  <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'rgba(255, 193, 7, 0.1)', borderLeft: '4px solid #ffc107', borderRadius: '4px' }}>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      <strong>Important:</strong> The video will be uploaded as <strong>Public</strong> and go live immediately. Ensure your Drive link is "Anyone with the link can view".
                    </p>
                  </div>
                </div>
              </div>
              <footer className="modal-footer" style={{ borderTop: '1px solid var(--border)', padding: '1rem 1.5rem', background: 'var(--surface)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowUploadModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={isUploading}>
                  {isUploading ? <><i className="fa-solid fa-spinner fa-spin" /> Uploading...</> : <><i className="fa-solid fa-cloud-arrow-up" /> Upload Video</>}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}


    </>
  )
}
