import type { ServerEvent } from './types'

export interface SocketOptions {
  url: () => string
  onEvent: (event: ServerEvent) => void
  onStatus?: (connected: boolean) => void
}

/** Class websocket with exponential reconnect and a keepalive ping. Returns a close function. */
export function connectClassSocket({ url, onEvent, onStatus }: SocketOptions): () => void {
  let socket: WebSocket | null = null
  let closed = false
  let attempt = 0
  let ping: ReturnType<typeof setInterval> | null = null
  let retry: ReturnType<typeof setTimeout> | null = null

  const open = (): void => {
    socket = new WebSocket(url())
    socket.onopen = () => {
      attempt = 0
      onStatus?.(true)
      ping = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('{"type":"ping"}'), 25_000)
    }
    socket.onmessage = (msg) => {
      try {
        const data = JSON.parse(String(msg.data)) as ServerEvent
        if (data.event && data.event !== 'pong') onEvent(data)
      } catch {
        /* ignore malformed frames */
      }
    }
    socket.onclose = (ev) => {
      if (ping) clearInterval(ping)
      onStatus?.(false)
      // 4403: not a member / bad token. The token may have just been refreshed, so still retry, but slowly.
      if (closed) return
      const delay = Math.min(30_000, 1000 * 2 ** attempt) * (ev.code === 4403 ? 3 : 1)
      attempt += 1
      retry = setTimeout(open, delay)
    }
  }

  open()
  return () => {
    closed = true
    if (retry) clearTimeout(retry)
    if (ping) clearInterval(ping)
    socket?.close()
  }
}
