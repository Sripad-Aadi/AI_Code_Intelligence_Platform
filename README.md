# AI Software Engineering Intelligence Platform

A full-stack AI platform that turns a GitHub repository into an engineering
knowledge base: structural parsing, dependency analysis, semantic code search,
grounded AI chat, a lightweight code-risk classifier, and pull-request impact
analysis.

Implementation roadmap and acceptance gates: see
`AI_Software_Engineering_Intelligence_Platform_Implementation_Plan_v2.docx`
(19 steps across V1 → V1.5 → V2 → V2.5 → V3). The v2 plan is authoritative
where it conflicts with the Overview document.

## Stack

| Layer      | Choice                                              |
|------------|-----------------------------------------------------|
| Backend    | Python 3.12, FastAPI, SQLAlchemy, Alembic, Celery   |
| Frontend   | React 19, TypeScript, Vite                          |
| Database   | Supabase Postgres + pgvector (free tier)            |
| Queue      | Upstash Redis (serverless, free tier)               |
| Parsing    | py-tree-sitter + tree-sitter-languages              |
| Embeddings | jina-embeddings-v2-base-code (768-d, CPU)           |
| LLM        | Groq (Llama 3.3 70B), selected via env var          |
| Risk model | scikit-learn baseline first, PyTorch MLP only if it wins |

No Docker required — plain venv + uvicorn + npm run dev.

## Repository layout

```
backend/
  app/
    api/          FastAPI routers (auth, projects, repos, chat, ...)
    core/         security, rate limiting
    db/           engine/session setup
    models/       SQLAlchemy models
    schemas/      Pydantic schemas
    ingestion/    clone, filters, language detection
    parsing/      tree-sitter parser, chunker
    embeddings/   embedding generation
    retrieval/    pgvector search
    agents/       LangChain tools + chat chain
    risk_model/   features, training, inference
    pr_analysis/  diff, impact walk, PR chain
    tasks/        Celery tasks
  alembic/        DB migrations
  tests/          pytest suite
frontend/
  src/
    pages/        Dashboard, ProjectDetail, AnalysisStatus, RepoExplorer,
                  Findings, Chat, PRDashboard
    api/          typed API client
    hooks/        React Query hooks (job polling, ...)
```

## Setup

### Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then fill in real credentials
```

Run the API:

```powershell
venv\Scripts\uvicorn app.main:app --reload
```

Run the Celery worker (once ingestion exists):

```powershell
venv\Scripts\celery -A app.worker worker --loglevel=info
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Quality gates

```powershell
cd backend
venv\Scripts\python -m pytest          # tests pass
venv\Scripts\python -m ruff check app tests alembic   # lint clean
```

## Configuration

All secrets live in `backend/.env` (gitignored). Required keys are documented
in `backend/.env.example`. **Never commit `.env`** — if credentials leak into
git history, rotate them immediately.

## Project status

- [x] Phase 0 — foundation, hygiene, lint/test gates
- [ ] V1 — core repository intelligence (Steps 1–6)
- [ ] V1.5 — semantic code search and RAG (Steps 7–9)
- [ ] V2 — code intelligence and risk model (Steps 10–12)
- [ ] V2.5 — pull request intelligence (Steps 13–15)
- [ ] V3 — incremental indexing and production hardening (Steps 16–19)
