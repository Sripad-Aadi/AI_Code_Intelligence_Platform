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

**Still unwired (Steps 11/12/14)** — frontend calls with no backend endpoint,
so those pages/cards fail when used:

- Findings (`/repos/:repoId/findings`, `/findings/summary`): no `findings`
  router and no `risk_findings` table (Step 12).
- PR analysis (`/repos/:repoId/prs/{pr}/analysis`): no `pull_requests` router
  and `pr_analysis/chain.py` still has no LLM call (Step 14).
- Risk model (`/risk/train`, `/risk/evaluate`): no router — these back *both*
  the RiskTraining page and the "Risk Model" card on Observability (Steps
  11/15), so those two forms fail today.
- Slack alerting from the Celery task on job failure is written but was not
  exercised in this pass.

**Skeleton / not verified (Steps 13–19)** — routes registered in the frontend,
partial work in the backend:

- Step 14: `pr_analysis/chain.py` has no LLM call, `tasks/analyze_pr.py`
  persists nothing, and there is no `pull_requests` table (its router was an
  empty shell and has been deleted).
- `app/api/webhooks.py` is mounted but half-implemented and `core/encryption.py`
  is unused (GitHub tokens are still plaintext) — neither has been run or
  proven. `core/cost_tracking.py` **is** fed now (Step 9 chat records usage
  every turn) but is in-memory, so totals reset when the API restarts.
- `benchmarks/risk_eval.py` imports `app.risk_model.train`, which was an empty
  shell, so it still cannot import (Step 15 does not exist yet).

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
- `requirements.txt` now declares `numpy` and `scikit-learn`, which
  `benchmarks/risk_eval.py` imports. `langchain` and `radon` are installed in
  the venv but imported by no code at all, so they are deliberately not
  declared.

## Project layout

```
backend/
  app/
    main.py          # FastAPI entrypoint (mounts 9 routers: auth, search, chat,
                     # projects, repos, ingestion, analysis, observability,
                     # webhooks — search before repos on purpose)
    config.py        # pydantic settings (DATABASE_URL, REDIS_URL, UPSTASH_TOKEN,
                     # SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_CLIENT_ID/SECRET,
                     # CLONE_ROOT_DIR, EMBEDDING_*, LLM_PROVIDER/LLM_MODEL)
    core/            # security.py (Supabase JWT auth), rate_limit.py,
                     #          encryption.py / cost_tracking.py / logging_json.py
    api/             # routers: auth, search, chat, projects, repos, ingestion,
                     #          analysis, observability, webhooks
    db/              # session.py, base.py
    models/          # 9 models: user, project, repository, analysis_job, file,
                     #          symbol, import_stmt, edge, code_embedding
    schemas/         # auth, project, repo, job, analysis, github, chat
    agents/          # chat_chain.py + tools.py (Step 9 grounded agent)
    ingestion/       # clone.py, filters.py, language_detect.py
    analysis/        # parsers.py, resolve.py (tree-sitter + import resolution)
    tasks/           # inject_repo.py (ingest), reindex_changed.py,
                     #          analyze_pr.py (stub)
    embeddings/      # chunker.py, jina.py (Step 7)
    retrieval/       # search.py (Step 8 cosine retrieval)
    pr_analysis/     # chain.py, diff.py, impact.py (Step 14, partial)
    benchmarks/      # retrieval_benchmark.py (imports; risk_eval.py cannot)
    worker.py        # Celery app
  alembic/           # migrations (head: d7c86d75d7b7)
  tests/             # 49 tests: smoke, ingestion, analysis, chunking, chat
frontend/
  src/
    App.tsx          # routes + AppShell
    api/client.ts    # typed fetch client
    api/types.ts     # mirrors Pydantic read schemas
    auth/            # AuthProvider, useAuth
    hooks/           # useJobStatus (TanStack polling)
    pages/           # Login, Dashboard, ProjectDetail, AnalysisStatus,
                     #          RepoExplorer, Search, Observability, Chat (working);
                     #          Findings/PRDashboard/RiskTraining (endpoints missing)
    components/      # AppShell, LinkGithub
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

Current state: **38 tests pass; `ruff check` and `ruff format --check` are
both clean** (as of fix pass 2, 2026-09-28). Frontend gates:

```powershell
cd frontend
npm run lint
npm run build
```

Both are clean.
