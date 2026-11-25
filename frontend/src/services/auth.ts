import { saveUserSettings, getUserSettings } from './storage'
import type { AuthUser } from './types'

const TOKEN_KEY = 'unimind_auth_token'
const USER_KEY = 'unimind_auth_user'

function emitAuthChange(): void {
  window.dispatchEvent(new CustomEvent('unimind:auth_updated'))
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

export const authService = {
  async login(email: string, password: string): Promise<AuthUser> {
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

  async register(params: {
    fullName: string
    email: string
    password: string
    registrationNo?: string
  }): Promise<AuthUser> {
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
    return data.user
  },

  async requestPasswordReset(
    email: string
  ): Promise<{ message: string; devResetCode?: string; expiresInMinutes: number }> {
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
      message: data.message,
      devResetCode: data.dev_reset_code ?? undefined,
      expiresInMinutes: data.expires_in_minutes ?? 15,
    }
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
}
