import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Moon,
  Sun,
  Laptop,
  Check,
  ShieldCheck,
  Server,
  Trash2,
  AlertTriangle,
  LogIn,
  LogOut,
  UserCheck,
} from 'lucide-react'
import { authService, getStoredAuthUser } from '../services/auth'
import {
  getUserSettings,
  saveUserSettings,
  applyTheme,
  applyFontSize,
  clearAllLocalData,
} from '../services/storage'
import type { AuthUser, UserSettings as UserSettingsType } from '../services/types'

const Section = ({
  t,
  desc,
  children,
}: {
  t: string
  desc?: string
  children: React.ReactNode
}) => (
  <section className="border-t border-line py-6">
    <h2 className="font-semibold text-sm text-ink mb-0.5">{t}</h2>
    {desc && <p className="text-xs text-ink2 mb-4">{desc}</p>}
    {children}
  </section>
)

export default function Settings() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<UserSettingsType>(getUserSettings)
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => getStoredAuthUser())
  const [savedName, setSavedName] = useState(false)
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'offline'>('checking')
  const [embeddingStatus, setEmbeddingStatus] = useState<'INITIALIZING' | 'READY' | 'FAILED' | 'UNKNOWN'>('UNKNOWN')
  const [embeddingError, setEmbeddingError] = useState<string | null>(null)
  const [serviceName, setServiceName] = useState('UniMind Knowledge Assistant')
  const [serviceVersion, setServiceVersion] = useState('0.1.0')
  const [clearConfirm, setClearConfirm] = useState(false)
  const [clearedNotice, setClearedNotice] = useState(false)

  useEffect(() => {
    const onAuth = () => setAuthUser(getStoredAuthUser())
    window.addEventListener('unimind:auth_updated', onAuth)
    fetch('/api/v1/health')
      .then((res) => {
        if (res.ok) return res.json()
        throw new Error('Unavailable')
      })
      .then((data) => {
        setBackendStatus('connected')
        if (data.service) setServiceName(data.service)
        if (data.version) setServiceVersion(data.version)
        setEmbeddingStatus(data.embedding_status || 'READY')
        setEmbeddingError(data.embedding_error || null)
      })
      .catch(() => {
        setBackendStatus('offline')
        setEmbeddingStatus('UNKNOWN')
      })
    return () => window.removeEventListener('unimind:auth_updated', onAuth)
  }, [])

  const updateSetting = <K extends keyof UserSettingsType>(key: K, value: UserSettingsType[K]) => {
    const updated = saveUserSettings({ [key]: value })
    setSettings(updated)
    if (key === 'theme') applyTheme(value as UserSettingsType['theme'])
    if (key === 'fontSize') applyFontSize(value as UserSettingsType['fontSize'])
  }

  const handleNameBlur = () => {
    setSavedName(true)
    setTimeout(() => setSavedName(false), 1500)
  }

  const handleClearData = () => {
    clearAllLocalData()
    setClearConfirm(false)
    setClearedNotice(true)
    setTimeout(() => setClearedNotice(false), 3000)
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8">
      <div className="max-w-[640px] mx-auto">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-ink">Settings</h1>
          <p className="text-sm text-ink2 mt-0.5">
            Manage appearance, chat behavior, and local session preferences.
          </p>
        </div>

        {/* Account */}
        <Section t="Account" desc="Sign in, register a new student account, or reset your password.">
          {authUser ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4 py-3.5">
              <div className="flex items-center gap-3 min-w-0">
                <span className="grid place-items-center w-9 h-9 rounded-full bg-accent-tint text-accent shrink-0">
                  <UserCheck size={17} />
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink truncate">{authUser.full_name}</div>
                  <div className="text-xs text-ink2 truncate">
                    {authUser.email}
                    {authUser.registration_no ? ` · Reg: ${authUser.registration_no}` : ''}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => authService.signOut()}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-line bg-bg hover:border-error/60 hover:text-error text-ink2 transition-colors"
              >
                <LogOut size={13} />
                <span>Sign out</span>
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4 py-3.5">
              <div>
                <div className="text-sm font-medium text-ink">Guest Session</div>
                <div className="text-xs text-ink2">
                  Sign in or create an account to save your student identity.
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => navigate('/auth?mode=signin')}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-full bg-pill text-pill-ink hover:opacity-90 transition-opacity"
                >
                  <LogIn size={13} />
                  <span>Sign in</span>
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/auth?mode=register')}
                  className="text-xs font-medium px-3 py-1.5 rounded-full border border-line bg-bg hover:bg-raised text-ink transition-colors"
                >
                  Register
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/auth?mode=forgot')}
                  className="text-xs font-medium text-ink2 hover:text-ink px-2 py-1 transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            </div>
          )}
        </Section>

        {/* Appearance */}
        <Section t="Appearance" desc="Select a color theme for the workspace.">
          <div className="grid grid-cols-3 gap-2.5">
            {(
              [
                { id: 'dark', label: 'Dark', Icon: Moon },
                { id: 'light', label: 'Light', Icon: Sun },
                { id: 'system', label: 'System', Icon: Laptop },
              ] as const
            ).map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => updateSetting('theme', id)}
                className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl border text-sm font-medium transition-colors ${
                  settings.theme === id
                    ? 'border-accent bg-accent-tint text-accent'
                    : 'border-line bg-surface hover:bg-raised text-ink2'
                }`}
              >
                <Icon size={16} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </Section>

        {/* Chat Preferences */}
        <Section t="Chat preferences" desc="Adjust message input behavior and reading size.">
          <div className="space-y-3">
            <label className="flex items-center justify-between gap-4 p-3.5 rounded-xl bg-surface border border-line cursor-pointer">
              <div>
                <span className="font-medium text-sm text-ink">Send message with Enter</span>
                <span className="block text-xs text-ink2 mt-0.5">
                  Press Shift+Enter for a new line. When turned off, use Ctrl+Enter to submit.
                </span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={settings.enterToSend}
                aria-label="Send message with Enter"
                onClick={() => updateSetting('enterToSend', !settings.enterToSend)}
                className={`w-10 h-6 rounded-full p-0.5 transition-colors shrink-0 ${
                  settings.enterToSend ? 'bg-accent' : 'bg-raised border border-line'
                }`}
              >
                <span
                  className={`block w-5 h-5 rounded-full bg-white shadow-xs transition-transform ${
                    settings.enterToSend ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <div className="p-3.5 rounded-xl bg-surface border border-line flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="font-medium text-sm text-ink">Text size</span>
                <span className="block text-xs text-ink2">Adjust reading density across chats.</span>
              </div>
              <div className="flex gap-1.5">
                {(['compact', 'normal', 'large'] as const).map((size) => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => updateSetting('fontSize', size)}
                    className={`py-1.5 px-3 rounded-lg border text-xs capitalize transition-colors ${
                      settings.fontSize === size
                        ? 'border-accent bg-accent-tint text-accent font-medium'
                        : 'border-line bg-bg hover:bg-raised text-ink2'
                    }`}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* Profile */}
        <Section t="Profile" desc="Set the display name shown in your sidebar.">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <input
                id="display-name"
                aria-label="Display name"
                value={settings.displayName}
                onChange={(e) => updateSetting('displayName', e.target.value)}
                onBlur={handleNameBlur}
                placeholder="Guest Student"
                className="flex-1 h-9.5 px-3 rounded-xl bg-surface border border-line outline-none focus:border-accent text-sm text-ink"
              />
              {savedName && (
                <span className="flex items-center gap-1 text-xs text-accent">
                  <Check size={14} />
                  Saved
                </span>
              )}
            </div>
            <p className="text-xs text-ink3">
              UniMind runs in a local session; university sign-in is not enabled yet.
            </p>
          </div>
        </Section>

        {/* System Status */}
        <Section t="Service status" desc="Live availability of the UniMind assistant.">
          <div className="bg-surface border border-line rounded-xl p-4 space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-ink flex items-center gap-2">
                <Server size={15} className="text-accent" />
                {serviceName}
              </span>
              <span
                className={`px-2.5 py-0.5 rounded-full font-medium ${
                  backendStatus === 'connected'
                    ? 'bg-accent-tint text-accent'
                    : backendStatus === 'checking'
                    ? 'bg-raised text-ink3'
                    : 'bg-error-tint text-error'
                }`}
              >
                {backendStatus === 'connected'
                  ? 'Connected'
                  : backendStatus === 'checking'
                  ? 'Checking…'
                  : 'Unavailable'}
              </span>
            </div>

            <div className="border-t border-line/60 pt-2.5 space-y-1.5 text-ink2">
              <div className="flex justify-between">
                <span className="text-ink3">Version</span>
                <span>{serviceVersion}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink3">Document search &amp; answers</span>
                <span
                  className={
                    backendStatus === 'connected' && embeddingStatus === 'READY'
                      ? 'text-accent font-medium'
                      : embeddingStatus === 'FAILED'
                      ? 'text-error font-medium'
                      : ''
                  }
                >
                  {backendStatus !== 'connected'
                    ? 'Unavailable'
                    : embeddingStatus === 'READY'
                    ? 'Ready'
                    : embeddingStatus === 'INITIALIZING'
                    ? 'Initializing…'
                    : 'Failed'}
                </span>
              </div>
              {embeddingStatus === 'FAILED' && embeddingError && (
                <div className="text-error text-[11px] pt-1">{embeddingError}</div>
              )}
              <div className="flex justify-between">
                <span className="text-ink3">Interface language</span>
                <span>English (multilingual queries supported)</span>
              </div>
            </div>
          </div>
        </Section>

        {/* Privacy & Data */}
        <Section t="Privacy & local data" desc="How your chat history and bookmarks are stored.">
          <div className="space-y-3 text-xs text-ink2 leading-relaxed">
            <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-surface border border-line">
              <ShieldCheck size={16} className="text-accent shrink-0 mt-0.5" />
              <p>
                Conversations, saved answers, feedback notes, and preferences are stored only in this browser&apos;s{' '}
                <code className="font-mono text-ink">localStorage</code> and are not synced across devices. Questions you submit are sent to the UniMind server to retrieve relevant university documents.
              </p>
            </div>

            {clearedNotice && (
              <p className="text-accent flex items-center gap-1.5">
                <Check size={14} />
                All local chats and saved answers have been cleared.
              </p>
            )}

            {clearConfirm ? (
              <div className="p-3 rounded-xl bg-error-tint border border-error/30 text-error flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-medium">
                  <AlertTriangle size={15} />
                  Delete all local chats and saved answers?
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleClearData}
                    className="px-2.5 py-1 rounded-md bg-error text-white font-medium hover:opacity-90"
                  >
                    Yes, clear all
                  </button>
                  <button
                    type="button"
                    onClick={() => setClearConfirm(false)}
                    className="px-2.5 py-1 rounded-md border border-line bg-surface text-ink"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setClearConfirm(true)}
                className="inline-flex items-center gap-1.5 text-ink3 hover:text-error transition-colors"
              >
                <Trash2 size={13} />
                <span>Clear local chat history and saved answers</span>
              </button>
            )}
          </div>
        </Section>
      </div>
    </div>
  )
}
