import { describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError, errorMessage } from './api'
import type { Tokens } from './types'

const json = (status: number, body: unknown): Response =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  })

describe('ApiClient', () => {
  it('sends the bearer token and parses JSON', async () => {
    const fetchFn = vi.fn(async () => json(200, { ok: true }))
    const api = new ApiClient({ baseUrl: 'http://srv/', tokens: { access: 'A', refresh: 'R' }, fetchFn })
    expect(await api.get('/classes')).toEqual({ ok: true })
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://srv/api/classes')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer A')
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    const seen: string[] = []
    const fetchFn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const u = String(url)
      if (u.endsWith('/auth/refresh')) return json(200, { access: 'A2', refresh: 'R2', user: {} })
      const auth = (init?.headers as Record<string, string>).Authorization
      seen.push(auth)
      return auth === 'Bearer A2' ? json(200, { n: 1 }) : json(401, { detail: 'Unauthorized' })
    })
    const saved: (Tokens | null)[] = []
    const api = new ApiClient({
      baseUrl: 'http://srv',
      tokens: { access: 'A', refresh: 'R' },
      fetchFn: fetchFn as typeof fetch,
      onTokens: (t) => saved.push(t)
    })
    const [a, b] = await Promise.all([api.get('/x'), api.get('/y')])
    expect(a).toEqual({ n: 1 })
    expect(b).toEqual({ n: 1 })
    const refreshCalls = fetchFn.mock.calls.filter(([u]) => String(u).endsWith('/auth/refresh'))
    expect(refreshCalls).toHaveLength(1)
    expect(saved).toEqual([{ access: 'A2', refresh: 'R2' }])
    expect(api.tokens?.access).toBe('A2')
  })

  it('logs out when the refresh token is rejected', async () => {
    const fetchFn = vi.fn(async (url: string | URL | Request) =>
      String(url).endsWith('/auth/refresh') ? json(401, { detail: 'expired' }) : json(401, { detail: 'Unauthorized' })
    )
    const saved: (Tokens | null)[] = []
    const api = new ApiClient({
      baseUrl: 'http://srv',
      tokens: { access: 'A', refresh: 'R' },
      fetchFn: fetchFn as typeof fetch,
      onTokens: (t) => saved.push(t)
    })
    await expect(api.get('/x')).rejects.toMatchObject({ status: 401 })
    expect(saved).toEqual([null])
    expect(api.tokens).toBeNull()
  })

  it('does not try to refresh on auth endpoints', async () => {
    const fetchFn = vi.fn(async () => json(401, { detail: 'Invalid email or password' }))
    const api = new ApiClient({ baseUrl: 'http://srv', tokens: null, fetchFn })
    await expect(api.post('/auth/login', {})).rejects.toThrow('Invalid email or password')
    expect(fetchFn).toHaveBeenCalledTimes(1)
  })

  it('surfaces server error details', async () => {
    const fetchFn = vi.fn(async () => json(409, { detail: 'You already asked your question on this node' }))
    const api = new ApiClient({ baseUrl: 'http://srv', tokens: { access: 'A', refresh: 'R' }, fetchFn })
    const err = (await api.post('/q', { text: 'x' }).catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.message).toBe('You already asked your question on this node')
  })

  it('returns undefined for 204', async () => {
    const api = new ApiClient({ baseUrl: 'http://srv', tokens: null, fetchFn: async () => new Response(null, { status: 204 }) })
    expect(await api.del('/x')).toBeUndefined()
  })

  it('builds the websocket URL from the server URL', () => {
    const api = new ApiClient({ baseUrl: 'https://srv.example', tokens: { access: 'a b', refresh: 'r' } })
    expect(api.wsUrl(3)).toBe('wss://srv.example/ws/classes/3/?token=a%20b')
  })
})

describe('errorMessage', () => {
  it('joins validation errors', () => {
    expect(errorMessage({ detail: [{ msg: 'field required' }, { msg: 'bad' }] }, 422)).toBe('field required; bad')
    expect(errorMessage(null, 500)).toBe('Request failed (500)')
  })
})
