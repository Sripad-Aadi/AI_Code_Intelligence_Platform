# AGENTS.md — AI Software Engineering Intelligence Platform

FastAPI backend + React (Vite) frontend, no Docker. Development is driven by the
19-step plan in `AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`,
executed in strict Step 1→19 order with an acceptance gate after each step.
Steps 1–7 are committed: Step 2 (Supabase auth + projects + repo CRUD), Step 3
(GitHub OAuth + shallow clone), Step 4 (repo ingestion via Celery), Step 5
(structural code analysis via tree-sitter), Step 6 (React frontend), and Step 7
(code chunking + jina embeddings into pgvector).
Step 3's
end-to-end proof (OAuth → list repos → shallow clone) was verified on 2026-09-26:
a dev user linked GitHub (`Sripad-Aadi`), listed 18 repos, attached +
shallow-cloned `Sripad-Aadi/AI_Code_Intelligence_Platform` into `backend/.clones/`
(via the API, not the test harness). Step 4's proof ran the same day: a Celery
worker (Upstash Redis broker) executed `ingestion.ingest_repo` on that clone —
filters + language detection → 132 files scanned / 99 indexed, with a language
histogram stored on the `analysis_jobs` row and pollable via `GET /jobs/{id}`.
Step 5's E2E proof ran the same day through the API/worker: re-ingest →
files/symbols/imports/edges persisted, `GET /repos/{id}/files|symbols|edges`
return data, import edges resolve through the `backend/` subdir (26 Python
edges: e.g. `backend/app/api/projects.py => backend/app/models/project.py`),
symbol span accuracy verified against source (`lifespan` 12–21, `GET /health`
41–43 in `backend/app/main.py`).
Step 6's proof ran the same day: the frontend (react-router 7 + TanStack Query
5 + Tailwind 4 + supabase-js) builds (lint + `npm run build` clean) and all 14
endpoint checks its four pages depend on passed via the API with a demo Supabase
JWT — including a live Celery ingest (job `524ca91a…` → completed, 99/132
files, 39 symbols) polled like the Analysis-status page does.

## Hard rule: `.env` is off-limits

- Never **read**, **modify**, or **print** `backend/.env` (or root `.env`) — it
  holds live credentials. Only `.env.example` files and env vars the user
  provides are fair game. Mask any credentials that leak into tool output.
- `backend/.env` must stay out of the git index: `backend/tests/test_smoke.py`
  enforces this via `git ls-files`. If an agent ever stages it, the gate fails.

## Developer commands (run from `backend/`; venv is `backend/venv`)

```powershell
cd backend
venv\Scripts\python -m pytest                        # tests (38: 3 smoke + 6 ingestion + 11 analysis + 18 chunking)
venv\Scripts\python -m ruff check app tests alembic  # lint: E/W/F/I, line 88
venv\Scripts\python -m ruff format --check app tests alembic
venv\Scripts\uvicorn app.main:app --reload           # API on :8000
venv\Scripts\celery -A app.worker worker --pool=solo --loglevel=info  # Step 5 worker (2nd terminal)
venv\Scripts\alembic revision --autogenerate -m "msg"
venv\Scripts\alembic upgrade head
venv\Scripts\alembic current
```

Frontend commands (run from `frontend/`; Node 22, no CI server needed):

```powershell
cd frontend
npm install            # after first checkout / dep changes
npm run dev            # Vite dev server on :5173 (proxies via CORS to :8000)
npm run build          # acceptance gate: tsc -b && vite build
npm run lint           # eslint (react-refresh/only-export-components is strict: split helpers out of .tsx)
```

- PowerShell, not bash: heredocs (`cat > x << EOF`) fail; use the `write` tool.
  Inline `python -c` breaks on quotes/f-strings — write a temp `.py` file with
  the `write` tool and run it instead.
- **Never leave servers running.** Background shells started via
  `background: true` (`uvicorn`, `celery`, `npm run dev`) keep holding their
  ports after the task is done, which blocks the user from starting the same
  server. Stop the listening process before ending a task:
  `Get-NetTCPConnection -LocalPort <port> -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`
  (note: Vite binds `[::1]:5173`, so probe `http://localhost:5173`, not
  `127.0.0.1`). Only leave a server up if the user asked for it.
- `ruff format` (not black) is the formatter, even though `tool.black` exists in
  `pyproject.toml`. Alembic files are part of the lint/format gate.
- **Frontend secrets**: `frontend/.env` (gitignored via root `.gitignore`) only
  holds public values — `VITE_API_BASE`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY`. The JWT lives in `localStorage`
  (`ai_sip_access_token`), same as the test-harness approach. Sign-in is
  Supabase email/password only — the paste-a-token box is gone, because
  `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` are always configured. The
  non-UI `/login?token=<jwt>` deep link still works and is what scripted/E2E
  sign-in uses (minting a JWT beats typing a password).

## Dependency and config gotchas (verified)

- **Celery broker on Windows/Upstash**: the worker needs `--pool=solo` (Windows
  has no `os.fork`; the default prefork pool refuses to start). The broker URL
  is resolved without reading `.env`: explicit `CELERY_BROKER_URL` → `REDIS_URL`
  if already redis(s):// → derived `rediss://default:<UPSTASH_TOKEN>@<rest-host>:6379`
  (Upstash REST and Redis share host + token). redis-py refuses `rediss://`
  URLs without `ssl_cert_reqs`, so `app/worker.py` appends
  `?ssl_cert_reqs=CERT_NONE`. The API enqueues with `.delay()`; if the broker
  is unreachable, `POST /repos/{id}/ingest` returns 503 (job marked failed).
- `app/config.py` requires `DATABASE_URL`, `REDIS_URL`, `UPSTASH_TOKEN`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GITHUB_CLIENT_ID`,
  `GITHUB_CLIENT_SECRET` — importing `app.config` raises a pydantic
  ValidationError when any are missing. Alembic is exempt: `alembic/env.py`
  imports only `app.db.base`, so migrations need just `DATABASE_URL` exported.
- **tree-sitter pins (Step 5, verified empirically)**: `tree-sitter-languages`
  calls the pre-0.22 `Language(path, name)` constructor, so `tree-sitter`
  must be `==0.21.3` (0.24 and 0.26 both broke). Also, in 0.21 bindings
  `Node.start_point`/`end_point` are plain `(row, col)` tuples (no `.row`) —
  `app/analysis/parsers.py` handles both via `_point_row`. Grammars available:
  python, javascript, typescript, tsx, go, rust, java, c, cpp, ruby, php,
  kotlin, scala, bash, css, html, json, yaml, toml, sql, lua, r, elixir,
  erlang, haskell. **Missing** (files recorded, not parsed): c-sharp, swift,
  dart, zig, scss.
- **Embedding stack pins (Step 7, verified by ImportError)**: `transformers`
  **must stay on 4.x**. `jina-embeddings-v2` ships a custom `JinaBertForMaskedLM`
  behind an `auto_map`, so it loads via `trust_remote_code=True` — and that
  remote `modeling_bert.py` does
  `from transformers.pytorch_utils import find_pruneable_heads_and_indices`,
  which **transformers 5.x removed**. transformers 5.17 + sentence-transformers
  6.1 fail at model load with `ImportError: cannot import name
  'find_pruneable_heads_and_indices'`. Since sentence-transformers 6.x
  hard-requires `transformers>=5,<6`, both go back together: pinned set is
  `sentence-transformers==3.4.1`, `transformers==4.46.3`,
  `huggingface-hub==0.35.3` (hub 0.x because only ST 6.x accepts hub 1.x, and
  the transformers-4.x custom-code loader expects the 0.x API). `torch` must be
  the **CPU wheel** (`--index-url https://download.pytorch.org/whl/cpu`,
  124MB) — the default PyPI wheel drags in ~2.5GB of unused CUDA libraries.
- **int8 dynamic quantization does NOT work for this model** (Step 7, measured):
  `torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear})` is
  *slower* than fp32 here (0.69x) **and wrong** — it bypasses the output
  normalisation, returning vectors of norm ~146 instead of 1.0 (mean cosine
  vs fp32 = 146.0), which would silently destroy `<=>` cosine search. Do not
  "optimise" with it.
- **CPU embedding throughput (Step 7, re-measured on this i5-1235U — the old
  note here was wrong, see below)**: the demo repo's 77 chunks now embed in
  ~1.2–1.6s/chunk (89–125s) at `EMBEDDING_MAX_SEQ_LENGTH=512`, down from
  ~7–11s/chunk. `max_seq_length` is the dominant lever and **512 is correct**,
  not just cheap: it is the model's *trained* context, whereas 2048 was an
  extrapolation.
  - **Why the long tail dominated**: cost is strictly `padded_tokens / ~200
    tok/s`, and ST pads each batch to *that batch's* longest member
    (`padding=True` = longest-in-batch, never `max_length`; truncation is
    already `longest_first` with `max_length`, so no `truncation=True` /
    `padding='longest'` fix is needed — that code is correct upstream).
    Chunk lengths are very long-tailed — median 152 tok but p90 645 and max
    3458, with 8 of 77 over 512 — so at 2048 one batch of 16 padded to 3458
    alone ran **over 10 minutes** while a median batch of 16 took 14s.
  - **Attention is quadratic in sequence length**, so the tail is worse than
    linear: throughput *falls* from 209 tok/s at 512 to 125 tok/s at 1024.
    Measured 77-chunk totals: 512 → 89–125s, 1024 → 215s.
  - Truncation hits only the **vector**, never the stored `content` (which
    stays the verbatim span), and only 8/77 chunks are affected. A 3,458-tok
    chunk embeds *faster* (4.96s) than a 1,301-tok one (8.85s) precisely
    because it truncates to 512.
- **`EMBEDDING_TORCH_THREADS` is a knob, not a fix** (measured, full 77-chunk
  repo at 512): 1 → 300s, 2 → 197s, 4 → 183s, 6 → 174s, 8 → 132s, 12 → 149s,
  and torch's own default (10) → 89–125s. The 8/10/12 rows are within
  run-to-run noise (~40% spread, likely thermal), so the default wins and the
  setting stays **unset by default**. An earlier hypothesis that OpenMP
  spin-wait on this 2P+8E part was the cause was **wrong** — single-threaded is
  3.4x *slower*, so threading genuinely helps. `jina.py:_configure_threads()`
  exports `OMP_NUM_THREADS`/`MKL_NUM_THREADS` *before* `import torch` (OpenMP
  reads them at init) and also calls `torch.set_num_threads()`; that ordering
  is load-bearing.
- **Model load is ~6–24s, one-off per process** (24s cold, ~6s with a warm HF
  cache), and is now logged separately from encode time, as are the structural
  walk and the embed pass — so "slow worker" is diagnosable from the log
  without re-timing by hand. The model is cached per process
  (`app/embeddings/jina.py` module global), so later repos in the same worker
  skip the load.

## Alembic / database state

- `alembic/env.py` inserts `DATABASE_URL` with `%`→`%%` escaping because
  ConfigParser interpolation rejects the `%40` (URL-encoded `@`) in the
  password. Never "fix" the URL in `.env` — the escaping belongs in env.py
  (already done).
- Autogenerate works: `alembic/env.py` imports `app.models`, so `Base.metadata`
  is populated and real migrations are produced (verified while generating the
  `analysis_jobs` table). Applied head: `d7c86d75d7b7` (add code_embeddings +
  `analysis_jobs.chunks_indexed`), previous: `a6dac032b9b5` (add structural
  analysis tables), before that: `79b4d93cb86f` (add analysis_jobs), then
  `12097b55786a` (users GitHub columns). `alembic current` =
  `d7c86d75d7b7 (head)`. The `symbols_indexed` and `chunks_indexed` add_columns
  carry `server_default='0'` (existing analysis_jobs rows would otherwise fail
  the NOT NULL ALTER).
- **pgvector is already enabled** on this Supabase project (verified 2026-09-27:
  `pg_extension` has `vector 0.8.2`, PostgreSQL 17.6, and the `hnsw` access
  method exists), so the Step 1 dashboard toggle was done. Migration
  `d7c86d75d7b7` still runs `CREATE EXTENSION IF NOT EXISTS vector` so a fresh
  database works without the manual toggle.
- The HNSW index is created **by the migration**
  (`ix_code_embeddings_embedding_hnsw`, `vector_cosine_ops`, `m=16`,
  `ef_construction=64`) rather than by pasting into the Supabase SQL editor as
  the plan says, so it is reproducible and `alembic downgrade` can drop it.
- Autogenerate does **not** emit the `import pgvector.sqlalchemy` line even
  though the generated `create_table` body references `pgvector.sqlalchemy…`.
  The checked-in migration was hand-corrected to import it explicitly.
- **pgvector value API gotchas (verified by round-trip)**: with
  `register_vector` wired up, a `select embedding` returns a
  `pgvector.psycopg2.vector.Vector`, which
  * has **no `__iter__`** — `np.asarray(v)` and `list(v)` both raise
    `TypeError: float() argument must be a string or a real number, not
    'Vector'`. Use `v.to_numpy()` or `v.to_list()`.
  * exposes `dimensions` as a **method**, not a property (`v.dimensions()`).
  * therefore `arr = np.array([v.to_numpy() for v in rows])` is the shape of
    code to copy in Step 8.
  Pass a **`list`**, not text, whenever the value goes through SQLAlchemy's
  typed bind param — i.e. `CodeEmbedding.embedding.cosine_distance(vec)`
  (Step 8, `app/retrieval/search.py`). pgvector 0.5.0's `Vector._to_db`
  accepts `list`/`ndarray`/`Vector` but **not `str`**: a `"[0.1, ...]"`
  string there raises `ValueError: expected list or ndarray` at execute
  time (verified 2026-09-28 — it 502'd the search endpoint until changed).
  The string form is still fine for *raw* SQL / psycopg2 params, where
  pgvector's implicit `text <-> vector` cast applies, and `_to_db` does the
  list→text serialisation itself. Cosine semantics check out on the live
  DB: distance to self = 0.000000, to an orthogonal unit vector = 1.000000.

## Supabase free-tier quirks

- Idle free-tier projects pause: `db.<ref>.supabase.co` intermittently fails DNS
  resolution. Resume the project in the dashboard.
- The transaction-pooler host (`aws-0-<region>.pooler.supabase.com:6543`)
  requires the project ref in the username (`postgres.<project-ref>@...`),
  otherwise `FATAL: (ENOIDENTIFIER) no tenant identifier provided`.
- **JWT signing is ES256 (EC keys), not RS256** — `users` JWTs verify with a
  JWKS entry that has `crv`/`x`/`y`, no RSA `n`/`e`. `decode_supabase_token`
  passes the raw JWK dict to `jose` (works for both RS256 and ES256), selected
  by the token's `alg` header. Never "fix" this back to a hardcoded RSA build.
- **Signup is enumeration-safe** (verified against this project, not from docs):
  signing up an already-registered email returns **HTTP 200, `session: null`,
  `user: null`** and sends no mail — indistinguishable from a brand-new
  account awaiting confirmation. Only `user === null` distinguishes them (a
  real signup returns the created user). `Login.tsx` therefore probes with
  `signInWithPassword` after a session-less signup: it signs the user in when
  the password matches, reports "not confirmed" for an unconfirmed existing
  account, and otherwise falls back on the `user == null` signal. Do **not**
  key off `status === 400`: 400 is also `email_address_invalid` (Supabase
  rejects `@example.com` as a reserved domain), and 429 is
  `over_email_send_rate_limit` (hitting the confirm-email rate limit on a
  free-tier project).
- The dashboard's **Project URL** is the bare domain (`https://<ref>.supabase.co`);
  the **REST API URL** adds `/rest/v1`. `SUPABASE_URL` must be the bare Project
  URL — the app builds the JWKS URL as `{SUPABASE_URL}/auth/v1/...`.

## Structure

- Mounted routers: `auth`, `projects`, `repos`, `ingestion`, `analysis`
  (`app/main.py`). `auth` has the real GitHub OAuth flow (Step 3):
  `GET /auth/github/login?state=<supabase-jwt>` (307 → GitHub),
  `GET /auth/github/callback` (exchanges code, stores the GitHub token on the
  caller's `users` row; **browsers get a 302 to `{FRONTEND_URL}/linked`** so
  the popup closes itself — never refreshes a code-bearing URL, which would
  replay a consumed code and trigger GitHub's `bad_verification_code`; API
  clients keep the JSON response), `GET /auth/github/status`,
  `DELETE /auth/github` (unlink — frees the `github_id`, exposed as the
  "Unlink" button next to the linked badge in `LinkGithub.tsx`).
  `FRONTEND_URL` (default `http://localhost:5173`) is a config setting.
  Because `uq_users_github_id` makes a GitHub account belong to exactly one
  user row, the callback **rejects a conflicting link with 409** (a clear
  error in the `/linked` popup) rather than silently stealing the binding.
  **Type gotcha**: `users.github_id` is `String(100)` but GitHub returns a
  *numeric* id, so the conflict check and assignment must coerce with
  `str(gh_user["id"])` — comparing the varchar column to an int makes Postgres
  raise `operator does not exist: character varying = integer` (HTTP 500).
  `ingestion` (Step 4) dispatches repo scans to Celery and is what the frontend
  polls: `POST /repos/{id}/ingest` (202 + enqueue), `GET /jobs/{job_id}` (status),
  `GET /repos/{id}/jobs` (history). `analysis` (Step 5) surfaces the parsed
  structure: `GET /repos/{id}/files` (path/limit/offset), `GET /files/{file_id}`
  (file + its symbols), `GET /repos/{id}/symbols` (kind/name filters), and
  `GET /repos/{id}/edges?edge_type=imports|belongs_to` (file→file / symbol→file).
  `search` (Step 8) and `observability` are mounted as well — `search_router`
  is deliberately registered **before** `repos_router`, or `/repos/search`
  would be swallowed by `/repos/{repo_id}`. `webhooks` is mounted but only
  half-implemented. `chat`, `findings` and `pull_requests` have **no files at
  all**: their 0-byte shells (plus the empty `agents/`, `parsing/` and
  `risk_model/` packages, 21 files total) were deleted in the 2026-09-28
  cleanup, so those frontend routes 404 until Steps 9/12/14 are written.
  `ruff check` and `ruff format --check` are clean as of that pass — keep them
  that way (34 pre-existing errors were fixed, not suppressed). Step 7 adds
  **no** endpoint — retrieval is Step 8's job; the only API surface that
  changed is `chunks_indexed` on the `AnalysisJobRead` schema.
- Step 7 embeddings (`backend/app/embeddings/`): `chunker.py` is **pure stdlib**
  (hermetic, 18 unit tests in `tests/test_chunking.py`) and does the chunking
  straight off the Step-5 symbol spans, so line metadata is the parser's own
  and cannot drift. One chunk per **top-level** symbol (nesting is detected by
  span containment, so a class chunk carries its methods and they are not
  emitted twice); files with no parseable structure fall back to markdown
  heading sections or paragraph blocks with `symbol_name` NULL. Spans over
  `MAX_CHUNK_LINES=120` are windowed into 100-line chunks with 20-line overlap,
  every window keeping its own exact `start_line`/`end_line`. Blank edges are
  trimmed so `content` starts on real code. `contextualize()` prepends
  `# file: …` / `# symbol: kind name (lines a-b)` to the text handed to the
  model while `content` stays the verbatim span — that is why the two differ.
  `jina.py` wraps the model: lazy, process-cached, `trust_remote_code=True`,
  L2-normalised (hence pgvector `<=>` cosine is meaningful), and
  `embed_query()` is the Step 8 entry point. Config: `EMBEDDING_ENABLED`
  (kill switch — structure still indexes), `EMBEDDING_MODEL`,
  `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_SEQ_LENGTH`. `_embed_chunks` in
  `app/tasks/inject_repo.py` never raises: it catches everything, rolls back
  the partial batch, and returns a `warning: …` string that the task stores on
  `job.error` **with status `completed`**, so a bad model download can never
  destroy the Steps 4–5 index. `AnalysisStatus.tsx` renders that as amber
  "Completed with warnings" (not the red "Job failed") whenever
  `status !== 'failed'`. `pgvector.psycopg2.register_vector` is wired as a
  SQLAlchemy `connect` event in `app/db/session.py`.
- **Step 7 ingest ordering** (extends the flush-ordering rule below): the
  structural phase **commits first** (`db.commit()` while the job is still
  `running`), then chunks are embedded in batches of 200 rows
  (`EMBED_BATCH_ROWS`) with a flush per batch, then the job is marked completed
  and committed again. The walk collects `file_ids_by_path: dict[str, UUID]`
  rather than ORM `SourceFile` objects on purpose — after the mid-task commit
  those objects are expired and every `.id` access would re-query.
- Step 6 frontend (`frontend/`, Vite 8 + React 19 + TS 6): `src/api/client.ts`
  is the typed fetch client (Bearer JWT from `localStorage`, 401 clears it,
  `VITE_API_BASE` default `http://localhost:8000`), `src/api/types.ts` mirrors
  the Pydantic read schemas. `src/auth/` = AuthProvider (Supabase JWT) +
  `useAuth` (context kept in `context.ts` because react-refresh forbids
  non-component exports from `.tsx`). `src/hooks/useJobStatus.ts` polls
  `GET /jobs/{id}` every 2 s with TanStack Query, stopping at
  completed/failed. Pages: `Login` (supabase-js email/password only, plus a
  UI-less `?token=` deep link for scripted sign-in), `Dashboard` (projects
  CRUD + GitHub link popup via `components/LinkGithub.tsx`), `ProjectDetail`
  (attach repo from `GET /user/repos`, analyze → navigate to `/jobs/:id?repo=`),
  `AnalysisStatus` (live poll + counts + language histogram + history),
  `RepoExplorer` (file tree built client-side from flat paths, symbol table
  with kind filters, imports/belongs_to edge tables, file-detail pane with
  symbol spans). Tailwind 4 via `@tailwindcss/vite` (CSS-first, `@import
  "tailwindcss"`, `@layer components` for `.btn/.card/.badge/...`).
- Auth is Supabase JWT (RS256 **or ES256** via JWKS — this project's key is
  ES256/EC), decoded in `app/core/security.py`, which
  upserts a local shadow `users` row on first authenticated request — auth
  endpoints need the `users` table to exist.
- GitHub OAuth binds the token to the Supabase user via the OAuth `state` param,
  which must be the caller's Supabase JWT. The token lives plaintext in
  `users.github_access_token` until Step 18 encrypts it.
- `GET /user/repos` lists GitHub repos (owner + collaborator) using the stored
  token. Repo attach (`POST /projects/{id}/repositories`) looks up the repo on
  GitHub, shallow-clones it (`git clone --depth=1`, private-repo OK via token
  URL) into `CLONE_ROOT_DIR` (default `./.clones`, gitignored), and records
  owner/name/default_branch/last_indexed_at. GitHub API helpers live in
  `app/services/github.py`, the clone in `app/ingestion/clone.py`.
- Step 4 ingestion: `app/ingestion/filters.py` (skip `node_modules`/`.git`/
  `dist`/`build`/`vendor`/`__pycache__`, lockfiles, binary+media, minified
  bundles, `.env`), `app/ingestion/language_detect.py` (extension → language),
  `app/worker.py` (Celery app), `app/tasks/inject_repo.py` (`ingestion.ingest_repo`
  task — walks the clone, updates the `analysis_jobs` row). `analysis_jobs`
  columns: id, repo_id, status, started_at, finished_at, error, files_scanned,
  files_indexed, symbols_indexed, chunks_indexed (Step 7), languages (JSON
  histogram), created_at.
- Step 5 structural analysis: `app/analysis/parsers.py` (tree-sitter parse →
  symbols with precise 1-based line spans, imports, FastAPI/Flask + Express
  routes; per-grammar cached parsers; a bad parse returns `ParseResult(error)`
  rather than raising, recorded on `files.parse_error`), `app/analysis/resolve.py`
  (import specifier → repo-relative path; Python absolute imports walk the
  ancestors of the importing file's dir — handles `repo/backend/app/...`
  layouts; JS/TS relative + `@/`; best-effort for the rest; local-only, target
  must exist on disk). New tables: `files` (unique repo_id+path, parse_error),
  `symbols` (kind function|class|method|route, 1-based start_line/end_line),
  `imports` (module/is_relative/resolved_path), `edges` (source_kind
  file|symbol, edge_type imports|belongs_to, target FK files.id). Route-decorated
  Python handlers count once (the route symbol; the inner function_definition
  is skipped); JS/TS named arrow functions (`const fn = () => {}`) are captured
  as symbols. **Route symbols are named `"<METHOD> <path>"`** (e.g.
  `GET /items/{item_id}`), not after the handler function — tests asserting on
  route names need that spelling.
- Step 7 vectors: table `code_embeddings` (id, repo_id, file_id FK→files ON
  DELETE CASCADE, file_path, language, symbol_kind, symbol_name, start_line,
  end_line, content, embedding `vector(768)`, created_at) + the HNSW cosine
  index. The plan's column list had no `file_id`/`language`/`symbol_kind`; they
  are additions because this step's stated focus is the row metadata, and
  `file_id` is what lets re-indexing delete chunks by cascade.
- **CRITICAL flush-ordering gotcha**: the ORM unit-of-work sorts INSERTs by
  declared `relationship()`s, and this project's models declare none — the
  insert order falls out of mapper registration order (CodeEdge registers first,
  so in one flush SQLAlchemy INSERTs `edges` *before* `files`, tripping the FK
  constraints). `ingest_repo` therefore persists in explicit phases:
  `db.add_all(file_rows)` → `flush()` → `symbols+imports` → `flush()` → `edges`,
  and calls `db.commit()` *inside* the try so a commit-time failure is recorded
  on the job (the `db_session()` context manager commits in `__exit__`, which is
  outside the task's try and would otherwise leave the job stuck `queued`).
- Frontend `src/pages/*`, `src/api/client.ts`, `src/hooks/useJobStatus.ts` are
  empty; react-router, react-query, and tailwind are not installed (needed at
  Step 6).