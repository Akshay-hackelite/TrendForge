import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import Breadcrumbs from '../components/Breadcrumbs'
import CustomSheetTable from '../components/tracker-sheet/CustomSheetTable'
import TrackerSheetViewSwitch from '../components/tracker-sheet/TrackerSheetViewSwitch'
import WeeklySheetTable from '../components/tracker-sheet/WeeklySheetTable'
import TrackerMonthPicker from '../components/tracker/TrackerMonthPicker'
import { monthLabel, todayParts } from '../components/tracker/trackerUtils'
import api from '../api'
import { useAuth } from '../context/AuthContext'
import { useUI } from '../context/UIContext'

export default function TrackerClientSheet({ mode = 'weekly' }) {
  const { clientId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { token, user } = useAuth()
  const { toast } = useUI()
  const today = useMemo(() => todayParts(), [])
  const year = Number(searchParams.get('year')) || today.year
  const month = Number(searchParams.get('month')) || today.month

  const [clientName, setClientName] = useState('')
  const [weeklyRows, setWeeklyRows] = useState([])
  const [weeklyComments, setWeeklyComments] = useState({})
  const [customWeeks, setCustomWeeks] = useState([])
  const [loading, setLoading] = useState(true)
  const saveTimers = useRef({})

  const setMonth = useCallback((nextYear, nextMonth) => {
    setSearchParams({ year: String(nextYear), month: String(nextMonth) })
  }, [setSearchParams])

  const loadClientName = useCallback(async () => {
    if (!token) return
    try {
      const result = await api.getTrackerSheetClients(token)
      const match = (result.clients || []).find((row) => row.client_id === clientId)
      setClientName(match?.name || 'Client')
    } catch (err) {
      toast(err.message, 'error')
    }
  }, [token, clientId, toast])

  const loadWeekly = useCallback(async () => {
    if (!token || !clientId) return
    setLoading(true)
    try {
      const result = await api.getTrackerSheetWeekly(token, clientId, year, month)
      setWeeklyRows(result.rows || [])
      setWeeklyComments(result.comments || {})
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, year, month, toast])

  const loadCustom = useCallback(async () => {
    if (!token || !clientId) return
    setLoading(true)
    try {
      const result = await api.getTrackerSheetCustom(token, clientId, year, month)
      const weeks = (result.weeks || []).map((weekDoc) => {
        const categories = weekDoc.categories || []
        const pruned = categories.filter((category) => (
          (category.name || '').trim() !== 'New category' || (category.issues || []).length > 0
        ))
        return {
          ...weekDoc,
          categories: pruned,
          pruned: pruned.length !== categories.length,
        }
      })
      setCustomWeeks(weeks.map(({ pruned, ...weekDoc }) => weekDoc))
      await Promise.all(
        weeks
          .filter((weekDoc) => weekDoc.pruned)
          .map((weekDoc) => api.saveCustomTracker(
            token,
            clientId,
            year,
            month,
            weekDoc.week,
            weekDoc.categories,
            0,
          )),
      )
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [token, clientId, year, month, toast])

  useEffect(() => {
    loadClientName()
  }, [loadClientName])

  useEffect(() => {
    if (mode === 'weekly') loadWeekly()
    else loadCustom()
  }, [mode, loadWeekly, loadCustom])

  useEffect(() => () => {
    Object.values(saveTimers.current).forEach(clearTimeout)
  }, [])

  async function saveWeeklyComment(row, comment) {
    if (!token || !clientId) return
    setWeeklyComments((prev) => ({ ...prev, [row.row_key]: comment }))
    try {
      await api.saveTrackerSheetComment(token, {
        clientId,
        year,
        month,
        week: row.week,
        rowKey: row.row_key,
        comment,
      })
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  function patchCustomWeek(week, mutator) {
    setCustomWeeks((prev) => {
      const next = prev.map((row) => {
        if (row.week !== week) return row
        const categories = JSON.parse(JSON.stringify(row.categories || []))
        const result = mutator(categories)
        return { ...row, categories: Array.isArray(result) ? result : categories }
      })
      const categories = next.find((row) => row.week === week)?.categories || []
      clearTimeout(saveTimers.current[week])
      saveTimers.current[week] = setTimeout(async () => {
        if (!token || !clientId) return
        try {
          await api.saveCustomTracker(token, clientId, year, month, week, categories, 0)
        } catch (err) {
          toast(err.message, 'error')
        }
      }, 500)
      return next
    })
  }

  function shiftMonth(delta) {
    const date = new Date(year, month - 1 + delta, 1)
    setMonth(date.getFullYear(), date.getMonth() + 1)
  }

  return (
    <div className="weekly-tracker-page tracker-sheet-page">
      <header className="content-header">
        <div className="greeting">
          <Breadcrumbs
            items={[
              { label: 'All trackers', to: '/tracker' },
              { label: clientName },
            ]}
          />
          <TrackerSheetViewSwitch clientId={clientId} year={year} month={month} />
          <div className="tracker-month-nav">
            <h1>{clientName}</h1>
            <div className="tracker-month-switch">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => shiftMonth(-1)}>
                <i className="fa-solid fa-chevron-left" />
              </button>
              <TrackerMonthPicker year={year} month={month} onSelect={setMonth} />
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => shiftMonth(1)}>
                <i className="fa-solid fa-chevron-right" />
              </button>
            </div>
          </div>
          <p>
            {mode === 'weekly'
              ? `Default tracker sheet for ${monthLabel(year, month)}. Stage and links are read-only; add notes in Comments.`
              : `Custom tracker sheet for ${monthLabel(year, month)}. Edits sync to the client custom board.`}
          </p>
          <Link className="tracker-text-btn" to={`/clients/${clientId}/videos/tracker`}>
            Open client tracker view
          </Link>
        </div>
      </header>

      {loading ? (
        <p className="text-muted sheet-empty">Loading sheet…</p>
      ) : mode === 'weekly' ? (
        <WeeklySheetTable
          rows={weeklyRows}
          comments={weeklyComments}
          year={year}
          month={month}
          onCommentSave={saveWeeklyComment}
        />
      ) : (
        <CustomSheetTable
          weeks={customWeeks}
          year={year}
          month={month}
          author={user?.username || ''}
          onPatchWeek={patchCustomWeek}
        />
      )}
    </div>
  )
}
