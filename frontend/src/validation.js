// Ranking validation: how well does the relevance score separate papers that a
// human judged relevant from those judged irrelevant, in a simple random sample?
// Pure functions so they can be unit-tested.

/** Labeled sample papers with their (live) score: [{ id, score, relevant }]. */
export function labeledPoints(papers, sampleIds) {
  const inSample = new Set(sampleIds || [])
  return papers
    .filter((p) => inSample.has(p.id) && (p.validation === 'relevant' || p.validation === 'irrelevant'))
    .map((p) => ({ id: p.id, title: p.title, score: p.evaluation?.score ?? 0, relevant: p.validation === 'relevant' }))
}

/** Probability that a random relevant paper scores higher than a random irrelevant one (ties count ½). */
export function auc(points) {
  const pos = points.filter((p) => p.relevant).map((p) => p.score)
  const neg = points.filter((p) => !p.relevant).map((p) => p.score)
  if (!pos.length || !neg.length) return null
  let wins = 0
  for (const a of pos) for (const b of neg) wins += a > b ? 1 : a === b ? 0.5 : 0
  return wins / (pos.length * neg.length)
}

/** Confusion counts if everything with score ≥ threshold were kept for screening. */
export function atThreshold(points, threshold) {
  let tp = 0, fp = 0, fn = 0, tn = 0
  for (const p of points) {
    const kept = p.score >= threshold
    if (p.relevant) kept ? tp++ : fn++
    else kept ? fp++ : tn++
  }
  return {
    tp, fp, fn, tn,
    kept: tp + fp,
    recall: tp + fn ? tp / (tp + fn) : null,
    precision: tp + fp ? tp / (tp + fp) : null,
  }
}

/** Wilson 95% interval for a proportion k/n. */
export function wilson(k, n, z = 1.96) {
  if (!n) return null
  const p = k / n
  const d = 1 + (z * z) / n
  const c = (p + (z * z) / (2 * n)) / d
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d
  return [Math.max(0, c - h), Math.min(1, c + h)]
}

/**
 * Highest threshold that still keeps at least `target` of the relevant papers
 * in the sample (e.g. 0.95). Null when no paper is labeled relevant.
 */
export function thresholdForRecall(points, target = 0.95) {
  const rel = points.filter((p) => p.relevant).map((p) => p.score).sort((a, b) => b - a)
  if (!rel.length) return null
  const k = Math.ceil(target * rel.length)
  return rel[k - 1]
}

export const pct = (x, digits = 0) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`)
