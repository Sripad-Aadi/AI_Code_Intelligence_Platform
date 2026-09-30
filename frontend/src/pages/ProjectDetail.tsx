import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  attachRepository,
  getGithubStatus,
  getProject,
  listGitHubRepos,
} from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'
import BackButton from '../components/BackButton'

export default function ProjectDetail() {
  const { projectId } = useParams()
  const queryClient = useQueryClient()
  const [selectedRepo, setSelectedRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [repoFilter, setRepoFilter] = useState('')
  const [attachError, setAttachError] = useState<string | null>(null)

  const project = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId as string),
    enabled: Boolean(projectId),
  })

  usePageTitle(project.data?.name ?? 'Project')

  const ghStatus = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
  })

  const ghRepos = useQuery({
    queryKey: ['github-repos'],
    queryFn: listGitHubRepos,
    enabled: Boolean(projectId) && ghStatus.data?.linked === true,
  })

  const attachMutation = useMutation({
    mutationFn: () => attachRepository(projectId as string, selectedRepo, branch || undefined),
    onSuccess: () => {
      setSelectedRepo('')
      setBranch('')
      setAttachError(null)
      queryClient.invalidateQueries({ queryKey: ['project'] })
      queryClient.invalidateQueries({ queryKey: ['attached-repos'] })
    },
    onError: (err: Error) => setAttachError(err.message),
  })

  const repos = project.data?.repositories ?? []

  const filteredRepos = useMemo(() => {
    const q = repoFilter.trim().toLowerCase()
    const rows = ghRepos.data ?? []
    return q ? rows.filter((r) => r.full_name.toLowerCase().includes(q)) : rows
  }, [ghRepos.data, repoFilter])

  const onPickRepo = (fullName: string) => {
    setSelectedRepo(fullName)
    const repo = ghRepos.data?.find((r) => r.full_name === fullName)
    setBranch(repo?.default_branch ?? '')
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <BackButton />
        <div>
          <p className="text-sm text-stone-400">
            <Link to="/" className="hover:text-stone-600">Projects</Link>
            {' / '}
            <span className="text-stone-600">{project.data?.name ?? '…'}</span>
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-stone-900">
            {project.data?.name ?? 'Loading project…'}
          </h1>
          {project.data?.description ? (
            <p className="mt-1 text-sm text-stone-500">{project.data.description}</p>
          ) : null}
        </div>
      </div>

      {ghStatus.data && !ghStatus.data.linked && (
        <div className="card flex items-center gap-3 border-rose-200 bg-rose-50 p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-100">
            <svg className="h-4 w-4 text-rose-600" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-12-12-12-12z"/>
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-rose-800">GitHub account required</p>
            <p className="mt-0.5 text-xs text-rose-700">
              Link your GitHub account to attach repositories and run analysis.
            </p>
          </div>
          <Link to="/profile" className="btn btn-primary btn-sm shrink-0">
            Link GitHub
          </Link>
        </div>
      )}

      {ghRepos.isError && (
        <div className="card flex items-center gap-3 border-amber-200 bg-amber-50 p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100">
            <svg className="h-4 w-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800">GitHub token expired</p>
            <p className="mt-0.5 text-xs text-amber-700">
              {ghRepos.error?.message ?? 'Re-link your GitHub account to continue.'}
            </p>
          </div>
          <Link to="/profile" className="btn btn-primary btn-sm shrink-0">
            Re-link GitHub
          </Link>
        </div>
      )}

      <div className="card-flat p-6">
        <h2 className="label">Attach a GitHub repository</h2>
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-64 flex-1">
            <label className="label" htmlFor="gh-repo">Repository</label>
            <select
              id="gh-repo"
              className="input"
              value={selectedRepo}
              onChange={(e) => onPickRepo(e.target.value)}
            >
              <option value="">
                {ghRepos.isLoading
                  ? 'Loading GitHub repos…'
                  : ghRepos.isError
                    ? 'Could not load GitHub repos'
                    : 'Select a repository'}
              </option>
              {ghRepos.isError && ghRepos.error && (
                <p className="mt-2 text-xs text-rose-600">
                  {ghRepos.error.message}
                </p>
              )}
              {filteredRepos.map((r) => (
                <option key={r.id} value={r.full_name}>
                  {r.full_name}
                  {r.private ? ' (private)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="repo-filter">Filter</label>
            <input
              id="repo-filter"
              className="input"
              placeholder="Search repos…"
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="branch">Branch</label>
            <input
              id="branch"
              className="input"
              placeholder="default"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!selectedRepo || attachMutation.isPending}
            onClick={() => attachMutation.mutate()}
          >
            {attachMutation.isPending ? 'Attaching…' : 'Attach & clone'}
          </button>
        </div>
        {attachError ? (
          <p className="mt-3 text-sm text-rose-600">{attachError}</p>
        ) : null}
        <p className="mt-3 text-xs text-stone-400">
          Attaching shallow-clones the repo on the server and lets you trigger structural analysis.
        </p>
      </div>

      {project.isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="card p-4">
              <div className="skeleton h-5 w-48" />
              <div className="skeleton mt-2 h-4 w-full" />
            </div>
          ))}
        </div>
      ) : project.isError ? (
        <div className="empty-state">
          <p className="text-sm text-stone-600">
            Failed to load project: {(project.error as Error).message}
          </p>
        </div>
      ) : repos.length === 0 ? (
        <div className="empty-state">
          <svg className="h-12 w-12 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <h3 className="mt-3 text-sm font-semibold text-stone-900">No repositories attached yet</h3>
          <p className="mt-1 text-sm text-stone-500">
            Attach a GitHub repository above to get started.
          </p>
        </div>
      ) : (
        <>
          <h2 className="section-heading">
            Attached repositories ({repos.length})
          </h2>
          <div className="space-y-2">
            {repos.map((repo) => (
              <Link
                key={repo.id}
                to={`/repos/${repo.id}`}
                className="card-flat flex items-center justify-between p-4 hover:border-teal-300"
              >
                <div>
                  <p className="font-mono text-sm font-semibold text-stone-900">
                    {repo.github_full_name ?? repo.id}
                  </p>
                  <p className="mt-1 text-xs text-stone-500">
                    {repo.default_branch ?? 'default branch'}
                    {repo.last_indexed_at
                      ? ` • Last indexed ${new Date(repo.last_indexed_at).toLocaleString()}`
                      : ' • Not indexed yet'}
                  </p>
                </div>
                <svg className="h-4 w-4 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
