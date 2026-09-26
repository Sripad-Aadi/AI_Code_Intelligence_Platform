# AI Software Intelligence — frontend (Step 6)

React (Vite) + TypeScript + Tailwind CSS + TanStack Query + React Router.

## Scripts

```sh
npm install        # install dependencies
npm run dev        # Vite dev server on http://localhost:5173
npm run build      # tsc -b && vite build (the acceptance gate)
npm run lint       # ESLint
npm run preview    # serve the production build
```

## Environment

Copy `.env.example` to `.env` and fill in:

| Variable               | Purpose                                                        |
| ---------------------- | -------------------------------------------------------------- |
| `VITE_API_BASE`        | Backend origin (default `http://localhost:8000`)               |
| `VITE_SUPABASE_URL`    | Supabase project URL — enables email/password sign-in          |
| `VITE_SUPABASE_ANON_KEY` | Supabase publishable key — enables email/password sign-in    |

Everything is embedded in the browser bundle, so only public values belong
here. If the Supabase vars are empty, the login page falls back to pasting a
Supabase access token JWT (full flow works this way too — the backend only
ever sees the JWT).

## Pages

- `/` — **Dashboard**: project list, create/delete projects, link GitHub
  (`GET /auth/github/status` + OAuth popup).
- `/linked` — **OAuth completion**: the GitHub callback 302s the popup here
  (`?login=` or `?error=`); the page auto-closes. Because the callback never
  leaves the browser on a code-bearing URL, refreshing/retrying can't replay
  an already-consumed GitHub `code` (`bad_verification_code`).
- `/projects/:projectId` — **Project detail**: attach GitHub repos
  (shallow clone), trigger analysis (`POST /repos/{id}/ingest`).
- `/jobs/:jobId` — **Analysis status**: polls `GET /jobs/{id}` every 2 s via
  `src/hooks/useJobStatus.ts` while the Celery job is `queued`/`running`.
- `/repos/:repoId` — **Repo explorer**: file tree + symbol table + import/
  belongs_to edges from the Step-5 structural analysis endpoints.

## Auth notes

The backend authenticates Supabase JWTs (`Authorization: Bearer <jwt>`).
This app stores the JWT in `localStorage` (`ai_sip_access_token`), which is
the same approach the existing test harness uses. A 401/403 clears it and
redirects to `/login`. You can sign in in one step via
`http://localhost:5173/login?token=<jwt>`.

Each page sets its own browser-tab title (`src/hooks/usePageTitle.ts` or the
static `<title>` in `index.html`), so the tab never duplicates the
"AI Software Intelligence" brand that already sits in the navbar / login
card.