# Literature Review Agent

A local tool for the **identification** phase of a literature review. It does four things:

1. **Collects** records from Semantic Scholar, OpenAlex and Scopus / Web of Science / Zotero CSV exports.
2. **Merges duplicates** and keeps a PRISMA-ready log of every search.
3. **Ranks** every paper by semantic similarity to your research question, using a multilingual model: write the question in Spanish, match English papers.
4. **Exports** the library to CSV / RIS / BibTeX.

Screening (deciding what to include) is meant to happen in a dedicated tool such as
[ASReview](https://asreview.nl) or [Rayyan](https://www.rayyan.ai); references go to Zotero.

> Nothing is ever deleted automatically. Missing abstracts, missing DOIs and (optionally) low
> citation counts become **flags**, and relevance becomes a **score** used for ordering. You decide what
> to exclude, and you can report why.

All data stays in `projects/` on your machine. The only network traffic goes to the public
Semantic Scholar and OpenAlex APIs and, on first start, to Hugging Face to download the model
(~470 MB).

---

## Workflow for a thesis review

1. **Create a project** in the header and write your **research context**: one or two sentences
   describing your question, in Spanish or English. Every paper in the project is scored against
   it. If you change it later, the whole library is rescored so scores stay comparable.
2. **Run several searches** (English keywords work best), optionally restricted by year. Import
   your Scopus / WoS exports with **Import CSV**. Each run is logged under `sessions/` with the
   exact query, date, per-source counts and the config used.
3. **Explore**: sort by score, filter by category, cluster, text or flags, and use **Ask** to ask
   natural-language questions in Spanish or English.
4. **Export**:
   - **CSV or RIS → ASReview / Rayyan** for title–abstract screening. Export the whole library,
     or only the current filtered view.
   - **RIS / BibTeX → Zotero**. The BibTeX keys (`smith2021deep`) are the same in `master.bib`, the
     download, and the per-paper *Copy* button.
5. **PRISMA**: the sidebar shows *records identified per source → duplicates removed → records to
   screen*. `python scripts/export.py --project <name> --prisma` prints the same numbers.

---

## Install and run

Requirements: **Python 3.11–3.13** and **Node.js 18+**. No conda, no GPU.

| | Windows | macOS / Linux |
|---|---|---|
| Install (once) | `install.bat` | `./install.sh` |
| Start | `start.bat` | `./start.sh` |
| Stop | `stop.bat` | `./stop.sh` |

The install step creates `.venv/` (CPU-only PyTorch) and installs the frontend. Once the app is
running, open <http://localhost:5173>; the API docs are at <http://127.0.0.1:8000/docs>.

Manual start:

```bash
.venv/Scripts/python -m uvicorn backend.main:app --port 8000   # Windows (use .venv/bin/python elsewhere)
cd frontend && npm run dev
```

### Strongly recommended

- **Semantic Scholar API key** (free): <https://www.semanticscholar.org/product/api>. Without a
  key the public pool answers HTTP 429 most of the time. The app retries 5 times, then continues
  with OpenAlex only and reports the failure in the log and in the session record.
- **OpenAlex email**: puts your requests in the faster "polite pool".

Both go in `config.yaml`.

---

## How scoring works

| Field | Meaning |
|---|---|
| `similarity` | Raw cosine similarity between your context and the paper's title + abstract (`intfloat/multilingual-e5-small`) |
| `semantic_score` | `similarity` rescaled to 0–1 using `evaluation.similarity_range` (E5 similarities sit in a narrow band; off-topic ≈ 0.75, on-topic ≈ 0.85–0.90) |
| `impact_score` | `log1p(citations) / log1p(citation_ref)`, capped at 1 |
| `score` | `0.8 · semantic_score + 0.2 · impact_score` (weights in `config.yaml`) |
| `category` | `relevante` ≥ 0.55 · `potencialmente_relevante` ≥ 0.35 · otherwise `no_relevante`. Labels only |

The **Scoring settings** sliders change weights and thresholds live in the browser. Permanent
defaults live in `config.yaml`.

These thresholds are heuristics, not validated cut-offs. Use the score to **order** your
screening, not to exclude papers without reading them. If you report the tool in your methods,
say it was used for ranking and deduplication.

| Flag | Meaning |
|---|---|
| `missing_abstract` | No abstract from any source: score is based on the title only |
| `missing_doi` | No DOI: deduplicated by fuzzy title instead |
| `missing_citation_count` | Source gave no citation count |
| `below_citation_floor` | Only when `citation_floors.enabled: true` |

---

## CLI

```bash
python scripts/search.py     --project tesis --query "anomaly detection time series" --context "Detección de anomalías en sensores industriales" --year-from 2015 --max-results 200
python scripts/import_csv.py --project tesis --file scopus.csv
python scripts/query_db.py   --project tesis --question "¿Qué métodos no supervisados se usan?"
python scripts/cluster.py    --project tesis --only relevante potencialmente_relevante
python scripts/export.py     --project tesis --format ris --out tesis.ris
python scripts/export.py     --project tesis --prisma
```

Run them with the venv's Python (`.venv\Scripts\python` on Windows). Tests: `python -m pytest tests`.

---

## Data layout

```
projects/<project>/
├── project.json            research context
├── master_db/
│   ├── papers.json         every unique record (source of truth)
│   ├── embeddings.npz      embedding cache (rebuilt automatically if the model changes)
│   ├── master.bib          BibTeX, regenerated after every run
│   └── clusters.json
└── sessions/<id>/
    ├── session.json        query, date, counts per source, duplicates, config snapshot
    └── results/<source>.json   raw records returned by each source
```

`papers.json` and `sessions/` cannot be regenerated, so back up the `projects/` folder.

## Code map

```
src/pipeline.py           search / import / rescore / query / PRISMA (used by API and CLI)
src/sources/              Semantic Scholar (with retry/backoff), OpenAlex
src/importers/            Scopus / WoS / Zotero CSV parser
src/utils/                records & DOI normalization, deduplication, BibTeX, CSV/RIS
src/embeddings/           shared model + per-project embedding cache
src/evaluation/scoring.py relevance score
src/filters/flags.py      quality flags
src/clustering.py         K-Means + elbow + KeyBERT labels
backend/                  FastAPI (SSE streaming for long runs)
frontend/                 React + Vite
```
