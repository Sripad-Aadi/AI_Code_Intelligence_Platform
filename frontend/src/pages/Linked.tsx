/** OAuth completion page — the GitHub callback 302s the popup here so it
 *  never lands on a code-bearing URL (which refresh/retry would replay). */

import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { usePageTitle } from '../hooks/usePageTitle'

export default function Linked() {
  const [params] = useSearchParams()
  const login = params.get('login')
  const error = params.get('error')

  usePageTitle('GitHub linking')

  useEffect(() => {
    // This page is normally opened as a popup — close it automatically.
    const handle = window.setTimeout(() => window.close(), 1800)
    return () => window.clearTimeout(handle)
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="card w-full max-w-md p-8 text-center">
        {error ? (
          <>
            <h1 className="text-lg font-bold text-rose-700">
              GitHub linking failed
            </h1>
            <p className="mt-2 break-all font-mono text-xs text-slate-600">
              {error}
            </p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-bold text-emerald-700">
              GitHub linked
            </h1>
            {login ? (
              <p className="mt-2 text-sm text-slate-600">
                Signed in as <span className="font-semibold">{login}</span>.
                Your repositories are now available to attach.
              </p>
            ) : null}
          </>
        )}
        <p className="mt-4 text-xs text-slate-400">
          This window closes automatically. If it stays open, close it and go
          back to the app — the link is already saved.
        </p>
        <Link to="/" className="btn btn-primary mt-4 w-full justify-center">
          Go to dashboard
        </Link>
      </div>
    </div>
  )
}