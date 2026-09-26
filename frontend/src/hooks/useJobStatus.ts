/** React Query hook that polls a job's status every 2s until it finishes. */

import { useQuery } from '@tanstack/react-query'
import { getJob } from '../api/client'
import type { AnalysisJob, JobStatus } from '../api/types'

const FINAL_STATUSES: JobStatus[] = ['completed', 'failed']

/** True while a job can still transition (plan says poll while running). */
export const isJobRunning = (status: string | undefined): boolean =>
  status === 'queued' || status === 'running'

export function useJobStatus(jobId: string | undefined) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && FINAL_STATUSES.includes(status) ? false : 2000
    },
  })
}

export function statusStyle(status: AnalysisJob['status']): string {
  switch (status) {
    case 'queued':
      return 'bg-amber-100 text-amber-700'
    case 'running':
      return 'bg-indigo-100 text-indigo-700'
    case 'completed':
      return 'bg-emerald-100 text-emerald-700'
    case 'failed':
      return 'bg-rose-100 text-rose-700'
    default:
      return 'bg-slate-100 text-slate-600'
  }
}