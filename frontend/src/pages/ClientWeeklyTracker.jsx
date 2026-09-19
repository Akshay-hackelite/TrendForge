import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import TrackerMonthPicker from '../components/tracker/TrackerMonthPicker'
import TrackerViewSwitch from '../components/tracker/TrackerViewSwitch'
import TrackerWeekBoard from '../components/tracker/TrackerWeekBoard'
import useSnapCurrentWeek from '../components/tracker/useSnapCurrentWeek'
import {
  EMPTY_WEEK_SUMMARY,
  formatChipRange,
  monthLabel,
  weekRanges,
} from '../components/tracker/trackerUtils'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientWeeklyTracker() {
  const { client, clientId } = useOutletContext()
  const { token } = useAuth()
  const { toast } = useUI()
  const { today, year, month, week, setYear, setMonth, setWeek } = useSnapCurrentWeek()
  const [weekSummaries, setWeekSummaries] = useState({})
  const loadedMonth = useRef('')

  const ranges = useMemo(() => weekRanges(year, month), [year, month])

  const loadSummaries = useCallback(async (nextYear, nextMonth) => {
    if (!token || !clientId) return
    try {
      const result = await api.getWeeklyTrackerMonthSummary(token, clientId, nextYear, nextMonth)
      const map = {}
      for (const row of result.weeks || []) map[row.week] = row
      loadedMonth.current = `${nextYear}-${nextMonth}`
      setWeekSummaries(map)
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, clientId, toast])

  useEffect(() => {
    loadSummaries(year, month)
  }, [year, month, loadSummaries])

  function handleBoardSummary(_clientId, nextWeek, summary) {
    if (loadedMonth.current !== `${year}-${month}`) return
    setWeekSummaries((prev) => ({ ...prev, [nextWeek]: summary }))
  }

  function applyMonth(nextYear, nextMonth) {
    setYear(nextYear)
    setMonth(nextMonth)
    const isCurrent = nextYear === today.year && nextMonth === today.month
    setWeek(isCurrent ? today.week : 1)
  }

  function shiftMonth(delta) {
    const date = new Date(year, month - 1 + delta, 1)
    applyMonth(date.getFullYear(), date.getMonth() + 1)
  }

  const isCurrentMonth = year === today.year && month === today.month

  return (
    <div className="weekly-tracker-page">
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'Clients', to: '/clients' },
              { label: client?.name || 'Client', to: `/clients/${clientId}/videos` },
              { label: 'Weekly tracker' },
            ]}
          />
          <TrackerViewSwitch clientId={clientId} />
          <div className="tracker-month-nav">
            <h1>{monthLabel(year, month)}</h1>
            <div className="tracker-month-switch">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => shiftMonth(-1)}>
                <i className="fa-solid fa-chevron-left" />
              </button>
              <TrackerMonthPicker year={year} month={month} onSelect={applyMonth} />
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => shiftMonth(1)}>
                <i className="fa-solid fa-chevron-right" />
              </button>
            </div>
          </div>
          <p>
            Today is {today.date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}.
            Every move is stamped with who made it.
          </p>
        </div>
      </header>

      <div className="tracker-week-row">
        {ranges.map((range) => {
          const summary = weekSummaries[range.week] || EMPTY_WEEK_SUMMARY
          const isNow = isCurrentMonth && today.week === range.week
          return (
            <button
              type="button"
              key={range.week}
              className={`tracker-week-chip${week === range.week ? ' is-active' : ''}`}
              onClick={() => setWeek(range.week)}
            >
              <div className="tracker-week-chip-top">
                <strong>Week {range.week}</strong>
                {isNow ? <span className="tracker-now">NOW</span> : null}
              </div>
              <small>{formatChipRange(year, month, range.start, range.end)}</small>
              <em>{`${summary.out}/${summary.total} out · ${summary.to_start} to start`}</em>
            </button>
          )
        })}
      </div>

      <TrackerWeekBoard
        clientId={clientId}
        year={year}
        month={month}
        week={week}
        onSummaryChange={handleBoardSummary}
      />
    </div>
  )
}
