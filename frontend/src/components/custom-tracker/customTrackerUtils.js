import { newId } from '../tracker/trackerUtils'

export const STATUSES = [
  { id: 'todo', label: 'To do' },
  { id: 'in_progress', label: 'In progress' },
  { id: 'done', label: 'Done' },
]

export const PRIORITIES = [
  { id: 'p0', label: 'P0' },
  { id: 'p1', label: 'P1' },
  { id: 'p2', label: 'P2' },
]

export function emptyCategory(name = 'New category') {
  return {
    id: newId('cat'),
    name,
    is_default: false,
    collapsed: false,
    issues: [],
  }
}

export function emptyIssue() {
  return {
    id: newId('iss'),
    display_id: '',
    title: '',
    status: 'todo',
    priority: 'p1',
    collapsed: false,
    comment: '',
    tasks: [],
    notes: [],
  }
}

export function emptyTask(title = '') {
  return {
    id: newId('tsk'),
    title,
    done: false,
    due_date: '',
    comment: '',
    subtasks: [],
  }
}

export function emptySubtask(title = '') {
  return {
    id: newId('sub'),
    title,
    done: false,
    due_date: '',
    comment: '',
  }
}

export function emptyNote(text, author = '') {
  return {
    id: newId('note'),
    text,
    created_by: author,
    created_at: new Date().toISOString(),
  }
}

export function formatDueDate(iso) {
  if (!iso) return ''
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return iso
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function categoryIssueCount(category) {
  return (category.issues || []).length
}

export function boardCounts(categories = []) {
  let issues = 0
  let done = 0
  for (const category of categories) {
    for (const issue of category.issues || []) {
      issues += 1
      if (issue.status === 'done') done += 1
    }
  }
  return { issues, done, open: issues - done }
}
