import { create } from 'zustand'
import { ApiClient } from './api'
import { applyEvent, initialClassState, type ClassState } from './events'
import type { AuthResponse, ClassInfo, Graph, ServerEvent, Tokens, User } from './types'

interface Session extends Tokens {
  user: User
}

interface AppState {
  ready: boolean
  serverUrl: string
  user: User | null
  api: ApiClient
  cls: ClassState
  init(): Promise<void>
  setServerUrl(url: string): Promise<void>
  login(email: string, password: string): Promise<void>
  register(email: string, password: string, fullName: string): Promise<void>
  logout(): Promise<void>
  openClass(id: number | null): void
  setClassInfo(info: ClassInfo): void
  setGraph(graph: Graph): void
  dispatch(event: ServerEvent): void
  clearHighlight(nodeId: number): void
  clearAnswered(): void
}

const bridge = (): Window['aib'] | undefined => (typeof window !== 'undefined' ? window.aib : undefined)

function makeApi(baseUrl: string, tokens: Tokens | null, onTokens: (t: Tokens | null) => void): ApiClient {
  return new ApiClient({ baseUrl, tokens, onTokens })
}

export const useApp = create<AppState>((set, get) => {
  const persist = (tokens: Tokens | null): void => {
    const user = get().user
    if (tokens && user) {
      void bridge()?.tokens.set(JSON.stringify({ ...tokens, user }))
    } else if (!tokens) {
      void bridge()?.tokens.clear()
      set({ user: null })
    }
  }

  const startSession = async (auth: AuthResponse): Promise<void> => {
    set({ user: auth.user })
    get().api.setTokens({ access: auth.access, refresh: auth.refresh })
  }

  return {
    ready: false,
    serverUrl: 'http://localhost:8000',
    user: null,
    api: makeApi('http://localhost:8000', null, persist),
    cls: initialClassState(),

    async init() {
      const serverUrl = (await bridge()?.server.get()) ?? 'http://localhost:8000'
      let session: Session | null = null
      try {
        const raw = await bridge()?.tokens.get()
        session = raw ? (JSON.parse(raw) as Session) : null
      } catch {
        session = null
      }
      const api = makeApi(serverUrl, session ? { access: session.access, refresh: session.refresh } : null, persist)
      set({ serverUrl, api, user: session?.user ?? null })
      if (session) {
        try {
          const user = await api.get<User>('/auth/me')
          set({ user })
        } catch {
          set({ user: null })
          await bridge()?.tokens.clear()
        }
      }
      set({ ready: true })
    },

    async setServerUrl(url) {
      const clean = url.trim().replace(/\/+$/, '')
      await bridge()?.server.set(clean)
      set({ serverUrl: clean, api: makeApi(clean, get().api.tokens, persist) })
    },

    async login(email, password) {
      const auth = await get().api.post<AuthResponse>('/auth/login', { email, password })
      await startSession(auth)
    },

    async register(email, password, fullName) {
      const auth = await get().api.post<AuthResponse>('/auth/register', { email, password, full_name: fullName })
      await startSession(auth)
    },

    async logout() {
      get().api.setTokens(null)
      set({ user: null, cls: initialClassState() })
    },

    openClass(id) {
      set({ cls: initialClassState(id) })
    },
    setClassInfo(info) {
      set((s) => ({ cls: { ...s.cls, classInfo: info } }))
    },
    setGraph(graph) {
      set((s) => ({ cls: { ...s.cls, graph } }))
    },
    dispatch(event) {
      set((s) => ({ cls: applyEvent(s.cls, event) }))
    },
    clearHighlight(nodeId) {
      set((s) => ({ cls: { ...s.cls, highlights: s.cls.highlights.filter((id) => id !== nodeId) } }))
    },
    clearAnswered() {
      set((s) => ({ cls: { ...s.cls, answeredQuestion: null } }))
    }
  }
})

export const isStaff = (info: ClassInfo | null): boolean => info?.role === 'professor' || info?.role === 'assistant'
