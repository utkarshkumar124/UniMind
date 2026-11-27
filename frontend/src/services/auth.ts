import type { User } from '@supabase/supabase-js'
import { supabase, isSupabaseConfigured } from './supabase'
import { saveUserSettings, getUserSettings } from './storage'
import type { AuthUser } from './types'

const TOKEN_KEY = 'unimind_auth_token'
const USER_KEY = 'unimind_auth_user'

function emitAuthChange(): void {
  window.dispatchEvent(new CustomEvent('unimind:auth_updated'))
}

function mapSupabaseUser(u: User): AuthUser {
  const meta = (u.user_metadata || {}) as Record<string, any>
  const emailName = u.email ? u.email.split('@')[0] : 'Student'
  return {
    user_id: u.id,
    full_name: String(meta.full_name || meta.name || emailName),
    email: u.email || '',
    registration_no: String(meta.registration_no || ''),
    created_at: u.created_at || new Date().toISOString(),
  }
}

export function getStoredAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredAuthUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

function persistAuthSession(user: AuthUser, token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  saveUserSettings({ displayName: user.full_name })
  emitAuthChange()
}

function clearAuthSession(): void {
  const previous = getStoredAuthUser()
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  if (previous && getUserSettings().displayName === previous.full_name) {
    saveUserSettings({ displayName: 'Guest Student' })
  }
  emitAuthChange()
}

async function parseAuthError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg
  } catch {
    // Ignore parse failure
  }
  return `${fallback} (HTTP ${res.status})`
}

export interface RegisterResult {
  user: AuthUser | null
  requiresEmailConfirmation: boolean
  message?: string
}

export interface ForgotPasswordResult {
  message: string
  viaSupabaseEmail: boolean
  devResetCode?: string
  expiresInMinutes: number
}

export const authService = {
  isUsingSupabase(): boolean {
    return isSupabaseConfigured && supabase !== null
  },

  async login(email: string, password: string): Promise<AuthUser> {
    if (supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error || !data.user || !data.session) {
        throw new Error(error?.message || 'Sign in failed.')
      }
      const mapped = mapSupabaseUser(data.user)
      persistAuthSession(mapped, data.session.access_token)
      return mapped
    }

    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      throw new Error(await parseAuthError(res, 'Sign in failed'))
    }
    const data = await res.json()
    persistAuthSession(data.user, data.access_token)
    return data.user
  },

  async signInWithGoogle(): Promise<void> {
    if (!supabase) {
      throw new Error(
        'Google Sign-In requires Supabase configuration in frontend/.env.local.'
      )
    }

    const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || '').trim()
    const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || '').trim()
    try {
      const settingsRes = await fetch(`${supabaseUrl}/auth/v1/settings`, {
        headers: { apikey: supabaseAnonKey },
      })
      if (settingsRes.ok) {
        const settingsJson = await settingsRes.json()
        if (settingsJson?.external && settingsJson.external.google === false) {
          throw new Error(
            'Google provider is disabled in your Supabase project. Enable Google under Authentication -> Providers -> Google in Supabase Dashboard.'
          )
        }
      }
    } catch (err: any) {
      if (err?.message?.includes('Google provider is disabled')) throw err
    }

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/`,
      },
    })
    if (error) {
      throw new Error(error.message)
    }
  },

  async register(params: {
    fullName: string
    email: string
    password: string
    registrationNo?: string
  }): Promise<RegisterResult> {
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({
        email: params.email,
        password: params.password,
        options: {
          emailRedirectTo: `${window.location.origin}/auth?mode=signin`,
          data: {
            full_name: params.fullName,
            registration_no: params.registrationNo || '',
          },
        },
      })
      if (error) {
        throw new Error(error.message)
      }
      if (data.user && data.session) {
        const mapped = mapSupabaseUser(data.user)
        persistAuthSession(mapped, data.session.access_token)
        return { user: mapped, requiresEmailConfirmation: false }
      }
      return {
        user: data.user ? mapSupabaseUser(data.user) : null,
        requiresEmailConfirmation: true,
        message: 'Verification email sent! Check your inbox and confirm your account before signing in.',
      }
    }

    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: params.fullName,
        email: params.email,
        password: params.password,
        registration_no: params.registrationNo || '',
      }),
    })
    if (!res.ok) {
      throw new Error(await parseAuthError(res, 'Registration failed'))
    }
    const data = await res.json()
    persistAuthSession(data.user, data.access_token)
    return { user: data.user, requiresEmailConfirmation: false }
  },

  async requestPasswordReset(email: string): Promise<ForgotPasswordResult> {
    if (supabase) {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth?mode=reset`,
      })
      if (error) {
        throw new Error(error.message)
      }
      return {
        viaSupabaseEmail: true,
        message: 'Password reset link sent to your email! Open the link in your inbox to set a new password.',
        expiresInMinutes: 60,
      }
    }

    const res = await fetch('/api/v1/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    if (!res.ok) {
      throw new Error(await parseAuthError(res, 'Could not generate reset code'))
    }
    const data = await res.json()
    return {
      viaSupabaseEmail: false,
      message: data.message,
      devResetCode: data.dev_reset_code ?? undefined,
      expiresInMinutes: data.expires_in_minutes ?? 15,
    }
  },

  async updateSupabasePassword(newPassword: string): Promise<string> {
    if (!supabase) {
      throw new Error('Supabase is not configured.')
    }
    const { data, error } = await supabase.auth.updateUser({ password: newPassword })
    if (error) {
      throw new Error(error.message)
    }
    if (data.user) {
      const { data: sess } = await supabase.auth.getSession()
      if (sess.session) {
        persistAuthSession(mapSupabaseUser(data.user), sess.session.access_token)
      }
    }
    return 'Password updated successfully.'
  },

  async resetPassword(params: {
    email: string
    resetCode: string
    newPassword: string
  }): Promise<string> {
    const res = await fetch('/api/v1/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: params.email,
        reset_code: params.resetCode,
        new_password: params.newPassword,
      }),
    })
    if (!res.ok) {
      throw new Error(await parseAuthError(res, 'Password reset failed'))
    }
    const data = await res.json()
    return data.message || 'Password updated successfully.'
  },

  async signOut(): Promise<void> {
    const token = getStoredAuthToken()
    clearAuthSession()
    if (supabase) {
      await supabase.auth.signOut().catch(() => {})
      return
    }
    if (!token) return
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
    } catch {
      // Local session already cleared
    }
  },

  async syncSession(): Promise<AuthUser | null> {
    if (supabase) {
      const { data } = await supabase.auth.getSession()
      if (data.session?.user) {
        const mapped = mapSupabaseUser(data.session.user)
        persistAuthSession(mapped, data.session.access_token)
        return mapped
      }
      clearAuthSession()
      return null
    }

    const token = getStoredAuthToken()
    if (!token) return null
    try {
      const res = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        clearAuthSession()
        return null
      }
      const user = (await res.json()) as AuthUser
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      emitAuthChange()
      return user
    } catch {
      return getStoredAuthUser()
    }
  },

  subscribeSupabaseEvents(onRecovery: () => void): () => void {
    if (!supabase) return () => {}
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') {
        onRecovery()
      } else if (session?.user && (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED' || event === 'USER_UPDATED')) {
        persistAuthSession(mapSupabaseUser(session.user), session.access_token)
      } else if (event === 'SIGNED_OUT') {
        clearAuthSession()
      }
    })
    return () => data.subscription.unsubscribe()
  },
}
