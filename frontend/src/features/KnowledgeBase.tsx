import { useEffect, useRef, useState } from 'react'
import {
  Search,
  Upload,
  FileText,
  X,
  AlertTriangle,
  Loader2,
  CheckCircle2,
  RefreshCw,
  Trash2,
  FolderOpen,
  ChevronDown,
} from 'lucide-react'
import { documentService } from '../services'
import type { Doc } from '../services/types'

const pillClass: Record<Doc['status'], string> = {
  processed: 'bg-accent-tint text-accent',
  processing: 'bg-amber-tint text-amber',
  failed: 'bg-error-tint text-error',
}

const statusLabel: Record<Doc['status'], string> = {
  processed: 'Indexed',
  processing: 'Processing',
  failed: 'Failed',
}

function formatBytes(bytes?: number): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export default function KnowledgeBase() {
  const [docs, setDocs] = useState<Doc[] | null>(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [department, setDepartment] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Doc | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [showUpload, setShowUpload] = useState(false)
  const [uploadDept, setUploadDept] = useState('Academics')
  const [uploadCat, setUploadCat] = useState('Policy')
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const [busyAction, setBusyAction] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDocs = () => {
    setErr('')
    documentService
      .list()
      .then((loaded) => setDocs(loaded))
      .catch((e) => {
        setDocs([])
        setErr(e?.message || 'Unable to load documents.')
      })
  }

  useEffect(() => {
    loadDocs()
  }, [])

  const openDetail = (d: Doc) => {
    setSelectedId(d.id)
    setConfirmDelete(false)
    setDetail(d)
    setDetailLoading(true)
    documentService.get(d.id).then((full) => {
      if (full) setDetail(full)
      setDetailLoading(false)
    })
  }

  async function handleUpload(f?: File) {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setBanner({ type: 'err', text: 'Only PDF documents are supported for indexing.' })
      return
    }
    if (f.size > 25 * 1024 * 1024) {
      setBanner({ type: 'err', text: 'File exceeds the 25 MB upload limit.' })
      return
    }

    setUploading(true)
    setBanner(null)
    try {
      const uploaded = await documentService.upload(f, uploadDept, uploadCat)
      setBanner({
        type: 'ok',
        text: `"${uploaded.title}" uploaded and queued for indexing.`,
      })
      setShowUpload(false)
      loadDocs()
    } catch (e: any) {
      setBanner({
        type: 'err',
        text: e?.message || 'Document upload failed. Verify backend connection.',
      })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleReprocess() {
    if (!detail || busyAction) return
    setBusyAction(true)
    setBanner(null)
    try {
      await documentService.process(detail.id, true)
      setBanner({ type: 'ok', text: `Reprocessed "${detail.title}".` })
      loadDocs()
      openDetail(detail)
    } catch (e: any) {
      setBanner({ type: 'err', text: e?.message || 'Failed to reprocess document.' })
    } finally {
      setBusyAction(false)
    }
  }

  async function handleDelete() {
    if (!detail || busyAction) return
    setBusyAction(true)
    setBanner(null)
    try {
      await documentService.remove(detail.id)
      setBanner({ type: 'ok', text: `Deleted "${detail.title}" from the knowledge library.` })
      setSelectedId(null)
      setDetail(null)
      setConfirmDelete(false)
      loadDocs()
    } catch (e: any) {
      setBanner({ type: 'err', text: e?.message || 'Failed to delete document.' })
    } finally {
      setBusyAction(false)
    }
  }

  const departments = Array.from(new Set(docs?.map((d) => d.department).filter(Boolean) || []))

  const rows = docs?.filter((d) => {
    const matchesQ =
      d.title.toLowerCase().includes(q.toLowerCase()) ||
      d.department.toLowerCase().includes(q.toLowerCase()) ||
      d.category.toLowerCase().includes(q.toLowerCase())
    const matchesStatus = status === 'all' || d.status === status
    const matchesDept = department === 'all' || d.department === department
    return matchesQ && matchesStatus && matchesDept
  })

  return (
    <div className="flex flex-1 min-h-0">
      <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 md:p-8">
        <div className="max-w-[920px] mx-auto space-y-5">
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-ink">Knowledge library</h1>
              <p className="text-sm text-ink2 mt-0.5">
                Official university PDFs indexed for question answering and source citations.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="icon-btn border border-line bg-surface"
                aria-label="Refresh document list"
                title="Refresh"
                onClick={loadDocs}
              >
                <RefreshCw size={15} />
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setShowUpload((v) => !v)}
              >
                <Upload size={15} />
                <span>Upload PDF</span>
              </button>
            </div>
          </div>

          {/* Collapsible Upload Panel */}
          {showUpload && (
            <div className="border border-line bg-surface rounded-2xl p-4 space-y-3 slide-in">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-ink">Add document to index</h2>
                <button
                  type="button"
                  className="icon-btn !w-7 !h-7"
                  aria-label="Close upload panel"
                  onClick={() => setShowUpload(false)}
                >
                  <X size={15} />
                </button>
              </div>

              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-ink2 mb-1">Department</label>
                  <input
                    value={uploadDept}
                    onChange={(e) => setUploadDept(e.target.value)}
                    placeholder="e.g. Academics, Examinations, Hostel"
                    className="w-full h-9 px-3 rounded-lg bg-bg border border-line text-sm text-ink outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="block text-xs text-ink2 mb-1">Category</label>
                  <input
                    value={uploadCat}
                    onChange={(e) => setUploadCat(e.target.value)}
                    placeholder="e.g. Policy, Syllabus, Timetable"
                    className="w-full h-9 px-3 rounded-lg bg-bg border border-line text-sm text-ink outline-none focus:border-accent"
                  />
                </div>
              </div>

              <div
                onDragEnter={(e) => {
                  e.preventDefault()
                  setDragActive(true)
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragActive(true)
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragActive(false)
                  handleUpload(e.dataTransfer.files?.[0])
                }}
                onClick={() => !uploading && fileInputRef.current?.click()}
                className={`border border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                  dragActive
                    ? 'border-accent bg-accent-tint/40'
                    : 'border-line bg-bg/60 hover:border-ink3'
                }`}
              >
                {uploading ? (
                  <div className="flex items-center justify-center gap-2 text-sm text-accent">
                    <Loader2 size={18} className="animate-spin" />
                    <span>Uploading and indexing document…</span>
                  </div>
                ) : (
                  <>
                    <Upload size={20} className="mx-auto text-ink3 mb-1.5" />
                    <p className="text-sm text-ink">
                      Drop a PDF file here, or{' '}
                      <span className="text-accent font-medium underline underline-offset-2">
                        choose file
                      </span>
                    </p>
                    <p className="text-xs text-ink3 mt-1">PDF only · Maximum 25 MB</p>
                  </>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                hidden
                onChange={(e) => handleUpload(e.target.files?.[0])}
              />
            </div>
          )}

          {/* Status Banner */}
          {banner && (
            <div
              role="status"
              className={`px-3.5 py-2.5 rounded-xl border text-sm flex items-center justify-between gap-2 ${
                banner.type === 'ok'
                  ? 'bg-accent-tint border-accent/25 text-accent'
                  : 'bg-error-tint border-error/25 text-error'
              }`}
            >
              <div className="flex items-center gap-2">
                {banner.type === 'ok' ? (
                  <CheckCircle2 size={16} className="shrink-0" />
                ) : (
                  <AlertTriangle size={16} className="shrink-0" />
                )}
                <span>{banner.text}</span>
              </div>
              <button
                type="button"
                onClick={() => setBanner(null)}
                className="opacity-70 hover:opacity-100"
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          )}

          {/* Search & Filters */}
          <div className="flex flex-wrap gap-2">
            <label className="flex items-center gap-2 px-3 h-9 rounded-lg bg-surface border border-line flex-1 min-w-[200px] focus-within:border-accent/60 text-ink2">
              <Search size={15} className="text-ink3 shrink-0" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Search documents"
                placeholder="Search by document title or department…"
                className="bg-transparent outline-none text-sm text-ink w-full placeholder:text-ink3"
              />
            </label>

            <div className="relative">
              <select
                aria-label="Filter by department"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="appearance-none h-9 pl-3 pr-8 rounded-lg bg-surface border border-line text-sm text-ink outline-none focus:border-accent/60"
              >
                <option value="all">All departments</option>
                {departments.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink3"
              />
            </div>

            <div className="relative">
              <select
                aria-label="Filter by status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="appearance-none h-9 pl-3 pr-8 rounded-lg bg-surface border border-line text-sm text-ink outline-none focus:border-accent/60"
              >
                <option value="all">All statuses</option>
                <option value="processed">Indexed</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink3"
              />
            </div>
          </div>

          {/* Document Table / Clean List */}
          {err ? (
            <div className="border border-line rounded-xl bg-surface p-8 text-center space-y-2">
              <AlertTriangle size={22} className="mx-auto text-error" />
              <p className="text-sm text-ink font-medium">{err}</p>
              <button type="button" className="btn text-xs mt-2" onClick={loadDocs}>
                Try again
              </button>
            </div>
          ) : docs === null ? (
            <div className="border border-line rounded-xl divide-y divide-line overflow-hidden">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-14" />
              ))}
            </div>
          ) : rows && rows.length === 0 ? (
            <div className="border border-line border-dashed rounded-2xl p-10 text-center">
              <FolderOpen size={24} className="mx-auto text-ink3 mb-2" />
              {docs.length > 0 ? (
                <>
                  <p className="text-sm font-medium text-ink">No matching documents</p>
                  <p className="text-xs text-ink2 mt-1">
                    Try adjusting your search or filter selections.
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-medium text-ink">No documents in library</p>
                  <p className="text-xs text-ink2 mt-1 max-w-sm mx-auto">
                    No official PDF files have been uploaded to the backend yet. Click &ldquo;Upload PDF&rdquo; to ingest university handbooks or regulations.
                  </p>
                </>
              )}
            </div>
          ) : (
            <div className="border border-line rounded-xl overflow-hidden bg-surface">
              {/* Desktop Column Headers */}
              <div className="hidden sm:grid grid-cols-[1fr_130px_90px_100px] gap-3 px-4 py-2.5 border-b border-line text-[11px] font-medium uppercase tracking-wider text-ink3 bg-shell/50">
                <span>Document</span>
                <span>Department</span>
                <span>Pages</span>
                <span className="text-right">Status</span>
              </div>

              <div className="divide-y divide-line">
                {rows?.map((d) => {
                  const active = selectedId === d.id
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => openDetail(d)}
                      className={`w-full text-left px-4 py-3 transition-colors hover:bg-raised/60 grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_130px_90px_100px] items-center gap-3 ${
                        active ? 'bg-raised/80' : ''
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText size={17} className="text-accent shrink-0" />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-ink truncate">{d.title}</div>
                          <div className="text-xs text-ink3 sm:hidden">
                            {d.department} · {d.pages} pages
                          </div>
                        </div>
                      </div>

                      <span className="hidden sm:block text-xs text-ink2 truncate">
                        {d.department}
                      </span>

                      <span className="hidden sm:block text-xs text-ink2">
                        {d.pages} {d.pages === 1 ? 'page' : 'pages'}
                      </span>

                      <div className="flex justify-end">
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${pillClass[d.status]}`}
                        >
                          {statusLabel[d.status]}
                        </span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Detail Drawer */}
      {detail && (
        <>
          <div
            className="lg:hidden fixed inset-0 bg-black/50 z-30"
            onClick={() => {
              setSelectedId(null)
              setDetail(null)
            }}
            aria-hidden="true"
          />
          <aside
            aria-label="Document details"
            className="slide-in fixed inset-x-0 bottom-0 max-h-[82vh] z-40 lg:static lg:max-h-none lg:w-[390px] shrink-0 bg-surface border-t lg:border-t-0 lg:border-l border-line rounded-t-2xl lg:rounded-none flex flex-col"
          >
            <div className="flex items-start gap-2.5 p-4 border-b border-line">
              <FileText size={18} className="text-accent shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <h2 className="font-medium text-sm text-ink truncate">{detail.title}</h2>
                <p className="text-xs text-ink2 mt-0.5">
                  {detail.department} · {detail.category}
                </p>
              </div>
              <button
                type="button"
                className="icon-btn shrink-0"
                aria-label="Close document details"
                onClick={() => {
                  setSelectedId(null)
                  setDetail(null)
                }}
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-4 space-y-4 overflow-y-auto flex-1">
              <dl className="bg-bg border border-line rounded-xl p-3 text-xs space-y-2">
                <div className="flex justify-between gap-2">
                  <dt className="text-ink3">Status</dt>
                  <dd className={`px-2 py-0.5 rounded-full font-medium ${pillClass[detail.status]}`}>
                    {statusLabel[detail.status]}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink3">Pages</dt>
                  <dd className="text-ink">{detail.pages}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink3">Size</dt>
                  <dd className="text-ink">{formatBytes(detail.fileSizeBytes)}</dd>
                </div>
                {typeof detail.totalChunks === 'number' && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-ink3">Indexed sections</dt>
                    <dd className="text-ink">{detail.totalChunks}</dd>
                  </div>
                )}
                {detail.uploaded && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-ink3">Uploaded</dt>
                    <dd className="text-ink">{detail.uploaded}</dd>
                  </div>
                )}
              </dl>

              {detail.needsOcrReview && (
                <div className="p-3 rounded-xl bg-amber-tint text-amber text-xs leading-relaxed">
                  Some pages in this PDF appear scanned and may have limited searchable text.
                </div>
              )}

              {/* Document Management Actions */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busyAction}
                  onClick={handleReprocess}
                  className="btn flex-1 text-xs"
                >
                  <RefreshCw size={13} className={busyAction ? 'animate-spin' : ''} />
                  Reprocess
                </button>

                {confirmDelete ? (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={busyAction}
                      onClick={handleDelete}
                      className="btn !bg-error !text-white !border-transparent text-xs"
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      className="btn text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={busyAction}
                    onClick={() => setConfirmDelete(true)}
                    className="btn text-xs text-error hover:bg-error-tint"
                  >
                    <Trash2 size={13} />
                    Delete
                  </button>
                )}
              </div>

              {/* Page Snippets */}
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-ink3 mb-2">
                  Extracted Content
                </p>
                {detailLoading ? (
                  <div className="space-y-2">
                    <div className="skeleton h-16 rounded-lg" />
                    <div className="skeleton h-16 rounded-lg" />
                  </div>
                ) : detail.preview.length > 0 ? (
                  <div className="space-y-2.5">
                    {detail.preview.map((p, i) => (
                      <div
                        key={i}
                        className="text-xs text-ink2 bg-bg border border-line rounded-lg p-3 leading-relaxed whitespace-pre-wrap"
                      >
                        <div className="text-[11px] font-medium text-accent mb-1">Page {i + 1}</div>
                        {p}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-ink3">No extracted page text returned.</p>
                )}
              </div>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}
