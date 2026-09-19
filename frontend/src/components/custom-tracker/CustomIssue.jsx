import { useEffect, useRef, useState } from 'react'
import {
  emptyNote,
  emptySubtask,
  emptyTask,
  formatDueDate,
  PRIORITIES,
  STATUSES,
} from './customTrackerUtils'

function DuePicker({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => {
    function onDoc(event) {
      if (!wrapRef.current?.contains(event.target)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div className="ct-due" ref={wrapRef}>
      <button
        type="button"
        className={`ct-due-btn${value ? ' has-date' : ''}`}
        title={value ? 'Change due date' : 'Set due date'}
        onClick={() => setOpen((v) => !v)}
      >
        {value ? formatDueDate(value) : <i className="fa-regular fa-calendar" />}
      </button>
      {open ? (
        <div className="ct-due-pop">
          <input
            type="date"
            value={value || ''}
            onChange={(event) => {
              onChange(event.target.value)
              setOpen(false)
            }}
          />
        </div>
      ) : null}
    </div>
  )
}

function DiscussNote({ note, onChange, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.text)
  const menuRef = useRef(null)

  useEffect(() => {
    function onDoc(event) {
      if (!menuRef.current?.contains(event.target)) setMenuOpen(false)
    }
    if (menuOpen) document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [menuOpen])

  function startEdit() {
    setDraft(note.text)
    setEditing(true)
    setMenuOpen(false)
  }

  function saveEdit() {
    const text = draft.trim()
    if (!text) return
    onChange({ ...note, text })
    setEditing(false)
  }

  function cancelEdit() {
    setDraft(note.text)
    setEditing(false)
  }

  return (
    <article className="ct-discuss-item">
      <header>
        <div className="ct-discuss-meta">
          {note.created_at ? (
            <span className="ct-discuss-time">{new Date(note.created_at).toLocaleString()}</span>
          ) : null}
        </div>
        {!editing ? (
          <div className="ct-discuss-actions" ref={menuRef}>
            <button
              type="button"
              className="ct-icon-btn"
              title="Message options"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <i className="fa-solid fa-ellipsis" />
            </button>
            {menuOpen ? (
              <div className="ct-discuss-menu">
                <button type="button" onClick={startEdit}>Edit</button>
                <button type="button" className="is-danger" onClick={() => { onDelete(); setMenuOpen(false) }}>
                  Delete
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </header>
      {editing ? (
        <div className="ct-discuss-edit">
          <div className="ct-discuss-edit-box">
            <textarea
              className="form-control"
              rows={2}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') cancelEdit()
              }}
            />
            <div className="ct-discuss-edit-actions">
              <button type="button" className="ct-discuss-save" onClick={saveEdit} disabled={!draft.trim()}>
                Save
              </button>
              <button type="button" className="ct-discuss-cancel" onClick={cancelEdit}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : (
        <p>{note.text}</p>
      )}
    </article>
  )
}

function AddRow({ nested = false, placeholder, onAdd }) {
  const [text, setText] = useState('')

  function commit() {
    const title = text.trim()
    if (!title) return
    onAdd(title)
    setText('')
  }

  return (
    <div className={`ct-task ct-composer${nested ? ' is-nested' : ''}`}>
      <span className="ct-check ct-check-ghost">
        <input type="checkbox" disabled tabIndex={-1} />
      </span>
      <input
        className="ct-inline-input"
        placeholder={placeholder}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            commit()
          }
        }}
      />
    </div>
  )
}

function TaskRow({ task, nested = false, onChange, onRemove }) {
  return (
    <div className={`ct-task${nested ? ' is-nested' : ''}${task.done ? ' is-complete' : ''}`}>
      <label className="ct-check">
        <input
          type="checkbox"
          checked={Boolean(task.done)}
          onChange={(event) => onChange({ ...task, done: event.target.checked })}
        />
      </label>
      <input
        className={`ct-inline-input${task.done ? ' is-done' : ''}`}
        value={task.title}
        placeholder={nested ? 'Subtask' : 'Task'}
        onChange={(event) => onChange({ ...task, title: event.target.value })}
      />
      <DuePicker value={task.due_date || ''} onChange={(due_date) => onChange({ ...task, due_date })} />
      <button type="button" className="ct-icon-btn" title="Remove" onClick={onRemove}>
        <i className="fa-solid fa-xmark" />
      </button>
    </div>
  )
}

export default function CustomIssue({ issue, author = '', onChange, onRemove }) {
  const [draftNote, setDraftNote] = useState('')
  const [hideCompleted, setHideCompleted] = useState(false)
  const tasks = issue.tasks || []
  const notes = issue.notes || []
  const hasCompleted = tasks.some((task) => task.done || (task.subtasks || []).some((sub) => sub.done))
  const visibleTasks = hideCompleted
    ? tasks.filter((task) => !task.done)
    : tasks

  function patch(next) {
    onChange({ ...issue, ...next })
  }

  function patchTask(taskId, nextTask) {
    patch({
      tasks: tasks.map((task) => (task.id === taskId ? nextTask : task)),
    })
  }

  function sendNote() {
    const text = draftNote.trim()
    if (!text) return
    patch({ notes: [...notes, emptyNote(text, author)] })
    setDraftNote('')
  }

  return (
    <article className={`ct-issue${issue.collapsed ? ' is-collapsed' : ''}${issue.status === 'done' ? ' is-done' : ''}`}>
      <header className="ct-issue-head">
        <button
          type="button"
          className="ct-icon-btn"
          onClick={() => patch({ collapsed: !issue.collapsed })}
          title={issue.collapsed ? 'Expand' : 'Collapse'}
        >
          <i className={`fa-solid ${issue.collapsed ? 'fa-chevron-right' : 'fa-chevron-down'}`} />
        </button>
        <input
          className="ct-issue-title"
          value={issue.title}
          placeholder="Issue title"
          onChange={(event) => patch({ title: event.target.value })}
        />
        <select
          className={`ct-priority ct-priority-${issue.priority}`}
          value={issue.priority}
          onChange={(event) => patch({ priority: event.target.value })}
        >
          {PRIORITIES.map((row) => (
            <option key={row.id} value={row.id}>{row.label}</option>
          ))}
        </select>
        <select
          className="ct-status"
          value={issue.status}
          onChange={(event) => patch({ status: event.target.value })}
        >
          {STATUSES.map((row) => (
            <option key={row.id} value={row.id}>{row.label}</option>
          ))}
        </select>
        <button type="button" className="ct-icon-btn" title="Remove issue" onClick={onRemove}>
          <i className="fa-regular fa-trash-can" />
        </button>
      </header>

      {!issue.collapsed && (
        <div className="ct-issue-body">
          {visibleTasks.map((task) => {
            const subtasks = hideCompleted
              ? (task.subtasks || []).filter((sub) => !sub.done)
              : (task.subtasks || [])
            return (
              <div key={task.id} className="ct-task-block">
                <TaskRow
                  task={task}
                  onChange={(next) => patchTask(task.id, next)}
                  onRemove={() => patch({ tasks: tasks.filter((row) => row.id !== task.id) })}
                />
                {subtasks.map((sub) => (
                  <TaskRow
                    key={sub.id}
                    nested
                    task={sub}
                    onChange={(next) => patchTask(task.id, {
                      ...task,
                      subtasks: (task.subtasks || []).map((row) => (row.id === sub.id ? next : row)),
                    })}
                    onRemove={() => patchTask(task.id, {
                      ...task,
                      subtasks: (task.subtasks || []).filter((row) => row.id !== sub.id),
                    })}
                  />
                ))}
                <AddRow
                  nested
                  placeholder="Add subtask"
                  onAdd={(title) => patchTask(task.id, {
                    ...task,
                    subtasks: [...(task.subtasks || []), emptySubtask(title)],
                  })}
                />
              </div>
            )
          })}
          <AddRow
            placeholder="Add task"
            onAdd={(title) => patch({ tasks: [...tasks, emptyTask(title)] })}
          />
          {hasCompleted ? (
            <button
              type="button"
              className="ct-text-btn ct-hide-completed"
              onClick={() => setHideCompleted((value) => !value)}
            >
              {hideCompleted ? 'Show completed' : 'Hide completed'}
            </button>
          ) : null}

          <section className="ct-discuss">
            <div className="ct-discuss-head">Internal discussions</div>
            {notes.length === 0 ? (
              <p className="ct-discuss-empty">No messages yet</p>
            ) : (
              <div className="ct-discuss-list">
                {notes.map((note) => (
                  <DiscussNote
                    key={note.id}
                    note={note}
                    onChange={(next) => patch({
                      notes: notes.map((row) => (row.id === note.id ? next : row)),
                    })}
                    onDelete={() => patch({
                      notes: notes.filter((row) => row.id !== note.id),
                    })}
                  />
                ))}
              </div>
            )}
            <div className="ct-discuss-compose">
              <textarea
                className="form-control"
                rows={2}
                placeholder="Send a message"
                value={draftNote}
                onChange={(event) => setDraftNote(event.target.value)}
              />
              <button type="button" className="btn btn-primary btn-sm ct-discuss-send" onClick={sendNote} disabled={!draftNote.trim()}>
                <i className="fa-solid fa-paper-plane" />
              </button>
            </div>
          </section>
        </div>
      )}
    </article>
  )
}
