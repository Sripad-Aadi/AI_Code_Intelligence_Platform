import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/context'
import AppShell from './components/AppShell'
import AnalysisStatus from './pages/AnalysisStatus'
import Dashboard from './pages/Dashboard'
import Linked from './pages/Linked'
import Login from './pages/Login'
import ProjectDetail from './pages/ProjectDetail'
import RepoExplorer from './pages/RepoExplorer'

const queryClient = new QueryClient()

function RequireAuth() {
  const { isAuthed } = useAuth()
  return isAuthed ? <AppShell /> : <Navigate to="/login" replace />
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
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  )
}