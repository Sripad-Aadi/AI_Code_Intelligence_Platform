/** Shared response shapes mirrored from the backend Pydantic schemas. */

export interface Project {
  id: string
  name: string
  description: string | null
  owner_id: string
  created_at: string
  updated_at: string
}

export interface ProjectRepository {
  id: string
  project_id: string
  github_repo_id: string | null
  github_owner: string | null
  github_name: string | null
  github_full_name: string | null
  default_branch: string | null
  last_indexed_at: string | null
  created_at: string
  updated_at: string
}

export interface ProjectWithRepos extends Project {
  repositories: ProjectRepository[]
}

export interface GitHubRepo {
  id: string
  full_name: string
  owner: string
  name: string
  default_branch: string | null
  private: boolean
  html_url: string | null
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface AnalysisJob {
  id: string
  repo_id: string
  status: JobStatus
  started_at: string | null
  finished_at: string | null
  error: string | null
  files_scanned: number
  files_indexed: number
  symbols_indexed: number
  languages: Record<string, number> | null
  created_at: string
}

export interface SourceFile {
  id: string
  repo_id: string
  path: string
  language: string
  line_count: number
  parse_error: string | null
  created_at: string
}

export type SymbolKind = 'function' | 'class' | 'method' | 'route'

export interface Symbol {
  id: string
  file_id: string
  kind: SymbolKind
  name: string
  start_line: number
  end_line: number
  file_path?: string | null
}

export interface FileWithSymbols extends SourceFile {
  symbols: Symbol[]
}

export interface ImportEdge {
  source_path: string
  target_path: string
  edge_type: 'imports' | 'belongs_to'
}

export interface GithubStatus {
  linked: boolean
  github_id: number | null
  github_login: string | null
}

export interface AttachedRepoRow {
  id: string
  project_id: string
  github_full_name: string | null
  default_branch: string | null
  last_indexed_at: string | null
}