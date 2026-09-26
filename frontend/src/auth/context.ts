/** Auth context object + hook (kept in a plain module so the provider file
 *  only exports its component, satisfying react-refresh/only-export-components). */

import { createContext, useContext } from 'react'

export interface AuthState {
  token: string | null
  email: string | null
  isAuthed: boolean
  loginWithToken: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export const useAuth = (): AuthState => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}