import { useState, type FormEvent } from 'react'
import { useApp } from '../lib/store'
import { useAction } from '../lib/hooks'

// Accounts created by `manage.py seed_demo` (server/demo/management/commands/seed_demo.py).
const DEMO_ACCOUNTS = [
  ['prof@demo.local', 'Prof. Marina Costa — professor'],
  ['ta1@demo.local', 'Rafael Lima — assistant'],
  ['ta2@demo.local', 'Júlia Souza — assistant'],
  ['ana@demo.local', 'Ana Silva — student'],
  ['bruno@demo.local', 'Bruno Santos — student'],
  ['carla@demo.local', 'Carla Oliveira — student'],
  ['diego@demo.local', 'Diego Pereira — student'],
  ['elisa@demo.local', 'Elisa Rocha — student'],
  ['felipe@demo.local', 'Felipe Alves — student']
] as const
const DEMO_PASSWORD = 'demo1234'

export default function Login(): JSX.Element {
  const { login, register, serverUrl, setServerUrl } = useApp()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [server, setServer] = useState(serverUrl)
  const [editServer, setEditServer] = useState(false)
  const { busy, error, run } = useAction()

  const submit = (e: FormEvent): void => {
    e.preventDefault()
    void run(() => (mode === 'login' ? login(email, password) : register(email, password, fullName)))
  }

  const demoLogin = (demoEmail: string): void => {
    if (!demoEmail) return
    setEmail(demoEmail)
    setPassword(DEMO_PASSWORD)
    void run(() => login(demoEmail, DEMO_PASSWORD))
  }

  return (
    <div className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="brand-mark big">◆</span>
          <h1>AIB Graph</h1>
          <p className="muted">Learning graphs that grow from your students' questions.</p>
        </div>

        {import.meta.env.DEV && (
          <label className="field">
            <span>Demo accounts</span>
            <select data-testid="demo-accounts" defaultValue="" onChange={(e) => demoLogin(e.target.value)} disabled={busy}>
              <option value="">Log in as a demo user…</option>
              {DEMO_ACCOUNTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}

        {mode === 'register' && (
          <label className="field">
            <span>Full name</span>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
          </label>
        )}
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            name="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            name="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={mode === 'register' ? 8 : undefined}
            required
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary wide" type="submit" disabled={busy}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <button type="button" className="link" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
          {mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}
        </button>

        <div className="server-row">
          {editServer ? (
            <>
              <input value={server} onChange={(e) => setServer(e.target.value)} aria-label="Server URL" />
              <button
                type="button"
                onClick={() => {
                  void setServerUrl(server)
                  setEditServer(false)
                }}
              >
                Save
              </button>
            </>
          ) : (
            <>
              <span className="muted small">Server: {serverUrl}</span>
              <button type="button" className="link small" onClick={() => setEditServer(true)}>
                change
              </button>
            </>
          )}
        </div>
      </form>
    </div>
  )
}
