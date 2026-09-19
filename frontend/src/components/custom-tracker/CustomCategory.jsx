import CustomIssue from './CustomIssue'
import { categoryIssueCount, emptyIssue } from './customTrackerUtils'

export default function CustomCategory({ category, author = '', onChange, onRemove }) {
  function patch(next) {
    onChange({ ...category, ...next })
  }

  function addIssue() {
    patch({
      collapsed: false,
      issues: [...(category.issues || []), emptyIssue()],
    })
  }

  return (
    <section className={`ct-category${category.collapsed ? ' is-collapsed' : ''}`}>
      <header className="ct-category-head">
        <button
          type="button"
          className="ct-icon-btn"
          onClick={() => patch({ collapsed: !category.collapsed })}
          title={category.collapsed ? 'Expand' : 'Collapse'}
        >
          <i className={`fa-solid ${category.collapsed ? 'fa-chevron-right' : 'fa-chevron-down'}`} />
        </button>
        <i className="fa-solid fa-layer-group ct-cat-icon" />
        <input
          className="ct-category-name"
          value={category.name}
          onChange={(e) => patch({ name: e.target.value })}
        />
        <span className="ct-category-count">{categoryIssueCount(category)} {categoryIssueCount(category) === 1 ? 'issue' : 'issues'}</span>
        <button type="button" className="ct-text-btn" onClick={addIssue}>+ Add issue</button>
        <button type="button" className="ct-icon-btn" title="Remove category" onClick={onRemove}>
          <i className="fa-regular fa-trash-can" />
        </button>
      </header>
      {!category.collapsed && (
        <div className="ct-category-body">
          {(category.issues || []).length === 0 ? (
            <p className="ct-empty">No issues in this domain yet.</p>
          ) : (
            (category.issues || []).map((issue) => (
              <CustomIssue
                key={issue.id}
                issue={issue}
                author={author}
                onChange={(next) => patch({
                  issues: (category.issues || []).map((row) => (row.id === issue.id ? next : row)),
                })}
                onRemove={() => patch({
                  issues: (category.issues || []).filter((row) => row.id !== issue.id),
                })}
              />
            ))
          )}
        </div>
      )}
    </section>
  )
}
