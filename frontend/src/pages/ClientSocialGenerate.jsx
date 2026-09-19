import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import ConfirmModal from '../components/ConfirmModal'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import { formatRecommendationScore } from '../utils/scoreFormat'

function clampCount(value, max) {
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed)) return 1
  return Math.max(1, Math.min(parsed, Math.max(1, max || parsed)))
}

function KeywordChoiceList({
  keywords,
  selectedTopicIds = [],
  onSelect,
  activeTopicId,
  onActiveSelect,
  name,
  emptyText = 'No recommendation keywords found with score 50 or higher.',
}) {
  if (!keywords?.length) {
    return <p className="text-muted">{emptyText}</p>
  }

  const handleToggle = (id) => {
    if (selectedTopicIds.includes(id)) {
      onSelect(selectedTopicIds.filter((tId) => tId !== id))
    } else {
      onSelect([...selectedTopicIds, id])
    }
  }

  return (
    <div className="choice-list">
      {keywords.map((topic) => {
        const isSelected = selectedTopicIds.includes(topic.topic_id)
        const isActive = activeTopicId === topic.topic_id
        return (
          <div
            key={topic.topic_id}
            className={`choice-row${isActive ? ' selected' : ''}`}
            onClick={() => onActiveSelect && onActiveSelect(topic.topic_id)}
            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
          >
            <input
              type="checkbox"
              name={name}
              checked={isSelected}
              onChange={(e) => {
                e.stopPropagation()
                handleToggle(topic.topic_id)
              }}
              onClick={(e) => e.stopPropagation()}
            />
            <span style={{ flex: 1, paddingLeft: '8px' }}>
              <strong>{topic.topic_text}</strong>
              <small style={{ display: 'block' }}>
                Recommended keyword · score {formatRecommendationScore(topic.recommendation_score)}
              </small>
            </span>
            <em>{formatRecommendationScore(topic.recommendation_score)}</em>
          </div>
        )
      })}
    </div>
  )
}

function assetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return `${base}${path}`
}

function formatSavedDate(value) {
  if (!value) return 'Saved draft'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Saved draft'
  return date.toLocaleString()
}

export default function ClientSocialGenerate() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()

  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState('script')
  const [data, setData] = useState({ scripted_items: [], recommended_keywords: [] })
  const [selectedScriptIds, setSelectedScriptIds] = useState([])
  const [activeScriptId, setActiveScriptId] = useState('')
  const [pickCount, setPickCount] = useState(3)
  const [pickedTopics, setPickedTopics] = useState([])
  const [selectedTopicIds, setSelectedTopicIds] = useState([])
  const [activeTopicId, setActiveTopicId] = useState('')
  const [selectedManualTopicIds, setSelectedManualTopicIds] = useState([])
  const [activeManualTopicId, setActiveManualTopicId] = useState('')
  const [picking, setPicking] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generatingProgress, setGeneratingProgress] = useState(null)
  const [loadingSavedPosts, setLoadingSavedPosts] = useState(false)
  const [draft, setDraft] = useState(null)
  const [savedPosts, setSavedPosts] = useState([])
  const [customPrompt, setCustomPrompt] = useState('')
  const [regeneratingPostId, setRegeneratingPostId] = useState(null)
  const [regeneratePrompt, setRegeneratePrompt] = useState('')
  const [uploadingMedia, setUploadingMedia] = useState(false)
  const fileInputRef = useRef(null)
  const [postingPost, setPostingPost] = useState(null)
  const [targetAction, setTargetAction] = useState('publish') // 'publish' | 'schedule'
  const [postToDelete, setPostToDelete] = useState(null)
  const [postToRemoveFromQueue, setPostToRemoveFromQueue] = useState(null)

  const [scheduleAllModalOpen, setScheduleAllModalOpen] = useState(false)
  const [schedulingAll, setSchedulingAll] = useState(false)

  const [postCaption, setPostCaption] = useState('')
  const [publishTargets, setPublishTargets] = useState(['instagram', 'facebook'])
  const [publishing, setPublishing] = useState(false)
  const [editingCaptionPostId, setEditingCaptionPostId] = useState(null)
  const [editingCaptionText, setEditingCaptionText] = useState('')
  const [savingCaption, setSavingCaption] = useState(false)
  const [queueingPostId, setQueueingPostId] = useState(null)
  
  const [referenceImageUrls, setReferenceImageUrls] = useState('')
  const [selectedReferenceMediaIds, setSelectedReferenceMediaIds] = useState([])
  const [showReferenceModal, setShowReferenceModal] = useState(false)
  const [instagramMedia, setInstagramMedia] = useState([])
  const [instagramCursor, setInstagramCursor] = useState(null)
  const [loadingMedia, setLoadingMedia] = useState(false)

  const fetchInstagramMedia = async (isSync = false) => {
    setLoadingMedia(true)
    try {
      const after = isSync ? null : instagramCursor
      const result = await api.getInstagramMedia(token, clientId, 12, after)
      setInstagramMedia(prev => isSync ? result.media : [...prev, ...result.media])
      setInstagramCursor(result.next_cursor)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoadingMedia(false)
    }
  }

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files)
    if (files.length === 0) return
    setUploadingMedia(true)
    try {
      const urls = []
      for (const file of files) {
        const result = await api.uploadInstagramMedia(token, clientId, file)
        urls.push(result.url)
      }
      setReferenceImageUrls(prev => {
        const current = prev.trim()
        return current ? `${current}, ${urls.join(', ')}` : urls.join(', ')
      })
      toast(`Successfully uploaded ${files.length} file(s)`, 'success')
    } catch (err) {
      toast(`Failed to upload files: ${err.message}`, 'error')
    } finally {
      setUploadingMedia(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const loadSources = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.getSocialPostSources(token, clientId)
      const firstScript = result.scripted_items?.[0]?.id || ''
      const firstKeyword = result.recommended_keywords?.[0]?.topic_id || ''
      setData(result)
      setSelectedScriptIds((prev) => prev.length ? prev : (firstScript ? [firstScript] : []))
      setSelectedTopicIds((prev) => prev.length ? prev : (firstKeyword ? [firstKeyword] : []))
      setSelectedManualTopicIds((prev) => prev.length ? prev : (firstKeyword ? [firstKeyword] : []))
      setActiveScriptId((prev) => prev || firstScript)
      setActiveTopicId((prev) => prev || firstKeyword)
      setActiveManualTopicId((prev) => prev || firstKeyword)
      setPickCount((prev) => clampCount(prev, result.recommended_keywords?.length || prev))
    } catch (err) {
      toast(`Failed to load post sources: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    if (token && clientId) void loadSources()
  }, [token, clientId, loadSources])

  const recommendedKeywords = data.recommended_keywords || []
  const maxKeywordCount = recommendedKeywords.length || 1

  const selectedScripts = useMemo(
    () => (data.scripted_items || []).filter((item) => selectedScriptIds.includes(item.id)),
    [data.scripted_items, selectedScriptIds],
  )

  const selectedTopics = useMemo(() => {
    const all = [...pickedTopics, ...recommendedKeywords]
    const unique = []
    const seen = new Set()
    for (const topic of all) {
      if (!seen.has(topic.topic_id) && selectedTopicIds.includes(topic.topic_id)) {
        unique.push(topic)
        seen.add(topic.topic_id)
      }
    }
    return unique
  }, [pickedTopics, recommendedKeywords, selectedTopicIds])

  const selectedManualTopics = useMemo(
    () => recommendedKeywords.filter((topic) => selectedManualTopicIds.includes(topic.topic_id)),
    [recommendedKeywords, selectedManualTopicIds],
  )

  const selectedSources = useMemo(() => {
    const sources = []
    if (mode === 'script') {
      selectedScriptIds.forEach(id => {
        sources.push({ source_type: 'script', content_plan_item_id: id })
      })
    }
    if (mode === 'manual_pick') {
      selectedManualTopicIds.forEach(id => {
        sources.push({ source_type: 'manual_pick', topic_id: id })
      })
    }
    if (mode === 'smart_pick') {
      selectedTopicIds.forEach(id => {
        sources.push({ source_type: 'smart_pick', topic_id: id })
      })
    }
    return sources
  }, [mode, selectedManualTopicIds, selectedScriptIds, selectedTopicIds])

  const activeSourceField = useMemo(() => {
    if (mode === 'script' && activeScriptId) {
      return { source_type: 'script', content_plan_item_id: activeScriptId }
    }
    if (mode === 'manual_pick' && activeManualTopicId) {
      return { source_type: 'manual_pick', topic_id: activeManualTopicId }
    }
    return null
  }, [mode, activeManualTopicId, activeScriptId])

  useEffect(() => {
    if (!token || !clientId || !activeSourceField) {
      setDraft(null)
      setSavedPosts([])
      return undefined
    }

    let cancelled = false
    setLoadingSavedPosts(true)
    setDraft(null)
    setSavedPosts([])

    api
      .getSocialPostVersions(token, clientId, activeSourceField)
      .then((result) => {
        if (cancelled) return
        setSavedPosts(result.posts || [])
        setDraft(result.current_post || null)
      })
      .catch((err) => {
        if (!cancelled) toast(`Failed to load saved post: ${err.message}`, 'error')
      })
      .finally(() => {
        if (!cancelled) setLoadingSavedPosts(false)
      })

    return () => {
      cancelled = true
    }
  }, [token, clientId, activeSourceField, toast])

  async function handlePickTopics() {
    setPicking(true)
    try {
      const result = await api.pickSocialKeywords(token, clientId, { count: pickCount })
      const topics = result.selected_keywords || []
      setPickedTopics(topics)
      setSelectedTopicIds(topics.map(t => t.topic_id))
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setPicking(false)
    }
  }

  async function handleGenerate(overrideFields = null, overridePrompt = undefined) {
    const sourcesToGenerate = overrideFields ? [overrideFields] : selectedSources
    if (!sourcesToGenerate || sourcesToGenerate.length === 0) return
    
    setGenerating(true)
    let successCount = 0
    let totalCount = sourcesToGenerate.length
    
    try {
      for (let i = 0; i < totalCount; i++) {
        const source = sourcesToGenerate[i]
        setGeneratingProgress(`Generating ${i + 1} of ${totalCount}...`)
        
        const payload = { ...source }
        const promptToUse = overridePrompt !== undefined ? overridePrompt : customPrompt
        if (promptToUse) {
          payload.custom_prompt = promptToUse
        }
        if (referenceImageUrls.trim()) {
          payload.reference_image_urls = referenceImageUrls.trim()
        }
        if (selectedReferenceMediaIds.length > 0) {
          payload.reference_media_ids = selectedReferenceMediaIds
        }
        
        const result = await api.generateSocialPostDraft(token, clientId, payload)
        setDraft(result.post)
        setSavedPosts((prev) => [result.post, ...prev.filter((post) => post.id !== result.post.id)])
        
        // Use standard logic for title/topic
        const title = mode === 'script' ? 'script' : 'topic'
        toast(`Successfully generated post ${i + 1} of ${totalCount}.`, 'success')
        successCount++
      }

      if (overridePrompt === undefined) {
        setCustomPrompt('')
      } else {
        setRegeneratingPostId(null)
        setRegeneratePrompt('')
      }
    } catch (err) {
      toast(`Failed during generation: ${err.message}`, 'error')
    } finally {
      setGenerating(false)
      setGeneratingProgress(null)
    }
  }

  function handleConfirmRegenerate(post) {
    const fields = { source_type: post.source_type }
    if (post.topic_id) fields.topic_id = post.topic_id
    if (post.content_plan_item_id) fields.content_plan_item_id = post.content_plan_item_id
    handleGenerate(fields, regeneratePrompt)
  }

  function handlePostToInsta(post) {
    setPostingPost(post)
    setPostCaption(post.brief?.caption || '')
    setTargetAction('publish')
  }

  async function handleConfirmPublish() {
    if (!postingPost) return
    if (publishTargets.length === 0) {
      toast('Please select at least one platform.', 'error')
      return
    }
    setPublishing(true)
    try {
      if (targetAction === 'publish') {
        await api.publishSocialPost(token, clientId, postingPost.id, postCaption, publishTargets)
        toast('Post successfully published!', 'success')
      } else {
        await api.addSocialPostToQueue(token, clientId, postingPost.id, publishTargets)
        toast('Post successfully added to schedule!', 'success')
      }
      setPostingPost(null)
      setPostCaption('')
      
      const result = await api.getSocialPostVersions(token, clientId, activeSourceField)
      setSavedPosts(result.posts || [])
      setDraft(result.current_post || null)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setPublishing(false)
    }
  }

  async function handleSelectPost(postId) {
    try {
      const result = await api.selectSocialPost(token, clientId, postId)
      setSavedPosts(result.posts || [])
      setDraft(result.current_post || null)
      toast('Generated post selected.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleDeletePost() {
    if (!postToDelete) return
    const idToDelete = postToDelete
    setPostToDelete(null)
    setSavedPosts(savedPosts.filter((p) => p.id !== idToDelete))
    if (draft && draft.id === idToDelete) {
      setDraft(null)
    }
    try {
      const result = await api.deleteSocialPost(token, clientId, idToDelete)
      toast('Generated post deleted.', 'success')
      if (draft && draft.id === idToDelete) {
        setDraft(result.current_post || null)
      }
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleEditCaptionSave(post) {
    if (!editingCaptionText.trim()) {
      toast('Caption cannot be empty', 'error')
      return
    }
    setSavingCaption(true)
    try {
      const result = await api.editSocialPostQueueCaption(token, clientId, post.id, editingCaptionText)
      setSavedPosts(savedPosts.map(p => p.id === post.id ? result.post : p))
      if (draft && draft.id === post.id) setDraft(result.post)
      setEditingCaptionPostId(null)
      toast('Caption saved.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingCaption(false)
    }
  }


  const handleConfirmScheduleAll = async () => {
    const unscheduledPosts = savedPosts.filter(p => p.publish_status === 'draft')
    if (unscheduledPosts.length === 0) return
    
    setSchedulingAll(true)
    try {
      const postIds = unscheduledPosts.map(p => p.id)
      const result = await api.bulkQueueSocialPosts(token, clientId, postIds, publishTargets)
      setSavedPosts(result.posts || [])
      
      if (draft && unscheduledPosts.some(p => p.id === draft.id)) {
        const updatedDraft = (result.posts || []).find(p => p.id === draft.id)
        if (updatedDraft) setDraft(updatedDraft)
      }
      toast(`Successfully scheduled ${postIds.length} posts!`, 'success')
      setScheduleAllModalOpen(false)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSchedulingAll(false)
    }
  }

  const handleToggleTarget = (post, target) => {
    const currentTargets = post.publish_targets || []
    let newTargets = []
    if (currentTargets.includes(target)) {
      newTargets = currentTargets.filter(t => t !== target)
    } else {
      newTargets = [...currentTargets, target]
    }
    
    if (newTargets.length === 0 && post.publish_status === 'scheduled') {
      setPostToRemoveFromQueue({ post, newTargets })
      return
    }
    
    executeToggleTarget(post, newTargets)
  }

  const executeToggleTarget = async (post, newTargets) => {
    // Optimistic update
    const updatedPost = { 
      ...post, 
      publish_targets: newTargets,
      publish_status: newTargets.length === 0 && post.publish_status === 'scheduled' ? 'draft' : 'scheduled'
    }
    setSavedPosts(savedPosts.map(p => p.id === post.id ? updatedPost : p))
    if (draft && draft.id === post.id) setDraft(updatedPost)
    
    try {
      const result = await api.updateSocialPostTargets(token, clientId, post.id, newTargets)
      if (newTargets.length === 0) {
        toast('Post removed from queue.', 'success')
      }
      setSavedPosts(savedPosts.map(p => p.id === post.id ? result.post : p))
      if (draft && draft.id === post.id) setDraft(result.post)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      if (postToRemoveFromQueue) {
        setPostToRemoveFromQueue(null)
      }
    }
  }

  const canGenerate = selectedSources && selectedSources.length > 0

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: 'Social Media' },
            ]}
          />
          <h1>Generate Instagram Post</h1>
          <p>Select a scripted topic or pick recommended keywords for a static Instagram post.</p>
        </div>
      </header>

      {loading ? (
        <div className="loading-overlay inline-loading">
          <div className="spinner-loader">
            <i className="fa-solid fa-spinner fa-spin" />
            <span>Loading post sources…</span>
          </div>
        </div>
      ) : (
        <div className="social-generate-grid">
          <section className="card profile-form social-card">
            <div className="profile-section">
              <h2>Content Source</h2>
              <div className="segmented-control">
                <button
                  type="button"
                  className={mode === 'script' ? 'active' : ''}
                  onClick={() => setMode('script')}
                >
                  From Script
                </button>
                <button
                  type="button"
                  className={mode === 'smart_pick' ? 'active' : ''}
                  onClick={() => setMode('smart_pick')}
                >
                  Smart Pick
                </button>
                <button
                  type="button"
                  className={mode === 'manual_pick' ? 'active' : ''}
                  onClick={() => setMode('manual_pick')}
                >
                  Manual Pick
                </button>
              </div>
            </div>

            {mode === 'script' && (
              <div className="profile-section">
                <h2>Scripted Keywords</h2>
                <p className="profile-section-desc">
                  Using scripts from the current latest content plan.
                </p>
                {data.scripted_items?.length ? (
                  <div className="choice-list">
                    {data.scripted_items.map((item) => {
                      const isSelected = selectedScriptIds.includes(item.id)
                      const isActive = activeScriptId === item.id
                      return (
                        <div
                          key={item.id}
                          className={`choice-row${isActive ? ' selected' : ''}`}
                          onClick={() => setActiveScriptId(item.id)}
                          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                        >
                          <input
                            type="checkbox"
                            name="scripted_item"
                            checked={isSelected}
                            onChange={(e) => {
                              e.stopPropagation()
                              if (isSelected) {
                                setSelectedScriptIds(selectedScriptIds.filter(id => id !== item.id))
                              } else {
                                setSelectedScriptIds([...selectedScriptIds, item.id])
                              }
                            }}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <span style={{ flex: 1, paddingLeft: '8px' }}>
                            <strong>{item.topic_text}</strong>
                            <small style={{ display: 'block' }}>{item.working_title || item.title_hinglish || item.title_en}</small>
                          </span>
                          <em>{formatRecommendationScore(item.recommendation_score)}</em>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-muted">No scripted items found in the current content plan.</p>
                )}
              </div>
            )}

            {mode === 'smart_pick' && (
              <div className="profile-section">
                <h2>Smart Pick</h2>
                <p className="profile-section-desc">
                  Picks from recommendation keywords with score 50 or higher, weighted by score.
                </p>
                <div className="pick-count-row">
                  <span>Keyword count</span>
                  <div className="count-stepper" aria-label="Keyword count">
                    <button
                      type="button"
                      onClick={() => setPickCount((prev) => clampCount(prev - 1, maxKeywordCount))}
                      disabled={pickCount <= 1}
                    >
                      <i className="fa-solid fa-minus" />
                    </button>
                    <input
                      type="number"
                      min="1"
                      max={maxKeywordCount}
                      value={pickCount}
                      onChange={(event) =>
                        setPickCount(clampCount(event.target.value, maxKeywordCount))
                      }
                    />
                    <button
                      type="button"
                      onClick={() => setPickCount((prev) => clampCount(prev + 1, maxKeywordCount))}
                      disabled={pickCount >= maxKeywordCount}
                    >
                      <i className="fa-solid fa-plus" />
                    </button>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={handlePickTopics}
                    disabled={picking || !recommendedKeywords.length}
                  >
                    <i className={`fa-solid ${picking ? 'fa-spinner fa-spin' : 'fa-shuffle'}`} />
                    {picking ? 'Picking…' : 'Pick Keywords'}
                  </button>
                </div>

                {pickedTopics.length > 0 && (
                  <>
                    <h3 className="subsection-title">Picked Keywords</h3>
                    <KeywordChoiceList
                      keywords={pickedTopics}
                      selectedTopicIds={selectedTopicIds}
                      onSelect={setSelectedTopicIds}
                      activeTopicId={activeTopicId}
                      onActiveSelect={setActiveTopicId}
                      name="picked_topic"
                    />
                  </>
                )}
              </div>
            )}

            {mode === 'manual_pick' && (
              <div className="profile-section">
                <h2>Manual Pick</h2>
                <p className="profile-section-desc">
                  Manually select recommendation keywords with score 50 or higher.
                </p>
                <details className="keyword-dropdown-card" open>
                  <summary>
                    <span>All Recommended Keywords</span>
                    <strong>{recommendedKeywords.length}</strong>
                  </summary>
                  <KeywordChoiceList
                    keywords={recommendedKeywords}
                    selectedTopicIds={selectedManualTopicIds}
                    onSelect={setSelectedManualTopicIds}
                    activeTopicId={activeManualTopicId}
                    onActiveSelect={setActiveManualTopicId}
                    name="manual_keyword"
                  />
                </details>
              </div>
            )}

            <div className="profile-section" style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
              <h2>Edit with AI</h2>
              <p className="profile-section-desc">
                Only this script is sent — plus format metadata and your instruction.
              </p>
              
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <label style={{ fontWeight: 600 }}>Reference Image URLs (Optional)</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <div style={{ position: 'relative', display: 'inline-block' }} className="tooltip-container">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          if (fileInputRef.current) fileInputRef.current.click()
                        }}
                        disabled={uploadingMedia}
                      >
                        <i className={`fa-solid ${uploadingMedia ? 'fa-spinner fa-spin' : 'fa-paperclip'}`} style={{ marginRight: '6px' }} />
                        {uploadingMedia ? 'Uploading...' : 'Upload Local'}
                      </button>
                      <div className="tooltip-content" style={{ position: 'absolute', bottom: '100%', right: 0, marginBottom: '8px', padding: '8px', backgroundColor: '#333', color: 'white', fontSize: '12px', borderRadius: '4px', width: '250px', textAlign: 'center', zIndex: 10, display: 'none', pointerEvents: 'none' }}>
                        Upload reference images directly from your computer.
                      </div>
                    </div>
                    <div style={{ position: 'relative', display: 'inline-block' }} className="tooltip-container">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setShowReferenceModal(true)
                          if (instagramMedia.length === 0) fetchInstagramMedia(true)
                        }}
                      >
                        <i className="fa-solid fa-images" style={{ marginRight: '6px' }} />
                        Choose Reference Posts
                      </button>
                      <div className="tooltip-content" style={{ position: 'absolute', bottom: '100%', right: 0, marginBottom: '8px', padding: '8px', backgroundColor: '#333', color: 'white', fontSize: '12px', borderRadius: '4px', width: '250px', textAlign: 'center', zIndex: 10, display: 'none', pointerEvents: 'none' }}>
                        Select reference images from your Instagram handle so the AI can take design inspiration from them.
                      </div>
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      ref={fileInputRef}
                      style={{ display: 'none' }}
                      onChange={handleFileUpload}
                    />
                  </div>
                </div>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. https://example.com/image.png (Public URLs only). Or click 'Choose Reference Posts' above to select from your Instagram handle."
                  value={referenceImageUrls}
                  onChange={(e) => setReferenceImageUrls(e.target.value)}
                  disabled={!canGenerate || generating}
                  style={{ 
                    width: '100%', 
                    marginBottom: '8px',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    outline: 'none',
                    boxShadow: 'none',
                    padding: '8px 12px'
                  }}
                />
                {referenceImageUrls.trim() && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '8px' }}>
                    {referenceImageUrls.split(',').map((url, i) => {
                      const trimmed = url.trim()
                      if (!trimmed) return null
                      return (
                        <div key={i} style={{ width: '60px', height: '60px', borderRadius: '4px', overflow: 'hidden', border: '1px solid var(--border-color)', position: 'relative' }}>
                          <img 
                            src={trimmed} 
                            alt={`Preview ${i}`} 
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                            onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex' }}
                          />
                          <div style={{ display: 'none', width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8f9fa', color: '#dc3545', fontSize: '12px' }}>
                            <i className="fa-solid fa-link-slash"></i>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const urls = referenceImageUrls.split(',').map(u => u.trim()).filter(Boolean)
                              urls.splice(i, 1)
                              setReferenceImageUrls(urls.join(', '))
                            }}
                            style={{
                              position: 'absolute',
                              top: '2px',
                              right: '2px',
                              background: 'rgba(255, 0, 0, 0.8)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '50%',
                              width: '18px',
                              height: '18px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: 'pointer',
                              padding: 0,
                              fontSize: '10px'
                            }}
                            title="Remove image"
                          >
                            <i className="fa-solid fa-xmark"></i>
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <label style={{ fontWeight: 600, display: 'block', marginBottom: '8px' }}>Instructions</label>
              <textarea
                className="form-control"
                placeholder="e.g. Softer host tone; complete intro sentence; clear CTA at end"
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                rows={4}
                disabled={!canGenerate || generating}
                style={{ 
                  marginBottom: '1rem', 
                  width: '100%', 
                  resize: 'vertical',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  outline: 'none',
                  boxShadow: 'none',
                  padding: '8px 12px'
                }}
              />
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <div style={{ position: 'relative', display: 'inline-block' }} className="tooltip-container">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleGenerate()}
                    disabled={selectedSources.length === 0 || generating}
                  >
                    <i
                      className={`fa-solid ${generating ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}`}
                    />
                    {generatingProgress ? generatingProgress : (generating ? 'Generating…' : 'Generate Post(s)')}
                  </button>
                  {(!referenceImageUrls && selectedReferenceMediaIds.length === 0) && (
                    <div className="tooltip-content" style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: '8px', padding: '8px', backgroundColor: '#333', color: 'white', fontSize: '12px', borderRadius: '4px', width: '300px', textAlign: 'left', zIndex: 10, display: 'none', pointerEvents: 'none' }}>
                      If no references are selected, the AI defaults to using your 3 most recent Instagram images.
                    </div>
                  )}
                  <style>{`
                    .tooltip-container:hover .tooltip-content {
                      display: block !important;
                    }
                  `}</style>
                </div>
                {savedPosts.filter(p => p.publish_status === 'draft').length > 0 && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setScheduleAllModalOpen(true)}
                    disabled={generating}
                  >
                    <i className="fa-solid fa-clock"></i> Schedule All Drafts
                  </button>
                )}
              </div>

            </div>
          </section>

          {!(mode === 'smart_pick' && savedPosts.length === 0) && (
            <section className="card profile-form social-card">
            <div className="profile-section">
              <div className="draft-heading-row">
                <h2>Draft Preview</h2>
                {draft ? (
                  <span className="status-pill success">
                    {draft.publish_status === 'published' ? 'Published' : draft.publish_status === 'scheduled' ? 'Scheduled' : 'Generated'}
                  </span>
                ) : null}
              </div>
              {loadingSavedPosts ? (
                <p className="profile-section-desc">Checking saved generated posts…</p>
              ) : !draft ? (
                <p className="profile-section-desc">
                  No generated post exists for this selected source yet.
                </p>
              ) : (
                <div className="draft-preview">
                  {draft.image_url ? (
                    <img
                      className="draft-generated-image"
                      src={assetUrl(draft.image_url)}
                      alt={`Generated Instagram post for ${draft.topic_text}`}
                    />
                  ) : (
                    <div className="draft-image-placeholder">
                      <i className="fa-solid fa-image" />
                      <span>{draft.image_status || 'Image generation pending'}</span>
                    </div>
                  )}
                  <dl>
                    <dt>Topic</dt>
                    <dd>{draft.topic_text}</dd>
                    <dt>Headline</dt>
                    <dd>{draft.brief?.headline}</dd>
                    <dt>Subheadline</dt>
                    <dd>{draft.brief?.subheadline}</dd>
                    <dt>Caption</dt>
                    <dd>{draft.brief?.caption}</dd>
                    <dt>Saved</dt>
                    <dd>{formatSavedDate(draft.created_at)}</dd>
                  </dl>
                </div>
              )}
            </div>

            {savedPosts.length > 0 && (
              <div className="profile-section">
                <h2>Saved Versions</h2>
                <p className="profile-section-desc">
                  Every generation is kept. Preview uses the selected version, or the newest version
                  when none is selected.
                </p>
                <div className="version-list">
                  {savedPosts.map((post, index) => (
                    <div
                      key={post.id}
                      className={`version-row${draft?.id === post.id ? ' active' : ''}`}
                    >
                      <button
                        type="button"
                        className="version-thumb"
                        onClick={() => setDraft(post)}
                        aria-label={`Preview version ${savedPosts.length - index}`}
                      >
                        {post.image_url ? (
                          <img src={assetUrl(post.image_url)} alt="" />
                        ) : (
                          <i className="fa-solid fa-image" />
                        )}
                      </button>
                      <div className="version-meta" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <strong>
                            Version {savedPosts.length - index}
                            {post.is_selected ? <span>Selected</span> : null}
                          </strong>
                          <small>{formatSavedDate(post.created_at)}</small>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {(post.publish_status === 'published' || post.publish_status === 'scheduled') && (
                            <span className="status-pill success">
                              {post.publish_status === 'published' ? 'Published' : 'Scheduled'}
                            </span>
                          )}
                          <button 
                            className="btn btn-icon btn-sm text-danger" 
                            title="Delete post"
                            onClick={(e) => { e.stopPropagation(); setPostToDelete(post.id); }}
                            style={{ padding: '4px' }}
                          >
                            <i className="fa-solid fa-trash"></i>
                          </button>
                        </div>
                      </div>
                      <div className="version-actions draft-actions" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', padding: '0 16px 16px' }}>
                        {regeneratingPostId === post.id ? (
                          <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <textarea
                              className="form-control"
                              placeholder="Optional custom instructions..."
                              value={regeneratePrompt}
                              onChange={(e) => setRegeneratePrompt(e.target.value)}
                              rows={2}
                              style={{ 
                                flex: 1, 
                                minHeight: '60px',
                                border: '1px solid #e2e8f0',
                                borderRadius: '8px',
                                outline: 'none',
                                boxShadow: 'none'
                              }}
                            />
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => handleRegeneratePost(post)}
                                disabled={generating}
                                style={{ flex: 1 }}
                              >
                                {generating ? 'Regenerating...' : 'Confirm'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => setRegeneratingPostId(null)}
                                disabled={generating}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : editingCaptionPostId === post.id ? (
                          <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <textarea
                              className="form-control"
                              value={editingCaptionText}
                              onChange={(e) => setEditingCaptionText(e.target.value)}
                              rows={4}
                              style={{ 
                                flex: 1, 
                                minHeight: '80px',
                                border: '1px solid #e2e8f0',
                                borderRadius: '8px',
                                outline: 'none',
                                boxShadow: 'none'
                              }}
                            />
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => handleEditCaptionSave(post)}
                                disabled={savingCaption}
                                style={{ flex: 1 }}
                              >
                                {savingCaption ? 'Saving...' : 'Save Caption'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => setEditingCaptionPostId(null)}
                                disabled={savingCaption}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="btn btn-outline-primary btn-sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                setRegeneratingPostId(post.id)
                                setRegeneratePrompt('')
                              }}
                              disabled={generating}
                            >
                              <i className="fa-solid fa-rotate"></i> Regenerate
                            </button>
                            <button
                              type="button"
                              className="btn btn-outline-secondary btn-sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                setEditingCaptionPostId(post.id)
                                setEditingCaptionText(post.brief?.caption || '')
                              }}
                              disabled={generating}
                            >
                              <i className="fa-solid fa-pen"></i> Edit Caption
                            </button>
                            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', backgroundColor: '#f1f5f9', padding: '4px 12px', borderRadius: '4px' }}>
                              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b', marginRight: '4px' }}>Schedule:</span>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleToggleTarget(post, 'facebook'); }}
                                title={(post.publish_targets || []).includes('facebook') ? "Scheduled for Facebook (Click to Unschedule)" : "Not scheduled for Facebook (Click to Schedule)"}
                                style={{
                                  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                                  color: (post.publish_targets || []).includes('facebook') ? '#1877F2' : '#cbd5e1',
                                  transition: 'color 0.2s', fontSize: '18px'
                                }}
                                disabled={generating}
                              >
                                <i className="fa-brands fa-facebook"></i>
                              </button>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleToggleTarget(post, 'instagram'); }}
                                title={(post.publish_targets || []).includes('instagram') ? "Scheduled for Instagram (Click to Unschedule)" : "Not scheduled for Instagram (Click to Schedule)"}
                                style={{
                                  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                                  color: (post.publish_targets || []).includes('instagram') ? '#E1306C' : '#cbd5e1',
                                  transition: 'color 0.2s', fontSize: '18px'
                                }}
                                disabled={generating}
                              >
                                <i className="fa-brands fa-instagram"></i>
                              </button>
                            </div>
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                handlePostToInsta(post)
                              }}
                              disabled={generating}
                            >
                              <i className="fa-solid fa-paper-plane"></i> Post Now
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
          )}

          <aside className="card social-side-panel">
            <h3>Current Selection</h3>
            {mode === 'script' && activeSourceField ? (
              <div>
                <strong>{(data.scripted_items || []).find(s => s.id === activeScriptId)?.topic_text || 'Select a script'}</strong>
              </div>
            ) : mode === 'smart_pick' && activeSourceField ? (
              <div>
                <strong>{[...pickedTopics, ...recommendedKeywords].find(t => t.topic_id === activeTopicId)?.topic_text || 'Select a topic'}</strong>
              </div>
            ) : mode === 'manual_pick' && activeSourceField ? (
              <div>
                <strong>{recommendedKeywords.find(t => t.topic_id === activeManualTopicId)?.topic_text || 'Select a topic'}</strong>
              </div>
            ) : (
              <p className="text-muted">Choose a source to continue.</p>
            )}
          </aside>
        </div>
      )}
      
      {showReferenceModal && (
        <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="modal-content" style={{ backgroundColor: 'white', borderRadius: '12px', padding: '24px', maxWidth: '800px', width: '90%', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ margin: 0 }}>Choose Reference Posts</h2>
              <div>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => fetchInstagramMedia(true)} disabled={loadingMedia} style={{ marginRight: '8px' }}>
                  <i className={`fa-solid fa-sync ${loadingMedia ? 'fa-spin' : ''}`} /> Sync Posts
                </button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowReferenceModal(false)}>Close</button>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '4px', minHeight: 0 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '16px' }}>
                {instagramMedia.filter(m => m.media_type === 'IMAGE' || m.media_type === 'CAROUSEL_ALBUM').map(media => {
                  const isSelected = selectedReferenceMediaIds.includes(media.id)
                  return (
                    <div
                      key={media.id}
                      onClick={() => {
                        if (isSelected) {
                          setSelectedReferenceMediaIds(prev => prev.filter(id => id !== media.id))
                        } else {
                          setSelectedReferenceMediaIds(prev => [...prev, media.id])
                        }
                      }}
                      style={{
                        cursor: 'pointer',
                        border: isSelected ? '4px solid var(--primary)' : '4px solid transparent',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        position: 'relative'
                      }}
                    >
                      <img src={media.thumbnail_url || media.media_url} alt="" style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block' }} />
                      {isSelected && (
                        <div style={{ position: 'absolute', top: '8px', right: '8px', backgroundColor: 'var(--primary)', color: 'white', borderRadius: '50%', width: '28px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 2px 4px rgba(0,0,0,0.2)' }}>
                          <i className="fa-solid fa-check" />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              {instagramCursor && (
                <div style={{ textAlign: 'center', marginTop: '16px', marginBottom: '16px' }}>
                  <button type="button" className="btn btn-secondary" onClick={() => fetchInstagramMedia(false)} disabled={loadingMedia}>
                    {loadingMedia ? 'Loading...' : 'Load More'}
                  </button>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px', borderTop: '1px solid #eee', paddingTop: '16px' }}>
              <button type="button" className="btn btn-primary" onClick={() => setShowReferenceModal(false)}>
                Confirm Selections ({selectedReferenceMediaIds.length})
              </button>
            </div>
          </div>
        </div>
      )}
      
      {postingPost && (
        <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="modal card" style={{ width: '90%', maxWidth: '500px', padding: '24px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '20px' }}>{targetAction === 'schedule' ? 'Schedule Post' : 'Post to Social Media'}</h3>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '20px' }}>
              <img src={assetUrl(postingPost.image_url)} alt="Preview" style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: '8px' }} />
              <textarea
                className="form-input"
                rows={4}
                value={postCaption}
                onChange={(e) => setPostCaption(e.target.value)}
                style={{ flex: 1, resize: 'none', fontSize: '0.9rem' }}
                disabled={targetAction === 'schedule'}
              />
            </div>
            
            <div style={{ marginBottom: '20px' }}>
              <p style={{ fontWeight: '500', marginBottom: '8px' }}>Publish To:</p>
              <div style={{ display: 'flex', gap: '16px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={publishTargets.includes('instagram')}
                    onChange={(e) => {
                      if (e.target.checked) setPublishTargets([...publishTargets, 'instagram'])
                      else setPublishTargets(publishTargets.filter(t => t !== 'instagram'))
                    }}
                  />
                  <span><i className="fa-brands fa-instagram" style={{ color: '#E1306C' }}></i> Instagram</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={publishTargets.includes('facebook')}
                    onChange={(e) => {
                      if (e.target.checked) setPublishTargets([...publishTargets, 'facebook'])
                      else setPublishTargets(publishTargets.filter(t => t !== 'facebook'))
                    }}
                  />
                  <span><i className="fa-brands fa-facebook" style={{ color: '#1877F2' }}></i> Facebook</span>
                </label>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button 
                className="btn btn-secondary" 
                onClick={() => setPostingPost(null)}
                disabled={publishing}
              >
                Cancel
              </button>
              <button 
                className="btn btn-primary" 
                onClick={handleConfirmPublish}
                disabled={publishing}
              >
                {publishing ? 'Processing...' : (targetAction === 'schedule' ? 'Schedule Post' : 'Publish Now')}
              </button>
            </div>
          </div>
        </div>
      )}

      {scheduleAllModalOpen && (
        <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="modal card" style={{ width: '90%', maxWidth: '500px', padding: '24px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '20px' }}>Schedule All Drafts</h3>
            <p style={{ marginBottom: '20px' }}>
              You are about to schedule <strong>{savedPosts.filter(p => p.publish_status === 'draft').length}</strong> newly generated posts. They will be added to the end of your queue.
            </p>
            <div style={{ marginBottom: '20px' }}>
              <p style={{ fontWeight: '500', marginBottom: '8px' }}>Publish To:</p>
              <div style={{ display: 'flex', gap: '16px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={publishTargets.includes('instagram')}
                    onChange={(e) => {
                      if (e.target.checked) setPublishTargets([...publishTargets, 'instagram'])
                      else setPublishTargets(publishTargets.filter(t => t !== 'instagram'))
                    }}
                  />
                  <span><i className="fa-brands fa-instagram" style={{ color: '#E1306C' }}></i> Instagram</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={publishTargets.includes('facebook')}
                    onChange={(e) => {
                      if (e.target.checked) setPublishTargets([...publishTargets, 'facebook'])
                      else setPublishTargets(publishTargets.filter(t => t !== 'facebook'))
                    }}
                  />
                  <span><i className="fa-brands fa-facebook" style={{ color: '#1877F2' }}></i> Facebook</span>
                </label>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button 
                className="btn btn-secondary" 
                onClick={() => setScheduleAllModalOpen(false)}
                disabled={schedulingAll}
              >
                Cancel
              </button>
              <button 
                className="btn btn-primary" 
                onClick={handleConfirmScheduleAll}
                disabled={schedulingAll || publishTargets.length === 0}
              >
                {schedulingAll ? 'Scheduling...' : 'Confirm Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}
      
      <ConfirmModal
        isOpen={!!postToDelete}
        title="Delete Generated Version"
        message="Are you sure you want to delete this generated version? This cannot be undone."
        onCancel={() => setPostToDelete(null)}
        onConfirm={handleDeletePost}
      />
      
      <ConfirmModal
        isOpen={!!postToRemoveFromQueue}
        title="Remove from Queue"
        message="Removing all platforms will remove this post from the queue and put it back in drafts. Continue?"
        confirmText="Remove"
        onCancel={() => setPostToRemoveFromQueue(null)}
        onConfirm={() => {
          if (postToRemoveFromQueue) {
            executeToggleTarget(postToRemoveFromQueue.post, postToRemoveFromQueue.newTargets)
          }
        }}
      />
    </>
  )
}
