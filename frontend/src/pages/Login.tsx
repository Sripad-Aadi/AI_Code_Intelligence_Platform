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

  const [mode, setMode] = useState<Mode>(params.get('mode') === 'signup' ? 'signup' : 'signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const t = params.get('token')
    if (!t) return
    params.delete('token')
    setParams(params, { replace: true })
    loginWithToken(t)
  }, [params, setParams, loginWithToken])

  if (isAuthed) return <Navigate to="/" replace />

  const handleGithubLogin = async () => {
    if (!supabase) return
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: {
        redirectTo: `${window.location.origin}/auth/github/callback`,
      },
    })
    if (error) {
      setError(error.message)
    }
  }

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

      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
      })
      if (authError) {
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
        loginWithToken(data.session.access_token)
        return
      }

      const looksExisting = data.user == null
      const probe = await supabase.auth.signInWithPassword({ email, password })
      if (probe.data.session) {
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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-stone-50 via-teal-50/30 to-stone-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-teal-600 text-white shadow-lg">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-stone-900">
            AI Software Intelligence
          </h1>
          <p className="mt-2 text-sm text-stone-500">
            {mode === 'signin'
              ? 'Sign in to access your projects and analyses.'
              : 'Create your account to start analyzing repositories.'}
          </p>
        </div>

        <div className="card p-8">
          <h2 className="text-lg font-semibold text-stone-900">
            {mode === 'signin' ? 'Welcome back' : 'Create your account'}
          </h2>
          <p className="mt-1 text-sm text-stone-500">
            {mode === 'signin'
              ? 'Sign in with your email and password.'
              : 'Sign up with your email and password.'}
          </p>

          <form onSubmit={handleAuth} className="mt-6 space-y-4">
            <div>
              <label className="label" htmlFor="email">Email</label>
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
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                className="input"
                placeholder={mode === 'signin' ? 'Your password' : 'At least 8 characters'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {notice ? (
              <div className="rounded-lg bg-teal-50 px-4 py-3 text-sm text-teal-800">
                {notice}
              </div>
            ) : null}
            {error ? (
              <div className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-800">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              className="btn btn-primary w-full justify-center"
              disabled={busy}
            >
              {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
            </button>

            <p className="text-center text-sm text-stone-500">
              {mode === 'signin' ? "Don't have an account?" : 'Have an account?'}{' '}
              <button
                type="button"
                className="font-medium text-teal-600 hover:text-teal-700 hover:underline"
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
            <div className="flex-1 border-t border-stone-200" />
            <span className="text-xs text-stone-400">or</span>
            <div className="flex-1 border-t border-stone-200" />
          </div>

          <button
            type="button"
            className="btn btn-outline w-full justify-center"
            onClick={handleGithubLogin}
            disabled={busy}
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
            Continue with GitHub
          </button>
        </div>

        <p className="mt-6 text-center text-xs text-stone-400">
          Secure authentication powered by Supabase
        </p>
      </div>
    </div>
  )
}
