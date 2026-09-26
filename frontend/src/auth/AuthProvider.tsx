/** Auth provider: the source of truth is the Supabase JWT in localStorage. */

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { clearToken, getToken, setToken } from '../api/client'
import { AuthContext } from './context'

function decodeEmail(token: string): string | null {
  try {
    const payload: { email?: string; sub?: string } = JSON.parse(
      atob(token.split('.')[1] ?? ''),
    )
    return payload.email ?? payload.sub ?? null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())

  useEffect(() => {
    const onUnauthorized = () => setTokenState(null)
    window.addEventListener('ai-sip:unauthorized', onUnauthorized)
    return () => window.removeEventListener('ai-sip:unauthorized', onUnauthorized)
  }, [])

  const loginWithToken = useCallback((next: string) => {
    setToken(next)
    setTokenState(next)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
  }, [])

  const value = useMemo(
    () => ({
      token,
      email: token ? decodeEmail(token) : null,
      isAuthed: token !== null,
      loginWithToken,
      logout,
    }),
    [token, loginWithToken, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}