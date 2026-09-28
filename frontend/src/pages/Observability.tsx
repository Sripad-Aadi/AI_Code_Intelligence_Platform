import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  getJobStats,
  getBenchmarkStatus,
  runRetrievalBenchmark,
  trainRiskModel,
  evaluateRiskModel,
  getCostSummary,
  listAttachedRepos,
} from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'

function StatCard({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
      <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`${color} h-full rounded-full`} style={{ width: '100%' }} />
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <h3 className="label mb-4">{title}</h3>
      {children}
    </div>
  )
}

export default function Observability() {
  // `?repo=<id>` scopes the page when it is opened from a repository;
  // without one the stats and costs are global, and the benchmark section
  // asks which repository to test. (The route itself has no `:repoId`
  // segment, so `useParams` would always be undefined here.)
  const [searchParams] = useSearchParams()
  const repoId = searchParams.get('repo')
  const [trainModelType, setTrainModelType] = useState<'logistic' | 'gbt'>('logistic')
  const [trainRepoIds, setTrainRepoIds] = useState<string>('')
  const [benchRepoId, setBenchRepoId] = useState<string>('')

  usePageTitle('Observability')

  const jobStats = useQuery({
    queryKey: ['job-stats', repoId],
    queryFn: () => getJobStats(repoId ?? undefined),
  })

  const attachedRepos = useQuery({
    queryKey: ['attached-repos'],
    queryFn: listAttachedRepos,
  })

  const benchmarkStatus = useQuery({
    queryKey: ['benchmark-status'],
    queryFn: getBenchmarkStatus,
  })

  const costSummary = useQuery({
    queryKey: ['cost-summary', repoId],
    queryFn: () => getCostSummary(repoId ?? undefined),
  })

  const runBenchmark = useMutation({
    mutationFn: ({ repoId, k }: { repoId: string; k: number }) => runRetrievalBenchmark(repoId, k),
  })

  const trainModel = useMutation({
    mutationFn: async ({ repoIds, modelType }: { repoIds?: string[]; modelType: string }) =>
      trainRiskModel(repoIds, modelType),
  })

  const evaluateModel = useMutation({
    mutationFn: async (repoIds?: string[]) =>
      evaluateRiskModel(repoIds),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Observability</h1>
        <p className="mt-1 text-sm text-slate-500">
          System metrics, job statistics, and benchmark management.
        </p>
      </div>

      {/* Job Statistics */}
      <Section title="Job Statistics">
        {jobStats.isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {jobStats.isError && !jobStats.isLoading && (
          <p className="text-sm text-rose-600">Failed to load: {(jobStats.error as Error).message}</p>
        )}
        {jobStats.data && !jobStats.isLoading && !jobStats.isError && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-4">
              <StatCard label="Total Jobs" value={jobStats.data.total_jobs} color="bg-indigo-500" />
              <StatCard label="Queued" value={jobStats.data.queued} color="bg-slate-500" />
              <StatCard label="Running" value={jobStats.data.running} color="bg-amber-500" />
              <StatCard label="Completed" value={jobStats.data.completed} color="bg-emerald-500" />
              <StatCard label="Failed" value={jobStats.data.failed} color="bg-rose-500" />
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Avg Duration (s)"
                value={jobStats.data.avg_duration_sec ? jobStats.data.avg_duration_sec.toFixed(1) : '—'}
                color="bg-indigo-500"
              />
              <StatCard label="Files Indexed" value={jobStats.data.total_files_indexed} color="bg-sky-500" />
              <StatCard label="Symbols Indexed" value={jobStats.data.total_symbols_indexed} color="bg-violet-500" />
              <StatCard label="Chunks Embedded" value={jobStats.data.total_chunks_embedded} color="bg-amber-500" />
            </div>
          </div>
        )}
      </Section>

      {/* Benchmark Status */}
      <Section title="Benchmarks">
        {benchmarkStatus.isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {benchmarkStatus.isError && !benchmarkStatus.isLoading && (
          <p className="text-sm text-rose-600">Failed to load: {(benchmarkStatus.error as Error).message}</p>
        )}
        {benchmarkStatus.data && !benchmarkStatus.isLoading && !benchmarkStatus.isError && (
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Retrieval Benchmark</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {benchmarkStatus.data.retrieval_benchmark_exists ? '✅ Exists' : '❌ Missing'}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Run to measure recall@k and MRR
              </p>
            </div>

            <div className="card p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Risk Model Eval</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {benchmarkStatus.data.risk_eval_exists ? '✅ Exists' : '❌ Missing'}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {benchmarkStatus.data.last_run
                  ? `Last run: ${new Date(benchmarkStatus.data.last_run).toLocaleString()}`
                  : 'Never run'}
              </p>
            </div>

            <div className="card p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">
                Run Retrieval Benchmark
              </p>
              {repoId ? null : (
                <select
                  className="input mt-2"
                  value={benchRepoId}
                  onChange={(e) => setBenchRepoId(e.target.value)}
                >
                  <option value="">Select a repository…</option>
                  {attachedRepos.data?.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.github_full_name}
                    </option>
                  ))}
                </select>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  className="btn btn-primary"
                  disabled={!repoId && !benchRepoId}
                  onClick={() =>
                    runBenchmark.mutate({ repoId: repoId ?? benchRepoId, k: 10 })
                  }
                >
                  {runBenchmark.isPending ? 'Running…' : 'Run (k=10)'}
                </button>
                <span className="text-xs text-slate-400 self-center">
                  Measures recall@1,3,5,10 and MRR
                </span>
              </div>
              {runBenchmark.isError && (
                <p className="mt-2 text-xs text-rose-600">
                  {(runBenchmark.error as Error).message}
                </p>
              )}
              {runBenchmark.isSuccess && (
                <p className="mt-2 text-xs text-emerald-600">
                  Ran {runBenchmark.data.questions_run} question
                  {runBenchmark.data.questions_run === 1 ? '' : 's'} — recall@1{' '}
                  {(runBenchmark.data.summary as Record<string, number>).recall_at_1?.toFixed(2) ?? '—'},
                  MRR{' '}
                  {(runBenchmark.data.summary as Record<string, number>).mrr?.toFixed(2) ?? '—'}
                </p>
              )}
            </div>
          </div>
        )}
        {!benchmarkStatus.isLoading && !benchmarkStatus.isError && !benchmarkStatus.data && (
          <p className="text-sm text-slate-400">No benchmark data available</p>
        )}
      </Section>

      {/* Risk Model Training */}
      <Section title="Risk Model">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="card p-4">
            <h4 className="label mb-3">Train Model</h4>
            <div className="space-y-3">
              <div>
                <label className="label">Model Type</label>
                <select
                  className="input"
                  value={trainModelType}
                  onChange={(e) => setTrainModelType(e.target.value as 'logistic' | 'gbt')}
                >
                  <option value="logistic">Logistic Regression (fast, interpretable)</option>
                  <option value="gbt">Gradient Boosting (non-linear)</option>
                </select>
              </div>
              <div>
                <label className="label">Repo IDs (comma-separated, optional)</label>
                <input
                  className="input"
                  placeholder="repo-uuid-1,repo-uuid-2"
                  value={trainRepoIds}
                  onChange={(e) => setTrainRepoIds(e.target.value)}
                />
              </div>
              <button
                className="btn btn-primary"
                disabled={trainModel.isPending}
                onClick={() => trainModel.mutate({ repoIds: trainRepoIds ? trainRepoIds.split(',').map((s) => s.trim()) : undefined, modelType: trainModelType })}
              >
                {trainModel.isPending ? 'Training…' : 'Train Model'}
              </button>
              {trainModel.isError && (
                <p className="text-sm text-rose-600">Failed: {(trainModel.error as Error).message}</p>
              )}
              {trainModel.isSuccess && (
                <p className="text-sm text-emerald-600">Training completed!</p>
              )}
            </div>
          </div>

          <div className="card p-4">
            <h4 className="label mb-3">Evaluate Model</h4>
            <div className="space-y-3">
              <div>
                <label className="label">Repo IDs (comma-separated, optional)</label>
                <input
                  className="input"
                  placeholder="repo-uuid-1,repo-uuid-2"
                  value={trainRepoIds}
                  onChange={(e) => setTrainRepoIds(e.target.value)}
                />
              </div>
              <button
                className="btn btn-outline"
                disabled={evaluateModel.isPending}
                onClick={() => evaluateModel.mutate(trainRepoIds ? trainRepoIds.split(',').map((s) => s.trim()) : undefined)}
              >
                {evaluateModel.isPending ? 'Evaluating…' : 'Run Evaluation'}
              </button>
              {evaluateModel.isError && (
                <p className="text-sm text-rose-600">Failed: {(evaluateModel.error as Error).message}</p>
              )}
              {evaluateModel.isSuccess && (
                <p className="text-sm text-emerald-600">Evaluation completed! Check logs for metrics.</p>
              )}
            </div>
          </div>
        </div>
      </Section>

      {/* Cost Tracking */}
      <Section title="LLM Cost Tracking">
        <div className="card p-4">
          <div className="grid gap-4 sm:grid-cols-4">
            <StatCard label="Total Calls" value={costSummary.data?.total_calls ?? 0} color="bg-indigo-500" />
            <StatCard label="Total Cost" value={`$${costSummary.data?.total_cost_usd.toFixed(4) ?? '0.0000'}`} color="bg-emerald-500" />
            <StatCard label="Input Tokens" value={costSummary.data?.total_input_tokens.toLocaleString() ?? '0'} color="bg-sky-500" />
            <StatCard label="Output Tokens" value={costSummary.data?.total_output_tokens.toLocaleString() ?? '0'} color="bg-amber-500" />
          </div>
          {costSummary.data?.by_model && Object.keys(costSummary.data.by_model).length > 0 && (
            <div className="mt-4">
              <h4 className="label mb-2">By Model</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      <th className="th">Model</th>
                      <th className="th">Calls</th>
                      <th className="th">Input Tokens</th>
                      <th className="th">Output Tokens</th>
                      <th className="th">Cost (USD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(costSummary.data.by_model).map(([model, data]) => (
                      <tr key={model} className="border-b border-slate-100 hover:bg-slate-50/50">
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