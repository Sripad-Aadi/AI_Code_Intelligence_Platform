import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getGithubStatus, unlinkGithub } from '../api/client'
import { useAuth } from '../auth/context'
import { usePageTitle } from '../hooks/usePageTitle'
import { supabase } from '../lib/supabase'
import { getApiBase } from '../api/client'

export default function Profile() {
  const { email, logout, token } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [polling, setPolling] = useState(false)
  usePageTitle('Profile')

  const { data: gh } = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
    refetchInterval: (query) => {
      const current = query.state.data as { linked?: boolean } | undefined
      return polling && !current?.linked ? 1500 : false
    },
  })

  const handleLink = () => {
    if (!token) return
    const url = `${getApiBase()}/auth/github/login?state=${encodeURIComponent(token)}`
    window.open(url, '_blank', 'noopener,noreferrer,width=900,height=700')
    setPolling(true)
    queryClient.invalidateQueries({ queryKey: ['github-status'] })
  }

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!supabase) return

    if (newPassword !== confirmPassword) {
      setMessage({ type: 'error', text: 'New passwords do not match.' })
      return
    }
    if (newPassword.length < 8) {
      setMessage({ type: 'error', text: 'Password must be at least 8 characters.' })
      return
    }

    setBusy(true)
    setMessage(null)

    try {
      const { error } = await supabase.auth.updateUser({ password: newPassword })
      if (error) {
        setMessage({ type: 'error', text: error.message })
      } else {
        setMessage({ type: 'success', text: 'Password updated successfully.' })
        setNewPassword('')
        setConfirmPassword('')
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to update password. Please try again.' })
    } finally {
      setBusy(false)
    }
  }

  const handleUnlinkGithub = async () => {
    if (!window.confirm('Unlink GitHub? You will need to re-link it to attach repositories.')) return
    try {
      await unlinkGithub()
      setMessage({ type: 'success', text: 'GitHub unlinked.' })
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to unlink GitHub.' })
    }
  }

  const handleSignOut = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-stone-900">Profile</h1>
        <p className="mt-1 text-sm text-stone-500">Manage your account settings.</p>
      </div>

      {/* Account info */}
      <div className="card-flat p-6">
        <h2 className="label">Account</h2>
        <div className="mt-4 flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-100 text-lg font-bold text-teal-700">
            {email?.charAt(0).toUpperCase() ?? '?'}
          </div>
          <div>
            <p className="text-base font-semibold text-stone-900">{email?.split('@')[0] ?? 'User'}</p>
            <p className="text-sm text-stone-500">{email}</p>
          </div>
        </div>
      </div>

      {/* GitHub connection */}
      <div className="card-flat p-6">
        <h2 className="label">GitHub Connection</h2>
        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-stone-900 text-white">
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-stone-900">
                {gh?.linked ? (gh.github_login ? `Connected as ${gh.github_login}` : 'Connected') : 'Not connected'}
              </p>
              <p className="text-xs text-stone-500">
                {gh?.linked ? 'Your GitHub account is linked' : 'Link GitHub to attach repositories'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {polling ? (
              <>
                <span className="animate-pulse text-xs text-indigo-600">
                  Waiting for you to authorize GitHub…
                </span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPolling(false)}>
                  Cancel
                </button>
              </>
            ) : null}
            {gh?.linked ? (
              <button type="button" className="btn btn-outline btn-sm" onClick={handleUnlinkGithub}>
                Unlink
              </button>
            ) : (
              <button type="button" className="btn btn-primary btn-sm" onClick={handleLink}>
                Link GitHub
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card-flat p-6">
        <h2 className="label">Change Password</h2>
        <p className="mt-1 text-sm text-stone-500">
          Set a password to enable email/password login in addition to GitHub OAuth.
        </p>
        <form onSubmit={handleChangePassword} className="mt-4 space-y-4">
          <div>
            <label className="label" htmlFor="new-password">New password</label>
            <input
              id="new-password"
              type="password"
              required
              minLength={8}
              className="input"
              placeholder="At least 8 characters"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              type="password"
              required
              minLength={8}
              className="input"
              placeholder="Re-enter password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>

          {message ? (
            <div className={`rounded-lg px-4 py-3 text-sm ${
              message.type === 'success' ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'
            }`}>
              {message.text}
            </div>
          ) : null}

          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Updating…' : 'Update password'}
          </button>
        </form>
      </div>

      {/* Sign out */}
      <div className="card-flat p-6">
        <h2 className="label">Session</h2>
        <div className="mt-4">
          <button type="button" className="btn btn-outline" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}
