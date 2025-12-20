import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from 'react'

interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  login: (password: string) => Promise<boolean>
  logout: () => void
  error: string | null
}

const AuthContext = createContext<AuthContextType | null>(null)

const TOKEN_KEY = 'agrawal_auth_token'
const TOKEN_EXPIRY_KEY = 'agrawal_auth_expiry'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Check for existing token on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem(TOKEN_KEY)
      const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY)

      if (token && expiry) {
        const expiryDate = new Date(parseInt(expiry, 10) * 1000)
        if (expiryDate > new Date()) {
          // Token exists and not expired, verify with server
          try {
            const response = await fetch('/api/v1/auth/verify', {
              headers: {
                Authorization: `Bearer ${token}`,
              },
            })
            if (response.ok) {
              setIsAuthenticated(true)
            } else {
              // Token invalid, clear it
              localStorage.removeItem(TOKEN_KEY)
              localStorage.removeItem(TOKEN_EXPIRY_KEY)
            }
          } catch {
            // Server not reachable, but token looks valid
            // Allow offline access
            setIsAuthenticated(true)
          }
        } else {
          // Token expired, clear it
          localStorage.removeItem(TOKEN_KEY)
          localStorage.removeItem(TOKEN_EXPIRY_KEY)
        }
      }
      setIsLoading(false)
    }

    checkAuth()
  }, [])

  const login = useCallback(async (password: string): Promise<boolean> => {
    setError(null)
    setIsLoading(true)

    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ password }),
      })

      if (response.ok) {
        const data = await response.json()
        localStorage.setItem(TOKEN_KEY, data.access_token)
        
        // Calculate expiry timestamp
        const expiryTimestamp = Math.floor(Date.now() / 1000) + data.expires_in
        localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTimestamp.toString())
        
        setIsAuthenticated(true)
        setIsLoading(false)
        return true
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Invalid password')
        setIsLoading(false)
        return false
      }
    } catch (err) {
      setError('Unable to connect to server')
      setIsLoading(false)
      return false
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(TOKEN_EXPIRY_KEY)
    setIsAuthenticated(false)
    
    // Optionally notify server
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }).catch(() => {
        // Ignore errors on logout
      })
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        login,
        logout,
        error,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

// Helper to get the auth token for API calls
export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

// Helper to create auth headers
export function getAuthHeaders(): HeadersInit {
  const token = getAuthToken()
  if (token) {
    return {
      Authorization: `Bearer ${token}`,
    }
  }
  return {}
}















