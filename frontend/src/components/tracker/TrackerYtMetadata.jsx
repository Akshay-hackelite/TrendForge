import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../api'
import { localeHasTitle, maybeAdvanceStage } from './trackerUtils'

const PAGE_SIZE = 9

export default function TrackerYtMetadata({ card, weekContext, onChange }) {
  const { token, clientId, toast, channels = [], reloadWeek } = weekContext
  const [generating, setGenerating] = useState(false)
  const [refining, setRefining] = useState(false)
  const [showRefs, setShowRefs] = useState(false)
  const [refChannelId, setRefChannelId] = useState(channels[0]?.id || '')
  const [videos, setVideos] = useState([])
  const [videoPage, setVideoPage] = useState(1)
  const [selectedRefIds, setSelectedRefIds] = useState([])
  const [refinePrompt, setRefinePrompt] = useState('')
  const locales = card.yt_locales || {}
  const hasMeta = localeHasTitle(locales)
  const preview = locales.hinglish || Object.values(locales).find((loc) => loc?.yt_title) || {}
  const linked = Boolean(card.content_plan_item_id)
  const busy = generating || refining

  useEffect(() => {
    if (!refChannelId && channels[0]?.id) setRefChannelId(channels[0].id)
  }, [channels, refChannelId])

  const loadVideos = useCallback(async (channelId) => {
    if (!token || !clientId || !channelId) return
    try {
      const data = await api.listVideos(token, clientId, channelId)
      const list = [...(data.videos || [])].sort((a, b) => String(b.published_at || '').localeCompare(String(a.published_at || '')))
      setVideos(list)
      setVideoPage(1)
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, clientId, toast])

  useEffect(() => {
    if (showRefs && refChannelId) loadVideos(refChannelId)
  }, [showRefs, refChannelId, loadVideos])

  const visibleVideos = useMemo(() => videos.slice(0, videoPage * PAGE_SIZE), [videos, videoPage])

  function applyLocales(nextLocales) {
    onChange(maybeAdvanceStage({ ...card, yt_locales: nextLocales || {} }))
  }

  async function refreshCardLocales(nextLocales) {
    if (nextLocales && localeHasTitle(nextLocales)) applyLocales(nextLocales)
    try {
      await reloadWeek?.()
    } catch {
      // Locales may already be on the card from applyLocales.
    }
  }

  async function handleGenerate() {
    if (!linked) {
      toast('Choose a generated script first.', 'error')
      return
    }
    setGenerating(true)
    let nextLocales = null
    try {
      const data = await api.generateYouTubeMetadata(token, clientId, {
        itemIds: [card.content_plan_item_id],
        referenceVideoIds: selectedRefIds,
        languages: ['hinglish'],
      })
      const item = (data.suggestions?.items || []).find((row) => row.id === card.content_plan_item_id)
      nextLocales = item?.yt_locales || null
      toast('YouTube metadata generated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
    await refreshCardLocales(nextLocales)
    setGenerating(false)
  }

  async function handleRefine() {
    if (!linked || !refinePrompt.trim()) {
      toast('Enter refine instructions.', 'error')
      return
    }
    setRefining(true)
    let nextLocales = null
    try {
      const data = await api.refineYouTubeMetadata(token, clientId, {
        itemId: card.content_plan_item_id,
        userPrompt: refinePrompt,
        referenceVideoIds: selectedRefIds,
        language: 'hinglish',
      })
      const item = (data.suggestions?.items || []).find((row) => row.id === card.content_plan_item_id)
      nextLocales = item?.yt_locales || locales
      setRefinePrompt('')
      toast('Metadata refined.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
    await refreshCardLocales(nextLocales)
    setRefining(false)
  }

  return (
    <section className="tracker-script-slot tracker-yt-meta">
      <div className="tracker-script-slot-head">
        <span className="tracker-kicker">YouTube metadata</span>
        {linked ? (
          <div className="tracker-script-slot-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy}
              onClick={() => setShowRefs((v) => !v)}
            >
              Choose reference ({selectedRefIds.length})
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={handleGenerate}
            >
              {generating ? (
                <>
                  <i className="fa-solid fa-spinner fa-spin" /> Generating…
                </>
              ) : hasMeta ? 'Regenerate' : 'Generate'}
            </button>
          </div>
        ) : null}
      </div>

      {!linked ? (
        <p className="tracker-hint">Choose a generated script first, then generate metadata here.</p>
      ) : null}

      {showRefs && (
        <div className="tracker-ref-grid-wrap">
          {channels.length > 1 && (
            <select
              className="form-control"
              value={refChannelId}
              onChange={(e) => setRefChannelId(e.target.value)}
            >
              {channels.map((ch) => (
                <option key={ch.id} value={ch.id}>{ch.title || ch.id}</option>
              ))}
            </select>
          )}
          <p className="tracker-hint">If you pick none, the newest 3 thumbnails are used.</p>
          <div className="tracker-ref-grid">
            {visibleVideos.map((video) => {
              const selected = selectedRefIds.includes(video.id)
              return (
                <button
                  type="button"
                  key={video.id}
                  className={`tracker-ref-tile${selected ? ' selected' : ''}`}
                  onClick={() => setSelectedRefIds(
                    selected ? selectedRefIds.filter((id) => id !== video.id) : [...selectedRefIds, video.id],
                  )}
                >
                  <img src={video.thumbnail_url} alt={video.title || ''} />
                </button>
              )
            })}
          </div>
          {videos.length > visibleVideos.length && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setVideoPage((n) => n + 1)}>
              Load more
            </button>
          )}
        </div>
      )}

      {hasMeta && (
        <>
          <div className="tracker-yt-preview">
            <div className="tracker-yt-preview-thumb">
              {preview.yt_thumbnail_url ? (
                <img src={preview.yt_thumbnail_url} alt="" />
              ) : (
                <div className="tracker-yt-thumb-empty">No thumbnail</div>
              )}
            </div>
            <div className="tracker-yt-preview-copy">
              <h4>{preview.yt_title}</h4>
              <p>{preview.yt_description}</p>
              {preview.yt_tags?.length ? (
                <small>{preview.yt_tags.map((t) => String(t).replace(/#/g, '')).join(', ')}</small>
              ) : null}
            </div>
          </div>
          <div className="tracker-refine-row">
            <input
              className="form-control"
              placeholder="E.g., Make the title more clickbait"
              value={refinePrompt}
              onChange={(e) => setRefinePrompt(e.target.value)}
            />
            <button type="button" className="btn btn-primary btn-sm" disabled={busy || !refinePrompt.trim()} onClick={handleRefine}>
              {refining ? (
                <>
                  <i className="fa-solid fa-spinner fa-spin" /> Refine
                </>
              ) : 'Refine'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
