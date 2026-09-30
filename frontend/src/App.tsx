import { useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/context'
import { supabase } from './lib/supabase'
import AppShell from './components/AppShell'
import AnalysisStatus from './pages/AnalysisStatus'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Linked from './pages/Linked'
import Login from './pages/Login'
import Observability from './pages/Observability'
import PRDashboard from './pages/PRDashboard'
import Profile from './pages/Profile'
import ProjectDetail from './pages/ProjectDetail'
import RepoExplorer from './pages/RepoExplorer'
import Search from './pages/Search'

const queryClient = new QueryClient()

function OAuthCallback() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const sb = supabase
    if (!sb) {
      setError('Supabase is not configured.')
      return
    }
    const checkSession = async () => {
      await new Promise((r) => setTimeout(r, 1000))
      const { data } = await sb.auth.getSession()
      if (data.session) {
        localStorage.setItem('ai_sip_access_token', data.session.access_token)
        window.dispatchEvent(new Event('ai-sip:auth-changed'))
        // Store the GitHub token on the user row so GitHub features work
        if (data.session.provider_token) {
          try {
            await fetch(`${import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'}/auth/github/store-token`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${data.session.access_token}`,
              },
              body: JSON.stringify({ github_token: data.session.provider_token }),
            })
          } catch {
            // Non-fatal — GitHub features just won't work until re-linked
          }
        }
        navigate('/', { replace: true })
      } else {
        setError('Sign-in failed. Please try again.')
      }
    }
    checkSession()
  }, [navigate])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50">
        <div className="text-center">
          <p className="text-sm text-rose-600">{error}</p>
          <button className="btn btn-primary mt-4" onClick={() => navigate('/login', { replace: true })}>
            Back to sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />
        <p className="text-sm text-stone-500">Completing sign-in…</p>
      </div>
    </div>
  )
}

function Root() {
  const { isAuthed } = useAuth()
  if (isAuthed) {
    return <AppShell />
  }
  return <Landing />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Root />}>
            <Route index element={<Dashboard />} />
            <Route path="projects/:projectId" element={<ProjectDetail />} />
            <Route path="jobs/:jobId" element={<AnalysisStatus />} />
            <Route path="repos/:repoId" element={<RepoExplorer />} />
            <Route path="repos/:repoId/chat" element={<Chat />} />
            <Route path="repos/:repoId/prs/:prNumber" element={<PRDashboard />} />
            <Route path="search" element={<Search />} />
            <Route path="observability" element={<Observability />} />
            <Route path="profile" element={<Profile />} />
          </Route>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/github/callback" element={<OAuthCallback />} />
          <Route path="/linked" element={<Linked />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  )
}
