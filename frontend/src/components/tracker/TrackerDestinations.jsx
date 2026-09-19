import { useState } from 'react'
import {
  LANG_LABELS,
  PLATFORM_LABELS,
  destPlatforms,
  destRows,
  destsFor,
  filledDestCount,
  newId,
} from './trackerUtils'

function DestinationCell({ dest, editingStructure, onSave, onRemove }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(dest.url || '')
  const url = (dest.url || '').trim()

  if (editing) {
    return (
      <div className="tracker-dest-edit">
        <input
          className="form-control"
          autoFocus
          value={draft}
          placeholder="Paste URL"
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="button" className="btn btn-primary btn-sm" onClick={() => { onSave(draft.trim()); setEditing(false) }}>
          Save
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => { setDraft(url); setEditing(false) }}
        >
          Cancel
        </button>
        {editingStructure && (
          <button type="button" className="tracker-slot-btn is-remove" onClick={onRemove} title="Remove">−</button>
        )}
      </div>
    )
  }

  if (url) {
    return (
      <div className="tracker-dest-filled">
        <a href={url} target="_blank" rel="noreferrer">{url}</a>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
          Edit
        </button>
        {editingStructure && (
          <button type="button" className="tracker-slot-btn is-remove" onClick={onRemove} title="Remove">−</button>
        )}
      </div>
    )
  }

  return (
    <div className="tracker-dest-filled">
      <button type="button" className="tracker-add-link" onClick={() => setEditing(true)}>
        + Add
      </button>
      {editingStructure && (
        <button type="button" className="tracker-slot-btn is-remove" onClick={onRemove} title="Remove">−</button>
      )}
    </div>
  )
}

function EmptySlot({ onCreate }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (editing) {
    return (
      <div className="tracker-dest-edit">
        <input
          className="form-control"
          autoFocus
          value={draft}
          placeholder="Paste URL"
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => {
            onCreate(draft.trim())
            setDraft('')
            setEditing(false)
          }}
        >
          Save
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => { setDraft(''); setEditing(false) }}
        >
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="tracker-dest-filled">
      <button type="button" className="tracker-add-link" onClick={() => setEditing(true)}>
        + Add
      </button>
    </div>
  )
}

export default function TrackerDestinations({ card, languages, onChange }) {
  const { filled, total } = filledDestCount(card, languages)
  const [editingStructure, setEditingStructure] = useState(false)
  const platforms = destPlatforms(card)
  const rows = destRows(card, languages)

  function setDestinations(destinations) {
    onChange({ ...card, destinations })
  }

  function saveUrl(destId, url) {
    setDestinations((card.destinations || []).map((d) => (d.id === destId ? { ...d, url } : d)))
  }

  function removeDest(destId) {
    setDestinations((card.destinations || []).filter((d) => d.id !== destId))
  }

  function addDest(language, platform, url = '') {
    setDestinations([
      ...(card.destinations || []),
      { id: newId('dest'), language: language || undefined, platform, url },
    ])
  }

  return (
    <section className="tracker-section">
      <div className="tracker-section-head">
        <h3 className="tracker-kicker">Where it went out</h3>
        <div className="tracker-section-head-actions">
          <span className={`tracker-live-count${filled ? '' : ' is-zero'}`}>{filled} of {total} live</span>
          <button type="button" className="tracker-text-btn" onClick={() => setEditingStructure((v) => !v)}>
            {editingStructure ? 'Done' : 'Edit structure'}
          </button>
        </div>
      </div>

      <div className="tracker-dest-table">
        <div className="tracker-dest-row tracker-dest-head" style={{ gridTemplateColumns: `120px repeat(${platforms.length}, minmax(140px, 1fr))` }}>
          <span />
          {platforms.map((platform) => (
            <span key={platform}>{PLATFORM_LABELS[platform] || platform}</span>
          ))}
        </div>
        {rows.map((language) => (
          <div
            key={language || 'row'}
            className="tracker-dest-row"
            style={{ gridTemplateColumns: `120px repeat(${platforms.length}, minmax(140px, 1fr))` }}
          >
            <span className="tracker-dest-lang">{language ? (LANG_LABELS[language] || language) : ''}</span>
            {platforms.map((platform) => {
              const slots = destsFor(card, language, platform)
              return (
                <div key={platform} className="tracker-dest-cell">
                  {slots.length === 0 ? (
                    <EmptySlot onCreate={(url) => addDest(language, platform, url)} />
                  ) : (
                    slots.map((dest) => (
                      <DestinationCell
                        key={dest.id}
                        dest={dest}
                        editingStructure={editingStructure}
                        onSave={(url) => saveUrl(dest.id, url)}
                        onRemove={() => removeDest(dest.id)}
                      />
                    ))
                  )}
                  {editingStructure && (
                    <button
                      type="button"
                      className="tracker-slot-btn is-add"
                      onClick={() => addDest(language, platform)}
                      title="Add link"
                    >
                      +
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </section>
  )
}
