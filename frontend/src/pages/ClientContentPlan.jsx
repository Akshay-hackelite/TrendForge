import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import api from '../api'
import { formatRecommendationScore } from '../utils/scoreFormat'

function videoLabel(list) {
  if (!list?.length) return '—'
  return list
    .slice(0, 2)
    .map((v) => v.title || v.video_id)
    .join(' · ')
}

export default function ClientContentPlan() {
  const { token } = useAuth()
  const { toast } = useUI()
  const { client, clientId } = useOutletContext()

  const [count, setCount] = useState(5)
  const [suggestions, setSuggestions] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState(null) // 'map' | 'generate' | 'scripts' | 'regen'
  const [regenPrompt, setRegenPrompt] = useState('')
  const [forceRemap, setForceRemap] = useState(false)
  const [showRegen, setShowRegen] = useState(false)
  const [showAllKeywords, setShowAllKeywords] = useState(false)
  const [showKeywordMap, setShowKeywordMap] = useState(false)
  const [showYTModal, setShowYTModal] = useState(false)
  const [ytChannels, setYtChannels] = useState([])
  const [selectedYTChannelId, setSelectedYTChannelId] = useState('')
  const [ytVideos, setYtVideos] = useState([])
  const [selectedYTVideos, setSelectedYTVideos] = useState([])
  const [ytVideosPage, setYtVideosPage] = useState(1)
  const [showScriptsCard, setShowScriptsCard] = useState(false)
  const [activeScriptTab, setActiveScriptTab] = useState('1')
  const [scriptExample1, setScriptExample1] = useState('')
  const [scriptExample2, setScriptExample2] = useState('')
  const YT_PAGE_SIZE = 9

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

  async function handleMap() {
    if (!token || !clientId) return
    setBusyAction('map')
    try {
      toast('Mapping library → keywords (Long/Short analysis)…', 'info')
      const data = await api.mapContentPlan(token, clientId, { force: true })
      setSuggestions(data.suggestions || null)
      toast('Keyword analysis saved', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleGenerate() {
    if (!token || !clientId) return
    setBusyAction('generate')
    try {
      toast('Generating titles from coverage analysis…', 'info')
      const data = await api.generateContentPlan(token, clientId, {
        count,
        forceRemap,
      })
      setSuggestions(data.suggestions || null)
      setForceRemap(false)
      toast('Content plan ready', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleRegenerate() {
    if (!token || !clientId) return
    const prompt = regenPrompt.trim()
    if (!prompt) {
      toast('Add a regenerate instruction first', 'error')
      return
    }
    setBusyAction('regen')
    try {
      toast('Regenerating with your prompt…', 'info')
      const data = await api.regenerateContentPlan(token, clientId, {
        count,
        userPrompt: prompt,
        forceRemap,
      })
      setSuggestions(data.suggestions || null)
      setForceRemap(false)
      toast('Content plan regenerated', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleGenerateScripts() {
    if (!token || !clientId) return
    const planItems = suggestions?.items || []
    if (!planItems.length) {
      toast('Generate titles first, then scripts', 'error')
      return
    }
    setBusyAction('scripts')
    try {
      toast('Generating Hinglish scripts for all plan topics…', 'info')
      const data = await api.generateContentScripts(token, clientId, scriptExample1, scriptExample2)
      setSuggestions(data.suggestions || null)
      toast('Scripts ready — click a title to open', 'success')
      setShowScriptsCard(false)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleOpenYTModal() {
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

  async function handleGenerateYTMetadata() {
    if (!token || !clientId) return
    const planItems = suggestions?.items || []
    if (!planItems.length) {
      toast('Generate titles first', 'error')
      return
    }
    setBusyAction('ytmetadata')
    setShowYTModal(false)
    try {
      toast('Generating YouTube Metadata for all topics…', 'info')
      const itemIds = planItems.map(i => i.id)
      const data = await api.generateYouTubeMetadata(token, clientId, {
        itemIds,
        referenceVideoIds: selectedYTVideos
      })
      setSuggestions(data.suggestions || null)
      toast('Metadata generated — open items to view', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusyAction(null)
    }
  }

  const items = suggestions?.items || []
  const coverage = suggestions?.coverage
  const recentTypes = suggestions?.recent_video_types || []
  const analysis = suggestions?.keyword_analysis || []
  const scriptedCount = items.filter((i) => i.script).length
  const anyBusy = Boolean(busyAction)
  const pendingRows = useMemo(
    () => analysis.filter((r) => r.pending_long || r.pending_short),
    [analysis],
  )
  const visibleAnalysis = showAllKeywords ? analysis : pendingRows.slice(0, 40)
  const hasAnalysis = analysis.length > 0

  return (
    <>
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}` },
              { label: 'Content Plan' },
            ]}
          />
          <h1>Content Plan</h1>
          <p>Map coverage, generate titles, then write Hinglish scripts</p>
        </div>
        <div className="header-actions plan-header-actions">
          <label className="plan-count-field">
            <span className="control-label">Count</span>
            <select
              value={count}
              disabled={anyBusy}
              onChange={(e) => setCount(Number(e.target.value))}
            >
              {Array.from({ length: 9 }, (_, i) => i + 2).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={anyBusy || loading}
            onClick={handleMap}
          >
            <i
              className={`fa-solid ${
                busyAction === 'map' ? 'fa-spinner fa-spin' : 'fa-diagram-project'
              }`}
            />
            1. Map
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={anyBusy || loading}
            onClick={handleGenerate}
          >
            <i
              className={`fa-solid ${
                busyAction === 'generate' ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'
              }`}
            />
            2. Titles
          </button>
          <button
            type="button"
            className={`btn btn-${showScriptsCard ? 'primary' : 'secondary'}`}
            disabled={anyBusy || loading || items.length === 0}
            onClick={() => setShowScriptsCard(!showScriptsCard)}
            title={
              items.length === 0
                ? 'Generate titles first'
                : 'Write Hinglish scripts for every plan topic'
            }
          >
            <i
              className={`fa-solid ${
                busyAction === 'scripts' ? 'fa-spinner fa-spin' : 'fa-file-pen'
              }`}
            />
            3. Scripts
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={anyBusy || loading || items.length === 0}
            onClick={handleOpenYTModal}
            title={items.length === 0 ? 'Generate titles first' : 'Generate YT Metadata'}
          >
            <i
              className={`fa-brands ${
                busyAction === 'ytmetadata' ? 'fa-spinner fa-spin' : 'fa-youtube'
              }`}
            />
            4. YT Metadata
          </button>
        </div>
      </header>

      {showScriptsCard && (
        <div style={{ background: 'var(--bg-light)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border)', marginBottom: '24px' }}>
          <h3 style={{ margin: '0 0 10px 0', fontSize: '1.25em' }}>Provide Reference Scripts (Optional)</h3>
          <p className="text-muted" style={{ marginBottom: '20px', fontSize: '0.95em' }}>
            Paste up to two example scripts to help the AI match your preferred format and tone. If you don't have any, skip this and click Generate Scripts!
          </p>
          
          <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
            <button 
              className={`btn ${activeScriptTab === '1' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveScriptTab('1')}
              style={{ flex: 1, padding: '10px', borderRadius: '8px' }}
            >
              Example 1
            </button>
            <button 
              className={`btn ${activeScriptTab === '2' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveScriptTab('2')}
              style={{ flex: 1, padding: '10px', borderRadius: '8px' }}
            >
              Example 2
            </button>
          </div>

          <div style={{ position: 'relative', marginBottom: '20px' }}>
            <textarea
              className="form-control"
              rows={6}
              placeholder="Paste your first example script here..."
              value={scriptExample1}
              onChange={e => setScriptExample1(e.target.value)}
              style={{ width: '100%', resize: 'vertical', borderRadius: '8px', display: activeScriptTab === '1' ? 'block' : 'none' }}
            />
            <textarea
              className="form-control"
              rows={6}
              placeholder="Paste your second example script here..."
              value={scriptExample2}
              onChange={e => setScriptExample2(e.target.value)}
              style={{ width: '100%', resize: 'vertical', borderRadius: '8px', display: activeScriptTab === '2' ? 'block' : 'none' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button className="btn btn-secondary" onClick={() => setShowScriptsCard(false)}>Cancel</button>
            <button className="btn btn-primary" onClick={handleGenerateScripts} disabled={busyAction === 'scripts'}>
              {busyAction === 'scripts' ? <><i className="fa-solid fa-spinner fa-spin" /> Generating...</> : <><i className="fa-solid fa-bolt" /> Generate Scripts</>}
            </button>
          </div>
        </div>
      )}

      <section className="plan-toolbar card animate-fade-in">
        <div className="plan-toolbar-grid">
          <div className="plan-rule">
            <span className="plan-rule-label">Long / Short coverage</span>
            <p>
              Covered in Short but not Long → Long still pending (and vice versa). Selection uses
              this after map.
            </p>
          </div>
          <div className="plan-rule">
            <span className="plan-rule-label">Theme</span>
            <p>
              Generate AI picks Excel themes that fit each topic. Mix Long themes across the batch
              — Disease explainer is only a soft option, not the default.
            </p>
          </div>
          <div className="plan-rule">
            <span className="plan-rule-label">Flow</span>
            <p>
              Call 1 maps library → keywords. Call 2 generates titles. Call 3 writes Hinglish
              scripts for every topic (duration, timing map, hook, CTA, checklist).
            </p>
          </div>
        </div>

        <div className="plan-toolbar-footer">
          <label className="plan-remap-check">
            <input
              type="checkbox"
              checked={forceRemap}
              disabled={anyBusy}
              onChange={(e) => setForceRemap(e.target.checked)}
            />
            Force re-map on generate
          </label>
          <div className="plan-toolbar-links">
            <Link to={`/clients/${clientId}/videos/settings`} className="text-link">
              Settings · topics & scores
            </Link>
            {hasAnalysis && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={anyBusy || loading}
                onClick={() => setShowKeywordMap((v) => !v)}
              >
                {showKeywordMap ? 'Hide keyword map' : 'Show keyword map'}
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={anyBusy || loading}
              onClick={() => setShowRegen((v) => !v)}
            >
              {showRegen ? 'Hide regenerate' : 'Regenerate with prompt'}
            </button>
          </div>
        </div>

        {coverage && (
          <div className="plan-coverage">
            <span>
              <strong>{coverage.mapped_to_keyword}</strong> mapped
            </span>
            <span>
              <strong>{coverage.out_of_keyword}</strong> out of keyword
            </span>
            <span>
              <strong>{coverage.total}</strong> videos
            </span>
            <span>
              <strong>{pendingRows.length}</strong> keywords pending Long or Short
            </span>
            {(suggestions?.mapped_at ||
              suggestions?.generated_at ||
              suggestions?.scripts_generated_at) && (
              <span className="plan-coverage-time">
                {suggestions.mapped_at
                  ? `Mapped ${new Date(suggestions.mapped_at).toLocaleString()}`
                  : null}
                {suggestions.generated_at
                  ? ` · Generated ${new Date(suggestions.generated_at).toLocaleString()}`
                  : ''}
                {suggestions.scripts_generated_at
                  ? ` · Scripts ${new Date(suggestions.scripts_generated_at).toLocaleString()}`
                  : ''}
              </span>
            )}
          </div>
        )}

        {items.length > 0 && (
          <div className="plan-coverage">
            <span>
              <strong>{scriptedCount}</strong> / {items.length} scripts written
            </span>
          </div>
        )}

        {recentTypes.length > 0 && (
          <div className="plan-recent-types">
            <span className="control-label">Recent themes (last 20)</span>
            <div className="trend-chips">
              {[...new Set(recentTypes)].slice(0, 12).map((t) => (
                <span key={t} className="trend-chip">
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {showRegen && (
        <section className="card plan-regen animate-fade-in">
          <h2>Regenerate</h2>
          <p className="text-muted">
            Keeps the current suggestion list. Rewrites titles/themes with your instruction.
            May swap a keyword only from a small spare pool if you ask.
          </p>
          <textarea
            className="plan-regen-input"
            rows={3}
            value={regenPrompt}
            disabled={anyBusy}
            placeholder="e.g. More report-anxiety titles in Hinglish; lean into FAQ and myth busters"
            onChange={(e) => setRegenPrompt(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={anyBusy || loading}
            onClick={handleRegenerate}
          >
            <i
              className={`fa-solid ${
                busyAction === 'regen' ? 'fa-spinner fa-spin' : 'fa-arrows-rotate'
              }`}
            />
            Run regenerate
          </button>
        </section>
      )}

      {loading && (
        <div className="inline-loading">
          <p className="text-muted">Loading plan…</p>
        </div>
      )}

      {!loading && !hasAnalysis && (
        <section className="client-profile-empty card">
          <div>
            <h2>No keyword analysis yet</h2>
            <p>
              Run <strong>1. Map keywords</strong> to link public videos to topics and see which
              Long/Short formats are still pending.
            </p>
          </div>
          <button type="button" className="btn btn-primary" disabled={anyBusy} onClick={handleMap}>
            Map keywords
          </button>
        </section>
      )}

      {!loading && hasAnalysis && showKeywordMap && (
        <section className="card plan-analysis animate-fade-in">
          <div className="plan-analysis-header">
            <div>
              <h2>Keyword coverage</h2>
              <p className="text-muted">
                Short covered but Long missing → Long pending. Same the other way.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowAllKeywords((v) => !v)}
            >
              {showAllKeywords ? 'Show pending only' : `Show all (${analysis.length})`}
            </button>
          </div>
          <div className="plan-analysis-table-wrap">
            <table className="plan-analysis-table">
              <thead>
                <tr>
                  <th>Keyword</th>
                  <th>Score</th>
                  <th>Long</th>
                  <th>Short</th>
                  <th>Long videos</th>
                  <th>Short videos</th>
                </tr>
              </thead>
              <tbody>
                {visibleAnalysis.map((row) => (
                  <tr key={row.topic_id}>
                    <td>
                      <strong>{row.topic_text}</strong>
                    </td>
                    <td className="plan-num">{formatRecommendationScore(row.recommendation_score)}</td>
                    <td>
                      <span
                        className={`plan-cov-pill ${row.pending_long ? 'is-pending' : 'is-done'}`}
                      >
                        {row.pending_long ? 'Pending' : 'Done'}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`plan-cov-pill ${row.pending_short ? 'is-pending' : 'is-done'}`}
                      >
                        {row.pending_short ? 'Pending' : 'Done'}
                      </span>
                    </td>
                    <td className="plan-vid-cell" title={videoLabel(row.long_videos)}>
                      {videoLabel(row.long_videos)}
                    </td>
                    <td className="plan-vid-cell" title={videoLabel(row.short_videos)}>
                      {videoLabel(row.short_videos)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!showAllKeywords && pendingRows.length > 40 && (
            <p className="text-muted plan-analysis-more">
              Showing 40 of {pendingRows.length} pending keywords.
            </p>
          )}
        </section>
      )}

      {!loading && items.length === 0 && hasAnalysis && (
        <section className="client-profile-empty card">
          <div>
            <h2>Ready to generate</h2>
            <p>Coverage is saved. Run Generate to pick pending Long/Short slots and write titles.</p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={anyBusy}
            onClick={handleGenerate}
          >
            Generate plan
          </button>
        </section>
      )}

      {!loading && items.length > 0 && (
        <ol className="plan-list">
          {items.map((item, idx) => {
            const scriptsTo = item.id
              ? `/clients/${clientId}/videos/scripts?item=${encodeURIComponent(item.id)}`
              : `/clients/${clientId}/videos/scripts`
            return (
              <li key={item.id || idx} className="plan-item card animate-fade-in">
                <Link
                  to={scriptsTo}
                  className="plan-item-summary plan-item-link"
                  title={item.script ? 'Open script' : 'Open scripts page'}
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
                      {item.script ? (
                        <span className="plan-script-pill">Script ready</span>
                      ) : (
                        <span className="plan-script-pill is-empty">No script</span>
                      )}
                      <span className="plan-score">
                        {formatRecommendationScore(item.recommendation_score)}
                      </span>
                    </div>
                    <h2 className="plan-title">{item.title_hinglish || item.working_title}</h2>
                    {(item.title_en || item.working_title) && (
                      <p className="plan-title-en">{item.title_en || item.working_title}</p>
                    )}
                    <p className="plan-keyword">
                      Keyword <strong>{item.topic_text}</strong>
                    </p>
                    <p className="plan-reasoning">{item.reasoning}</p>
                  </div>
                  <i className="fa-solid fa-chevron-right plan-item-chevron" aria-hidden />
                </Link>
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
                onClick={handleGenerateYTMetadata}
              >
                <i className="fa-brands fa-youtube" />
                Generate YT Metadata
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  )
}
