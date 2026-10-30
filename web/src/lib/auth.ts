import { create } from 'zustand'
import type { TokenResponse, User } from './api'

type AuthStore = {
  token: string | null
  user: User | null
  login: (data: TokenResponse) => void
  logout: () => void
}

function storedUser(): User | null {
  try { const value = sessionStorage.getItem('migrapilot_user'); return value ? JSON.parse(value) as User : null }
  catch { return null }
}

export const useAuth = create<AuthStore>(set => ({
  token: sessionStorage.getItem('migrapilot_token'),
  user: storedUser(),
  login(data) {
    sessionStorage.setItem('migrapilot_token', data.access_token)
    sessionStorage.setItem('migrapilot_user', JSON.stringify(data.user))
    set({ token: data.access_token, user: data.user })
  },
  logout() {
    sessionStorage.removeItem('migrapilot_token')
    sessionStorage.removeItem('migrapilot_user')
    set({ token: null, user: null })
  },
}))
