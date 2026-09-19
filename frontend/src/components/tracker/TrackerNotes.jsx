import { useRef, useState } from 'react'
import api from '../../api'
import { LANG_LABELS, parseTimecode } from './trackerUtils'

const PAGE_SIZE = 8

function NoteTrail({ notes, page, onPage }) {
  const totalPages = Math.max(1, Math.ceil(notes.length / PAGE_SIZE))
  const slice = notes.slice().reverse().slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  if (!notes.length) return <p className="text-muted tracker-notes-empty">No notes yet.</p>
  return (
    <div>
      <div className="tracker-note-trail">
        {slice.map((note) => (
          <article key={note.id} className="tracker-note-item">
            <div className="tracker-note-meta">
              <strong>{note.created_by || 'unknown'}</strong>
              <span>{note.created_at ? new Date(note.created_at).toLocaleString() : ''}</span>
              {note.language && note.language !== 'all' ? <em>{LANG_LABELS[note.language] || note.language}</em> : null}
              {parseTimecode(note.text) ? <em>{parseTimecode(note.text)}</em> : null}
            </div>
            {note.text ? <p>{note.text}</p> : null}
            {note.attachments?.length ? (
              <div className="tracker-note-files">
                {note.attachments.map((file) => (
                  <a key={file.id} href={file.url} target="_blank" rel="noreferrer">
                    {file.content_type?.startsWith('image/') ? <img src={file.url} alt={file.name} /> : file.name}
                  </a>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="tracker-pagination">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Prev</button>
          <span>Page {page} of {totalPages}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  )
}

export default function TrackerNotes({
  title,
  hint,
  section,
  card,
  languages,
  weekContext,
  onWeekUpdate,
  showDoctorFiles = false,
}) {
  const { token, clientId, year, month, week, toast } = weekContext
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('all')
  const [pending, setPending] = useState([])
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const fileRef = useRef(null)
  const doctorFileRef = useRef(null)
  const notes = section === 'feedback' ? card.feedback_notes || [] : card.doctor_notes || []

  async function uploadPending(file) {
    const result = await api.uploadWeeklyTrackerFile(
      token,
      { clientId, year, month, week, cardId: card.id, target: 'pending', language },
      file,
    )
    return result.file
  }

  async function handleAttach(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const uploaded = await uploadPending(file)
      setPending((prev) => [...prev, uploaded])
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handlePaste(event) {
    const item = [...(event.clipboardData?.items || [])].find((entry) => entry.type.startsWith('image/'))
    if (!item) return
    event.preventDefault()
    const file = item.getAsFile()
    if (!file) return
    try {
      const uploaded = await uploadPending(file)
      setPending((prev) => [...prev, uploaded])
      toast('Screenshot attached.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  async function handleAddNote() {
    if (!text.trim() && pending.length === 0) {
      toast('Enter a note or attach a file.', 'error')
      return
    }
    setSaving(true)
    try {
      const result = await api.addWeeklyTrackerNote(token, {
        client_id: clientId,
        year,
        month,
        week,
        card_id: card.id,
        section,
        text: text.trim(),
        language,
        attachments: pending,
      })
      onWeekUpdate(result)
      setText('')
      setPending([])
      setPage(1)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleDoctorFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const result = await api.uploadWeeklyTrackerFile(
        token,
        { clientId, year, month, week, cardId: card.id, target: 'doctor_files' },
        file,
      )
      onWeekUpdate(result)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <section className="tracker-section">
      <div className="tracker-section-head">
        <h3 className="tracker-kicker">{title}</h3>
        {showDoctorFiles && (
          <>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => doctorFileRef.current?.click()}>
              Add
            </button>
            <input ref={doctorFileRef} type="file" hidden onChange={handleDoctorFile} />
          </>
        )}
      </div>
      {hint ? <p className="tracker-hint">{hint}</p> : null}

      {showDoctorFiles && (card.doctor_files || []).length > 0 && (
        <div className="tracker-note-files" style={{ marginBottom: 12 }}>
          {card.doctor_files.map((file) => (
            <a key={file.id} href={file.url} target="_blank" rel="noreferrer">{file.name}</a>
          ))}
        </div>
      )}

      <textarea
        className="form-control"
        rows={3}
        value={text}
        placeholder={section === 'feedback' ? 'Type 2:30 the broll is wrong and the timecode is picked up automatically.' : 'Anything the editor or the client said that isn’t a stage change.'}
        onChange={(e) => setText(e.target.value)}
        onPaste={handlePaste}
      />
      {pending.length > 0 && (
        <div className="tracker-pending-files">
          {pending.map((file) => (
            <span key={file.id}>{file.name}</span>
          ))}
        </div>
      )}
      <div className="tracker-note-actions">
        <select className="form-control tracker-lang-select" value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="all">All languages</option>
          {languages.map((lang) => (
            <option key={lang} value={lang}>{LANG_LABELS[lang] || lang}</option>
          ))}
        </select>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => fileRef.current?.click()}>
          Attach
        </button>
        <input ref={fileRef} type="file" hidden onChange={handleAttach} />
        <button type="button" className="btn btn-primary btn-sm" onClick={handleAddNote} disabled={saving}>
          {saving ? 'Adding…' : 'Add note'}
        </button>
      </div>
      <NoteTrail notes={notes} page={page} onPage={setPage} />
    </section>
  )
}
