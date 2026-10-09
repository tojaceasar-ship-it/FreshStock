import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { api } from '../lib/api'

interface User {
  id: number
  email: string
  username: string
  full_name: string
  role: string
  is_active: boolean
}

interface AuthContextType {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      api.get('/auth/me')
        .then(res => setUser(res.data))
        .catch((err) => {
          console.error('Auth me failed:', err)
          // Don't remove tokens immediately, try refresh via interceptor
          // Only remove if refresh also fails
          if (err.response?.status === 401) {
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
          }
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (username: string, password: string) => {
    try {
      const res = await api.post('/auth/login', { username, password })
      console.log('Login response:', res.data)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      
      // Try to get user profile, but if it fails, create minimal user from token
      try {
        const me = await api.get('/auth/me')
        setUser(me.data)
      } catch (meErr: any) {
        console.error('Failed to get /auth/me after login, using token payload:', meErr)
        // Decode token payload to get basic user info
        try {
          const payload = JSON.parse(atob(res.data.access_token.split('.')[1]))
          // Fallback user - will be replaced on next /auth/me call
          setUser({
            id: parseInt(payload.sub),
            email: username.includes('@') ? username : `${username}@freshstock.pl`,
            username: username,
            full_name: username,
            role: payload.role || 'OWNER',
            is_active: true
          })
          // Try again after small delay
          setTimeout(async () => {
            try {
              const meRetry = await api.get('/auth/me')
              setUser(meRetry.data)
            } catch {
              // Profil zostanie ponownie pobrany przy następnym odświeżeniu sesji.
            }
          }, 500)
        } catch {
          throw meErr
        }
      }
    } catch (err) {
      // Clean up on failure
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      throw err
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

// Provider i hook celowo dzielą ten sam prywatny kontekst.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
