import { Link, useParams, useSearchParams } from 'react-router-dom'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  isJobRunning,
  statusStyle,
  useJobStatus,
} from '../hooks/useJobStatus'

function Languages({ histogram }: { histogram: Record<string, number> | null }) {
  if (!histogram) return null
  const total = Object.values(histogram).reduce((a, b) => a + b, 0)
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(histogram)
        .sort((a, b) => b[1] - a[1])
        .map(([lang, count]) => (
          <span key={lang} className="badge bg-slate-100 text-slate-600">
            {lang}
            <span className="text-slate-400">
              {count} ({Math.round((count / total) * 100)}%)
            </span>
          </span>
        ))}
    </div>
  )
}

export default function AnalysisStatus() {
  const { jobId } = useParams()
  useSearchParams()
  // const repoId = params.get('repo') // Available for future use

  usePageTitle('Analysis status')

  const job = useJobStatus(jobId)

  const running = isJobRunning(job.data?.status)

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Analysis status</h1>
          <p className="mt-1 font-mono text-xs text-slate-400">
            Job {jobId}
          </p>
        </div>
        {job.data ? (
          <div className="flex items-center gap-2">
            <span className={`badge ${statusStyle(job.data.status)}`}>
              {running ? (
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              ) : null}
              {job.data.status}
            </span>
            <span className={`badge ${job.data.error?.includes('incremental') ? 'bg-sky-100 text-sky-700' : 'bg-violet-100 text-violet-700'}`}>
              {job.data.error?.includes('incremental') ? 'Incremental' : 'Full'}
            </span>
          </div>
        ) : null}
      </div>

      {job.isLoading ? (
        <p className="text-sm text-slate-400">Loading job…</p>
      ) : job.isError ? (
        <p className="text-sm text-rose-600">{(job.error as Error).message}</p>
      ) : job.data ? (
        <>
          {running ? (
            <div className="card flex items-center gap-3 p-4 text-sm text-indigo-700">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
              Repository analysis in progress — this page refreshes every 2
              seconds until it finishes.
            </div>
          ) : null}

          {job.data.error ? (
            <div
              className={`card p-4 text-sm ${
                job.data.status === 'failed'
                  ? 'border-rose-200 text-rose-700'
                  : 'border-amber-200 text-amber-800'
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

          <div className="card p-4">
            <h2 className="label">Counts</h2>
            <dl className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-6">
              <div>
                <dt className="text-xs text-slate-400">Files scanned</dt>
                <dd className="text-2xl font-bold text-slate-900">
                  {job.data.files_scanned}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Files indexed</dt>
                <dd className="text-2xl font-bold text-slate-900">
                  {job.data.files_indexed}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Symbols indexed</dt>
                <dd className="text-2xl font-bold text-slate-900">
                  {job.data.symbols_indexed}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Chunks embedded</dt>
                <dd className="text-2xl font-bold text-slate-900">
                  {job.data.chunks_indexed}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Started</dt>
                <dd className="text-sm font-medium text-slate-700">
                  {job.data.started_at
                    ? new Date(job.data.started_at).toLocaleString()
                    : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Indexing mode</dt>
                <dd className="text-sm font-medium text-slate-700">
                  <span className={`badge ${job.data.error?.includes('incremental') ? 'bg-sky-100 text-sky-700' : 'bg-violet-100 text-violet-700'}`}>
                    {job.data.error?.includes('incremental') ? 'Incremental' : 'Full'}
                  </span>
                </dd>
              </div>
            </dl>
          </div>

          <div className="card p-4">
            <h2 className="label">Languages</h2>
            <div className="mt-2">
              <Languages histogram={job.data.languages} />
            </div>
          </div>

          <div className="flex gap-2">
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