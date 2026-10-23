/**
 * Where the renderer may navigate and which hosts it may reach. Pure functions, unit-tested.
 *
 * The renderer shows LLM-written Markdown, so a link or image can point anywhere. Navigating
 * away would hand the preload bridge (and the JWTs it exposes) to a remote page, and network
 * requests could leak data, so both are limited to the app itself and the configured server.
 */

const NETWORK_SCHEMES: Record<string, string> = { 'http:': 'http:', 'https:': 'https:', 'ws:': 'http:', 'wss:': 'https:' }

/** Origin of a URL with ws(s) mapped to http(s), or null for non-network or malformed URLs. */
export function httpOrigin(url: string): string | null {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  const scheme = NETWORK_SCHEMES[parsed.protocol]
  return scheme ? `${scheme}//${parsed.host}` : null
}

/** Is `url` the app's own page (the dev server, or the bundled index.html)? */
export function isAppPage(url: string, app: { rendererUrl?: string; indexUrl: string }): boolean {
  if (app.rendererUrl) return httpOrigin(url) !== null && httpOrigin(url) === httpOrigin(app.rendererUrl)
  try {
    const parsed = new URL(url)
    parsed.hash = ''
    parsed.search = ''
    return parsed.href === new URL(app.indexUrl).href
  } catch {
    return false
  }
}

/** May the renderer send this request? Local schemes always; network only to the server or the dev server. */
export function isAllowedRequest(url: string, allowed: { serverUrl: string; rendererUrl?: string }): boolean {
  let protocol: string
  try {
    protocol = new URL(url).protocol
  } catch {
    return false
  }
  if (!(protocol in NETWORK_SCHEMES)) return true // file:, data:, blob:, devtools:…
  const origin = httpOrigin(url)
  return origin === httpOrigin(allowed.serverUrl) || (!!allowed.rendererUrl && origin === httpOrigin(allowed.rendererUrl))
}

/** Links worth handing to the system browser. */
export const isExternalLink = (url: string): boolean => /^https?:\/\//i.test(url)
