# AI Software Engineering Intelligence Platform

An AI-powered platform that helps developers understand, explore, and
analyze software repositories through semantic code search,
repository-aware AI chat, structural code analysis, and engineering
observability.

## Overview

Understanding an unfamiliar codebase can be time-consuming, especially
when a project contains multiple files, functions, dependencies, and
interconnected components.

The **AI Software Engineering Intelligence Platform** addresses this
challenge by connecting GitHub repositories to an AI-assisted
development environment. Developers can organize repositories into
projects, clone and index source code, explore code structure, search
for relevant implementations using natural-language queries, and ask
questions about their codebase with supporting code references.

The platform combines repository ingestion, code parsing, semantic
retrieval, and Large Language Model (LLM) integration to make code
exploration more accessible and context-aware.

## Key Features

### 1. GitHub Integration

-   Connect a GitHub account through authentication.
-   Retrieve and browse accessible repositories.
-   Attach repositories to individual projects.
-   Clone selected repositories and branches for analysis.
-   Manage the GitHub connection through profile settings.

### 2. Project Management

-   Create projects with custom names and descriptions.
-   Organize related repositories under individual projects.
-   Attach and manage repositories within projects.
-   View repository indexing and analysis status.
-   Re-run repository analysis when required.

### 3. Repository Ingestion and Code Indexing

-   Clone repositories for server-side processing.
-   Identify and process supported source files.
-   Extract repository structure and programming-language information.
-   Index files and code symbols for exploration and retrieval.
-   Track indexing and analysis jobs.

### 4. Semantic Code Search

-   Search source code using natural-language queries.
-   Retrieve code sections relevant to a developer's question.
-   Filter search results by programming language.
-   Configure the number of results to retrieve.
-   Inspect matching files, functions, and relevant code snippets.

Semantic search helps developers locate code by its meaning and purpose
rather than relying exclusively on exact keyword matches.

### 5. Repository-Aware AI Chat

-   Ask natural-language questions about a connected repository.
-   Retrieve relevant code and documentation as supporting context.
-   Generate answers grounded in retrieved repository information.
-   Display supporting evidence with file names and line references.
-   Explore database models, authentication flows, application
    structure, and other implementation details.

### 6. Code Intelligence

-   Browse the indexed repository structure.
-   Explore available files and code symbols.
-   Inspect import relationships and code organization.
-   View programming-language distribution and indexing statistics.
-   Navigate repository information from a centralized project
    interface.

### 7. Pull Request Interface

-   Access the pull-request section from the repository analysis
    dashboard.
-   Provide an interface for integrating pull-request-related analysis.
-   Support the planned extension toward change-impact analysis and
    identification of potentially affected components.


### 8. Observability and Usage Tracking

-   Monitor total, queued, running, completed, and failed analysis jobs.
-   View average job duration.
-   Track the number of indexed files and symbols.
-   Monitor embedded code chunks.
-   Track LLM API calls and associated costs.
-   Inspect input and output token usage.
-   Review usage statistics by model.


### 9. Account and Profile Management

-   View account information.
-   Manage the linked GitHub account.
-   Configure password-based authentication where supported.
-   Access account settings through the profile dashboard.

## Technology Stack

The platform's implementation uses a combination of web technologies,
source-code analysis, and AI-assisted retrieval. The following reflects
the intended technology stack; verify individual components against the
actual implementation before publishing.

  Layer                   Technologies
  ----------------------- ----------------------------------------------------
  Frontend                React, TypeScript, Tailwind CSS
  Backend                 Python, FastAPI, SQLAlchemy, Alembic
  Database                PostgreSQL, pgvector
  Background Processing   Celery, Redis
  AI/ML                   PyTorch, Transformers, Sentence Transformers, Hugging Face Hub, Scikit-learn
  AI Orchestration        LangChain
  Source Control          Git, GitHub API
  Code Analysis           AST-based parsing and source-code analysis tools
  Semantic Retrieval      Code embeddings and vector search


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


```powershell
cd frontend
npm run lint
npm run build
```

Both are clean.
