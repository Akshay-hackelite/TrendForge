import { useState, useRef, useEffect } from 'react'

export default function CustomSelect({
  options = [],
  value,
  onChange,
  placeholder = 'Select option',
  searchable = false,
  icon = null,
  className = '',
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const containerRef = useRef(null)

  // Find currently selected option
  const selectedOption = options.find((opt) => String(opt.value) === String(value))

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Reset search when opening/closing
  useEffect(() => {
    if (!isOpen) {
      setSearchTerm('')
    }
  }, [isOpen])

  const filteredOptions = searchable
    ? options.filter((opt) =>
        String(opt.label).toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(opt.detail || '').toLowerCase().includes(searchTerm.toLowerCase())
      )
    : options

  return (
    <div className={`custom-select-container ${className}`} ref={containerRef}>
      <button
        type="button"
        className={`custom-select-trigger ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="custom-select-trigger-content">
          {icon && <span className="custom-select-trigger-icon">{icon}</span>}
          <span className="custom-select-trigger-label">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          {selectedOption?.badge && (
            <span className="custom-select-badge">{selectedOption.badge}</span>
          )}
        </span>
        <i className={`fa-solid fa-chevron-down select-arrow-icon ${isOpen ? 'open' : ''}`} />
      </button>

      {isOpen && (
        <div className="custom-select-dropdown">
          {searchable && (
            <div className="custom-select-search-wrapper">
              <i className="fa-solid fa-magnifying-glass search-icon" />
              <input
                type="text"
                className="custom-select-search-input"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                autoFocus
              />
            </div>
          )}

          <div className="custom-select-options-list" role="listbox">
            {filteredOptions.length === 0 ? (
              <div className="custom-select-no-results">No options found</div>
            ) : (
              filteredOptions.map((opt) => {
                const isSelected = String(opt.value) === String(value)
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className={`custom-select-option ${isSelected ? 'selected' : ''}`}
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => {
                      onChange(opt.value)
                      setIsOpen(false)
                    }}
                  >
                    <span className="custom-select-option-left">
                      {opt.icon && <span className="custom-select-option-icon">{opt.icon}</span>}
                      <span className="custom-select-option-text">
                        <span className="custom-select-option-label">{opt.label}</span>
                        {opt.detail && (
                          <span className="custom-select-option-detail">{opt.detail}</span>
                        )}
                      </span>
                    </span>
                    <span className="custom-select-option-right">
                      {opt.badge && (
                        <span className="custom-select-badge">{opt.badge}</span>
                      )}
                      {isSelected && (
                        <i className="fa-solid fa-check option-check-icon" />
                      )}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
