import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import api, { apiFetch } from '../api'
import VideoUrlAttachField from '../components/VideoUrlAttachField'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import { formatRecommendationScore } from '../utils/scoreFormat'

function itemLocales(item) {
  const locales = { ...(item?.yt_locales || {}) }
  if (!locales.hinglish && item?.yt_title) {
    locales.hinglish = {
      yt_title: item.yt_title,
      yt_description: item.yt_description,
      yt_tags: item.yt_tags,
      yt_thumbnail_url: item.yt_thumbnail_url,
    }
  }
  return locales
}

function mapPlanItem(i) {
  return {
    id: i.id,
    topic_id: i.topic_id,
    topic: i.topic_text || i.working_title || i.title_en || 'Scripted Topic',
    yt_title: i.yt_title,
    yt_description: i.yt_description,
    yt_tags: i.yt_tags,
    yt_thumbnail_url: i.yt_thumbnail_url,
    yt_locales: i.yt_locales || {},
    recommendation_score: i.recommendation_score || 0,
  }
}

export default function ClientPostVideo() {
  const { clientId, channels = [], activeChannelId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()
  const [searchParams] = useSearchParams()
  const focusItemId = searchParams.get('item')
  const appliedFocusRef = useRef(null)

  const [contentPlan, setContentPlan] = useState(null)
  const [loadingPlan, setLoadingPlan] = useState(false)

  const [mode, setMode] = useState('script')
  const [selectedScriptItemIds, setSelectedScriptItemIds] = useState([])
  const [selectedManualItemIds, setSelectedManualItemIds] = useState([])
  const [activeItemId, setActiveItemId] = useState(null)
  const [pageError, setPageError] = useState('')

  const [videoUrlsByChannel, setVideoUrlsByChannel] = useState({})
  const [socialVideoLink, setSocialVideoLink] = useState('')
  const [postToYT, setPostToYT] = useState(true)
  const [postToIG, setPostToIG] = useState(false)
  const [postToFB, setPostToFB] = useState(false)

  const [selectedChannelIds, setSelectedChannelIds] = useState(
    activeChannelId ? [activeChannelId] : (channels[0] ? [channels[0].id] : []),
  )

  const [showRefModal, setShowRefModal] = useState(false)
  const [channelVideos, setChannelVideos] = useState([])
  const [selectedRefVideoIds, setSelectedRefVideoIds] = useState([])
  const [modalChannelId, setModalChannelId] = useState(activeChannelId || channels[0]?.id)

  const [metadataBusy, setMetadataBusy] = useState(false)
  const [refinePrompt, setRefinePrompt] = useState('')
  const [postingBusy, setPostingBusy] = useState(false)

  const loadPlan = useCallback(async () => {
    if (!token || !clientId) return
    setLoadingPlan(true)
    try {
      const data = await api.getContentPlan(token, clientId)
      setContentPlan(data.suggestions || { items: [] })
    } catch (err) {
      toast(`Failed to load content plan: ${err.message}`, 'error')
    } finally {
      setLoadingPlan(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    loadPlan()
  }, [loadPlan])

  useEffect(() => {
    if (!channels.length) return
    setSelectedChannelIds((prev) => {
      const stillLinked = prev.filter((id) => channels.some((c) => c.id === id))
      if (stillLinked.length) return stillLinked
      return activeChannelId && channels.some((c) => c.id === activeChannelId)
        ? [activeChannelId]
        : [channels[0].id]
    })
    setModalChannelId((prev) =>
      channels.some((c) => c.id === prev) ? prev : (activeChannelId || channels[0].id),
    )
  }, [channels, activeChannelId])

  const allItems = contentPlan?.items || []
  const scriptItems = useMemo(
    () => allItems.filter((i) => !!i.script).map(mapPlanItem),
    [allItems],
  )

  useEffect(() => {
    if (!focusItemId || appliedFocusRef.current === focusItemId) return
    if (!scriptItems.some((item) => item.id === focusItemId)) return
    appliedFocusRef.current = focusItemId
    setMode('script')
    setActiveItemId(focusItemId)
    setSelectedScriptItemIds([focusItemId])
  }, [focusItemId, scriptItems])

  const manualItems = useMemo(
    () =>
      (contentPlan?.keyword_analysis || [])
        .filter((k) => k.recommendation_score >= 50)
        .sort((a, b) => b.recommendation_score - a.recommendation_score)
        .map((k) => ({
          id: k.topic_id,
          topic_id: k.topic_id,
          topic: k.topic_text,
          recommendation_score: k.recommendation_score,
          yt_title: k.yt_title,
          yt_description: k.yt_description,
          yt_tags: k.yt_tags,
          yt_thumbnail_url: k.yt_thumbnail_url,
          yt_locales: k.yt_locales || {},
        })),
    [contentPlan],
  )

  const allPossibleItems = [...scriptItems, ...manualItems]
  const activeItem = useMemo(
    () => allPossibleItems.find((i) => i.id === activeItemId),
    [allPossibleItems, activeItemId],
  )

  const currentSelectedIds = mode === 'script' ? selectedScriptItemIds : selectedManualItemIds

  const activeLocales = useMemo(() => itemLocales(activeItem), [activeItem])
  const previewMeta = activeLocales.hinglish || Object.values(activeLocales).find((loc) => loc?.yt_title) || {}

  const loadChannelVideos = useCallback(async () => {
    if (!token || !clientId || !modalChannelId) return
    try {
      const data = await api.listVideos(token, clientId, modalChannelId)
      setChannelVideos(data.videos || [])
    } catch (err) {
      toast(`Failed to load channel videos: ${err.message}`, 'error')
    }
  }, [token, clientId, modalChannelId, toast])

  useEffect(() => {
    if (showRefModal && channelVideos.length === 0) {
      loadChannelVideos()
    }
  }, [showRefModal, modalChannelId, loadChannelVideos, channelVideos.length])

  const handleToggleItem = (id) => {
    if (mode === 'script') {
      setSelectedScriptItemIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
    } else {
      setSelectedManualItemIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
    }
    setActiveItemId(id)
  }

  const openGenerateModal = () => {
    setPageError('')
    if (currentSelectedIds.length === 0) {
      setPageError('Please select at least one keyword.')
      return
    }
    handleGenerateMetadata()
  }

  const handleGenerateMetadata = async (e) => {
    e?.preventDefault?.()
    e?.stopPropagation?.()
    setPageError('')
    const itemIds = [...currentSelectedIds]
    if (itemIds.length === 0) {
      setPageError('Please select at least one keyword.')
      return
    }
    setMetadataBusy(true)
    toast('Generating metadata…', 'info')
    try {
      await api.generateYouTubeMetadata(token, clientId, {
        itemIds,
        referenceVideoIds: selectedRefVideoIds,
        languages: ['hinglish'],
      })
      toast(`Metadata generated for ${itemIds.length} item(s)!`, 'success')
    } catch (err) {
      setPageError(`Failed to generate metadata: ${err.message}`)
    }
    try {
      await loadPlan()
    } catch {
      // Preview may still update from a partial generate.
    } finally {
      setMetadataBusy(false)
    }
  }

  const handleRefineMetadata = async () => {
    setPageError('')
    if (!activeItemId) return
    if (!refinePrompt.trim()) {
      setPageError('Please enter some instructions to refine the metadata or thumbnail.')
      return
    }
    setMetadataBusy(true)
    try {
      await api.refineYouTubeMetadata(token, clientId, {
        itemId: activeItemId,
        userPrompt: refinePrompt,
        referenceVideoIds: selectedRefVideoIds,
        language: 'hinglish',
      })
      toast('Metadata refined successfully!', 'success')
      setRefinePrompt('')
    } catch (err) {
      setPageError(`Failed to refine metadata: ${err.message}`)
    }
    try {
      await loadPlan()
    } catch {
      // Keep current preview if reload fails.
    } finally {
      setMetadataBusy(false)
    }
  }

  const selectedYtChannels = useMemo(
    () => (channels || []).filter((c) => selectedChannelIds.includes(c.id)),
    [channels, selectedChannelIds],
  )

  const firstSelectedUrl = useMemo(() => {
    const first = selectedYtChannels[0]
    return (first && videoUrlsByChannel[first.id]) || ''
  }, [selectedYtChannels, videoUrlsByChannel])

  const handlePostVideo = async () => {
    setPageError('')
    if (!activeItem) {
      setPageError('Please select a keyword to preview.')
      return
    }
    if (!postToYT && !postToIG && !postToFB) {
      setPageError('Please select at least one platform to post to.')
      return
    }
    if (postToYT && selectedChannelIds.length === 0) {
      setPageError('You must select at least one YouTube channel to post to YouTube.')
      return
    }

    const locales = itemLocales(activeItem)
    const meta = locales.hinglish || Object.values(locales).find((loc) => loc?.yt_title) || {}
    if (postToYT && !meta.yt_title) {
      setPageError('Generate YouTube metadata first.')
      return
    }
    if (postToYT) {
      for (const ch of selectedYtChannels) {
        if (!(videoUrlsByChannel[ch.id] || '').trim()) {
          setPageError(`Add a video URL for "${ch.title || ch.id}".`)
          return
        }
      }
    }

    const socialUrl = (socialVideoLink || firstSelectedUrl || Object.values(videoUrlsByChannel).find(Boolean) || '').trim()
    if ((postToIG || postToFB) && !postToYT && !socialUrl) {
      setPageError('Please provide a social video URL.')
      return
    }

    setPostingBusy(true)
    try {
      if (postToYT) {
        const socialChannelId = selectedYtChannels[0]?.id
        for (const ch of selectedYtChannels) {
          const cleanTags = (meta.yt_tags || []).map((t) => t.replace(/#/g, ''))
          const attachSocial = (postToIG || postToFB) && ch.id === socialChannelId
          await apiFetch('/video.upload', {
            token,
            body: {
              client_id: clientId,
              channel_id: ch.id,
              drive_link: (videoUrlsByChannel[ch.id] || '').trim(),
              title: meta.yt_title || activeItem.topic,
              description: meta.yt_description || '',
              tags: cleanTags,
              thumbnail_url: meta.yt_thumbnail_url,
              post_to_instagram: attachSocial && postToIG,
              post_to_facebook: attachSocial && postToFB,
              topic_id: activeItem.topic_id || activeItem.id,
              language: 'hinglish',
              social_source_url: attachSocial ? (socialVideoLink || firstSelectedUrl || '').trim() || undefined : undefined,
            },
          })
        }
      } else {
        const cleanTags = (meta.yt_tags || []).map((t) => t.replace(/#/g, ''))
        await apiFetch('/video.upload', {
          token,
          body: {
            client_id: clientId,
            channel_id: channels[0]?.id || '',
            drive_link: socialUrl,
            title: meta.yt_title || activeItem.topic,
            description: meta.yt_description || '',
            tags: cleanTags,
            thumbnail_url: meta.yt_thumbnail_url,
            post_to_instagram: postToIG,
            post_to_facebook: postToFB,
            topic_id: activeItem.topic_id || activeItem.id,
            language: 'hinglish',
            social_source_url: socialUrl || undefined,
          },
        })
      }

      toast('Video posted successfully!', 'success')
      setVideoUrlsByChannel({})
      setSocialVideoLink('')
    } catch (err) {
      setPageError(`Failed to post video: ${err.message}`)
    } finally {
      setPostingBusy(false)
    }
  }

  const renderKeywordRow = (item) => {
    const isSelected = currentSelectedIds.includes(item.id)
    const isActive = activeItemId === item.id
    return (
      <div
        key={item.id}
        className={`choice-row${isActive ? ' selected' : ''}`}
        onClick={() => setActiveItemId(item.id)}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => {
            e.stopPropagation()
            handleToggleItem(item.id)
          }}
          onClick={(e) => e.stopPropagation()}
        />
        <span style={{ flex: 1, paddingLeft: '12px' }}>
          <strong style={{ fontSize: '1rem' }}>{item.topic}</strong>
          <small style={{ display: 'block', color: 'var(--text-muted)' }}>
            {item.yt_title || itemLocales(item).hinglish?.yt_title || 'No metadata generated yet'}
          </small>
        </span>
        {item.recommendation_score ? <em>{formatRecommendationScore(item.recommendation_score)}</em> : null}
      </div>
    )
  }

  return (
    <>
      <header className="content-header" style={{ marginBottom: '20px', justifyContent: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <h1 style={{ textAlign: 'center', margin: 0 }}>Post Video</h1>
          <p className="text-muted" style={{ textAlign: 'center', maxWidth: '100%', marginTop: '10px' }}>
            Select a topic, generate YouTube metadata, then publish each selected channel with its own video URL.
          </p>
        </div>
      </header>

      {pageError && (
        <div style={{ position: 'fixed', bottom: '30px', left: '50%', transform: 'translateX(-50%)', background: '#f8d7da', color: '#842029', padding: '16px 24px', borderRadius: '12px', fontWeight: '500', display: 'flex', alignItems: 'center', gap: '12px', zIndex: 9999, boxShadow: '0 8px 32px rgba(220, 53, 69, 0.25)', border: '1px solid #f5c2c7' }}>
          <i className="fa-solid fa-circle-exclamation" style={{ fontSize: '1.2em' }} /> {pageError}
          <button onClick={() => setPageError('')} style={{ background: 'none', border: 'none', marginLeft: '12px', cursor: 'pointer', color: '#842029', padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="fa-solid fa-xmark" style={{ fontSize: '1.2em' }} />
          </button>
        </div>
      )}

      {loadingPlan ? (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading content plan…</span>
          </div>
        </div>
      ) : (
        <div className="social-generate-grid">
          <section className="card profile-form social-card">
            <div className="profile-section">
              <h2 style={{ textAlign: 'center' }}>Content Source</h2>
              <div className="segmented-control" style={{ marginTop: '15px' }}>
                <button type="button" className={mode === 'script' ? 'active' : ''} onClick={() => setMode('script')}>
                  From Script
                </button>
                <button type="button" className={mode === 'manual' ? 'active' : ''} onClick={() => setMode('manual')}>
                  Manual Pick
                </button>
              </div>
            </div>

            <div className="profile-section" style={{ marginTop: '20px' }}>
              <h2>{mode === 'script' ? 'Scripted Keywords' : 'Manual Pick'}</h2>
              <p className="profile-section-desc">
                {mode === 'script'
                  ? 'Using scripts from the latest plan.'
                  : 'Manually select recommendation keywords with score 50 or higher.'}
              </p>

              {mode === 'manual' ? (
                <details className="keyword-dropdown-card" open style={{ background: 'var(--bg-light)', borderRadius: '12px', border: '1px solid var(--border)' }}>
                  <summary style={{ padding: '15px', fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', cursor: 'pointer', borderBottom: '1px solid var(--border)' }}>
                    <span>All Recommended Keywords</span>
                    <strong>{manualItems.length}</strong>
                  </summary>
                  <div className="choice-list" style={{ maxHeight: '600px', overflowY: 'auto', padding: '10px' }}>
                    {manualItems.length === 0 && <p className="text-muted" style={{ padding: '10px' }}>No keywords found.</p>}
                    {manualItems.map(renderKeywordRow)}
                  </div>
                </details>
              ) : (
                <div className="choice-list" style={{ maxHeight: '600px', overflowY: 'auto' }}>
                  {scriptItems.length === 0 && <p className="text-muted">No keywords found.</p>}
                  {scriptItems.map(renderKeywordRow)}
                </div>
              )}

              <div style={{ marginTop: '20px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
                <button
                  className="btn btn-secondary btn-block"
                  onClick={() => setShowRefModal(true)}
                  style={{ marginBottom: '15px', padding: '14px', fontSize: '1.05em', fontWeight: '500', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}
                >
                  <i className="fa-solid fa-images" /> Choose Reference Thumbnails ({selectedRefVideoIds.length})
                </button>
                <button
                  className="btn btn-primary btn-block"
                  style={{ padding: '14px', fontSize: '1.05em', fontWeight: '500', borderRadius: '12px' }}
                  onClick={openGenerateModal}
                  disabled={metadataBusy || currentSelectedIds.length === 0}
                >
                  {`Generate Metadata (${currentSelectedIds.length})`}
                </button>
              </div>
            </div>
          </section>

          <section className="card profile-form social-card">
            {!activeItem ? (
              <div style={{ padding: '80px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <i className="fa-solid fa-arrow-pointer" style={{ fontSize: '4em', marginBottom: '20px', opacity: 0.3 }} />
                <h3 style={{ fontSize: '1.5em' }}>Select a keyword to preview</h3>
                <p style={{ fontSize: '1.1em' }}>Click on any keyword card on the left to edit its metadata and post the video.</p>
              </div>
            ) : (
              <div className="profile-section">
                <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>
                  Ready to post: <span style={{ color: 'var(--primary)' }}>{activeItem.topic}</span>
                </h2>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {previewMeta.yt_title ? (
                    <div className="tracker-yt-preview metadata-preview">
                      <div className="tracker-yt-preview-thumb">
                        {previewMeta.yt_thumbnail_url ? (
                          <img src={previewMeta.yt_thumbnail_url} alt="Thumbnail" />
                        ) : (
                          <div className="tracker-yt-thumb-empty">
                            <i className="fa-regular fa-image" />
                            <span>No thumbnail</span>
                          </div>
                        )}
                      </div>
                      <div className="tracker-yt-preview-copy">
                        <h4>{previewMeta.yt_title}</h4>
                        <p>{previewMeta.yt_description}</p>
                        {previewMeta.yt_tags?.length > 0 ? (
                          <small>
                            {previewMeta.yt_tags.map((t) => t.replace(/#/g, '')).join(', ')}
                          </small>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <div style={{ padding: '40px', background: 'var(--bg-light)', borderRadius: '16px', color: 'var(--text-muted)', textAlign: 'center', border: '1px dashed var(--border)' }}>
                      <i className="fa-solid fa-align-left" style={{ fontSize: '2em', opacity: 0.5, marginBottom: '10px' }} />
                      <p>Generate metadata first to preview title and description.</p>
                    </div>
                  )}

                  {activeLangKeys.length > 0 && (
                    <>
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="E.g., Make the title more clickbaity..."
                          value={refinePrompt}
                          onChange={(e) => setRefinePrompt(e.target.value)}
                          style={{ flex: 1, borderRadius: '12px', padding: '14px 20px', fontSize: '1.05em', border: '1px solid var(--border-dark, #000)' }}
                        />
                        <button
                          className="btn btn-primary"
                          onClick={handleRefineMetadata}
                          disabled={metadataBusy || !previewMeta.yt_title}
                          style={{ borderRadius: '12px', padding: '0 24px', fontSize: '1.05em', fontWeight: '500' }}
                        >
                          {metadataBusy ? <i className="fa-solid fa-spinner fa-spin" /> : 'Refine'}
                        </button>
                      </div>

                      <div style={{ marginTop: '20px', paddingTop: '30px', borderTop: '1px solid var(--border)' }}>
                  <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>Post Video</h2>

                  <div style={{ marginTop: '8px', marginBottom: '25px' }}>
                    <p style={{ textAlign: 'center', fontWeight: '600', marginBottom: '12px', fontSize: '1.05em', color: 'var(--text-main)' }}>
                      Where do you want to post?
                    </p>
                    <div style={{ display: 'flex', gap: '15px', justifyContent: 'center', alignItems: 'center', flexWrap: 'nowrap' }}>
                      <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px 18px', background: 'var(--bg-light)', border: '1px solid var(--border-dark, #000)', borderRadius: '12px' }}>
                        <input type="checkbox" checked={postToYT} onChange={(e) => setPostToYT(e.target.checked)} />
                        <i className="fa-brands fa-youtube" style={{ color: '#ff0000', fontSize: '1.8em' }} />
                      </label>
                      <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px 18px', background: 'var(--bg-light)', border: '1px solid var(--border-dark, #000)', borderRadius: '12px' }}>
                        <input type="checkbox" checked={postToIG} onChange={(e) => setPostToIG(e.target.checked)} />
                        <i className="fa-brands fa-instagram" style={{ color: '#E1306C', fontSize: '1.8em' }} />
                      </label>
                      <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px 18px', background: 'var(--bg-light)', border: '1px solid var(--border-dark, #000)', borderRadius: '12px' }}>
                        <input type="checkbox" checked={postToFB} onChange={(e) => setPostToFB(e.target.checked)} />
                        <i className="fa-brands fa-facebook" style={{ color: '#1877F2', fontSize: '1.8em' }} />
                      </label>
                    </div>
                  </div>

                  {postToYT && (
                    <details className="keyword-dropdown-card" style={{ background: 'var(--bg-light)', borderRadius: '12px', border: '1px solid var(--border)', marginBottom: '20px' }}>
                      <summary style={{ padding: '15px', fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', cursor: 'pointer', borderBottom: '1px solid var(--border)' }}>
                        <span>Select YouTube Channels ({selectedChannelIds.length})</span>
                      </summary>
                      <div className="choice-list" style={{ maxHeight: '200px', overflowY: 'auto', padding: '10px' }}>
                        {channels.map((c) => {
                          const isSel = selectedChannelIds.includes(c.id)
                          return (
                            <div
                              key={c.id}
                              className={`choice-row${isSel ? ' selected' : ''}`}
                              onClick={() =>
                                setSelectedChannelIds((prev) =>
                                  prev.includes(c.id) ? prev.filter((id) => id !== c.id) : [...prev, c.id],
                                )
                              }
                              style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                            >
                              <input type="checkbox" checked={isSel} onChange={() => {}} />
                              <span style={{ marginLeft: '12px', fontWeight: '500' }}>
                                {c.title || c.id}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    </details>
                  )}

                  {postToYT && selectedYtChannels.length > 0 && (
                    <div className="form-group" style={{ marginBottom: '20px' }}>
                      <label style={{ display: 'block', fontWeight: '600', marginBottom: '10px', fontSize: '1.05em' }}>
                        Video URL for each channel
                      </label>
                      <p className="text-muted" style={{ marginTop: 0, marginBottom: '12px', fontSize: '0.9em' }}>
                        Each selected channel gets its own video URL. The same metadata is used for every channel.
                      </p>
                      {selectedYtChannels.map((ch) => (
                        <div key={ch.id} className="channel-video-row">
                          <div className="channel-video-row-header">
                            <span className="channel-name" title={ch.title || ch.id}>
                              {ch.title || ch.id}
                            </span>
                          </div>
                          <VideoUrlAttachField
                            token={token}
                            clientId={clientId}
                            toast={toast}
                            value={videoUrlsByChannel[ch.id] || ''}
                            onChange={(url) =>
                              setVideoUrlsByChannel((prev) => ({ ...prev, [ch.id]: url }))
                            }
                            inputStyle={{ padding: '12px 16px', fontSize: '1em', borderRadius: '12px', border: '1px solid var(--border-dark, #000)' }}
                          />
                        </div>
                      ))}
                    </div>
                  )}

                  {(postToIG || postToFB) && (
                    <div className="form-group" style={{ marginBottom: '20px' }}>
                      <label style={{ display: 'block', fontWeight: '600', marginBottom: '10px', fontSize: '1.05em' }}>
                        Social video URL
                      </label>
                      <VideoUrlAttachField
                        token={token}
                        clientId={clientId}
                        toast={toast}
                        placeholder={firstSelectedUrl ? 'Optional — uses the first channel URL if blank' : 'https://drive.google.com/...'}
                        value={socialVideoLink}
                        onChange={setSocialVideoLink}
                        inputStyle={{ width: '100%', padding: '14px 20px', fontSize: '1.05em', borderRadius: '12px', border: '1px solid var(--border-dark, #000)' }}
                      />
                    </div>
                  )}

                  <button
                    className="btn btn-primary btn-block"
                    style={{ padding: '14px', fontSize: '1.05em', fontWeight: '500', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}
                    onClick={handlePostVideo}
                    disabled={postingBusy}
                  >
                    {postingBusy ? (
                      <>
                        <i className="fa-solid fa-spinner fa-spin" /> Uploading and Posting...
                      </>
                    ) : (
                      <>
                        <i className="fa-solid fa-paper-plane" /> Publish Video
                      </>
                    )}
                  </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {showRefModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowRefModal(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            className="modal-content"
            style={{
              maxWidth: '800px',
              width: '90%',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--bg-card, #222)',
              color: '#fff',
              borderRadius: '12px',
              overflow: 'hidden',
              boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>Select Reference Thumbnails</h3>
              <button className="btn-close" onClick={() => setShowRefModal(false)} style={{ background: 'none', border: 'none', fontSize: '1.5em', cursor: 'pointer', color: '#fff' }}>
                <i className="fa-solid fa-xmark" />
              </button>
            </div>
            <div className="modal-body" style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
              <div className="form-group">
                <label style={{ color: '#fff', display: 'block', marginBottom: '8px' }}>YouTube Channel</label>
                <select
                  className="form-control"
                  value={modalChannelId}
                  onChange={(e) => {
                    setModalChannelId(e.target.value)
                    setChannelVideos([])
                  }}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.1)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
                >
                  {channels.map((c) => (
                    <option key={c.id} value={c.id} style={{ color: '#000' }}>
                      {c.title || c.id}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '20px', marginTop: '20px' }}>
                {channelVideos.length === 0 ? <p style={{ color: 'rgba(255,255,255,0.5)' }}>No videos found for this channel.</p> : null}
                {channelVideos.map((video) => {
                  const isSel = selectedRefVideoIds.includes(video.id)
                  return (
                    <div
                      key={video.id}
                      onClick={() => {
                        setSelectedRefVideoIds((prev) =>
                          prev.includes(video.id) ? prev.filter((id) => id !== video.id) : [...prev, video.id],
                        )
                      }}
                      style={{
                        cursor: 'pointer',
                        border: isSel ? '4px solid var(--primary)' : '4px solid transparent',
                        borderRadius: '12px',
                        overflow: 'hidden',
                        position: 'relative',
                        transition: 'all 0.2s',
                      }}
                    >
                      <img src={video.thumbnail_url} alt={video.title} style={{ width: '100%', display: 'block', aspectRatio: '16/9', objectFit: 'cover' }} />
                      {isSel && (
                        <div style={{ position: 'absolute', top: '8px', right: '8px', background: 'var(--primary)', color: 'white', borderRadius: '50%', width: '28px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 2px 4px rgba(0,0,0,0.3)' }}>
                          <i className="fa-solid fa-check" />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            <div className="modal-footer" style={{ padding: '20px', borderTop: '1px solid rgba(255,255,255,0.1)', textAlign: 'right', background: 'transparent' }}>
              <button className="btn btn-primary" style={{ padding: '10px 24px' }} onClick={() => setShowRefModal(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
