import { useState } from 'react'
import CustomCategory from './CustomCategory'
import { categoryIssueCount, emptyCategory } from './customTrackerUtils'

export default function CustomBoard({ categories, author = '', onChange }) {
  const [adding, setAdding] = useState(false)
  const [draftName, setDraftName] = useState('')

  function patchCategory(nextCategory) {
    onChange((categories || []).map((row) => (row.id === nextCategory.id ? nextCategory : row)))
  }

  function addCategory() {
    const name = draftName.trim()
    if (!name) return
    onChange([...(categories || []), emptyCategory(name)])
    setDraftName('')
    setAdding(false)
  }

  return (
    <div className="ct-board">
      <div className="ct-board-head">
        <div>
          <h2>To-dos by domain</h2>
          <p>Issues, tasks, and the small steps that move work forward.</p>
        </div>
        {adding ? (
          <div className="ct-add-category">
            <input
              className="form-control"
              autoFocus
              value={draftName}
              placeholder="Category name"
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addCategory()
                if (e.key === 'Escape') setAdding(false)
              }}
            />
            <button type="button" className="btn btn-primary btn-sm" onClick={addCategory}>Add</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => setAdding(true)}>
            + Add category
          </button>
        )}
      </div>

      <div className="ct-jump">
        {(categories || []).map((category) => (
          <button
            type="button"
            key={category.id}
            className="ct-jump-pill"
            onClick={() => {
              const el = document.querySelector(`[data-ct-category="${category.id}"]`)
              el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
          >
            <i className="fa-solid fa-layer-group" />
            <span>{category.name || 'Untitled'}</span>
            <em>{categoryIssueCount(category)}</em>
          </button>
        ))}
      </div>

      <div className="ct-category-stack">
        {(categories || []).map((category) => (
          <div key={category.id} data-ct-category={category.id}>
            <CustomCategory
              category={category}
              author={author}
              onChange={patchCategory}
              onRemove={() => onChange((categories || []).filter((row) => row.id !== category.id))}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
