import { NavLink } from 'react-router-dom'

export default function TrackerSheetViewSwitch({ clientId, year, month }) {
  const base = `/tracker/${clientId}`
  const query = `?year=${year}&month=${month}`
  return (
    <div className="segmented-control tracker-view-switch">
      <NavLink to={`${base}${query}`} end className={({ isActive }) => (isActive ? 'active' : '')}>
        Default trackers
      </NavLink>
      <NavLink to={`${base}/custom${query}`} className={({ isActive }) => (isActive ? 'active' : '')}>
        Custom trackers
      </NavLink>
    </div>
  )
}
