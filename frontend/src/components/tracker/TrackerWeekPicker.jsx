import { useMemo, useState } from 'react'
import TrackerMonthPicker from './TrackerMonthPicker'
import { formatChipRange, todayParts, weekRanges } from './trackerUtils'

export default function TrackerWeekPicker({
  onConfirm,
  onCancel,
  busy = false,
}) {
  const today = useMemo(() => todayParts(), [])
  const [year, setYear] = useState(today.year)
  const [month, setMonth] = useState(today.month)
  const ranges = useMemo(() => weekRanges(year, month), [year, month])

  return (
    <div className="tracker-week-mini" onClick={(e) => e.stopPropagation()}>
      <div className="tracker-week-mini-head">
        <TrackerMonthPicker
          year={year}
          month={month}
          onSelect={(nextYear, nextMonth) => {
            setYear(nextYear)
            setMonth(nextMonth)
          }}
        />
        {onCancel && (
          <button type="button" className="tracker-text-btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <div className="tracker-week-mini-list">
        {ranges.map((range) => (
          <button
            type="button"
            key={range.week}
            className={`tracker-week-mini-row${range.week === today.week && year === today.year && month === today.month ? ' is-current' : ''}`}
            disabled={busy}
            onClick={() => onConfirm({ year, month, week: range.week })}
          >
            <strong>Week {range.week}</strong>
            <span>{formatChipRange(year, month, range.start, range.end)}</span>
          </button>
        ))}
      </div>
      {busy ? <p className="tracker-hint">Adding…</p> : null}
    </div>
  )
}
