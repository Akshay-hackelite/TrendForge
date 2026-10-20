import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../api'
import { localeHasTitle, maybeAdvanceStage } from './trackerUtils'

const PAGE_SIZE = 9
const TITLE_MAX = 100
const DESCRIPTION_MAX = 5000
const TAGS_MAX = 500
const TAG_MAX = 100

function tagList(value) {
  return String(value || '')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function tagsInvalid(value) {
  const tags = tagList(value)
  if (tags.join(',').length > TAGS_MAX) return true
  return tags.some((tag) => tag.length > TAG_MAX || /[#<>]/.test(tag))
}

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
  const [editingMeta, setEditingMeta] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [descriptionDraft, setDescriptionDraft] = useState('')
  const [tagsDraft, setTagsDraft] = useState('')
  const [savingDescription, setSavingDescription] = useState(false)
  const locales = card.yt_locales || {}
  const hasMeta = localeHasTitle(locales)
  const previewLang = 'hinglish'
  const preview = locales.hinglish || Object.values(locales).find((loc) => loc?.yt_title) || {}
  const hasScript = Boolean(String(card.assets?.script_text || '').trim())
  const busy = generating || refining || savingDescription
  const format = card.type === 'short' ? 'Short' : 'Long'

  useEffect(() => {
    setEditingMeta(false)
    setTitleDraft('')
    setDescriptionDraft('')
    setTagsDraft('')
  }, [previewLang, card.id])

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
  const titleOver = titleDraft.length > TITLE_MAX
  const descriptionOver = descriptionDraft.length > DESCRIPTION_MAX
  const tagsOver = tagsInvalid(tagsDraft)
  const saveDisabled = busy || !titleDraft.trim() || titleOver || descriptionOver || tagsOver

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
    if (!hasScript) {
      toast('Add a script first, then generate metadata here.', 'error')
      return
    }
    const manualScript = card.assets?.script_source === 'manual'
      ? String(card.assets?.script_text || '').trim()
      : ''
    let topicId = card.topic_id
    if (!card.content_plan_item_id && !topicId) {
      topicId = crypto.randomUUID()
      onChange({ ...card, topic_id: topicId })
    }
    setGenerating(true)
    let nextLocales = null
    try {
      const data = card.content_plan_item_id
        ? await api.generateYouTubeMetadata(token, clientId, {
          itemIds: [card.content_plan_item_id],
          referenceVideoIds: selectedRefIds,
          languages: ['hinglish'],
          scriptOverride: manualScript || undefined,
          format,
        })
        : await api.generateYouTubeMetadata(token, clientId, {
          itemIds: [],
          referenceVideoIds: selectedRefIds,
          languages: ['hinglish'],
          scriptOverride: String(card.assets?.script_text || '').trim() || undefined,
          topicId,
          topicTitle: card.title,
          format,
        })
      if (!card.content_plan_item_id) {
        nextLocales = data.yt_locales || null
      } else {
        const item = (data.suggestions?.items || []).find((row) => row.id === card.content_plan_item_id)
        nextLocales = item?.yt_locales || data.yt_locales || null
      }
      toast('YouTube metadata generated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
    await refreshCardLocales(nextLocales)
    setGenerating(false)
  }

  async function handleRefine() {
    if (!hasScript || !refinePrompt.trim()) {
      toast('Enter refine instructions.', 'error')
      return
    }
    setRefining(true)
    let nextLocales = null
    try {
      const data = await api.refineYouTubeMetadata(token, clientId, {
        itemId: card.content_plan_item_id || undefined,
        userPrompt: refinePrompt,
        referenceVideoIds: selectedRefIds,
        language: 'hinglish',
        topicId: card.content_plan_item_id ? undefined : card.topic_id,
        topicTitle: card.title,
        format,
      })
      if (data.yt_locales) {
        nextLocales = data.yt_locales
      } else {
        const item = (data.suggestions?.items || []).find((row) => row.id === card.content_plan_item_id)
        nextLocales = item?.yt_locales || locales
      }
      setRefinePrompt('')
      toast('Metadata refined.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
    await refreshCardLocales(nextLocales)
    setRefining(false)
  }

  function startMetaEdit() {
    setTitleDraft(preview.yt_title || '')
    setDescriptionDraft(preview.yt_description || '')
    setTagsDraft((preview.yt_tags || []).map((tag) => String(tag).replace(/#/g, '')).join(', '))
    setEditingMeta(true)
  }

  async function saveMetaEdit() {
    if (!card.topic_id) {
      toast('Choose a generated script first.', 'error')
      return
    }
    setSavingDescription(true)
    try {
      const data = await api.updateYouTubeDescription(token, clientId, {
        topicId: card.topic_id,
        language: previewLang,
        title: titleDraft.trim(),
        description: descriptionDraft,
        tags: tagList(tagsDraft),
      })
      setEditingMeta(false)
      toast('Metadata saved.', 'success')
      await refreshCardLocales(data.yt_locales)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingDescription(false)
    }
  }

  return (
    <section className="tracker-script-slot tracker-yt-meta">
      <div className="tracker-script-slot-head">
        <span className="tracker-kicker">YouTube metadata</span>
        {hasScript ? (
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
              ) : hasMeta ? 'Regenerate metadata' : 'Generate metadata'}
            </button>
          </div>
        ) : null}
      </div>

      {!hasScript ? (
        <p className="tracker-hint">Add a script first, then generate metadata here.</p>
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
              {editingMeta ? (
                <>
                  <label className="tracker-meta-field">
                    <span>Title</span>
                    <input className="form-control" value={titleDraft} onChange={(e) => setTitleDraft(e.target.value)} />
                    <small className={`char-count${titleOver ? ' is-over' : ''}`}>{titleDraft.length} / {TITLE_MAX}</small>
                  </label>
                  <label className="tracker-meta-field">
                    <span>Description</span>
                    <textarea className="form-control" rows={5} value={descriptionDraft} onChange={(e) => setDescriptionDraft(e.target.value)} />
                    <small className={`char-count${descriptionOver ? ' is-over' : ''}`}>{descriptionDraft.length} / {DESCRIPTION_MAX}</small>
                  </label>
                  <label className="tracker-meta-field">
                    <span>Tags</span>
                    <textarea className="form-control" rows={3} value={tagsDraft} onChange={(e) => setTagsDraft(e.target.value)} />
                    <small className={`char-count${tagsOver ? ' is-over' : ''}`}>{tagList(tagsDraft).join(',').length} / {TAGS_MAX}</small>
                  </label>
                  <div className="tracker-script-slot-actions">
                    <button type="button" className="btn btn-primary btn-sm" disabled={saveDisabled} onClick={saveMetaEdit}>
                      {savingDescription ? 'Saving…' : 'Save'}
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setEditingMeta(false)}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <h4>
                    {preview.yt_title}
                    <button type="button" className="tracker-icon-btn" onClick={startMetaEdit} aria-label="Edit metadata">
                      <i className="fa-solid fa-pencil" />
                    </button>
                  </h4>
                  <p>{preview.yt_description}</p>
                  {preview.yt_tags?.length ? (
                    <small>{preview.yt_tags.map((t) => String(t).replace(/#/g, '')).join(', ')}</small>
                  ) : null}
                </>
              )}
            </div>
          </div>
          {!editingMeta && (
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
          )}
        </>
      )}
    </section>
  )
}
