export default function ConfirmModal({ isOpen, title, message, onConfirm, onCancel, confirmText = 'Delete', confirmColor = 'danger' }) {
  if (!isOpen) return null
  return (
    <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1050 }}>
      <div className="modal card" style={{ width: '90%', maxWidth: '400px', padding: '24px' }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px' }}>{title}</h3>
        <p style={{ marginBottom: '24px', color: '#475569' }}>{message}</p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className={`btn btn-${confirmColor}`} onClick={onConfirm}>{confirmText}</button>
        </div>
      </div>
    </div>
  )
}
