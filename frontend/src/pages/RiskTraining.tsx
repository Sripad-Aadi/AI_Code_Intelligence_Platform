import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { trainRiskModel, evaluateRiskModel, getJobStats, listAttachedRepos } from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'

export default function RiskTraining() {
  const [modelType, setModelType] = useState<'logistic' | 'gbt'>('logistic')
  const [selectedRepoIds, setSelectedRepoIds] = useState<string[]>([])

  usePageTitle('Risk Model Training')

  const stats = useQuery({
    queryKey: ['job-stats'],
    queryFn: () => getJobStats(),
  })

  const repos = useQuery({
    queryKey: ['attached-repos'],
    queryFn: listAttachedRepos,
  })

  const trainModel = useMutation({
    mutationFn: async ({ repoIds, modelType }: { repoIds?: string[]; modelType: string }) =>
      trainRiskModel(repoIds, modelType),
  })

  const evaluateModel = useMutation({
    mutationFn: async (repoIds?: string[]) => evaluateRiskModel(repoIds),
  })

  const toggleRepo = (repoId: string) => {
    setSelectedRepoIds(prev =>
      prev.includes(repoId) ? prev.filter(id => id !== repoId) : [...prev, repoId]
    )
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Risk Model Training</h1>
        <p className="mt-1 text-sm text-slate-500">
          Train and evaluate the 3-class risk classifier (low/medium/high).
          Features: cyclomatic complexity, LOC, fan-in/out, test file heuristic, churn.
        </p>
      </div>

      {/* Data Overview */}
      <div className="card p-4 mb-6">
        <h3 className="label mb-3">Available Training Data</h3>
        {stats.isLoading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : stats.isError ? (
          <p className="text-sm text-rose-600">Failed to load stats</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="card p-3 bg-emerald-50 border-emerald-200">
              <p className="text-xs text-emerald-700">Completed Jobs</p>
              <p className="text-2xl font-bold text-emerald-900">{stats.data?.completed ?? 0}</p>
            </div>
            <div className="card p-3 bg-indigo-50 border-indigo-200">
              <p className="text-xs text-indigo-700">Total Files Indexed</p>
              <p className="text-2xl font-bold text-indigo-900">{stats.data?.total_files_indexed ?? 0}</p>
            </div>
            <div className="card p-3 bg-violet-50 border-violet-200">
              <p className="text-xs text-violet-700">Total Symbols</p>
              <p className="text-2xl font-bold text-violet-900">{stats.data?.total_symbols_indexed ?? 0}</p>
            </div>
            <div className="card p-3 bg-amber-50 border-amber-200">
              <p className="text-xs text-amber-700">Total Chunks</p>
              <p className="text-2xl font-bold text-amber-900">{stats.data?.total_chunks_embedded ?? 0}</p>
            </div>
          </div>
        )}
      </div>

      {/* Repo Selector */}
      <div className="card p-4 mb-6">
        <h3 className="label mb-3">Select Repositories for Training/Evaluation</h3>
        {repos.isLoading ? (
          <p className="text-sm text-slate-400">Loading repositories…</p>
        ) : repos.isError ? (
          <p className="text-sm text-rose-600">Failed to load repositories</p>
        ) : (
          <div className="space-y-2 max-h-60 overflow-auto">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={repos.data && selectedRepoIds.length === repos.data.length && repos.data.length > 0}
                onChange={() => {
                  if (repos.data) {
                    setSelectedRepoIds(
                      selectedRepoIds.length === repos.data.length
                        ? []
                        : repos.data.map(r => r.id)
                    )
                  }
                }}
                className="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500"
              />
              <span className="text-sm font-medium text-slate-700">
                {selectedRepoIds.length === repos.data?.length && repos.data?.length > 0 ? 'Deselect all' : 'Select all'} ({repos.data?.length ?? 0} repos)
              </span>
            </label>
            <div className="max-h-48 overflow-auto border border-slate-200 rounded p-2">
              {repos.data?.map(repo => (
                <label key={repo.id} className="flex items-center gap-2 cursor-pointer px-2 py-1 hover:bg-slate-50 rounded">
                  <input
                    type="checkbox"
                    checked={selectedRepoIds.includes(repo.id)}
                    onChange={() => toggleRepo(repo.id)}
                    className="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">
                      {repo.github_full_name ?? repo.id}
                    </p>
                    <p className="text-xs text-slate-500">
                      {repo.default_branch ? `branch: ${repo.default_branch}` : 'no branch'}
                    </p>
                  </div>
                </label>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-2">
              {selectedRepoIds.length} of {repos.data?.length ?? 0} selected. Leave empty to use all repositories.
            </p>
          </div>
        )}
      </div>

      {/* Training Form */}
      <div className="card p-6 space-y-6">
        <h3 className="label">Train New Model</h3>

        <div className="space-y-4">
          <div>
            <label className="label">Model Type</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="modelType"
                  value="logistic"
                  checked={modelType === 'logistic'}
                  onChange={() => setModelType('logistic')}
                  className="w-4 h-4 text-indigo-600 border-slate-300 focus:ring-indigo-500"
                />
                <span className="text-sm text-slate-700">
                  <strong>Logistic Regression</strong> — Fast, linear, interpretable coefficients
                </span>
              </label>
            </div>
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="modelType"
                  value="gbt"
                  checked={modelType === 'gbt'}
                  onChange={() => setModelType('gbt')}
                  className="w-4 h-4 text-indigo-600 border-slate-300 focus:ring-indigo-500"
                />
                <span className="text-sm text-slate-700">
                  <strong>Gradient Boosting</strong> — Non-linear, may capture complex patterns
                </span>
              </label>
            </div>
          </div>
        </div>

        <button
          className="btn btn-primary w-full sm:w-auto"
          disabled={trainModel.isPending}
          onClick={() => trainModel.mutate({
            repoIds: selectedRepoIds.length > 0 ? selectedRepoIds : undefined,
            modelType,
          })}
        >
          {trainModel.isPending ? 'Training…' : 'Train Model'}
        </button>

        {trainModel.isError && (
          <p className="text-sm text-rose-600">Training failed: {(trainModel.error as Error).message}</p>
        )}
        {trainModel.isSuccess && (
          <p className="text-sm text-emerald-600">Model trained successfully! Check server logs for metrics.</p>
        )}
      </div>

      {/* Evaluation Form */}
      <div className="card p-6 space-y-4 border-amber-200">
        <h3 className="label text-amber-700">Evaluate Existing Model</h3>
        <p className="text-sm text-slate-500">
          Runs the trained model on held-out test data and reports precision/recall/F1 per class.
        </p>

        <div className="space-y-3">
          <button
            className="btn btn-outline"
            disabled={evaluateModel.isPending}
            onClick={() => evaluateModel.mutate(selectedRepoIds.length > 0 ? selectedRepoIds : undefined)}
          >
            {evaluateModel.isPending ? 'Evaluating…' : 'Run Evaluation'}
          </button>

          {evaluateModel.isError && (
            <p className="text-sm text-rose-600">Evaluation failed: {(evaluateModel.error as Error).message}</p>
          )}
          {evaluateModel.isSuccess && (
            <p className="text-sm text-emerald-600">Evaluation completed! Check server logs for detailed metrics.</p>
          )}
        </div>
      </div>

      {/* Model Features Reference */}
      <div className="card p-4">
        <h3 className="label mb-3">Feature Reference</h3>
        <p className="text-sm text-slate-500 mb-3">
          The risk model uses these 6 engineered features concatenated with the 768-dim Jina embedding:
        </p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <div className="card p-3 bg-emerald-50 border-emerald-200">
            <p className="font-medium text-emerald-900">1. Cyclomatic Complexity</p>
            <p className="text-xs text-emerald-700">radon (Python) or AST-depth approx (others)</p>
          </div>
          <div className="card p-3 bg-blue-50 border-blue-200">
            <p className="font-medium text-blue-900">2. Lines of Code</p>
            <p className="text-xs text-blue-700">Symbol span (end_line - start_line + 1)</p>
          </div>
          <div className="card p-3 bg-violet-50 border-violet-200">
            <p className="font-medium text-violet-900">3. Fan-in</p>
            <p className="text-xs text-violet-700">Files importing this file (1-hop)</p>
          </div>
          <div className="card p-3 bg-amber-50 border-amber-200">
            <p className="font-medium text-amber-900">4. Fan-out</p>
            <p className="text-xs text-amber-700">Files this file imports (1-hop)</p>
          </div>
          <div className="card p-3 bg-indigo-50 border-indigo-200">
            <p className="font-medium text-indigo-900">5. Has Test File</p>
            <p className="text-xs text-indigo-700">Heuristic: test_*, *_test, *.test.* patterns</p>
          </div>
          <div className="card p-3 bg-rose-50 border-rose-200">
            <p className="font-medium text-rose-900">6. Recent Churn</p>
            <p className="text-xs text-rose-700">Git commits touching file (last 90 days)</p>
          </div>
        </div>
      </div>
    </div>
  )
}