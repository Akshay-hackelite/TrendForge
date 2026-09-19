import { STAGES, TYPE_LABELS } from '../tracker/trackerUtils'

export function stageLabel(cardType, stageId) {
  const stages = STAGES[cardType] || []
  const match = stages.find((row) => row.id === stageId)
  return match?.label || stageId?.replace(/_/g, ' ') || ''
}

export function typeLabel(cardType) {
  return TYPE_LABELS[cardType] || cardType || ''
}

export function typePillClass(cardType) {
  const map = {
    long_video: 'tracker-pill-blue',
    short: 'tracker-pill-pink',
    static_post: 'tracker-pill-gold',
    blog: 'tracker-pill-green',
  }
  return map[cardType] || 'tracker-pill-blue'
}

export function stagePillClass(stageId) {
  if (stageId === 'posted' || stageId === 'published') return 'sheet-pill-done'
  if (stageId === 'planned') return 'sheet-pill-planned'
  return 'sheet-pill-progress'
}

export function notesToText(notes = []) {
  return (notes || [])
    .map((note) => String(note?.text || '').trim())
    .filter(Boolean)
    .join('\n')
}

export function textToNotes(text, existingNotes = [], author = '') {
  const lines = String(text || '').split('\n').map((line) => line.trim()).filter(Boolean)
  if (!lines.length) return []
  return lines.map((line, index) => {
    const existing = existingNotes[index]
    if (existing?.id) return { ...existing, text: line }
    return {
      id: `note-${Date.now()}-${index}`,
      text: line,
      created_by: author,
      created_at: new Date().toISOString(),
    }
  })
}

function pushTaskRows(rows, week, category, issue, task) {
  const subtasks = task.subtasks || []
  rows.push({
    week,
    category,
    issue,
    task,
    subtask: null,
    leaf: task,
    leafType: 'task',
    isTaskAnchor: true,
  })
  for (const subtask of subtasks) {
    rows.push({
      week,
      category,
      issue,
      task,
      subtask,
      leaf: subtask,
      leafType: 'subtask',
    })
  }
  if (subtasks.length) {
    rows.push({
      week,
      category,
      issue,
      task,
      subtask: null,
      leaf: null,
      leafType: 'add-subtask',
    })
  }
}

export function buildCustomSheetRows(weeks = []) {
  const flat = []
  for (const weekDoc of weeks) {
    const week = weekDoc.week
    for (const category of weekDoc.categories || []) {
      for (const issue of category.issues || []) {
        const tasks = issue.tasks || []
        if (!tasks.length) {
          flat.push({
            week,
            category,
            issue,
            task: null,
            subtask: null,
            leaf: issue,
            leafType: 'issue',
          })
          continue
        }
        for (const task of tasks) {
          pushTaskRows(flat, week, category, issue, task)
        }
        flat.push({
          week,
          category,
          issue,
          task: null,
          subtask: null,
          leaf: null,
          leafType: 'add-task',
        })
      }
    }
  }

  const rows = []
  let index = 0
  while (index < flat.length) {
    const week = flat[index].week
    let weekEnd = index
    while (weekEnd < flat.length && flat[weekEnd].week === week) weekEnd += 1
    const weekSpan = weekEnd - index

    let cursor = index
    while (cursor < weekEnd) {
      const category = flat[cursor].category
      let catEnd = cursor
      while (catEnd < weekEnd && flat[catEnd].category.id === category.id) catEnd += 1
      const catSpan = catEnd - cursor

      let issueCursor = cursor
      while (issueCursor < catEnd) {
        const issue = flat[issueCursor].issue
        let issueEnd = issueCursor
        while (issueEnd < catEnd && flat[issueEnd].issue.id === issue.id) issueEnd += 1
        const issueSpan = issueEnd - issueCursor

        let taskCursor = issueCursor
        while (taskCursor < issueEnd) {
          const task = flat[taskCursor].task
          let taskEnd = taskCursor
          if (!task) {
            taskEnd = taskCursor + 1
          } else {
            while (
              taskEnd < issueEnd
              && flat[taskEnd].task?.id === task.id
            ) taskEnd += 1
          }
          const taskSpan = taskEnd - taskCursor

          for (let rowIndex = taskCursor; rowIndex < taskEnd; rowIndex += 1) {
            const source = flat[rowIndex]
            rows.push({
              ...source,
              showWeek: rowIndex === index,
              weekRowspan: weekSpan,
              showCategory: rowIndex === cursor,
              categoryRowspan: catSpan,
              showIssue: rowIndex === issueCursor,
              issueRowspan: issueSpan,
              showTask: rowIndex === taskCursor,
              taskRowspan: taskSpan,
              showSubtask: Boolean(source.subtask) || !source.task,
            })
          }
          taskCursor = taskEnd
        }
        issueCursor = issueEnd
      }
      cursor = catEnd
    }
    index = weekEnd
  }
  return rows
}
