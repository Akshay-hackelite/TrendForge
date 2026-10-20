export default function PublishProgressBusy({ stage, elapsed }) {
  const minutes = Math.floor((elapsed || 0) / 60)
  const seconds = String((elapsed || 0) % 60).padStart(2, '0')
  return (
    <span className="publish-progress-busy">
      <span>
        <i className="fa-solid fa-spinner fa-spin" /> {stage || 'Starting publish…'} ({minutes}:{seconds})
      </span>
      <small>Keep this tab open. Do not refresh.</small>
    </span>
  )
}
