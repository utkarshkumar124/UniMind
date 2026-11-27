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

type AuthMode = 'signin' | 'register' | 'forgot' | 'reset'

const VALID_MODES: AuthMode[] = ['signin', 'register', 'forgot', 'reset']

export default function Auth() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const usingSupabase = authService.isUsingSupabase()

  const initialMode = (searchParams.get('mode') as AuthMode) || 'signin'
  const [mode, setMode] = useState<AuthMode>(
    VALID_MODES.includes(initialMode) ? initialMode : 'signin'
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
    if (paramMode && VALID_MODES.includes(paramMode)) {
      setMode(paramMode)
    }
  }, [searchParams])

  useEffect(() => {
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const queryParams = new URLSearchParams(window.location.search)
    const oauthErr =
      queryParams.get('error_description') ||
      hashParams.get('error_description') ||
      queryParams.get('error') ||
      hashParams.get('error')
    if (oauthErr) {
      setError(decodeURIComponent(oauthErr.replace(/\+/g, ' ')))
    }
  }, [])

  useEffect(() => {
    return authService.subscribeSupabaseEvents(() => {
      setMode('reset')
      setError(null)
      setNotice('Verified! Enter your new password below.')
    })
  }, [])

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

  const handleGoogleSignIn = async () => {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await authService.signInWithGoogle()
    } catch (err: any) {
      setError(err?.message || 'Google Sign-In failed.')
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
      const res = await authService.register({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
        registrationNo: registrationNo.trim(),
      })
      if (res.requiresEmailConfirmation) {
        setMode('signin')
        setSearchParams({ mode: 'signin' }, { replace: true })
        setPassword('')
        setConfirmPassword('')
        setNotice(res.message || 'Check your email to confirm your account, then sign in.')
        return
      }
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
      setNotice(res.message)
      if (!res.viaSupabaseEmail) {
        setDevResetCode(res.devResetCode || null)
        setForgotStep('reset')
      }
    } catch (err: any) {
      setError(err?.message || 'Could not start password reset.')
    } finally {
      setBusy(false)
    }
  }

  const handleSupabaseRecoveryUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
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
      const msg = await authService.updateSupabasePassword(password)
      setPassword('')
      setConfirmPassword('')
      setNotice(msg)
      navigate('/')
    } catch (err: any) {
      setError(err?.message || 'Could not update password.')
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
      : mode === 'reset'
      ? 'Set new password'
      : 'Reset your password'

  const subtitleText =
    mode === 'signin'
      ? 'Sign in to sync your student profile across UniMind.'
      : mode === 'register'
      ? 'Register with your student email to personalize your UniMind assistant.'
      : mode === 'reset'
      ? 'Choose a strong new password for your Supabase account.'
      : usingSupabase
      ? 'Enter your email to receive a password recovery link.'
      : forgotStep === 'email'
      ? 'Enter your registered email to receive a 6-digit reset verification code.'
      : 'Enter the verification code and choose a new password.'

  return (
    <div className="relative flex-1 overflow-y-auto px-4 py-6 sm:py-8 flex flex-col items-center refero-enter">
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

      <div className="relative z-10 w-full max-w-[430px] my-auto space-y-4">
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
          {mode !== 'forgot' && mode !== 'reset' && (
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

          {/* Sign in with Google Option */}
          {(mode === 'signin' || mode === 'register') && (
            <div className="relative z-10 space-y-3">
              <div className="flex items-center gap-3 text-[11.5px] text-ink3 uppercase tracking-wider">
                <div className="h-px flex-1 bg-white/10" />
                <span>or</span>
                <div className="h-px flex-1 bg-white/10" />
              </div>

              <button
                type="button"
                disabled={busy}
                onClick={handleGoogleSignIn}
                className="ios-glass-chip w-full h-11 rounded-full px-4 inline-flex items-center justify-center gap-2.5 text-[14px] font-medium text-ink transition-all"
              >
                <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current shrink-0" aria-hidden="true">
                  <path d="M21.35 11.1h-9.18v2.98h5.27c-.23 1.49-1.72 4.38-5.27 4.38-3.17 0-5.76-2.62-5.76-5.86s2.59-5.86 5.76-5.86c1.81 0 3.02.77 3.71 1.43l2.53-2.44C16.79 4.22 14.69 3.3 12.17 3.3 7.03 3.3 2.86 7.47 2.86 12.6s4.17 9.3 9.31 9.3c5.37 0 8.93-3.77 8.93-9.09 0-.61-.07-1.08-.15-1.71z" />
                </svg>
                <span>Continue with Google</span>
              </button>
            </div>
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

          {/* Supabase Password Recovery Reset Form (from email link /auth?mode=reset) */}
          {mode === 'reset' && (
            <form onSubmit={handleSupabaseRecoveryUpdate} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="sb-new-pw" className="block text-[12.5px] font-medium text-ink2">
                  New password <span className="text-ink3 font-normal">(min 6 chars)</span>
                </label>
                <div className="relative">
                  <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink3" />
                  <input
                    id="sb-new-pw"
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
                <label htmlFor="sb-confirm-pw" className="block text-[12.5px] font-medium text-ink2">
                  Confirm new password
                </label>
                <input
                  id="sb-confirm-pw"
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
                {busy ? 'Updating password…' : 'Save new password'}
              </button>
            </form>
          )}

          {/* Subtle Auth Provider Status */}
          <div className="pt-1 border-t border-white/10 text-center">
            <span className="text-[11.5px] text-ink3">
              {usingSupabase
                ? 'Supabase Auth active (email verification & password recovery enabled)'
                : 'Local Auth mode · Set VITE_SUPABASE_URL & VITE_SUPABASE_ANON_KEY in frontend/.env.local for Supabase Auth'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
