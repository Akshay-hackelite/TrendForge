import { NavLink } from 'react-router-dom'

export function NavSection({ title, children }) {
  return (
    <div className="nav-section">
      {title && <div className="nav-section-title">{title}</div>}
      <div className="nav-section-items">{children}</div>
    </div>
  )
}

export function NavItem({ to, end, icon, children, onClick }) {
  if (onClick && !to) {
    return (
      <button type="button" className="menu-item menu-item-btn" onClick={onClick}>
        {icon}
        <span>{children}</span>
      </button>
    )
  }

  return (
    <NavLink to={to} end={end} className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}>
      {icon}
      <span>{children}</span>
    </NavLink>
  )
}
