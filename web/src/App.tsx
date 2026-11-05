import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import Landing from './pages/Landing'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import ProjectWorkspace from './pages/ProjectWorkspace'
import { useAuth } from './lib/auth'

function Protected({ children }: { children: React.ReactNode }) {
  const token = useAuth(s => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return <Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<Auth mode="login" />} />
    <Route path="/register" element={<Auth mode="register" />} />
    <Route path="/app" element={<Protected><Shell /></Protected>}>
      <Route index element={<Dashboard />} />
      <Route path="projects" element={<Dashboard />} />
      <Route path="projects/:id" element={<ProjectWorkspace />} />
      <Route path="projects/:id/mappings/:mappingId" element={<ProjectWorkspace />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}
