import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { todayParts } from './trackerUtils'

export default function useSnapCurrentWeek() {
  const location = useLocation()
  const today = useMemo(() => todayParts(), [location.pathname])
  const [year, setYear] = useState(today.year)
  const [month, setMonth] = useState(today.month)
  const [week, setWeek] = useState(today.week)

  useEffect(() => {
    setYear(today.year)
    setMonth(today.month)
    setWeek(today.week)
  }, [today.year, today.month, today.week])

  return { today, year, month, week, setYear, setMonth, setWeek }
}
