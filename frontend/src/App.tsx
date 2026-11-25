import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Menu, PanelLeftOpen } from 'lucide-react'
import Sidebar from './components/Sidebar'
import Chat from './features/Chat'
import KnowledgeBase from './features/KnowledgeBase'
import SavedAnswers from './features/SavedAnswers'
import Settings from './features/Settings'
import Auth from './features/Auth'
import { authService } from './services/auth'
import { getUserSettings, applyTheme, applyFontSize } from './services/storage'

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(false)

  useEffect(() => {
    const s = getUserSettings()
    applyTheme(s.theme)
    applyFontSize(s.fontSize)
    authService.syncSession()
  }, [])

  return (
    <div className="flex h-full bg-shell">
      <Sidebar
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        collapsed={desktopCollapsed}
        onToggleCollapse={() => setDesktopCollapsed((c) => !c)}
      />

      <main className="flex-1 min-w-0 flex flex-col bg-bg overflow-hidden relative">
        {/* Mobile Header */}
        <header className="md:hidden flex items-center gap-2 px-3 h-12 border-b border-line bg-shell shrink-0">
          <button
            type="button"
            className="icon-btn"
            aria-label="Open navigation menu"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <span className="grid place-items-center w-6 h-6 rounded-full border-2 border-brand text-brand font-bold text-xs">
              U
            </span>
            <span className="font-semibold tracking-tight text-ink text-sm">UniMind</span>
          </div>
        </header>

        {/* Desktop Sidebar Expand Button (only shown when sidebar is collapsed) */}
        {desktopCollapsed && (
          <div className="hidden md:flex items-center px-3 pt-3 shrink-0">
            <button
              type="button"
              className="icon-btn border border-line bg-surface"
              aria-label="Expand sidebar"
              title="Open sidebar"
              onClick={() => setDesktopCollapsed(false)}
            >
              <PanelLeftOpen size={16} />
            </button>
          </div>
        )}

        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/c/:id" element={<Chat />} />
          <Route path="/saved" element={<SavedAnswers />} />
          <Route path="/knowledge" element={<KnowledgeBase />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/auth" element={<Auth />} />
        </Routes>
      </main>
    </div>
  )
}
