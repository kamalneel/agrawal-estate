import { useState, FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { Lock, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import styles from './Login.module.css'

export function Login() {
  const { isAuthenticated, login, error, isLoading } = useAuth()
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // If already authenticated, redirect to dashboard
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!password.trim() || isSubmitting) return

    setIsSubmitting(true)
    await login(password)
    setIsSubmitting(false)
  }

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <p>Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        {/* Logo */}
        <div className={styles.logo}>
          <img src="/Agrawal Family Trust Full size.png" alt="Agrawal Family Trust" className={styles.logoIcon} />
        </div>

        <h1 className={styles.title}>Estate Planner</h1>
        <p className={styles.subtitle}>Enter family password to continue</p>

        {/* Error Message */}
        {error && (
          <div className={styles.error}>
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <Lock size={20} className={styles.inputIcon} />
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Family Password"
              className={styles.input}
              autoFocus
              disabled={isSubmitting}
            />
            <button
              type="button"
              className={styles.togglePassword}
              onClick={() => setShowPassword(!showPassword)}
              tabIndex={-1}
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>

          <button
            type="submit"
            className={styles.submitButton}
            disabled={isSubmitting || !password.trim()}
          >
            {isSubmitting ? (
              <>
                <div className={styles.buttonSpinner} />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <p className={styles.footer}>
          Private family application
        </p>
      </div>
    </div>
  )
}

