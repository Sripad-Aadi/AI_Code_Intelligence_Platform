# AGENTS.md — AI Software Engineering Intelligence Platform

FastAPI backend + React (Vite) frontend, no Docker. Development is driven by the
19-step plan in `AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`,
executed in strict Step 1→19 order with an acceptance gate after each step.
Steps 1–6 are committed: Step 2 (Supabase auth + projects + repo CRUD), Step 3
(GitHub OAuth + shallow clone), Step 4 (repo ingestion via Celery), Step 5
(structural code analysis via tree-sitter), and Step 6 (React frontend).
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
venv\Scripts\python -m pytest                        # tests (20: 3 smoke + 6 ingestion + 11 analysis)
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

## Alembic / database state

- `alembic/env.py` inserts `DATABASE_URL` with `%`→`%%` escaping because
  ConfigParser interpolation rejects the `%40` (URL-encoded `@`) in the
  password. Never "fix" the URL in `.env` — the escaping belongs in env.py
  (already done).
- Autogenerate works: `alembic/env.py` imports `app.models`, so `Base.metadata`
  is populated and real migrations are produced (verified while generating the
  `analysis_jobs` table). Applied head: `a6dac032b9b5` (add structural analysis
  tables), previous: `79b4d93cb86f` (add analysis_jobs), before that:
  `12097b55786a` (users GitHub columns). `alembic current` =
  `a6dac032b9b5 (head)`. The `symbols_indexed` add_column carries
  `server_default='0'` (existing analysis_jobs rows would otherwise fail the
  NOT NULL ALTER).

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
  `chat`, `findings`, `search`, `pull_requests`, `webhooks` are placeholder
  stubs for later steps and remain commented out in `app/main.py`.
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
  files_indexed, symbols_indexed, languages (JSON histogram), created_at.
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
  as symbols.
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