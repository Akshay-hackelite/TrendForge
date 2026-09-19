import { useRef, useState } from 'react'
import api from '../api'

const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm'

export default function VideoUrlAttachField({
  token,
  clientId,
  value = '',
  onChange,
  placeholder = 'https://drive.google.com/...',
  toast,
  inputStyle,
}) {
  const fileRef = useRef(null)
  const [uploading, setUploading] = useState(false)

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !token || !clientId) return
    setUploading(true)
    try {
      const result = await api.uploadLocalVideo(token, clientId, file)
      const url = result?.url || ''
      if (!url) throw new Error('Upload did not return a URL')
      onChange(url)
      toast?.('Video uploaded', 'success')
    } catch (err) {
      toast?.(err.message, 'error')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="video-url-attach">
      <input
        type="text"
        className="form-control"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={inputStyle}
      />
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={uploading || !token || !clientId}
        onClick={() => fileRef.current?.click()}
      >
        {uploading ? (
          <>
            <i className="fa-solid fa-spinner fa-spin" /> Uploading…
          </>
        ) : (
          <>
            <i className="fa-solid fa-paperclip" /> Attach local
          </>
        )}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept={VIDEO_ACCEPT}
        hidden
        onChange={handleUpload}
      />
    </div>
  )
}
