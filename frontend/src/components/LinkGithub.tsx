/** "Link GitHub" button: opens the Step-3 OAuth flow in a popup, then polls
 *  /auth/github/status until the account shows as linked. */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getApiBase, getGithubStatus } from '../api/client'
import { useAuth } from '../auth/context'

export default function LinkGithub() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [polling, setPolling] = useState(false)

  const { data: status } = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
    refetchInterval: polling ? 1500 : false,
  })

  const handleLink = () => {
    if (!token) return
    const url = `${getApiBase()}/auth/github/login?state=${encodeURIComponent(token)}`
    window.open(url, '_blank', 'noopener,noreferrer,width=900,height=700')
    setPolling(true)
    // Stop polling once the OAuth tab completes and the status flips.
    queryClient.invalidateQueries({ queryKey: ['github-status'] })
  }

  const cancelPolling = () => setPolling(false)

  if (status?.linked) {
    return (
      <span className="badge bg-emerald-100 text-emerald-700">
        GitHub linked as {status.github_login}
      </span>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <button type="button" className="btn btn-primary" onClick={handleLink}>
        Link GitHub
      </button>
      {polling ? (
        <button
          type="button"
          className="btn btn-ghost"
          onClick={cancelPolling}
        >
          Cancel
        </button>
      ) : null}
      {status && !status.linked ? (
        <span className="text-xs text-slate-500">
          Not linked yet — completing the GitHub OAuth flow in the new tab
          stores your access token for repo attachment.
        </span>
      ) : null}
      {polling ? (
        <span className="animate-pulse text-xs text-indigo-600">
          Waiting for GitHub auth to complete…
        </span>
      ) : null}
    </div>
  )
}