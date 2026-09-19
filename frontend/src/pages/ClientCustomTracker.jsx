import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import CustomBoard from '../components/custom-tracker/CustomBoard'
import { boardCounts } from '../components/custom-tracker/customTrackerUtils'
import TrackerMonthPicker from '../components/tracker/TrackerMonthPicker'
import TrackerViewSwitch from '../components/tracker/TrackerViewSwitch'
import useSnapCurrentWeek from '../components/tracker/useSnapCurrentWeek'
import {
  formatChipRange,
  monthLabel,
  weekRanges,
} from '../components/tracker/trackerUtils'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function ClientCustomTracker() {
  const { client, clientId } = useOutletContext()
  const { token, user } = useAuth()
  const { toast } = useUI()
  const { today, year, month, week, setYear, setMonth, setWeek } = useSnapCurrentWeek()
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [weekSummaries, setWeekSummaries] = useState({})
  const saveTimer = useRef(null)
  const skipNextSave = useRef(true)
  const loadedKey = useRef('')

  const ranges = useMemo(() => weekRanges(year, month), [year, month])

  const loadWeek = useCallback(async (nextClientId, nextYear, nextMonth, nextWeek) => {
    if (!token || !nextClientId) return
    setLoading(true)
    try {
      const result = await api.getCustomTracker(token, nextClientId, nextYear, nextMonth, nextWeek)
      loadedKey.current = `${nextClientId}-${nextYear}-${nextMonth}-${nextWeek}`
      skipNextSave.current = true
      setCategories(result.tracker?.categories || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, toast])

  const loadSummaries = useCallback(async (nextYear, nextMonth) => {
    if (!token || !clientId) return
    try {
      const result = await api.getCustomTrackerMonthSummary(token, clientId, nextYear, nextMonth)
      const map = {}
      for (const row of result.weeks || []) map[row.week] = row
      setWeekSummaries(map)
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, clientId, toast])

  useEffect(() => {
    loadWeek(clientId, year, month, week)
  }, [clientId, year, month, week, loadWeek])

  useEffect(() => {
    loadSummaries(year, month)
  }, [year, month, loadSummaries])

  useEffect(() => {
    if (skipNextSave.current) {
      skipNextSave.current = false
      return
    }
    if (!token || !clientId) return
    const key = `${clientId}-${year}-${month}-${week}`
    if (loadedKey.current !== key) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      if (loadedKey.current !== key) return
      try {
        await api.saveCustomTracker(token, clientId, year, month, week, categories, 0)
        const counts = boardCounts(categories)
        setWeekSummaries((prev) => ({
          ...prev,
          [week]: { week, issues: counts.issues, done: counts.done, open: counts.open },
        }))
      } catch (err) {
        toast(err.message, 'error')
      }
    }, 400)
  }, [categories, token, clientId, year, month, week, toast])

  useEffect(() => () => clearTimeout(saveTimer.current), [])

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
              { label: 'Custom board' },
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
          <p>Week-scoped work board. Same week chips as Content week — a DevRev-style list for everything else.</p>
        </div>
      </header>

      <div className="tracker-week-row">
        {ranges.map((range) => {
          const summary = weekSummaries[range.week] || { issues: 0, open: 0, done: 0 }
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
              <em>{`${summary.open || 0} open · ${summary.issues || 0} issues`}</em>
            </button>
          )
        })}
      </div>

      {loading ? (
        <p className="text-muted" style={{ padding: '16px 0' }}>Loading board…</p>
      ) : (
        <CustomBoard
          categories={categories}
          author={user?.username || ''}
          onChange={setCategories}
        />
      )}
    </div>
  )
}
