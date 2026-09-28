import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { get, getToken, post, setToken } from './api'

export type Role = 'bd_manager' | 'bd_exec' | 'survey_manager' | 'survey_exec'
export interface User {
  id: number
  username: string
  name: string
  role: Role
  phone?: string
}

export const ROLE_LABEL: Record<Role, string> = {
  bd_manager: 'BD Manager',
  bd_exec: 'BD Executive',
  survey_manager: 'Survey Manager',
  survey_exec: 'Survey Executive',
}

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  switchTo: (id: number) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

const USER_KEY = 'sitescout.user'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const u = localStorage.getItem(USER_KEY)
      return u && getToken() ? JSON.parse(u) : null
    } catch {
      return null
    }
  })
  const [loading, setLoading] = useState(!!getToken())

  useEffect(() => {
    if (!getToken()) return setLoading(false)
    get<User>('/api/auth/me')
      .then(save)
      .catch((e) => {
        // offline: keep the cached user so field staff can keep working
        if (e?.status === 401) save(null)
      })
      .finally(() => setLoading(false))
  }, [])

  function save(u: User | null, token?: string) {
    if (token !== undefined) setToken(token)
    setUser(u)
    try {
      if (u) localStorage.setItem(USER_KEY, JSON.stringify(u))
      else localStorage.removeItem(USER_KEY)
    } catch {
      /* ignore */
    }
  }

  const value: AuthCtx = {
    user,
    loading,
    async login(username, password) {
      const r = await post<{ token: string; user: User }>('/api/auth/login', { username, password })
      save(r.user, r.token)
    },
    async switchTo(id) {
      const r = await post<{ token: string; user: User }>(`/api/auth/switch/${id}`)
      save(r.user, r.token)
    },
    logout() {
      save(null, null as unknown as string)
      setToken(null)
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
