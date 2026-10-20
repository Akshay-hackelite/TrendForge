export function languageName(language) {
  const value = String(language || '').trim()
  if (!value) return ''
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export function metaForLanguage(locales, language) {
  const key = String(language || '').trim().toLowerCase()
  const row = key && locales ? locales[key] : null
  if (row?.yt_title) return row
  return {}
}

export function hinglishChannel(channels) {
  return (channels || []).find((channel) => String(channel.language || '').trim().toLowerCase() === 'hinglish') || null
}

export function publishValidation({
  surface,
  postToYT,
  postToIG,
  postToFB,
  selectedChannels,
  videoUrlsByChannel,
  socialVideoLink,
  locales,
}) {
  if (!postToYT && !postToIG && !postToFB) {
    return surface === 'page'
      ? 'Please select at least one platform to post to.'
      : 'Select at least one platform.'
  }
  if (postToYT && selectedChannels.length === 0) {
    return surface === 'page'
      ? 'You must select at least one YouTube channel to post to YouTube.'
      : 'Select at least one YouTube channel.'
  }
  if (postToYT) {
    for (const channel of selectedChannels) {
      const title = channel.title || channel.id
      const language = String(channel.language || '').trim()
      if (!language) {
        return surface === 'page'
          ? `Assign a language in Settings for "${title}" before posting.`
          : `Assign a language in Settings for "${title}" first.`
      }
      if (!metaForLanguage(locales, language).yt_title) {
        return `Generate metadata for ${languageName(language)} first.`
      }
      if (!(videoUrlsByChannel[channel.id] || '').trim()) {
        return `Add a video URL for "${title}".`
      }
    }
  }
  const hinglish = hinglishChannel(selectedChannels)
  const hinglishUrl = hinglish ? (videoUrlsByChannel[hinglish.id] || '').trim() : ''
  const socialUrl = (socialVideoLink || hinglishUrl || '').trim()
  if ((postToIG || postToFB) && !postToYT && !socialUrl) {
    return 'Please provide a social video URL.'
  }
  return ''
}

export function videoUploadBody({
  clientId,
  topicId,
  postToYT,
  postToIG,
  postToFB,
  selectedChannels,
  videoUrlsByChannel,
  socialVideoLink,
  locales,
  fallbackChannelId,
}) {
  const channels = postToYT
    ? selectedChannels.map((channel) => {
      const meta = metaForLanguage(locales, channel.language)
      return {
        channel_id: channel.id,
        drive_link: (videoUrlsByChannel[channel.id] || '').trim(),
        language: channel.language,
        title: meta.yt_title,
        description: meta.yt_description || '',
        tags: (meta.yt_tags || []).map((tag) => String(tag).replace(/#/g, '')),
        thumbnail_url: meta.yt_thumbnail_url || undefined,
        topic_id: topicId,
      }
    })
    : []
  return {
    client_id: clientId,
    channel_id: fallbackChannelId || selectedChannels[0]?.id || '',
    topic_id: topicId,
    stream_progress: true,
    post_to_youtube: !!postToYT,
    post_to_instagram: !!postToIG,
    post_to_facebook: !!postToFB,
    social_video_url: (socialVideoLink || '').trim() || undefined,
    channels,
  }
}
