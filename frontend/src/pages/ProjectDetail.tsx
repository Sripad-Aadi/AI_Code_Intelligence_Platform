import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  attachRepository,
  detachRepository,
  getProject,
  listGitHubRepos,
  listRepoJobs,
  registerWebhook,
  startIngestion,
} from '../api/client'
import type { ProjectRepository } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'
import { isJobRunning, statusStyle } from '../hooks/useJobStatus'

function RepoRow({ repo }: { repo: ProjectRepository }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const latestJob = useQuery({
    queryKey: ['repo-jobs', repo.id, 1],
    queryFn: () => listRepoJobs(repo.id, 1),
  })

  const ingestMutation = useMutation({
    mutationFn: () => startIngestion(repo.id),
    onSuccess: (job) => {
      navigate(`/jobs/${job.id}?repo=${repo.id}`, { replace: true })
    },
  })

  const detachMutation = useMutation({
    mutationFn: () => detachRepository(repo.project_id, repo.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project'] })
      queryClient.invalidateQueries({ queryKey: ['attached-repos'] })
    },
  })

  const registerWebhookMutation = useMutation({
    mutationFn: () => registerWebhook(repo.id),
    onSuccess: () => {
      // Webhook registered successfully
    },
    onError: (err: Error) => {
      window.alert(`Failed to register webhook: ${err.message}`)
    },
  })

  const job = latestJob.data?.[0]
  const running = isJobRunning(job?.status)

  return (
    <li className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm font-semibold text-slate-900">
            {repo.github_full_name ?? repo.id}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {repo.github_owner && repo.github_name
              ? `${repo.github_name} • ${repo.default_branch ?? 'default branch'}`
              : 'No GitHub metadata'}
            {repo.last_indexed_at
              ? ` • Last indexed ${new Date(repo.last_indexed_at).toLocaleString()}`
              : ' • Not indexed yet'}
          </p>
        </div>
        {job ? (
          <span className={`badge ${statusStyle(job.status)}`}>
            {running ? (
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
            ) : null}
            {job.status}
            {job.status === 'completed'
              ? ` (${job.files_indexed} files)`
              : ''}
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={ingestMutation.isPending}
          onClick={() => ingestMutation.mutate()}
        >
          {ingestMutation.isPending ? 'Analyzing…' : 'Analyze'}
        </button>
        <Link to={`/repos/${repo.id}`} className="btn btn-outline">
          Explore code
        </Link>
        <button
          type="button"
          className="btn btn-outline"
          disabled={registerWebhookMutation.isPending}
          onClick={() => registerWebhookMutation.mutate()}
        >
          {registerWebhookMutation.isPending ? 'Registering…' : 'Register Webhook'}
        </button>
        <button
          type="button"
          className="btn btn-ghost text-rose-600"
          onClick={() => {
            if (
              window.confirm(`Detach ${repo.github_full_name ?? repo.id}?`)
            ) {
              detachMutation.mutate()
            }
          }}
        >
          Detach
        </button>
      </div>
      {ingestMutation.isError ? (
        <p className="mt-2 text-sm text-rose-600">
          {(ingestMutation.error as Error).message}
        </p>
      ) : null}
    </li>
  )
}

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

  const ghRepos = useQuery({
    queryKey: ['github-repos'],
    queryFn: listGitHubRepos,
    enabled: Boolean(projectId),
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
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">
            <Link to="/" className="hover:text-slate-600">
              Projects
            </Link>{' '}
            / {project.data?.name ?? '…'}
          </p>
          <h1 className="mt-1 text-xl font-bold text-slate-900">
            {project.data?.name ?? 'Loading project…'}
          </h1>
          {project.data?.description ? (
            <p className="text-sm text-slate-500">{project.data.description}</p>
          ) : null}
        </div>
      </div>

      <div className="card p-4">
        <h2 className="label">Attach a GitHub repository</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <label className="label" htmlFor="gh-repo">
              Repository (owner/name)
            </label>
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
              {filteredRepos.map((r) => (
                <option key={r.id} value={r.full_name}>
                  {r.full_name}
                  {r.private ? ' (private)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="repo-filter">
              Filter
            </label>
            <input
              id="repo-filter"
              className="input"
              placeholder="Search repos…"
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="branch">
              Branch
            </label>
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
          <p className="mt-2 text-sm text-rose-600">{attachError}</p>
        ) : null}
        <p className="mt-2 text-xs text-slate-400">
          Attaching shallow-clones the repo on the server and lets you trigger
          structural analysis. You must{' '}
          <span className="font-medium text-slate-500">link GitHub</span> first.
        </p>
      </div>

      {project.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : project.isError ? (
        <p className="text-sm text-rose-600">
          Failed to load project: {(project.error as Error).message}
        </p>
      ) : repos.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-500">
          No repositories attached yet.
        </div>
      ) : (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Attached repositories ({repos.length})
          </h2>
          <ul className="space-y-3">
            {repos.map((repo) => (
              <RepoRow key={repo.id} repo={repo} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}