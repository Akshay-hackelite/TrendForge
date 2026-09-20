/** API base: local http://localhost:8000, production set VITE_API_URL */
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

function url(path) {
  return `${API_URL}${path}`
}

async function parseError(response) {
  const err = await response.json().catch(() => ({}))
  return err.detail || `HTTP ${response.status}`
}

export async function apiFetch(path, { token, body, form, formData } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (formData) {
    // Do NOT set Content-Type for FormData; browser sets it with boundary
    payload = formData
  } else if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = form
  } else {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body ?? {})
  }

  const response = await fetch(url(path), { method: 'POST', headers, body: payload })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  if (response.status === 204) return null
  return response.json()
}

function isMp3Buffer(buffer) {
  if (!buffer || buffer.byteLength < 2) return false
  const head = new Uint8Array(buffer, 0, Math.min(3, buffer.byteLength))
  // ID3 tag or MPEG frame sync
  if (head[0] === 0x49 && head[1] === 0x44 && head[2] === 0x33) return true
  return head[0] === 0xff && (head[1] & 0xe0) === 0xe0
}

/**
 * Fetch narration as a stream. Calls onStart as soon as headers arrive,
 * onChunk for each audio chunk, then resolves with the full blob.
 */
async function apiFetchNarrationStream(path, { token, body, onStart, onChunk } = {}) {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
  const response = await fetch(url(path), {
    method: 'POST',
    headers,
    body: JSON.stringify(body ?? {}),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const cached = response.headers.get('X-Narration-Cached') === '1'
  onStart?.({ cached, response })

  if (!response.body) {
    const buffer = await response.arrayBuffer()
    if (!isMp3Buffer(buffer)) {
      throw new Error('Narration did not return playable audio')
    }
    const chunk = new Uint8Array(buffer)
    onChunk?.(chunk)
    return {
      blob: new Blob([buffer], { type: 'audio/mpeg' }),
      cached,
    }
  }

  const reader = response.body.getReader()
  const parts = []
  let total = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (!value?.byteLength) continue
    parts.push(value)
    total += value.byteLength
    onChunk?.(value)
  }
  if (total < 256) {
    throw new Error('Narration audio was empty')
  }
  const buffer = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    buffer.set(part, offset)
    offset += part.byteLength
  }
  if (!isMp3Buffer(buffer.buffer)) {
    throw new Error('Narration did not return playable audio')
  }
  return {
    blob: new Blob([buffer], { type: 'audio/mpeg' }),
    cached,
  }
}

/**
 * Progressive MP3 playback via MediaSource (best-effort).
 * OpenAI returns raw ADTS MP3; MSE often fails mid-stream in Chromium,
 * so callers must always finish on a blob: URL for reliable playback.
 */
export function createStreamingMp3Player(audioEl) {
  const mime = 'audio/mpeg'
  const canStream =
    typeof MediaSource !== 'undefined' &&
    MediaSource.isTypeSupported?.(mime) &&
    audioEl

  if (!canStream) {
    return {
      supported: false,
      failed: false,
      append() {},
      async end() {},
      objectUrl: null,
      destroy() {},
    }
  }

  const mediaSource = new MediaSource()
  const objectUrl = URL.createObjectURL(mediaSource)
  // Do not set audioEl.src here — React owns src via state.

  let sourceBuffer = null
  let closed = false
  let failed = false
  const queue = []
  let pumping = false
  let endRequested = false
  let openPromiseResolve
  let openPromiseReject
  const openPromise = new Promise((resolve, reject) => {
    openPromiseResolve = resolve
    openPromiseReject = reject
  })

  mediaSource.addEventListener(
    'sourceopen',
    () => {
      try {
        sourceBuffer = mediaSource.addSourceBuffer(mime)
        sourceBuffer.mode = 'sequence'
        openPromiseResolve()
        void pump()
      } catch (err) {
        failed = true
        openPromiseReject(err)
      }
    },
    { once: true },
  )
  mediaSource.addEventListener(
    'error',
    () => {
      failed = true
      openPromiseReject(new Error('MediaSource failed'))
    },
    { once: true },
  )

  async function pump() {
    if (pumping || closed || failed) return
    pumping = true
    try {
      await openPromise
      while (!closed && !failed && sourceBuffer && queue.length > 0) {
        if (sourceBuffer.updating) {
          await new Promise((resolve) => {
            sourceBuffer.addEventListener('updateend', resolve, { once: true })
          })
          continue
        }
        const chunk = queue.shift()
        try {
          sourceBuffer.appendBuffer(chunk)
        } catch {
          failed = true
          queue.length = 0
          break
        }
        try {
          await new Promise((resolve, reject) => {
            const onEnd = () => {
              sourceBuffer.removeEventListener('error', onErr)
              resolve()
            }
            const onErr = () => {
              sourceBuffer.removeEventListener('updateend', onEnd)
              reject(new Error('SourceBuffer append failed'))
            }
            sourceBuffer.addEventListener('updateend', onEnd, { once: true })
            sourceBuffer.addEventListener('error', onErr, { once: true })
          })
        } catch {
          failed = true
          queue.length = 0
          break
        }
      }
      if (
        endRequested &&
        !closed &&
        !failed &&
        sourceBuffer &&
        !sourceBuffer.updating &&
        queue.length === 0 &&
        mediaSource.readyState === 'open'
      ) {
        try {
          mediaSource.endOfStream()
        } catch {
          failed = true
        }
      }
    } catch {
      failed = true
      queue.length = 0
    } finally {
      pumping = false
      if (!closed && !failed && queue.length > 0) void pump()
    }
  }

  return {
    supported: true,
    get failed() {
      return failed
    },
    objectUrl,
    append(chunk) {
      if (closed || failed || !chunk?.byteLength) return
      // Copy so the underlying fetch ArrayBuffer can be reused/released safely
      const copy = new Uint8Array(chunk.byteLength)
      copy.set(chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk))
      queue.push(copy)
      void pump()
    },
    async end() {
      endRequested = true
      await openPromise.catch(() => {
        failed = true
      })
      if (!failed) await pump()
      if (sourceBuffer?.updating) {
        await new Promise((resolve) => {
          sourceBuffer.addEventListener('updateend', resolve, { once: true })
        })
      }
      if (!closed && !failed && mediaSource.readyState === 'open' && queue.length === 0) {
        try {
          mediaSource.endOfStream()
        } catch {
          failed = true
        }
      }
    },
    destroy() {
      closed = true
      queue.length = 0
      try {
        if (mediaSource.readyState === 'open') mediaSource.endOfStream()
      } catch {
        /* ignore */
      }
      try {
        URL.revokeObjectURL(objectUrl)
      } catch {
        /* ignore */
      }
    },
  }
}

async function apiFetchBlob(path, { token, body } = {}) {
  return apiFetchNarrationStream(path, { token, body })
}

export const api = {
  login: (username, password) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    return apiFetch('/auth.login', { form })
  },
  register: (username, password) =>
    apiFetch('/auth.register', { body: { username, password } }),
  me: (token) => apiFetch('/auth.me', { token }),

  listClients: (token) => apiFetch('/client.list', { token }),
  createClient: (token, name) => apiFetch('/client.create', { token, body: { name } }),
  updateClient: (token, clientId, fields) =>
    apiFetch('/client.update', { token, body: { client_id: clientId, ...fields } }),
  scrapeClientProfile: (token, clientId, fields = {}) =>
    apiFetch('/client.scrape-profile', {
      token,
      body: { client_id: clientId, ...fields },
    }),
  refreshClientTopics: (token, clientId, fields = {}) =>
    apiFetch('/client.refresh-topics', {
      token,
      body: { client_id: clientId, ...fields },
    }),
  analyzeClientTrends: (token, clientId, { force = false } = {}) => {
    console.log('[trends:api] analyzeClientTrends', { clientId, force })
    return apiFetch('/client.analyze-trends', {
      token,
      body: { client_id: clientId, force },
    }).then((data) => {
      console.log('[trends:api] response', {
        scored: data?.scored,
        api_tasks: data?.api_tasks,
        total_cost: data?.total_cost,
        skipped_cached: data?.skipped_cached,
        error: data?.error,
      })
      return data
    })
  },
  saveClientRecommendations: (token, clientId) =>
    apiFetch('/client.save-recommendations', {
      token,
      body: { client_id: clientId },
    }),
  getContentPlan: (token, clientId) =>
    apiFetch('/client.content-plan.get', {
      token,
      body: { client_id: clientId },
    }),
  mapContentPlan: (token, clientId, { force = true } = {}) =>
    apiFetch('/client.content-plan.map', {
      token,
      body: { client_id: clientId, force },
    }),
  generateContentPlan: (token, clientId, { count = 5, forceRemap = false } = {}) =>
    apiFetch('/client.content-plan.generate', {
      token,
      body: {
        client_id: clientId,
        count,
        force_remap: forceRemap,
      },
    }),
  regenerateContentPlan: (
    token,
    clientId,
    { count, userPrompt, forceRemap = false } = {},
  ) =>
    apiFetch('/client.content-plan.regenerate', {
      token,
      body: {
        client_id: clientId,
        count,
        user_prompt: userPrompt,
        force_remap: forceRemap,
      },
    }),
  generateContentScripts: (token, clientId, example1, example2) =>
    apiFetch('/client.content-plan.generate-scripts', {
      token,
      body: { client_id: clientId, example1, example2 },
    }),
  refineContentScript: (token, clientId, { itemId, userPrompt } = {}) =>
    apiFetch('/client.content-plan.refine-script', {
      token,
      body: {
        client_id: clientId,
        item_id: itemId,
        user_prompt: userPrompt,
      },
    }),
  updateContentScript: (token, clientId, { itemId, script } = {}) =>
    apiFetch('/client.content-plan.update-script', {
      token,
      body: {
        client_id: clientId,
        item_id: itemId,
        script,
      },
    }),
  generateYouTubeMetadata: (token, clientId, { itemIds, userPrompt, referenceVideoIds, languages } = {}) =>
    apiFetch('/client.content-plan-generate-metadata', {
      token,
      body: {
        client_id: clientId,
        item_ids: itemIds,
        user_prompt: userPrompt,
        reference_video_ids: referenceVideoIds || [],
        languages: languages || ['hinglish'],
      },
    }),
  uploadLocalVideo: (token, clientId, file) => {
    const formData = new FormData()
    formData.append('client_id', clientId)
    formData.append('file', file)
    return apiFetch('/video.local.upload', { token, formData })
  },
  refineYouTubeMetadata: (token, clientId, { itemId, userPrompt, referenceVideoIds, language } = {}) =>
    apiFetch('/client.content-plan-refine-metadata', {
      token,
      body: {
        client_id: clientId,
        item_id: itemId,
        user_prompt: userPrompt,
        reference_video_ids: referenceVideoIds || [],
        language: language || 'hinglish',
      },
    }),
  narrateContentScript: (
    token,
    clientId,
    { itemId, combined = false, force = false, onStart, onChunk } = {},
  ) =>
    apiFetchNarrationStream('/client.content-plan.narrate-script', {
      token,
      body: {
        client_id: clientId,
        item_id: itemId || null,
        combined,
        force,
      },
      onStart,
      onChunk,
    }),
  selectClient: (token, clientId) =>
    apiFetch('/client.select', { token, body: { client_id: clientId } }),
  deleteClient: (token, clientId) =>
    apiFetch('/client.delete', { token, body: { client_id: clientId } }),
  syncChannels: (token, clientId) =>
    apiFetch('/client.sync-channels', { token, body: { client_id: clientId } }),

  listChannels: (token, clientId) =>
    apiFetch('/channel.list', { token, body: { client_id: clientId } }),
  getChannel: (token, channelId, clientId) =>
    apiFetch('/channel.get', { token, body: { channel_id: channelId, client_id: clientId } }),
  selectChannel: (token, channelId, clientId) =>
    apiFetch('/channel.select', {
      token,
      body: { channel_id: channelId, client_id: clientId },
    }),
  deleteChannel: (token, channelId, clientId) =>
    apiFetch('/channel.disconnect', {
      token,
      body: { channel_id: channelId, client_id: clientId },
    }),
  setChannelLanguages: (token, clientId, assignments) =>
    apiFetch('/channel.set-languages', {
      token,
      body: { client_id: clientId, assignments },
    }),

  googleLogin: (token, clientId) =>
    apiFetch('/google.login', { token, body: { client_id: clientId } }),

  getInstagramConfig: (token, clientId) =>
    apiFetch('/social.instagram-config.get', { token, body: { client_id: clientId } }),
  saveInstagramConfig: (token, clientId, { app_id, app_secret }) =>
    apiFetch('/social.instagram-config.save', {
      token,
      body: { client_id: clientId, app_id, app_secret },
    }),
  createInstagramConnectUrl: (token, clientId) =>
    apiFetch('/social.instagram.connect-url', { token, body: { client_id: clientId } }),
  getInstagramAnalytics: (token, clientId, { since, until } = {}) =>
    apiFetch('/social.instagram.analytics.get', {
      token,
      body: { client_id: clientId, since, until },
    }),
    
  getFacebookConfig: (token, clientId) =>
    apiFetch('/social.facebook-config.get', { token, body: { client_id: clientId } }),
  saveFacebookConfig: (token, clientId, { app_id, app_secret }) =>
    apiFetch('/social.facebook-config.save', {
      token,
      body: { client_id: clientId, app_id, app_secret },
    }),
  createFacebookConnectUrl: (token, clientId) =>
    apiFetch('/social.facebook.connect-url', { token, body: { client_id: clientId } }),
  getFacebookPages: (token, clientId) =>
    apiFetch('/social.facebook.pages.get', { token, body: { client_id: clientId } }),
  selectFacebookPage: (token, clientId, page_id, page_name, page_access_token) =>
    apiFetch('/social.facebook.page.select', {
      token,
      body: { client_id: clientId, page_id, page_name, page_access_token },
    }),
  disconnectFacebook: (token, clientId) =>
    apiFetch('/social.facebook.disconnect', { token, body: { client_id: clientId } }),
  getInstagramMedia: (token, clientId, limit = 30, after = null) =>
    apiFetch('/social.instagram.media.get', { token, body: { client_id: clientId, limit, after } }),
  uploadInstagramMedia: (token, clientId, file) => {
    const formData = new FormData()
    formData.append('client_id', clientId)
    formData.append('file', file)
    return apiFetch('/social.instagram.media.upload', { token, formData })
  },
  getSocialPostSources: (token, clientId) =>
    apiFetch('/social.post-sources.get', { token, body: { client_id: clientId } }),
  pickSocialKeywords: (token, clientId, { count }) =>
    apiFetch('/social.keywords.pick', { token, body: { client_id: clientId, count } }),
  getSocialPostVersions: (token, clientId, fields) =>
    apiFetch('/social.posts.source.get', {
      token,
      body: { client_id: clientId, ...fields },
    }),
  generateSocialPostDraft: (token, clientId, fields) =>
    apiFetch('/social.post-draft.generate', {
      token,
      body: { client_id: clientId, ...fields },
    }),
  publishSocialPost: (token, clientId, postId, caption, targets = ['instagram'], week = {}) =>
    apiFetch('/social.post.publish', {
      token,
      body: {
        client_id: clientId,
        post_id: postId,
        caption,
        targets,
        year: week.year || undefined,
        month: week.month || undefined,
        week: week.week || undefined,
      },
    }),
  selectSocialPost: (token, clientId, postId) =>
    apiFetch('/social.post.select', {
      token,
      body: { client_id: clientId, post_id: postId },
    }),
  deleteSocialPost: (token, clientId, postId) =>
    apiFetch('/social.post.delete', {
      token,
      body: { client_id: clientId, post_id: postId },
    }),

  listVideos: (token, clientId, channelId) =>
    apiFetch('/video.list', { token, body: { client_id: clientId, channel_id: channelId } }),
  syncVideos: (token, clientId, channelId) =>
    apiFetch('/video.sync', { token, body: { client_id: clientId, channel_id: channelId } }),
  updateVideo: (token, videoId, clientId, channelId, notes, metadataFields) =>
    apiFetch('/video.update', {
      token,
      body: {
        video_id: videoId,
        client_id: clientId,
        channel_id: channelId,
        notes,
        metadata_fields: metadataFields,
      },
    }),
  uploadToYouTube: (token, clientId, channelId, driveLink, title, description, tags, thumbnailUrl) =>
    apiFetch('/video.upload', {
      token,
      body: {
        client_id: clientId,
        channel_id: channelId,
        drive_link: driveLink,
        title,
        description,
        tags,
        thumbnail_url: thumbnailUrl,
      }
    }),
  analytics: (token, body) => apiFetch('/video.analytics', { token, body }),

  listReports: (token, clientId) =>
    apiFetch('/report.list', { token, body: { client_id: clientId } }),
  getReport: (token, reportId) =>
    apiFetch('/report.get', { token, body: { report_id: reportId } }),
  generateReport: (token, clientId, { reportMonth, channelIds } = {}) =>
    apiFetch('/report.generate', {
      token,
      body: {
        client_id: clientId,
        report_month: reportMonth || null,
        channel_ids: channelIds || null,
      },
    }),
  refineReport: (token, reportId, prompt) =>
    apiFetch('/report.refine', {
      token,
      body: { report_id: reportId, prompt },
    }),
  fetchReportHtml: async (token, reportId) => {
    const response = await fetch(url(`/report.html/${reportId}`), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error(await parseError(response))
    return response.text()
  },
  fetchReportPdfBlob: async (token, reportId) => {
    const response = await fetch(url(`/report.pdf/${reportId}`), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error(await parseError(response))
    return response.blob()
  },

  adminUnlock: (adminPassword) =>
    apiFetch('/admin.unlock', { body: { admin_password: adminPassword } }),
  adminListUsers: (adminPassword) =>
    apiFetch('/admin.users.list', { body: { admin_password: adminPassword } }),
  adminCreateUser: (adminPassword, username, password) =>
    apiFetch('/admin.users.create', {
      body: { admin_password: adminPassword, username, password },
    }),
  adminDeleteUser: (adminPassword, username) =>
    apiFetch('/admin.users.delete', {
      body: { admin_password: adminPassword, username },
    }),
  adminResetPassword: (adminPassword, username, password) =>
    apiFetch('/admin.users.reset-password', {
      body: { admin_password: adminPassword, username, password },
    }),
  adminSetActive: (adminPassword, username, isActive) =>
    apiFetch('/admin.users.set-active', {
      body: { admin_password: adminPassword, username, is_active: isActive },
    }),

  // Social Scheduling and Queue API
  addSocialPostToQueue: (token, clientId, postId, targets = ['instagram']) =>
    apiFetch('/social.post.queue.add', {
      token,
      body: { client_id: clientId, post_id: postId, targets },
    }),
  bulkQueueSocialPosts: (token, clientId, postIds, targets = ['instagram']) =>
    apiFetch('/social.post.queue.add_bulk', {
      token,
      body: { client_id: clientId, post_ids: postIds, targets },
    }),
  updateSocialPostTargets: (token, clientId, postId, targets = ['instagram']) =>
    apiFetch('/social.post.targets.update', {
      token,
      body: { client_id: clientId, post_id: postId, targets },
    }),
  removeSocialPostFromQueue: (token, clientId, postId) =>
    apiFetch('/social.post.queue.remove', {
      token,
      body: { client_id: clientId, post_id: postId },
    }),
  reorderSocialPostQueue: (token, clientId, orderedPostIds) =>
    apiFetch('/social.post.queue.reorder', {
      token,
      body: { client_id: clientId, ordered_post_ids: orderedPostIds },
    }),
  editSocialPostQueueCaption: (token, clientId, postId, caption) =>
    apiFetch('/social.post.queue.edit', {
      token,
      body: { client_id: clientId, post_id: postId, caption },
    }),
  getSocialSchedule: (token, clientId) =>
    apiFetch('/social.schedule.get', {
      token,
      body: { client_id: clientId, post_id: 'dummy' }, // using action request
    }),
  listSocialPostQueue: (token, clientId) =>
    apiFetch('/social.post.queue.list', {
      token,
      body: { client_id: clientId, post_id: 'dummy' },
    }),
  getFestivePosts: (token, clientId) =>
    apiFetch('/social.festivals.get', {
      token,
      body: { client_id: clientId },
    }),
  saveSocialSchedule: (
    token,
    clientId,
    frequency,
    selectedDays,
    autoFallback,
    postsPerDay,
    festiveAutoPublish,
    facebookAutoPublish = false,
    festiveFacebookAutoPublish = false,
  ) =>
    apiFetch('/social.schedule.save', {
      token,
      body: {
        client_id: clientId,
        frequency,
        selected_days: selectedDays,
        auto_fallback: autoFallback,
        posts_per_day: postsPerDay,
        festive_auto_publish: festiveAutoPublish,
        facebook_auto_publish: facebookAutoPublish,
        festive_facebook_auto_publish: festiveFacebookAutoPublish,
      },
    }),

  getWeeklyTracker: (token, clientId, year, month, week) =>
    apiFetch('/weekly.tracker.get', {
      token,
      body: { client_id: clientId, year, month, week },
    }),
  getWeeklyTrackerMonthSummary: (token, clientId, year, month) =>
    apiFetch('/weekly.tracker.month.summary', {
      token,
      body: { client_id: clientId, year, month },
    }),
  getWeeklyTrackerPocSummary: (token, year, month) =>
    apiFetch('/weekly.tracker.poc.summary', {
      token,
      body: { year, month },
    }),
  saveWeeklyTracker: (token, clientId, year, month, week, cards) =>
    apiFetch('/weekly.tracker.save', {
      token,
      body: { client_id: clientId, year, month, week, cards },
    }),
  getTrackerScriptLinks: (token, clientId) =>
    apiFetch('/weekly.tracker.script-links.get', {
      token,
      body: { client_id: clientId },
    }),
  attachTrackerScript: (token, clientId, { itemId, year, month, week, cardId } = {}) =>
    apiFetch('/weekly.tracker.attach-script', {
      token,
      body: {
        client_id: clientId,
        item_id: itemId,
        year,
        month,
        week,
        card_id: cardId || null,
      },
    }),
  addWeeklyTrackerNote: (token, fields) =>
    apiFetch('/weekly.tracker.note.add', {
      token,
      body: fields,
    }),
  uploadWeeklyTrackerFile: (token, fields, file) => {
    const formData = new FormData()
    formData.append('client_id', fields.clientId)
    formData.append('year', String(fields.year))
    formData.append('month', String(fields.month))
    formData.append('week', String(fields.week))
    formData.append('card_id', fields.cardId)
    formData.append('target', fields.target || 'pending')
    formData.append('language', fields.language || 'all')
    formData.append('text', fields.text || '')
    formData.append('file', file)
    return apiFetch('/weekly.tracker.file.upload', { token, formData })
  },
  getCustomTracker: (token, clientId, year, month, week) =>
    apiFetch('/custom.tracker.get', {
      token,
      body: { client_id: clientId, year, month, week },
    }),
  getCustomTrackerMonthSummary: (token, clientId, year, month) =>
    apiFetch('/custom.tracker.month.summary', {
      token,
      body: { client_id: clientId, year, month },
    }),
  saveCustomTracker: (token, clientId, year, month, week, categories, issueSeq) =>
    apiFetch('/custom.tracker.save', {
      token,
      body: {
        client_id: clientId,
        year,
        month,
        week,
        categories,
        issue_seq: issueSeq,
      },
    }),
  getTrackerSheetClients: (token) =>
    apiFetch('/tracker.sheet.clients', { token, body: {} }),
  getTrackerSheetWeekly: (token, clientId, year, month) =>
    apiFetch('/tracker.sheet.weekly', {
      token,
      body: { client_id: clientId, year, month },
    }),
  getTrackerSheetCustom: (token, clientId, year, month) =>
    apiFetch('/tracker.sheet.custom', {
      token,
      body: { client_id: clientId, year, month },
    }),
  saveTrackerSheetComment: (token, { clientId, year, month, week, rowKey, comment }) =>
    apiFetch('/tracker.sheet.comment.save', {
      token,
      body: {
        client_id: clientId,
        year,
        month,
        week,
        row_key: rowKey,
        comment,
      },
    }),
}

export default api
