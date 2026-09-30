import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  getJobStats,
  getCostSummary,
} from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'
import BackButton from '../components/BackButton'

function StatCard({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className="stat-card">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-200">
        <div className={`${color} h-full rounded-full`} style={{ width: '100%' }} />
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card-flat p-6">
      <h2 className="label mb-4">{title}</h2>
      {children}
    </div>
  )
}

export default function Observability() {
  const [searchParams] = useSearchParams()
  const repoId = searchParams.get('repo')

  usePageTitle('Observability')

  const jobStats = useQuery({
    queryKey: ['job-stats', repoId],
    queryFn: () => getJobStats(repoId ?? undefined),
  })

  const costSummary = useQuery({
    queryKey: ['cost-summary', repoId],
    queryFn: () => getCostSummary(repoId ?? undefined),
  })

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <BackButton />
        <h1 className="text-2xl font-bold tracking-tight text-stone-900">Observability</h1>
        <p className="mt-1 text-sm text-stone-500">
          System metrics, job statistics, and cost tracking.
        </p>
      </div>

      <Section title="Job Statistics">
        {jobStats.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton h-20" />
            ))}
          </div>
        ) : jobStats.isError ? (
          <p className="text-sm text-rose-600">Failed to load: {(jobStats.error as Error).message}</p>
        ) : jobStats.data ? (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard label="Total Jobs" value={jobStats.data.total_jobs} color="bg-teal-500" />
              <StatCard label="Queued" value={jobStats.data.queued} color="bg-stone-400" />
              <StatCard label="Running" value={jobStats.data.running} color="bg-amber-500" />
              <StatCard label="Completed" value={jobStats.data.completed} color="bg-emerald-500" />
              <StatCard label="Failed" value={jobStats.data.failed} color="bg-rose-500" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Avg Duration (s)"
                value={jobStats.data.avg_duration_sec ? jobStats.data.avg_duration_sec.toFixed(1) : '—'}
                color="bg-teal-500"
              />
              <StatCard label="Files Indexed" value={jobStats.data.total_files_indexed} color="bg-sky-500" />
              <StatCard label="Symbols Indexed" value={jobStats.data.total_symbols_indexed} color="bg-stone-500" />
              <StatCard label="Chunks Embedded" value={jobStats.data.total_chunks_embedded} color="bg-amber-500" />
            </div>
          </div>
        ) : null}
      </Section>

      <Section title="LLM Cost Tracking">
        <div className="stat-card">
          <div className="grid gap-4 sm:grid-cols-4">
            <StatCard label="Total Calls" value={costSummary.data?.total_calls ?? 0} color="bg-teal-500" />
            <StatCard label="Total Cost" value={`$${costSummary.data?.total_cost_usd.toFixed(4) ?? '0.0000'}`} color="bg-emerald-500" />
            <StatCard label="Input Tokens" value={costSummary.data?.total_input_tokens.toLocaleString() ?? '0'} color="bg-sky-500" />
            <StatCard label="Output Tokens" value={costSummary.data?.total_output_tokens.toLocaleString() ?? '0'} color="bg-amber-500" />
          </div>
          {costSummary.data?.by_model && Object.keys(costSummary.data.by_model).length > 0 && (
            <div className="mt-4">
              <h3 className="label mb-2">By Model</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-stone-200 bg-stone-50">
                      <th className="th">Model</th>
                      <th className="th">Calls</th>
                      <th className="th">Input Tokens</th>
                      <th className="th">Output Tokens</th>
                      <th className="th">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(costSummary.data.by_model).map(([model, data]) => (
                      <tr key={model} className="border-b border-stone-100 hover:bg-stone-50/50">
                        <td className="td font-mono text-xs">{model}</td>
                        <td className="td">{data.calls}</td>
                        <td className="td font-mono">{data.input_tokens.toLocaleString()}</td>
                        <td className="td font-mono">{data.output_tokens.toLocaleString()}</td>
                        <td className="td font-mono">${data.cost_usd.toFixed(6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </Section>
    </div>
  )
}
