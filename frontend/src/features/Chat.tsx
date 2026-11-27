import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowUp,
  Square,
  Copy,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Check,
  Bookmark,
  ShieldCheck,
  AlertCircle,
  RotateCcw,
  X,
  Search,
  Focus,
  CornerDownRight,
  ChevronRight,
  Sparkles,
  Library,
  LogIn,
} from 'lucide-react'
import { chatService, documentService } from '../services'
import { getStoredAuthUser } from '../services/auth'
import {
  saveAnswer,
  removeSavedAnswerByContent,
  isAnswerSaved,
  getUserSettings,
  saveUserSettings,
  getConversations,
} from '../services/storage'
import SourcePanel from '../components/SourcePanel'
import MarkdownAnswer from '../components/MarkdownAnswer'
import type { AuthUser, LlmMode, Message, Source } from '../services/types'

const FEEDBACK_REASONS = [
  'Incorrect information',
  'Missing details',
  'Irrelevant answer',
  'Incorrect source',
  'Other',
]

function AssistantMessage({
  m,
  streaming,
  question,
  convId,
  onOpenSource,
  onRegen,
  onUpdateMessage,
}: {
  m: Message
  streaming?: boolean
  question?: string
  convId?: string
  onOpenSource: (s: Source) => void
  onRegen: () => void
  onUpdateMessage?: (updated: Message) => void
}) {
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(() => isAnswerSaved(m.content))
  const [showReasons, setShowReasons] = useState(false)

  useEffect(() => {
    setSaved(isAnswerSaved(m.content))
  }, [m.content])

  const hasSources = Boolean(m.sources && m.sources.length > 0)

  const handleCopy = () => {
    navigator.clipboard?.writeText(m.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleToggleSave = () => {
    if (saved) {
      removeSavedAnswerByContent(m.content)
      setSaved(false)
      onUpdateMessage?.({ ...m, bookmarked: false })
    } else {
      saveAnswer({
        convId,
        question: question || 'University query',
        content: m.content,
        sources: m.sources || [],
      })
      setSaved(true)
      onUpdateMessage?.({ ...m, bookmarked: true })
    }
  }

  const handleFeedback = (type: 'up' | 'down') => {
    const next = m.feedback === type ? null : type
    setShowReasons(next === 'down')
    onUpdateMessage?.({ ...m, feedback: next, feedbackReason: undefined })
  }

  const handleSelectReason = (reason: string) => {
    setShowReasons(false)
    onUpdateMessage?.({ ...m, feedback: 'down', feedbackReason: reason })
  }

  const timeStr = m.timestamp
    ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <article className="group space-y-3.5 refero-enter">
      {/* Editorial Markdown Answer directly on canvas */}
      <MarkdownAnswer
        content={m.content}
        sources={m.sources}
        onOpenSource={onOpenSource}
        className={`prose-um ${streaming ? 'cursor' : ''}`}
      />

      {/* Sources Showcase Container (Refero card container style) & Action Bar */}
      {!streaming && m.content && (
        <>
          {hasSources ? (
            <div className="bg-surface border border-line rounded-2xl p-3.5 sm:p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs">
                  <ShieldCheck size={14} className="text-accent shrink-0" />
                  <span className="font-medium text-ink">Verified document sources</span>
                  <span className="text-ink3">· {m.sources!.length} cited</span>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenSource(m.sources![0])}
                  className="inline-flex items-center gap-0.5 text-xs font-medium text-ink2 hover:text-ink transition-colors"
                >
                  <span>Inspect</span>
                  <ChevronRight size={14} />
                </button>
              </div>

              <div className="grid sm:grid-cols-2 gap-2">
                {m.sources!.map((s) => (
                  <button
                    key={s.n}
                    type="button"
                    onClick={() => onOpenSource(s)}
                    className="text-left rounded-xl border border-line bg-bg/60 hover:bg-raised hover:border-ink3 px-3 py-2.5 transition-colors space-y-1 min-w-0"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink truncate">
                        <span className="text-accent font-semibold">[{s.n}]</span>
                        <span className="truncate">{s.docTitle}</span>
                      </span>
                      <span className="text-[11px] text-ink3 shrink-0">p. {s.page}</span>
                    </div>
                    <p className="text-[12px] text-ink2 line-clamp-2 leading-snug">
                      {s.quote}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ) : !/^(hi!|hello!|you're welcome|goodbye!)/i.test(m.content.trim()) ? (
            <div className="flex items-center gap-1.5 text-xs text-amber">
              <AlertCircle size={14} className="shrink-0" />
              <span>No supporting document excerpts matched this query.</span>
            </div>
          ) : null}

          {/* Action Toolbar */}
          <div className="flex items-center gap-0.5 -ml-1.5 text-ink2">
            <button
              type="button"
              className="icon-btn"
              aria-label="Copy answer"
              title="Copy answer"
              onClick={handleCopy}
            >
              {copied ? <Check size={14} className="text-accent" /> : <Copy size={14} />}
            </button>

            <button
              type="button"
              className={`icon-btn ${saved ? '!text-accent' : ''}`}
              aria-label={saved ? 'Remove saved answer' : 'Save answer'}
              title={saved ? 'Saved to bookmarks' : 'Save answer'}
              onClick={handleToggleSave}
            >
              <Bookmark size={14} fill={saved ? 'currentColor' : 'none'} />
            </button>

            <button
              type="button"
              className="icon-btn"
              aria-label="Regenerate answer"
              title="Regenerate"
              onClick={onRegen}
            >
              <RefreshCw size={14} />
            </button>

            <div className="h-3 w-px bg-line mx-1" />

            <button
              type="button"
              className="icon-btn"
              aria-label="Helpful"
              title="Helpful (saved locally)"
              aria-pressed={m.feedback === 'up'}
              onClick={() => handleFeedback('up')}
            >
              <ThumbsUp size={14} className={m.feedback === 'up' ? 'text-accent' : ''} />
            </button>

            <button
              type="button"
              className="icon-btn"
              aria-label="Not helpful"
              title="Not helpful (saved locally)"
              aria-pressed={m.feedback === 'down'}
              onClick={() => handleFeedback('down')}
            >
              <ThumbsDown size={14} className={m.feedback === 'down' ? 'text-error' : ''} />
            </button>

            {m.feedbackReason && (
              <span className="text-[11px] text-ink3 ml-1.5">
                Noted locally: {m.feedbackReason}
              </span>
            )}

            {m.providerUsed && m.providerUsed !== 'small-talk' && (
              <span className="text-[11px] text-ink3 px-2 py-0.5 rounded-full border border-line/70 bg-surface/60">
                {m.providerUsed}
              </span>
            )}

            {timeStr && (
              <span className="text-[11px] text-ink3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                {timeStr}
              </span>
            )}
          </div>

          {showReasons && (
            <div className="p-3 bg-surface border border-line rounded-xl text-xs space-y-2 max-w-md">
              <div className="flex items-center justify-between">
                <p className="text-ink2 font-medium">What could be improved? (saved locally)</p>
                <button
                  type="button"
                  onClick={() => setShowReasons(false)}
                  className="text-ink3 hover:text-ink"
                >
                  Dismiss
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {FEEDBACK_REASONS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleSelectReason(r)}
                    className="px-2.5 py-1 rounded-lg border border-line bg-raised hover:border-ink3 text-ink transition-colors"
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </article>
  )
}

const HOME_SUGGESTION_TABS: Record<string, string[]> = {
  Popular: [
    'What are the minimum attendance requirements?',
    'How does exam re-evaluation work?',
    'What is the continuous assessment weightage?',
    'What are the hostel rules and curfew timings?',
    'Explain the academic probation guidelines',
    'How are end-term examination grades calculated?',
  ],
  Academics: [
    'Minimum attendance required for end-term exams',
    'Medical leave and duty leave attendance rules',
    'Course registration and add/drop deadlines',
    'CGPA calculation and promotion criteria',
    'Backlog and reappear registration process',
    'Academic integrity and plagiarism rules',
  ],
  Examinations: [
    'Continuous assessment vs end-term weightage',
    'How to apply for answer script re-evaluation',
    'Passing marks criteria in theory and practicals',
    'Examination hall conduct and barred items',
    'Make-up exam eligibility for medical emergencies',
    'Grade improvement and re-test policies',
  ],
  'Hostel & Campus': [
    'Hostel curfew and late-entry timings',
    'Gate pass and weekend leave approval process',
    'Mess rules and meal schedule guidelines',
    'Hostel room allotment and change procedure',
    'Library borrowing limits and fine structure',
    'Anti-ragging and campus disciplinary rules',
  ],
}

export default function Chat() {
  const { id: routeConvId } = useParams()
  const navigate = useNavigate()

  const [msgs, setMsgs] = useState<Message[]>([])
  const [loading, setLoading] = useState(Boolean(routeConvId))
  const [input, setInput] = useState('')
  const [live, setLive] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const [lastFailedPrompt, setLastFailedPrompt] = useState<string | null>(null)
  const [src, setSrc] = useState<Source | null>(null)
  const [enterToSend, setEnterToSend] = useState(() => getUserSettings().enterToSend)
  const [llmMode, setLlmMode] = useState<LlmMode>(() => getUserSettings().llmMode)
  const [departments, setDepartments] = useState<string[]>([])
  const [selectedDept, setSelectedDept] = useState<string | null>(null)
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => getStoredAuthUser())
  const [convTitle, setConvTitle] = useState<string>('')
  const [showQuickScope, setShowQuickScope] = useState(false)
  const [activeHomeTab, setActiveHomeTab] = useState<string>('Popular')

  const activeConvIdRef = useRef<string | undefined>(routeConvId)
  const abortRef = useRef<AbortController>()
  const endRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const userScrolledUp = useRef(false)

  useEffect(() => {
    const onSettings = () => {
      const s = getUserSettings()
      setEnterToSend(s.enterToSend)
      setLlmMode(s.llmMode)
    }
    const onAuth = () => setAuthUser(getStoredAuthUser())
    window.addEventListener('unimind:settings_updated', onSettings)
    window.addEventListener('unimind:auth_updated', onAuth)
    return () => {
      window.removeEventListener('unimind:settings_updated', onSettings)
      window.removeEventListener('unimind:auth_updated', onAuth)
    }
  }, [])

  // Discover real indexed departments for scope filter pills
  useEffect(() => {
    documentService
      .list()
      .then((docs) => {
        const depts = Array.from(new Set(docs.map((d) => d.department).filter(Boolean)))
        setDepartments(depts)
      })
      .catch(() => {})
  }, [])

  // Sync conversation title from storage
  useEffect(() => {
    const syncTitle = () => {
      const id = activeConvIdRef.current
      if (!id) {
        setConvTitle('')
        return
      }
      const match = getConversations().find((c) => c.id === id)
      setConvTitle(match?.title || '')
    }
    syncTitle()
    window.addEventListener('unimind:conversations_updated', syncTitle)
    return () => window.removeEventListener('unimind:conversations_updated', syncTitle)
  }, [routeConvId])

  useEffect(() => {
    if (routeConvId === activeConvIdRef.current) {
      if (routeConvId && msgs.length === 0 && !live) {
        setLoading(true)
        chatService.getMessages(routeConvId).then((m) => {
          setMsgs(m)
          setLoading(false)
        })
      }
      return
    }

    abortRef.current?.abort()
    activeConvIdRef.current = routeConvId
    setSrc(null)
    setErr('')
    setLastFailedPrompt(null)
    setLive(null)

    if (routeConvId) {
      setLoading(true)
      chatService.getMessages(routeConvId).then((m) => {
        if (activeConvIdRef.current === routeConvId) {
          setMsgs(m)
          setLoading(false)
        }
      })
    } else {
      setMsgs([])
      setLoading(false)
    }
  }, [routeConvId])

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const t = e.currentTarget
    userScrolledUp.current = t.scrollHeight - t.scrollTop - t.clientHeight > 120
  }

  useEffect(() => {
    if (!userScrolledUp.current) {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [msgs, live])

  const busy = live !== null

  const persistMessages = useCallback((id: string, updated: Message[]) => {
    chatService.saveMessages(id, updated)
  }, [])

  const handleUpdateSingleMessage = (updated: Message) => {
    setMsgs((prev) => {
      const next = prev.map((m) => (m.id === updated.id ? updated : m))
      if (activeConvIdRef.current) {
        persistMessages(activeConvIdRef.current, next)
      }
      return next
    })
  }

  async function run(prompt: string, base: Message[], convId: string) {
    setErr('')
    setLastFailedPrompt(null)
    setLive('')
    const controller = new AbortController()
    abortRef.current = controller
    let acc = ''

    try {
      const historyPayload = base
        .slice(0, -1)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 600) }))

      const r = await chatService.reply(
        prompt,
        (t) => {
          acc += t
          setLive(acc)
        },
        controller.signal,
        selectedDept || undefined,
        llmMode,
        historyPayload
      )

      const assistantMsg: Message = {
        id: 'msg-' + Date.now(),
        role: 'assistant',
        content: r.content,
        sources: r.sources,
        providerUsed: r.providerUsed,
        followups: r.followups,
        timestamp: Date.now(),
      }

      const finalMsgs = [...base, assistantMsg]
      if (activeConvIdRef.current === convId) {
        setMsgs(finalMsgs)
      }
      persistMessages(convId, finalMsgs)
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        const stoppedMsg: Message = {
          id: 'msg-' + Date.now(),
          role: 'assistant',
          content: acc ? `${acc}\n\n*(Stopped)*` : '*(Generation stopped)*',
          timestamp: Date.now(),
        }
        const finalMsgs = [...base, stoppedMsg]
        if (activeConvIdRef.current === convId) {
          setMsgs(finalMsgs)
        }
        persistMessages(convId, finalMsgs)
      } else {
        setErr(e?.message || 'Unable to generate a response. Please try again.')
        setLastFailedPrompt(prompt)
      }
    } finally {
      setLive(null)
    }
  }

  async function send(text = input) {
    const t = text.trim()
    if (!t || busy) return

    userScrolledUp.current = false
    let targetConvId = activeConvIdRef.current

    if (!targetConvId) {
      const title = t.length > 42 ? t.slice(0, 40) + '…' : t
      const newConv = await chatService.createConversation(title)
      targetConvId = newConv.id
      activeConvIdRef.current = targetConvId
      setConvTitle(title)
      navigate(`/c/${targetConvId}`, { replace: true })
    }

    const userMsg: Message = {
      id: 'msg-' + Date.now(),
      role: 'user',
      content: t,
      timestamp: Date.now(),
    }

    const base = [...msgs, userMsg]
    setMsgs(base)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    persistMessages(targetConvId, base)
    run(t, base, targetConvId)
  }

  function regen(i: number) {
    if (busy || !activeConvIdRef.current) return
    const base = msgs.slice(0, i)
    const lastUser = [...base].reverse().find((m) => m.role === 'user')
    if (lastUser) {
      setMsgs(base)
      persistMessages(activeConvIdRef.current, base)
      run(lastUser.content, base, activeConvIdRef.current)
    }
  }

  function retryLast() {
    if (busy || !lastFailedPrompt || !activeConvIdRef.current) return
    run(lastFailedPrompt, msgs, activeConvIdRef.current)
  }

  const isEmptyHome = !loading && msgs.length === 0 && !busy

  const askedQuestionsSet = new Set(
    msgs
      .filter((m) => m.role === 'user')
      .map((m) => m.content.trim().toLowerCase().replace(/[?.!,]+$/, ''))
  )
  const lastAssistantWithFollowups = [...msgs]
    .reverse()
    .find((m) => m.role === 'assistant' && Array.isArray(m.followups) && m.followups.length > 0)

  const dynamicFollowups = (lastAssistantWithFollowups?.followups || [])
    .filter((qText) => !askedQuestionsSet.has(qText.trim().toLowerCase().replace(/[?.!,]+$/, '')))
    .slice(0, 3)

  const floatingComposer = (centered: boolean) => (
    <div
      className={
        centered
          ? 'w-full'
          : 'pointer-events-none absolute bottom-0 inset-x-0 z-10 px-3 sm:px-4 pb-4'
      }
      style={!centered ? { paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' } : undefined}
    >
      <div className={`pointer-events-auto relative ${centered ? 'max-w-[640px]' : 'max-w-[640px] mx-auto space-y-2.5'}`}>
        {/* Stacked Card-Deck Follow-up Pills (dynamic & never repeats asked questions) */}
        {!centered && !busy && msgs.length > 0 && !input.trim() && dynamicFollowups.length > 0 && (
          <div className="followup-deck">
            {dynamicFollowups.map((fq, idx) => (
              <button
                key={fq}
                type="button"
                onClick={() => send(fq)}
                className={`followup-pill followup-pill-${idx} ios-glass-chip inline-flex items-center gap-2 text-[13px] font-medium px-4 py-1.5 rounded-full text-ink max-w-full`}
              >
                <CornerDownRight size={14} className="text-ink3 shrink-0" />
                <span className="truncate">{fq}</span>
              </button>
            ))}
          </div>
        )}

        {/* Quick Scope Popover triggered by left Focus icon */}
        {showQuickScope && (
          <div className="refero-drop absolute bottom-full left-0 mb-2.5 z-20 bg-surface border border-line rounded-2xl p-2 shadow-2xl min-w-[220px] space-y-1">
            <div className="px-2.5 py-1 text-[11px] font-medium text-ink3">Search scope</div>
            <button
              type="button"
              onClick={() => {
                setSelectedDept(null)
                setShowQuickScope(false)
              }}
              className={`w-full text-left text-xs px-2.5 py-1.5 rounded-lg transition-colors ${
                selectedDept === null ? 'bg-raised text-ink font-medium' : 'text-ink2 hover:bg-raised/60'
              }`}
            >
              All university documents
            </button>
            {departments.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => {
                  setSelectedDept(d)
                  setShowQuickScope(false)
                }}
                className={`w-full text-left text-xs px-2.5 py-1.5 rounded-lg transition-colors ${
                  selectedDept === d ? 'bg-raised text-ink font-medium' : 'text-ink2 hover:bg-raised/60'
                }`}
              >
                {d}
              </button>
            ))}
            <div className="border-t border-line/60 my-1 pt-1">
              <button
                type="button"
                onClick={() => {
                  setShowQuickScope(false)
                  navigate('/knowledge')
                }}
                className="w-full text-left text-xs px-2.5 py-1.5 rounded-lg text-accent hover:bg-raised/60"
              >
                Manage knowledge library →
              </button>
            </div>
          </div>
        )}

        {/* Larger iOS Liquid-Glass Floating Pill Bar */}
        <div
          className={`ios-glass transition-colors flex items-center gap-2.5 px-2.5 py-2 ${
            input.includes('\n') || input.length > 72 ? 'rounded-[28px] items-end' : 'rounded-full'
          }`}
        >
          <button
            type="button"
            onClick={() => setShowQuickScope((v) => !v)}
            aria-label="Filter document scope"
            title={selectedDept ? `Scope: ${selectedDept}` : 'Filter document scope'}
            className={`w-9.5 h-9.5 rounded-full grid place-items-center shrink-0 transition-colors ${
              selectedDept
                ? 'bg-accent-tint border border-accent/40 text-accent'
                : 'ios-glass-chip text-ink2 hover:text-ink'
            }`}
          >
            <Focus size={16} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            aria-label="Ask UniMind a question"
            placeholder={
              centered
                ? 'Ask about rules, attendance, or exams…'
                : 'Ask follow up…'
            }
            onChange={(e) => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
            }}
            onKeyDown={(e) => {
              if (enterToSend) {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              } else {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault()
                  send()
                }
              }
            }}
            className="w-full resize-none bg-transparent outline-none py-1.5 placeholder:text-ink3 max-h-[140px] text-ink text-[15px] font-medium tracking-[-0.02em] leading-snug"
          />

          <div className="shrink-0 flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                const order: LlmMode[] = ['auto', 'gemini', 'local']
                const next = order[(order.indexOf(llmMode) + 1) % order.length]
                setLlmMode(next)
                saveUserSettings({ llmMode: next })
              }}
              title="Switch answer model: Auto (Gemma 4 -> Gemini 3) -> Gemini 3 -> Gemma 4"
              className="ios-glass-chip hidden sm:inline-flex items-center px-2.5 h-8 rounded-full text-[11.5px] font-medium text-ink2 hover:text-ink transition-colors"
            >
              {llmMode === 'local' ? 'Gemma 4' : llmMode === 'gemini' ? 'Gemini 3' : 'Auto LLM'}
            </button>
            {busy ? (
              <button
                type="button"
                className="btn btn-primary !rounded-full !px-3.5 !h-9.5 text-xs"
                aria-label="Stop generating"
                onClick={() => abortRef.current?.abort()}
              >
                <Square size={12} fill="currentColor" />
                <span>Stop</span>
              </button>
            ) : (
              <button
                type="button"
                aria-label="Send question"
                disabled={!input.trim()}
                onClick={() => send()}
                className={`w-9.5 h-9.5 rounded-full grid place-items-center transition-all ${
                  input.trim()
                    ? 'bg-pill text-pill-ink hover:opacity-90 shadow-sm'
                    : 'ios-glass-chip text-ink3 !opacity-100 cursor-not-allowed'
                }`}
              >
                <ArrowUp size={16} strokeWidth={2.2} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <div className="flex flex-1 min-h-0">
      <section className="flex-1 min-w-0 flex flex-col relative">
        {/* Top Query Bar (Active Chat) */}
        {!isEmptyHome && (
          <div className="shrink-0 px-4 pt-3 sm:pt-4 pb-2 border-b border-line/40 bg-bg">
            <div className="max-w-[760px] mx-auto">
              <div className="bg-surface border border-line rounded-2xl px-4 h-12 flex items-center justify-between gap-3">
                <h1 className="text-[15.5px] font-medium tracking-[-0.02em] text-ink truncate">
                  {convTitle || msgs.find((m) => m.role === 'user')?.content || 'Conversation'}
                </h1>
                <button
                  type="button"
                  onClick={() => navigate('/')}
                  className="icon-btn !w-7 !h-7 shrink-0"
                  title="Close conversation & start new"
                  aria-label="Close conversation"
                >
                  <X size={15} />
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto" onScroll={handleScroll}>
          {isEmptyHome ? (
            <div className="min-h-full flex flex-col px-4 py-6 refero-enter">
              {/* Top Utility Bar: Knowledge Library + Auth Actions */}
              <div className="flex items-center justify-between gap-3 pt-1 pb-4 max-w-[960px] w-full mx-auto">
                <button
                  type="button"
                  onClick={() => navigate('/knowledge')}
                  className="inline-flex items-center gap-2 text-[13px] font-medium text-ink2 hover:text-ink transition-colors"
                >
                  <Library size={14} className="text-ink3" />
                  <span>Browse Knowledge Library</span>
                </button>

                {authUser ? (
                  <button
                    type="button"
                    onClick={() => navigate('/settings')}
                    className="inline-flex items-center gap-2 text-[12.5px] font-medium px-3 py-1.5 rounded-full border border-line bg-surface/70 hover:bg-surface text-ink transition-colors"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                    <span className="max-w-[140px] truncate">{authUser.full_name}</span>
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => navigate('/auth?mode=signin')}
                      className="inline-flex items-center gap-1.5 text-[12.5px] font-medium px-3 py-1.5 rounded-full border border-line bg-surface/60 hover:bg-surface text-ink2 hover:text-ink transition-colors"
                    >
                      <LogIn size={13} />
                      <span>Sign in</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate('/auth?mode=register')}
                      className="inline-flex items-center text-[12.5px] font-semibold px-3.5 py-1.5 rounded-full bg-pill text-pill-ink hover:opacity-90 transition-opacity"
                    >
                      Register
                    </button>
                  </div>
                )}
              </div>

              {/* Centered Hero + Two-Row Composer + Tabbed 2-Column Suggestions */}
              <div className="flex-1 flex flex-col justify-center w-full max-w-[680px] mx-auto pb-10 space-y-8">
                {/* Editorial Serif Hero */}
                <div className="text-center space-y-3">
                  <h1 className="font-hero text-[36px] sm:text-[46px] leading-[1.1] font-normal text-ink">
                    Make every decision with context
                  </h1>
                  <p className="text-[14.5px] text-ink2 max-w-[460px] mx-auto leading-relaxed">
                    Official university regulations, academic handbooks, and campus policies — answered with verified citations.
                  </p>
                </div>

                {/* Two-Row Rounded Composer Card (Refero Homepage Style) */}
                <div className="bg-surface border border-line focus-within:border-ink3/70 rounded-[22px] px-4.5 pt-3.5 pb-3 shadow-[0_14px_38px_rgba(0,0,0,0.35)] transition-colors">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    rows={1}
                    aria-label="Ask UniMind a question"
                    placeholder="Ask a question about university rules, exams, or attendance"
                    onChange={(e) => {
                      setInput(e.target.value)
                      e.target.style.height = 'auto'
                      e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'
                    }}
                    onKeyDown={(e) => {
                      if (enterToSend) {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          send()
                        }
                      } else {
                        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                          e.preventDefault()
                          send()
                        }
                      }
                    }}
                    className="w-full resize-none bg-transparent outline-none py-1 placeholder:text-ink3 max-h-[150px] text-ink text-[15px] font-medium tracking-[-0.02em] leading-relaxed"
                  />

                  <div className="flex items-center justify-between gap-2 pt-3">
                    <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                      <button
                        type="button"
                        onClick={() => navigate('/knowledge')}
                        aria-label="Knowledge library"
                        title="Browse knowledge documents"
                        className="w-8.5 h-8.5 rounded-full bg-raised/80 border border-line text-ink2 hover:text-ink hover:border-ink3 grid place-items-center shrink-0 transition-colors"
                      >
                        <Focus size={15} />
                      </button>

                      <button
                        type="button"
                        onClick={() => setSelectedDept(null)}
                        title="Grounded mode across official documents"
                        className={`inline-flex items-center gap-1.5 text-[13px] px-2.5 sm:px-3 h-8.5 rounded-full border shrink-0 transition-all duration-200 ${
                          selectedDept === null
                            ? 'bg-raised border-ink3/60 text-ink font-medium'
                            : 'border-transparent text-ink2 hover:bg-raised/60 hover:text-ink'
                        }`}
                      >
                        <Sparkles size={13} className="text-accent shrink-0" />
                        <span className="hidden sm:inline whitespace-nowrap">Grounded mode</span>
                      </button>

                      <div
                        className="inline-flex items-center p-0.5 rounded-full border border-line bg-bg/70 shrink-0"
                        role="group"
                        aria-label="Answer LLM mode"
                      >
                        {(
                          [
                            { id: 'auto', label: 'Auto' },
                            { id: 'gemini', label: 'Gemini 3' },
                            { id: 'local', label: 'Gemma 4' },
                          ] as const
                        ).map((opt) => (
                          <button
                            key={opt.id}
                            type="button"
                            onClick={() => {
                              setLlmMode(opt.id)
                              saveUserSettings({ llmMode: opt.id })
                            }}
                            className={`px-2 sm:px-2.5 h-7 rounded-full text-[11.5px] sm:text-[12px] font-medium whitespace-nowrap transition-colors ${
                              llmMode === opt.id
                                ? 'bg-pill text-pill-ink'
                                : 'text-ink2 hover:text-ink'
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      aria-label="Send question"
                      disabled={!input.trim()}
                      onClick={() => send()}
                      className={`w-9 h-9 rounded-full grid place-items-center shrink-0 transition-all ml-auto ${
                        input.trim()
                          ? 'bg-pill text-pill-ink hover:opacity-90 shadow-xs'
                          : 'bg-raised border border-line text-ink3 !opacity-100 cursor-not-allowed'
                      }`}
                    >
                      <ArrowUp size={16} strokeWidth={2.1} />
                    </button>
                  </div>
                </div>

                {/* Tabbed 2-Column Clean Prompt Grid (Refero Homepage Bottom) */}
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {Object.keys(HOME_SUGGESTION_TABS).map((tab) => (
                      <button
                        key={tab}
                        type="button"
                        onClick={() => setActiveHomeTab(tab)}
                        className={`text-[13px] px-3.5 py-1.5 rounded-xl transition-all duration-200 ${
                          activeHomeTab === tab
                            ? 'bg-surface border border-line text-ink font-medium'
                            : 'border border-transparent text-ink2 hover:text-ink'
                        }`}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>

                  <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2.5">
                    {(HOME_SUGGESTION_TABS[activeHomeTab] || []).map((qText) => (
                      <button
                        key={qText}
                        type="button"
                        onClick={() => send(qText)}
                        className="group text-left flex items-center gap-2.5 py-1 text-[13.5px] text-ink2 hover:text-ink transition-colors min-w-0"
                      >
                        <CornerDownRight
                          size={14}
                          className="text-ink3 group-hover:text-ink2 shrink-0 transition-colors"
                        />
                        <span className="truncate">{qText}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-[760px] mx-auto px-4 pt-6 pb-44 space-y-7">
              {loading && (
                <div className="space-y-4">
                  <div className="skeleton h-12 rounded-2xl w-2/3" />
                  <div className="skeleton h-24 rounded-2xl w-full" />
                </div>
              )}

              {msgs.map((m, i) => {
                const prevUserQuestion =
                  m.role === 'assistant'
                    ? [...msgs.slice(0, i)].reverse().find((x) => x.role === 'user')?.content
                    : undefined

                return m.role === 'user' ? (
                  <div key={m.id} className="group flex flex-col items-start gap-1 refero-enter">
                    {/* Signature Refero High-Contrast White User Pill */}
                    <div className="bg-pill text-pill-ink px-5 py-3 rounded-2xl w-fit max-w-[90%] sm:max-w-[82%] whitespace-pre-wrap text-[14.5px] leading-[1.5] tracking-[-0.02em] shadow-sm font-normal">
                      {m.content}
                    </div>
                    {m.timestamp && (
                      <span className="text-[11px] text-ink3 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {new Date(m.timestamp).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    )}
                  </div>
                ) : (
                  <AssistantMessage
                    key={m.id}
                    m={m}
                    question={prevUserQuestion}
                    convId={activeConvIdRef.current}
                    onOpenSource={setSrc}
                    onRegen={() => regen(i)}
                    onUpdateMessage={handleUpdateSingleMessage}
                  />
                )
              })}

              {busy && (
                <AssistantMessage
                  m={{ id: 'live', role: 'assistant', content: live ?? '' }}
                  streaming
                  onOpenSource={setSrc}
                  onRegen={() => {}}
                />
              )}

              {err && (
                <div
                  role="alert"
                  className="bg-error-tint border border-error/30 text-error text-sm rounded-2xl px-4 py-3 flex items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <AlertCircle size={16} className="shrink-0" />
                    <span className="break-words">{err}</span>
                  </div>
                  {lastFailedPrompt && (
                    <button
                      type="button"
                      onClick={retryLast}
                      className="btn !py-1 !px-2.5 text-xs shrink-0 border-error/30 text-error hover:bg-error/10"
                    >
                      <RotateCcw size={12} />
                      Retry
                    </button>
                  )}
                </div>
              )}

              <div ref={endRef} />
            </div>
          )}
        </div>

        {!isEmptyHome && floatingComposer(false)}
      </section>

      {src && <SourcePanel s={src} onClose={() => setSrc(null)} />}
    </div>
  )
}
