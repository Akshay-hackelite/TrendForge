import { useEffect, useRef, useState } from 'react'

export default function SheetCommentCell({ value, onSave, disabled = false }) {
  const [draft, setDraft] = useState(value || '')
  const timer = useRef(null)

  useEffect(() => {
    setDraft(value || '')
  }, [value])

  useEffect(() => () => clearTimeout(timer.current), [])

  function scheduleSave(next) {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onSave(next), 400)
  }

  return (
    <textarea
      className="sheet-cell-input"
      rows={2}
      value={draft}
      disabled={disabled}
      placeholder="Add a comment"
      onChange={(event) => {
        const next = event.target.value
        setDraft(next)
        scheduleSave(next)
      }}
      onBlur={() => {
        clearTimeout(timer.current)
        onSave(draft)
      }}
    />
  )
}
