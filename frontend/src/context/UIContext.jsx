import { createContext, useContext, useState, useCallback } from 'react'

const UIContext = createContext(null)

export function UIProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [confirmState, setConfirmState] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
    onCancel: null,
    isDanger: false,
  })
  const [promptState, setPromptState] = useState({
    isOpen: false,
    title: '',
    placeholder: '',
    defaultValue: '',
    onConfirm: null,
    onCancel: null,
  })

  // Toasts
  const toast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random().toString(36).substr(2, 5)
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }, [])

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Confirm Modal
  const confirm = useCallback(({ title, message, onConfirm, isDanger = false }) => {
    return new Promise((resolve) => {
      setConfirmState({
        isOpen: true,
        title,
        message,
        isDanger,
        onConfirm: () => {
          setConfirmState((prev) => ({ ...prev, isOpen: false }))
          if (onConfirm) onConfirm()
          resolve(true)
        },
        onCancel: () => {
          setConfirmState((prev) => ({ ...prev, isOpen: false }))
          resolve(false)
        },
      })
    })
  }, [])

  // Prompt Modal
  const prompt = useCallback(({ title, placeholder = '', defaultValue = '' }) => {
    return new Promise((resolve) => {
      setPromptState({
        isOpen: true,
        title,
        placeholder,
        defaultValue,
        onConfirm: (val) => {
          setPromptState((prev) => ({ ...prev, isOpen: false }))
          resolve(val)
        },
        onCancel: () => {
          setPromptState((prev) => ({ ...prev, isOpen: false }))
          resolve(null)
        },
      })
    })
  }, [])

  return (
    <UIContext.Provider value={{ toast, confirm, prompt }}>
      {children}

      {/* Toasts Container */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} onClick={() => removeToast(t.id)}>
            <div className="toast-icon">
              {t.type === 'success' && <i className="fa-solid fa-circle-check" />}
              {t.type === 'error' && <i className="fa-solid fa-circle-exclamation" />}
              {t.type === 'info' && <i className="fa-solid fa-circle-info" />}
            </div>
            <div className="toast-message">{t.message}</div>
            <button className="toast-close" onClick={(e) => { e.stopPropagation(); removeToast(t.id); }}>
              <i className="fa-solid fa-xmark" />
            </button>
          </div>
        ))}
      </div>

      {/* Confirm Modal */}
      {confirmState.isOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>{confirmState.title}</h3>
              <button className="modal-close-btn" onClick={confirmState.onCancel}>
                <i className="fa-solid fa-xmark" />
              </button>
            </div>
            <div className="modal-body">
              <p>{confirmState.message}</p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={confirmState.onCancel}>
                Cancel
              </button>
              <button
                className={`btn ${confirmState.isDanger ? 'btn-danger-confirm' : 'btn-primary'}`}
                onClick={confirmState.onConfirm}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Prompt Modal */}
      {promptState.isOpen && (
        <PromptModalComponent
          title={promptState.title}
          placeholder={promptState.placeholder}
          defaultValue={promptState.defaultValue}
          onConfirm={promptState.onConfirm}
          onCancel={promptState.onCancel}
        />
      )}
    </UIContext.Provider>
  )
}

function PromptModalComponent({ title, placeholder, defaultValue, onConfirm, onCancel }) {
  const [value, setValue] = useState(defaultValue)

  const handleSubmit = (e) => {
    e.preventDefault()
    onConfirm(value)
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h3>{title}</h3>
            <button type="button" className="modal-close-btn" onClick={onCancel}>
              <i className="fa-solid fa-xmark" />
            </button>
          </div>
          <div className="modal-body">
            <input
              type="text"
              className="modal-input"
              placeholder={placeholder}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Submit
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function useUI() {
  const context = useContext(UIContext)
  if (!context) throw new Error('useUI must be used within UIProvider')
  return context
}
