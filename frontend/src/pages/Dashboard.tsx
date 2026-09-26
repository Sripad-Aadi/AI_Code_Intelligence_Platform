import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { createProject, deleteProject, listProjects } from '../api/client'
import LinkGithub from '../components/LinkGithub'

export default function Dashboard() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
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
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Projects</h1>
          <p className="text-sm text-slate-500">
            Attach GitHub repositories, run structural analysis, and explore
            the results.
          </p>
        </div>
        <LinkGithub />
      </div>

      <div className="card p-4">
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div className="min-w-52 flex-1">
            <label className="label" htmlFor="project-name">
              New project
            </label>
            <input
              id="project-name"
              className="input"
              placeholder="e.g. My platform"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="min-w-52 flex-1">
            <label className="label" htmlFor="project-description">
              Description
            </label>
            <input
              id="project-description"
              className="input"
              placeholder="Optional"
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
          <p className="mt-2 text-sm text-rose-600">{createError}</p>
        ) : null}
      </div>

      {projects.isLoading ? (
        <p className="text-sm text-slate-400">Loading projects…</p>
      ) : projects.isError ? (
        <p className="text-sm text-rose-600">
          Failed to load projects: {(projects.error as Error).message}
        </p>
      ) : !projects.data || projects.data.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-500">
          No projects yet — create one above to get started.
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {projects.data.map((project) => (
            <li key={project.id} className="card flex flex-col p-4">
              <Link
                to={`/projects/${project.id}`}
                className="text-base font-semibold text-indigo-700 hover:underline"
              >
                {project.name}
              </Link>
              {project.description ? (
                <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                  {project.description}
                </p>
              ) : null}
              <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                <span>
                  Created{' '}
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
                <span aria-hidden>•</span>
                <span>Opened from dashboard</span>
              </div>
              <div className="mt-3 flex gap-2">
                <Link
                  to={`/projects/${project.id}`}
                  className="btn btn-outline flex-1 justify-center"
                >
                  Open project
                </Link>
                <button
                  type="button"
                  className="btn btn-ghost text-rose-600"
                  onClick={() => {
                    if (window.confirm(`Delete project "${project.name}"?`)) {
                      deleteMutation.mutate(project.id)
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}