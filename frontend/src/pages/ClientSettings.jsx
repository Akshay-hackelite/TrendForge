import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import api from '../api'
import Breadcrumbs from '../components/Breadcrumbs'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'
import { formatRecommendationScore } from '../utils/scoreFormat'

const WEIGHTS = [
  { key: 'high', label: 'High priority', hint: 'Core themes this brand covers most' },
  { key: 'medium', label: 'Medium priority', hint: 'Related / supporting topics' },
  { key: 'low', label: 'Low priority', hint: 'Adjacent or experimental topics' },
]

const WEIGHT_POINTS = { high: 50, medium: 30, low: 10 }

const TREND_FIELDS = [
  'trend_score',
  'trend_confidence',
  'trend_geo',
  'web_interest',
  'youtube_interest',
  'momentum',
  'rising_flag',
  'trend_fetched_at',
  'recommendation_score',
  'priority_points',
  'trend_points',
  'recommendation_saved_at',
]

function newId() {
  return crypto.randomUUID ? crypto.randomUUID() : `t-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function pickTrendFields(item) {
  const out = {}
  for (const key of TREND_FIELDS) {
    if (item[key] !== undefined && item[key] !== null) out[key] = item[key]
  }
  return out
}

function normalizeTopics(list) {
  if (!Array.isArray(list)) return []
  const seen = new Set()
  const out = []
  for (const item of list) {
    if (typeof item === 'string') {
      const text = item.trim()
      if (!text || seen.has(text.toLowerCase())) continue
      seen.add(text.toLowerCase())
      out.push({ id: newId(), text, weight: 'medium', source: 'manual' })
      continue
    }
    if (!item || typeof item !== 'object') continue
    const text = (item.text || '').trim()
    if (!text || seen.has(text.toLowerCase())) continue
    seen.add(text.toLowerCase())
    out.push({
      id: item.id || newId(),
      text,
      weight: ['high', 'medium', 'low'].includes(item.weight) ? item.weight : 'medium',
      source: item.source === 'auto' ? 'auto' : 'manual',
      ...pickTrendFields(item),
    })
  }
  return out
}

function formatMomentum(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const pct = Math.round(Number(value) * 100)
  return `${pct > 0 ? '+' : ''}${pct}%`
}

function risingLabel(flag) {
  if (flag === 2) return 'Breakout'
  if (flag === 1) return 'Rising'
  return null
}

/** Brand / topic-bucket priority (50/30/10) + trend share ((score/100)*50). Max 100. */
function recommendationScore(topic) {
  const priority = WEIGHT_POINTS[topic.weight] ?? WEIGHT_POINTS.medium
  const trend =
    topic.trend_score != null && !Number.isNaN(Number(topic.trend_score))
      ? (Number(topic.trend_score) / 100) * 50
      : 0
  return Math.round((priority + trend) * 10) / 10
}

function currentMonthValue(today = new Date()) {
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
}

export default function ClientSettings() {
  const { client, clientId } = useOutletContext()
  const { token, patchUser } = useAuth()
  const { toast, confirm } = useUI()

  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [designation, setDesignation] = useState('')
  const [aiVideosStartedFrom, setAiVideosStartedFrom] = useState(currentMonthValue)
  const [description, setDescription] = useState('')
  const [referenceYoutube, setReferenceYoutube] = useState('')
  const [topics, setTopics] = useState([])
  const [newTopic, setNewTopic] = useState('')
  const [newWeight, setNewWeight] = useState('high')
  const [topicFilter, setTopicFilter] = useState('')
  const [userPrompt, setUserPrompt] = useState('')
  const [saving, setSaving] = useState(false)
  const [scraping, setScraping] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [analyzingTrends, setAnalyzingTrends] = useState(false)
  const [forceTrendsRefresh, setForceTrendsRefresh] = useState(false)
  const [trendSummary, setTrendSummary] = useState(null)
  const [scrapeHint, setScrapeHint] = useState(null)
  const [activeTab, setActiveTab] = useState('topics')
  const [recoPage, setRecoPage] = useState('primary') // primary (>=50) | secondary (<50)
  const [savingRecommendations, setSavingRecommendations] = useState(false)

  // Hydrate only when switching clients — not on every patchUser (that was
  // clobbering a fresh refresh with a stale clients[].topics snapshot).
  useEffect(() => {
    if (!client || client.id !== clientId) return
    setName(client.name || '')
    setWebsiteUrl(client.website_url || '')
    setSpecialty(client.specialty || '')
    setDesignation(client.designation || '')
    setDescription(client.description || '')
    setReferenceYoutube(client.reference_youtube_channel || '')
    setAiVideosStartedFrom(client.ai_videos_started_from || currentMonthValue())
    setTopics(normalizeTopics(client.topics || client.topic_ideas || []))
    setScrapeHint(null)
  }, [clientId, client?.id])

  const buckets = useMemo(() => {
    const grouped = { high: [], medium: [], low: [] }
    for (const topic of topics) {
      const key = grouped[topic.weight] ? topic.weight : 'medium'
      grouped[key].push(topic)
    }
    return grouped
  }, [topics])

  const filteredBuckets = useMemo(() => {
    const q = topicFilter.trim().toLowerCase()
    if (!q) return buckets
    const grouped = { high: [], medium: [], low: [] }
    for (const key of Object.keys(grouped)) {
      grouped[key] = buckets[key].filter((t) => t.text.toLowerCase().includes(q))
    }
    return grouped
  }, [buckets, topicFilter])

  const filteredCount =
    filteredBuckets.high.length + filteredBuckets.medium.length + filteredBuckets.low.length

  const trendBuckets = useMemo(() => {
    const sortByTrend = (list) =>
      [...list].sort((a, b) => {
        const sa = a.trend_score
        const sb = b.trend_score
        if (sa == null && sb == null) return a.text.localeCompare(b.text)
        if (sa == null) return 1
        if (sb == null) return -1
        if (sb !== sa) return sb - sa
        return a.text.localeCompare(b.text)
      })
    return {
      high: sortByTrend(buckets.high),
      medium: sortByTrend(buckets.medium),
      low: sortByTrend(buckets.low),
    }
  }, [buckets])

  const scoredCount = useMemo(
    () => topics.filter((t) => t.trend_score != null).length,
    [topics],
  )

  const recommendedTopics = useMemo(() => {
    const q = topicFilter.trim().toLowerCase()
    const list = topics
      .map((t) => {
        const priority_points = WEIGHT_POINTS[t.weight] ?? WEIGHT_POINTS.medium
        const trend_points =
          t.trend_score != null && !Number.isNaN(Number(t.trend_score))
            ? Math.round((Number(t.trend_score) / 100) * 50 * 10) / 10
            : 0
        const liveScore = recommendationScore(t)
        return {
          ...t,
          priority_points: t.priority_points ?? priority_points,
          trend_points: t.trend_points ?? trend_points,
          recommendation_score:
            t.recommendation_score != null ? Number(t.recommendation_score) : liveScore,
        }
      })
      .filter((t) => !q || t.text.toLowerCase().includes(q))
    list.sort((a, b) => {
      if (b.recommendation_score !== a.recommendation_score) {
        return b.recommendation_score - a.recommendation_score
      }
      return a.text.localeCompare(b.text)
    })
    return list
  }, [topics, topicFilter])

  const primaryTopics = useMemo(
    () => recommendedTopics.filter((t) => t.recommendation_score >= 50),
    [recommendedTopics],
  )

  const secondaryTopics = useMemo(
    () => recommendedTopics.filter((t) => t.recommendation_score < 50),
    [recommendedTopics],
  )

  const recoPageTopics = recoPage === 'primary' ? primaryTopics : secondaryTopics
  const recommendationsSavedAt = useMemo(() => {
    const stamps = topics
      .map((t) => t.recommendation_saved_at)
      .filter(Boolean)
      .sort()
    return stamps.length ? stamps[stamps.length - 1] : null
  }, [topics])

  async function saveTopicsDirectly(updatedTopics) {
    if (refreshing) return
    try {
      const data = await api.updateClient(token, clientId, {
        name: name.trim() || client?.name || 'Client',
        website_url: websiteUrl.trim(),
        specialty: specialty.trim(),
        designation: designation.trim(),
        description: description.trim(),
        reference_youtube_channel: referenceYoutube.trim(),
        ai_videos_started_from: aiVideosStartedFrom.trim() || null,
        topics: updatedTopics,
      })
      if (data.clients?.length) {
        patchUser({
          clients: data.clients,
          active_client_id: data.active_client_id,
          active_channel_id: data.active_channel_id,
        })
      }
    } catch (err) {
      toast(`Failed to auto-save topics: ${err.message}`, 'error')
    }
  }

  function addTopic(text, weight = newWeight) {
    const cleaned = text.trim()
    if (!cleaned) return
    if (topics.some((t) => t.text.toLowerCase() === cleaned.toLowerCase())) return
    const updated = [
      ...topics,
      { id: newId(), text: cleaned, weight, source: 'manual' },
    ]
    setTopics(updated)
    saveTopicsDirectly(updated)
    setNewTopic('')
  }

  function removeTopic(id) {
    const updated = topics.filter((t) => t.id !== id)
    setTopics(updated)
    saveTopicsDirectly(updated)
  }

  function moveTopic(id, weight) {
    const updated = topics.map((t) => (t.id === id ? { ...t, weight } : t))
    setTopics(updated)
    saveTopicsDirectly(updated)
  }

  function mergeAutoTopics(suggested) {
    const autoIncoming = normalizeTopics(suggested).map((t) => ({ ...t, source: 'auto' }))
    setTopics((prev) => {
      const manuals = prev.filter((t) => t.source === 'manual')
      const seen = new Set(manuals.map((t) => t.text.toLowerCase()))
      const next = [...manuals]
      for (const topic of autoIncoming) {
        const key = topic.text.toLowerCase()
        if (seen.has(key)) continue
        seen.add(key)
        next.push(topic)
      }
      return next
    })
  }

  async function handleScrape() {
    if (!websiteUrl.trim() && !specialty.trim() && !referenceYoutube.trim()) {
      toast('Enter a website URL, niche, or reference YouTube channel first', 'error')
      return
    }
    setScraping(true)
    setScrapeHint(null)
    try {
      const data = await api.scrapeClientProfile(token, clientId, {
        website_url: websiteUrl.trim() || undefined,
        specialty: specialty.trim() || undefined,
        reference_youtube_channel: referenceYoutube.trim() || undefined,
      })
      if (data.clients?.length) {
        patchUser({
          clients: data.clients,
          active_client_id: data.active_client_id,
          active_channel_id: data.active_channel_id,
        })
      }
      if (data.website_url) setWebsiteUrl(data.website_url)
      if (data.specialty) setSpecialty(data.specialty)
      if (data.suggested_topics?.length) mergeAutoTopics(data.suggested_topics)
      setScrapeHint({
        title: data.page_title,
        snippet: data.openai_rationale || data.page_snippet,
        pages: data.pages_scraped,
      })
      toast(
        data.specialty
          ? `Saved profile · detected niche: ${data.specialty}`
          : 'Website saved and scraped — review topic buckets',
        'success',
      )
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setScraping(false)
    }
  }

  async function runTopicRefresh({ withPrompt = false } = {}) {
    const prompt = userPrompt.trim()
    if (withPrompt && !prompt) {
      toast('Enter a refine prompt first', 'error')
      return
    }
    setRefreshing(true)
    setScrapeHint(null)
    try {
      const data = await api.refreshClientTopics(token, clientId, {
        website_url: websiteUrl.trim() || undefined,
        specialty: specialty.trim() || undefined,
        description: description.trim() || undefined,
        reference_youtube_channel: referenceYoutube.trim() || undefined,
        topics,
        ...(withPrompt ? { user_prompt: prompt } : {}),
      })
      patchUser({
        clients: data.clients,
        active_client_id: data.active_client_id,
        active_channel_id: data.active_channel_id,
      })
      setTopics(normalizeTopics(data.topics))
      if (data.specialty) setSpecialty(data.specialty)
      setScrapeHint({
        title: data.page_title,
        snippet: data.openai_rationale || data.page_snippet,
        pages: data.pages_scraped,
      })
      if (withPrompt) setUserPrompt('')
      if (data.openai_error) {
        toast(
          `Topics refreshed with fallback (OpenAI failed: ${data.openai_error})`,
          'error',
        )
      } else {
        const count = Array.isArray(data.topics) ? data.topics.length : 0
        toast(
          data.generator === 'openai'
            ? withPrompt
              ? `Topics updated from your prompt (${count}) — manual topics kept`
              : `Auto topics refreshed with GPT-5.6 (${count}) — manual topics kept`
            : `Auto topics refreshed (${count}) — manual topics kept`,
          'success',
        )
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleRefreshTopics() {
    const isConfirmed = await confirm({
      title: 'Refresh Auto Topics?',
      message: 'Are you sure you want to refresh auto topics? This will re-analyze your niche/website signals and update auto topics. Manual topics will be preserved.',
    })
    if (!isConfirmed) return
    return runTopicRefresh({ withPrompt: false })
  }

  async function handleApplyRefinePrompt() {
    const isConfirmed = await confirm({
      title: 'Apply Refine Prompt?',
      message: 'Are you sure you want to apply this prompt to refine your auto topics? This will use OpenAI to update topics. Manual topics will be preserved.',
    })
    if (!isConfirmed) return
    return runTopicRefresh({ withPrompt: true })
  }

  async function handleAnalyzeTrends() {
    if (!topics.length) {
      toast('Add topics before analyzing trends', 'error')
      return
    }
    const isConfirmed = await confirm({
      title: 'Analyze Google & YouTube Trends?',
      message: 'Are you sure you want to analyze trends? This fetches real-time quantitative search interest for India from Google and YouTube APIs and may spend API credits.',
    })
    if (!isConfirmed) return

    const force = forceTrendsRefresh
    console.log('[trends:ui] Analyze trends clicked', {
      clientId,
      force,
      topicCount: topics.length,
    })
    setAnalyzingTrends(true)
    try {
      const data = await api.analyzeClientTrends(token, clientId, { force })
      if (data.clients?.length) {
        patchUser({
          clients: data.clients,
          active_client_id: data.active_client_id,
          active_channel_id: data.active_channel_id,
        })
      }
      setTopics(normalizeTopics(data.topics))
      setTrendSummary({
        geo: data.geo || 'IN',
        scored: data.scored ?? 0,
        insufficient_data: data.insufficient_data ?? 0,
        skipped_cached: data.skipped_cached ?? 0,
        fetched_at: data.fetched_at,
        error: data.error,
        api_tasks: data.api_tasks ?? 0,
        total_cost: data.total_cost ?? 0,
      })
      if (force) setForceTrendsRefresh(false)
      if (data.error) {
        toast(
          `Trends partial: ${data.error}` +
            (data.total_cost != null ? ` · spent ~$${Number(data.total_cost).toFixed(3)}` : ''),
          'error',
        )
      } else {
        toast(
          `Trends updated (India) · ${data.scored ?? 0} scored` +
            (data.insufficient_data ? ` · ${data.insufficient_data} low data` : '') +
            (data.skipped_cached ? ` · ${data.skipped_cached} cached` : '') +
            (data.api_tasks ? ` · ${data.api_tasks} API tasks` : '') +
            (data.total_cost != null ? ` · $${Number(data.total_cost).toFixed(3)}` : ''),
          'success',
        )
      }
    } catch (err) {
      console.error('[trends:ui] analyze failed', err)
      toast(err.message, 'error')
    } finally {
      setAnalyzingTrends(false)
    }
  }

  async function handleSaveRecommendations() {
    if (!topics.length) {
      toast('Add topics before saving recommendations', 'error')
      return
    }
    const isConfirmed = await confirm({
      title: 'Save recommendation scores?',
      message:
        'This computes the combined score for every topic (priority 50/30/10 + trend share) and writes it to the database. Primary (≥50) and Secondary (<50) lists will use the saved scores.',
    })
    if (!isConfirmed) return

    setSavingRecommendations(true)
    try {
      const data = await api.saveClientRecommendations(token, clientId)
      if (data.clients?.length) {
        patchUser({
          clients: data.clients,
          active_client_id: data.active_client_id,
          active_channel_id: data.active_channel_id,
        })
      }
      setTopics(normalizeTopics(data.topics))
      toast(
        `Recommendations saved · ${data.primary_count ?? 0} primary (≥50) · ${data.secondary_count ?? 0} secondary (<50)`,
        'success',
      )
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSavingRecommendations(false)
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!name.trim()) {
      toast('Client name is required', 'error')
      return
    }
    if (refreshing) {
      toast('Wait for topic refresh to finish before saving the profile', 'error')
      return
    }
    setSaving(true)
    try {
      const data = await api.updateClient(token, clientId, {
        name: name.trim(),
        website_url: websiteUrl.trim(),
        specialty: specialty.trim(),
        designation: designation.trim(),
        description: description.trim(),
        reference_youtube_channel: referenceYoutube.trim(),
        ai_videos_started_from: aiVideosStartedFrom.trim() || null,
        topics,
      })
      patchUser({
        clients: data.clients,
        active_client_id: data.active_client_id,
        active_channel_id: data.active_channel_id,
      })
      toast('Client profile saved', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
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
              { label: 'Settings' },
            ]}
          />
          <h1>Brand profile</h1>
          <p>
            Capture this creator&apos;s brand details and content topics.
          </p>
        </div>
      </header>

      <form className="profile-form card animate-fade-in" onSubmit={handleSave}>
        <section className="profile-section">
          <h2>Brand profile</h2>
          <p className="profile-section-desc">
            Basic creator info. Paste a website to scrape niche signals and topic ideas. Niche also
            shapes topic generation.
          </p>

          <div className="input-group">
            <label htmlFor="client-name">Name</label>
            <input
              id="client-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Smith"
              required
            />
          </div>

          <div className="input-group">
            <label htmlFor="client-website">Website</label>
            <div className="input-with-action">
              <input
                id="client-website"
                type="url"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://www.example.com"
              />
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleScrape}
                disabled={scraping || refreshing}
              >
                {scraping ? (
                  <>
                    <i className="fa-solid fa-spinner fa-spin" /> Scraping…
                  </>
                ) : (
                  <>
                    <i className="fa-solid fa-globe" /> Scrape
                  </>
                )}
              </button>
            </div>
            <span className="field-hint">
              Deep-scrapes the site (homepage + key pages), niche, and YouTube titles from a
              linked library or reference channel when available. Preview only — use Refresh Topics
              to save auto topics.
            </span>
          </div>

          <div className="input-group">
            <label htmlFor="client-reference-yt">Reference YouTube channel</label>
            <input
              id="client-reference-yt"
              type="text"
              value={referenceYoutube}
              onChange={(e) => setReferenceYoutube(e.target.value)}
              placeholder="https://www.youtube.com/@channel or /channel/UC…"
            />
            <span className="field-hint">
              Optional. Public channel URL or @handle — no Google login required. Recent public
              titles are read via YouTube&apos;s RSS feed and used as keyword signals (especially
              useful when this client has no connected channel yet).
            </span>
          </div>

          {scrapeHint && (scrapeHint.title || scrapeHint.snippet) && (
            <div className="scrape-preview">
              {scrapeHint.title && <strong>{scrapeHint.title}</strong>}
              {scrapeHint.snippet && <p>{scrapeHint.snippet}</p>}
              {scrapeHint.pages > 0 && (
                <p className="scrape-pages">{scrapeHint.pages} page(s) analyzed</p>
              )}
            </div>
          )}

          <div className="input-group">
            <label htmlFor="client-specialty">Niche</label>
            <input
              id="client-specialty"
              type="text"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              placeholder="e.g. Fitness, SaaS, Cooking, Personal finance"
            />
            <span className="field-hint">
              Used as a primary signal when generating / refreshing topics.
            </span>
          </div>

          <div className="input-group">
            <label htmlFor="client-designation">Title / role</label>
            <input
              id="client-designation"
              type="text"
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              placeholder="e.g. Host, Founder, Coach"
            />
            <span className="field-hint">
              Spoken title in video scripts (name + role + today&apos;s topic).
            </span>
          </div>

          <div className="input-group">
            <label htmlFor="client-ai-start">AI videos started from</label>
            <input
              id="client-ai-start"
              type="month"
              value={aiVideosStartedFrom}
              onChange={(e) => setAiVideosStartedFrom(e.target.value)}
            />
            <span className="field-hint">
              Monthly reports treat videos published on or after this month as AI/new content.
            </span>
          </div>

          <div className="input-group">
            <label htmlFor="client-description">Description</label>
            <textarea
              id="client-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief bio, niche, tone of voice, audience, preferred CTA…"
              rows={5}
            />
          </div>

          <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-start' }}>
            <button type="submit" className="btn btn-primary" disabled={saving || refreshing}>
              {saving ? (
                <>
                  <i className="fa-solid fa-spinner fa-spin" /> Saving…
                </>
              ) : (
                <>
                  <i className="fa-solid fa-floppy-disk" /> Save profile
                </>
              )}
            </button>
          </div>
        </section>

        <div className="tabs-container" style={{ display: 'flex', background: '#f1f5f9', padding: '4px', borderRadius: '8px', marginBottom: '24px', width: 'fit-content', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => setActiveTab('topics')}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              border: 'none',
              fontWeight: '600',
              fontSize: '14px',
              cursor: 'pointer',
              background: activeTab === 'topics' ? '#ffffff' : 'transparent',
              color: activeTab === 'topics' ? '#4f46e5' : '#64748b',
              boxShadow: activeTab === 'topics' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <i className="fa-solid fa-list" /> Topics
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('trends')}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              border: 'none',
              fontWeight: '600',
              fontSize: '14px',
              cursor: 'pointer',
              background: activeTab === 'trends' ? '#ffffff' : 'transparent',
              color: activeTab === 'trends' ? '#4f46e5' : '#64748b',
              boxShadow: activeTab === 'trends' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <i className="fa-solid fa-chart-line" /> Trends Analysis
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('recommendations')}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              border: 'none',
              fontWeight: '600',
              fontSize: '14px',
              cursor: 'pointer',
              background: activeTab === 'recommendations' ? '#ffffff' : 'transparent',
              color: activeTab === 'recommendations' ? '#4f46e5' : '#64748b',
              boxShadow: activeTab === 'recommendations' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <i className="fa-solid fa-ranking-star" /> Recommendations
          </button>
        </div>

        {activeTab === 'topics' && (
          <section className="profile-section animate-fade-in">
            <div className="topics-header">
              <div>
                <h2>Topics</h2>
                <p className="profile-section-desc">
                  Topics derived from this brand and niche — website scrape, niche
                  signals, and your refine prompts. Bucketed by how central each topic is to this
                  creator&apos;s content. Manual topics stay untouched on refresh.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRefreshTopics}
                disabled={refreshing || scraping}
              >
                {refreshing && !userPrompt.trim() ? (
                  <>
                    <i className="fa-solid fa-spinner fa-spin" /> Refreshing…
                  </>
                ) : (
                  <>
                    <i className="fa-solid fa-arrows-rotate" /> Refresh topics
                  </>
                )}
              </button>
            </div>

            <div className="input-group topic-prompt-group">
              <label htmlFor="topic-user-prompt">Refine with a prompt</label>
              <textarea
                id="topic-user-prompt"
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                placeholder='e.g. "Add more beginner topics, drop off-brand ideas, emphasize how-tos"'
                rows={3}
                disabled={refreshing || scraping}
              />
              <div className="topic-prompt-actions">
                <span className="field-hint">
                  Applies only to auto topics using your instruction. Manual topics stay unchanged.
                </span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleApplyRefinePrompt}
                  disabled={refreshing || scraping || !userPrompt.trim()}
                >
                  {refreshing && userPrompt.trim() ? (
                    <>
                      <i className="fa-solid fa-spinner fa-spin" /> Applying…
                    </>
                  ) : (
                    <>
                      <i className="fa-solid fa-wand-magic-sparkles" /> Apply prompt
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="topic-add-row">
              <input
                type="text"
                value={newTopic}
                onChange={(e) => setNewTopic(e.target.value)}
                placeholder="Add a broad topic (e.g. sciatica)…"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addTopic(newTopic)
                  }
                }}
              />
              <select
                className="topic-weight-select"
                value={newWeight}
                onChange={(e) => setNewWeight(e.target.value)}
                aria-label="Topic priority"
              >
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => addTopic(newTopic)}
                disabled={!newTopic.trim()}
              >
                <i className="fa-solid fa-plus" /> Add
              </button>
            </div>

            <div className="topic-filter-row">
              <input
                type="search"
                value={topicFilter}
                onChange={(e) => setTopicFilter(e.target.value)}
                placeholder="Filter topics…"
                aria-label="Filter topics"
              />
              <span className="topic-count-summary">
                {topics.length} topic{topics.length === 1 ? '' : 's'}
                {topicFilter.trim() ? ` · ${filteredCount} shown` : ''}
              </span>
            </div>

            <div className="topic-buckets">
              {WEIGHTS.map(({ key, label, hint }) => {
                const items = filteredBuckets[key]
                return (
                  <div key={key} className={`topic-bucket topic-bucket-${key}`}>
                    <div className="topic-bucket-header">
                      <h3>
                        {label} <em>{items.length}</em>
                      </h3>
                      <span>{hint}</span>
                    </div>
                    {items.length === 0 ? (
                      <p className="empty-topics">
                        {topicFilter.trim() ? 'No matches in this bucket.' : 'No topics in this bucket.'}
                      </p>
                    ) : (
                      <div className="topic-chip-grid">
                        {items.map((topic) => (
                          <div
                            key={topic.id}
                            className={`topic-chip topic-chip-${topic.source}`}
                            title={topic.source === 'manual' ? 'Manual' : 'Auto'}
                          >
                            <span className="topic-chip-text">{topic.text}</span>
                            <select
                              value={topic.weight}
                              onChange={(e) => moveTopic(topic.id, e.target.value)}
                              aria-label={`Move ${topic.text}`}
                            >
                              <option value="high">H</option>
                              <option value="medium">M</option>
                              <option value="low">L</option>
                            </select>
                            <button
                              type="button"
                              className="topic-remove"
                              onClick={() => removeTopic(topic.id)}
                              aria-label={`Remove ${topic.text}`}
                            >
                              <i className="fa-solid fa-xmark" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {activeTab === 'trends' && (
          <section className="profile-section trends-section animate-fade-in">
            <div className="topics-header">
              <div>
                <h2>Trends analysis</h2>
                <p className="profile-section-desc">
                  Internet demand from Google Search + YouTube Search interest for India — scraped
                  and scored via trends APIs. Each priority bucket is sorted by quantitative trend
                  score (highest first). Topics with sparse data still get a score and a Low data
                  badge.
                </p>
              </div>
              <div className="trends-actions">
                <label className="trends-force-toggle" title="Re-fetch all topics and spend API credit again">
                  <input
                    type="checkbox"
                    checked={forceTrendsRefresh}
                    onChange={(e) => setForceTrendsRefresh(e.target.checked)}
                    disabled={analyzingTrends || refreshing}
                  />
                  Re-fetch all (costs more)
                </label>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleAnalyzeTrends}
                  disabled={analyzingTrends || refreshing || !topics.length}
                >
                  {analyzingTrends ? (
                    <>
                      <i className="fa-solid fa-spinner fa-spin" /> Analyzing…
                    </>
                  ) : (
                    <>
                      <i className="fa-solid fa-chart-line" /> Analyze trends
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="trends-meta">
              <span className="trends-geo">Region: India (IN)</span>
              <span>
                {scoredCount} of {topics.length} scored
                {trendSummary?.insufficient_data
                  ? ` · ${trendSummary.insufficient_data} insufficient data`
                  : ''}
              </span>
              {trendSummary?.fetched_at ? (
                <span className="trends-fetched">
                  Last run {new Date(trendSummary.fetched_at).toLocaleString()}
                </span>
              ) : null}
            </div>

            {!topics.length ? (
              <p className="empty-topics">Add topics above, then run Analyze trends.</p>
            ) : scoredCount === 0 ? (
              <p className="empty-topics">
                No trend scores yet. Click Analyze trends to pull Google + YouTube interest for India.
              </p>
            ) : null}

            <div className="topic-buckets trends-buckets">
              {WEIGHTS.map(({ key, label }) => {
                const items = trendBuckets[key]
                return (
                  <div key={key} className={`topic-bucket topic-bucket-${key}`}>
                    <div className="topic-bucket-header">
                      <h3>
                        {label} <em>{items.length}</em>
                      </h3>
                      <span>Sorted by trend score</span>
                    </div>
                    {items.length === 0 ? (
                      <p className="empty-topics">No topics in this bucket.</p>
                    ) : (
                      <ul className="trend-row-list">
                        {items.map((topic) => {
                          const rising = risingLabel(topic.rising_flag)
                          return (
                            <li key={topic.id} className="trend-row">
                              <span className="trend-row-text" title={topic.text}>
                                {topic.text}
                              </span>
                              <span
                                className={`trend-score ${
                                  topic.trend_score == null ? 'trend-score-null' : ''
                                }`}
                              >
                                {topic.trend_score != null ? Math.round(topic.trend_score) : '—'}
                              </span>
                              <span className="trend-chips">
                                <span className="trend-chip" title="Google Search interest (12mo avg)">
                                  Web {topic.web_interest != null ? Math.round(topic.web_interest) : '—'}
                                </span>
                                <span className="trend-chip" title="YouTube Search interest (12mo avg)">
                                  YT{' '}
                                  {topic.youtube_interest != null
                                    ? Math.round(topic.youtube_interest)
                                    : '—'}
                                </span>
                                <span
                                  className="trend-chip"
                                  title="Momentum: recent ~90 days search interest vs the prior ~90 days. + means rising, − means fading."
                                >
                                  Mom {formatMomentum(topic.momentum)}
                                </span>
                                {rising ? (
                                  <span className={`trend-chip trend-chip-rising rising-${topic.rising_flag}`}>
                                    {rising}
                                  </span>
                                ) : null}
                                {topic.trend_confidence === 'low' ? (
                                  <span className="trend-chip trend-chip-low">Low data</span>
                                ) : null}
                              </span>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {activeTab === 'recommendations' && (
          <section className="profile-section recommendations-section animate-fade-in">
            <div className="topics-header">
              <div>
                <h2>Combined recommendations</h2>
                <p className="profile-section-desc">
                  One ranked list blending topic priority with internet demand.
                  Score = priority points (High 50 / Mid 30 / Low 10) + (trend score ÷ 100 × 50).
                  Max 100. Split at 50 into Primary and Secondary. Click Save to write scores to the DB.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveRecommendations}
                disabled={savingRecommendations || !topics.length}
              >
                {savingRecommendations ? (
                  <>
                    <i className="fa-solid fa-spinner fa-spin" /> Saving…
                  </>
                ) : (
                  <>
                    <i className="fa-solid fa-floppy-disk" /> Save recommendations
                  </>
                )}
              </button>
            </div>

            <div className="trends-meta">
              <span>
                {primaryTopics.length} primary · {secondaryTopics.length} secondary
                {topicFilter.trim() ? ' (filtered)' : ''}
              </span>
              <span>
                {scoredCount} of {topics.length} with trend data
              </span>
              {recommendationsSavedAt ? (
                <span className="trends-fetched">
                  Saved {new Date(recommendationsSavedAt).toLocaleString()}
                </span>
              ) : (
                <span className="trends-fetched">Not saved to DB yet</span>
              )}
            </div>

            <div
              className="reco-page-tabs"
              style={{
                display: 'flex',
                background: '#f1f5f9',
                padding: '4px',
                borderRadius: '8px',
                marginBottom: '16px',
                width: 'fit-content',
                flexWrap: 'wrap',
              }}
            >
              <button
                type="button"
                onClick={() => setRecoPage('primary')}
                style={{
                  padding: '7px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  fontWeight: '600',
                  fontSize: '13px',
                  cursor: 'pointer',
                  background: recoPage === 'primary' ? '#ffffff' : 'transparent',
                  color: recoPage === 'primary' ? '#4f46e5' : '#64748b',
                  boxShadow: recoPage === 'primary' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  transition: 'all 0.2s',
                }}
              >
                Primary (≥50) · {primaryTopics.length}
              </button>
              <button
                type="button"
                onClick={() => setRecoPage('secondary')}
                style={{
                  padding: '7px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  fontWeight: '600',
                  fontSize: '13px',
                  cursor: 'pointer',
                  background: recoPage === 'secondary' ? '#ffffff' : 'transparent',
                  color: recoPage === 'secondary' ? '#4f46e5' : '#64748b',
                  boxShadow: recoPage === 'secondary' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  transition: 'all 0.2s',
                }}
              >
                Secondary (&lt;50) · {secondaryTopics.length}
              </button>
            </div>

            <div className="topic-filter-row">
              <input
                type="search"
                value={topicFilter}
                onChange={(e) => setTopicFilter(e.target.value)}
                placeholder="Filter recommendations…"
                aria-label="Filter recommendations"
              />
            </div>

            <p className="profile-section-desc" style={{ marginTop: 0, marginBottom: '12px' }}>
              {recoPage === 'primary'
                ? 'Primary page — topics scoring 50 or above. Strong brand fit and/or demand.'
                : 'Secondary page — topics scoring below 50. Lower priority or weaker trend signal.'}
            </p>

            {!topics.length ? (
              <p className="empty-topics">Add topics first, then run Analyze trends for full scores.</p>
            ) : recoPageTopics.length === 0 ? (
              <p className="empty-topics">
                {topicFilter.trim()
                  ? 'No topics match this filter on this page.'
                  : recoPage === 'primary'
                    ? 'No primary topics yet (score ≥ 50).'
                    : 'No secondary topics (all scored ≥ 50).'}
              </p>
            ) : (
              <ul className="trend-row-list recommendation-list">
                {recoPageTopics.map((topic, index) => (
                  <li key={topic.id} className="trend-row recommendation-row">
                    <span className="recommendation-rank" aria-hidden="true">
                      {index + 1}
                    </span>
                    <span className="trend-row-text" title={topic.text}>
                      {topic.text}
                    </span>
                    <span className="trend-score" title="Combined recommendation score">
                      {formatRecommendationScore(topic.recommendation_score)}
                    </span>
                    <span className="trend-chips">
                      <span
                        className={`trend-chip trend-chip-weight weight-${topic.weight}`}
                        title={`Topic priority → ${topic.priority_points} pts`}
                      >
                        {topic.weight === 'high' ? 'High' : topic.weight === 'low' ? 'Low' : 'Mid'}{' '}
                        {topic.priority_points}
                      </span>
                      <span
                        className="trend-chip"
                        title={
                          topic.trend_score != null
                            ? `Trend ${Math.round(topic.trend_score)}/100 → ${topic.trend_points} pts`
                            : 'No trend score yet — trend share is 0'
                        }
                      >
                        Trend{' '}
                        {topic.trend_score != null
                          ? `${Math.round(topic.trend_score)} → ${topic.trend_points}`
                          : '—'}
                      </span>
                      {topic.trend_confidence === 'low' ? (
                        <span className="trend-chip trend-chip-low">Low data</span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </form>
    </>
  )
}
