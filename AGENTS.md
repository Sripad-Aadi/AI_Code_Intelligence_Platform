# AGENTS.md — AI Software Engineering Intelligence Platform

FastAPI backend + React (Vite) frontend, no Docker. Development is driven by the
19-step plan in `AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`,
executed in strict Step 1→19 order with an acceptance gate after each step.
Steps 1–3 are committed: Step 2 (Supabase auth + projects + repo CRUD) and Step 3
(GitHub OAuth + shallow clone). Step 3's end-to-end proof (OAuth → list repos →
shallow clone) is still pending because the app cannot boot: `backend/.env` is
missing `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. The frontend is still
untouched Vite boilerplate (Step 6).

## Hard rule: `.env` is off-limits

- Never **read**, **modify**, or **print** `backend/.env` (or root `.env`) — it
  holds live credentials. Only `.env.example` files and env vars the user
  provides are fair game. Mask any credentials that leak into tool output.
- `backend/.env` must stay out of the git index: `backend/tests/test_smoke.py`
  enforces this via `git ls-files`. If an agent ever stages it, the gate fails.

## Developer commands (run from `backend/`; venv is `backend/venv`)

```powershell
cd backend
venv\Scripts\python -m pytest                        # tests (currently 3 smoke-only)
venv\Scripts\python -m ruff check app tests alembic  # lint: E/W/F/I, line 88
venv\Scripts\python -m ruff format --check app tests alembic
venv\Scripts\uvicorn app.main:app --reload           # API on :8000
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

- **`backend/requirements.txt` is stale**: `app/config.py` imports
  `pydantic-settings` and `app/core/security.py` imports `httpx`, but neither is
  pinned. `httpx` is not even installed in the venv yet, so
  `uvicorn app.main:app` fails on import until it is installed and pinned.
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
- **Autogenerate currently yields empty migrations**: env.py sets
  `target_metadata = Base.metadata` but never imports the model modules, so the
  metadata is empty at load time. `app/models/__init__.py` exports
  `User`/`Project`/`ProjectRepository` but nothing imports it. Add
  `import app.models` (or the model modules) in env.py before generating a real
  migration; the existing migration was generated empty (`pass` bodies).
- DB is stamped `b73895e1740e`, but that stub migration's file was deleted from
  `backend/alembic/versions/`, so alembic fails with "Can't locate revision
  identified by 'b73895e1740e'". The `users` / `projects` /
  `project_repositories` tables were **not** created by it — verify the Supabase
  schema and reconcile `alembic_version` before the next migration.

## Supabase free-tier quirks

- Idle free-tier projects pause: `db.<ref>.supabase.co` intermittently fails DNS
  resolution. Resume the project in the dashboard.
- The transaction-pooler host (`aws-0-<region>.pooler.supabase.com:6543`)
  requires the project ref in the username (`postgres.<project-ref>@...`),
  otherwise `FATAL: (ENOIDENTIFIER) no tenant identifier provided`.

## Structure

- Mounted routers: `auth`, `projects`, `repos` (`app/main.py`). `auth` now has
  the real GitHub OAuth flow (Step 3): `GET /auth/github/login?state=<supabase-jwt>`
  (307 → GitHub), `GET /auth/github/callback` (exchanges code, stores the GitHub
  token on the caller's `users` row), `GET /auth/github/status`.
  `ingestion`, `chat`, `findings`, `search`, `pull_requests`, `webhooks` are
  placeholder stubs for later steps and are commented out.
- Auth is Supabase JWT (RS256 via JWKS), decoded in `app/core/security.py`, which
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
- Frontend `src/pages/*`, `src/api/client.ts`, `src/hooks/useJobStatus.ts` are
  empty; react-router, react-query, and tailwind are not installed (needed at
  Step 6).