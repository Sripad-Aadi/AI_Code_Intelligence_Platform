/** "Link GitHub" button: opens the Step-3 OAuth flow in a popup, then polls
 *  /auth/github/status until the account shows as linked. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getApiBase, getGithubStatus, unlinkGithub } from '../api/client'
import type { GithubStatus } from '../api/types'
import { useAuth } from '../auth/context'

export default function LinkGithub() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [polling, setPolling] = useState(false)

  const { data: status } = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
    // Poll while the OAuth flow runs, and stop as soon as status flips to
    // linked (function form reads the query's own state — no setState needed).
    refetchInterval: (query) => {
      const current = query.state.data as GithubStatus | undefined
      return polling && !current?.linked ? 1500 : false
    },
  })

  const unlink = useMutation({
    mutationFn: unlinkGithub,
    onSuccess: () => {
      setPolling(false)
      queryClient.invalidateQueries({ queryKey: ['github-status'] })
    },
  })

  const handleLink = () => {
    if (!token) return
    const url = `${getApiBase()}/auth/github/login?state=${encodeURIComponent(token)}`
    window.open(url, '_blank', 'noopener,noreferrer,width=900,height=700')
    setPolling(true)
    queryClient.invalidateQueries({ queryKey: ['github-status'] })
  }

  if (status?.linked) {
    return (
      <span className="flex items-center gap-2">
        <span className="badge bg-emerald-100 text-emerald-700">
          GitHub linked as {status.github_login}
        </span>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={unlink.isPending}
          onClick={() => {
            if (
              window.confirm(
                `Unlink GitHub (${status.github_login}) from this account?`,
              )
            ) {
              unlink.mutate()
            }
          }}
        >
          {unlink.isPending ? 'Unlinking…' : 'Unlink'}
        </button>
      </span>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <button type="button" className="btn btn-primary" onClick={handleLink}>
        Link GitHub
      </button>
      {polling ? (
        <>
          <span className="animate-pulse text-xs text-indigo-600">
            Waiting for you to authorize GitHub — it will pick this up
            automatically.
          </span>
          <button type="button" className="btn btn-ghost" onClick={() => setPolling(false)}>
            Cancel
          </button>
        </>
      ) : null}
    </div>
  )
}