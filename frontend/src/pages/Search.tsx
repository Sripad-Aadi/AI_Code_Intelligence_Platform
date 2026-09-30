import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { searchRepo } from '../api/client'
import type { SearchHit } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'
import BackButton from '../components/BackButton'

const LANGUAGE_OPTIONS = [
  'Python', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'Java',
  'C', 'C++', 'C#', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala',
  'HTML', 'CSS', 'Markdown', 'JSON', 'YAML', 'TOML', 'SQL',
  'Shell', 'Dockerfile', 'Other',
]

function HighlightMatch({ content, query }: { content: string; query: string }) {
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
          <mark key={i} className="rounded bg-amber-200 px-0.5">{part}</mark>
        ) : (
          part
        )
      )}
    </code>
  )
}

function HitCard({ hit, query }: { hit: SearchHit; query: string }) {
  const riskColor = hit.symbol_kind
    ? hit.symbol_kind === 'class' ? 'badge-stone'
      : hit.symbol_kind === 'method' ? 'badge-teal'
      : hit.symbol_kind === 'route' ? 'badge-amber'
      : 'badge-emerald'
    : 'badge-stone'

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="truncate font-mono text-sm font-semibold text-teal-700">
          {hit.file_path}
        </span>
        <div className="flex shrink-0 flex-wrap gap-1">
          {hit.language && (
            <span className="badge badge-stone text-xs">{hit.language}</span>
          )}
          {hit.symbol_kind && (
            <span className={`badge ${riskColor} text-xs`}>
              {hit.symbol_kind} {hit.symbol_name ?? ''}
            </span>
          )}
        </div>
      </div>

      <div className="mb-2 font-mono text-xs text-stone-500">
        lines {hit.start_line}–{hit.end_line}
      </div>

      <div className="max-h-40 overflow-auto rounded-lg bg-stone-50 p-3 font-mono text-xs text-stone-700 border border-stone-100">
        <HighlightMatch content={hit.content} query={query} />
      </div>
    </div>
  )
}

export default function Search() {
  const [searchParams] = useSearchParams()
  const repoId = searchParams.get('repo')
  const [query, setQuery] = useState('')
  const [language, setLanguage] = useState('')
  const [k, setK] = useState(10)
  const [submittedQuery, setSubmittedQuery] = useState('')

  usePageTitle('Code Search')

  const searchQuery = useQuery({
    queryKey: ['search-repo', repoId, submittedQuery, language],
    queryFn: () => searchRepo(repoId!, submittedQuery, { k, language: language || undefined }),
    enabled: Boolean(repoId && submittedQuery),
  })

  const results = searchQuery.data?.hits ?? []
  const isLoading = searchQuery.isLoading
  const isError = searchQuery.isError
  const activeError = searchQuery.error
  const hasSearched = Boolean(submittedQuery)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSubmittedQuery(query)
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <BackButton />
        <h1 className="text-2xl font-bold tracking-tight text-stone-900">Code Search</h1>
        <p className="mt-1 text-sm text-stone-500">
          Semantic search within this repository.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card-flat p-6 space-y-4">
        <div className="flex flex-wrap gap-4">
          <div className="min-w-[250px] flex-1">
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
            <div>
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
          </div>

          <div className="flex items-end gap-2">
            <div>
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
        <div className="empty-state">
          <svg className="h-12 w-12 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <h3 className="mt-3 text-sm font-semibold text-stone-900">No results found</h3>
          <p className="mt-1 text-sm text-stone-500">
            No matches for "<span className="font-mono text-stone-700">{submittedQuery}</span>"
          </p>
        </div>
      )}

      {isError && (
        <div className="card border-rose-200 bg-rose-50 p-4 text-rose-700">
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
