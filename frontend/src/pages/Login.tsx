import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { usePageTitle } from '../hooks/usePageTitle'
import { supabase, supabaseConfigured } from '../lib/supabase'

type Mode = 'signin' | 'signup'

export default function Login() {
  const { isAuthed, loginWithToken } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()

  usePageTitle('Sign in')

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tokenInput, setTokenInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // One-shot: accept ?token=<supabase-jwt> from a URL (useful for demos).
  useEffect(() => {
    const t = params.get('token')
    if (!t) return
    params.delete('token')
    setParams(params, { replace: true })
    loginWithToken(t)
  }, [params, setParams, loginWithToken])

  if (isAuthed) return <Navigate to="/" replace />

  const handleAuth = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) {
      setError(
        'Supabase is not configured (set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env). Paste an access token below instead.',
      )
      return
    }
    setBusy(true)
    setError(null)
    const { data, error: authError } =
      mode === 'signin'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
    setBusy(false)

    if (authError) {
      setError(authError.message)
      return
    }
    if (!data.session) {
      setError('No session returned — confirm your email address first.')
      return
    }
    loginWithToken(data.session.access_token)
  }

  const handleToken = () => {
    const t = tokenInput.trim()
    if (!t) {
      setError('Paste an access token first.')
      return
    }
    loginWithToken(t)
    if (supabaseConfigured) navigate('/', { replace: true })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-xl font-bold text-slate-900">
          AI Software Intelligence
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Sign in to analyze your repositories.
        </p>

        <form onSubmit={handleAuth} className="mt-6 space-y-4">
          <div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete={
                mode === 'signin' ? 'current-password' : 'new-password'
              }
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error ? (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="btn btn-primary w-full justify-center"
            disabled={busy}
          >
            {busy
              ? 'Please wait…'
              : mode === 'signin'
                ? 'Sign in'
                : 'Create account'}
          </button>

          <button
            type="button"
            className="w-full text-center text-sm text-indigo-600 hover:underline"
            onClick={() => {
              setMode(mode === 'signin' ? 'signup' : 'signin')
              setError(null)
            }}
          >
            {mode === 'signin'
              ? 'Need an account? Sign up'
              : 'Have an account? Sign in'}
          </button>
        </form>

        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-slate-200" />
          <span className="text-xs uppercase tracking-wide text-slate-400">
            or use an access token
          </span>
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="space-y-2">
          <textarea
            className="input min-h-20 font-mono text-xs"
            placeholder="Paste a Supabase access token (JWT)…"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-outline w-full justify-center"
            onClick={handleToken}
          >
            Continue with token
          </button>
          <p className="text-xs text-slate-400">
            Tip: you can also open the app as{' '}
            <code className="rounded bg-slate-100 px-1">
              /login?token=&lt;jwt&gt;
            </code>{' '}
            to sign in in one step.
          </p>
        </div>
      </div>
    </div>
  )
}