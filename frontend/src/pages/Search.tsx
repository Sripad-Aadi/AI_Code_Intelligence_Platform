import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { searchRepo, searchAcrossRepos } from '../api/client'
import type { SearchHit } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'

const LANGUAGE_OPTIONS = [
  'Python', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'Java',
  'C', 'C++', 'C#', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala',
  'HTML', 'CSS', 'Markdown', 'JSON', 'YAML', 'TOML', 'SQL',
  'Shell', 'Dockerfile', 'Other',
]

function HighlightMatch({ content, query }: { content: string; query: string }) {
  // The page's own placeholder is a natural-language question, so highlight
  // each word of the query rather than the whole phrase (which would almost
  // never match verbatim).
  const words = query.split(/\s+/).filter((w) => w.length >= 2)
  if (words.length === 0) return <code className="text-sm">{content}</code>

  const pattern = words
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  const matched = new Set(words.map((w) => w.toLowerCase()))
  const parts = content.split(new RegExp(`(${pattern})`, 'gi'))

  return (
    <code className="text-sm">
      {parts.map((part, i) =>
        matched.has(part.toLowerCase()) ? (
          <mark key={i} className="bg-amber-200 px-0.5 rounded">{part}</mark>
        ) : (
          part
        )
      )}
    </code>
  )
}

function HitCard({ hit, query }: { hit: SearchHit; query: string }) {
  const riskColor = hit.symbol_kind
    ? hit.symbol_kind === 'class' ? 'bg-violet-100 text-violet-700'
      : hit.symbol_kind === 'method' ? 'bg-sky-100 text-sky-700'
      : hit.symbol_kind === 'route' ? 'bg-amber-100 text-amber-700'
      : 'bg-emerald-100 text-emerald-700'
    : 'bg-slate-100 text-slate-600'

  return (
    <div className="card p-4 hover:border-indigo-300 transition-colors">
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="font-mono text-sm text-indigo-700 font-semibold truncate max-w-[80%]">
          {hit.file_path}
        </span>
        <div className="flex flex-wrap gap-1 shrink-0">
          {hit.language && (
            <span className="badge bg-slate-100 text-slate-600 text-xs">{hit.language}</span>
          )}
          {hit.symbol_kind && (
            <span className={`badge ${riskColor} text-xs`}>
              {hit.symbol_kind} {hit.symbol_name ?? ''}
            </span>
          )}
        </div>
      </div>

      <div className="text-xs text-slate-500 mb-2 font-mono">
        lines {hit.start_line}–{hit.end_line}
      </div>

      <div className="bg-slate-50 rounded p-2 max-h-40 overflow-auto font-mono text-xs text-slate-700 border border-slate-100">
        <HighlightMatch content={hit.content} query={query} />
      </div>
    </div>
  )
}

export default function Search() {
  // The route is `/search` with no `:repoId` segment, so a repo scope arrives
  // as `?repo=<id>` (RepoExplorer links here with one). With no repo there is
  // nothing to scope "This repo" to, so the page searches everything instead
  // of silently running nothing.
  const [searchParams] = useSearchParams()
  const repoId = searchParams.get('repo')
  const [query, setQuery] = useState('')
  const [language, setLanguage] = useState('')
  const [k, setK] = useState(10)
  const [searchMode, setSearchMode] = useState<'repo' | 'all'>(repoId ? 'repo' : 'all')
  // The query that is actually being searched. Keying the queries off this
  // instead of `query` keeps two things true: nothing is sent until the form
  // is submitted (otherwise every keystroke re-embeds and re-queries), and
  // whatever is on screen belongs to the text the user submitted, even if
  // they have edited the box since.
  const [submittedQuery, setSubmittedQuery] = useState('')

  usePageTitle('Code Search')

  const repoQuery = useQuery({
    queryKey: ['search-repo', repoId, submittedQuery, language, k],
    queryFn: () => searchRepo(repoId!, submittedQuery, { k, language: language || undefined }),
    enabled: Boolean(repoId && submittedQuery && searchMode === 'repo'),
  })

  const allQuery = useQuery({
    queryKey: ['search-all', submittedQuery, language, k],
    queryFn: () => searchAcrossRepos(submittedQuery, { k, language: language || undefined }),
    enabled: Boolean(submittedQuery && searchMode === 'all'),
  })

  const results = searchMode === 'repo' ? repoQuery.data?.hits ?? [] : allQuery.data?.hits ?? []
  const isLoading = searchMode === 'repo' ? repoQuery.isLoading : allQuery.isLoading
  const isError = searchMode === 'repo' ? repoQuery.isError : allQuery.isError
  const activeError = searchMode === 'repo' ? repoQuery.error : allQuery.error
  const hasSearched = Boolean(submittedQuery)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSubmittedQuery(query)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Code Search</h1>
        <p className="mt-1 text-sm text-slate-500">
          Semantic search over indexed code chunks. Uses pgvector cosine similarity.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card p-4 space-y-4">
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[250px]">
            <label className="label">Search query</label>
            <input
              type="text"
              className="input"
              placeholder="e.g. how does authentication work"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
          </div>

          <div className="flex items-end gap-2">
            <label className="label">Mode</label>
            <select
              className="input w-auto"
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value as 'repo' | 'all')}
            >
              <option value="all">All repos</option>
              <option value="repo" disabled={!repoId}>
                This repo{repoId ? '' : ' (no repo selected)'}
              </option>
            </select>
          </div>

          <div className="flex items-end gap-2">
            <label className="label">Language</label>
            <select
              className="input w-auto"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">All</option>
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>

          <div className="flex items-end gap-2">
            <label className="label">Results (k)</label>
            <input
              type="number"
              min="1"
              max="50"
              className="input w-24"
              value={k}
              onChange={(e) => setK(Math.max(1, Math.min(50, parseInt(e.target.value) || 10)))}
            />
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={!query.trim() || isLoading}
        >
          {isLoading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {hasSearched && !isLoading && !isError && results.length === 0 && (
        <div className="card p-8 text-center text-slate-400">
          No results found for "
          <span className="font-mono text-slate-600">{submittedQuery}</span>"
        </div>
      )}

      {isError && (
        <div className="card p-4 text-rose-600">
          Search failed: {(activeError as Error)?.message ?? 'unknown error'}
        </div>
      )}

      {hasSearched && !isLoading && results.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {results.map((hit) => (
            <HitCard key={hit.id} hit={hit} query={submittedQuery} />
          ))}
        </div>
      )}
    </div>
  )
}