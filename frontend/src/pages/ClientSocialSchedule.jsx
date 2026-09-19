import React, { useState, useEffect, useCallback } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import ConfirmModal from '../components/ConfirmModal'

function assetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
  return `${base}${path}`
}

const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function ClientSocialSchedule() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  
  const [frequency, setFrequency] = useState('off')
  const [selectedDays, setSelectedDays] = useState([])
  const [autoFallback, setAutoFallback] = useState(false)
  const [facebookAutoPublish, setFacebookAutoPublish] = useState(false)
  const [festiveAutoPublish, setFestiveAutoPublish] = useState(false)

  const [queuedPosts, setQueuedPosts] = useState([])
  const [festivePosts, setFestivePosts] = useState([])
  const [editingPostId, setEditingPostId] = useState(null)
  const [editingCaption, setEditingCaption] = useState('')
  const [savingCaption, setSavingCaption] = useState(false)
  
  const [postToDelete, setPostToDelete] = useState(null)
  const [postToRemoveFromQueue, setPostToRemoveFromQueue] = useState(null)
  
  // Drag and Drop state
  const [draggedIdx, setDraggedIdx] = useState(null)
  
  const [showTooltip, setShowTooltip] = useState(false)
  const [isEditing, setIsEditing] = useState(true)
  const [originalConfig, setOriginalConfig] = useState(null)
  const [postsPerDay, setPostsPerDay] = useState(1)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [scheduleRes, queueRes, festiveRes] = await Promise.all([
        api.getSocialSchedule(token, clientId),
        api.listSocialPostQueue(token, clientId),
        api.getFestivePosts(token, clientId)
      ])
      
      if (scheduleRes && Object.keys(scheduleRes).length > 0) {
        setIsEditing(false)
      } else {
        setIsEditing(true)
      }
      setFrequency(scheduleRes.frequency || 'off')
      setSelectedDays(scheduleRes.selected_days || [])
      setAutoFallback(!!scheduleRes.auto_fallback)
      setPostsPerDay(scheduleRes.posts_per_day || 1)
      setFestiveAutoPublish(!!scheduleRes.festive_auto_publish)
      setFacebookAutoPublish(!!scheduleRes.facebook_auto_publish)
      setOriginalConfig({
        frequency: scheduleRes.frequency || 'off',
        selectedDays: scheduleRes.selected_days || [],
        autoFallback: !!scheduleRes.auto_fallback,
        postsPerDay: scheduleRes.posts_per_day || 1,
        festiveAutoPublish: !!scheduleRes.festive_auto_publish,
        facebookAutoPublish: !!scheduleRes.facebook_auto_publish
      })
      setQueuedPosts(queueRes.posts || [])
      setFestivePosts(festiveRes.posts || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, toast])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSaveSchedule = async () => {
    setSaving(true)
    try {
      await api.saveSocialSchedule(token, clientId, frequency, selectedDays, autoFallback, postsPerDay, festiveAutoPublish, facebookAutoPublish)
      setOriginalConfig({ frequency, selectedDays, autoFallback, postsPerDay, festiveAutoPublish, facebookAutoPublish })
      setIsEditing(false)
      toast('Schedule saved successfully.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleCancelEdit = () => {
    if (originalConfig) {
      setFrequency(originalConfig.frequency)
      setSelectedDays(originalConfig.selectedDays)
      setAutoFallback(originalConfig.autoFallback)
      setPostsPerDay(originalConfig.postsPerDay || 1)
      setFestiveAutoPublish(originalConfig.festiveAutoPublish)
      setFacebookAutoPublish(originalConfig.facebookAutoPublish || false)
    }
    setIsEditing(false)
  }

  const handleDayToggle = (day) => {
    setSelectedDays(prev => {
      if (prev.includes(day)) {
        return prev.filter(d => d !== day)
      }
      const limit = frequency === 'once_a_week' ? 1 : 2;
      const next = [...prev, day];
      if (next.length > limit) {
        return next.slice(next.length - limit);
      }
      return next;
    })
  }

  const handleRemoveFromQueue = async () => {
    if (!postToDelete) return
    const idToDelete = postToDelete
    setPostToDelete(null)
    setQueuedPosts(queuedPosts.filter(p => p.id !== idToDelete))
    try {
      await api.removeSocialPostFromQueue(token, clientId, idToDelete)
      toast('Removed from schedule.', 'success')
    } catch (err) {
      toast(err.message, 'error')
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
    
    if (newTargets.length === 0) {
      setPostToRemoveFromQueue({ post, newTargets })
      return
    }
    
    executeToggleTarget(post, newTargets)
  }

  const executeToggleTarget = async (post, newTargets) => {
    // Optimistic update
    const updatedPost = { ...post, publish_targets: newTargets }
    if (newTargets.length === 0) {
      setQueuedPosts(queuedPosts.filter(p => p.id !== post.id))
    } else {
      setQueuedPosts(queuedPosts.map(p => p.id === post.id ? updatedPost : p))
    }
    
    try {
      await api.updateSocialPostTargets(token, clientId, post.id, newTargets)
      if (newTargets.length === 0) {
        toast('Post removed from queue.', 'success')
      }
    } catch (err) {
      toast(err.message, 'error')
      loadData()
    } finally {
      if (postToRemoveFromQueue) {
        setPostToRemoveFromQueue(null)
      }
    }
  }

  const handleSaveCaption = async (postId) => {
    if (!editingCaption.trim()) return toast('Caption cannot be empty', 'error')
    setSavingCaption(true)
    try {
      const result = await api.editSocialPostQueueCaption(token, clientId, postId, editingCaption)
      setQueuedPosts(queuedPosts.map(p => p.id === postId ? result.post : p))
      setEditingPostId(null)
      toast('Caption updated.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingCaption(false)
    }
  }

  const handleDragStart = (e, index) => {
    setDraggedIdx(index)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e, index) => {
    e.preventDefault()
  }

  const handleDrop = async (e, dropIdx) => {
    e.preventDefault()
    if (draggedIdx === null || draggedIdx === dropIdx) {
      setDraggedIdx(null)
      return
    }

    const newQueue = [...queuedPosts]
    const draggedItem = newQueue[draggedIdx]
    newQueue.splice(draggedIdx, 1)
    newQueue.splice(dropIdx, 0, draggedItem)
    setQueuedPosts(newQueue)
    setDraggedIdx(null)

    const orderedIds = newQueue.map(p => p.id)
    try {
      await api.reorderSocialPostQueue(token, clientId, orderedIds)
    } catch (err) {
      toast('Failed to save queue order: ' + err.message, 'error')
    }
  }

  if (loading) {
    return (
      <div className="loading-overlay inline-loading">
        <div className="spinner-loader" />
      </div>
    )
  }

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: 'Publishing Schedule' },
            ]}
          />
          <h1>Publishing Schedule</h1>
          <p>Set up when you want your posts to go out automatically on Instagram.</p>
        </div>
      </header>

      <section className="card" style={{ padding: '32px', marginBottom: '24px', backgroundColor: '#ffffff', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)', border: '1px solid #e2e8f0', borderRadius: '12px' }}>
        <h3 style={{ marginBottom: '24px', fontSize: '1.25rem', color: '#0f172a', fontWeight: '600' }}>Schedule Settings</h3>
        
        <div className="form-group" style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label className="form-label" style={{ fontWeight: '500', color: '#334155', margin: 0 }}>Frequency</label>
          <select 
            className="form-control" 
            style={{ padding: '10px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', outline: 'none', width: '250px', backgroundColor: isEditing ? '#fff' : '#f1f5f9', cursor: isEditing ? 'auto' : 'not-allowed' }}
            disabled={!isEditing}
            value={frequency} 
            onChange={(e) => {
              setFrequency(e.target.value)
              if (e.target.value === 'off' || e.target.value === 'daily' || e.target.value === 'weekdays') {
                setSelectedDays([])
              }
            }}
          >
            <option value="off">Off (Scheduler disabled)</option>
            <option value="daily">Daily</option>
            <option value="weekdays">Weekdays (Mon-Fri)</option>
            <option value="once_a_week">Once a Week</option>
            <option value="twice_a_week">Twice a Week</option>
          </select>
        </div>

        <div className="form-group" style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label className="form-label" style={{ fontWeight: '500', color: '#334155', margin: 0 }}>Number of Posts per day you want to Publish</label>
          <div style={{ display: 'flex', alignItems: 'center', width: '250px', backgroundColor: isEditing ? '#fff' : '#f1f5f9', borderRadius: '8px', border: '1px solid #cbd5e1', overflow: 'hidden', opacity: isEditing ? 1 : 0.7 }}>
            <button
              type="button"
              onClick={() => isEditing && setPostsPerDay(Math.max(1, postsPerDay - 1))}
              disabled={!isEditing || postsPerDay <= 1}
              style={{ padding: '10px 16px', backgroundColor: '#f8fafc', border: 'none', borderRight: '1px solid #cbd5e1', cursor: isEditing && postsPerDay > 1 ? 'pointer' : 'not-allowed', color: '#334155', fontWeight: 'bold' }}
            >
              -
            </button>
            <div style={{ flex: 1, textAlign: 'center', padding: '10px 0', fontWeight: '500', color: '#0f172a' }}>
              {postsPerDay}
            </div>
            <button
              type="button"
              onClick={() => isEditing && setPostsPerDay(postsPerDay + 1)}
              disabled={!isEditing}
              style={{ padding: '10px 16px', backgroundColor: '#f8fafc', border: 'none', borderLeft: '1px solid #cbd5e1', cursor: isEditing ? 'pointer' : 'not-allowed', color: '#334155', fontWeight: 'bold' }}
            >
              +
            </button>
          </div>
        </div>

        {(frequency === 'once_a_week' || frequency === 'twice_a_week') && (
          <div className="form-group" style={{ marginBottom: '24px' }}>
            <label className="form-label" style={{ fontWeight: '500', color: '#334155', display: 'flex', alignItems: 'center' }}>
              Select {frequency === 'once_a_week' ? 'Day' : 'Days'} 
              <span className="text-muted" style={{ fontWeight: 'normal', marginLeft: '8px' }}>
                (Please select exactly {frequency === 'once_a_week' ? '1 day' : '2 days'})
              </span>
            </label>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '12px' }}>
              {DAYS_OF_WEEK.map(day => {
                const isSelected = selectedDays.includes(day);
                const isDisabled = !isEditing;
                return (
                  <label key={day} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    padding: '8px 16px',
                    borderRadius: '20px',
                    backgroundColor: isSelected ? 'var(--primary, #3b82f6)' : '#f1f5f9',
                    color: isSelected ? '#ffffff' : '#64748b',
                    border: `1px solid ${isSelected ? 'var(--primary, #3b82f6)' : '#e2e8f0'}`,
                    cursor: isDisabled ? 'not-allowed' : 'pointer',
                    opacity: isDisabled ? 0.6 : 1,
                    transition: 'all 0.2s',
                    fontWeight: isSelected ? '600' : 'normal',
                    userSelect: 'none'
                  }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleDayToggle(day)}
                      disabled={isDisabled}
                      style={{ display: 'none' }}
                    />
                    {day}
                  </label>
                )
              })}
            </div>
          </div>
        )}

        <div className="form-group" style={{ marginBottom: '32px', marginTop: '32px', paddingTop: '24px', borderTop: '1px solid #e2e8f0' }}>
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', fontWeight: '500', color: '#334155' }}>
            Automatic Publisher
            <div 
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
            >
              <span 
                className="badge" 
                style={{ 
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '18px', 
                  height: '18px',
                  borderRadius: '50%', 
                  cursor: 'help', 
                  backgroundColor: '#e2e8f0', 
                  color: '#475569',
                  fontSize: '11px',
                  fontWeight: 'bold'
                }}
              >
                i
              </span>
              {showTooltip && (
                <div style={{
                  position: 'absolute',
                  bottom: '100%',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  marginBottom: '8px',
                  backgroundColor: '#1e293b',
                  color: '#f8fafc',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 'normal',
                  width: '260px',
                  textAlign: 'center',
                  zIndex: 10,
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                }}>
                  When enabled, if your scheduled post queue runs empty, the system will automatically find your newest, un-published generated draft and publish it at the scheduled time to ensure you never miss a post.
                  <div style={{
                    position: 'absolute',
                    bottom: '-4px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 0,
                    height: 0,
                    borderLeft: '4px solid transparent',
                    borderRight: '4px solid transparent',
                    borderTop: '4px solid #1e293b'
                  }} />
                </div>
              )}
            </div>
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: isEditing ? 'pointer' : 'not-allowed', opacity: isEditing ? 1 : 0.6 }}>
              <div style={{
                position: 'relative',
                width: '44px',
                height: '24px',
                backgroundColor: autoFallback ? 'var(--primary, #3b82f6)' : '#cbd5e1',
                borderRadius: '24px',
                transition: 'background-color 0.3s',
                pointerEvents: isEditing ? 'auto' : 'none'
              }}>
                <div style={{
                  position: 'absolute',
                  top: '2px',
                  left: autoFallback ? '22px' : '2px',
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
                checked={autoFallback} 
                onChange={(e) => setAutoFallback(e.target.checked)} 
                style={{ display: 'none' }}
              />
              <span style={{ color: '#334155', fontWeight: '500' }}><i className="fa-brands fa-instagram" style={{ color: '#E1306C', marginRight: '6px' }} /> Automatically publish newest drafts to Instagram if queue is empty</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: isEditing ? 'pointer' : 'not-allowed', opacity: isEditing ? 1 : 0.6 }}>
              <div style={{
                position: 'relative',
                width: '44px',
                height: '24px',
                backgroundColor: facebookAutoPublish ? 'var(--primary, #3b82f6)' : '#cbd5e1',
                borderRadius: '24px',
                transition: 'background-color 0.3s',
                pointerEvents: isEditing ? 'auto' : 'none'
              }}>
                <div style={{
                  position: 'absolute',
                  top: '2px',
                  left: facebookAutoPublish ? '22px' : '2px',
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
                checked={facebookAutoPublish} 
                onChange={(e) => setFacebookAutoPublish(e.target.checked)} 
                style={{ display: 'none' }}
              />
              <span style={{ color: '#334155', fontWeight: '500' }}><i className="fa-brands fa-facebook" style={{ color: '#1877F2', marginRight: '6px' }} /> Automatically publish newest drafts to Facebook if queue is empty</span>
            </label>
          </div>
        </div>


        {isEditing ? (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button 
              type="button" 
              style={{ backgroundColor: '#059669', color: '#fff', border: 'none', padding: '10px 24px', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', fontSize: '1rem', transition: 'background-color 0.2s' }}
              onClick={handleSaveSchedule}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
            <button 
              type="button" 
              style={{ backgroundColor: '#e11d48', color: '#fff', border: 'none', padding: '10px 24px', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', fontSize: '1rem', transition: 'background-color 0.2s' }}
              onClick={handleCancelEdit}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button 
            type="button" 
            className="btn btn-primary" 
            onClick={() => setIsEditing(true)}
          >
            Change Settings
          </button>
        )}
      </section>

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3>Queue Manager</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              onClick={() => {
                api.listSocialPostQueue(token, clientId)
                  .then(queueRes => {
                    setQueuedPosts(queueRes.posts || []);
                  })
                  .catch(err => toast(err.message, 'error'));
              }}
              className="btn btn-outline-secondary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '20px', padding: '6px 12px', fontSize: '0.85rem' }}
              disabled={loading}
              title="Refresh Queue"
            >
              <i className="fa-solid fa-rotate-right"></i> Sync Queue
            </button>
            <span className="text-muted">{queuedPosts.length} posts scheduled</span>
          </div>
        </div>

        {queuedPosts.length === 0 ? (
          <div className="card text-center" style={{ padding: '48px 24px', color: 'var(--text-secondary)' }}>
            <i className="fa-solid fa-list-check" style={{ fontSize: '32px', marginBottom: '16px' }}></i>
            <p>Your queue is empty.</p>
            <p style={{ fontSize: '0.9rem' }}>Go to "Generate Posts" to schedule upcoming posts.</p>
          </div>
        ) : (
          <div className="queue-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
            {queuedPosts.map((post, idx) => (
              <div 
                key={post.id} 
                className="card queue-item" 
                draggable
                onDragStart={(e) => handleDragStart(e, idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDrop={(e) => handleDrop(e, idx)}
                style={{ 
                  display: 'flex', 
                  flexDirection: 'column',
                  padding: 0,
                  overflow: 'hidden',
                  cursor: draggedIdx === idx ? 'grabbing' : 'grab',
                  opacity: draggedIdx === idx ? 0.5 : 1,
                  boxShadow: draggedIdx === idx ? 'none' : '0 1px 3px rgba(0,0,0,0.1)',
                  transition: 'transform 0.1s ease',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div style={{ padding: '8px 12px', backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: '500', fontSize: '0.85rem' }}>
                  <span><i className="fa-solid fa-grip-vertical" style={{ marginRight: '8px', color: '#94a3b8' }}></i> #{idx + 1} in Queue</span>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button
                      type="button"
                      onClick={() => handleToggleTarget(post, 'facebook')}
                      title={(post.publish_targets || []).includes('facebook') ? "Scheduled for Facebook (Click to Unschedule)" : "Not scheduled for Facebook (Click to Schedule)"}
                      style={{
                        background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                        color: (post.publish_targets || []).includes('facebook') ? '#1877F2' : '#cbd5e1',
                        transition: 'color 0.2s', fontSize: '16px'
                      }}
                    >
                      <i className="fa-brands fa-facebook"></i>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleToggleTarget(post, 'instagram')}
                      title={(post.publish_targets || []).includes('instagram') ? "Scheduled for Instagram (Click to Unschedule)" : "Not scheduled for Instagram (Click to Schedule)"}
                      style={{
                        background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                        color: (post.publish_targets || []).includes('instagram') ? '#E1306C' : '#cbd5e1',
                        transition: 'color 0.2s', fontSize: '16px'
                      }}
                    >
                      <i className="fa-brands fa-instagram"></i>
                    </button>
                  </div>
                </div>
                
                <div style={{ height: '280px', backgroundColor: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                  {post.image_url ? (
                    <img src={assetUrl(post.image_url)} alt="Draft" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <i className="fa-solid fa-image" style={{ fontSize: '32px', color: '#cbd5e1' }} />
                  )}
                </div>
                
                <div style={{ padding: '16px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                  {editingPostId === post.id ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                      <textarea
                        className="form-input"
                        rows={4}
                        value={editingCaption}
                        onChange={(e) => setEditingCaption(e.target.value)}
                        style={{ width: '100%', resize: 'none', fontSize: '0.85rem', flex: 1 }}
                      />
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button className="btn btn-primary btn-xs" onClick={() => handleSaveCaption(post.id)} disabled={savingCaption}>
                          {savingCaption ? 'Saving...' : 'Save'}
                        </button>
                        <button className="btn btn-secondary btn-xs" onClick={() => setEditingPostId(null)} disabled={savingCaption}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p style={{ fontSize: '0.85rem', margin: 0, marginBottom: '12px', flex: 1, color: 'var(--text-color)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {post.brief?.caption || <span className="text-muted">No caption</span>}
                      </p>
                      
                      <div style={{ display: 'flex', gap: '8px', marginTop: 'auto' }}>
                        <button 
                          className="btn btn-secondary btn-sm" 
                          style={{ flex: 1 }}
                          onClick={() => {
                            setEditingPostId(post.id)
                            setEditingCaption(post.brief?.caption || '')
                          }}
                        >
                          Edit Caption
                        </button>
                        <button
                          className="btn btn-icon btn-sm text-danger"
                          onClick={() => setPostToDelete(post.id)}
                          title="Remove from Queue"
                          style={{ padding: '4px' }}
                        >
                          <i className="fa-solid fa-trash"></i>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
      <ConfirmModal
        isOpen={!!postToDelete}
        title="Remove from Queue"
        message="Are you sure you want to remove this post from the queue? It will be moved back to your drafts."
        confirmText="Remove"
        onCancel={() => setPostToDelete(null)}
        onConfirm={handleRemoveFromQueue}
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
