import type { Conversation, Message, SavedAnswer, UserSettings } from './types'

const CONV_KEY = 'unimind_conversations'
const MSG_KEY_PREFIX = 'unimind_messages_'
const SAVED_KEY = 'unimind_saved_answers'
const SETTINGS_KEY = 'unimind_settings'

export const DEFAULT_SETTINGS: UserSettings = {
  theme: 'dark',
  enterToSend: true,
  displayName: 'Guest Student',
  fontSize: 'normal',
  llmMode: 'auto',
}

export function getConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CONV_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // Filter out any legacy seeded demo welcome entry if it has no real user interaction
    return parsed.filter((c) => c && typeof c.id === 'string' && c.id !== 'welcome-conv')
  } catch {
    return []
  }
}

export function conversationExists(id: string): boolean {
  return getConversations().some((c) => c.id === id)
}

export function saveConversation(conv: Conversation): void {
  try {
    const list = getConversations()
    const idx = list.findIndex((c) => c.id === conv.id)
    if (idx >= 0) {
      list[idx] = { ...list[idx], ...conv, updatedAt: Date.now() }
    } else {
      list.unshift({ ...conv, createdAt: Date.now(), updatedAt: Date.now() })
    }
    localStorage.setItem(CONV_KEY, JSON.stringify(list))
    window.dispatchEvent(new CustomEvent('unimind:conversations_updated'))
  } catch (e) {
    console.error('Failed to save conversation', e)
  }
}

export function deleteConversation(id: string): void {
  try {
    const list = getConversations().filter((c) => c.id !== id)
    localStorage.setItem(CONV_KEY, JSON.stringify(list))
    localStorage.removeItem(MSG_KEY_PREFIX + id)
    window.dispatchEvent(new CustomEvent('unimind:conversations_updated'))
  } catch (e) {
    console.error('Failed to delete conversation', e)
  }
}

export function renameConversation(id: string, newTitle: string): void {
  try {
    const clean = newTitle.trim()
    if (!clean) return
    const list = getConversations().map((c) =>
      c.id === id ? { ...c, title: clean, updatedAt: Date.now() } : c
    )
    localStorage.setItem(CONV_KEY, JSON.stringify(list))
    window.dispatchEvent(new CustomEvent('unimind:conversations_updated'))
  } catch (e) {
    console.error('Failed to rename conversation', e)
  }
}

export function getMessages(convId: string): Message[] {
  try {
    const raw = localStorage.getItem(MSG_KEY_PREFIX + convId)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveMessages(convId: string, messages: Message[]): void {
  try {
    localStorage.setItem(MSG_KEY_PREFIX + convId, JSON.stringify(messages))
    const list = getConversations()
    const idx = list.findIndex((c) => c.id === convId)
    if (idx >= 0) {
      list[idx].updatedAt = Date.now()
      // Move updated conversation to top
      const [updated] = list.splice(idx, 1)
      list.unshift(updated)
      localStorage.setItem(CONV_KEY, JSON.stringify(list))
      window.dispatchEvent(new CustomEvent('unimind:conversations_updated'))
    }
  } catch (e) {
    console.error('Failed to save messages for ' + convId, e)
  }
}

export function getSavedAnswers(): SavedAnswer[] {
  try {
    const raw = localStorage.getItem(SAVED_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveAnswer(answer: Omit<SavedAnswer, 'id' | 'savedAt'>): SavedAnswer {
  const list = getSavedAnswers()
  const existing = list.find((a) => a.content === answer.content)
  if (existing) return existing

  const newAnswer: SavedAnswer = {
    ...answer,
    id: 'saved-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7),
    savedAt: Date.now(),
  }
  list.unshift(newAnswer)
  localStorage.setItem(SAVED_KEY, JSON.stringify(list))
  window.dispatchEvent(new CustomEvent('unimind:saved_answers_updated'))
  return newAnswer
}

export function removeSavedAnswer(id: string): void {
  try {
    const list = getSavedAnswers().filter((a) => a.id !== id)
    localStorage.setItem(SAVED_KEY, JSON.stringify(list))
    window.dispatchEvent(new CustomEvent('unimind:saved_answers_updated'))
  } catch (e) {
    console.error('Failed to remove saved answer', e)
  }
}

export function removeSavedAnswerByContent(content: string): void {
  try {
    const list = getSavedAnswers().filter((a) => a.content !== content)
    localStorage.setItem(SAVED_KEY, JSON.stringify(list))
    window.dispatchEvent(new CustomEvent('unimind:saved_answers_updated'))
  } catch (e) {
    console.error('Failed to remove saved answer by content', e)
  }
}

export function isAnswerSaved(content: string): boolean {
  return getSavedAnswers().some((a) => a.content === content)
}

export function getUserSettings(): UserSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const parsed = JSON.parse(raw)
    return {
      theme: parsed.theme === 'light' || parsed.theme === 'system' ? parsed.theme : 'dark',
      enterToSend: typeof parsed.enterToSend === 'boolean' ? parsed.enterToSend : true,
      displayName: typeof parsed.displayName === 'string' ? parsed.displayName : 'Guest Student',
      fontSize:
        parsed.fontSize === 'compact' || parsed.fontSize === 'large' ? parsed.fontSize : 'normal',
      llmMode:
        parsed.llmMode === 'gemini' || parsed.llmMode === 'local' ? parsed.llmMode : 'auto',
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function saveUserSettings(settings: Partial<UserSettings>): UserSettings {
  try {
    const current = getUserSettings()
    const updated = { ...current, ...settings }
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(updated))
    applyTheme(updated.theme)
    applyFontSize(updated.fontSize)
    window.dispatchEvent(new CustomEvent('unimind:settings_updated', { detail: updated }))
    return updated
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function applyTheme(theme: 'dark' | 'light' | 'system'): void {
  const root = document.documentElement
  let effectiveTheme: 'dark' | 'light' = 'dark'
  if (theme === 'system') {
    effectiveTheme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  } else {
    effectiveTheme = theme
  }
  root.setAttribute('data-theme', effectiveTheme)
}

export function applyFontSize(size: 'compact' | 'normal' | 'large'): void {
  document.documentElement.setAttribute('data-font-size', size)
}

export function clearAllLocalData(): void {
  try {
    const keysToRemove: string[] = [CONV_KEY, SAVED_KEY]
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(MSG_KEY_PREFIX)) {
        keysToRemove.push(k)
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k))
    window.dispatchEvent(new CustomEvent('unimind:conversations_updated'))
    window.dispatchEvent(new CustomEvent('unimind:saved_answers_updated'))
  } catch (e) {
    console.error('Failed to clear local data', e)
  }
}
