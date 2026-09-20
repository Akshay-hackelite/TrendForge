import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('jwt_token'))
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!localStorage.getItem('jwt_token'))

  const logout = useCallback(() => {
    localStorage.removeItem('jwt_token')
    setToken(null)
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    if (!token) {
      setUser(null)
      setLoading(false)
      return null
    }
    try {
      const me = await api.me(token)
      setUser(me)
      return me
    } catch {
      logout()
      return null
    } finally {
      setLoading(false)
    }
  }, [token, logout])

  useEffect(() => {
    refreshUser()
  }, [refreshUser])

  const establishSession = useCallback(async (accessToken) => {
    localStorage.setItem('jwt_token', accessToken)
    setToken(accessToken)
    setLoading(true)
    try {
      const me = await api.me(accessToken)
      setUser(me)
      return me
    } catch {
      localStorage.removeItem('jwt_token')
      setToken(null)
      setUser(null)
      throw new Error('Failed to load user profile')
    } finally {
      setLoading(false)
    }
  }, [])

  const login = useCallback(
    async (username, password) => {
      const data = await api.login(username, password)
      return establishSession(data.access_token)
    },
    [establishSession],
  )

  const register = useCallback(
    async (username, password) => {
      await api.register(username, password)
      const data = await api.login(username, password)
      return establishSession(data.access_token)
    },
    [establishSession],
  )

  const patchUser = useCallback((patch) => {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev))
  }, [])

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      login,
      register,
      logout,
      refreshUser,
      patchUser,
      activeClientId: user?.active_client_id ?? null,
      activeChannelId: user?.active_channel_id ?? null,
    }),
    [token, user, loading, login, register, logout, refreshUser, patchUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
