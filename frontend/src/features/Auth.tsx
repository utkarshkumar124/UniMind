import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  KeyRound,
  Mail,
  User,
  Hash,
} from 'lucide-react'
import { authService } from '../services/auth'

type AuthMode = 'signin' | 'register' | 'forgot'

export default function Auth() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const initialMode = (searchParams.get('mode') as AuthMode) || 'signin'
  const [mode, setMode] = useState<AuthMode>(
    ['signin', 'register', 'forgot'].includes(initialMode) ? initialMode : 'signin'
  )

  const [fullName, setFullName] = useState('')
  const [registrationNo, setRegistrationNo] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  // Forgot password state
  const [forgotStep, setForgotStep] = useState<'email' | 'reset'>('email')
  const [resetCode, setResetCode] = useState('')
  const [devResetCode, setDevResetCode] = useState<string | null>(null)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    const paramMode = searchParams.get('mode') as AuthMode | null
    if (paramMode && ['signin', 'register', 'forgot'].includes(paramMode) && paramMode !== mode) {
      setMode(paramMode)
    }
  }, [searchParams])

  const switchMode = (next: AuthMode) => {
    setMode(next)
    setSearchParams({ mode: next }, { replace: true })
    setError(null)
    setNotice(null)
    setPassword('')
    setConfirmPassword('')
    if (next === 'forgot') {
      setForgotStep('email')
      setResetCode('')
      setDevResetCode(null)
    }
  }

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (!email.trim() || !password) {
      setError('Please enter your email and password.')
      return
    }
    setBusy(true)
    try {
      await authService.login(email.trim(), password)
      navigate('/')
    } catch (err: any) {
      setError(err?.message || 'Sign in failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (fullName.trim().length < 2) {
      setError('Please enter your full name.')
      return
    }
    if (!email.trim() || !email.includes('@')) {
      setError('Please enter a valid email address.')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters long.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await authService.register({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
        registrationNo: registrationNo.trim(),
      })
      navigate('/')
    } catch (err: any) {
      setError(err?.message || 'Registration failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (!email.trim() || !email.includes('@')) {
      setError('Please enter the email associated with your account.')
      return
    }
    setBusy(true)
    try {
      const res = await authService.requestPasswordReset(email.trim())
      setDevResetCode(res.devResetCode || null)
      setNotice(res.message)
      setForgotStep('reset')
    } catch (err: any) {
      setError(err?.message || 'Could not start password reset.')
    } finally {
      setBusy(false)
    }
  }

  const handleCompleteReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (!resetCode.trim()) {
      setError('Please enter your 6-digit verification code.')
      return
    }
    if (password.length < 6) {
      setError('New password must be at least 6 characters long.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const msg = await authService.resetPassword({
        email: email.trim(),
        resetCode: resetCode.trim(),
        newPassword: password,
      })
      setMode('signin')
      setSearchParams({ mode: 'signin' }, { replace: true })
      setPassword('')
      setConfirmPassword('')
      setResetCode('')
      setDevResetCode(null)
      setForgotStep('email')
      setNotice(msg)
    } catch (err: any) {
      setError(err?.message || 'Password reset failed.')
    } finally {
      setBusy(false)
    }
  }

  const titleText =
    mode === 'signin'
      ? 'Welcome back'
      : mode === 'register'
      ? 'Create your account'
      : 'Reset your password'

  const subtitleText =
    mode === 'signin'
      ? 'Sign in to sync your student profile across UniMind.'
      : mode === 'register'
      ? 'Register with your student email to personalize your UniMind assistant.'
      : forgotStep === 'email'
      ? 'Enter your registered email to receive a 6-digit reset verification code.'
      : 'Enter the verification code and choose a new password.'

  return (
    <div className="relative flex-1 overflow-y-auto px-4 py-8 flex flex-col justify-center items-center refero-enter">
      {/* Ambient Monochrome Liquid Refraction Backdrop */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true">
        <div
          className="liquid-orb w-[340px] h-[340px] -top-10 left-[28%] opacity-35"
          style={{ background: 'radial-gradient(circle, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.04) 65%, transparent 100%)' }}
        />
        <div
          className="liquid-orb liquid-orb-delayed w-[380px] h-[380px] bottom-[-40px] right-[22%] opacity-30"
          style={{ background: 'radial-gradient(circle, rgba(212,212,216,0.18) 0%, rgba(255,255,255,0.03) 65%, transparent 100%)' }}
        />
      </div>

      <div className="relative z-10 w-full max-w-[430px] space-y-5">
        {/* Back button pill */}
        <button
          type="button"
          onClick={() => navigate('/')}
          className="ios-glass-chip inline-flex items-center gap-1.5 text-[13px] font-medium text-ink2 hover:text-ink px-3.5 py-1.5 rounded-full transition-colors"
        >
          <ArrowLeft size={14} />
          <span>Back to UniMind</span>
        </button>

        {/* Main Liquid Glass Auth Card */}
        <div className="liquid-glass-card rounded-[28px] p-6 sm:p-8 space-y-5 overflow-hidden">
          {/* Header */}
          <div className="relative z-10 space-y-2 text-center">
            <div className="ios-glass-chip inline-grid place-items-center w-11 h-11 rounded-full border border-white/25 text-brand font-bold text-base mx-auto">
              U
            </div>
            <h1 className="font-hero text-[34px] leading-[1.1] font-normal text-ink">
              {titleText}
            </h1>
            <p className="text-[13.5px] text-ink2 leading-relaxed">{subtitleText}</p>
          </div>

          {/* Mode Tabs (Liquid Glass Segmented Pill) */}
          {mode !== 'forgot' && (
            <div className="relative z-10 grid grid-cols-2 p-1 rounded-full bg-black/35 border border-white/10 backdrop-blur-md">
              <button
                type="button"
                onClick={() => switchMode('signin')}
                className={`h-9 rounded-full text-[13.5px] font-medium transition-all ${
                  mode === 'signin'
                    ? 'ios-glass-chip text-ink'
                    : 'text-ink2 hover:text-ink'
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => switchMode('register')}
                className={`h-9 rounded-full text-[13.5px] font-medium transition-all ${
                  mode === 'register'
                    ? 'ios-glass-chip text-ink'
                    : 'text-ink2 hover:text-ink'
                }`}
              >
                Register
              </button>
            </div>
          )}

          {/* Error / Notice Banners */}
          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-error/40 bg-error/10 px-3.5 py-2.5 text-[13px] text-error">
              <AlertCircle size={15} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {notice && (
            <div className="flex items-start gap-2 rounded-xl border border-accent/40 bg-accent-tint px-3.5 py-2.5 text-[13px] text-accent">
              <CheckCircle2 size={15} className="shrink-0 mt-0.5" />
              <span>{notice}</span>
            </div>
          )}

          {/* Sign In Form */}
          {mode === 'signin' && (
            <form onSubmit={handleSignIn} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="auth-email" className="block text-[12.5px] font-medium text-ink2">
                  Email address
                </label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="auth-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@lpu.in"
                    className="input !pl-10"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="auth-password" className="block text-[12.5px] font-medium text-ink2">
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => switchMode('forgot')}
                    className="text-[12px] font-medium text-accent hover:underline"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="auth-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="input !pl-10 !pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink3 hover:text-ink transition-colors"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary w-full h-11 rounded-full text-[14.5px] font-semibold mt-1"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          )}

          {/* Register Form */}
          {mode === 'register' && (
            <form onSubmit={handleRegister} className="space-y-3.5">
              <div className="space-y-1.5">
                <label htmlFor="reg-name" className="block text-[12.5px] font-medium text-ink2">
                  Full name
                </label>
                <div className="relative">
                  <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="reg-name"
                    type="text"
                    autoComplete="name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g., Aarav Sharma"
                    className="input !pl-10"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reg-email" className="block text-[12.5px] font-medium text-ink2">
                  Email address
                </label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="reg-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@lpu.in"
                    className="input !pl-10"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reg-id" className="block text-[12.5px] font-medium text-ink2">
                  LPU Registration No. <span className="text-ink3 font-normal">(optional)</span>
                </label>
                <div className="relative">
                  <Hash size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="reg-id"
                    type="text"
                    value={registrationNo}
                    onChange={(e) => setRegistrationNo(e.target.value)}
                    placeholder="e.g., 12304567"
                    className="input !pl-10"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reg-password" className="block text-[12.5px] font-medium text-ink2">
                  Password <span className="text-ink3 font-normal">(min 6 chars)</span>
                </label>
                <div className="relative">
                  <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="reg-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Create a password"
                    className="input !pl-10 !pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink3 hover:text-ink transition-colors"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reg-confirm" className="block text-[12.5px] font-medium text-ink2">
                  Confirm password
                </label>
                <input
                  id="reg-confirm"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter your password"
                  className="input"
                />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary w-full h-11 rounded-full text-[14.5px] font-semibold mt-1"
              >
                {busy ? 'Creating account…' : 'Create account'}
              </button>
            </form>
          )}

          {/* Forgot Password Flow */}
          {mode === 'forgot' && forgotStep === 'email' && (
            <form onSubmit={handleRequestReset} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="forgot-email" className="block text-[12.5px] font-medium text-ink2">
                  Registered email address
                </label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="forgot-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@lpu.in"
                    className="input !pl-10"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary w-full h-11 rounded-full text-[14.5px] font-semibold"
              >
                {busy ? 'Sending code…' : 'Send reset code'}
              </button>

              <div className="text-center">
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="text-[13px] font-medium text-ink2 hover:text-ink transition-colors"
                >
                  Back to Sign in
                </button>
              </div>
            </form>
          )}

          {mode === 'forgot' && forgotStep === 'reset' && (
            <form onSubmit={handleCompleteReset} className="space-y-3.5">
              {devResetCode && (
                <div className="rounded-xl border border-line bg-bg px-3.5 py-2.5 text-[12.5px] text-ink2 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-ink3 text-[11px]">Local dev verification code</div>
                    <div className="font-mono font-semibold text-ink tracking-wider text-sm">
                      {devResetCode}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setResetCode(devResetCode)}
                    className="px-2.5 py-1 rounded-full bg-raised border border-line text-[12px] text-ink hover:border-ink3 transition-colors shrink-0"
                  >
                    Fill code
                  </button>
                </div>
              )}

              <div className="space-y-1.5">
                <label htmlFor="reset-code" className="block text-[12.5px] font-medium text-ink2">
                  6-digit verification code
                </label>
                <input
                  id="reset-code"
                  type="text"
                  inputMode="numeric"
                  maxLength={10}
                  value={resetCode}
                  onChange={(e) => setResetCode(e.target.value)}
                  placeholder="Enter 6-digit code"
                  className="input font-mono tracking-widest"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reset-new-pw" className="block text-[12.5px] font-medium text-ink2">
                  New password <span className="text-ink3 font-normal">(min 6 chars)</span>
                </label>
                <div className="relative">
                  <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="reset-new-pw"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Choose a new password"
                    className="input !pl-10 !pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink3 hover:text-ink transition-colors"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="reset-confirm" className="block text-[12.5px] font-medium text-ink2">
                  Confirm new password
                </label>
                <input
                  id="reset-confirm"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  className="input"
                />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="btn btn-primary w-full h-11 rounded-full text-[14.5px] font-semibold"
              >
                {busy ? 'Updating password…' : 'Reset password'}
              </button>

              <div className="flex items-center justify-between text-[12.5px]">
                <button
                  type="button"
                  onClick={() => {
                    setForgotStep('email')
                    setError(null)
                    setNotice(null)
                  }}
                  className="text-ink2 hover:text-ink transition-colors"
                >
                  Change email
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="text-ink2 hover:text-ink transition-colors"
                >
                  Back to Sign in
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
