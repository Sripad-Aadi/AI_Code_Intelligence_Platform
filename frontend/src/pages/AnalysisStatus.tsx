import { Link, useParams } from 'react-router-dom'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  isJobRunning,
  statusStyle,
  useJobStatus,
} from '../hooks/useJobStatus'
import BackButton from '../components/BackButton'

export default function AnalysisStatus() {
  const { jobId } = useParams()

  usePageTitle('Analysis status')

  const job = useJobStatus(jobId)

  const running = isJobRunning(job.data?.status)

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <BackButton />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-stone-900">Analysis status</h1>
            <p className="mt-1 font-mono text-xs text-stone-400">
              Job {jobId}
            </p>
          </div>
        </div>
        {job.data ? (
          <div className="flex items-center gap-2">
            <span className={`badge ${statusStyle(job.data.status)}`}>
              {running ? (
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              ) : null}
              {job.data.status}
            </span>
            <span className={`badge ${job.data.mode === 'incremental' ? 'badge-teal' : 'badge-stone'}`}>
              {job.data.mode === 'incremental' ? 'Incremental' : 'Full'}
            </span>
          </div>
        ) : null}
      </div>

      {job.isLoading ? (
        <div className="space-y-4">
          <div className="card p-6">
            <div className="skeleton h-6 w-32" />
            <div className="skeleton mt-4 h-4 w-full" />
          </div>
          <div className="card p-6">
            <div className="skeleton h-6 w-24" />
            <div className="skeleton mt-4 h-20 w-full" />
          </div>
        </div>
      ) : job.isError ? (
        <div className="empty-state">
          <p className="text-sm text-stone-600">{(job.error as Error).message}</p>
        </div>
      ) : job.data ? (
        <>
          {running ? (
            <div className="card flex items-center gap-3 border-teal-200 bg-teal-50 p-4 text-sm text-teal-800">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />
              Repository analysis in progress — this page refreshes every 2 seconds until it finishes.
            </div>
          ) : null}

          {job.data.error ? (
            <div
              className={`card p-4 text-sm ${
                job.data.status === 'failed'
                  ? 'border-rose-200 bg-rose-50 text-rose-800'
                  : 'border-amber-200 bg-amber-50 text-amber-800'
              }`}
            >
              <p className="font-semibold">
                {job.data.status === 'failed'
                  ? 'Job failed'
                  : 'Completed with warnings'}
              </p>
              <p className="mt-1 font-mono text-xs">{job.data.error}</p>
            </div>
          ) : null}

          <div className="card p-6">
            <h2 className="label">Counts</h2>
            <dl className="mt-4 grid grid-cols-2 gap-6 sm:grid-cols-4">
              <div>
                <dt className="stat-label">Files scanned</dt>
                <dd className="stat-value">{job.data.files_scanned}</dd>
              </div>
              <div>
                <dt className="stat-label">Files indexed</dt>
                <dd className="stat-value">{job.data.files_indexed}</dd>
              </div>
              <div>
                <dt className="stat-label">Symbols indexed</dt>
                <dd className="stat-value">{job.data.symbols_indexed}</dd>
              </div>
              <div>
                <dt className="stat-label">Chunks embedded</dt>
                <dd className="stat-value">{job.data.chunks_indexed}</dd>
              </div>
            </dl>
            <div className="mt-6 grid grid-cols-2 gap-6 border-t border-stone-100 pt-4 sm:grid-cols-2">
              <div>
                <dt className="stat-label">Started</dt>
                <dd className="mt-1 text-sm font-medium text-stone-700">
                  {job.data.started_at
                    ? new Date(job.data.started_at).toLocaleString()
                    : '—'}
                </dd>
              </div>
              <div>
                <dt className="stat-label">Indexing mode</dt>
                <dd className="mt-1">
                  <span className={`badge ${job.data.mode === 'incremental' ? 'badge-teal' : 'badge-stone'}`}>
                    {job.data.mode === 'incremental' ? 'Incremental' : 'Full'}
                  </span>
                </dd>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <Link to={`/repos/${job.data.repo_id}`} className="btn btn-primary">
              Explore repository
            </Link>
            <Link to="/" className="btn btn-outline">
              Back to projects
            </Link>
          </div>
        </>
      ) : null}
    </div>
  )
}
