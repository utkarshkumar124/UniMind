import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  Bookmark,
  Search,
  Trash2,
  Copy,
  Check,
  ExternalLink,
  ShieldCheck,
} from 'lucide-react'
import {
  getSavedAnswers,
  removeSavedAnswer,
  conversationExists,
} from '../services/storage'
import SourcePanel from '../components/SourcePanel'
import type { SavedAnswer, Source } from '../services/types'

export default function SavedAnswers() {
  const [items, setItems] = useState<SavedAnswer[]>([])
  const [q, setQ] = useState('')
  const [selectedSource, setSelectedSource] = useState<Source | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const reload = () => setItems(getSavedAnswers())

  useEffect(() => {
    reload()
    const handleUpdate = () => reload()
    window.addEventListener('unimind:saved_answers_updated', handleUpdate)
    return () => window.removeEventListener('unimind:saved_answers_updated', handleUpdate)
  }, [])

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard?.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  const handleDelete = (id: string) => {
    removeSavedAnswer(id)
    setItems((prev) => prev.filter((item) => item.id !== id))
  }

  const filtered = items.filter(
    (item) =>
      item.question.toLowerCase().includes(q.toLowerCase()) ||
      item.content.toLowerCase().includes(q.toLowerCase()) ||
      item.sources.some((s) => s.docTitle.toLowerCase().includes(q.toLowerCase()))
  )

  return (
    <div className="flex flex-1 min-h-0">
      <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 md:p-8">
        <div className="max-w-[780px] mx-auto">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-ink">Saved answers</h1>
              <p className="text-sm text-ink2 mt-0.5">
                Bookmarked answers and document references stored locally on this browser.
              </p>
            </div>
            {items.length > 0 && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-surface border border-line text-ink2">
                {items.length} saved
              </span>
            )}
          </div>

          {items.length > 0 && (
            <div className="mb-6">
              <label className="flex items-center gap-2 px-3 h-9.5 rounded-xl bg-surface border border-line focus-within:border-accent/60 text-ink2 max-w-md">
                <Search size={15} className="text-ink3 shrink-0" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search saved answers or sources…"
                  aria-label="Search saved answers"
                  className="bg-transparent outline-none text-sm text-ink w-full placeholder:text-ink3"
                />
              </label>
            </div>
          )}

          {items.length === 0 ? (
            <div className="border border-line border-dashed rounded-2xl p-10 text-center my-4">
              <div className="w-10 h-10 rounded-full bg-surface border border-line grid place-items-center mx-auto mb-3 text-ink3">
                <Bookmark size={18} />
              </div>
              <h2 className="font-medium text-sm text-ink mb-1">No saved answers yet</h2>
              <p className="text-xs text-ink2 max-w-sm mx-auto mb-5 leading-relaxed">
                Click the bookmark icon below any assistant response in chat to keep important rules and excerpts handy here.
              </p>
              <Link to="/" className="btn text-xs">
                Ask a question
              </Link>
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-sm text-ink2 border border-line rounded-xl bg-surface">
              No saved answers match &ldquo;{q}&rdquo;.
            </div>
          ) : (
            <div className="divide-y divide-line border-t border-line">
              {filtered.map((item) => {
                const formattedDate = new Date(item.savedAt).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
                const canOpenChat = Boolean(item.convId && conversationExists(item.convId))

                return (
                  <article key={item.id} className="py-6 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="font-medium text-[15px] text-ink">{item.question}</h2>
                        <p className="text-xs text-ink3 mt-0.5">Saved {formattedDate}</p>
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0">
                        {canOpenChat && (
                          <Link
                            to={`/c/${item.convId}`}
                            className="icon-btn"
                            title="Open original conversation"
                            aria-label="Open original conversation"
                          >
                            <ExternalLink size={15} />
                          </Link>
                        )}
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label="Copy saved answer"
                          title="Copy answer"
                          onClick={() => handleCopy(item.id, item.content)}
                        >
                          {copiedId === item.id ? (
                            <Check size={15} className="text-accent" />
                          ) : (
                            <Copy size={15} />
                          )}
                        </button>
                        <button
                          type="button"
                          className="icon-btn hover:!text-error"
                          aria-label="Remove saved answer"
                          title="Remove bookmark"
                          onClick={() => handleDelete(item.id)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>

                    <div className="prose-um text-sm">
                      <ReactMarkdown
                        urlTransform={(u) => u}
                        components={{
                          a: ({ href, children }) => {
                            const n = href?.startsWith('#cite-') ? Number(href.slice(6)) : 0
                            const s = item.sources?.find((x) => x.n === n)
                            return n ? (
                              <button
                                type="button"
                                disabled={!s}
                                onClick={() => s && setSelectedSource(s)}
                                className="inline-flex items-center justify-center text-[11px] font-semibold px-1.5 py-0.5 mx-0.5 rounded bg-accent-tint text-accent hover:bg-accent hover:text-accent-ink leading-none align-baseline transition-colors"
                              >
                                {n}
                              </button>
                            ) : (
                              <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-accent underline underline-offset-2"
                              >
                                {children}
                              </a>
                            )
                          },
                        }}
                      >
                        {item.content.replace(/\[(\d+)\]/g, '[$1](#cite-$1)')}
                      </ReactMarkdown>
                    </div>

                    {item.sources && item.sources.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <ShieldCheck size={13} className="text-accent mr-0.5" />
                        {item.sources.map((s) => (
                          <button
                            key={s.n}
                            type="button"
                            onClick={() => setSelectedSource(s)}
                            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-line bg-surface hover:border-accent/60 hover:bg-raised text-ink2 hover:text-ink transition-colors"
                          >
                            <span className="text-accent font-semibold">{s.n}</span>
                            <span className="truncate max-w-[180px]">{s.docTitle}</span>
                            <span className="text-ink3">p. {s.page}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {selectedSource && (
        <SourcePanel s={selectedSource} onClose={() => setSelectedSource(null)} />
      )}
    </div>
  )
}
