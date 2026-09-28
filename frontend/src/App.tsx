import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/context'
import AppShell from './components/AppShell'
import AnalysisStatus from './pages/AnalysisStatus'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Findings from './pages/Findings'
import Linked from './pages/Linked'
import Login from './pages/Login'
import Observability from './pages/Observability'
import PRDashboard from './pages/PRDashboard'
import ProjectDetail from './pages/ProjectDetail'
import RepoExplorer from './pages/RepoExplorer'
import RiskTraining from './pages/RiskTraining'
import Search from './pages/Search'

const queryClient = new QueryClient()

function RequireAuth() {
  const { isAuthed } = useAuth()
  // Renders the matched child route, which is where <AppShell /> lives. This
  // guard used to render <AppShell /> itself, so every page was wrapped in
  // two shells and showed the navbar twice.
  return isAuthed ? <Outlet /> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/linked" element={<Linked />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<AppShell />}>
              <Route index element={<Dashboard />} />
              <Route path="projects/:projectId" element={<ProjectDetail />} />
              <Route path="jobs/:jobId" element={<AnalysisStatus />} />
              <Route path="repos/:repoId" element={<RepoExplorer />} />
              <Route path="repos/:repoId/chat" element={<Chat />} />
              <Route path="repos/:repoId/findings" element={<Findings />} />
              <Route path="repos/:repoId/prs/:prNumber" element={<PRDashboard />} />
              <Route path="search" element={<Search />} />
              <Route path="observability" element={<Observability />} />
              <Route path="risk-training" element={<RiskTraining />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  )
}