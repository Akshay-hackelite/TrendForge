import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AuthPage() {
  const { login, register, token, user, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const isRegister = location.pathname === '/register'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && token && user) {
    const dest = user.active_client_id ? `/clients/${user.active_client_id}` : '/clients'
    return <Navigate to={dest} replace />
  }

  async function handleSignIn(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const me = await login(username.trim(), password)
      const dest = me?.active_client_id ? `/clients/${me.active_client_id}` : '/clients'
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err.message || 'Invalid username or password')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSignUp(e) {
    e.preventDefault()
    setError('')
    const name = username.trim()
    if (name.length < 2) {
      setError('Username must be at least 2 characters')
      return
    }
    if (password.length < 4) {
      setError('Password must be at least 4 characters')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    setSubmitting(true)
    try {
      const me = await register(name, password)
      const dest = me?.active_client_id ? `/clients/${me.active_client_id}` : '/clients'
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err.message || 'Could not create account')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="card login-box">
        <div className="logo">
          <h2>TrendForge</h2>
        </div>
        <p className="subtitle">
          {isRegister
            ? 'Create an account — username and password only'
            : 'Sign in to plan, publish, and track content'}
        </p>

        {isRegister ? (
          <form onSubmit={handleSignUp}>
            <div className="input-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                placeholder="Choose a username"
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="input-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                placeholder="At least 4 characters"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="input-group">
              <label htmlFor="confirm-password">Confirm password</label>
              <input
                id="confirm-password"
                type="password"
                placeholder="Repeat password"
                required
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            {error && <div className="auth-error">{error}</div>}
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSignIn}>
            <div className="input-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                placeholder="Username"
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="input-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                placeholder="Password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && <div className="auth-error">{error}</div>}
            <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}

        <p className="auth-switch">
          {isRegister ? (
            <>
              Already have an account?{' '}
              <Link to="/login" className="text-link" onClick={() => setError('')}>
                Sign in
              </Link>
            </>
          ) : (
            <>
              Don&apos;t have an account?{' '}
              <Link to="/register" className="text-link" onClick={() => setError('')}>
                Create one
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
