import { useRef, useState } from 'react'
import api from '../../api'
import TrackerDestinations from './TrackerDestinations'
import TrackerNotes from './TrackerNotes'
import TrackerPublishVideo from './TrackerPublishVideo'
import TrackerScriptSlot from './TrackerScriptSlot'
import TrackerStaticGenerate from './TrackerStaticGenerate'
import TrackerYtMetadata from './TrackerYtMetadata'
import {
  TYPE_LABELS,
  TYPE_PILL,
  maybeAdvanceStage,
  nextStageLabel,
  nextStageSection,
  sectionForStage,
  stageList,
} from './trackerUtils'

const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm'
const MAX_VIDEO_BYTES = 50 * 1024 * 1024

function AssetRow({ label, value, onSave, section }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')
  const sectionProps = section ? { 'data-tracker-section': section } : {}

  if (editing) {
    return (
      <div className="tracker-asset-row is-editing" {...sectionProps}>
        <span className="tracker-kicker">{label}</span>
        <input className="form-control" autoFocus value={draft} placeholder="Paste Drive URL" onChange={(e) => setDraft(e.target.value)} />
        <button type="button" className="btn btn-primary btn-sm" onClick={() => { onSave(draft.trim()); setEditing(false) }}>Save</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDraft(value || ''); setEditing(false) }}>Cancel</button>
      </div>
    )
  }

  return (
    <button type="button" className="tracker-asset-row" onClick={() => setEditing(true)} {...sectionProps}>
      <span className="tracker-kicker">{label}</span>
      <em>{value || 'Not added yet — click to add'}</em>
    </button>
  )
}

function VideoAssetRow({ card, value, onSave, weekContext }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const { token, clientId, year, month, week, toast, onWeekUpdate } = weekContext || {}

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !token || !clientId) return
    if (file.size > MAX_VIDEO_BYTES) {
      toast('Video must be 50 MB or smaller.', 'error')
      return
    }
    setUploading(true)
    try {
      const result = await api.uploadWeeklyTrackerFile(
        token,
        { clientId, year, month, week, cardId: card.id, target: 'video_url' },
        file,
      )
      if (onWeekUpdate) onWeekUpdate(result)
      else if (result.file?.url) onSave(result.file.url)
      toast('Video uploaded', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setUploading(false)
    }
  }

  if (uploading) {
    return (
      <div className="tracker-asset-row is-video is-uploading" data-tracker-section="video">
        <span className="tracker-kicker">Video for the client <span className="tracker-file-limit">Max 50 MB</span></span>
        <em><i className="fa-solid fa-spinner fa-spin" /> Uploading…</em>
      </div>
    )
  }

  if (editing) {
    return (
      <div className="tracker-asset-row is-editing" data-tracker-section="video">
        <span className="tracker-kicker">Video for the client <span className="tracker-file-limit">Max 50 MB</span></span>
        <input className="form-control" autoFocus value={draft} placeholder="Paste Drive URL" onChange={(e) => setDraft(e.target.value)} />
        <button type="button" className="btn btn-primary btn-sm" onClick={() => { onSave(draft.trim()); setEditing(false) }}>Save</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDraft(value || ''); setEditing(false) }}>Cancel</button>
      </div>
    )
  }

  return (
    <div className="tracker-asset-row is-video" data-tracker-section="video">
      <span className="tracker-kicker">Video for the client <span className="tracker-file-limit">Max 50 MB</span></span>
      <em>{value || 'Not added yet — paste a link or upload'}</em>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDraft(value || ''); setEditing(true) }}>
        Paste link
      </button>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()}>
        Upload from computer
      </button>
      <input ref={fileRef} type="file" accept={VIDEO_ACCEPT} hidden onChange={handleUpload} />
    </div>
  )
}

function Timeline({ card, onSelectStage }) {
  const stages = stageList(card.type)
  const current = Math.max(0, stages.findIndex((s) => s.id === card.stage))
  const progress = stages.length <= 1 ? 1 : current / (stages.length - 1)
  return (
    <div className="tracker-timeline" style={{ '--tracker-steps': String(stages.length) }}>
      <div className="tracker-timeline-track">
        <div className="tracker-timeline-fill" style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="tracker-timeline-steps">
        {stages.map((stage, index) => (
          <button
            type="button"
            key={stage.id}
            className={`tracker-timeline-step${index <= current ? ' is-done' : ''}${index === current ? ' is-current' : ''}`}
            onClick={() => onSelectStage?.(stage.id)}
          >
            <span className="tracker-timeline-dot" />
            <small>{stage.label}</small>
          </button>
        ))}
      </div>
    </div>
  )
}

function Grip({ onDragStart, onDragEnd, label }) {
  return (
    <span
      className="tracker-drag"
      title="Reorder"
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', label || 'Card')
        const chip = document.createElement('div')
        chip.className = 'tracker-drag-chip'
        chip.textContent = label || 'Moving card'
        chip.style.cssText = 'position:fixed;top:-80px;left:12px;padding:8px 14px;background:#fff;border:1px solid #4f46e5;border-radius:999px;font:700 13px/1.2 system-ui,sans-serif;box-shadow:0 8px 24px rgba(15,23,42,.14);white-space:nowrap;pointer-events:none;z-index:9999'
        document.body.appendChild(chip)
        event.dataTransfer.setDragImage(chip, 24, 20)
        const cleanup = () => {
          chip.remove()
          window.removeEventListener('dragend', cleanup)
        }
        window.addEventListener('dragend', cleanup)
        onDragStart(event)
      }}
      onDragEnd={(event) => onDragEnd?.(event)}
    >
      <i className="fa-solid fa-grip-vertical" />
    </span>
  )
}

export default function TrackerCard({
  card,
  languages,
  weekContext,
  scriptedItems = [],
  scriptBusy = false,
  onPickScript,
  onSaveScriptText,
  onChange,
  onStart,
  onAddSameType,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDragging,
  isDropTarget,
}) {
  const nextLabel = nextStageLabel(card)
  const nextSection = nextStageSection(card)
  const dragLabel = `${TYPE_LABELS[card.type]}${card.title ? ` · ${card.title}` : ''}`
  const [confirmRemove, setConfirmRemove] = useState(false)
  const cardRef = useRef(null)

  function saveAsset(key, url) {
    const assets = { ...(card.assets || {}), [key]: url }
    onChange(maybeAdvanceStage({ ...card, assets }))
  }

  function scrollToSection(sectionId) {
    if (!sectionId || !cardRef.current) return
    const el = cardRef.current.querySelector(`[data-tracker-section="${sectionId}"]`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.remove('tracker-section-flash')
    void el.offsetWidth
    el.classList.add('tracker-section-flash')
    window.setTimeout(() => el.classList.remove('tracker-section-flash'), 1300)
  }

  const dragProps = {
    onDragOver,
    onDrop,
  }
  const stateClass = `${isDragging ? ' is-dragging' : ''}${isDropTarget ? ' is-drop-target' : ''}`

  if (!card.started) {
    return (
      <div className={`tracker-type-card is-idle${stateClass}`} {...dragProps}>
        <Grip onDragStart={onDragStart} onDragEnd={onDragEnd} label={dragLabel} />
        <span className={`tracker-pill ${TYPE_PILL[card.type]}`}>{TYPE_LABELS[card.type]}</span>
        <span className="tracker-idle-status">Not started</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onStart}>
          Start
        </button>
      </div>
    )
  }

  if (card.collapsed) {
    return (
      <div className={`tracker-type-card is-collapsed${stateClass}`} {...dragProps}>
        <Grip onDragStart={onDragStart} onDragEnd={onDragEnd} label={dragLabel} />
        <span className={`tracker-pill ${TYPE_PILL[card.type]}`}>{TYPE_LABELS[card.type]}</span>
        <strong className="tracker-collapsed-title">{card.title || 'Untitled'}</strong>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange({ ...card, collapsed: false })}>
          Expand
        </button>
      </div>
    )
  }

  return (
    <article ref={cardRef} className={`tracker-expanded-card${stateClass}`} {...dragProps}>
      <header className="tracker-expanded-head">
        <Grip onDragStart={onDragStart} onDragEnd={onDragEnd} label={dragLabel} />
        <span className={`tracker-pill ${TYPE_PILL[card.type]}`}>{TYPE_LABELS[card.type]}</span>
        <input
          className="tracker-title-input"
          value={card.title || ''}
          placeholder="What's this one about?"
          onChange={(e) => onChange({ ...card, title: e.target.value })}
        />
        <div className="tracker-head-actions">
          <button type="button" className="tracker-icon-btn" title="Add another" onClick={onAddSameType}>
            <i className="fa-solid fa-plus" />
          </button>
          <button type="button" className="tracker-icon-btn" title="Collapse" onClick={() => onChange({ ...card, collapsed: true })}>
            <i className="fa-regular fa-square" />
          </button>
          {confirmRemove ? (
            <div className="tracker-card-confirm">
              <span>Remove this card?</span>
              <button type="button" className="btn btn-success btn-sm" onClick={() => { setConfirmRemove(false); onRemove() }}>Remove</button>
              <button type="button" className="btn btn-danger-confirm btn-sm" onClick={() => setConfirmRemove(false)}>Cancel</button>
            </div>
          ) : (
            <button type="button" className="tracker-icon-btn" title="Remove" onClick={() => setConfirmRemove(true)}>
              <i className="fa-solid fa-xmark" />
            </button>
          )}
        </div>
      </header>

      <div className="tracker-stage-block">
        <Timeline card={card} onSelectStage={(stageId) => scrollToSection(sectionForStage(card, stageId))} />
        <div className="tracker-next-row">
          <div>
            <strong>Next: {nextLabel || 'Done'}</strong>
            <p className="tracker-hint">{card.stage === 'planned' ? 'Not started yet.' : `Current stage: ${card.stage.replace(/_/g, ' ')}`}</p>
          </div>
          {nextLabel && (
            <button type="button" className="btn btn-primary" onClick={() => scrollToSection(nextSection)}>
              {nextLabel} →
            </button>
          )}
        </div>
        {(card.type === 'long_video' || card.type === 'short') && (
          <div className="tracker-asset-list">
            <div data-tracker-section="script">
              <TrackerScriptSlot
                card={card}
                scriptedItems={scriptedItems}
                busy={scriptBusy}
                onPick={onPickScript}
                onSaveEdit={onSaveScriptText}
              />
            </div>
            <div data-tracker-section="yt_metadata">
              <TrackerYtMetadata card={card} weekContext={weekContext} onChange={onChange} />
            </div>
            <AssetRow section="audio" label="Audio file" value={card.assets?.audio_url} onSave={(url) => saveAsset('audio_url', url)} />
            <VideoAssetRow
              card={card}
              value={card.assets?.video_url}
              onSave={(url) => saveAsset('video_url', url)}
              weekContext={weekContext}
            />
            <div data-tracker-section="publish">
              <TrackerPublishVideo card={card} weekContext={weekContext} onChange={onChange} />
            </div>
          </div>
        )}
      </div>

      {card.type === 'static_post' && (
        <div data-tracker-section="generate">
          <TrackerStaticGenerate card={card} weekContext={weekContext} onChange={onChange} />
        </div>
      )}

      <TrackerNotes
        title="Feedback"
        hint="Type 2:30 the broll is wrong and the timecode is picked up automatically."
        section="feedback"
        card={card}
        languages={languages}
        weekContext={weekContext}
        onWeekUpdate={weekContext.onWeekUpdate}
      />
      <div data-tracker-section="doctor">
        <TrackerNotes
          title="From the client"
          hint="Photos or files the client gave us for this one."
          section="doctor"
          card={card}
          languages={languages}
          weekContext={weekContext}
          onWeekUpdate={weekContext.onWeekUpdate}
          showDoctorFiles
        />
      </div>

      <div data-tracker-section="destinations">
        <TrackerDestinations card={card} languages={languages} onChange={onChange} />
      </div>
    </article>
  )
}
