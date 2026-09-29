import { useQuery } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'
import { useState } from 'react'
import { listRepoFindings, getFindingsSummary } from '../api/client'
import type { RiskLevel } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'

const LEVEL_STYLES: Record<RiskLevel, string> = {
  low: 'bg-emerald-100 text-emerald-700',
  medium: 'bg-amber-100 text-amber-700',
  high: 'bg-rose-100 text-rose-700',
}

function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`badge ${LEVEL_STYLES[level]}`}>
      {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  )
}

function ProbabilityBar({ prob }: { prob: number }) {
  const pct = Math.round(prob * 100)
  let color = 'bg-emerald-500'
  if (prob >= 0.7) color = 'bg-rose-500'
  else if (prob >= 0.4) color = 'bg-amber-500'
  return (
    <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
      <div className={`${color} h-full rounded-full transition-all`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export default function Findings() {
  const { repoId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [riskLevel, setRiskLevel] = useState<RiskLevel | ''>('')
  const [minProb, setMinProb] = useState(0)

  usePageTitle('Risk Findings')

  const summary = useQuery({
    queryKey: ['findings-summary', repoId],
    queryFn: () => getFindingsSummary(repoId as string),
    enabled: Boolean(repoId),
  })

  const findings = useQuery({
    queryKey: ['findings', repoId, riskLevel, minProb, searchParams.get('page') ?? '1'],
    queryFn: () =>
      listRepoFindings(repoId as string, {
        risk_level: riskLevel || undefined,
        min_probability: minProb || undefined,
        limit: 50,
        offset: (parseInt(searchParams.get('page') ?? '1') - 1) * 50,
      }),
    enabled: Boolean(repoId),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Risk Findings</h1>
          <p className="mt-1 text-sm text-slate-500">
            Functions and classes scored by the risk model (low / medium / high).
          </p>
        </div>
      </div>

      {/* Summary cards */}
      {summary.data && (
        <div className="grid gap-4 sm:grid-cols-3">
          {(['low', 'medium', 'high'] as RiskLevel[]).map((level) => (
            <div
              key={level}
              className={`card p-4 border-l-4 ${LEVEL_STYLES[level].replace('bg-', 'border-').replace('text-', '')}`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide">{level}</p>
                  <p className="mt-1 text-3xl font-bold text-slate-900">
                    {summary.data.by_level[level] ?? 0}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap gap-1">
            {(['low', 'medium', 'high'] as RiskLevel[]).map((l) => (
              <button
                key={l}
                type="button"
                className={
                  riskLevel === l
                    ? 'rounded-md bg-indigo-600 px-2 py-1 text-xs font-medium text-white'
                    : 'rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50'
                }
                onClick={() => setRiskLevel(riskLevel === l ? '' : l)}
              >
                {l.charAt(0).toUpperCase() + l.slice(1)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-xs text-slate-500">Min probability:</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={minProb}
              onChange={(e) => setMinProb(Number(e.target.value))}
              className="w-32 accent-indigo-600"
            />
            <span className="text-xs font-mono text-slate-600 w-10 text-right">
              {Math.round(minProb * 100)}%
            </span>
          </div>
        </div>
      </div>

      {/* Findings table */}
      <div className="card overflow-hidden">
        {findings.isLoading ? (
          <p className="p-3 text-sm text-slate-400">Loading findings…</p>
        ) : findings.isError ? (
          <p className="p-3 text-sm text-rose-600">
            {(findings.error as Error).message}
          </p>
        ) : !findings.data || findings.data.findings.length === 0 ? (
          <p className="p-3 text-sm text-slate-400">
            {riskLevel || minProb > 0
              ? 'No findings match the current filters.'
              : 'No risk findings for this repository. Train the model from Risk Training.'}
          </p>
        ) : (
          <>
            <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500">
              Showing {findings.data.findings.length} of {findings.data.total} findings
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="th">Risk</th>
                  <th className="th">Probability</th>
                  <th className="th">Symbol</th>
                  <th className="th">File</th>
                  <th className="th">Lines</th>
                  <th className="th">Model</th>
                </tr>
              </thead>
              <tbody>
                {findings.data.findings.map((f) => (
                  <tr key={f.id} className="border-b border-slate-100 hover:bg-slate-50/50">
                    <td className="td">
                      <RiskBadge level={f.risk_level} />
                    </td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <ProbabilityBar prob={f.probability} />
                        <span className="text-xs font-mono text-slate-600">
                          {Math.round(f.probability * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="td">
                      <span className="font-mono text-xs font-semibold">
                        {f.symbol_kind} {f.symbol_name}
                      </span>
                    </td>
                    <td className="td max-w-56 truncate font-mono text-xs text-slate-500">
                      {f.file_path}
                    </td>
                    <td className="td text-xs text-slate-500 font-mono">
                      {f.start_line}–{f.end_line}
                    </td>
                    <td className="td text-xs text-slate-400 font-mono">
                      {f.model_version.slice(0, 20)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {findings.data.total > 50 && (
              <div className="border-t border-slate-200 px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Page {parseInt(searchParams.get('page') ?? '1')} of {Math.ceil(findings.data.total / 50)}
                </span>
                <div className="flex gap-1">
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={!searchParams.get('page') || parseInt(searchParams.get('page')!) <= 1}
                    onClick={() => {
                      const prev = parseInt(searchParams.get('page') ?? '2') - 1
                      setSearchParams(prev > 1 ? { page: String(prev) } : {})
                    }}
                  >
                    Prev
                  </button>
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={parseInt(searchParams.get('page') ?? '1') * 50 >= findings.data.total}
                    onClick={() => {
                      const next = parseInt(searchParams.get('page') ?? '1') + 1
                      setSearchParams({ page: String(next) })
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}