"""
Free, local keyphrases per paper (KeyBERT on the shared embedding model).

Candidates come from a vocabulary shared by the batch (n-grams that appear in
at least two papers), so the same phrase is reused across papers. That makes
keyphrases comparable: the frontend counts them per year to surface
"emerging" terms in each cluster.
"""
import re

from src.embeddings.model import Embedder
from src.utils.records import paper_text

_GENERIC = {
    "data", "information", "framework", "approach", "approaches", "method", "methods", "model",
    "models", "system", "systems", "algorithm", "algorithms", "paper", "study", "results", "proposed",
    "based", "using", "novel", "new", "important", "different", "various", "performance", "analysis",
    "research", "work", "problem", "problems", "technique", "techniques", "application", "applications",
    "use", "used", "high", "real", "time", "effective", "efficient", "propose", "present", "presents",
}

# Filler words that make a phrase non-topical when they appear anywhere in it
# ("datasets demonstrate", "deviations expected", "future research").
_WEAK = {
    "demonstrate", "demonstrates", "demonstrated", "show", "shows", "shown", "showed", "expected",
    "important", "selected", "achieve", "achieves", "achieved", "outperforms", "outperform",
    "significantly", "significant", "existing", "recent", "recently", "current", "currently",
    "future", "research", "advancements", "advances", "results", "proposed", "propose", "based",
    "using", "novel", "new", "various", "different", "including", "make", "makes", "paper", "study",
    "studies", "work", "works", "aims", "aim", "addressed", "address", "provide", "provides",
    "effectively", "efficiently", "particularly", "widely", "commonly", "key", "main", "overall",
    "challenges", "challenging", "improve", "improved", "improves", "experiments", "experimental",
    "evaluate", "evaluated", "conducted", "previous", "state", "art", "superior", "better",
}


def _stem(word: str) -> str:
    return re.sub(r"(ing|ed|es|s|al|ions|ion)$", "", word)[:6]


def _pick(candidates: list[tuple[str, float]], n: int) -> list[str]:
    """Drop generic and near-duplicate phrases ('detection anomalous' after 'anomaly detection')."""
    out, seen = [], set()
    for phrase, _score in candidates:
        words = phrase.split()
        if all(w in _GENERIC for w in words) or (len(words) == 1 and len(phrase) < 4):
            continue
        if any(w in _WEAK for w in words) or any(w.isdigit() for w in words):
            continue
        stems = {_stem(w) for w in words if w not in _GENERIC}
        if not stems or stems & seen:
            continue
        out.append(phrase)
        seen |= stems
        if len(out) == n:
            break
    return out


def extract_keywords(papers: list[dict], embedder: Embedder, per_paper: int = 5,
                     on_progress=None) -> None:
    """Fill paper['keywords'] in place for papers that don't have them yet."""
    from keybert import KeyBERT
    from sklearn.feature_extraction.text import CountVectorizer

    todo = [p for p in papers if p.get("keywords") is None and (p.get("title") or p.get("abstract"))]
    if not todo:
        return
    docs = [paper_text(p) for p in todo]
    kb = KeyBERT(model=embedder.model)
    for start in range(0, len(docs), 200):
        chunk = docs[start:start + 200]
        min_df = 2 if len(chunk) >= 10 else 1
        try:
            vec = CountVectorizer(ngram_range=(1, 2), stop_words="english", min_df=min_df)
            results = kb.extract_keywords(chunk, vectorizer=vec, top_n=15)
        except ValueError:  # vocabulary empty (e.g. a tiny batch) -> fall back to per-doc candidates
            results = kb.extract_keywords(chunk, keyphrase_ngram_range=(1, 2), stop_words="english", top_n=15)
        if chunk and results and isinstance(results[0], tuple):  # single doc returns a flat list
            results = [results]
        for paper, cands in zip(todo[start:start + 200], results):
            paper["keywords"] = _pick(cands or [], per_paper)
        if on_progress:
            on_progress(min(start + 200, len(docs)), len(docs))


def label_from_keywords(groups: list[list[dict]], n: int = 3) -> list[list[str]]:
    """
    Distinctive keyphrases per group (cluster), from the per-paper keywords:
    frequent inside the group and rare in the other groups (a TF-IDF over clusters).
    Returns [] for a group whose papers have no keywords.
    """
    import math
    from collections import Counter

    counts = [Counter(k for p in g for k in (p.get("keywords") or [])) for g in groups]
    df = Counter(k for c in counts for k, v in c.items() if v >= 2)
    out = []
    for g, c in zip(groups, counts):
        # log(K/df) is 0 for a phrase present in every group ("anomaly detection" when that is
        # the whole review topic), so shared terms only appear if nothing distinctive is left.
        scored = sorted(
            ((k, (v / max(len(g), 1)) * (math.log(len(groups) / max(df[k], 1)) + 1e-3))
             for k, v in c.items() if v >= 2),
            key=lambda kv: kv[1], reverse=True)
        out.append(_pick(scored, n))
    return out
