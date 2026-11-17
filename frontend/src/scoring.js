// ── Client-side re-scoring ─────────────────────────────────────────────────────
// Mirrors src/evaluation/scoring.py so weights/thresholds can be tuned live.
// Nothing is ever removed: the category is only a label used for filtering.
export function recompute(papers, s, simRange) {
  if (!s || !simRange) return papers
  const [lo, hi] = simRange
  return papers.map((paper) => {
    const ev = paper.evaluation
    if (!ev || ev.similarity == null) return paper
    const sem = Math.min(1, Math.max(0, (ev.similarity - lo) / Math.max(hi - lo, 1e-9)))
    const imp = Math.min(Math.log1p(Math.max(0, paper.citationCount || 0)) / Math.log1p(Math.max(1, s.citationRef)), 1)
    const score = s.weightSemantic * sem + (1 - s.weightSemantic) * imp
    const category =
      score >= s.thresholdRelevant ? 'relevante'
      : score >= s.thresholdPotential ? 'potencialmente_relevante'
      : 'no_relevante'
    return {
      ...paper,
      evaluation: { ...ev, semantic_score: sem, impact_score: imp, score, category },
    }
  })
}

export function settingsFromConfig(ev) {
  return {
    weightSemantic:     ev.weights.semantic,
    citationRef:        ev.citation_ref,
    thresholdRelevant:  ev.thresholds.relevant,
    thresholdPotential: ev.thresholds.potentially,
  }
}
