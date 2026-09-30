import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { createProject, deleteProject, getGithubStatus, listProjects } from '../api/client'
import type { ProjectWithRepos } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'

export default function Dashboard() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  usePageTitle('Projects')

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })

  const ghStatus = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
  })

  const createMutation = useMutation({
    mutationFn: () => createProject(name, description),
    onSuccess: () => {
      setName('')
      setDescription('')
      setCreateError(null)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (err: Error) => setCreateError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (err: Error) => setCreateError(err.message),
  })

  const handleCreate = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createMutation.mutate()
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-stone-900">Projects</h1>
        <p className="mt-1 text-sm text-stone-500">
          Organize your repositories into projects and run AI-powered analysis.
        </p>
      </div>

      {ghStatus.data && !ghStatus.data.linked && (
        <div className="card flex items-center gap-3 border-amber-200 bg-amber-50 p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100">
            <svg className="h-4 w-4 text-amber-600" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-12-12-12-12z"/>
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800">Link your GitHub account to get started</p>
            <p className="mt-0.5 text-xs text-amber-700">
              Connect GitHub to attach repositories, run analysis, and use AI-powered features.
            </p>
          </div>
          <Link to="/profile" className="btn btn-primary btn-sm shrink-0">
            Link GitHub
          </Link>
        </div>
      )}

      <div className="card-flat p-6">
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4">
          <div className="min-w-52 flex-1">
            <label className="label" htmlFor="project-name">Project name</label>
            <input
              id="project-name"
              className="input"
              placeholder="e.g. My platform"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="min-w-52 flex-1">
            <label className="label" htmlFor="project-description">Description</label>
            <input
              id="project-description"
              className="input"
              placeholder="What does this project contain?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating…' : 'Create project'}
          </button>
        </form>
        {createError ? (
          <p className="mt-3 text-sm text-rose-600">{createError}</p>
        ) : null}
      </div>

      {projects.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2].map((i) => (
            <div key={i} className="card p-6">
              <div className="skeleton h-5 w-32" />
              <div className="skeleton mt-3 h-4 w-full" />
              <div className="skeleton mt-2 h-4 w-2/3" />
            </div>
          ))}
        </div>
      ) : projects.isError ? (
        <div className="empty-state">
          <svg className="h-12 w-12 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="mt-3 text-sm text-stone-600">
            Failed to load projects: {(projects.error as Error).message}
          </p>
        </div>
      ) : !projects.data || projects.data.length === 0 ? (
        <div className="empty-state">
          <svg className="h-12 w-12 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <h3 className="mt-3 text-sm font-semibold text-stone-900">No projects yet</h3>
          <p className="mt-1 text-sm text-stone-500">
            Create your first project to start analyzing repositories.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {projects.data.map((project) => (
            <div key={project.id} className="card flex flex-col p-6">
              <Link
                to={`/projects/${project.id}`}
                className="text-lg font-semibold text-teal-700 hover:text-teal-800 hover:underline"
              >
                {project.name}
              </Link>
              {project.description ? (
                <p className="mt-2 line-clamp-2 text-sm text-stone-600">
                  {project.description}
                </p>
              ) : null}
              <div className="mt-4 flex items-center gap-2 text-xs text-stone-400">
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                Created {new Date(project.created_at).toLocaleDateString()}
                {(project as ProjectWithRepos).repositories?.length ? ` • ${(project as ProjectWithRepos).repositories.length} repo(s)` : ''}
              </div>
              <div className="mt-4 flex gap-2 border-t border-stone-100 pt-4">
                <Link
                  to={`/projects/${project.id}`}
                  className="btn btn-outline flex-1 justify-center"
                >
                  Open project
                </Link>
                <button
                  type="button"
                  className="btn btn-ghost text-rose-600 hover:bg-rose-50"
                  onClick={() => {
                    if (window.confirm(`Delete project "${project.name}"?`)) {
                      deleteMutation.mutate(project.id)
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
