import { useEffect, useState } from 'react'
import { X, FileText, Quote, Info } from 'lucide-react'
import { documentService } from '../services'
import type { Source, Doc } from '../services/types'

export default function SourcePanel({ s, onClose }: { s: Source; onClose: () => void }) {
  const [doc, setDoc] = useState<Doc | undefined>(undefined)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    documentService.get(s.docId).then((res) => {
      if (active) {
        setDoc(res)
        setLoading(false)
      }
    })
    return () => {
      active = false
    }
  }, [s.docId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const pageText = doc?.preview?.[s.page - 1] ?? doc?.preview?.[0]

  return (
    <>
      <div
        className="lg:hidden fixed inset-0 bg-black/50 z-30 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        aria-label="Source details"
        className="slide-in fixed inset-x-0 bottom-0 max-h-[82vh] z-40 lg:static lg:max-h-none lg:w-[376px] shrink-0 bg-surface border-t lg:border-t-0 lg:border-l border-line rounded-t-2xl lg:rounded-none flex flex-col"
      >
        {/* Mobile grab handle */}
        <div className="lg:hidden flex justify-center pt-2.5 pb-1">
          <div className="w-9 h-1 rounded-full bg-line" />
        </div>

        {/* Header */}
        <div className="flex items-start gap-2.5 px-4 py-3.5 border-b border-line">
          <div className="w-8 h-8 rounded-lg bg-accent-tint text-accent grid place-items-center shrink-0 mt-0.5">
            <FileText size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="font-medium text-sm text-ink truncate" title={s.docTitle}>
              {s.docTitle}
            </h2>
            <p className="text-xs text-ink2 mt-0.5">
              Citation [{s.n}] · Page {s.page}
              {doc?.department ? ` · ${doc.department}` : ''}
            </p>
          </div>
          <button
            className="icon-btn shrink-0"
            aria-label="Close source panel"
            title="Close (Esc)"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto space-y-5 flex-1">
          <div>
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink3 mb-2">
              <Quote size={12} className="text-accent" />
              <span>Cited Passage</span>
            </div>
            <blockquote className="border-l-2 border-accent bg-accent-tint/60 px-3.5 py-2.5 rounded-r-lg text-[13.5px] text-ink leading-relaxed">
              {s.quote}
            </blockquote>
          </div>

          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink3 mb-2">
              Page {s.page} Context
            </p>
            {loading ? (
              <div className="space-y-2">
                <div className="skeleton h-4 rounded w-full" />
                <div className="skeleton h-4 rounded w-5/6" />
                <div className="skeleton h-4 rounded w-4/6" />
              </div>
            ) : pageText ? (
              <div className="text-[13px] text-ink2 bg-bg border border-line rounded-xl p-3.5 whitespace-pre-wrap leading-relaxed max-h-[360px] overflow-y-auto">
                {pageText}
              </div>
            ) : (
              <div className="flex items-start gap-2 text-xs text-ink3 bg-bg border border-line rounded-xl p-3.5 leading-relaxed">
                <Info size={14} className="shrink-0 mt-0.5" />
                <span>
                  Full page text preview is not available for this index entry. The retrieved excerpt above contains the matched evidence.
                </span>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
