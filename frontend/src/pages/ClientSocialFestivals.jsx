import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import ConfirmModal from '../components/ConfirmModal'

const PAGE_SIZE = 6

function assetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return `${base}${path}`
}

// generation_origin is extra metadata so this page can split Auto vs Manual
// sections without parsing topic_id. 9 AM auto-publish still uses topic_id
// (festival_YYYY-MM-DD), not this field.
function isAutoFestivePost(post) {
  if (post?.generation_origin === 'manual-festival') return false
  if (post?.generation_origin === 'cron-festival') return true
  // Old drafts have no origin; date-shaped topic_id is auto.
  return /^festival_\d{4}-\d{2}-\d{2}$/.test(post?.topic_id || '')
}

function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px' }}>
      <button className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </button>
      <span style={{ alignSelf: 'center', fontSize: '0.9rem', color: '#64748b' }}>
        Page {page} of {totalPages}
      </span>
      <button className="btn btn-secondary btn-sm" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </div>
  )
}

export default function ClientSocialFestivals() {
  const { clientId } = useParams()
  const { token } = useAuth()
  const { toast } = useUI()

  const [loading, setLoading] = useState(true)
  const [savingSchedule, setSavingSchedule] = useState(false)
  const [scheduleData, setScheduleData] = useState(null)

  const [festivePosts, setFestivePosts] = useState([])

  const [regeneratingPostId, setRegeneratingPostId] = useState(null)
  const [regeneratePrompt, setRegeneratePrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [manualPrompt, setManualPrompt] = useState('')
  const [manualGenerating, setManualGenerating] = useState(false)

  const [editingCaptionPostId, setEditingCaptionPostId] = useState(null)
  const [editingCaptionText, setEditingCaptionText] = useState('')
  const [savingCaption, setSavingCaption] = useState(false)

  const [queueingPostId, setQueueingPostId] = useState(null)
  const [postingPost, setPostingPost] = useState(null)
  const [targetAction, setTargetAction] = useState('publish')
  const [postCaption, setPostCaption] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [postToDelete, setPostToDelete] = useState(null)
  const [publishTargets, setPublishTargets] = useState(['instagram', 'facebook'])

  const [autoPage, setAutoPage] = useState(1)
  const [manualPage, setManualPage] = useState(1)

  const [selectedReferenceMediaIds, setSelectedReferenceMediaIds] = useState([])
  const [regenerateReferenceMediaIds, setRegenerateReferenceMediaIds] = useState([])
  const [showReferenceModal, setShowReferenceModal] = useState(false)
  const [referencePickerFor, setReferencePickerFor] = useState('generate')
  const [instagramMedia, setInstagramMedia] = useState([])
  const [instagramCursor, setInstagramCursor] = useState(null)
  const [loadingMedia, setLoadingMedia] = useState(false)

  const loadData = useCallback(async () => {
    if (!token || !clientId) return
    setLoading(true)
    try {
      const [scheduleRes, postsRes] = await Promise.all([
        api.getSocialSchedule(token, clientId),
        api.getFestivePosts(token, clientId)
      ])
      setScheduleData(scheduleRes || {})
      setFestivePosts(postsRes.posts || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    loadData()
  }, [loadData])

  const autoPosts = useMemo(() => festivePosts.filter(isAutoFestivePost), [festivePosts])
  const manualPosts = useMemo(() => festivePosts.filter((p) => !isAutoFestivePost(p)), [festivePosts])

  const autoTotalPages = Math.max(1, Math.ceil(autoPosts.length / PAGE_SIZE))
  const manualTotalPages = Math.max(1, Math.ceil(manualPosts.length / PAGE_SIZE))
  const autoSlice = autoPosts.slice((autoPage - 1) * PAGE_SIZE, autoPage * PAGE_SIZE)
  const manualSlice = manualPosts.slice((manualPage - 1) * PAGE_SIZE, manualPage * PAGE_SIZE)

  useEffect(() => {
    if (autoPage > autoTotalPages) setAutoPage(autoTotalPages)
  }, [autoPage, autoTotalPages])

  useEffect(() => {
    if (manualPage > manualTotalPages) setManualPage(manualTotalPages)
  }, [manualPage, manualTotalPages])

  const fetchInstagramMedia = async (isSync = false) => {
    setLoadingMedia(true)
    try {
      const after = isSync ? null : instagramCursor
      const result = await api.getInstagramMedia(token, clientId, 12, after)
      setInstagramMedia((prev) => (isSync ? result.media : [...prev, ...result.media]))
      setInstagramCursor(result.next_cursor)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoadingMedia(false)
    }
  }

  const openReferenceModal = (target) => {
    setReferencePickerFor(target)
    setShowReferenceModal(true)
    if (instagramMedia.length === 0) fetchInstagramMedia(true)
  }

  async function handleToggleAutoPublish(checked, platform = 'instagram') {
    if (!scheduleData) return
    setSavingSchedule(true)
    try {
      const fbChecked = platform === 'facebook' ? checked : (scheduleData.festive_facebook_auto_publish || false)
      const igChecked = platform === 'instagram' ? checked : (scheduleData.festive_auto_publish || false)

      await api.saveSocialSchedule(
        token,
        clientId,
        scheduleData.frequency || 'off',
        scheduleData.selected_days || [],
        scheduleData.auto_fallback || false,
        scheduleData.posts_per_day || 1,
        igChecked,
        scheduleData.facebook_auto_publish || false,
        fbChecked
      )
      setScheduleData((prev) => ({
        ...prev,
        festive_auto_publish: igChecked,
        festive_facebook_auto_publish: fbChecked
      }))
      toast(`Festive ${platform} auto-publish setting updated.`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingSchedule(false)
    }
  }

  async function handleManualGenerate() {
    const prompt = manualPrompt.trim()
    if (!prompt) {
      toast('Enter festival instructions first.', 'error')
      return
    }
    setManualGenerating(true)
    try {
      const fields = {
        source_type: 'festival',
        custom_prompt: prompt,
        // Extra metadata for Festive Posts sections so the UI does not parse topic_id.
        generation_origin: 'manual-festival',
      }
      if (selectedReferenceMediaIds.length > 0) {
        fields.reference_media_ids = selectedReferenceMediaIds
      }
      const result = await api.generateSocialPostDraft(token, clientId, fields)
      setFestivePosts((prev) => [result.post, ...prev.filter((p) => p.id !== result.post.id)])
      setManualPrompt('')
      setManualPage(1)
      toast('Festive post generated.', 'success')
    } catch (err) {
      toast(`Failed to generate: ${err.message}`, 'error')
    } finally {
      setManualGenerating(false)
    }
  }

  async function handleConfirmRegenerate(post) {
    setGenerating(true)
    try {
      const fields = {
        source_type: 'festival',
        topic_id: post.topic_id,
        topic_text: post.topic_text,
        custom_prompt: regeneratePrompt || undefined,
        // Keep origin so regenerate stays in the same Auto vs Manual section.
        generation_origin: post.generation_origin || (isAutoFestivePost(post) ? 'cron-festival' : 'manual-festival'),
      }
      if (regenerateReferenceMediaIds.length > 0) {
        fields.reference_media_ids = regenerateReferenceMediaIds
      }
      const result = await api.generateSocialPostDraft(token, clientId, fields)
      setFestivePosts((prev) => [result.post, ...prev.filter((p) => p.id !== result.post.id && p.id !== post.id)])
      setRegeneratingPostId(null)
      setRegeneratePrompt('')
      setRegenerateReferenceMediaIds([])
      toast('Successfully regenerated festive post.', 'success')
    } catch (err) {
      toast(`Failed to regenerate: ${err.message}`, 'error')
    } finally {
      setGenerating(false)
    }
  }

  async function handleSaveCaption(postId) {
    setSavingCaption(true)
    try {
      const result = await api.editSocialPostQueueCaption(token, clientId, postId, editingCaptionText)
      setFestivePosts((prev) => prev.map((p) => (p.id === postId ? result.post : p)))
      setEditingCaptionPostId(null)
      toast('Caption updated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingCaption(false)
    }
  }

  async function handleSchedulePost(post) {
    if (post.publish_status === 'scheduled') {
      setQueueingPostId(post.id)
      try {
        await api.removeSocialPostFromQueue(token, clientId, post.id)
        toast('Removed from schedule.', 'success')
        await loadData()
      } catch (err) {
        toast(err.message, 'error')
      } finally {
        setQueueingPostId(null)
      }
    } else {
      setPostingPost(post)
      setPostCaption(post.brief?.caption || '')
      setTargetAction('schedule')
    }
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
      await loadData()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setPublishing(false)
    }
  }

  async function handleDeletePost() {
    if (!postToDelete) return
    const idToDelete = postToDelete
    setPostToDelete(null)
    setFestivePosts((prev) => prev.filter((p) => p.id !== idToDelete))
    try {
      await api.deleteSocialPost(token, clientId, idToDelete)
      toast('Draft deleted.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const statusLabel = (post, showAutoPublishHint) => {
    if (post.publish_status === 'published') return 'Published'
    if (post.publish_status === 'scheduled') return 'Scheduled'
    if (showAutoPublishHint && scheduleData?.festive_auto_publish) return 'Scheduled'
    return 'Generated'
  }

  const renderDraftCard = (post, { showAutoPublishHint }) => (
    <div key={post.id} className="card draft-item" style={{ display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: '500', fontSize: '0.9rem', color: '#334155' }}>
          {post.topic_text || 'Festive Post'}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="status-pill success">{statusLabel(post, showAutoPublishHint)}</span>
          <button
            className="btn btn-icon btn-sm text-danger"
            title="Delete post"
            onClick={() => setPostToDelete(post.id)}
            style={{ padding: '4px' }}
          >
            <i className="fa-solid fa-trash" />
          </button>
        </div>
      </div>

      <div className="draft-image" style={{ height: '300px', backgroundColor: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
        {post.image_url ? (
          <img src={assetUrl(post.image_url)} alt="Draft" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <i className="fa-solid fa-image" style={{ fontSize: '48px', color: '#cbd5e1' }} />
        )}

        {regeneratingPostId === post.id && (
          <div style={{
            position: 'absolute', inset: 0, backgroundColor: 'rgba(255,255,255,0.95)',
            display: 'flex', flexDirection: 'column', padding: '24px', zIndex: 10
          }}>
            <h4 style={{ margin: '0 0 16px 0', fontSize: '1rem', color: '#1e293b' }}>Regenerate Image</h4>
            <textarea
              className="form-input"
              rows={3}
              placeholder="Optional: Enter custom instructions for the new image..."
              value={regeneratePrompt}
              onChange={(e) => setRegeneratePrompt(e.target.value)}
              style={{ width: '100%', resize: 'none', marginBottom: '12px', fontSize: '0.9rem' }}
              disabled={generating}
            />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ marginBottom: '12px', alignSelf: 'flex-start' }}
              onClick={() => openReferenceModal('regenerate')}
              disabled={generating}
            >
              <i className="fa-solid fa-images" style={{ marginRight: '6px' }} />
              Choose Reference Posts ({regenerateReferenceMediaIds.length})
            </button>
            <div style={{ display: 'flex', gap: '8px', marginTop: 'auto' }}>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={() => handleConfirmRegenerate(post)}
                disabled={generating}
              >
                {generating ? 'Regenerating...' : 'Confirm'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setRegeneratingPostId(null)
                  setRegeneratePrompt('')
                  setRegenerateReferenceMediaIds([])
                }}
                disabled={generating}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="draft-content" style={{ padding: '20px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        {editingCaptionPostId === post.id ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: 1 }}>
            <textarea
              className="form-input"
              rows={5}
              value={editingCaptionText}
              onChange={(e) => setEditingCaptionText(e.target.value)}
              style={{ width: '100%', resize: 'none', fontSize: '0.9rem', flex: 1 }}
            />
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => handleSaveCaption(post.id)}
                disabled={savingCaption}
                style={{ flex: 1 }}
              >
                {savingCaption ? 'Saving...' : 'Save Caption'}
              </button>
              <button
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
            <p style={{ fontSize: '0.9rem', margin: 0, marginBottom: '20px', flex: 1, color: '#475569', lineHeight: '1.5' }}>
              {post.brief?.caption || <span className="text-muted">No caption</span>}
            </p>

            <div className="draft-actions" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <button
                className="btn btn-outline-primary btn-sm"
                onClick={() => {
                  setRegeneratingPostId(post.id)
                  setRegeneratePrompt('')
                  setRegenerateReferenceMediaIds([])
                }}
              >
                <i className="fa-solid fa-rotate" /> Regenerate
              </button>
              <button
                className="btn btn-outline-secondary btn-sm"
                onClick={() => {
                  setEditingCaptionPostId(post.id)
                  setEditingCaptionText(post.brief?.caption || '')
                }}
              >
                <i className="fa-solid fa-pen" /> Edit Caption
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleSchedulePost(post)}
                disabled={queueingPostId === post.id}
              >
                <i className="fa-solid fa-clock" /> {post.publish_status === 'scheduled' ? 'Unschedule' : (queueingPostId === post.id ? 'Scheduling...' : 'Schedule')}
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setPostingPost(post)
                  setPostCaption(post.brief?.caption || '')
                  setTargetAction('publish')
                }}
              >
                <i className="fa-solid fa-paper-plane" /> Post Now
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )

  const pickerIds = referencePickerFor === 'regenerate' ? regenerateReferenceMediaIds : selectedReferenceMediaIds
  const setPickerIds = referencePickerFor === 'regenerate' ? setRegenerateReferenceMediaIds : setSelectedReferenceMediaIds

  if (loading) return <div style={{ padding: '24px' }}>Loading...</div>

  return (
    <div className="client-social-festivals" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Breadcrumbs items={[{ label: 'Social Media', to: '..' }, { label: 'Festive Posts' }]} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 'bold' }}>Festive Posts</h1>
      </div>

      <div className="card" style={{ marginBottom: '32px', padding: '24px' }}>
        <h3 style={{ marginBottom: '16px' }}>Automatic Festive Publisher</h3>
        <p style={{ color: '#64748b', marginBottom: '16px', fontSize: '0.9rem' }}>
          When enabled, the system will automatically generate and publish posts for major holidays and festivals on the day of the event.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: savingSchedule ? 'wait' : 'pointer' }}>
            <div style={{
              position: 'relative',
              width: '44px',
              height: '24px',
              backgroundColor: scheduleData?.festive_auto_publish ? 'var(--primary, #3b82f6)' : '#cbd5e1',
              borderRadius: '24px',
              transition: 'background-color 0.3s',
              pointerEvents: savingSchedule ? 'none' : 'auto'
            }}>
              <div style={{
                position: 'absolute',
                top: '2px',
                left: scheduleData?.festive_auto_publish ? '22px' : '2px',
                width: '20px',
                height: '20px',
                backgroundColor: '#ffffff',
                borderRadius: '50%',
                transition: 'left 0.3s',
                boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
              }} />
            </div>
            <input
              type="checkbox"
              checked={scheduleData?.festive_auto_publish || false}
              onChange={(e) => handleToggleAutoPublish(e.target.checked, 'instagram')}
              style={{ display: 'none' }}
              disabled={savingSchedule}
            />
            <span style={{ color: '#334155', fontWeight: '500' }}><i className="fa-brands fa-instagram" style={{ color: '#E1306C', marginRight: '6px' }} /> Automatically publish to Instagram(For Auto-Generated Festive Posts Only)</span>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: savingSchedule ? 'wait' : 'pointer' }}>
            <div style={{
              position: 'relative',
              width: '44px',
              height: '24px',
              backgroundColor: scheduleData?.festive_facebook_auto_publish ? 'var(--primary, #3b82f6)' : '#cbd5e1',
              borderRadius: '24px',
              transition: 'background-color 0.3s',
              pointerEvents: savingSchedule ? 'none' : 'auto'
            }}>
              <div style={{
                position: 'absolute',
                top: '2px',
                left: scheduleData?.festive_facebook_auto_publish ? '22px' : '2px',
                width: '20px',
                height: '20px',
                backgroundColor: '#ffffff',
                borderRadius: '50%',
                transition: 'left 0.3s',
                boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
              }} />
            </div>
            <input
              type="checkbox"
              checked={scheduleData?.festive_facebook_auto_publish || false}
              onChange={(e) => handleToggleAutoPublish(e.target.checked, 'facebook')}
              style={{ display: 'none' }}
              disabled={savingSchedule}
            />
            <span style={{ color: '#334155', fontWeight: '500' }}><i className="fa-brands fa-facebook" style={{ color: '#1877F2', marginRight: '6px' }} /> Automatically publish to Facebook(For Auto-Generated Festive Posts Only)</span>
          </label>
        </div>
      </div>

      <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
        Auto-Generated Festive Drafts
      </h2>

      {autoPosts.length === 0 ? (
        <div className="card text-center" style={{ padding: '48px 24px', color: 'var(--text-secondary)', marginBottom: '40px' }}>
          <i className="fa-solid fa-gift" style={{ fontSize: '32px', marginBottom: '16px' }} />
          <p>No festive posts generated yet.</p>
        </div>
      ) : (
        <div style={{ marginBottom: '40px' }}>
          <div className="saved-posts-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '24px' }}>
            {autoSlice.map((post) => renderDraftCard(post, { showAutoPublishHint: true }))}
          </div>
          <Pagination page={autoPage} totalPages={autoTotalPages} onChange={setAutoPage} />
        </div>
      )}

      <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
        Manual Festive Generation
      </h2>
      <div className="card" style={{ marginBottom: '24px', padding: '24px' }}>
        <p style={{ color: '#64748b', marginBottom: '12px', fontSize: '0.9rem' }}>
          Type the festival name and any extra notes. Optional Instagram references follow the same style as Generate Post.
        </p>
        <textarea
          className="form-input"
          rows={4}
          placeholder="e.g. Ganesh Chaturthi — festive greeting for your audience"
          value={manualPrompt}
          onChange={(e) => setManualPrompt(e.target.value)}
          style={{ width: '100%', marginBottom: '12px', fontSize: '0.95rem', resize: 'vertical' }}
          disabled={manualGenerating}
        />
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => openReferenceModal('generate')}
            disabled={manualGenerating}
          >
            <i className="fa-solid fa-images" style={{ marginRight: '6px' }} />
            Choose Reference Posts ({selectedReferenceMediaIds.length})
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleManualGenerate}
            disabled={manualGenerating || !manualPrompt.trim()}
          >
            {manualGenerating ? 'Generating...' : 'Generate'}
          </button>
        </div>
      </div>

      {manualPosts.length === 0 ? (
        <div className="card text-center" style={{ padding: '48px 24px', color: 'var(--text-secondary)' }}>
          <i className="fa-solid fa-pen-to-square" style={{ fontSize: '32px', marginBottom: '16px' }} />
          <p>No manually generated festive posts yet.</p>
        </div>
      ) : (
        <>
          <div className="saved-posts-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '24px' }}>
            {manualSlice.map((post) => renderDraftCard(post, { showAutoPublishHint: false }))}
          </div>
          <Pagination page={manualPage} totalPages={manualTotalPages} onChange={setManualPage} />
        </>
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
                {instagramMedia.filter((m) => m.media_type === 'IMAGE' || m.media_type === 'CAROUSEL_ALBUM').map((media) => {
                  const isSelected = pickerIds.includes(media.id)
                  return (
                    <div
                      key={media.id}
                      onClick={() => {
                        if (isSelected) {
                          setPickerIds((prev) => prev.filter((id) => id !== media.id))
                        } else {
                          setPickerIds((prev) => [...prev, media.id])
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
                Confirm Selections ({pickerIds.length})
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
                      else setPublishTargets(publishTargets.filter((t) => t !== 'instagram'))
                    }}
                  />
                  <span><i className="fa-brands fa-instagram" style={{ color: '#E1306C' }} /> Instagram</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={publishTargets.includes('facebook')}
                    onChange={(e) => {
                      if (e.target.checked) setPublishTargets([...publishTargets, 'facebook'])
                      else setPublishTargets(publishTargets.filter((t) => t !== 'facebook'))
                    }}
                  />
                  <span><i className="fa-brands fa-facebook" style={{ color: '#1877F2' }} /> Facebook</span>
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
      <ConfirmModal
        isOpen={!!postToDelete}
        title="Delete Post"
        message="Are you sure you want to delete this post? This cannot be undone."
        onCancel={() => setPostToDelete(null)}
        onConfirm={handleDeletePost}
      />
    </div>
  )
}
