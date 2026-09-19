import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../../api'

function assetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return `${base}${path}`
}

export default function TrackerStaticGenerate({ card, weekContext, onChange }) {
  const { token, clientId, toast, year, month, week } = weekContext
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('script')
  const [sources, setSources] = useState({ scripted_items: [], recommended_keywords: [] })
  const [selectedScriptIds, setSelectedScriptIds] = useState([])
  const [selectedManualTopicIds, setSelectedManualTopicIds] = useState([])
  const [viewed, setViewed] = useState(null)
  const [loadingSources, setLoadingSources] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [customPrompt, setCustomPrompt] = useState('')
  const [posts, setPosts] = useState([])
  const [loadingPosts, setLoadingPosts] = useState(false)
  const [regeneratingId, setRegeneratingId] = useState(null)
  const [regeneratePrompt, setRegeneratePrompt] = useState('')
  const [editingCaptionId, setEditingCaptionId] = useState(null)
  const [captionDraft, setCaptionDraft] = useState('')
  const [deleteId, setDeleteId] = useState(null)
  const [showRefs, setShowRefs] = useState(false)
  const [instagramMedia, setInstagramMedia] = useState([])
  const [instagramCursor, setInstagramCursor] = useState(null)
  const [loadingMedia, setLoadingMedia] = useState(false)
  const [selectedRefIds, setSelectedRefIds] = useState([])
  const [publishFor, setPublishFor] = useState(null)
  const [scheduleFor, setScheduleFor] = useState(null)
  const [targets, setTargets] = useState(['instagram', 'facebook'])
  const fileRef = useRef(null)

  const selectedSources = useMemo(() => {
    if (mode === 'script') {
      return selectedScriptIds.map((id) => ({ source_type: 'script', content_plan_item_id: id }))
    }
    return selectedManualTopicIds.map((topic_id) => ({ source_type: 'manual_pick', topic_id }))
  }, [mode, selectedScriptIds, selectedManualTopicIds])

  async function loadSources() {
    setLoadingSources(true)
    try {
      const result = await api.getSocialPostSources(token, clientId)
      setSources(result || { scripted_items: [], recommended_keywords: [] })
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoadingSources(false)
    }
  }

  useEffect(() => {
    if (open && token && clientId) loadSources()
  }, [open, token, clientId])

  useEffect(() => {
    setViewed(null)
    setPosts([])
  }, [mode])

  async function loadViewedVersions(source) {
    if (!source || !token || !clientId) {
      setPosts([])
      return
    }
    setLoadingPosts(true)
    try {
      const result = await api.getSocialPostVersions(token, clientId, source)
      setPosts(result.posts || [])
    } catch (err) {
      toast(err.message, 'error')
      setPosts([])
    } finally {
      setLoadingPosts(false)
    }
  }

  useEffect(() => {
    loadViewedVersions(viewed)
  }, [viewed, token, clientId])

  async function fetchInstagramMedia(reset = false) {
    setLoadingMedia(true)
    try {
      const after = reset ? null : instagramCursor
      const result = await api.getInstagramMedia(token, clientId, 12, after)
      setInstagramMedia((prev) => (reset ? result.media : [...prev, ...result.media]))
      setInstagramCursor(result.next_cursor)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoadingMedia(false)
    }
  }

  function rememberIds(ids, extra = {}) {
    const merged = [...new Set([...(card.generated_post_ids || []), ...ids])]
    onChange({ ...card, ...extra, generated_post_ids: merged })
  }

  function sameSource(source, post) {
    if (!source || !post) return false
    if (source.source_type === 'script') return post.content_plan_item_id === source.content_plan_item_id
    return post.topic_id === source.topic_id
  }

  async function handleGenerate() {
    if (!selectedSources.length) {
      toast('Select at least one script or keyword.', 'error')
      return
    }
    setGenerating(true)
    try {
      const created = []
      for (const source of selectedSources) {
        const payload = { ...source }
        if (customPrompt.trim()) payload.custom_prompt = customPrompt.trim()
        if (selectedRefIds.length) payload.reference_media_ids = selectedRefIds
        const result = await api.generateSocialPostDraft(token, clientId, payload)
        created.push(result.post)
      }
      rememberIds(created.map((p) => p.id))
      if (viewed && created.some((p) => sameSource(viewed, p))) {
        await loadViewedVersions(viewed)
      }
      toast('Post generated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setGenerating(false)
    }
  }

  async function handleRegenerate(post) {
    setGenerating(true)
    try {
      const fields = { source_type: post.source_type }
      if (post.topic_id) fields.topic_id = post.topic_id
      if (post.content_plan_item_id) fields.content_plan_item_id = post.content_plan_item_id
      if (regeneratePrompt.trim()) fields.custom_prompt = regeneratePrompt.trim()
      if (selectedRefIds.length) fields.reference_media_ids = selectedRefIds
      const result = await api.generateSocialPostDraft(token, clientId, fields)
      rememberIds([result.post.id])
      await loadViewedVersions(viewed)
      setRegeneratingId(null)
      setRegeneratePrompt('')
      toast('Regenerated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setGenerating(false)
    }
  }

  function revertPost(previous) {
    setPosts((prev) => prev.map((p) => (p.id === previous.id ? previous : p)))
  }

  async function handleSaveCaption(post) {
    try {
      const result = await api.editSocialPostQueueCaption(token, clientId, post.id, captionDraft)
      setPosts((prev) => prev.map((p) => (p.id === post.id ? result.post : p)))
      setEditingCaptionId(null)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  function handleDelete(postId) {
    const previous = posts
    const previousIds = card.generated_post_ids || []
    setDeleteId(null)
    setPosts((prev) => prev.filter((p) => p.id !== postId))
    onChange({
      ...card,
      generated_post_ids: previousIds.filter((id) => id !== postId),
    })
    api.deleteSocialPost(token, clientId, postId).catch((err) => {
      setPosts(previous)
      onChange({ ...card, generated_post_ids: previousIds })
      toast(err.message, 'error')
    })
  }

  function applyPermalinks(post, published, nextTargets) {
    const destinations = [...(card.destinations || [])]
    const destinationPostIds = { ...(card.destination_post_ids || {}) }
    if (nextTargets.includes('instagram') && published.instagram_permalink) {
      const idx = destinations.findIndex((d) => d.platform === 'instagram')
      if (idx >= 0) destinations[idx] = { ...destinations[idx], url: published.instagram_permalink }
      else destinations.push({ id: `dest-ig-${post.id}`, platform: 'instagram', url: published.instagram_permalink })
      destinationPostIds.instagram = post.id
    }
    if (nextTargets.includes('facebook') && published.facebook_permalink) {
      const idx = destinations.findIndex((d) => d.platform === 'facebook')
      if (idx >= 0) destinations[idx] = { ...destinations[idx], url: published.facebook_permalink }
      else destinations.push({ id: `dest-fb-${post.id}`, platform: 'facebook', url: published.facebook_permalink })
      destinationPostIds.facebook = post.id
    }
    return {
      destinations,
      destination_post_ids: destinationPostIds,
      stage: 'posted',
    }
  }

  function handlePublish(post) {
    if (!targets.length) {
      toast('Select Instagram or Facebook.', 'error')
      return
    }
    const previous = post
    const nextTargets = [...targets]
    setPosts((prev) => prev.map((p) => (p.id === post.id ? { ...p, publish_status: 'published' } : p)))
    setPublishFor(null)
    toast('Published.', 'success')
    api.publishSocialPost(
      token,
      clientId,
      post.id,
      post.brief?.caption || '',
      nextTargets,
      { year, month, week },
    ).then(async (published) => {
      if (weekContext.reloadWeek) {
        await weekContext.reloadWeek()
      } else {
        rememberIds([post.id], applyPermalinks(post, published, nextTargets))
      }
    }).catch((err) => {
      revertPost(previous)
      toast(err.message, 'error')
    })
  }

  function handleSchedule(post) {
    if (!targets.length) {
      toast('Select Instagram or Facebook.', 'error')
      return
    }
    const previous = post
    const nextTargets = [...targets]
    setPosts((prev) => prev.map((p) => (p.id === post.id ? { ...p, publish_status: 'scheduled', publish_targets: nextTargets } : p)))
    setScheduleFor(null)
    toast('Scheduled.', 'success')
    api.addSocialPostToQueue(token, clientId, post.id, nextTargets).catch((err) => {
      revertPost(previous)
      toast(err.message, 'error')
    })
  }

  function handleUnscheduleFrom(post, platform) {
    const current = post.publish_targets || []
    const nextTargets = current.filter((t) => t !== platform)
    const previous = post
    if (nextTargets.length === 0) {
      setPosts((prev) => prev.map((p) => (
        p.id === post.id ? { ...p, publish_status: 'draft', publish_targets: [] } : p
      )))
      setScheduleFor(null)
      toast('Removed from schedule.', 'success')
      api.removeSocialPostFromQueue(token, clientId, post.id).catch((err) => {
        revertPost(previous)
        toast(err.message, 'error')
      })
      return
    }
    setPosts((prev) => prev.map((p) => (
      p.id === post.id ? { ...p, publish_status: 'scheduled', publish_targets: nextTargets } : p
    )))
    toast(`Unscheduled from ${platform}.`, 'success')
    api.updateSocialPostTargets(token, clientId, post.id, nextTargets).catch((err) => {
      revertPost(previous)
      toast(err.message, 'error')
    })
  }

  function toggleTarget(platform) {
    setTargets((prev) => (prev.includes(platform) ? prev.filter((t) => t !== platform) : [...prev, platform]))
  }

  async function handleLocalUpload(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      await api.uploadInstagramMedia(token, clientId, file)
      toast('Reference uploaded. Pick it from Instagram media after sync, or generate with auto refs.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  function isViewed(source) {
    if (!viewed) return false
    if (source.source_type === 'script') return viewed.content_plan_item_id === source.content_plan_item_id
    return viewed.topic_id === source.topic_id
  }

  function toggleScript(id) {
    setSelectedScriptIds((prev) => (prev.includes(id) ? prev.filter((itemId) => itemId !== id) : [...prev, id]))
  }

  function toggleManual(topicId) {
    setSelectedManualTopicIds((prev) => (
      prev.includes(topicId) ? prev.filter((id) => id !== topicId) : [...prev, topicId]
    ))
  }

  return (
    <section className="tracker-section">
      <button type="button" className="tracker-generate-toggle" onClick={() => setOpen((v) => !v)}>
        <i className={`fa-solid ${open ? 'fa-chevron-down' : 'fa-chevron-right'}`} />
        Generate in this card
      </button>
      {open && (
        <div className="tracker-generate">
          <div className="segmented-control">
            <button type="button" className={mode === 'script' ? 'active' : ''} onClick={() => setMode('script')}>From Script</button>
            <button type="button" className={mode === 'manual_pick' ? 'active' : ''} onClick={() => setMode('manual_pick')}>Manual keyword</button>
          </div>
          {loadingSources ? <p className="text-muted">Loading sources…</p> : null}
          {mode === 'script' && (
            <div className="choice-list tracker-choice-list">
              {(sources.scripted_items || []).map((item) => {
                const source = { source_type: 'script', content_plan_item_id: item.id }
                const checked = selectedScriptIds.includes(item.id)
                return (
                  <div
                    key={item.id}
                    className={`choice-row tracker-source-row${isViewed(source) ? ' selected' : ''}${checked ? ' is-checked' : ''}`}
                    onClick={() => toggleScript(item.id)}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        e.stopPropagation()
                        toggleScript(item.id)
                      }}
                    />
                    <span style={{ flex: 1 }}>{item.topic_text}</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        setViewed(isViewed(source) ? null : source)
                      }}
                    >
                      View
                    </button>
                  </div>
                )
              })}
              {!sources.scripted_items?.length ? <p className="text-muted">No scripts in the current content plan.</p> : null}
            </div>
          )}
          {mode === 'manual_pick' && (
            <div className="choice-list tracker-choice-list">
              {(sources.recommended_keywords || []).map((topic) => {
                const source = { source_type: 'manual_pick', topic_id: topic.topic_id }
                const checked = selectedManualTopicIds.includes(topic.topic_id)
                return (
                  <div
                    key={topic.topic_id}
                    className={`choice-row tracker-source-row${isViewed(source) ? ' selected' : ''}${checked ? ' is-checked' : ''}`}
                    onClick={() => toggleManual(topic.topic_id)}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        e.stopPropagation()
                        toggleManual(topic.topic_id)
                      }}
                    />
                    <span style={{ flex: 1 }}>{topic.topic_text}</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        setViewed(isViewed(source) ? null : source)
                      }}
                    >
                      View
                    </button>
                  </div>
                )
              })}
              {!sources.recommended_keywords?.length ? <p className="text-muted">No keywords with score 50+.</p> : null}
            </div>
          )}

          <textarea
            className="form-control"
            rows={2}
            placeholder="Optional custom instructions"
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
          />
          <div className="tracker-note-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setShowRefs((v) => !v)
                if (!showRefs && instagramMedia.length === 0) fetchInstagramMedia(true)
              }}
            >
              Choose reference images ({selectedRefIds.length})
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => fileRef.current?.click()}>
              Upload local
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleLocalUpload} />
            <button type="button" className="btn btn-primary btn-sm" onClick={handleGenerate} disabled={generating}>
              {generating ? 'Generating…' : 'Generate'}
            </button>
          </div>

          {showRefs && (
            <div className="tracker-ref-grid-wrap">
              <div className="tracker-ref-grid">
                {instagramMedia.filter((m) => m.media_type === 'IMAGE' || m.media_type === 'CAROUSEL_ALBUM').map((media) => {
                  const selected = selectedRefIds.includes(media.id)
                  return (
                    <button
                      type="button"
                      key={media.id}
                      className={`tracker-ref-tile${selected ? ' selected' : ''}`}
                      onClick={() => setSelectedRefIds(selected ? selectedRefIds.filter((id) => id !== media.id) : [...selectedRefIds, media.id])}
                    >
                      <img src={media.thumbnail_url || media.media_url} alt="" />
                    </button>
                  )
                })}
              </div>
              {instagramCursor && (
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => fetchInstagramMedia(false)} disabled={loadingMedia}>
                  {loadingMedia ? 'Loading…' : 'Load more'}
                </button>
              )}
            </div>
          )}

          {viewed && (
            <div className="tracker-generated-list">
              {loadingPosts ? <p className="text-muted">Loading drafts…</p> : null}
              {!loadingPosts && posts.length === 0 ? <p className="text-muted">No generated drafts for this keyword yet.</p> : null}
              {posts.map((post) => (
                <article key={post.id} className="tracker-generated-card">
                  {post.image_url ? <img src={assetUrl(post.image_url)} alt="" /> : <div className="draft-image-placeholder">No image</div>}
                  <p className="tracker-generated-caption">{post.brief?.caption || 'No caption'}</p>
                  {regeneratingId === post.id && (
                    <div className="tracker-inline-panel">
                      <textarea className="form-control" rows={2} value={regeneratePrompt} onChange={(e) => setRegeneratePrompt(e.target.value)} placeholder="Custom instructions" />
                      <div className="tracker-note-actions">
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => handleRegenerate(post)} disabled={generating}>Confirm</button>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setRegeneratingId(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                  {editingCaptionId === post.id && (
                    <div className="tracker-inline-panel">
                      <textarea className="form-control" rows={3} value={captionDraft} onChange={(e) => setCaptionDraft(e.target.value)} />
                      <div className="tracker-note-actions">
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => handleSaveCaption(post)}>Save caption</button>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditingCaptionId(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                  {deleteId === post.id && (
                    <div className="tracker-inline-panel">
                      <p>Delete this generated version?</p>
                      <div className="tracker-note-actions">
                        <button type="button" className="btn btn-success btn-sm" onClick={() => handleDelete(post.id)}>Delete</button>
                        <button type="button" className="btn btn-danger-confirm btn-sm" onClick={() => setDeleteId(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                  {(publishFor === post.id || (scheduleFor === post.id && post.publish_status !== 'scheduled')) && (
                    <div className="tracker-inline-panel">
                      <p>{publishFor === post.id ? 'Post now to' : 'Schedule on'}</p>
                      <div className="tracker-unschedule-picks">
                        <button
                          type="button"
                          className={`btn btn-secondary btn-sm${targets.includes('instagram') ? ' is-selected' : ''}`}
                          onClick={() => toggleTarget('instagram')}
                        >
                          <i className="fa-brands fa-instagram" /> Instagram
                        </button>
                        <button
                          type="button"
                          className={`btn btn-secondary btn-sm${targets.includes('facebook') ? ' is-selected' : ''}`}
                          onClick={() => toggleTarget('facebook')}
                        >
                          <i className="fa-brands fa-facebook" /> Facebook
                        </button>
                      </div>
                      <div className="tracker-note-actions">
                        {publishFor === post.id ? (
                          <button type="button" className="btn btn-primary btn-sm" onClick={() => handlePublish(post)}>Publish now</button>
                        ) : (
                          <button type="button" className="btn btn-primary btn-sm" onClick={() => handleSchedule(post)}>Schedule</button>
                        )}
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setPublishFor(null); setScheduleFor(null) }}>Cancel</button>
                      </div>
                    </div>
                  )}
                  {scheduleFor === post.id && post.publish_status === 'scheduled' && (
                    <div className="tracker-inline-panel">
                      <p>Unschedule from</p>
                      <div className="tracker-unschedule-picks">
                        {((post.publish_targets || []).length ? post.publish_targets : ['instagram', 'facebook']).includes('instagram') && (
                          <button type="button" className="btn btn-secondary btn-sm is-selected" onClick={() => handleUnscheduleFrom(post, 'instagram')}>
                            <i className="fa-brands fa-instagram" /> Instagram
                          </button>
                        )}
                        {((post.publish_targets || []).length ? post.publish_targets : ['instagram', 'facebook']).includes('facebook') && (
                          <button type="button" className="btn btn-secondary btn-sm is-selected" onClick={() => handleUnscheduleFrom(post, 'facebook')}>
                            <i className="fa-brands fa-facebook" /> Facebook
                          </button>
                        )}
                      </div>
                      <div className="tracker-note-actions">
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setScheduleFor(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                  <div className="tracker-generated-actions">
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setRegeneratingId(post.id); setRegeneratePrompt('') }}>Regenerate</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setEditingCaptionId(post.id); setCaptionDraft(post.brief?.caption || '') }}>Edit caption</button>
                    {post.publish_status === 'scheduled' ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setScheduleFor(post.id)
                          setPublishFor(null)
                          setTargets(post.publish_targets || ['instagram', 'facebook'])
                        }}
                      >
                        Unschedule
                      </button>
                    ) : post.publish_status !== 'published' ? (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setScheduleFor(post.id); setPublishFor(null); setTargets(['instagram', 'facebook']) }}>Schedule</button>
                    ) : null}
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => { setPublishFor(post.id); setScheduleFor(null); setTargets(['instagram', 'facebook']) }}>Post now</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDeleteId(post.id)}>Delete</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
