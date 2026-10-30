import axios from 'axios'

export type User = { id: number; email: string; role: 'admin' | 'engineer' | 'viewer'; created_at: string }
export type TokenResponse = { access_token: string; token_type: 'bearer'; user: User }
export type Project = { id: number; owner_id: number; name: string; source_system: string; target_system: string; created_at: string }
export type NewProject = { name: string; source_system: string; target_system: string }
export type Dashboard = {
  project: Project; total_mappings: number; parsed: number; converted: number; verified: number; failing: number;
  converted_percent: number; verified_percent: number; failing_percent: number;
}

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1', timeout: 20000 })
api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('migrapilot_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(item => item.msg ?? 'Invalid field').join('; ')
    return error.response ? `Request failed (${error.response.status})` : 'Cannot connect to API. Check that Docker services are running.'
  }
  return 'Something went wrong. Please try again.'
}
