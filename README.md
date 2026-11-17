# Literature Review Agent

A local tool for the **identification** phase of a literature review. It does four things:

1. **Collects** records from OpenAlex (free, no key), Scopus / Web of Science / Zotero CSV exports, and citation snowballing.
2. **Merges duplicates** and keeps a PRISMA-ready log of every search.
3. **Ranks** every paper by semantic similarity to your research question, using a multilingual model: write the question in Spanish, match English papers.
4. **Exports** the library to CSV / RIS / BibTeX.

Screening (deciding what to include) is meant to happen in a dedicated tool such as
[ASReview](https://asreview.nl) or [Rayyan](https://www.rayyan.ai); references go to Zotero.

> Nothing is ever deleted automatically. Missing abstracts, missing DOIs and (optionally) low
> citation counts become **flags**, and relevance becomes a **score** used for ordering. You decide what
> to exclude, and you can report why.

All data stays in `projects/` on your machine (and the optional API key in `.env`). The only network traffic goes to the public
OpenAlex API and, on first start, to Hugging Face to download the model
(~470 MB).

---

## Workflow for a thesis review

1. **Create a project** in the header and write your **research context**: one or two sentences
   describing your question, in Spanish or English. Every paper in the project is scored against
   it. If you change it later, the whole library is rescored so scores stay comparable.
2. **Run several searches** (English keywords work best), optionally restricted by year. Import
   your Scopus / WoS exports with **Import CSV**. Each run is logged under `sessions/` with the
   exact query, date, per-source counts and the config used.
3. **Explore**: sort by score, filter by category, cluster, keyword, text, flags, stars or reviews,
   check **Trends** and the **Map**, and use **Ask** to ask natural-language questions in Spanish or English.
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

### Recommended: a free OpenAlex API key

When OpenAlex is busy it rate-limits searches made without a key, and they fail with
"rate limit reached". A free key avoids that:

1. Sign up at <https://openalex.org/rest-api> and copy your API key.
2. In the app, click **Settings** (top right) and paste it. It is saved in `.env` in the project
   folder, which git ignores. You can also write `OPENALEX_API_KEY=...` in `.env` yourself.

The same dialog takes an optional contact email (`OPENALEX_EMAIL`).

### Choosing a topic: Trends, Map and the reading list

- **Trends** tab. *How much is published on a topic?* gives works per year across all of OpenAlex
  (title/abstract matches) and growth over the last 3 full years; use `"quotes"` for an exact
  phrase. The tab also shows your library per year and a table of your clusters with per-year
  bars, the share of recent papers, emerging keywords and the surveys to read first.
- **Map** tab. A 2-D map (t-SNE) of the clustered papers: close dots are similar papers.
- **Keywords.** Each paper gets up to 5 keyphrases, extracted locally with the same embedding
  model (KeyBERT; no paid API). Click a keyword to filter the library by it.
- **Surveys / reviews** are detected automatically (badge + filter). Read them first.
- **Reading list.** Star papers (☆) and write notes in the paper panel. Stars and notes survive new
  searches and go into the CSV/RIS exports.
- **History.** In the sidebar, *↻ reuse* puts an old query back in the search box.
- The app remembers each project's tab, filters, sort and scoring sliders in your browser.

### Long runs

A running search, import or snowballing can be stopped with **Cancel** in the pipeline log. A
cancelled run leaves nothing behind (no papers, no PRISMA entry) unless it had already reached
*Saving…*. **Recompute keywords** (sidebar, under Clusters) re-extracts every paper's keyphrases;
regenerate the clusters afterwards to refresh their labels.

Settings also has an **Appearance** switch (match system / light / dark).

### Snowballing

Open any paper → **← References** (older work it builds on), **Cited by →** (newer work citing it)
or **Both**. Results go through the same deduplication and scoring, and PRISMA reports them as
*citation searching*, separately from database searches.

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

These thresholds are heuristics until you check them. Use the score to **order** your
screening, not to exclude papers without reading them. If you report the tool in your methods,
say it was used for ranking and deduplication.

### Checking the ranking (Validate tab)

1. **Draw random sample** (e.g. 50 papers). It is a simple random sample of the library, so the
   estimates hold for the whole library.
2. Label each paper **Relevant / Not relevant / Unsure** (keys `R`, `N`, `U`; `Z` undoes) from
   its title and abstract. The score is hidden while you label.
3. The tab reports the **AUC** (how well the score separates the two groups), and for each
   threshold the papers you would screen, **recall** (with a 95% interval), precision and the
   relevant papers missed, plus the threshold that keeps ≥ 95% of the relevant papers. Move the
   sliders and the numbers update. A **Copy** button gives a paragraph for your methods section.

Labels are stored with the project and exported in the CSV `validation` column. Add 25 more
papers at a time when the interval is too wide.

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

Run them with the venv's Python (`.venv\Scripts\python` on Windows). Tests: `python -m pytest tests`
(backend) and `npm test` in `frontend/` (scoring, validation metrics, trends).

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
src/sources/openalex.py   OpenAlex search, snowballing, yearly trends (with retry/backoff)
src/importers/            Scopus / WoS / Zotero CSV parser
src/utils/                records & DOI normalization, deduplication, BibTeX, CSV/RIS
src/embeddings/           shared model + per-project embedding cache
src/evaluation/scoring.py relevance score
src/filters/flags.py      quality flags
src/clustering.py         K-Means + elbow + labels + 2-D t-SNE map
src/keywords.py           per-paper keyphrases (KeyBERT, local) and distinctive cluster labels
backend/                  FastAPI (SSE streaming for long runs; closing the stream cancels the run)
frontend/                 React + Vite
frontend/src/scoring.js   live rescoring (mirrors src/evaluation/scoring.py)
frontend/src/validation.js  AUC, recall/precision, Wilson intervals for the Validate tab
```
