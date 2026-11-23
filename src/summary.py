"""
Library summary: an overview of a set of papers, built locally and for free.

It is *extractive*: nothing is written by an AI. Abstracts are split into
sentences, embedded with the same multilingual model used for ranking, and
the app picks

  * for each topic (cluster), the sentences closest to the topic's centre,
    from different papers - "what these papers say", each with its APA in-text
    citation so it can be quoted or paraphrased;
  * for each paper, the sentence closest to your research question - why the
    paper matters for you.

Around that it adds counts per year, top venues and authors, the most cited
papers, the surveys to read first and the reading list with your notes.
"""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from typing import Callable

import numpy as np

from src.embeddings.model import get_embedder
from src.storage.project_manager import ProjectManager
from src.utils.apa import apa_in_text
from src.utils.bibtex_exporter import split_name

Emit = Callable[[dict], None]

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(\[])")
_BOILERPLATE = re.compile(
    r"©|\(c\)\s*\d{4}|copyright|all rights reserved|published by|licensee|creative commons|"
    r"this is an open access|the author\(s\)|elsevier|springer nature|ieee\.|mdpi", re.IGNORECASE)
MAX_PAPERS_PER_SENTENCE_LIST = 300


def split_sentences(abstract: str) -> list[str]:
    """Abstract → informative sentences (boilerplate and fragments dropped)."""
    out = []
    text = " ".join((abstract or "").split())
    # Scopus/WoS abstracts often end with "© 2021 Elsevier Ltd. All rights reserved." glued to
    # the last real sentence: cut the notice off first so that sentence is kept.
    text = re.split(r"\s*(?:©|\(c\)\s*\d{4}|\bcopyright\b)", text, maxsplit=1, flags=re.IGNORECASE)[0]
    for s in _SPLIT.split(text):
        s = s.strip()
        if 40 <= len(s) <= 450 and not _BOILERPLATE.search(s):
            out.append(s)
    return out


def context_tag(context: str) -> str:
    """Short fingerprint of the research question: cached key sentences go stale when it changes."""
    return hashlib.md5(context.strip().encode("utf-8")).hexdigest()[:10] if context.strip() else "none"


def _best_sentence(idx: np.ndarray, vecs: np.ndarray, target: np.ndarray | None) -> int:
    if target is None:  # no research question: the sentence most typical of the abstract
        target = vecs[idx].mean(axis=0)
    return int(idx[int(np.argmax(vecs[idx] @ target))])


def _store_key_sentences(pm: ProjectManager, project: str, found: dict[str, str], tag: str) -> None:
    with pm.lock(project):
        library = pm.get_papers(project)
        for p in library:
            if p["id"] in found:
                p["key_sentence"] = found[p["id"]]
                p["key_sentence_for"] = tag
        pm.save_papers(project, library)


def fill_key_sentences(project: str, config: dict, ids: list[str] | None = None,
                       emit: Emit = lambda e: None) -> int:
    """
    Make sure every selected paper has `key_sentence` - the sentence of its abstract
    closest to the research question - for the current question. Cached in papers.json,
    so only new papers or a changed question cost time. Returns how many were computed.
    """
    pm = ProjectManager(config["storage"]["projects_dir"])
    context = (pm.get_meta(project).get("context") or "").strip()
    tag = context_tag(context)
    wanted = set(ids) if ids is not None else None
    todo = [p for p in pm.get_papers(project)
            if (wanted is None or p["id"] in wanted) and p.get("key_sentence_for") != tag]
    if not todo:
        return 0
    sents, owners = [], []
    for p in todo:
        for s in split_sentences(p.get("abstract") or ""):
            sents.append(s)
            owners.append(p["id"])
    embedder = get_embedder(config)
    chunks = []
    for i in range(0, len(sents), 256):
        chunks.append(embedder.encode_passages(sents[i:i + 256]))
        emit({"type": "summary_progress", "done": min(i + 256, len(sents)), "total": len(sents)})
    found = {p["id"]: "" for p in todo}   # papers without an abstract get an empty sentence
    if chunks:
        vecs, owner_arr = np.vstack(chunks), np.array(owners)
        target = embedder.encode_query(context) if context else None
        for pid in found:
            idx = np.where(owner_arr == pid)[0]
            if len(idx):
                found[pid] = sents[_best_sentence(idx, vecs, target)]
    _store_key_sentences(pm, project, found, tag)
    return len(found)


def _author_key(name: str) -> str:
    last, first = split_name(name)
    initials = "".join(f"{p[0]}." for p in first.replace(".", " ").split() if p)
    return f"{last}, {initials}".strip(", ") if last else ""


def _pick_diverse(scores: np.ndarray, vecs: np.ndarray, owners: list[str], k: int,
                  max_sim: float = 0.92) -> list[int]:
    """Best-scoring sentences, at most one per paper, skipping near-duplicates."""
    chosen, used = [], set()
    for i in np.argsort(-scores):
        if owners[i] in used:
            continue
        if any(float(vecs[i] @ vecs[j]) > max_sim for j in chosen):
            continue
        chosen.append(int(i))
        used.add(owners[i])
        if len(chosen) == k:
            break
    return chosen


def build_summary(project: str, config: dict, ids: list[str] | None = None,
                  emit: Emit = lambda e: None) -> dict:
    pm = ProjectManager(config["storage"]["projects_dir"])
    library = pm.get_papers(project)
    wanted = set(ids) if ids is not None else None
    papers = [p for p in library if wanted is None or p["id"] in wanted]
    if not papers:
        raise ValueError("There are no papers in this selection.")
    by_id = {p["id"]: p for p in papers}
    score = lambda p: (p.get("evaluation") or {}).get("score") or 0  # noqa: E731
    cite = {p["id"]: apa_in_text(p) for p in papers}
    context = (pm.get_meta(project).get("context") or "").strip()

    # ── overview ────────────────────────────────────────────────────────────
    years = Counter(p["year"] for p in papers if p.get("year"))
    venues = Counter(p["venue"].strip() for p in papers if (p.get("venue") or "").strip())
    authors = Counter(k for p in papers for k in {_author_key(a.get("name", "")) for a in p.get("authors") or []} if k)
    overview = {
        "papers": len(papers),
        "library_size": len(library),
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "per_year": [{"year": y, "count": years[y]} for y in sorted(years)],
        "categories": dict(Counter((p.get("evaluation") or {}).get("category", "unevaluated") for p in papers)),
        "reviews": sum(1 for p in papers if p.get("is_review")),
        "starred": sum(1 for p in papers if p.get("starred")),
        "with_abstract": sum(1 for p in papers if (p.get("abstract") or "").strip()),
        "top_venues": [{"name": v, "count": n} for v, n in venues.most_common(6)],
        "top_authors": [{"name": a, "count": n} for a, n in authors.most_common(8)],
        "most_cited": [{"id": p["id"], "title": p.get("title"), "year": p.get("year"),
                        "citations": p.get("citationCount") or 0, "cite": cite[p["id"]]}
                       for p in sorted(papers, key=lambda p: -(p.get("citationCount") or 0))[:6]],
    }

    # ── sentences ───────────────────────────────────────────────────────────
    sents, owners = [], []
    for p in papers:
        for s in split_sentences(p.get("abstract") or ""):
            sents.append(s)
            owners.append(p["id"])
    emit({"type": "summary_start", "papers": len(papers), "sentences": len(sents)})
    embedder = get_embedder(config)
    chunks = []
    for i in range(0, len(sents), 256):
        chunks.append(embedder.encode_passages(sents[i:i + 256]))
        emit({"type": "summary_progress", "done": min(i + 256, len(sents)), "total": len(sents)})
    vecs = np.vstack(chunks) if chunks else np.zeros((0, 1), dtype=np.float32)
    owner_arr = np.array(owners)

    # ── topics ──────────────────────────────────────────────────────────────
    clusters_file = pm.clusters_path(project)
    groups = []
    if clusters_file.exists():
        for c in json.loads(clusters_file.read_text(encoding="utf-8")).get("clusters", []):
            members = [pid for pid in c.get("paper_ids", []) if pid in by_id]
            if len(members) >= 2:
                groups.append((c.get("label") or f"Topic {len(groups) + 1}", members))
    grouped = {pid for _, m in groups for pid in m}
    rest = [p["id"] for p in papers if p["id"] not in grouped]
    if not groups:
        groups = [("All papers in the selection", [p["id"] for p in papers])]
    elif len(rest) >= 3:
        groups.append(("Not in any cluster", rest))

    topics = []
    for label, members in groups:
        mset = set(members)
        idx = np.array([i for i, o in enumerate(owners) if o in mset], dtype=int)
        key_sentences = []
        if len(idx):
            centre = vecs[idx].mean(axis=0)
            centre /= np.linalg.norm(centre) or 1
            local = _pick_diverse(vecs[idx] @ centre, vecs[idx], [owners[i] for i in idx], 4)
            key_sentences = [{"text": sents[idx[j]], "id": owners[idx[j]], "cite": cite[owners[idx[j]]]}
                             for j in local]
        ps = [by_id[m] for m in members]
        yrs = [p["year"] for p in ps if p.get("year")]
        kw = Counter(k for p in ps for k in p.get("keywords") or [])
        topics.append({
            "label": label,
            "papers": len(ps),
            "years": [min(yrs), max(yrs)] if yrs else None,
            "keywords": [k for k, _ in kw.most_common(6)],
            "top_papers": [{"id": p["id"], "title": p.get("title"), "cite": cite[p["id"]]}
                           for p in sorted(ps, key=score, reverse=True)[:3]],
            "key_sentences": key_sentences,
        })

    # ── one key sentence per paper (closest to the research question) ───────
    target = embedder.encode_query(context) if context else None
    key = {p["id"]: "" for p in papers}
    for pid in key:
        idx = np.where(owner_arr == pid)[0] if len(owners) else []
        if len(idx):
            key[pid] = sents[_best_sentence(idx, vecs, target)]
    _store_key_sentences(pm, project, key, context_tag(context))  # reused by the CSV export
    per_paper = [{"id": p["id"], "title": p.get("title"), "cite": cite[p["id"]],
                  "score": round(score(p), 3), "starred": bool(p.get("starred")), "sentence": key[p["id"]]}
                 for p in sorted(papers, key=score, reverse=True)[:MAX_PAPERS_PER_SENTENCE_LIST]]

    return {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "project": project,
        "context": context,
        "overview": overview,
        "topics": topics,
        "per_paper": per_paper,
        "per_paper_truncated": len(papers) > MAX_PAPERS_PER_SENTENCE_LIST,
        "surveys": [{"id": p["id"], "title": p.get("title"), "cite": cite[p["id"]], "year": p.get("year")}
                    for p in sorted((p for p in papers if p.get("is_review")), key=score, reverse=True)[:8]],
        "reading_list": [{"id": p["id"], "title": p.get("title"), "cite": cite[p["id"]], "note": p.get("note") or ""}
                         for p in sorted((p for p in papers if p.get("starred")), key=score, reverse=True)],
        "method": ("Extractive summary: sentences are taken word for word from the abstracts and chosen with "
                   f"the embedding model {embedder.name}; nothing is generated. Topic sentences are the ones "
                   "closest to each cluster's centre; per-paper sentences are the ones closest to the research "
                   "question."),
    }
