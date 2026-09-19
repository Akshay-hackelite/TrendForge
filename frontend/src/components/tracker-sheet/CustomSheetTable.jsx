import { useEffect, useState } from 'react'
import { buildCustomSheetRows, notesToText, textToNotes } from './sheetUtils'
import SheetCommentCell from './SheetCommentCell'
import {
  emptyCategory,
  emptyIssue,
  emptySubtask,
  emptyTask,
  PRIORITIES,
  STATUSES,
} from '../custom-tracker/customTrackerUtils'
import { formatChipRange, weekRanges } from '../tracker/trackerUtils'

const CREATE_CATEGORY = '__create__'

function SheetInput({ value, onChange, placeholder = '' }) {
  return (
    <input
      className="sheet-cell-input sheet-cell-inline"
      value={value || ''}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

function IconBtn({ title, icon, danger = false, onClick }) {
  return (
    <button
      type="button"
      className={`sheet-icon-btn ct-icon-btn${danger ? ' is-danger' : ''}`}
      title={title}
      onClick={onClick}
    >
      <i className={`fa-solid ${icon}`} />
    </button>
  )
}

function SheetAddComposer({ placeholder, onAdd }) {
  const [text, setText] = useState('')

  function commit() {
    const title = text.trim()
    if (!title) return
    onAdd(title)
    setText('')
  }

  return (
    <input
      className="sheet-cell-input sheet-cell-inline sheet-add-composer"
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
  )
}

function CustomSheetWeekTable({
  week,
  year,
  month,
  categories = [],
  author = '',
  onPatchWeek,
}) {
  const weekDoc = { week, categories }
  const rows = buildCustomSheetRows([weekDoc])
  const range = weekRanges(year, month).find((row) => row.week === week)
  const [headerCategoryId, setHeaderCategoryId] = useState('')
  const [newCategoryName, setNewCategoryName] = useState('')

  const creating = headerCategoryId === CREATE_CATEGORY || !categories.length
  const targetCategoryId = creating ? '' : (headerCategoryId || categories[0]?.id)

  useEffect(() => {
    if (!categories.length) {
      setHeaderCategoryId(CREATE_CATEGORY)
      return
    }
    if (headerCategoryId === CREATE_CATEGORY) return
    if (!categories.some((category) => category.id === headerCategoryId)) {
      setHeaderCategoryId(categories[0].id)
    }
  }, [categories, headerCategoryId])

  function patchWeek(mutator) {
    onPatchWeek(week, mutator)
  }

  function updateCategory(categoryId, patch) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      if (category) Object.assign(category, patch)
    })
  }

  function updateIssue(categoryId, issueId, patch) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      if (issue) Object.assign(issue, patch)
    })
  }

  function updateTask(categoryId, issueId, taskId, patch) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      const task = issue?.tasks?.find((row) => row.id === taskId)
      if (task) Object.assign(task, patch)
    })
  }

  function updateSubtask(categoryId, issueId, taskId, subtaskId, patch) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      const task = issue?.tasks?.find((row) => row.id === taskId)
      const subtask = task?.subtasks?.find((row) => row.id === subtaskId)
      if (subtask) Object.assign(subtask, patch)
    })
  }

  function addIssue(categoryId) {
    if (!categoryId) return
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      if (category) category.issues = [...(category.issues || []), emptyIssue()]
    })
  }

  function createCategory() {
    const name = newCategoryName.trim()
    if (!name) return
    const category = emptyCategory(name)
    patchWeek((items) => {
      items.push(category)
    })
    setHeaderCategoryId(category.id)
    setNewCategoryName('')
  }

  function addTask(categoryId, issueId, title) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      if (issue) issue.tasks = [...(issue.tasks || []), emptyTask(title)]
    })
  }

  function addSubtask(categoryId, issueId, taskId, title) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      const task = issue?.tasks?.find((row) => row.id === taskId)
      if (task) task.subtasks = [...(task.subtasks || []), emptySubtask(title)]
    })
  }

  function removeIssue(categoryId, issueId) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      if (category) category.issues = (category.issues || []).filter((row) => row.id !== issueId)
    })
  }

  function removeTask(categoryId, issueId, taskId) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      if (issue) issue.tasks = (issue.tasks || []).filter((row) => row.id !== taskId)
    })
  }

  function removeSubtask(categoryId, issueId, taskId, subtaskId) {
    patchWeek((items) => {
      const category = items.find((row) => row.id === categoryId)
      const issue = category?.issues?.find((row) => row.id === issueId)
      const task = issue?.tasks?.find((row) => row.id === taskId)
      if (task) task.subtasks = (task.subtasks || []).filter((row) => row.id !== subtaskId)
    })
  }

  function renderStatusControl(row) {
    if (row.leafType === 'add-task' || row.leafType === 'add-subtask') {
      return <span className="text-muted">—</span>
    }
    if (row.leafType === 'issue') {
      return (
        <select
          className="sheet-cell-select"
          value={row.issue.status}
          onChange={(event) => updateIssue(row.category.id, row.issue.id, { status: event.target.value })}
        >
          {STATUSES.map((item) => (
            <option key={item.id} value={item.id}>{item.label}</option>
          ))}
        </select>
      )
    }
    const done = Boolean(row.leaf?.done)
    return (
      <select
        className="sheet-cell-select"
        value={done ? 'done' : 'todo'}
        onChange={(event) => {
          const nextDone = event.target.value === 'done'
          if (row.leafType === 'task') {
            updateTask(row.category.id, row.issue.id, row.task.id, { done: nextDone })
          } else {
            updateSubtask(row.category.id, row.issue.id, row.task.id, row.subtask.id, { done: nextDone })
          }
        }}
      >
        <option value="todo">To do</option>
        <option value="done">Done</option>
      </select>
    )
  }

  function renderDueDate(row) {
    if (row.leafType === 'issue' || row.leafType === 'add-task' || row.leafType === 'add-subtask') {
      return <span className="text-muted">—</span>
    }
    const value = row.leaf?.due_date || ''
    const onChange = (due_date) => {
      if (row.leafType === 'task') {
        updateTask(row.category.id, row.issue.id, row.task.id, { due_date })
      } else {
        updateSubtask(row.category.id, row.issue.id, row.task.id, row.subtask.id, { due_date })
      }
    }
    return (
      <input
        type="date"
        className="sheet-cell-input sheet-cell-inline"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    )
  }

  function renderComment(row) {
    if (row.leafType === 'add-task' || row.leafType === 'add-subtask') {
      return <span className="text-muted">—</span>
    }
    const onChange = (comment) => {
      if (row.leafType === 'issue') {
        updateIssue(row.category.id, row.issue.id, { comment })
      } else if (row.leafType === 'task') {
        updateTask(row.category.id, row.issue.id, row.task.id, { comment })
      } else {
        updateSubtask(row.category.id, row.issue.id, row.task.id, row.subtask.id, { comment })
      }
    }
    return <SheetCommentCell value={row.leaf?.comment || ''} onSave={onChange} />
  }

  function renderTaskCell(row) {
    if (row.leafType === 'add-task' || row.leafType === 'issue') {
      return (
        <SheetAddComposer
          placeholder="+ Add task"
          onAdd={(title) => addTask(row.category.id, row.issue.id, title)}
        />
      )
    }
    if (row.task && row.leafType !== 'add-subtask') {
      return (
        <div className="sheet-inline-field">
          <SheetInput
            value={row.task.title}
            placeholder="Task"
            onChange={(title) => updateTask(row.category.id, row.issue.id, row.task.id, { title })}
          />
          <IconBtn
            title="Remove task"
            icon="fa-xmark"
            danger
            onClick={() => removeTask(row.category.id, row.issue.id, row.task.id)}
          />
        </div>
      )
    }
    return <span className="text-muted">—</span>
  }

  function renderSubtaskCell(row) {
    if (row.leafType === 'subtask') {
      return (
        <div className="sheet-inline-field">
          <SheetInput
            value={row.subtask.title}
            placeholder="Subtask"
            onChange={(title) => updateSubtask(
              row.category.id,
              row.issue.id,
              row.task.id,
              row.subtask.id,
              { title },
            )}
          />
          <IconBtn
            title="Remove subtask"
            icon="fa-xmark"
            danger
            onClick={() => removeSubtask(row.category.id, row.issue.id, row.task.id, row.subtask.id)}
          />
        </div>
      )
    }
    if (
      row.leafType === 'add-subtask'
      || (row.leafType === 'task' && !(row.task?.subtasks || []).length)
    ) {
      return (
        <SheetAddComposer
          placeholder="+ Add subtask"
          onAdd={(title) => addSubtask(row.category.id, row.issue.id, row.task.id, title)}
        />
      )
    }
    return <span className="text-muted">—</span>
  }

  return (
    <section className="sheet-week-block">
      <header className="sheet-week-block-head">
        <div>
          <strong>Week {week}</strong>
          {range ? <span>{formatChipRange(year, month, range.start, range.end)}</span> : null}
        </div>
        <div className="sheet-week-block-actions">
          <span className="sheet-header-label">Category</span>
          <select
            className="sheet-cell-select sheet-header-category"
            value={creating ? CREATE_CATEGORY : targetCategoryId}
            onChange={(event) => setHeaderCategoryId(event.target.value)}
          >
            {categories.map((category) => (
              <option key={category.id} value={category.id}>{category.name || 'Untitled'}</option>
            ))}
            <option value={CREATE_CATEGORY}>+ Create category</option>
          </select>
          {creating ? (
            <div className="sheet-header-create">
              <input
                className="sheet-cell-input sheet-cell-inline"
                value={newCategoryName}
                placeholder="Category name"
                onChange={(event) => setNewCategoryName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    createCategory()
                  }
                }}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!newCategoryName.trim()}
                onClick={createCategory}
              >
                Add
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="ct-text-btn"
              onClick={() => addIssue(targetCategoryId)}
            >
              + Issue
            </button>
          )}
        </div>
      </header>

      {!rows.length ? (
        <div className="sheet-week-empty">
          <p className="text-muted">No issues in this week yet.</p>
          {targetCategoryId ? (
            <button type="button" className="ct-text-btn" onClick={() => addIssue(targetCategoryId)}>
              + Add first issue
            </button>
          ) : (
            <p className="text-muted">Create a category above, then add an issue.</p>
          )}
        </div>
      ) : (
        <div className="sheet-table-wrap sheet-table-wrap-nested">
          <table className="sheet-table sheet-table-custom">
            <thead>
              <tr>
                <th>Category</th>
                <th>Issue</th>
                <th>Task</th>
                <th>Subtask</th>
                <th>Status</th>
                <th>Due date</th>
                <th>Internal discussion</th>
                <th>Comments</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.category.id}-${row.issue.id}-${row.task?.id || 'issue'}-${row.subtask?.id || row.leafType}`}>
                  {row.showCategory ? (
                    <td rowSpan={row.categoryRowspan} className="sheet-category-cell">
                      <SheetInput
                        value={row.category.name}
                        placeholder="Category"
                        onChange={(name) => updateCategory(row.category.id, { name })}
                      />
                    </td>
                  ) : null}
                  {row.showIssue ? (
                    <td rowSpan={row.issueRowspan} className="sheet-issue-cell">
                      <div className="sheet-inline-field">
                        <SheetInput
                          value={row.issue.title}
                          placeholder="Issue"
                          onChange={(title) => updateIssue(row.category.id, row.issue.id, { title })}
                        />
                        <IconBtn
                          title="Remove issue"
                          icon="fa-trash-can"
                          danger
                          onClick={() => removeIssue(row.category.id, row.issue.id)}
                        />
                        <select
                          className="sheet-cell-select sheet-issue-priority"
                          value={row.issue.priority}
                          onChange={(event) => updateIssue(row.category.id, row.issue.id, { priority: event.target.value })}
                        >
                          {PRIORITIES.map((item) => (
                            <option key={item.id} value={item.id}>{item.label}</option>
                          ))}
                        </select>
                      </div>
                    </td>
                  ) : null}
                  {row.showTask ? (
                    <td rowSpan={row.taskRowspan} className="sheet-task-cell">
                      {renderTaskCell(row)}
                    </td>
                  ) : null}
                  <td className="sheet-subtask-cell">{renderSubtaskCell(row)}</td>
                  <td>{renderStatusControl(row)}</td>
                  <td>{renderDueDate(row)}</td>
                  {row.showIssue ? (
                    <td rowSpan={row.issueRowspan}>
                      <textarea
                        className="sheet-cell-input"
                        rows={3}
                        value={notesToText(row.issue.notes)}
                        placeholder="Internal discussion"
                        onChange={(event) => updateIssue(
                          row.category.id,
                          row.issue.id,
                          { notes: textToNotes(event.target.value, row.issue.notes, author) },
                        )}
                      />
                    </td>
                  ) : null}
                  <td>{renderComment(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function CustomSheetTable({ weeks = [], year, month, author = '', onPatchWeek }) {
  return (
    <div className="sheet-custom-stack">
      <div className="sheet-week-stack">
        {weeks.map((weekDoc) => (
          <CustomSheetWeekTable
            key={weekDoc.week}
            week={weekDoc.week}
            year={year}
            month={month}
            categories={weekDoc.categories || []}
            author={author}
            onPatchWeek={onPatchWeek}
          />
        ))}
      </div>
    </div>
  )
}
