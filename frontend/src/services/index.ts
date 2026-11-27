import type { ChatService, DocumentService, Doc, Reply, Source, Conversation, Message, LlmMode } from './types'
import {
  getConversations,
  saveConversation,
  deleteConversation,
  renameConversation,
  getMessages,
  saveMessages,
} from './storage'

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

function mapBackendDoc(item: any): Doc {
  const filename = item.filename || 'Document.pdf'
  const ext = (filename.split('.').pop() || 'pdf').toLowerCase()
  const fileType: 'pdf' | 'docx' | 'xlsx' =
    ext === 'xlsx' ? 'xlsx' : ext === 'docx' ? 'docx' : 'pdf'
  const rawStatus = (item.status || '').toLowerCase()
  const status: 'processed' | 'processing' | 'failed' =
    rawStatus === 'processed' ? 'processed' : rawStatus.includes('fail') ? 'failed' : 'processing'

  const previewSnippets: string[] = []
  if (Array.isArray(item.pages) && item.pages.length > 0) {
    for (const p of item.pages) {
      const text = (p.text || p.snippet || '').trim()
      previewSnippets.push(text || '[No extractable text on this page]')
    }
  }

  return {
    id: item.doc_id,
    title: filename,
    department: item.department || 'General',
    category: item.category || 'Policy',
    type: fileType,
    uploaded: item.uploaded_at ? item.uploaded_at.slice(0, 10) : '',
    status,
    pages: item.total_pages ?? previewSnippets.length ?? 0,
    fileSizeBytes: item.file_size_bytes,
    totalChunks: item.total_chunks,
    needsOcrReview: Boolean(item.needs_ocr_review),
    isEmpty: Boolean(item.is_empty),
    preview: previewSnippets,
  }
}

async function parseErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg
  } catch {
    // Ignore JSON parse failure
  }
  return `${fallback} (HTTP ${res.status})`
}

export const chatService: ChatService = {
  async listConversations(): Promise<Conversation[]> {
    return getConversations()
  },

  async getMessages(id: string): Promise<Message[]> {
    return getMessages(id)
  },

  async saveMessages(id: string, messages: Message[]): Promise<void> {
    saveMessages(id, messages)
  },

  async createConversation(title: string): Promise<Conversation> {
    const conv: Conversation = {
      id: 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6),
      title: title.trim() || 'New Conversation',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    saveConversation(conv)
    return conv
  },

  async renameConversation(id: string, title: string): Promise<void> {
    renameConversation(id, title)
  },

  async deleteConversation(id: string): Promise<void> {
    deleteConversation(id)
  },

  suggestions: () => [
    'What are the minimum attendance requirements?',
    'How does exam re-evaluation work?',
    'What is the continuous assessment weightage?',
    'What are the hostel rules and curfew timings?',
    'Explain the academic probation guidelines',
    'How are end-term examination grades calculated?',
  ],

  async reply(
    prompt: string,
    onToken: (t: string) => void,
    signal: AbortSignal,
    department?: string,
    llmProvider?: LlmMode,
    history?: Array<{ role: 'user' | 'assistant'; content: string }>
  ): Promise<Reply> {
    let res: Response
    try {
      res = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          ...(department ? { department } : {}),
          ...(llmProvider ? { llm_provider: llmProvider } : {}),
          ...(history && history.length > 0 ? { history } : {}),
        }),
        signal,
      })
    } catch (e: any) {
      if (e?.name === 'AbortError') throw e
      throw new Error('Could not connect to the UniMind backend. Check that the server is running.')
    }

    if (!res.ok) {
      const msg = await parseErrorMessage(res, 'Failed to generate answer')
      throw new Error(msg)
    }

    const data = await res.json()
    const content = data.content || ''
    const sources: Source[] = Array.isArray(data.sources)
      ? data.sources.map((s: any) => ({
          n: s.n,
          docId: s.docId,
          docTitle: s.docTitle,
          page: s.page,
          quote: s.quote,
        }))
      : []

    for (const w of content.match(/\S+\s*|\n/g) ?? []) {
      if (signal.aborted) throw new DOMException('Stopped', 'AbortError')
      onToken(w)
      await wait(12)
    }

    return {
      content,
      sources,
      providerUsed: data.provider_used || undefined,
      followups: Array.isArray(data.followups) ? data.followups : undefined,
    }
  },
}

// Cache known document IDs from list() so clicking a citation from an uncataloged index entry doesn't spam 404s
let knownDocIds: Set<string> | null = null

export const documentService: DocumentService = {
  async list(): Promise<Doc[]> {
    let res: Response
    try {
      res = await fetch('/api/v1/documents')
    } catch {
      throw new Error('Could not reach the UniMind backend to load documents.')
    }

    if (!res.ok) {
      throw new Error(await parseErrorMessage(res, 'Could not load documents'))
    }

    const liveDocs = await res.json()
    if (!Array.isArray(liveDocs)) return []

    const mapped = liveDocs.map(mapBackendDoc)
    knownDocIds = new Set(mapped.map((d) => d.id))
    return mapped
  },

  async get(id: string): Promise<Doc | undefined> {
    if (!id) return undefined
    if (knownDocIds === null) {
      try {
        await this.list()
      } catch {
        return undefined
      }
    }
    if (knownDocIds !== null && !knownDocIds.has(id)) {
      return undefined
    }
    try {
      const res = await fetch(`/api/v1/documents/${encodeURIComponent(id)}`)
      if (res.ok) {
        const detail = await res.json()
        return mapBackendDoc(detail)
      }
    } catch {
      return undefined
    }
    return undefined
  },

  async upload(file: File, department = 'General', category = 'Policy'): Promise<Doc> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('department', department)
    formData.append('category', category)

    let res: Response
    try {
      res = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        body: formData,
      })
    } catch {
      throw new Error('Could not reach the backend server to upload the document.')
    }

    if (!res.ok) {
      throw new Error(await parseErrorMessage(res, 'Document upload failed'))
    }

    const uploaded = await res.json()
    const doc = mapBackendDoc(uploaded)
    if (knownDocIds) knownDocIds.add(doc.id)

    // Trigger indexing; don't hide errors if user inspects status later
    try {
      await fetch(`/api/v1/documents/${encodeURIComponent(doc.id)}/process`, {
        method: 'POST',
      })
    } catch {
      // Processing can be retried from the Knowledge Library detail panel
    }

    return doc
  },

  async process(id: string, force = false): Promise<void> {
    const res = await fetch(
      `/api/v1/documents/${encodeURIComponent(id)}/process?force=${force ? 'true' : 'false'}`,
      { method: 'POST' }
    )
    if (!res.ok) {
      throw new Error(await parseErrorMessage(res, 'Document processing failed'))
    }
  },

  async remove(id: string): Promise<void> {
    const res = await fetch(`/api/v1/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      throw new Error(await parseErrorMessage(res, 'Failed to delete document'))
    }
    if (knownDocIds) knownDocIds.delete(id)
  },
}
