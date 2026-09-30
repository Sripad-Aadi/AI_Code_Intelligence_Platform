import { useQuery, useMutation } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { getPRAnalysis } from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-stone-500 uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-3xl font-bold text-stone-900">{value}</p>
      <div className="mt-2 h-1.5 bg-stone-100 rounded-full overflow-hidden">
        <div className={`${color} h-full rounded-full`} style={{ width: '100%' }} />
      </div>
    </div>
  )
}

export default function PRDashboard() {
  const { repoId, prNumber } = useParams()
  const prNum = Number(prNumber)

  usePageTitle(`PR #${prNum}`)

  const analysis = useQuery({
    queryKey: ['pr-analysis', repoId, prNum],
    queryFn: () => getPRAnalysis(repoId!, prNum),
    enabled: Boolean(repoId && prNum),
  })

  const runAnalysis = useMutation({
    mutationFn: ({ repoId, prNumber }: { repoId: string; prNumber: number }) =>
      getPRAnalysis(repoId, prNumber),
    onSuccess: () => {
      // The query will be invalidated by the mutation
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-stone-400">
            <Link to="/" className="hover:text-stone-600">
              Projects
            </Link>{' '}
            /{' '}
            <Link to={`/repos/${repoId}`} className="hover:text-stone-600">
              Repository
            </Link>{' '}
            / PR #{prNum}
          </p>
          <h1 className="mt-1 text-xl font-bold text-slate-900">
            PR #{prNum} Analysis
          </h1>
          <p className="mt-1 text-sm text-stone-500">
            Impact analysis, affected files, and recommended tests for this pull request.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={analysis.isLoading || runAnalysis.isPending}
            onClick={() => runAnalysis.mutate({ repoId: repoId!, prNumber: prNum })}
          >
            {runAnalysis.isPending ? 'Analyzing…' : analysis.isLoading ? 'Loading…' : 'Run Analysis'}
          </button>
        </div>
      </div>

      {analysis.isLoading ? (
        <p className="text-sm text-stone-400">Loading analysis…</p>
      ) : analysis.isError ? (
        <p className="text-sm text-rose-600">
          Failed to load analysis: {(analysis.error as Error).message}
        </p>
      ) : analysis.data ? (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="Files Changed" value={analysis.data.files_changed} color="bg-indigo-500" />
            <SummaryCard label="Symbols Changed" value={analysis.data.symbols_changed} color="bg-sky-500" />
            <SummaryCard label="Affected Files" value={analysis.data.affected_files_count} color="bg-amber-500" />
            <SummaryCard label="Test Files" value={analysis.data.test_files_count} color="bg-emerald-500" />
          </div>

          {/* AI Summary */}
      {(analysis.data.summary || analysis.data.key_risks.length > 0) && (
        <div className="card p-4">
          <h2 className="label mb-2">AI Impact Summary</h2>
          {analysis.data.summary && (
            <p className="text-sm text-stone-700 whitespace-pre-line">
              {analysis.data.summary}
            </p>
          )}
          {analysis.data.key_risks.length > 0 && (
            <ul className="mt-2 list-disc pl-5 space-y-1">
              {analysis.data.key_risks.map((risk, i) => (
                <li key={i} className="text-sm text-stone-700">
                  {risk}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Changed Symbols */}
          <div className="card overflow-hidden">
            <h2 className="label px-4 pt-4">Changed Symbols</h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-50">
                    <th className="th">Symbol</th>
                    <th className="th">Kind</th>
                    <th className="th">File</th>
                    <th className="th">Lines</th>
                    <th className="th">Changed Lines</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.changed_symbols.map((s) => (
                    <tr key={s.symbol_id} className="border-b border-stone-100 hover:bg-stone-50/50">
                      <td className="td font-mono text-xs font-semibold text-indigo-700">{s.symbol_name}</td>
                      <td className="td">
                        <span className="badge bg-stone-100 text-stone-600 text-xs">{s.symbol_kind}</span>
                      </td>
                      <td className="td max-w-56 truncate font-mono text-xs text-stone-500">{s.file_path}</td>
                      <td className="td text-xs text-stone-500">{s.start_line}–{s.end_line}</td>
                      <td className="td font-mono text-xs">
                        {s.changed_lines.slice(0, 5).join(', ')}
                        {s.changed_lines.length > 5 && '…'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Affected Files (1-hop fan-in) */}
          <div className="card overflow-hidden">
            <h2 className="label px-4 pt-4">Potentially Affected Files (1-hop fan-in)</h2>
            <p className="px-4 py-2 text-xs text-stone-500 border-b border-stone-100">
              Files that import the changed files. Review these for potential breakage.
            </p>
            {analysis.data.affected_files.length === 0 ? (
              <p className="p-4 text-sm text-stone-400">No affected files detected.</p>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-50">
                    <th className="th">Affected File</th>
                    <th className="th">Reason</th>
                    <th className="th">Via Symbol/File</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.affected_files.map((af, i) => (
                    <tr key={i} className="border-b border-stone-100 hover:bg-stone-50/50">
                      <td className="td max-w-80 truncate font-mono text-xs">{af.file_path}</td>
                      <td className="td">
                        <span className="badge bg-indigo-100 text-indigo-700 text-xs">{af.reason}</span>
                      </td>
                      <td className="td max-w-56 truncate font-mono text-xs text-stone-500">{af.via_symbol}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Recommended Test Files */}
          <div className="card overflow-hidden">
            <h2 className="label px-4 pt-4">Recommended Test Files</h2>
            <p className="px-4 py-2 text-xs text-stone-500 border-b border-stone-100">
              Heuristically identified test files related to changed/affected code.
            </p>
            {analysis.data.test_files.length === 0 ? (
              <p className="p-4 text-sm text-stone-400">No test files found.</p>
            ) : (
              <ul className="divide-y divide-stone-100">
                {analysis.data.test_files.map((tf, i) => (
                  <li key={i} className="px-4 py-2 flex items-center gap-3">
                    <span className="w-5 h-5 rounded bg-emerald-100 flex items-center justify-center">
                      <svg className="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </span>
                    <span className="font-mono text-xs text-stone-700">{tf}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Navigation */}
          <div className="flex gap-2">
            <Link to={`/repos/${repoId}`} className="btn btn-outline">
              Back to Repository
            </Link>
          </div>
        </>
      ) : (
        <p className="text-sm text-stone-400">
          No analysis data available. Click "Run Analysis" to analyze this PR.
        </p>
      )}
    </div>
  )
}