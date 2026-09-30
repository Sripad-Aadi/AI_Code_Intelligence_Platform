import { useMutation, useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  detachRepository,
  getFileWithSymbols,
  listAttachedRepos,
  listPullRequests,
  listRepoEdges,
  listRepoFiles,
  listRepoJobs,
  listRepoSymbols,
  startIngestion,
} from '../api/client'
import type { SourceFile, SymbolKind, FileWithSymbols } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'
import { isJobRunning, statusStyle } from '../hooks/useJobStatus'
import BackButton from '../components/BackButton'

type Tab = 'files' | 'symbols' | 'imports' | 'pulls'

interface TreeNode {
  name: string
  path: string
  children: Map<string, TreeNode>
  file: SourceFile | null
}

function buildTree(files: SourceFile[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map(), file: null }
  for (const f of files) {
    const parts = f.path.split('/')
    let node = root
    let acc = ''
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i]
      let child = node.children.get(parts[i])
      if (!child) {
        child = { name: parts[i], path: acc, children: new Map(), file: null }
        node.children.set(parts[i], child)
      }
      node = child
    }
    const leafName = parts[parts.length - 1] ?? f.path
    node.children.set(leafName, {
      name: leafName,
      path: f.path,
      children: new Map(),
      file: f,
    })
  }
  return root
}

function sortedEntries(node: TreeNode): [string, TreeNode][] {
  return [...node.children.entries()].sort((a, b) => {
    const aDir = a[1].children.size > 0
    const bDir = b[1].children.size > 0
    if (aDir !== bDir) return aDir ? -1 : 1
    return a[0].localeCompare(b[0])
  })
}

function FileTree({
  node,
  depth,
  onPick,
}: {
  node: TreeNode
  depth: number
  onPick: (file: SourceFile) => void
}) {
  const entries = sortedEntries(node)
  return (
    <ul className={depth > 0 ? 'ml-3 border-l border-stone-200 pl-2' : ''}>
      {entries.map(([name, child]) =>
        child.file ? (
          <li key={child.path}>
            <button
              type="button"
              className="tree-item w-full text-left font-mono text-xs text-stone-700 hover:bg-teal-50 hover:text-teal-700"
              onClick={() => onPick(child.file as SourceFile)}
            >
              {name}
            </button>
          </li>
        ) : (
          <li key={child.path}>
            <p className="truncate px-3 py-0.5 font-mono text-xs font-semibold text-stone-500">
              {name}/
            </p>
            <FileTree node={child} depth={depth + 1} onPick={onPick} />
          </li>
        ),
      )}
    </ul>
  )
}

const KIND_FILTERS: { label: string; value: SymbolKind | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Function', value: 'function' },
  { label: 'Class', value: 'class' },
  { label: 'Method', value: 'method' },
  { label: 'Route', value: 'route' },
]

export default function RepoExplorer() {
  const { repoId } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('files')
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null)
  const [kindFilter, setKindFilter] = useState<SymbolKind | ''>('')
  const [edgeType, setEdgeType] = useState<'imports' | 'belongs_to'>('imports')

  const attached = useQuery({
    queryKey: ['attached-repos'],
    queryFn: listAttachedRepos,
  })
  const latestJob = useQuery({
    queryKey: ['repo-jobs', repoId, 1],
    queryFn: () => listRepoJobs(repoId as string, 1),
  })
  const files = useQuery({
    queryKey: ['repo-files', repoId],
    queryFn: () => listRepoFiles(repoId as string, { limit: 1000 }),
    enabled: tab === 'files',
  })
  const symbols = useQuery({
    queryKey: ['repo-symbols', repoId, kindFilter],
    queryFn: () =>
      listRepoSymbols(repoId as string, {
        kind: kindFilter || undefined,
        limit: 1000,
      }),
    enabled: tab === 'symbols',
  })
  const edges = useQuery({
    queryKey: ['repo-edges', repoId, edgeType],
    queryFn: () => listRepoEdges(repoId as string, edgeType, 500),
    enabled: tab === 'imports',
  })
  const fileDetail = useQuery({
    queryKey: ['file', selectedFileId],
    queryFn: () => getFileWithSymbols(selectedFileId as string),
    enabled: Boolean(selectedFileId),
  })
  const pulls = useQuery({
    queryKey: ['repo-pulls', repoId],
    queryFn: () => listPullRequests(repoId as string, 'open'),
    enabled: tab === 'pulls',
  })
  const [prNumber, setPrNumber] = useState('')

  const symbolRows = symbols.data ?? []
  const edgeRows = edges.data ?? []

  const ingest = useMutation({
    mutationFn: () => startIngestion(repoId as string),
    onSuccess: (job) => navigate(`/jobs/${job.id}?repo=${repoId}`),
  })

  const detach = useMutation({
    mutationFn: () => detachRepository(repoMeta?.project_id as string, repoId as string),
    onSuccess: () => navigate('/', { replace: true }),
  })

  const repoMeta = attached.data?.find((r) => r.id === repoId)

  usePageTitle(repoMeta?.github_full_name ?? 'Repository explorer')
  const tree = useMemo(
    () => (files.data ? buildTree(files.data) : null),
    [files.data],
  )
  const job = latestJob.data?.[0]
  const running = isJobRunning(job?.status)

  // Compute language histogram from files
  const langHistogram = useMemo(() => {
    if (!files.data) return null
    const hist: Record<string, number> = {}
    for (const f of files.data) {
      hist[f.language] = (hist[f.language] || 0) + 1
    }
    return hist
  }, [files.data])

  const tabBtn = (value: Tab, label: string) => (
    <button
      type="button"
      className={
        tab === value
          ? 'nav-link-active'
          : 'nav-link'
      }
      onClick={() => setTab(value)}
    >
      {label}
    </button>
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <BackButton />
          <div>
            <p className="text-sm text-stone-400">
              <Link to="/" className="hover:text-stone-600">Projects</Link>
              {' / '}
              {repoMeta ? (
                <Link to={`/projects/${repoMeta.project_id}`} className="hover:text-stone-600">Project</Link>
              ) : (
                'Repository'
              )}
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-stone-900">
              {repoMeta?.github_full_name ?? 'Repository explorer'}
            </h1>
            <p className="mt-1 text-xs text-stone-500">
              {repoMeta?.default_branch ? `Branch ${repoMeta.default_branch}` : ''}
              {job?.finished_at ? ` • Last analyzed ${new Date(job.finished_at).toLocaleString()}` : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {job ? (
            <span className={`badge ${statusStyle(job.status)}`}>
              {running ? (
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              ) : null}
              {job.status}
            </span>
          ) : null}
        </div>
      </div>

      {/* Features and Options */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          <Link to={`/search?repo=${repoId}`} className="btn btn-outline">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Search
          </Link>
          <Link to={`/repos/${repoId}/chat`} className="btn btn-outline">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            Ask AI
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={ingest.isPending}
            onClick={() => ingest.mutate()}
          >
            {ingest.isPending ? 'Analyzing…' : repoMeta?.last_indexed_at ? 'Re-analyze' : 'Analyze'}
          </button>
          {job ? (
            <Link to={`/jobs/${job.id}?repo=${repoId}`} className="btn btn-outline">
              Job status
            </Link>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost text-rose-600 hover:bg-rose-50"
            disabled={detach.isPending}
            onClick={() => {
              if (window.confirm(`Detach ${repoMeta?.github_full_name ?? 'this repo'}?`)) {
                detach.mutate()
              }
            }}
          >
            {detach.isPending ? 'Detaching…' : 'Detach'}
          </button>
        </div>
      </div>

      {/* Language histogram */}
      {langHistogram && tab === 'files' && (
        <div className="card p-4">
          <h3 className="label">Languages</h3>
          <div className="mt-3 space-y-2">
            {Object.entries(langHistogram)
              .sort((a, b) => b[1] - a[1])
              .map(([lang, count]) => {
                const total = Object.values(langHistogram).reduce((a, b) => a + b, 0)
                const max = Math.max(...Object.values(langHistogram))
                return (
                  <div key={lang} className="flex items-center gap-3">
                    <span className="w-20 text-xs font-medium text-stone-600">{lang}</span>
                    <div className="progress-bar flex-1">
                      <div className="progress-fill" style={{ width: `${(count / max) * 100}%` }} />
                    </div>
                    <span className="w-16 text-right text-xs text-stone-500">
                      {count} ({Math.round((count / total) * 100)}%)
                    </span>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      <nav className="flex gap-1 border-b border-stone-200 pb-px">
        {tabBtn('files', 'Browse code')}
        {tabBtn('symbols', `Symbols${symbols.data ? ` (${symbols.data.length})` : ''}`)}
        {tabBtn('imports', `Imports${edges.data ? ` (${edges.data.length})` : ''}`)}
        {tabBtn('pulls', `Pull requests${pulls.data ? ` (${pulls.data.length})` : ''}`)}
      </nav>

      {tab === 'files' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card max-h-[70vh] overflow-auto p-2">
            {files.isLoading ? (
              <div className="p-3 text-sm text-stone-400">Loading files…</div>
            ) : files.isError ? (
              <div className="p-3 text-sm text-rose-600">{(files.error as Error).message}</div>
            ) : !tree ? (
              <div className="p-3 text-sm text-stone-400">No indexed files.</div>
            ) : (
              <FileTree node={tree} depth={0} onPick={(f) => setSelectedFileId(f.id)} />
            )}
          </div>
          <FileDetail fileId={selectedFileId} query={fileDetail} />
        </div>
      ) : null}

      {tab === 'symbols' ? (
        <div className="card-flat overflow-hidden">
          <div className="flex flex-wrap gap-1 border-b border-stone-200 bg-stone-50 px-3 py-2">
            {KIND_FILTERS.map((k) => (
              <button
                key={k.label}
                type="button"
                className={
                  kindFilter === k.value
                    ? 'rounded-md bg-teal-600 px-2.5 py-1 text-xs font-medium text-white'
                    : 'rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs font-medium text-stone-600 hover:bg-stone-50'
                }
                onClick={() => setKindFilter(k.value)}
              >
                {k.label}
              </button>
            ))}
          </div>
          {symbols.isLoading ? (
            <div className="p-3 text-sm text-stone-400">Loading symbols…</div>
          ) : symbols.isError ? (
            <div className="p-3 text-sm text-rose-600">{(symbols.error as Error).message}</div>
          ) : symbolRows.length === 0 ? (
            <div className="p-3 text-sm text-stone-400">No matching symbols.</div>
          ) : (
            <div className="max-h-[70vh] overflow-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-50">
                    <th className="th">Kind</th>
                    <th className="th">Name</th>
                    <th className="th">File</th>
                    <th className="th">Lines</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolRows.map((s) => (
                    <tr
                      key={s.id}
                      className="cursor-pointer border-b border-stone-100 hover:bg-teal-50/50"
                      onClick={() => setSelectedFileId(s.file_id)}
                    >
                      <td className="td">
                        <span className={`badge ${kindStyle(s.kind)}`}>{s.kind}</span>
                      </td>
                      <td className="td font-mono text-xs font-semibold">{s.name}</td>
                      <td className="td max-w-56 truncate font-mono text-xs text-stone-500">{s.file_path}</td>
                      <td className="td text-xs text-stone-500">{s.start_line}–{s.end_line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {tab === 'imports' ? (
        <div className="card-flat overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 bg-stone-50 px-3 py-2">
            <button
              type="button"
              className={
                edgeType === 'imports'
                  ? 'rounded-md bg-teal-600 px-2.5 py-1 text-xs font-medium text-white'
                  : 'rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs font-medium text-stone-600 hover:bg-stone-50'
              }
              onClick={() => setEdgeType('imports')}
            >
              File → file imports
            </button>
            <button
              type="button"
              className={
                edgeType === 'belongs_to'
                  ? 'rounded-md bg-teal-600 px-2.5 py-1 text-xs font-medium text-white'
                  : 'rounded-md border border-stone-300 bg-white px-2.5 py-1 text-xs font-medium text-stone-600 hover:bg-stone-50'
              }
              onClick={() => setEdgeType('belongs_to')}
            >
              Symbol → file
            </button>
            <span className="ml-auto text-xs text-stone-400">{edgeRows.length} edges</span>
          </div>
          {edges.isLoading ? (
            <div className="p-3 text-sm text-stone-400">Loading edges…</div>
          ) : edges.isError ? (
            <div className="p-3 text-sm text-rose-600">{(edges.error as Error).message}</div>
          ) : edgeRows.length === 0 ? (
            <div className="p-3 text-sm text-stone-400">No edges.</div>
          ) : (
            <div className="max-h-[62vh] overflow-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-50">
                    <th className="th">Source</th>
                    <th className="th" />
                    <th className="th">Target</th>
                  </tr>
                </thead>
                <tbody>
                  {edgeRows.map((e, i) => (
                    <tr key={`${e.source_path}-${e.target_path}-${i}`} className="border-b border-stone-100">
                      <td className="td max-w-80 truncate font-mono text-xs">{e.source_path}</td>
                      <td className="td px-2 text-center text-stone-300">→</td>
                      <td className="td max-w-80 truncate font-mono text-xs">{e.target_path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {tab === 'pulls' ? (
        <div className="card-flat overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 bg-stone-50 px-3 py-2">
            <span className="text-xs text-stone-500">Analyze a pull request for impacted components, risk and tests.</span>
            <form
              className="ml-auto flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                const n = parseInt(prNumber, 10)
                if (Number.isFinite(n) && n > 0) {
                  navigate(`/repos/${repoId}/prs/${n}`)
                }
              }}
            >
              <input
                value={prNumber}
                onChange={(e) => setPrNumber(e.target.value)}
                placeholder="PR #"
                inputMode="numeric"
                className="w-20 rounded-md border border-stone-300 bg-white px-2 py-1 text-xs"
              />
              <button type="submit" className="btn btn-outline btn-sm">Analyze PR</button>
            </form>
          </div>
          {pulls.isLoading ? (
            <div className="p-3 text-sm text-stone-400">Loading pull requests…</div>
          ) : pulls.isError ? (
            <div className="p-3 text-sm text-rose-600">{(pulls.error as Error).message}</div>
          ) : !pulls.data || pulls.data.length === 0 ? (
            <div className="p-3 text-sm text-stone-400">No open pull requests. Enter a PR number above to analyze any PR.</div>
          ) : (
            <ul className="divide-y divide-stone-100">
              {pulls.data.map((pr) => (
                <li key={pr.number} className="flex items-center gap-3 px-4 py-2">
                  <span className="font-mono text-xs font-semibold text-teal-700">#{pr.number}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-stone-700">{pr.title}</span>
                  <span className="font-mono text-xs text-stone-400">{pr.head_ref} → {pr.base_ref}</span>
                  <Link to={`/repos/${repoId}/prs/${pr.number}`} className="btn btn-outline btn-sm">Analyze</Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}

function kindStyle(kind: string): string {
  switch (kind) {
    case 'class':
      return 'badge-stone'
    case 'method':
      return 'badge-teal'
    case 'route':
      return 'badge-amber'
    default:
      return 'badge-emerald'
  }
}

function FileDetail({
  fileId,
  query,
}: {
  fileId: string | null
  query: UseQueryResult<FileWithSymbols, Error>
}) {
  const file = query.data
  if (!fileId) {
    return (
      <div className="card flex items-center justify-center p-8 text-sm text-stone-400">
        Select a file to see its extracted symbols.
      </div>
    )
  }
  if (query.isLoading) {
    return (
      <div className="card flex items-center justify-center p-8 text-sm text-stone-400">Loading file…</div>
    )
  }
  if (query.isError || !file) {
    return (
      <div className="card p-8 text-sm text-rose-600">
        Failed to load file: {(query.error as Error).message}
      </div>
    )
  }
  return (
    <div className="card space-y-3 p-4">
      <div>
        <p className="break-all font-mono text-sm font-semibold text-stone-900">{file.path}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="badge badge-stone">{file.language}</span>
          <span className="badge badge-stone">{file.line_count} lines</span>
          {file.parse_error ? (
            <span className="badge badge-rose">parse error</span>
          ) : null}
        </div>
      </div>
      {file.parse_error ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">{file.parse_error}</p>
      ) : null}
      {file.symbols.length === 0 ? (
        <p className="text-sm text-stone-400">No functions, classes, or routes extracted from this file.</p>
      ) : (
        <ul className="divide-y divide-stone-100">
          {file.symbols.map((s) => (
            <li key={s.id} className="flex items-center gap-3 py-1.5">
              <span className={`badge ${kindStyle(s.kind)}`}>{s.kind}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-sm text-stone-800">{s.name}</span>
              <span className="shrink-0 text-xs text-stone-400">{s.start_line}–{s.end_line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
