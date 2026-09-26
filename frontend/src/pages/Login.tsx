import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { usePageTitle } from '../hooks/usePageTitle'
import { supabase } from '../lib/supabase'

type Mode = 'signin' | 'signup'

export default function Login() {
  const { isAuthed, loginWithToken } = useAuth()
  const [params, setParams] = useSearchParams()

  usePageTitle('Sign in')

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // One-shot: accept ?token=<supabase-jwt> from a URL. Undocumented in the UI
  // on purpose (email/password is the only way in for a human) but kept for
  // scripted/E2E sign-in, where minting a JWT is easier than typing a password.
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
        'Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env and restart the dev server.',
      )
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)

    try {
      if (mode === 'signin') {
        const { data, error: authError } =
          await supabase.auth.signInWithPassword({ email, password })
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
      if (authError) {
        // Only a genuine duplicate maps to "already exists". A blanket
        // status check is wrong: 400 also covers email_address_invalid, and
        // 429 is the email-send rate limit.
        const code = (authError as { code?: string }).code ?? ''
        const alreadyExists =
          code === 'email_exists' ||
          /already (been )?registered|already exists/i.test(authError.message)
        if (alreadyExists) {
          setMode('signin')
          setNotice(
            'An account with this email already exists — sign in with your password below.',
          )
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

      // No error *and* no session is ambiguous: Supabase is enumeration-safe
      // and answers an already-registered email with HTTP 200 + a null user,
      // which looks just like a new account awaiting confirmation. Verified
      // against this project: an existing email returns user === null and
      // sends no mail, while a new signup returns the created user.
      const looksExisting = data.user == null

      const probe = await supabase.auth.signInWithPassword({ email, password })
      if (probe.data.session) {
        // The account already existed and the password matches — just log in.
        setNotice('That account already exists — signed you in.')
        loginWithToken(probe.data.session.access_token)
        return
      }
      if (/not confirmed/i.test(probe.error?.message ?? '')) {
        setMode('signin')
        setNotice(
          'That account already exists but is not confirmed yet. Check your email to confirm it, then sign in.',
        )
        return
      }
      setMode('signin')
      setNotice(
        looksExisting
          ? 'An account with this email already exists — sign in with your password below.'
          : 'Account created. Check your email to confirm it, then sign in below.',
      )
    } finally {
      setBusy(false)
    }
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
      </div>
    </div>
  )
}