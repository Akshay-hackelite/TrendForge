export const CARD_TYPES = {
  long_video: 'long_video',
  short: 'short',
  static_post: 'static_post',
  blog: 'blog',
}

export const TYPE_LABELS = {
  long_video: 'Long video',
  short: 'Short',
  static_post: 'Static post',
  blog: 'Blog',
}

export const TYPE_PILL = {
  long_video: 'tracker-pill-blue',
  short: 'tracker-pill-pink',
  static_post: 'tracker-pill-gold',
  blog: 'tracker-pill-green',
}

export const LANG_LABELS = {
  hinglish: 'Hindi',
  arabic: 'Arabic',
  russian: 'Russian',
}

export const PLATFORM_LABELS = {
  youtube: 'YouTube',
  facebook: 'Facebook',
  instagram: 'Instagram',
  website: 'Website',
  other: 'Other',
}

export const STAGES = {
  long_video: [
    { id: 'planned', label: 'Planned' },
    { id: 'script_generated', label: 'Script generated' },
    { id: 'yt_metadata_generated', label: 'YT metadata generated' },
    { id: 'audio_generated', label: 'Audio generated' },
    { id: 'video_edited', label: 'Video edited' },
    { id: 'shared_with_doctor', label: 'Shared with client' },
    { id: 'posted', label: 'Posted' },
  ],
  short: [
    { id: 'planned', label: 'Planned' },
    { id: 'script_generated', label: 'Script generated' },
    { id: 'yt_metadata_generated', label: 'YT metadata generated' },
    { id: 'audio_generated', label: 'Audio generated' },
    { id: 'video_edited', label: 'Video edited' },
    { id: 'shared_with_doctor', label: 'Shared with client' },
    { id: 'posted', label: 'Posted' },
  ],
  static_post: [
    { id: 'planned', label: 'Planned' },
    { id: 'posted', label: 'Posted' },
  ],
  blog: [
    { id: 'planned', label: 'Planned' },
    { id: 'published', label: 'Published' },
  ],
}

export const DEFAULT_PLATFORMS = {
  long_video: ['youtube', 'facebook', 'instagram'],
  short: ['youtube', 'facebook', 'instagram'],
  static_post: ['facebook', 'instagram'],
  blog: ['website'],
}

export const LANG_ORDER = ['hinglish']

export const VIDEO_DEFAULT_SLOTS = {
  default: ['youtube', 'facebook', 'instagram'],
}

export function displayLanguages(languages = []) {
  const found = LANG_ORDER.filter((lang) => languages.includes(lang))
  return found.length ? found : ['hinglish']
}

export function newId(prefix = 'id') {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID().slice(0, 12)}`
  }
  return `${prefix}-${Math.random().toString(16).slice(2, 14)}`
}

export function emptyCard(type, sortOrder, isDefault = false) {
  return {
    id: newId('card'),
    type,
    title: '',
    started: false,
    collapsed: true,
    sort_order: sortOrder,
    stage: 'planned',
    is_default: isDefault,
    assets: { script_url: '', script_text: '', audio_url: '', video_url: '' },
    destinations: [],
    structure: {
      platforms: [...(DEFAULT_PLATFORMS[type] || [])],
      extra_slots: [],
      hidden_cells: [],
    },
    generated_post_ids: [],
    generated_posts: [],
    destination_post_ids: {},
    feedback_notes: [],
    doctor_notes: [],
    doctor_files: [],
    content_plan_item_id: null,
    topic_id: null,
  }
}

export function seedDestinations(card, languages = []) {
  const destinations = []
  if (card.type === 'long_video' || card.type === 'short') {
    for (const platform of VIDEO_DEFAULT_SLOTS.default) {
      destinations.push({ id: newId('dest'), language: 'hinglish', platform, url: '' })
    }
  } else {
    const platforms = card.structure?.platforms || DEFAULT_PLATFORMS[card.type] || []
    for (const platform of platforms) {
      destinations.push({ id: newId('dest'), platform, url: '' })
    }
  }
  return destinations
}

export function startCard(card, languages) {
  const destinations = card.destinations?.length ? card.destinations : seedDestinations(card, languages)
  return { ...card, started: true, collapsed: false, destinations }
}

export function stageList(type) {
  return STAGES[type] || STAGES.blog
}

export function nextStage(card) {
  const stages = stageList(card.type)
  const idx = Math.max(0, stages.findIndex((s) => s.id === card.stage))
  if (idx >= stages.length - 1) return card
  return { ...card, stage: stages[idx + 1].id }
}

export function nextStageId(card) {
  const stages = stageList(card.type)
  const idx = Math.max(0, stages.findIndex((s) => s.id === card.stage))
  if (idx >= stages.length - 1) return null
  return stages[idx + 1].id
}

export function sectionForStage(card, stageId) {
  if (card.type === 'blog') return 'destinations'
  if (card.type === 'static_post') return 'generate'
  if (!stageId || stageId === 'planned') return 'script'
  if (stageId === 'script_generated') return 'script'
  if (stageId === 'yt_metadata_generated') return 'yt_metadata'
  if (stageId === 'audio_generated') return 'audio'
  if (stageId === 'video_edited') return 'video'
  if (stageId === 'shared_with_doctor') return 'doctor'
  if (stageId === 'posted') return 'publish'
  return 'destinations'
}

export function nextStageSection(card) {
  const stageId = nextStageId(card)
  if (!stageId) return null
  return sectionForStage(card, stageId)
}

export function maybeAdvanceStage(card) {
  const stages = stageList(card.type).map((s) => s.id)
  let idx = Math.max(0, stages.indexOf(card.stage))
  const bump = (id) => {
    const next = stages.indexOf(id)
    if (next > idx) idx = next
  }
  if (card.type === 'long_video' || card.type === 'short') {
    if (card.assets?.script_text || (card.assets?.script_url && !/^https?:\/\//i.test(card.assets.script_url))) {
      bump('script_generated')
    }
    const locales = card.yt_locales || {}
    if (Object.values(locales).some((loc) => loc && String(loc.yt_title || '').trim())) {
      bump('yt_metadata_generated')
    }
    if (card.assets?.audio_url) bump('audio_generated')
    if (card.assets?.video_url) bump('video_edited')
  }
  return { ...card, stage: stages[idx] }
}

export function nextStageLabel(card) {
  const stages = stageList(card.type)
  const idx = Math.max(0, stages.findIndex((s) => s.id === card.stage))
  if (idx >= stages.length - 1) return null
  return stages[idx + 1].label
}

export function weekRanges(year, month) {
  const last = new Date(year, month, 0).getDate()
  return [
    { week: 1, start: 1, end: Math.min(7, last) },
    { week: 2, start: 8, end: Math.min(14, last) },
    { week: 3, start: 15, end: Math.min(21, last) },
    { week: 4, start: 22, end: last },
  ].filter((row) => row.start <= last)
}

export function weekOfDate(date) {
  const d = date.getDate()
  if (d <= 7) return 1
  if (d <= 14) return 2
  if (d <= 21) return 3
  return 4
}

export function todayParts() {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1, week: weekOfDate(now), date: now }
}

export const EMPTY_WEEK_SUMMARY = { out: 0, total: 4, to_start: 4 }

export function monthLabel(year, month) {
  return new Date(year, month - 1, 1).toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

export function formatChipRange(year, month, start, end) {
  const startDate = new Date(year, month - 1, start)
  const endDate = new Date(year, month - 1, end)
  const startName = startDate.toLocaleString('en-US', { month: 'short' })
  const endName = endDate.toLocaleString('en-US', { month: 'short' })
  if (startName === endName) return `${startName} ${start} – ${end}`
  return `${startName} ${start} – ${endName} ${end}`
}

export function destPlatforms(card) {
  if (card.type === 'long_video' || card.type === 'short') return ['youtube', 'facebook', 'instagram']
  if (card.type === 'blog') return ['website']
  return ['facebook', 'instagram']
}

export function destRows(card, languages = []) {
  if (card.type === 'long_video' || card.type === 'short') return displayLanguages(languages)
  return [null]
}

export function destsFor(card, language, platform) {
  return (card.destinations || []).filter((dest) => (
    dest.platform === platform && (language ? dest.language === language : !dest.language)
  ))
}

export function filledDestCount(card, languages = []) {
  const platforms = destPlatforms(card)
  const rows = destRows(card, languages)
  let total = 0
  let filled = 0
  for (const language of rows) {
    for (const platform of platforms) {
      const slots = destsFor(card, language, platform)
      total += Math.max(slots.length, 1)
      filled += slots.filter((dest) => (dest.url || '').trim()).length
    }
  }
  return { filled, total }
}

export function cardsSummary(cards) {
  const total = cards.length
  const out = cards.filter((card) => (
    (card.destinations || []).some((dest) => (dest.url || '').trim())
  )).length
  const toStart = cards.filter((card) => !card.started).length
  return { out, total, toStart }
}

export function serializableCard(card) {
  const { generated_posts, yt_locales, ...rest } = card
  return rest
}

export const YT_LANGUAGE_OPTIONS = [
  { key: 'hinglish', label: 'Hinglish' },
]

export function localeHasTitle(locales = {}) {
  return Object.values(locales).some((loc) => loc && String(loc.yt_title || '').trim())
}

export function scriptTextValue(assets = {}) {
  if ((assets.script_text || '').trim()) return assets.script_text
  const legacy = assets.script_url || ''
  if (legacy && !/^https?:\/\//i.test(legacy)) return legacy
  return ''
}

export function parseTimecode(text) {
  const match = String(text || '').match(/\b(\d{1,2}:\d{2}(?::\d{2})?)\b/)
  return match ? match[1] : null
}
