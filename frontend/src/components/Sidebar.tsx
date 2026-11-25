import { useEffect, useState, useMemo } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  Plus,
  Search,
  Library,
  Settings,
  X,
  Bookmark,
  Trash2,
  Pencil,
  Check,
  PanelLeftClose,
  LogIn,
  LogOut,
} from 'lucide-react'
import { chatService } from '../services'
import { authService, getStoredAuthUser } from '../services/auth'
import { getUserSettings, getSavedAnswers } from '../services/storage'
import type { AuthUser, Conversation, UserSettings as UserSettingsType } from '../services/types'

const navClass =
  'flex items-center gap-2.5 px-3 h-10 rounded-[12px] text-[15px] font-medium tracking-[-0.02em] text-ink2 hover:bg-surface hover:text-ink transition-all duration-200'
const navActive = ({ isActive }: { isActive: boolean }) =>
  `${navClass} ${isActive ? '!bg-surface border border-line !text-ink' : 'border border-transparent'}`

interface DateGroup {
  label: string
  items: Conversation[]
}

function groupConversations(convs: Conversation[]): DateGroup[] {
  const now = Date.now()
  const oneDay = 24 * 60 * 60 * 1000

  const today: Conversation[] = []
  const yesterday: Conversation[] = []
  const prev7: Conversation[] = []
  const older: Conversation[] = []

  for (const c of convs) {
    const time = c.updatedAt || c.createdAt || now
    const diff = now - time
    if (diff < oneDay) today.push(c)
    else if (diff < 2 * oneDay) yesterday.push(c)
    else if (diff < 7 * oneDay) prev7.push(c)
    else older.push(c)
  }

  const groups: DateGroup[] = []
  if (today.length) groups.push({ label: 'Today', items: today })
  if (yesterday.length) groups.push({ label: 'Yesterday', items: yesterday })
  if (prev7.length) groups.push({ label: 'Previous 7 days', items: prev7 })
  if (older.length) groups.push({ label: 'Older', items: older })
  return groups
}

export default function Sidebar({
  open,
  onClose,
  collapsed,
  onToggleCollapse,
}: {
  open: boolean
  onClose: () => void
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  const [convs, setConvs] = useState<Conversation[] | null>(null)
  const [savedCount, setSavedCount] = useState<number>(() => getSavedAnswers().length)
  const [q, setQ] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [userSettings, setUserSettings] = useState<UserSettingsType>(getUserSettings())
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => getStoredAuthUser())
  const [backendStatus, setBackendStatus] = useState<{
    reachable: boolean
    embedding: 'INITIALIZING' | 'READY' | 'FAILED' | 'UNKNOWN'
  } | null>(null)

  const go = useNavigate()
  const location = useLocation()

  const loadConvs = () => {
    chatService.listConversations().then(setConvs)
  }

  useEffect(() => {
    loadConvs()
    const handleConvUpdate = () => loadConvs()
    const handleSavedUpdate = () => setSavedCount(getSavedAnswers().length)
    const handleSettingsUpdate = () => setUserSettings(getUserSettings())
    const handleAuthUpdate = () => setAuthUser(getStoredAuthUser())

    window.addEventListener('unimind:conversations_updated', handleConvUpdate)
    window.addEventListener('unimind:saved_answers_updated', handleSavedUpdate)
    window.addEventListener('unimind:settings_updated', handleSettingsUpdate)
    window.addEventListener('unimind:auth_updated', handleAuthUpdate)

    fetch('/api/v1/health')
      .then(async (r) => {
        if (!r.ok) throw new Error('offline')
        const data = await r.json()
        setBackendStatus({
          reachable: true,
          embedding: data.embedding_status || 'READY',
        })
      })
      .catch(() => setBackendStatus({ reachable: false, embedding: 'UNKNOWN' }))

    return () => {
      window.removeEventListener('unimind:conversations_updated', handleConvUpdate)
      window.removeEventListener('unimind:saved_answers_updated', handleSavedUpdate)
      window.removeEventListener('unimind:settings_updated', handleSettingsUpdate)
      window.removeEventListener('unimind:auth_updated', handleAuthUpdate)
    }
  }, [])

  const startRename = (c: Conversation, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setConfirmDeleteId(null)
    setEditingId(c.id)
    setEditTitle(c.title)
  }

  const saveRename = async (id: string, e: React.MouseEvent | React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (editTitle.trim()) {
      await chatService.renameConversation(id, editTitle.trim())
      loadConvs()
    }
    setEditingId(null)
  }

  const requestDelete = (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setEditingId(null)
    setConfirmDeleteId(id)
  }

  const confirmDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    await chatService.deleteConversation(id)
    setConfirmDeleteId(null)
    loadConvs()
    if (location.pathname === `/c/${id}`) {
      go('/')
    }
  }

  const filteredConvs = useMemo(() => {
    if (!convs) return null
    if (!q.trim()) return convs
    return convs.filter((c) => c.title.toLowerCase().includes(q.toLowerCase()))
  }, [convs, q])

  const groups = useMemo(() => {
    return filteredConvs ? groupConversations(filteredConvs) : []
  }, [filteredConvs])

  const initials = useMemo(() => {
    const name = authUser?.full_name || userSettings.displayName || 'Guest'
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return (parts[0]?.slice(0, 2) || 'GS').toUpperCase()
  }, [authUser, userSettings.displayName])

  return (
    <>
      {open && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 z-30 transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed md:static z-40 inset-y-0 left-0 bg-shell flex flex-col transition-all duration-200 shrink-0 border-r border-line/60 md:border-r-0 ${
          open ? 'translate-x-0 w-[256px]' : '-translate-x-full md:translate-x-0'
        } ${collapsed ? 'md:w-0 md:overflow-hidden md:p-0' : 'md:w-[244px]'}`}
        aria-label="Sidebar navigation"
      >
        <div className="flex flex-col h-full w-[244px] px-3.5 py-4 gap-4">
          {/* Refero-style Bold Round Logo + Collapse */}
          <div className="flex items-center justify-between px-1">
            <NavLink
              to="/"
              onClick={onClose}
              className="flex items-center gap-2.5 text-ink hover:opacity-85 transition-opacity"
            >
              <span className="grid place-items-center w-8 h-8 rounded-full border-2 border-brand text-brand font-bold text-sm tracking-tight">
                U
              </span>
              <span className="font-semibold tracking-tight text-[15px]">UniMind</span>
            </NavLink>

            <div className="flex items-center gap-0.5">
              <button
                className="icon-btn hidden md:inline-grid"
                aria-label="Collapse sidebar"
                title="Collapse sidebar"
                onClick={onToggleCollapse}
              >
                <PanelLeftClose size={16} />
              </button>
              <button
                className="icon-btn md:hidden"
                aria-label="Close navigation menu"
                onClick={onClose}
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Crisp High-Contrast Primary Button (+ New chat) */}
          <button
            className="btn btn-primary w-full justify-start px-3.5 h-10.5 rounded-[12px] text-[15px] shadow-xs"
            onClick={() => {
              go('/')
              onClose()
            }}
          >
            <Plus size={17} strokeWidth={2.2} />
            <span>New chat</span>
          </button>

          {/* Primary Navigation (Refero style right under CTA) */}
          <div className="space-y-0.5">
            <NavLink to="/knowledge" onClick={onClose} className={navActive}>
              <Library size={16} className="shrink-0" />
              <span>Knowledge library</span>
            </NavLink>
            <NavLink to="/saved" onClick={onClose} className={navActive}>
              <Bookmark size={16} className="shrink-0" />
              <span className="flex-1">Saved answers</span>
              {savedCount > 0 && (
                <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-surface border border-line text-ink2">
                  {savedCount}
                </span>
              )}
            </NavLink>
            <NavLink to="/settings" onClick={onClose} className={navActive}>
              <Settings size={16} className="shrink-0" />
              <span>Settings</span>
            </NavLink>
          </div>

          {/* History Section */}
          <div className="flex-1 min-h-0 flex flex-col pt-2 border-t border-line/60">
            <div className="flex items-center justify-between px-2 mb-2">
              <span className="text-[11px] font-medium text-ink3">History</span>
              {convs && convs.length > 3 && (
                <span className="text-[11px] text-ink3">{convs.length}</span>
              )}
            </div>

            {convs && convs.length > 0 && (
              <label className="flex items-center gap-2 px-2.5 h-8 mb-2 rounded-lg bg-surface border border-line/80 text-ink2 focus-within:border-ink3">
                <Search size={13} className="text-ink3 shrink-0" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Filter history…"
                  aria-label="Search conversations"
                  className="bg-transparent outline-none text-xs text-ink w-full placeholder:text-ink3"
                />
                {q && (
                  <button
                    type="button"
                    onClick={() => setQ('')}
                    className="text-ink3 hover:text-ink"
                    aria-label="Clear search"
                  >
                    <X size={12} />
                  </button>
                )}
              </label>
            )}

            <nav className="flex-1 overflow-y-auto -mx-1 px-1 space-y-3" aria-label="Chat history">
              {!convs && [0, 1].map((i) => <div key={i} className="skeleton h-8 rounded-xl" />)}

              {groups.map((group) => (
                <div key={group.label} className="space-y-1">
                  {groups.length > 1 && (
                    <div className="px-2 text-[10.5px] font-medium text-ink3">
                      {group.label}
                    </div>
                  )}
                  {group.items.map((c) => {
                    const isEditing = editingId === c.id
                    const isConfirming = confirmDeleteId === c.id

                    if (isEditing) {
                      return (
                        <form
                          key={c.id}
                          onSubmit={(e) => saveRename(c.id, e)}
                          className="flex items-center gap-1 px-2.5 h-9 bg-surface rounded-xl border border-ink3"
                        >
                          <input
                            autoFocus
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') setEditingId(null)
                            }}
                            aria-label="Rename conversation"
                            className="bg-transparent text-[13px] text-ink outline-none w-full min-w-0"
                          />
                          <button
                            type="submit"
                            className="icon-btn !w-6 !h-6 text-accent"
                            aria-label="Save title"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="icon-btn !w-6 !h-6 text-ink3"
                            aria-label="Cancel rename"
                          >
                            <X size={13} />
                          </button>
                        </form>
                      )
                    }

                    if (isConfirming) {
                      return (
                        <div
                          key={c.id}
                          className="flex items-center justify-between gap-1 px-2.5 h-9 bg-error-tint border border-error/30 rounded-xl text-xs"
                        >
                          <span className="text-error font-medium truncate">Delete?</span>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              onClick={(e) => confirmDelete(c.id, e)}
                              className="px-2 py-0.5 rounded-md bg-error text-white text-[11px] font-medium hover:opacity-90"
                              aria-label="Confirm delete"
                            >
                              Yes
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setConfirmDeleteId(null)
                              }}
                              className="px-1.5 py-0.5 rounded-md bg-surface text-ink2 text-[11px] hover:text-ink"
                              aria-label="Cancel delete"
                            >
                              No
                            </button>
                          </div>
                        </div>
                      )
                    }

                    return (
                      <div key={c.id} className="group relative flex items-center">
                        <NavLink
                          to={`/c/${c.id}`}
                          onClick={onClose}
                          className={({ isActive }) =>
                            `flex items-center px-3 h-9.5 rounded-[12px] text-[14px] font-medium tracking-[-0.02em] w-full pr-14 transition-all duration-200 ${
                              isActive
                                ? 'bg-surface border border-line text-ink'
                                : 'text-ink2 hover:bg-surface/70 hover:text-ink border border-transparent'
                            }`
                          }
                        >
                          <span className="truncate">{c.title}</span>
                        </NavLink>
                        <div className="absolute right-1.5 hidden group-hover:flex group-focus-within:flex items-center gap-0.5 bg-raised rounded-lg px-0.5">
                          <button
                            className="icon-btn !w-6 !h-6"
                            title="Rename"
                            aria-label={`Rename ${c.title}`}
                            onClick={(e) => startRename(c, e)}
                          >
                            <Pencil size={12} />
                          </button>
                          <button
                            className="icon-btn !w-6 !h-6 hover:!text-error"
                            title="Delete"
                            aria-label={`Delete ${c.title}`}
                            onClick={(e) => requestDelete(c.id, e)}
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ))}

              {filteredConvs && filteredConvs.length === 0 && (
                <p className="text-xs text-ink3 px-2 py-4">
                  {q ? 'No matching conversations.' : 'No conversations yet.'}
                </p>
              )}
            </nav>
          </div>

          {/* Bottom Account & Status Area */}
          {authUser ? (
            <div className="flex items-center gap-2 px-2.5 py-2 rounded-xl border border-line bg-surface/50">
              <NavLink
                to="/settings"
                onClick={onClose}
                className="flex items-center gap-2.5 min-w-0 flex-1 hover:opacity-90 transition-opacity"
              >
                <span className="grid place-items-center w-7 h-7 rounded-full bg-raised text-ink font-medium text-[11px] border border-line shrink-0">
                  {initials}
                </span>
                <div className="leading-tight min-w-0 flex-1">
                  <div className="text-[13px] font-medium text-ink truncate">
                    {authUser.full_name}
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-ink3">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        backendStatus?.reachable && backendStatus.embedding === 'READY'
                          ? 'bg-accent'
                          : backendStatus?.reachable && backendStatus.embedding === 'FAILED'
                          ? 'bg-error'
                          : backendStatus !== null
                          ? 'bg-amber'
                          : 'bg-ink3'
                      }`}
                    />
                    <span className="truncate">{authUser.email}</span>
                  </div>
                </div>
              </NavLink>
              <button
                type="button"
                onClick={() => authService.signOut()}
                className="icon-btn !w-7 !h-7 shrink-0 hover:!text-error"
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <div className="space-y-1.5">
              <button
                type="button"
                onClick={() => {
                  go('/auth?mode=signin')
                  onClose()
                }}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl border border-line bg-surface/70 hover:bg-surface text-[13px] font-medium text-ink transition-colors"
              >
                <span className="flex items-center gap-2">
                  <LogIn size={14} className="text-accent" />
                  <span>Sign in / Register</span>
                </span>
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    backendStatus?.reachable && backendStatus.embedding === 'READY'
                      ? 'bg-accent'
                      : backendStatus?.reachable && backendStatus.embedding === 'FAILED'
                      ? 'bg-error'
                      : backendStatus !== null
                      ? 'bg-amber'
                      : 'bg-ink3'
                  }`}
                  title={
                    backendStatus?.reachable && backendStatus.embedding === 'READY'
                      ? 'Assistant ready'
                      : 'Checking server'
                  }
                />
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
