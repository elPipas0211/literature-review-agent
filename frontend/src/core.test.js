import { describe, expect, it } from 'vitest'
import { recompute, settingsFromConfig } from './scoring.js'
import { atThreshold, auc, labeledPoints, thresholdForRecall, wilson } from './validation.js'
import { emergingKeywords } from './components/TrendsView.jsx'
import { loadPref, savePref } from './prefs.js'

const settings = settingsFromConfig({
  weights: { semantic: 0.8 }, citation_ref: 300, thresholds: { relevant: 0.55, potentially: 0.35 },
})

describe('client-side scoring (mirrors src/evaluation/scoring.py)', () => {
  it('rescales similarity and labels papers', () => {
    const [low, high, unscored] = recompute([
      { id: 'a', citationCount: 0, evaluation: { similarity: 0.74 } },
      { id: 'b', citationCount: 300, evaluation: { similarity: 0.9 } },
      { id: 'c' },
    ], settings, [0.75, 0.9])
    expect(low.evaluation.semantic_score).toBe(0)
    expect(low.evaluation.category).toBe('no_relevante')
    expect(high.evaluation.score).toBeCloseTo(1)
    expect(high.evaluation.category).toBe('relevante')
    expect(unscored.evaluation).toBeUndefined()
  })
})

describe('ranking validation', () => {
  const papers = [
    { id: 'r1', validation: 'relevant', evaluation: { score: 0.9 } },
    { id: 'r2', validation: 'relevant', evaluation: { score: 0.6 } },
    { id: 'i1', validation: 'irrelevant', evaluation: { score: 0.7 } },
    { id: 'i2', validation: 'irrelevant', evaluation: { score: 0.2 } },
    { id: 'u1', validation: 'unsure', evaluation: { score: 0.5 } },
    { id: 'out', validation: 'relevant', evaluation: { score: 0.1 } },   // not in the sample
  ]
  const pts = labeledPoints(papers, ['r1', 'r2', 'i1', 'i2', 'u1'])

  it('uses only sampled, decided labels', () => {
    expect(pts.map((p) => p.id)).toEqual(['r1', 'r2', 'i1', 'i2'])
  })
  it('computes AUC with ties counted as half', () => {
    expect(auc(pts)).toBeCloseTo(0.75)   // 0.9 beats both; 0.6 beats 0.2 only
    expect(auc([{ score: 0.5, relevant: true }, { score: 0.5, relevant: false }])).toBe(0.5)
    expect(auc([{ score: 1, relevant: true }])).toBeNull()
  })
  it('counts recall and precision at a threshold', () => {
    const m = atThreshold(pts, 0.65)
    expect([m.tp, m.fp, m.fn, m.tn]).toEqual([1, 1, 1, 1])
    expect(m.recall).toBe(0.5)
    expect(m.precision).toBe(0.5)
  })
  it('finds the threshold that keeps the target recall', () => {
    expect(thresholdForRecall(pts, 0.95)).toBe(0.6)
    expect(thresholdForRecall(pts, 0.5)).toBe(0.9)
    expect(thresholdForRecall([], 0.95)).toBeNull()
  })
  it('gives a Wilson interval inside 0..1', () => {
    const [lo, hi] = wilson(9, 10)
    expect(lo).toBeGreaterThan(0.5)
    expect(hi).toBeLessThanOrEqual(1)
    expect(wilson(0, 0)).toBeNull()
  })
})

describe('emerging keywords', () => {
  it('ranks phrases that grew in the last 3 years', () => {
    const now = new Date().getFullYear()
    const papers = [
      ...Array.from({ length: 4 }, () => ({ year: now, keywords: ['transformer'] })),
      ...Array.from({ length: 4 }, () => ({ year: now - 8, keywords: ['autoencoder'] })),
      { year: now, keywords: ['autoencoder'] }, { year: now - 1, keywords: ['autoencoder'] },
    ]
    const top = emergingKeywords(papers, 2)
    expect(top[0].k).toBe('transformer')
  })
})

describe('preferences', () => {
  it('never throws when storage is unavailable', () => {
    // vitest's default node environment has no localStorage at all
    expect(() => savePref('x', { a: 1 })).not.toThrow()
    expect(loadPref('x', 'fallback')).toBe('fallback')
  })
})
