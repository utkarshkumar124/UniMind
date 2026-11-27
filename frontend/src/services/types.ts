export interface Doc {
  id: string
  title: string
  category: string
  department: string
  type: 'pdf' | 'docx' | 'xlsx'
  uploaded: string
  status: 'processed' | 'processing' | 'failed'
  pages: number
  fileSizeBytes?: number
  totalChunks?: number
  needsOcrReview?: boolean
  isEmpty?: boolean
  preview: string[]
}

export interface Source {
  n: number
  docId: string
  docTitle: string
  page: number
  quote: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  timestamp?: number
  feedback?: 'up' | 'down' | null
  feedbackReason?: string
  bookmarked?: boolean
  providerUsed?: string
  followups?: string[]
}

export interface Conversation {
  id: string
  title: string
  createdAt?: number
  updatedAt?: number
}

export interface SavedAnswer {
  id: string
  convId?: string
  question: string
  content: string
  sources: Source[]
  savedAt: number
}

export type LlmMode = 'auto' | 'gemini' | 'local'

export interface UserSettings {
  theme: 'dark' | 'light' | 'system'
  enterToSend: boolean
  displayName: string
  fontSize: 'compact' | 'normal' | 'large'
  llmMode: LlmMode
}

export interface AuthUser {
  user_id: string
  full_name: string
  email: string
  registration_no: string
  created_at: string
}

export interface Reply {
  content: string
  sources: Source[]
  providerUsed?: string
  followups?: string[]
}

export interface ChatService {
  listConversations(): Promise<Conversation[]>
  getMessages(id: string): Promise<Message[]>
  saveMessages(id: string, messages: Message[]): Promise<void>
  createConversation(title: string): Promise<Conversation>
  renameConversation(id: string, title: string): Promise<void>
  deleteConversation(id: string): Promise<void>
  reply(
    prompt: string,
    onToken: (t: string) => void,
    signal: AbortSignal,
    department?: string,
    llmProvider?: LlmMode,
    history?: Array<{ role: 'user' | 'assistant'; content: string }>
  ): Promise<Reply>
  suggestions(): string[]
}

export interface DocumentService {
  list(): Promise<Doc[]>
  get(id: string): Promise<Doc | undefined>
  upload(file: File, department?: string, category?: string): Promise<Doc>
  process(id: string, force?: boolean): Promise<void>
  remove(id: string): Promise<void>
}
