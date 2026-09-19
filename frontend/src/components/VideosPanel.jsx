import { useState, useMemo } from 'react'

const DEFAULT_THUMB =
  'https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?auto=format&fit=crop&w=80&q=80'

export default function VideosPanel({ videos = [], onSync, onUpdate, isClientLevel = false }) {
  const [syncing, setSyncing] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [sortBy, setSortBy] = useState('views') // 'views', 'likes', 'comments', 'date', 'title', 'channel'
  const [sortOrder, setSortOrder] = useState('desc') // 'asc', 'desc'
  const [videoType, setVideoType] = useState('all') // 'all', 'video', 'short'
  const [selectedChannel, setSelectedChannel] = useState('all')

  // Editing state for expandable sections
  const [expandedVideoId, setExpandedVideoId] = useState(null)
  const [editingNotes, setEditingNotes] = useState('')
  const [editingMetadata, setEditingMetadata] = useState([]) // array of { key: '', value: '' }
  const [savingId, setSavingId] = useState(null)

  const renderSortIcon = (field) => {
    if (sortBy !== field) return null
    return (
      <i
        className={`fa-solid ${sortOrder === 'asc' ? 'fa-arrow-up-short-wide' : 'fa-arrow-down-wide-short'}`}
        style={{ marginLeft: '6px', color: '#4f46e5' }}
      />
    )
  }

  const handleHeaderClick = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      if (field === 'title' || field === 'channel') {
        setSortOrder('asc')
      } else {
        setSortOrder('desc')
      }
    }
  }

  const handleSortChange = (value) => {
    setSortBy(value)
    if (value === 'title' || value === 'channel') {
      setSortOrder('asc')
    } else {
      setSortOrder('desc')
    }
  }

  async function handleSync() {
    setSyncing(true)
    try {
      const count = await onSync()
      alert(`Successfully synced ${count} videos and their stats!`)
    } catch (err) {
      alert(`Error syncing videos:\n\n${err.message}`)
    } finally {
      setSyncing(false)
    }
  }

  // Toggle video details expand/collapse
  function toggleExpand(video) {
    if (expandedVideoId === video.id) {
      setExpandedVideoId(null)
    } else {
      setExpandedVideoId(video.id)
      setEditingNotes(video.notes || '')
      
      const meta = video.metadata_fields || {}
      setEditingMetadata(
        Object.entries(meta).map(([key, value]) => ({ key, value }))
      )
    }
  }

  // Save changes to backend
  async function handleSave(video) {
    if (!onUpdate) return
    setSavingId(video.id)
    try {
      // Convert list of { key, value } back to object
      const metaObj = {}
      editingMetadata.forEach(({ key, value }) => {
        const trimmedKey = key.trim()
        if (trimmedKey) {
          metaObj[trimmedKey] = value.trim()
        }
      })

      await onUpdate(video.id, video.channelId, editingNotes.trim(), metaObj)
      setExpandedVideoId(null)
    } catch (err) {
      alert(`Failed to save changes: ${err.message}`)
    } finally {
      setSavingId(null)
    }
  }

  // Get unique channels list from videos (if in Client Level)
  const uniqueChannels = useMemo(() => {
    const channels = new Map()
    videos.forEach((v) => {
      if (v.channelId && v.channelTitle) {
        channels.set(v.channelId, v.channelTitle)
      }
    })
    return Array.from(channels.entries()).map(([id, title]) => ({ id, title }))
  }, [videos])

  // Filter and Sort videos
  const processedVideos = useMemo(() => {
    let result = [...videos]

    // 1. Search Filter
    if (searchTerm.trim()) {
      const query = searchTerm.toLowerCase()
      result = result.filter(
        (v) =>
          v.title.toLowerCase().includes(query) ||
          (v.channelTitle && v.channelTitle.toLowerCase().includes(query))
      )
    }

    // 2. Channel Filter (only relevant if isClientLevel)
    if (isClientLevel && selectedChannel !== 'all') {
      result = result.filter((v) => v.channelId === selectedChannel)
    }

    // 3. Video Type Filter (segregation of videos and shorts)
    if (videoType === 'video') {
      result = result.filter((v) => !v.is_short)
    } else if (videoType === 'short') {
      result = result.filter((v) => v.is_short)
    }

    // 4. Sorting
    result.sort((a, b) => {
      let valA, valB
      if (sortBy === 'views') {
        valA = Number(a.view_count || 0)
        valB = Number(b.view_count || 0)
      } else if (sortBy === 'likes') {
        valA = Number(a.like_count || 0)
        valB = Number(b.like_count || 0)
      } else if (sortBy === 'comments') {
        valA = Number(a.comment_count || 0)
        valB = Number(b.comment_count || 0)
      } else if (sortBy === 'date') {
        valA = new Date(a.published_at || 0).getTime()
        valB = new Date(b.published_at || 0).getTime()
      } else if (sortBy === 'title') {
        const titleA = (a.title || '').toLowerCase()
        const titleB = (b.title || '').toLowerCase()
        return sortOrder === 'asc' ? titleA.localeCompare(titleB) : titleB.localeCompare(titleA)
      } else if (sortBy === 'channel') {
        const channelA = (a.channelTitle || '').toLowerCase()
        const channelB = (b.channelTitle || '').toLowerCase()
        return sortOrder === 'asc' ? channelA.localeCompare(channelB) : channelB.localeCompare(channelA)
      } else {
        return 0
      }

      if (sortOrder === 'asc') {
        return valA - valB
      } else {
        return valB - valA
      }
    })

    return result
  }, [videos, searchTerm, sortBy, sortOrder, selectedChannel, videoType, isClientLevel])

  return (
    <div className="videos-panel animate-fade-in">
      <div className="videos-header-row">
        <div className="videos-summary-box">
          <h2>Videos & Shorts Library</h2>
          <p>
            {isClientLevel
              ? `Showing consolidated library across ${uniqueChannels.length} channel(s)`
              : 'All synced videos and shorts from your selected YouTube channel.'}
          </p>
        </div>
        <button
          className={`btn btn-primary sync-btn-glow ${syncing ? 'spinning' : ''}`}
          onClick={handleSync}
          disabled={syncing}
        >
          <i className="fa-solid fa-arrows-rotate" />
          <span>{syncing ? 'Syncing Library...' : 'Sync video stats'}</span>
        </button>
      </div>

      {/* Filter and search bar */}
      <div className="table-controls-card card mb-6">
        <div className="controls-grid">
          <div className="search-box">
            <i className="fa-solid fa-magnifying-glass search-icon" />
            <input
              type="text"
              placeholder="Search video titles or description..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="search-clear-btn" onClick={() => setSearchTerm('')}>
                <i className="fa-solid fa-circle-xmark" />
              </button>
            )}
          </div>

          <div className="filters-right">
            {isClientLevel && uniqueChannels.length > 0 && (
              <div className="filter-group">
                <label htmlFor="channel-filter">Channel</label>
                <select
                  id="channel-filter"
                  className="filter-select"
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                >
                  <option value="all">All Channels</option>
                  {uniqueChannels.map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      {ch.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="filter-group">
              <label htmlFor="type-filter">Type</label>
              <select
                id="type-filter"
                className="filter-select"
                value={videoType}
                onChange={(e) => setVideoType(e.target.value)}
              >
                <option value="all">All Types</option>
                <option value="video">Long Videos</option>
                <option value="short">Shorts</option>
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="sort-filter">Sort by</label>
              <select
                id="sort-filter"
                className="filter-select"
                value={sortBy}
                onChange={(e) => handleSortChange(e.target.value)}
              >
                <option value="views">Most Viewed</option>
                <option value="likes">Most Liked</option>
                <option value="comments">Most Commented</option>
                <option value="date">Publish Date</option>
                <option value="title">Title (A-Z)</option>
                {isClientLevel && <option value="channel">Channel (A-Z)</option>}
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="table-section card">
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th style={{ width: '80px' }} />
                <th
                  onClick={() => handleHeaderClick('title')}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                  title="Click to sort by title"
                >
                  Video details {renderSortIcon('title')}
                </th>
                {isClientLevel && (
                  <th
                    onClick={() => handleHeaderClick('channel')}
                    style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                    title="Click to sort by channel"
                  >
                    YouTube Channel {renderSortIcon('channel')}
                  </th>
                )}
                <th
                  onClick={() => handleHeaderClick('date')}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                  title="Click to sort by publish date"
                >
                  Published Date {renderSortIcon('date')}
                </th>
                <th
                  onClick={() => handleHeaderClick('views')}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                  title="Click to sort by views"
                >
                  Views {renderSortIcon('views')}
                </th>
                <th
                  onClick={() => handleHeaderClick('likes')}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                  title="Click to sort by likes"
                >
                  Likes {renderSortIcon('likes')}
                </th>
                <th
                  onClick={() => handleHeaderClick('comments')}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                  title="Click to sort by comments"
                >
                  Comments {renderSortIcon('comments')}
                </th>
                <th style={{ width: '90px', textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {processedVideos.length === 0 ? (
                <tr>
                  <td colSpan={isClientLevel ? 9 : 8} className="text-center text-muted py-12">
                    <i className="fa-solid fa-film block mb-2" style={{ fontSize: '24px', opacity: 0.5 }} />
                    <p className="font-semibold mb-1">No videos found</p>
                    <p className="text-xs">
                      {videos.length === 0
                        ? 'Click Sync video stats to fetch videos from YouTube.'
                        : 'Try resetting your search query or filters.'}
                    </p>
                  </td>
                </tr>
              ) : (
                processedVideos.map((v) => {
                  const thumbUrl = v.thumbnail_url || DEFAULT_THUMB
                  const pubDate = new Date(v.published_at).toLocaleDateString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })
                  const hasMeta = v.metadata_fields && Object.keys(v.metadata_fields).length > 0
                  
                  return (
                    <>
                      <tr key={v.id} className="video-row-hover">
                        <td>
                          <img
                            src={thumbUrl}
                            alt="thumbnail"
                            className="video-thumbnail"
                            onError={(e) => {
                              e.currentTarget.src = DEFAULT_THUMB
                            }}
                          />
                        </td>
                        <td>
                          <div className="video-title-container">
                            <span className="video-title" title={v.title}>
                              {v.title}
                            </span>
                            <span className="video-id">ID: {v.id}</span>
                            
                            {/* Badges for segregation & info */}
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                              {v.is_short ? (
                                <span style={{ fontSize: '11px', background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a', padding: '1px 6px', borderRadius: '4px', fontWeight: '600', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                  <i className="fa-solid fa-bolt" /> Short
                                </span>
                              ) : (
                                <span style={{ fontSize: '11px', background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe', padding: '1px 6px', borderRadius: '4px', fontWeight: '600', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                  <i className="fa-solid fa-video" /> Video
                                </span>
                              )}
                              
                              {v.notes && (
                                <span style={{ fontSize: '11px', background: '#f8fafc', color: '#475569', border: '1px solid #e2e8f0', padding: '1px 6px', borderRadius: '4px', display: 'inline-flex', alignItems: 'center', gap: '3px' }} title={v.notes}>
                                  <i className="fa-solid fa-note-sticky" /> Notes
                                </span>
                              )}

                              {hasMeta && (
                                <span style={{ fontSize: '11px', background: '#faf5ff', color: '#6b21a8', border: '1px solid #e9d5ff', padding: '1px 6px', borderRadius: '4px', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                  <i className="fa-solid fa-tags" /> {Object.keys(v.metadata_fields).length} Meta
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        {isClientLevel && (
                          <td>
                            <span className="video-channel-badge">
                              <i className="fa-solid fa-layer-group" />
                              {v.channelTitle || 'Unknown Channel'}
                            </span>
                          </td>
                        )}
                        <td>
                          <span className="text-secondary">{pubDate}</span>
                        </td>
                        <td>
                          <strong className="view-highlight">{Number(v.view_count).toLocaleString()}</strong>
                        </td>
                        <td>
                          <span className="likes-badge">
                            <i className="fa-solid fa-thumbs-up" />
                            {Number(v.like_count).toLocaleString()}
                          </span>
                        </td>
                        <td>
                          <span className="comments-badge">
                            <i className="fa-solid fa-comment" />
                            {Number(v.comment_count).toLocaleString()}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', alignItems: 'center' }}>
                            <a
                              href={v.is_short ? (v.short_link || `https://www.youtube.com/shorts/${v.id}`) : `https://www.youtube.com/watch?v=${v.id}`}
                              target="_blank"
                              rel="noreferrer"
                              className="action-watch-btn"
                              style={{
                                color: v.is_short ? '#b45309' : '#ef4444',
                                background: v.is_short ? '#fffbeb' : '#fef2f2',
                                borderColor: v.is_short ? '#fde68a' : '#fee2e2',
                              }}
                              title={v.is_short ? 'Watch Short on YouTube' : 'Watch on YouTube'}
                            >
                              <i className={v.is_short ? 'fa-solid fa-bolt' : 'fa-brands fa-youtube'} />
                            </a>
                            {onUpdate && (
                              <button
                                type="button"
                                onClick={() => toggleExpand(v)}
                                className="action-edit-btn"
                                style={{
                                  color: '#4f46e5',
                                  width: '32px',
                                  height: '32px',
                                  borderRadius: '50%',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  background: expandedVideoId === v.id ? '#4f46e5' : '#f5f3ff',
                                  color: expandedVideoId === v.id ? 'white' : '#4f46e5',
                                  border: 'none',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s',
                                }}
                                title="Edit notes & custom metadata"
                              >
                                <i className={expandedVideoId === v.id ? 'fa-solid fa-chevron-up' : 'fa-solid fa-pen-to-square'} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expandable row for editing notes & custom metadata */}
                      {expandedVideoId === v.id && (
                        <tr key={`${v.id}-expanded`} style={{ background: '#fcfbfe' }}>
                          <td colSpan={isClientLevel ? 9 : 8} style={{ padding: '24px 32px', borderTop: 'none' }}>
                            <div style={{ background: 'white', border: '1px solid #e0e0f0', borderRadius: '12px', padding: '24px', boxShadow: '0 4px 12px rgba(0,0,0,0.03)' }}>
                              <h4 style={{ margin: '0 0 16px 0', color: '#1e1b4b', fontSize: '15px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <i className="fa-solid fa-pen-to-square" style={{ color: '#4f46e5' }} />
                                Edit Video Notes & Custom Metadata
                              </h4>
                              
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                                {/* Notes Section */}
                                <div>
                                  <label style={{ display: 'block', fontWeight: '600', color: '#475569', fontSize: '13px', marginBottom: '8px' }}>
                                    Notes / Comments
                                  </label>
                                  <textarea
                                    rows={4}
                                    placeholder="Add notes, ideas, tags, or reminders for this video..."
                                    style={{
                                      width: '100%',
                                      padding: '12px',
                                      borderRadius: '8px',
                                      border: '1px solid #cbd5e1',
                                      fontSize: '13.5px',
                                      lineHeight: '1.5',
                                      resize: 'vertical',
                                      outline: 'none',
                                      fontFamily: 'inherit',
                                    }}
                                    value={editingNotes}
                                    onChange={(e) => setEditingNotes(e.target.value)}
                                  />
                                </div>

                                {/* Custom Metadata Section */}
                                <div>
                                  <label style={{ display: 'block', fontWeight: '600', color: '#475569', fontSize: '13px', marginBottom: '8px' }}>
                                    Custom Metadata Fields
                                  </label>
                                  <div style={{ maxHeight: '160px', overflowY: 'auto', marginBottom: '12px', paddingRight: '4px' }}>
                                    {editingMetadata.length === 0 ? (
                                      <div style={{ color: '#94a3b8', fontSize: '13px', padding: '16px', textAlign: 'center', background: '#f8fafc', borderRadius: '8px', border: '1px dashed #e2e8f0', marginBottom: '8px' }}>
                                        No custom metadata fields added yet.
                                      </div>
                                    ) : (
                                      editingMetadata.map((field, idx) => (
                                        <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                                          <input
                                            type="text"
                                            placeholder="Field Name (e.g., Platform)"
                                            style={{
                                              flex: '1',
                                              padding: '8px 12px',
                                              borderRadius: '6px',
                                              border: '1px solid #cbd5e1',
                                              fontSize: '13px',
                                              outline: 'none',
                                            }}
                                            value={field.key}
                                            onChange={(e) => {
                                              const updated = [...editingMetadata]
                                              updated[idx].key = e.target.value
                                              setEditingMetadata(updated)
                                            }}
                                          />
                                          <input
                                            type="text"
                                            placeholder="Field Value (e.g., Instagram)"
                                            style={{
                                              flex: '1',
                                              padding: '8px 12px',
                                              borderRadius: '6px',
                                              border: '1px solid #cbd5e1',
                                              fontSize: '13px',
                                              outline: 'none',
                                            }}
                                            value={field.value}
                                            onChange={(e) => {
                                              const updated = [...editingMetadata]
                                              updated[idx].value = e.target.value
                                              setEditingMetadata(updated)
                                            }}
                                          />
                                          <button
                                            type="button"
                                            style={{
                                              padding: '8px 12px',
                                              borderRadius: '6px',
                                              border: '1px solid #fca5a5',
                                              background: '#fef2f2',
                                              color: '#ef4444',
                                              cursor: 'pointer',
                                              display: 'flex',
                                              alignItems: 'center',
                                              justifyContent: 'center',
                                              transition: 'all 0.2s',
                                            }}
                                            onClick={() => {
                                              setEditingMetadata(editingMetadata.filter((_, i) => i !== idx))
                                            }}
                                            title="Remove field"
                                          >
                                            <i className="fa-solid fa-trash" />
                                          </button>
                                        </div>
                                      ))
                                    )}
                                  </div>
                                  <button
                                    type="button"
                                    style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '6px',
                                      padding: '6px 12px',
                                      borderRadius: '6px',
                                      border: '1px solid #cbd5e1',
                                      background: 'white',
                                      color: '#475569',
                                      fontSize: '12px',
                                      fontWeight: '600',
                                      cursor: 'pointer',
                                      boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                                      transition: 'all 0.2s',
                                    }}
                                    onClick={() => setEditingMetadata([...editingMetadata, { key: '', value: '' }])}
                                  >
                                    <i className="fa-solid fa-plus" /> Add Meta Field
                                  </button>
                                </div>
                              </div>

                              {/* Action Row */}
                              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #f1f5f9' }}>
                                <button
                                  type="button"
                                  style={{
                                    padding: '8px 16px',
                                    borderRadius: '8px',
                                    border: '1px solid #cbd5e1',
                                    background: 'white',
                                    color: '#475569',
                                    fontSize: '13.5px',
                                    fontWeight: '600',
                                    cursor: 'pointer',
                                  }}
                                  disabled={savingId === v.id}
                                  onClick={() => setExpandedVideoId(null)}
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  style={{
                                    padding: '8px 20px',
                                    borderRadius: '8px',
                                    border: 'none',
                                    background: '#4f46e5',
                                    color: 'white',
                                    fontSize: '13.5px',
                                    fontWeight: '600',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                    boxShadow: '0 2px 4px rgba(79, 70, 229, 0.2)',
                                  }}
                                  disabled={savingId === v.id}
                                  onClick={() => handleSave(v)}
                                >
                                  {savingId === v.id ? (
                                    <>
                                      <i className="fa-solid fa-circle-notch spinning" />
                                      Saving...
                                    </>
                                  ) : (
                                    'Save Changes'
                                  )}
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
