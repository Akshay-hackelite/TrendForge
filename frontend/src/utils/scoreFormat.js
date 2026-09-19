/** Combined recommendation score (priority + trend share), one decimal everywhere. */
export function formatRecommendationScore(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return '0.0'
  return n.toFixed(1)
}
