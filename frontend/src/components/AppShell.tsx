import { useQuery } from '@tanstack/react-query'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getGithubStatus } from '../api/client'
import { useAuth } from '../auth/context'

export default function AppShell() {
  const { email, logout } = useAuth()
  const navigate = useNavigate()
  const { data: gh } = useQuery({
    queryKey: ['github-status'],
    queryFn: getGithubStatus,
    refetchInterval: 30_000,
  })

  const handleSignOut = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
          <Link
            to="/"
            className="text-sm font-bold tracking-tight text-slate-900"
          >
            AI Software Intelligence
          </Link>
          <nav className="flex gap-1">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                isActive ? 'nav-link-active' : 'nav-link'
              }
            >
              Projects
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {gh?.linked ? (
              <span className="badge bg-emerald-100 text-emerald-700">
                GitHub: {gh.github_login}
              </span>
            ) : gh ? (
              <span className="badge bg-amber-100 text-amber-700">
                GitHub not linked
              </span>
            ) : null}
            <span className="hidden text-slate-500 sm:inline">{email}</span>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleSignOut}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}