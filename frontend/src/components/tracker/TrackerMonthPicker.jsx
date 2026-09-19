import { useEffect, useRef, useState } from 'react'
import { monthLabel } from './trackerUtils'

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function TrackerMonthPicker({ year, month, onSelect }) {
  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(year)
  const ref = useRef(null)

  useEffect(() => {
    if (open) setViewYear(year)
  }, [open, year])

  useEffect(() => {
    if (!open) return undefined
    function onDoc(event) {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false)
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="tracker-month-picker" ref={ref}>
      <button
        type="button"
        className="tracker-month-picker-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {monthLabel(year, month)}
        <i className={`fa-solid ${open ? 'fa-chevron-up' : 'fa-chevron-down'}`} />
      </button>
      {open && (
        <div className="tracker-month-popover">
          <div className="tracker-month-year-row">
            <button type="button" className="tracker-icon-btn" onClick={() => setViewYear((value) => value - 1)} aria-label="Previous year">
              <i className="fa-solid fa-chevron-left" />
            </button>
            <strong>{viewYear}</strong>
            <button type="button" className="tracker-icon-btn" onClick={() => setViewYear((value) => value + 1)} aria-label="Next year">
              <i className="fa-solid fa-chevron-right" />
            </button>
          </div>
          <div className="tracker-month-grid">
            {MONTH_NAMES.map((name, index) => {
              const value = index + 1
              const active = viewYear === year && value === month
              return (
                <button
                  type="button"
                  key={name}
                  className={`tracker-month-cell${active ? ' is-active' : ''}`}
                  onClick={() => {
                    onSelect(viewYear, value)
                    setOpen(false)
                  }}
                >
                  {name}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
