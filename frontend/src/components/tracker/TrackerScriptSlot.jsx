import { useMemo, useState } from 'react'
import { scriptTextValue } from './trackerUtils'

function itemLabel(item) {
  return item.title_hinglish || item.working_title || item.title_en || item.topic_text || 'Untitled'
}

export default function TrackerScriptSlot({
  card,
  scriptedItems = [],
  onPick,
  onSaveEdit,
  busy = false,
}) {
  const [mode, setMode] = useState(null)
  const [draft, setDraft] = useState('')
  const value = scriptTextValue(card.assets)
  const title = card.title || ''
  const available = useMemo(
    () => scriptedItems.filter((item) => item.id && (item.script || '').trim()),
    [scriptedItems],
  )

  function startEdit() {
    setDraft(value)
    setMode('edit')
  }

  if (mode === 'edit') {
    return (
      <div className="tracker-script-slot is-editing">
        <div className="tracker-script-slot-head">
          <span className="tracker-kicker">Final script</span>
        </div>
        <textarea
          className="form-control"
          autoFocus
          rows={8}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="tracker-script-slot-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !draft.trim()}
            onClick={() => {
              onSaveEdit(draft)
              setMode(null)
            }}
          >
            Save
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setMode(null)}>
            Cancel
          </button>
        </div>
      </div>
    )
  }

  if (mode === 'pick' || !value) {
    return (
      <div className="tracker-script-slot">
        <div className="tracker-script-slot-head">
          <span className="tracker-kicker">Final script</span>
          {value ? (
            <button type="button" className="tracker-text-btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          ) : null}
        </div>
        <div className="tracker-script-choose">
          <strong>Choose a generated script</strong>
          <p className="tracker-hint">Pick one to fill this card.</p>
          {available.length === 0 ? (
            <p className="tracker-hint">No generated {card.type === 'short' ? 'short' : 'long'} scripts yet. Generate scripts in Content Plan first.</p>
          ) : (
            <div className="tracker-script-keyword-list">
              {available.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`tracker-script-keyword${item.id === card.content_plan_item_id ? ' is-current' : ''}`}
                  disabled={busy}
                  onClick={() => {
                    onPick(item)
                    setMode(null)
                  }}
                >
                  <strong>{itemLabel(item)}</strong>
                  <small>Keyword · {item.topic_text}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="tracker-script-slot">
      <div className="tracker-script-slot-head">
        <span className="tracker-kicker">Final script</span>
        <div className="tracker-script-slot-actions">
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={startEdit}>
            Edit
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setMode('pick')}>
            Choose
          </button>
        </div>
      </div>
      {title ? <h4 className="tracker-script-title">{title}</h4> : null}
      <pre className="tracker-script-body">{value}</pre>
    </div>
  )
}
