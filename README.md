# AI Software Engineering Intelligence Platform

FastAPI + React (Vite) monorepo for repository ingestion, structural code analysis,
embeddings, and AI-assisted retrieval. `backend/` and `frontend/` are sibling
folders, deliberately **not** a package-workspace monorepo, so each side installs
and runs independently.

See `AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`
for the 19-step build plan and `AI_Software_Engineering_Intelligence_Platform_Overview.docx`
for the product overview.

## Status (audited 2026-09-28)

**Verified end-to-end (Steps 1–7)** — every claim below was exercised against the
live API in an earlier session:

- Step 1: database schema + Supabase project (pgvector enabled).
- Step 2: Supabase email/password auth, shadow `users` rows, projects CRUD.
- Step 3: GitHub OAuth (`/auth/github/login` → callback, token stored on `users`
  row), `GET /user/repos`, repo attach with `git clone --depth=1`.
- Step 4: Celery repo ingestion (Upstash Redis broker, `--pool=solo` on Windows) —
  filters, language detection, language histogram on the `analysis_jobs` row.
- Step 5: tree-sitter structural analysis — files, symbols (precise 1-based line
  spans), imports (resolved through `backend/` subdirs), import/belongs_to edges,
  FastAPI + Express route extraction.
- Step 6: React frontend — Login, Dashboard (projects + GitHub link), Project
  Detail (attach + analyze), Analysis Status (live 2s polling + histogram),
  Repo Explorer (file tree / symbols / edges / file detail). `npm run build` and
  `npm run lint` are clean.
- Step 7: code chunking (pure-stdlib `chunker.py`, 18 unit tests) + Jina v2
  embeddings into `pgvector` (`code_embeddings`, HNSW cosine index). Demo repo:
  28 chunks embedded and searchable at the DB level.

**Fixed and verified this session (2026-09-28, fix pass 1)** — each item was
exercised in a browser against a live API:

- Step 8 retrieval now exists: `app/retrieval/search.py::search_code` (pgvector
  cosine `<=>`, optional `language`/`file_path` filters, top-k ≤ 50) behind
  `GET /repos/{repo_id}/search` and `GET /repos/search`. Both modes return hits
  with file/line metadata and word-level highlighting; the first query costs
  ~15 s while the API process loads the Jina model, ~1 s after that.
  `benchmarks/retrieval_benchmark.py` imports and reports a real hit score
  (it used to compare each embedding with itself, i.e. always 1.0).
- `app/api/observability.py` is mounted: job stats, benchmark status and cost
  summary all return 200 with real data (3 jobs, 45.8 s avg, 84 chunks).
- `App.tsx` rendered `<AppShell/>` twice (in `RequireAuth` *and* in the route),
  so every page had a double navbar — the guard now renders `<Outlet/>`.
- `Search.tsx` read `useParams().repoId` on a route with no `:repoId`, so it
  ran nothing and said "No results found". It now reads `?repo=<id>` (RepoExplorer
  links here with one), disables "This repo" when absent, and only queries on
  submit instead of on every keystroke.
- `Observability.tsx` had the same `useParams` bug (the cost panel was
  permanently disabled); it now loads globally and can run the benchmark
  against a chosen repo.

**Step 9 implemented (2026-09-28, fix pass 3)** — repository-aware AI chat:

- `POST /chat` (ownership-checked, 20 req/min/user) runs a LangChain
  tool-calling agent on Groq with the four tools the plan specifies, all thin
  wrappers over data that already exists: `search_code` (Step 8 retrieval),
  `get_file`, `get_symbol`, `get_dependencies` (Step 5 tables). It answers
  `{answer, evidence[]}` and each assistant bubble renders its own evidence
  panel (`Chat.tsx` read `mutation.data`, so every older answer was showing
  the *newest* run's sources).
- **The plan's model no longer exists**: `llama-3.3-70b-versatile` 404s on
  Groq today, and that surfaced as an opaque 502. The default is now
  `openai/gpt-oss-20b` (Groq free tier, cheapest paid rate) via `LLM_MODEL`;
  404/401/429 now map to 503/503/429 naming the config to fix.
- Verified in the browser on the demo repo: *"How does authentication work in
  this API?"* → *"I could not find any authentication implementation or API in
  this repository"* (correct — the Portfolio repo has none and the retrieved
  evidence is README + React pages: the plan's "don't invent when evidence is
  thin" check), and *"What tech stack does this project use?"* → cites
  `README.md:17-25` and `src/pages/contact.jsx:4-65`, both accurate.
- Step 19's cost tracker is finally fed (usage recorded per turn, including
  the fallback call below). Streaming had to be **disabled**: Groq reports
  usage only on the final streamed chunk and `AgentExecutor` discards it, so
  the summary read 0 calls after two real turns.
- **Small-model hardening** (all measured against `gpt-oss-20b`, which garbles
  tool calls): a malformed tool-call JSON (`{"query":"tsx",""}`) makes Groq
  400 with `tool_use_failed` — one retry, then a deterministic fallback
  answers directly from retrieved chunks with the same cite-or-admit prompt
  (no tools → cannot 400 or loop). A "Stop rule" orders the answer right
  after the first sufficient results; `get_file`/`get_dependencies` answer
  directory paths with a file listing instead of "no match" (the old miss
  text told the model to search again, looping to force-stop); and
  `_sanitize_answer` cuts leaked Harmony prologues (`assistant to=...`) from
  final text. `MAX_ITERATIONS` is 6 — longer chains are looping, and the
  fallback covers them.
- `RepoExplorer` gained an "Ask AI" link — `/repos/:id/chat` had no entry
  point anywhere in the UI.
- Chat's clone reader used the wrong layout (`CLONE_ROOT_DIR/owner/name`)
  and silently fell back to chunks every time; the real layout is
  `<project_id>/<owner>__<name>`, now shared via `risk_model/features.py`.

**Steps 10–12 implemented (2026-09-29, fix pass 4)** — risk dataset, model,
findings:

- **Dataset verdict on CodeSearchNet: does not fit.** It is 2M code/NL pairs
  with no risk labels — right for retrieval, wrong for this classifier — so
  per the agreed fallback it was not used. Instead: feature engineering over
  the caller's indexed repos (complexity via radon for Python, branch-keyword
  approximation otherwise; LOC; file fan-in/out from Step 5 edges; test-file
  filename heuristic; git churn) with deterministic v1 weak-label rules
  (low/medium/high), topped up per class to 50 with a seeded synthetic
  Python generator that runs through the *same* feature and labeling code
  (verified by test: every synthetic sample lands its intended class).
  v1 is documented as a heuristic distiller, not reviewed truth — every
  sample records its `label_source`, and `manual` already outranks the rest.
- **Model (Step 11)**: jina 768-d + 6 engineered features (scaler fits the
  engineered tail only), `logistic` (default) or `gbt` (the page offers
  both), stratified 80/20 split, pickle artifacts + meta + saved test split
  under `app/risk_model/artifacts/` (gitignored — `POST /risk/train`
  rebuilds them). Live: `logistic-v1` on 150 samples (12 real + 138
  synthetic), test acc=1.0/macro_f1=1.0 on 30 held-out rows.
- **Endpoints (Step 12)**: `POST /risk/train` (trains, then scores the
  trained repos into `risk_findings`), `POST /risk/evaluate` (same saved
  split — a double-scaling bug made it disagree with train until the split
  was saved unscaled), `GET /repos/{id}/findings` (filters + pagination,
  rows joined with symbol/file context) and `.../findings/summary`
  (all three levels always present). Findings page shows 12 rows with real
  names/paths/lines; its pagination buttons were dead (`searchParams.set`
  without `setSearchParams`) and its Symbol/File/Lines columns rendered raw
  UUIDs — all fixed. `benchmarks/risk_eval.py` imports the real module now
  and measures the saved split instead of `randn`.

**Step 14 implemented (2026-09-29, fix pass 5)** — PR impact analysis:

- `GET /repos/{id}/pulls` (open-PR list) + `GET /repos/{id}/prs/{n}/analysis`
  (ownership + 10 req/min rate limit per Step 18), computed on demand: PR
  metadata + diff from GitHub, symbol mapping, 1-hop affected files, test
  heuristic, risk scores from the findings table, then the LLM summary —
  one tool-free Groq completion under a validated JSON schema
  (`summary_markdown` + `key_risks`), cost-tracked. No new table: the result
  is derived data (the Celery task already covers the webhook flow).
- The summary degrades, never fails: no key or provider error keeps the
  structural analysis with an empty summary. Dead stored token (GitHub 401)
  is 409 "re-link GitHub", not 502.
- RepoExplorer gained a Pull requests tab (open PRs + manual number entry —
  the dashboard route had no entry point); PRDashboard gained the AI summary
  card. Its table already matched the contract; its pagination-style dead
  code was not present here.
- Verified: real-DB impact (Contact/Navbar → App.jsx/Layout.jsx 1-hop),
  real risk scores, real Groq summary with cites; browser pulls tab +
  dashboard error states. Full click-through needs a live GitHub token —
  the stored one 401s, so re-link on the dashboard first.

**Skeleton / not verified (Steps 13, 16–19)** — partial work in the backend:

- `core/encryption.py` is unused (GitHub tokens are still plaintext).
  `core/cost_tracking.py` is fed now (chat + PR summary record usage every
  call) and persists to `app/cost_records.json` so totals survive restarts.
- Step 16 (incremental indexing) and the Step 17/18 hardening beyond
  rate limits + timeouts are not implemented.

**Cleanup (fix pass 2, 2026-09-28)**:

- Deleted 21 empty 0-byte scaffold files: the whole `agents/`, `parsing/` and
  `risk_model/` packages plus `api/chat|findings|pull_requests.py`,
  `models/risk_finding|pull_request|code_structure|embedding.py`,
  `embeddings/embedder.py` and `schemas/chat|finding|pr.py`. Nothing imported
  them — the only two live references (`benchmarks/risk_eval.py` and
  `pr_analysis/impact.py::get_risk_scores_for_symbols`) already failed against
  the empty modules.
- `ruff check` and `ruff format --check` are clean: 34 errors in 8 Steps 13–19
  files (unused imports, long lines, missing EOF newlines, one unsorted import
  block, one unused variable) were fixed and those 8 files formatted.
- `requirements.txt` declares `numpy`, `scikit-learn`, `radon` (Step 10
  complexity) and `langchain` + `langchain-groq` (Step 9 agent) — all real
  imports, verified by an AST sweep of `app`/`tests`/`alembic`.

**Risk model removed (2026-09-30)** — the Steps 10–12 risk classifier was
removed after it backfired. Deleted: `app/api/findings.py`, `app/api/risk.py`,
`app/api/webhooks.py`, `app/models/risk_finding.py`, `app/risk_model/`,
`app/schemas/risk.py`, `app/tasks/analyze_pr.py`, `app/tasks/reindex_changed.py`,
`app/benchmarks/risk_eval.py`, `frontend/src/pages/Findings.tsx`,
`frontend/src/pages/RiskTraining.tsx`. The PR analysis chain no longer
computes risk scores — the Risk/Confidence columns were removed from the
PR dashboard.

## Project layout

```
backend/
  app/
    main.py          # FastAPI entrypoint (mounts 9 routers: auth, search, chat,
                     # pull_requests, projects, repos, ingestion, analysis,
                     # observability)
    config.py        # pydantic settings (DATABASE_URL, REDIS_URL, UPSTASH_TOKEN,
                     # SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_CLIENT_ID/SECRET,
                     # CLONE_ROOT_DIR, EMBEDDING_*, LLM_PROVIDER/LLM_MODEL)
    core/            # security.py (Supabase JWT auth), rate_limit.py,
                     #          cost_tracking.py
    api/             # routers: auth, search, chat, pull_requests, projects,
                     #          repos, ingestion, analysis, observability
    db/              # session.py, base.py
    models/          # 9 models: user, project, repository, analysis_job, file,
                     #          symbol, import_stmt, edge, code_embedding
    schemas/         # auth, project, repo, job, analysis, github, chat
    agents/          # chat_chain.py + tools.py (Step 9 grounded agent)
    ingestion/       # clone.py, filters.py, language_detect.py
    analysis/        # parsers.py, resolve.py (tree-sitter + import resolution)
    tasks/           # inject_repo.py (ingest)
    embeddings/      # chunker.py, jina.py (Step 7)
    retrieval/       # search.py (Step 8 cosine retrieval)
    pr_analysis/     # chain.py, diff.py, impact.py (Step 14)
    benchmarks/      # retrieval_benchmark.py
    worker.py        # Celery app
  alembic/           # migrations (head: 2c35e0edd4ef drop risk_findings)
  tests/             # 60 tests: smoke, ingestion, analysis, chunking, chat, pr
frontend/
  src/
    App.tsx          # routes + AppShell
    api/client.ts    # typed fetch client
    api/types.ts     # mirrors Pydantic read schemas
    auth/            # AuthProvider, useAuth
    hooks/           # useJobStatus (TanStack polling)
    pages/           # Login, Dashboard, ProjectDetail, AnalysisStatus,
                     #          RepoExplorer, Search, Observability, Chat,
                     #          PRDashboard, Profile, Landing
    components/      # AppShell
```

## Prerequisites

- Python 3.11+ (tested with `backend/venv`)
- Node.js 22+
- Supabase project (Auth + Postgres with the `pgvector` extension)
- GitHub OAuth App (client ID + secret)
- Redis (Upstash works) for Celery
- Jina embedding model (first run downloads `jina-embeddings-v2-base-code`)

## Backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # then fill in values
```

Required `.env` values (see `.env.example`): `DATABASE_URL`, `REDIS_URL`,
`UPSTASH_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET`.

Run the API:

```powershell
cd backend
venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Run Celery (separate terminal; Windows needs `--pool=solo`):

```powershell
cd backend
venv\Scripts\celery -A app.worker worker --pool=solo --loglevel=info
```

If no worker is running, `POST /repos/{id}/ingest` returns 503 and the job is
marked failed; with a worker, the job stays `queued` until it picks the task up.

Apply migrations:

```powershell
cd backend
venv\Scripts\alembic upgrade head
```

## Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

`VITE_API_BASE`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` come from
`frontend/.env` (public values only; the JWT lives in `localStorage`). The dev
server runs on `http://localhost:5173`.

## Tests

```powershell
cd backend
venv\Scripts\python -m pytest
venv\Scripts\python -m ruff check app tests alembic
venv\Scripts\python -m ruff format --check app tests alembic
```

Current state: **60 tests pass; `ruff check` and `ruff format --check` are
both clean** (as of 2026-09-30). Frontend gates:

```powershell
cd frontend
npm run lint
npm run build
```

Both are clean.
