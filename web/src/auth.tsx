import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken, type Me } from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (organization_name: string, email: string, password: string, display_name: string) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState>(null!)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!getToken()) { setLoading(false); return }
    api.get<Me>('/auth/me').then(setMe).catch(() => setToken(null)).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<Me & { token: string }>('/auth/login', { email, password })
    setToken(r.token)
    setMe({ organization: r.organization, user: r.user })
  }, [])

  const register = useCallback(async (organization_name: string, email: string, password: string, display_name: string) => {
    const r = await api.post<Me & { token: string }>('/auth/register-org', { organization_name, email, password, display_name })
    setToken(r.token)
    setMe({ organization: r.organization, user: r.user })
  }, [])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout') } catch { /* ignore */ }
    setToken(null)
    setMe(null)
  }, [])

  return <Ctx.Provider value={{ me, loading, login, register, logout }}>{children}</Ctx.Provider>
}

export function useAuth() { return useContext(Ctx) }

export const MANAGER_ROLES = ['org_admin', 'survey_manager']
export const TESTER_ROLES = ['org_admin', 'survey_manager', 'pt_tester']
