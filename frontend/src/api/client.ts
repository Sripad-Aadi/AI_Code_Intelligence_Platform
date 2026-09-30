/** Thin typed client for the FastAPI backend (no REST lib, plain fetch). */

import type {
  AnalysisJob,
  AttachedRepoRow,
  ChatResponse,
  ChatRequest,
  CostSummaryResponse,
  FileWithSymbols,
  GitHubRepo,
  GithubStatus,
  ImportEdge,
  JobStatsResponse,
  PRAnalysisResult,
  Project,
  ProjectRepository,
  ProjectWithRepos,
  PullRequestSummary,
  SearchResponse,
  SourceFile,
  Symbol,
} from './types'

const TOKEN_KEY = 'ai_sip_access_token'

export function getApiBase(): string {
  const base = import.meta.env.VITE_API_BASE as string | undefined
  return (base ?? 'http://localhost:8000').replace(/\/+$/, '')
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const resp = await fetch(`${getApiBase()}${path}`, { ...init, headers })

  if (resp.status === 401) {
    clearToken()
    window.dispatchEvent(new Event('ai-sip:unauthorized'))
  }

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const body: unknown = await resp.json()
      if (typeof body === 'object' && body !== null && 'detail' in body) {
        const d = (body as { detail: unknown }).detail
        if (typeof d === 'string') detail = d
      }
    } catch {
      // non-JSON body — keep the fallback message
    }
    throw new ApiError(resp.status, detail)
  }

  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

const jsonBody = (data: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

// --- GitHub auth (Step 3) ---

export const getGithubStatus = () => apiFetch<GithubStatus>('/auth/github/status')

export const unlinkGithub = () =>
  apiFetch<{ status: string }>('/auth/github', { method: 'DELETE' })

// --- Projects (Step 2) ---

export const listProjects = () => apiFetch<Project[]>('/projects')

export const createProject = (name: string, description?: string) =>
  apiFetch<Project>('/projects', jsonBody({ name, description: description ?? null }))

export const getProject = (projectId: string) =>
  apiFetch<ProjectWithRepos>(`/projects/${projectId}`)

export const deleteProject = (projectId: string) =>
  apiFetch<void>(`/projects/${projectId}`, { method: 'DELETE' })

// --- Repositories (Steps 2-3) ---

export const listAttachedRepos = () => apiFetch<AttachedRepoRow[]>('/repos')

export const listGitHubRepos = () => apiFetch<GitHubRepo[]>('/user/repos')

export const attachRepository = (
  projectId: string,
  githubFullName: string,
  branch?: string,
) =>
  apiFetch<ProjectRepository>(
    `/projects/${projectId}/repositories`,
    jsonBody({ github_full_name: githubFullName, branch: branch ?? null }),
  )

export const detachRepository = (projectId: string, repoId: string) =>
  apiFetch<void>(`/projects/${projectId}/repositories/${repoId}`, {
    method: 'DELETE',
  })

// --- Ingestion jobs (Step 4) ---

export const startIngestion = (repoId: string) =>
  apiFetch<AnalysisJob>(`/repos/${repoId}/ingest`, { method: 'POST' })

export const getJob = (jobId: string) => apiFetch<AnalysisJob>(`/jobs/${jobId}`)

export const listRepoJobs = (repoId: string, limit = 20) =>
  apiFetch<AnalysisJob[]>(`/repos/${repoId}/jobs?limit=${limit}`)

// --- Structural analysis (Step 5) ---

export const listRepoFiles = (
  repoId: string,
  opts: { path?: string; limit?: number; offset?: number } = {},
) => {
  const params = new URLSearchParams()
  if (opts.path) params.set('path', opts.path)
  params.set('limit', String(opts.limit ?? 200))
  params.set('offset', String(opts.offset ?? 0))
  return apiFetch<SourceFile[]>(`/repos/${repoId}/files?${params.toString()}`)
}

export const getFileWithSymbols = (fileId: string) =>
  apiFetch<FileWithSymbols>(`/files/${fileId}`)

export const listRepoSymbols = (
  repoId: string,
  opts: { kind?: string; name?: string; limit?: number; offset?: number } = {},
) => {
  const params = new URLSearchParams()
  if (opts.kind) params.set('kind', opts.kind)
  if (opts.name) params.set('name', opts.name)
  params.set('limit', String(opts.limit ?? 500))
  params.set('offset', String(opts.offset ?? 0))
  return apiFetch<Symbol[]>(`/repos/${repoId}/symbols?${params.toString()}`)
}

export const listRepoEdges = (
  repoId: string,
  edgeType: 'imports' | 'belongs_to' = 'imports',
  limit = 500,
) => apiFetch<ImportEdge[]>(`/repos/${repoId}/edges?edge_type=${edgeType}&limit=${limit}`)

// --- Semantic search (Step 8) ---

export const searchRepo = (
  repoId: string,
  query: string,
  opts: { k?: number; language?: string; file_path?: string } = {},
) => {
  const params = new URLSearchParams()
  params.set('q', query)
  if (opts.k) params.set('k', String(opts.k))
  if (opts.language) params.set('language', opts.language)
  if (opts.file_path) params.set('file_path', opts.file_path)
  return apiFetch<SearchResponse>(`/repos/${repoId}/search?${params.toString()}`)
}

// --- Chat (Step 9) ---

export const chat = (request: ChatRequest) =>
  apiFetch<ChatResponse>('/chat', jsonBody(request))

// --- PR Analysis (Step 14-15) ---

export const getPRAnalysis = (repoId: string, prNumber: number) =>
  apiFetch<PRAnalysisResult>(`/repos/${repoId}/prs/${prNumber}/analysis`)

export const listPullRequests = (repoId: string, state = 'open') =>
  apiFetch<PullRequestSummary[]>(`/repos/${repoId}/pulls?state=${state}`)

// --- Observability (Step 19) ---

export const getJobStats = (repoId?: string) => {
  const params = new URLSearchParams()
  if (repoId) params.set('repo_id', repoId)
  return apiFetch<JobStatsResponse>(`/observability/jobs/stats?${params.toString()}`)
}

// --- Cost Tracking (Step 19) ---

export const getCostSummary = (repoId?: string) => {
  const params = new URLSearchParams()
  if (repoId) params.set('repo_id', repoId)
  return apiFetch<CostSummaryResponse>(`/observability/costs/summary?${params.toString()}`)
}