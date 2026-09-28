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
  chunks_indexed: number
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

// --- Search (Step 8) ---

export interface SearchHit {
  id: string
  repo_id: string
  file_id: string | null
  file_path: string
  language: string | null
  symbol_kind: string | null
  symbol_name: string | null
  start_line: number
  end_line: number
  content: string
}

export interface SearchResponse {
  query: string
  repo_id: string
  hits: SearchHit[]
}

// --- Chat (Step 9) ---

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  repo_id: string
  query: string
  chat_history: ChatMessage[]
}

export interface EvidenceChunk {
  file_path: string
  symbol_name: string | null
  symbol_kind: string | null
  start_line: number
  end_line: number
  content: string
}

export interface ChatResponse {
  answer: string
  evidence: EvidenceChunk[]
}

// --- Findings (Step 12) ---

export type RiskLevel = 'low' | 'medium' | 'high'

export interface RiskFinding {
  id: string
  repo_id: string
  symbol_id: string
  risk_level: RiskLevel
  probability: number
  features_json: Record<string, unknown>
  model_version: string
  created_at: string
  updated_at: string
}

export interface RiskFindingListResponse {
  repo_id: string
  findings: RiskFinding[]
  total: number
  limit: number
  offset: number
}

export interface FindingsSummary {
  repo_id: string
  by_level: Record<RiskLevel, number>
  total: number
}

// --- PR Analysis (Step 14-15) ---

export interface ChangedSymbolOut {
  symbol_id: string
  file_path: string
  symbol_name: string
  symbol_kind: string
  start_line: number
  end_line: number
  changed_lines: number[]
  risk_level?: RiskLevel
  risk_probability?: number
}

export interface AffectedFileOut {
  file_path: string
  reason: string
  via_symbol: string
}

export interface PRAnalysisResult {
  repo_id: string
  pr_number: number
  pr_title: string
  files_changed: number
  symbols_changed: number
  affected_files_count: number
  test_files_count: number
  changed_symbols: ChangedSymbolOut[]
  affected_files: AffectedFileOut[]
  test_files: string[]
  high_risk_symbols: number
  medium_risk_symbols: number
  low_risk_symbols: number
}

// --- Observability (Step 19) ---

export interface JobStatsResponse {
  total_jobs: number
  queued: number
  running: number
  completed: number
  failed: number
  avg_duration_sec: number | null
  total_files_indexed: number
  total_symbols_indexed: number
  total_chunks_embedded: number
}

export interface BenchmarkStatusResponse {
  retrieval_benchmark_exists: boolean
  risk_eval_exists: boolean
  last_run: string | null
}

// --- Webhooks (Step 13) ---

export interface Webhook {
  id: number
  url: string
  events: string[]
  active: boolean
  created_at: string
  updated_at: string
}

export interface WebhookRegisterResponse {
  status: string
  webhook_id: number
}

export interface WebhookListResponse {
  webhooks: Webhook[]
}

export interface WebhookDeleteResponse {
  status: string
  hook_id: number
}

// --- Cost Tracking (Step 19) ---

export interface CostSummaryResponse {
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
  by_model?: Record<string, {
    calls: number
    input_tokens: number
    output_tokens: number
    cost_usd: number
  }>
}