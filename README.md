# Literature Review Agent

A self-hosted systematic literature review assistant. It fetches academic papers from Semantic Scholar and OpenAlex, evaluates them against your research context using sentence-transformer embeddings, and serves a web interface for browsing, querying, and organizing your library.

> **Runs 100% locally.** No cloud service, no subscription, no paid API is required. Semantic Scholar and OpenAlex are free public APIs. The embedding model (`all-MiniLM-L6-v2`) runs on your CPU. Every paper, embedding, and export is stored in a `projects/` folder on your own machine — nothing leaves it.

All processing runs locally. No API keys are required for the default sources, and all data is stored on your machine.

---

## Features

| Feature | Description |
|---|---|
| **Multi-source search** | Queries Semantic Scholar and OpenAlex in parallel |
| **CSV import** | Ingests manual exports from Scopus and Web of Science |
| **Semantic evaluation** | Scores papers by cosine similarity to your research context + log-normalized citation impact |
| **Deduplication** | Removes duplicates by DOI and by title string similarity (SequenceMatcher ratio > 0.90) |
| **Persistent library** | Stores all accepted papers in ChromaDB + `papers.json` + `master.bib` |
| **Cluster analysis** | K-Means with automatic k selection (elbow method) + KeyBERT thematic labels |
| **Semantic query** | Ask natural-language questions over the library; returns top matches by cosine similarity |
| **Real-time pipeline log** | Server-Sent Events stream the progress of every search or import |
| **BibTeX export** | `master.bib` is regenerated on every search/import; individual entries are copyable from the UI |
| **Project management** | Create, rename, and delete independent projects from the header |
| **Interactive filter settings** | Adjust evaluation weights and thresholds and see re-classified results instantly, without re-searching |

---

## Architecture

```
literature-review-agent/
│
├── backend/                  FastAPI application
│   ├── main.py               App entry point, CORS
│   ├── config.py             Loads config.yaml (paths resolved to absolute)
│   ├── pipeline.py           Search and import pipeline (SSE event emitter)
│   └── routers/
│       ├── projects.py       GET/POST/PATCH/DELETE /api/projects
│       ├── papers.py         GET /api/projects/{p}/papers
│       ├── search.py         POST /api/projects/{p}/search  → SSE
│       ├── import_csv.py     POST /api/projects/{p}/import  → SSE
│       ├── query.py          POST /api/projects/{p}/query
│       └── clusters.py       GET/POST /api/projects/{p}/clusters → SSE
│
├── frontend/                 React + Vite application
│   └── src/
│       ├── App.jsx           Root state, re-evaluation logic
│       ├── api/client.js     Fetch + SSE client (encodeURIComponent on all routes)
│       └── components/
│           ├── Masthead      Header with project selector (create/rename/delete)
│           ├── SearchPanel   Query + context inputs, max-results control
│           ├── PipelineLog   Real-time SSE event renderer
│           ├── PaperLibrary  Scrollable paper list with category filter pills
│           ├── PaperCard     Compact card: badge, year, citations, title, abstract
│           ├── PaperDetail   Slide-in panel: full abstract, scores, DOI, BibTeX
│           ├── Sidebar       Stats cards, cluster filter, filter settings sliders
│           ├── SemanticQuery "Ask" tab: natural-language query over ChromaDB
│           └── ImportModal   CSV drag-drop with SSE progress log
│
├── src/                      Core Python library
│   ├── sources/              semantic_scholar.py, openalex.py
│   ├── filters/              mechanical.py (abstract/DOI/cites), citation_floor.py
│   ├── evaluation/           embedding_evaluator.py, claude_evaluator.py
│   ├── embeddings/           chroma_store.py (MasterVectorDB)
│   ├── storage/              project_manager.py
│   └── utils/                bibtex_exporter.py, deduplication.py
│
├── scripts/                  Standalone CLI tools
│   ├── search.py             Full search pipeline
│   ├── import_csv.py         CSV import pipeline
│   ├── query_db.py           Semantic query over ChromaDB
│   └── cluster.py            K-Means clustering + KeyBERT labeling
│
├── projects/                 Data directory (created at runtime)
│   └── <project-name>/
│       ├── master_db/
│       │   ├── papers.json   Master paper list (all accepted papers)
│       │   ├── master.bib    BibTeX export (regenerated on every run)
│       │   ├── clusters.json K-Means cluster report
│       │   └── embeddings/   ChromaDB persistent vector store
│       └── sessions/         Per-search session logs and raw results
│
├── config.yaml               Global configuration
├── environment.yml           Conda environment specification
├── install.sh / install.bat  Setup scripts
├── start.sh / start.bat      Launch scripts
└── stop.sh / stop.bat        Shutdown scripts
```

**Data flow for a search:**
1. Semantic Scholar and OpenAlex are queried in parallel.
2. Results pass through a mechanical filter (must have abstract, DOI, citation count).
3. DOI and title-similarity deduplication removes duplicates across sources.
4. A citation floor discards old papers with too few citations.
5. If a `--context` is provided, each paper is scored by `weight_sem × cosine_sim + weight_imp × log_norm_citations`. Papers below the minimum semantic threshold are discarded first.
6. Accepted papers are upserted into ChromaDB and `papers.json`, and `master.bib` is regenerated.

---

## Getting Started

> **Everything runs on your machine.** There is no server to sign up for and no data is sent anywhere except to the public Semantic Scholar and OpenAlex APIs when you run a search. The web UI is served locally at `localhost:5173` and talks only to the local FastAPI backend at `localhost:8000`.

### Prerequisites

| Tool | Required version | Notes |
|---|---|---|
| **Conda** | Any (Miniconda ≥ 23) | [miniconda.html](https://docs.conda.io/en/latest/miniconda.html) |
| **Node.js** | v18 or newer | [nodejs.org](https://nodejs.org) |
| **npm** | Bundled with Node.js | |

No GPU is required. The embedding model (`all-MiniLM-L6-v2`) runs comfortably on CPU.

> **First-launch note:** the backend downloads and initializes the `all-MiniLM-L6-v2` model on startup. Expect a delay of 5–15 seconds before the first search or query responds — subsequent requests are fast because the model stays loaded in memory.

---

### Mac / Linux

#### 1 — Navigate to the project folder

All scripts must be run from the **project root** (the folder that contains `config.yaml`, `backend/`, and `frontend/`). If you cloned the repo, that is the top-level directory:

```bash
cd path/to/literature-review-agent
```

#### 2 — Install

```bash
chmod +x install.sh start.sh stop.sh
./install.sh
```

This will:
- Verify conda and Node.js are available.
- Create (or update) the `litreview` conda environment from `environment.yml`.
- Run `npm install` in the `frontend/` directory.

#### 3 — Start

```bash
./start.sh
```

Both servers start as background processes. Logs are written to `.logs/backend.log` and `.logs/frontend.log`. The terminal prints the URLs when ready.

> **First run:** the backend will download `all-MiniLM-L6-v2` from Hugging Face (~90 MB) and initialize it before accepting requests. This happens once — the model is cached locally by sentence-transformers afterward. Allow an extra minute on the first launch; subsequent starts take only a few seconds.

#### 4 — Open the app

```
http://localhost:5173
```

#### 5 — Stop

```bash
./stop.sh
```

Kills any process on ports 8000 and 5173.

---

### Windows

#### 1 — Navigate to the project folder

Open **Anaconda Prompt** (required so that `conda` is on the PATH) and navigate to the project root — the folder that contains `config.yaml`, `backend/`, and `frontend/`:

```cmd
cd C:\path\to\literature-review-agent
```

> **Tip:** You can also open Anaconda Prompt directly in the project folder by right-clicking the folder in File Explorer and choosing **Open in Terminal**, or by launching Anaconda Prompt and running the `cd` command above. If `conda` is still not recognized, open the **Anaconda Prompt** application from the Start menu instead of a regular terminal.

#### 2 — Install

```cmd
install.bat
```

This will:
- Verify conda and Node.js are available.
- Create (or update) the `litreview` conda environment.
- Run `npm install` in the `frontend/` folder.

#### 3 — Start

```cmd
start.bat
```

Two new console windows open — **LRA-Backend** (uvicorn) and **LRA-Frontend** (Vite). The original terminal prints the URLs when ready.

> **First run:** the backend will download `all-MiniLM-L6-v2` from Hugging Face (~90 MB) and initialize it before accepting requests. This happens once — the model is cached locally by sentence-transformers afterward. Allow an extra minute on the first launch; subsequent starts take only a few seconds.

#### 4 — Open the app

```
http://localhost:5173
```

#### 5 — Stop

```cmd
stop.bat
```

Terminates any process on ports 8000 and 5173. You can also simply close the two console windows.

---

### Manual start (any OS)

If you prefer to manage processes yourself:

```bash
# Terminal 1 — backend
conda activate litreview
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

---

## Usage Guide

### Managing Projects

Click the project selector in the header to open the project dropdown:

- **Select** a project by clicking its name.
- **Create** a new project with the **+ New project** button at the bottom of the dropdown. Type a name and press Enter or click **Create**.
- **Rename** a project by hovering over it and clicking the **✎** icon. Edit the name and press Enter.
- **Delete** a project by hovering over it and clicking the **🗑** icon. Confirm the action when prompted. This permanently removes all data for that project.

Each project is stored in its own subdirectory under `projects/`.

---

### Searching for Papers

1. Select a project.
2. Type a search query in the main input (e.g. `anomaly detection deep learning time series`).
3. Optionally, enter a **research context** — a sentence or paragraph describing your research focus. When provided, every paper is scored by semantic similarity to this text.
4. Set **Max results** (10–500 per source).
5. Click **Search**.

The pipeline log streams in real time: fetch → mechanical filter → dedup → citation floor → semantic evaluation → insert. When complete, the library refreshes automatically.

**Tips:**
- Use natural language or keyword phrases — the APIs handle both.
- The context field is the most important parameter for relevance quality. A good context describes your specific research question, not just the topic.
- Without a context, all papers that pass the mechanical and citation filters are accepted regardless of topic relevance.

---

### Importing from Scopus / Web of Science

Papers can be imported from CSV exports downloaded directly from the databases.

**Export from Scopus:**
1. Run a search on [scopus.com](https://www.scopus.com).
2. Select results → **Export** → **CSV** → include all fields.

**Export from Web of Science:**
1. Run a search on [webofscience.com](https://www.webofscience.com).
2. **Export** → **Tab-delimited** (plain text) or **CSV**.

**Import in the app:**
1. Click **Import CSV** in the header.
2. Drag and drop the file, or click to browse.
3. Enter a research context (required — papers are classified by similarity to this text).
4. Click **Import**.

The import applies the same mechanical filter, citation floor, deduplication, and semantic evaluation pipeline as a regular search. Only papers that pass all filters and are semantically relevant are added to the library.

---

### Browsing the Library

The **Papers** tab shows all papers in the current project, sorted by citation count.

**Relevance badges:**
- **Relevant** — combined score ≥ the relevant threshold.
- **Potential** — combined score ≥ the potential threshold.
- **Uncategorized** — imported without a research context; no evaluation was run.

**Filtering:**
- Use the **All / Relevant / Potential** pill buttons to filter by category.
- Click a cluster in the sidebar to filter by thematic group.
- Both filters stack.

**Paper detail:** Click any paper card to open the detail panel. It shows the full abstract, semantic and impact scores, DOI (with a link), and a copyable BibTeX entry.

---

### Semantic Query ("Ask" tab)

Switch to the **Ask** tab to query the library with a natural-language question:

```
What methods are used for unsupervised anomaly detection?
What are the main limitations of LSTM-based forecasting?
```

The query is embedded with the same model used during evaluation, and the top matching papers are returned by cosine similarity to your question. Useful for exploring your library without knowing exact paper titles.

---

### Cluster Analysis

The **Clusters** section in the sidebar groups papers by thematic similarity.

Click **Generate clusters** to run:
1. K-Means is run for k = 2 through 8 (configurable in `scripts/cluster.py`).
2. The elbow of the inertia curve (maximum-perpendicular-distance method) selects the optimal k automatically.
3. KeyBERT extracts the most representative keyphrases from each cluster's combined titles and abstracts.
4. The cluster label is the top 3 keyphrases joined by `|`.

Click a cluster card to filter the library to only those papers. Click **All papers** or the × chip in the library header to clear the filter. Click **Regenerate** to re-cluster after adding new papers.

---

### Filter Settings (real-time re-evaluation)

The collapsible **Filter settings** section at the bottom of the sidebar provides sliders to adjust the scoring formula. Changes re-classify all papers immediately without re-fetching or re-embedding anything — only the stored `semantic_score` and `citationCount` values are used.

| Slider | What it controls |
|---|---|
| **Min. semantic score** | Abstracts below this threshold are discarded regardless of citations |
| **Semantic weight** | Balance between topic relevance and citation impact in the combined score |
| **Citation reference** | Papers with this many citations reach the maximum impact score |
| **Relevant threshold** | Minimum combined score to mark a paper as relevant |
| **Potential threshold** | Minimum score to keep a paper as potentially relevant |

Click **Reset to defaults** to restore the values from `config.yaml`.

> **Note:** These adjustments are client-side only and are not persisted to disk. To permanently change the defaults, edit `config.yaml` and restart the backend.

---

### CLI Scripts

All pipeline functions are also available as standalone command-line scripts, useful for automation or bulk processing.

```bash
# Activate the environment first
conda activate litreview

# Full search pipeline
python scripts/search.py \
    --project mythesis \
    --query "anomaly detection deep learning" \
    --context "fault detection in industrial IoT systems" \
    --max-results 100

# Import a Scopus or WoS CSV export
python scripts/import_csv.py \
    --project mythesis \
    --file ~/Downloads/scopus_export.csv \
    --context "fault detection in industrial IoT systems"

# Semantic query over the library
python scripts/query_db.py \
    --project mythesis \
    --question "What deep learning architectures are used for time series anomaly detection?" \
    --top 10

# Cluster the library (K-Means, automatic k selection)
python scripts/cluster.py \
    --project mythesis \
    --k-min 2 \
    --k-max 10
```

---

## Data Storage

### Where data lives

All project data is stored under the `projects/` directory at the root of the repository:

```
projects/
└── <project-name>/
    ├── master_db/
    │   ├── papers.json      All accepted papers (title, abstract, DOI, year, cites, scores)
    │   ├── master.bib       BibTeX file — regenerated on every search or import
    │   ├── clusters.json    K-Means cluster report (generated on demand)
    │   └── embeddings/      ChromaDB vector store (sentence-transformer embeddings)
    └── sessions/
        └── <timestamp>/     Raw search results and per-source logs
```

`papers.json` is the source of truth. ChromaDB is derived from it (embeddings) and can be rebuilt if corrupted by re-importing from the CSV or re-running a search.

### Backup recommendation

The `projects/` folder is the only data that cannot be regenerated automatically. **Back it up regularly.**

A simple approach:

```bash
# Mac / Linux — create a timestamped archive
tar -czf backup_$(date +%Y%m%d).tar.gz projects/

# Windows PowerShell
Compress-Archive -Path projects\ -DestinationPath "backup_$(Get-Date -Format 'yyyyMMdd').zip"
```

Suggested backup frequency: after every significant search session.

The `frontend/node_modules/` and the `litreview` conda environment can both be fully recreated by running `install.sh` / `install.bat` and do not need to be backed up.

---

## Configuration

All tunable parameters are in `config.yaml` at the project root.

```yaml
sources:
  semantic_scholar:
    api_key: ""          # Optional — raises the rate limit significantly
    rate_limit_delay: 1.0
    max_results_per_query: 100
  openalex:
    email: ""            # Optional — enables the "polite pool" (faster)

filters:
  require_abstract: true
  require_doi: true
  require_citation_count: true

citation_floors:
  pre_2015:
    year_cutoff: 2015
    min_citations: 500   # Papers older than 2015 need ≥ 500 citations
  mid_range:
    year_from: 2015
    year_to: 2020
    min_citations: 100   # Papers 2015–2020 need ≥ 100 citations
  # Papers after 2020: no floor

evaluation:
  weights:
    semantic: 0.80       # Fraction of the combined score from cosine similarity
    impact:   0.20       # Fraction from log-normalized citation count
  citation_ref: 300      # Citations at which impact score saturates at 1.0
  thresholds:
    min_semantic: 0.40   # Below this → discarded before combining scores
    relevant:     0.50   # Combined score ≥ this → "Relevant"
    potentially:  0.30   # Combined score ≥ this → "Potentially Relevant"

embeddings:
  model: "all-MiniLM-L6-v2"   # Any sentence-transformers model works here
```

**Semantic Scholar API key:** Free key available at [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api). Without a key, the API allows ~100 requests/5 min. With a key, the limit is much higher.

**OpenAlex email:** Adding your email to the `openalex.email` field places your requests in the "polite pool", which has higher rate limits and lower latency.

---

## Troubleshooting

**`conda` is not recognized (Windows)**
Open **Anaconda Prompt** instead of a standard terminal. If using Windows Terminal, you may need to initialize conda first: `conda init cmd.exe` and then restart the terminal.

**Port already in use**
Run `stop.sh` / `stop.bat` before starting again, or manually kill the process:
- Mac/Linux: `lsof -ti:8000 | xargs kill`
- Windows: `netstat -aon | findstr :8000` → `taskkill /F /PID <pid>`

**`conda env create` fails mid-way**
Remove the partial environment and retry:
```bash
conda env remove -n litreview
./install.sh
```

**No papers found after search**
- The mechanical filter requires abstract + DOI + citation count. Many preprints and conference papers lack these fields on Semantic Scholar.
- Citation floors are aggressive by default for older papers. Lower `min_citations` in `config.yaml` if needed.
- Try a broader query first, then refine with the context field.

**ChromaDB collection appears empty after re-running a search**
ChromaDB deduplicates by DOI on upsert — papers already in the DB are not re-added. This is expected behavior. Use `query_db.py --top 20` to verify the current state.

---

## Built with

- [sentence-transformers](https://www.sbert.net/) — local embedding model (`all-MiniLM-L6-v2`) for semantic similarity
- [ChromaDB](https://www.trychroma.com/) — persistent local vector store
- [KeyBERT](https://maartengr.github.io/KeyBERT/) — keyphrase extraction for cluster labels
- [FastAPI](https://fastapi.tiangolo.com/) — backend API with Server-Sent Events for pipeline streaming
- [React](https://react.dev/) + [Vite](https://vitejs.dev/) — frontend
- [Claude Code](https://claude.ai/code) — development
