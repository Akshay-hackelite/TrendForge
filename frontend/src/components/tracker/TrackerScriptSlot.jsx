import { useMemo, useState } from 'react'
import { scriptTextValue } from './trackerUtils'

function itemLabel(item) {
  return item.title_hinglish || item.working_title || item.title_en || item.topic_text || 'Untitled'
}

function fuzzyScore(query, text) {
  const q = query.trim().toLowerCase()
  const value = String(text || '').toLowerCase()
  if (!q) return 1
  const at = value.indexOf(q)
  if (at >= 0) return 200 - at
  let qi = 0
  let streak = 0
  for (const ch of value) {
    if (ch === q[qi]) {
      qi += 1
      streak += 1
      if (qi === q.length) return 40 + streak
    }
  }
  return 0
}

export default function TrackerScriptSlot({
  card,
  scriptedItems = [],
  titleOptions = [],
  onPick,
  onSaveEdit,
  onSaveManual,
  busy = false,
}) {
  const [mode, setMode] = useState(null)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [pickedTitle, setPickedTitle] = useState(null)
  const [scriptOpen, setScriptOpen] = useState(true)
  const value = scriptTextValue(card.assets)
  const title = card.title || ''
  const source = card.assets?.script_source === 'manual' ? 'custom' : 'existing'
  const tab = mode === 'title' || mode === 'write' ? 'custom' : mode === 'pick' ? 'existing' : source
  const available = useMemo(
    () => scriptedItems.filter((item) => item.id && (item.script || '').trim()),
    [scriptedItems],
  )
  const titles = useMemo(() => {
    const scored = (titleOptions || []).map((row) => ({
      row,
      score: Math.max(fuzzyScore(query, row.title), fuzzyScore(query, row.keyword)),
    })).filter((entry) => entry.score > 0)
    scored.sort((a, b) => b.score - a.score || String(a.row.title).localeCompare(String(b.row.title)))
    return scored.map((entry) => entry.row)
  }, [query, titleOptions])

  function openExisting() {
    setMode('pick')
    setScriptOpen(true)
  }

  function openCustom() {
    setMode('title')
    setDraft('')
    setQuery('')
    setPickedTitle(null)
    setScriptOpen(true)
  }

  const header = (
    <div className="tracker-script-slot-head">
      <span className="tracker-kicker">Final script</span>
      <div className="tracker-script-slot-actions">
        {value && mode == null ? (
          <button type="button" className="tracker-icon-btn" aria-label="Edit script" onClick={() => { setDraft(value); setMode('edit') }}>
            <i className="fa-solid fa-pencil" />
          </button>
        ) : null}
        <div className="tracker-script-switch">
          <button type="button" className={tab === 'existing' ? 'is-on' : ''} onClick={openExisting}>
            Choose Existing script
          </button>
          <button type="button" className={tab === 'custom' ? 'is-on' : ''} onClick={openCustom}>
            Custom script
          </button>
        </div>
        <button type="button" className="tracker-icon-btn" aria-label={scriptOpen ? 'Collapse script' : 'Expand script'} onClick={() => setScriptOpen((open) => !open)}>
          <i className={`fa-solid ${scriptOpen ? 'fa-chevron-up' : 'fa-chevron-down'}`} />
        </button>
      </div>
    </div>
  )

  if (!scriptOpen) {
    return <div className="tracker-script-slot">{header}</div>
  }

  if (mode === 'edit') {
    return (
      <div className="tracker-script-slot is-editing">
        {header}
        <textarea className="form-control" autoFocus rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <div className="tracker-script-slot-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !draft.trim()}
            onClick={() => { onSaveEdit(draft); setMode(null) }}
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

  if (mode === 'pick') {
    return (
      <div className="tracker-script-slot">
        {header}
        <div className="tracker-script-choose">
          <strong>Choose a generated script</strong>
          {available.length === 0 ? (
            <p className="tracker-hint">No generated {card.type === 'short' ? 'short' : 'long'} scripts yet. Generate scripts in Content Plan first.</p>
          ) : (
            <div className="tracker-script-keyword-list">
              {available.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`tracker-script-keyword${item.id === card.content_plan_item_id && card.assets?.script_source !== 'manual' ? ' is-current' : ''}`}
                  disabled={busy}
                  onClick={() => { onPick(item); setMode(null) }}
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

  if (mode === 'title' || mode === 'write') {
    return (
      <div className="tracker-script-slot">
        {header}
        <input className="form-control" placeholder="Search titles" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="tracker-script-keyword-list tracker-title-results">
          {titles.map((row) => (
            <button
              key={row.key}
              type="button"
              className={`tracker-script-keyword${pickedTitle?.key === row.key ? ' is-current' : ''}`}
              onClick={() => { setPickedTitle(row); setMode('write') }}
            >
              <strong>{row.title}</strong>
              <small>Keyword · {row.keyword}</small>
            </button>
          ))}
        </div>
        {mode === 'write' && pickedTitle ? (
          <>
            <p className="tracker-hint">Writing for {pickedTitle.title}</p>
            <textarea className="form-control" rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <div className="tracker-script-slot-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busy || !draft.trim()}
                onClick={() => {
                  onSaveManual?.({
                    text: draft,
                    title: pickedTitle.title,
                    topicId: pickedTitle.topicId,
                    itemId: pickedTitle.itemId,
                  })
                  setMode(null)
                }}
              >
                Save
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  if (!value) {
                    setMode('title')
                    setPickedTitle(null)
                  } else {
                    setMode(null)
                  }
                }}
              >
                Cancel
              </button>
            </div>
          </>
        ) : null}
      </div>
    )
  }

  return (
    <div className="tracker-script-slot">
      {header}
      {value ? (
        <>
          {title ? <h4 className="tracker-script-title">{title}</h4> : null}
          <pre className="tracker-script-body">{value}</pre>
        </>
      ) : (
        <p className="tracker-hint">Choose an existing script or write a custom one.</p>
      )}
    </div>
  )
}
