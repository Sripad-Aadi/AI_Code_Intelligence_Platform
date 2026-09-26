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
  const [notice, setNotice] = useState<string | null>(null)
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
    setNotice(null)

    if (mode === 'signin') {
      const { data, error: authError } =
        await supabase.auth.signInWithPassword({ email, password })
      setBusy(false)
      if (authError) {
        setError(
          authError.message === 'Invalid login credentials'
            ? 'Incorrect email or password. If you signed up earlier, use the same password — or create an account below.'
            : authError.message,
        )
        return
      }
      if (!data.session) {
        setError('Sign-in failed — no session returned. Please try again.')
        return
      }
      loginWithToken(data.session.access_token)
      return
    }

    // Signup
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
    })
    setBusy(false)
    if (authError) {
      // Supabase reuses the same message for "already registered" and other
      // signup failures, so map the common case to a useful next action.
      const alreadyExists =
        /already|registered|exists/i.test(authError.message) ||
        authError.status === 422 ||
        authError.status === 400
      if (alreadyExists) {
        setMode('signin')
        setNotice(
          'An account with this email already exists — sign in with your password below.',
        )
        setError(null)
      } else {
        setError(authError.message)
      }
      return
    }
    if (data.session) {
      // Email confirmation disabled: session returned immediately.
      loginWithToken(data.session.access_token)
      return
    }
    // Confirmation email sent — the account exists now, so switch to login.
    setMode('signin')
    setNotice(
      'Account created. Check your email to confirm it, then sign in below.',
    )
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
          {mode === 'signin'
            ? 'Sign in to analyze your repositories.'
            : 'Create an account to analyze your repositories.'}
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
              placeholder="you@example.com"
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
              minLength={8}
              autoComplete={
                mode === 'signin' ? 'current-password' : 'new-password'
              }
              className="input"
              placeholder={
                mode === 'signin' ? 'Your password' : 'At least 8 characters'
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {notice ? (
            <p className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-700">
              {notice}
            </p>
          ) : null}
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

          <p className="text-center text-sm text-slate-500">
            {mode === 'signin' ? "Don't have an account?" : 'Have an account?'}{' '}
            <button
              type="button"
              className="text-indigo-600 hover:underline"
              onClick={() => {
                setMode(mode === 'signin' ? 'signup' : 'signin')
                setError(null)
                setNotice(null)
              }}
            >
              {mode === 'signin' ? 'Create one' : 'Sign in'}
            </button>
          </p>
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