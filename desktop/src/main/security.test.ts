import { describe, expect, it } from 'vitest'
import { httpOrigin, isAllowedRequest, isAppPage, isExternalLink } from './security'

describe('httpOrigin', () => {
  it('maps websocket URLs to their http origin', () => {
    expect(httpOrigin('ws://localhost:8000/ws/classes/1/?token=x')).toBe('http://localhost:8000')
    expect(httpOrigin('wss://aib.example.org/ws/')).toBe('https://aib.example.org')
  })
  it('ignores non-network and malformed URLs', () => {
    expect(httpOrigin('file:///app/index.html')).toBeNull()
    expect(httpOrigin('not a url')).toBeNull()
  })
})

describe('isAppPage', () => {
  const packaged = { indexUrl: 'file:///Applications/AIB.app/out/renderer/index.html' }
  const dev = { rendererUrl: 'http://localhost:5173', indexUrl: packaged.indexUrl }

  it('accepts the bundled page, with or without a hash', () => {
    expect(isAppPage('file:///Applications/AIB.app/out/renderer/index.html#/x', packaged)).toBe(true)
  })
  it('rejects remote pages and other local files', () => {
    expect(isAppPage('https://evil.example/steal', packaged)).toBe(false)
    expect(isAppPage('file:///tmp/evil.html', packaged)).toBe(false)
  })
  it('accepts only the dev server in development', () => {
    expect(isAppPage('http://localhost:5173/', dev)).toBe(true)
    expect(isAppPage('http://localhost:8000/', dev)).toBe(false)
    expect(isAppPage('file:///Applications/AIB.app/out/renderer/index.html', dev)).toBe(false)
  })
})

describe('isAllowedRequest', () => {
  const allowed = { serverUrl: 'http://localhost:8000' }

  it('allows the configured server over http and websockets', () => {
    expect(isAllowedRequest('http://localhost:8000/api/classes', allowed)).toBe(true)
    expect(isAllowedRequest('ws://localhost:8000/ws/classes/3/?token=t', allowed)).toBe(true)
  })
  it('blocks every other host, port or scheme', () => {
    expect(isAllowedRequest('https://tracker.example/pixel.png', allowed)).toBe(false)
    expect(isAllowedRequest('http://localhost:9000/api', allowed)).toBe(false)
    expect(isAllowedRequest('https://localhost:8000/api', allowed)).toBe(false)
  })
  it('allows local schemes and the dev server', () => {
    expect(isAllowedRequest('file:///app/index.html', allowed)).toBe(true)
    expect(isAllowedRequest('data:image/png;base64,AAAA', allowed)).toBe(true)
    expect(isAllowedRequest('ws://localhost:5173/', { ...allowed, rendererUrl: 'http://localhost:5173' })).toBe(true)
  })
})

it('hands only http(s) links to the system browser', () => {
  expect(isExternalLink('https://edukors.org/graph/')).toBe(true)
  expect(isExternalLink('file:///etc/passwd')).toBe(false)
  expect(isExternalLink('javascript:alert(1)')).toBe(false)
})
