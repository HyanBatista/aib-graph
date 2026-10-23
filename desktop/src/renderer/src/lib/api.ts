import type { Tokens } from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
  }
}

type FetchFn = typeof fetch

export interface ApiOptions {
  baseUrl: string
  tokens: Tokens | null
  onTokens?: (tokens: Tokens | null) => void
  fetchFn?: FetchFn
}

/** Extract a readable message from Django Ninja error bodies ({detail: str | [{msg}]}). */
export function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join('; ')
    }
  }
  return `Request failed (${status})`
}

export class ApiClient {
  baseUrl: string
  tokens: Tokens | null
  private onTokens?: (tokens: Tokens | null) => void
  private fetchFn: FetchFn
  private refreshing: Promise<boolean> | null = null

  constructor(opts: ApiOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '')
    this.tokens = opts.tokens
    this.onTokens = opts.onTokens
    this.fetchFn = opts.fetchFn ?? ((...args) => fetch(...args))
  }

  setTokens(tokens: Tokens | null): void {
    this.tokens = tokens
    this.onTokens?.(tokens)
  }

  url(path: string): string {
    return `${this.baseUrl}/api${path}`
  }

  private async send(method: string, path: string, body?: unknown): Promise<Response> {
    const headers: Record<string, string> = {}
    let payload: BodyInit | undefined
    if (body instanceof FormData) {
      payload = body
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json'
      payload = JSON.stringify(body)
    }
    if (this.tokens) headers.Authorization = `Bearer ${this.tokens.access}`
    return this.fetchFn(this.url(path), { method, headers, body: payload })
  }

  /** Refresh the access token once, even if several requests hit a 401 at the same time. */
  private refresh(): Promise<boolean> {
    if (!this.tokens) return Promise.resolve(false)
    if (!this.refreshing) {
      const refreshToken = this.tokens.refresh
      this.refreshing = (async () => {
        try {
          const res = await this.fetchFn(this.url('/auth/refresh'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: refreshToken })
          })
          if (!res.ok) {
            this.setTokens(null)
            return false
          }
          const data = await res.json()
          this.setTokens({ access: data.access, refresh: data.refresh })
          return true
        } catch {
          return false
        } finally {
          this.refreshing = null
        }
      })()
    }
    return this.refreshing
  }

  async raw(method: string, path: string, body?: unknown): Promise<Response> {
    let res = await this.send(method, path, body)
    if (res.status === 401 && this.tokens && !path.startsWith('/auth/')) {
      if (await this.refresh()) res = await this.send(method, path, body)
    }
    if (!res.ok) {
      let parsed: unknown = null
      try {
        parsed = await res.json()
      } catch {
        /* not JSON */
      }
      throw new ApiError(res.status, errorMessage(parsed, res.status))
    }
    return res
  }

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await this.raw(method, path, body)
    if (res.status === 204) return undefined as T
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path)
  }
  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body ?? {})
  }
  put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PUT', path, body)
  }
  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PATCH', path, body)
  }
  del<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path)
  }

  wsUrl(classId: number): string {
    const base = this.baseUrl.replace(/^http/, 'ws')
    return `${base}/ws/classes/${classId}/?token=${encodeURIComponent(this.tokens?.access ?? '')}`
  }
}
