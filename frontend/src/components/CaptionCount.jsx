export const IG_CAPTION_MAX = 2200

export function captionTooLong(value) {
  return String(value || '').length > IG_CAPTION_MAX
}

export default function CaptionCount({ value }) {
  const count = String(value || '').length
  const over = count > IG_CAPTION_MAX
  return (
    <small className={`char-count${over ? ' is-over' : ''}`}>
      {count} / {IG_CAPTION_MAX}
    </small>
  )
}
