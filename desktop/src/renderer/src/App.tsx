import { useEffect, useState } from 'react'
import { useApp } from './lib/store'
import Login from './pages/Login'
import ClassList from './pages/ClassList'
import ClassPage from './pages/ClassPage'

export default function App(): JSX.Element {
  const { ready, user, init, logout } = useApp()
  const [classId, setClassId] = useState<number | null>(null)

  useEffect(() => {
    void init()
  }, [init])

  useEffect(() => {
    if (!user) setClassId(null)
  }, [user])

  if (!ready) return <div className="center muted">Loading…</div>
  if (!user) return <Login />

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => setClassId(null)} title="All classes">
          <span className="brand-mark">◆</span> AIB Graph
        </button>
        <div className="spacer" />
        <span className="muted small" data-testid="current-user">
          {user.full_name || user.email}
        </span>
        <button className="ghost" onClick={() => void logout()}>
          Sign out
        </button>
      </header>
      <main className="content">
        {classId === null ? (
          <ClassList onOpen={setClassId} />
        ) : (
          <ClassPage classId={classId} onBack={() => setClassId(null)} />
        )}
      </main>
    </div>
  )
}
