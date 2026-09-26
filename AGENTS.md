# AGENTS.md — AI Software Engineering Intelligence Platform

FastAPI backend + React (Vite) frontend, no Docker. Development is driven by the
19-step plan in `AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`,
executed in strict Step 1→19 order with an acceptance gate after each step.
Steps 1–4 are committed: Step 2 (Supabase auth + projects + repo CRUD), Step 3
(GitHub OAuth + shallow clone), and Step 4 (repo ingestion via Celery). Step 3's
end-to-end proof (OAuth → list repos → shallow clone) was verified on 2026-09-26:
a dev user linked GitHub (`Sripad-Aadi`), listed 18 repos, attached +
shallow-cloned `Sripad-Aadi/AI_Code_Intelligence_Platform` into `backend/.clones/`
(via the API, not the test harness). Step 4's proof ran the same day: a Celery
worker (Upstash Redis broker) executed `ingestion.ingest_repo` on that clone —
filters + language detection → 132 files scanned / 99 indexed, with a language
histogram stored on the `analysis_jobs` row and pollable via `GET /jobs/{id}`.
The frontend is still untouched Vite boilerplate (Step 6).

## Hard rule: `.env` is off-limits

- Never **read**, **modify**, or **print** `backend/.env` (or root `.env`) — it
  holds live credentials. Only `.env.example` files and env vars the user
  provides are fair game. Mask any credentials that leak into tool output.
- `backend/.env` must stay out of the git index: `backend/tests/test_smoke.py`
  enforces this via `git ls-files`. If an agent ever stages it, the gate fails.

## Developer commands (run from `backend/`; venv is `backend/venv`)

```powershell
cd backend
venv\Scripts\python -m pytest                        # tests (9: 3 smoke + 6 ingestion)
venv\Scripts\python -m ruff check app tests alembic  # lint: E/W/F/I, line 88
venv\Scripts\python -m ruff format --check app tests alembic
venv\Scripts\uvicorn app.main:app --reload           # API on :8000
venv\Scripts\celery -A app.worker worker --pool=solo --loglevel=info  # Step 4 worker (2nd terminal)
venv\Scripts\alembic revision --autogenerate -m "msg"
venv\Scripts\alembic upgrade head
venv\Scripts\alembic current
```

- PowerShell, not bash: heredocs (`cat > x << EOF`) fail; use the `write` tool.
  Inline `python -c` breaks on quotes/f-strings — write a temp `.py` file with
  the `write` tool and run it instead.
- `ruff format` (not black) is the formatter, even though `tool.black` exists in
  `pyproject.toml`. Alembic files are part of the lint/format gate.

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

## Alembic / database state

- `alembic/env.py` inserts `DATABASE_URL` with `%`→`%%` escaping because
  ConfigParser interpolation rejects the `%40` (URL-encoded `@`) in the
  password. Never "fix" the URL in `.env` — the escaping belongs in env.py
  (already done).
- Autogenerate works: `alembic/env.py` imports `app.models`, so `Base.metadata`
  is populated and real migrations are produced (verified while generating the
  `analysis_jobs` table). Applied head: `79b4d93cb86f` (add analysis_jobs),
  previous: `12097b55786a` (users GitHub columns). `alembic current` =
  `79b4d93cb86f (head)`.

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
- The dashboard's **Project URL** is the bare domain (`https://<ref>.supabase.co`);
  the **REST API URL** adds `/rest/v1`. `SUPABASE_URL` must be the bare Project
  URL — the app builds the JWKS URL as `{SUPABASE_URL}/auth/v1/...`.

## Structure

- Mounted routers: `auth`, `projects`, `repos`, `ingestion` (`app/main.py`).
  `auth` has the real GitHub OAuth flow (Step 3): `GET /auth/github/login?state=<supabase-jwt>`
  (307 → GitHub), `GET /auth/github/callback` (exchanges code, stores the GitHub
  token on the caller's `users` row), `GET /auth/github/status`.
  `ingestion` (Step 4) dispatches repo scans to Celery and is what the frontend
  polls: `POST /repos/{id}/ingest` (202 + enqueue), `GET /jobs/{job_id}` (status),
  `GET /repos/{id}/jobs` (history). `chat`, `findings`, `search`,
  `pull_requests`, `webhooks` are placeholder stubs for later steps and remain
  commented out in `app/main.py`.
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
  files_indexed, languages (JSON histogram), created_at.
- Frontend `src/pages/*`, `src/api/client.ts`, `src/hooks/useJobStatus.ts` are
  empty; react-router, react-query, and tailwind are not installed (needed at
  Step 6).