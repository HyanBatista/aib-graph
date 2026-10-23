import { useState, type FormEvent } from 'react'
import { useApp } from '../lib/store'
import { useAction, useResource } from '../lib/hooks'
import { STATUS_LABEL } from '../lib/format'
import type { ClassInfo } from '../lib/types'

export default function ClassList({ onOpen }: { onOpen: (id: number) => void }): JSX.Element {
  const api = useApp((s) => s.api)
  const classes = useResource(() => api.get<ClassInfo[]>('/classes'), [api])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const create = useAction()
  const join = useAction()

  const onCreate = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    const c = await create.run(() => api.post<ClassInfo>('/classes', { name }))
    if (c) onOpen(c.id)
  }
  const onJoin = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    const c = await join.run(() => api.post<ClassInfo>('/classes/join', { invite_code: code }))
    if (c) onOpen(c.id)
  }

  return (
    <div className="page">
      <h2>Your classes</h2>
      {classes.error && <div className="error">{classes.error}</div>}
      {classes.loading && !classes.data && <p className="muted">Loading…</p>}
      <div className="class-grid">
        {classes.data?.map((c) => (
          <button key={c.id} className="card class-card" onClick={() => onOpen(c.id)} data-testid="class-card">
            <div className="row">
              <span className={`badge status-${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span>
              <span className="spacer" />
              <span className="badge role">{c.role}</span>
            </div>
            <h3>{c.name}</h3>
            <p className="muted small">{c.book_title ?? 'No book yet'}</p>
            <div className="progress">
              <div style={{ width: `${c.topics_total ? (100 * c.topics_covered) / c.topics_total : 0}%` }} />
            </div>
            <p className="muted small">
              {c.topics_covered}/{c.topics_total} topics · {c.members} members · {c.professor}
            </p>
          </button>
        ))}
        {classes.data?.length === 0 && <p className="muted">You are not in any class yet.</p>}
      </div>

      <div className="two-col">
        <form className="card" onSubmit={(e) => void onCreate(e)}>
          <h3>Create a class</h3>
          <p className="muted small">You will be its professor and can upload the book.</p>
          <div className="row">
            <input placeholder="Class name" value={name} onChange={(e) => setName(e.target.value)} required />
            <button className="primary" disabled={create.busy}>
              Create
            </button>
          </div>
          {create.error && <div className="error">{create.error}</div>}
        </form>
        <form className="card" onSubmit={(e) => void onJoin(e)}>
          <h3>Join a class</h3>
          <p className="muted small">Ask your professor for the invite code.</p>
          <div className="row">
            <input
              placeholder="Invite code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              required
            />
            <button className="primary" disabled={join.busy}>
              Join
            </button>
          </div>
          {join.error && <div className="error">{join.error}</div>}
        </form>
      </div>
    </div>
  )
}
