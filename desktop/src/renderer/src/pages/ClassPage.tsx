import { useEffect, useState } from 'react'
import { isStaff, useApp } from '../lib/store'
import { connectClassSocket } from '../lib/ws'
import { STATUS_LABEL } from '../lib/format'
import type { ClassInfo } from '../lib/types'
import BookSetup from '../components/BookSetup'
import IndexEditor from '../components/IndexEditor'
import GraphTab from '../components/GraphTab'
import TestTab from '../components/TestTab'
import Dashboard from '../components/Dashboard'
import Members from '../components/Members'

type Tab = 'setup' | 'index' | 'graph' | 'test' | 'dashboard' | 'members'

const GRAPH_STATUSES = ['growing', 'complete', 'frozen']

export default function ClassPage({ classId, onBack }: { classId: number; onBack: () => void }): JSX.Element {
  const { api, openClass, setClassInfo, dispatch } = useApp()
  const cls = useApp((s) => s.cls)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [tab, setTab] = useState<Tab | null>(null)

  useEffect(() => {
    openClass(classId)
    const close = connectClassSocket({ url: () => useApp.getState().api.wsUrl(classId), onEvent: dispatch, onStatus: setConnected })
    return () => {
      close()
      openClass(null)
    }
  }, [classId, openClass, dispatch])

  useEffect(() => {
    api
      .get<ClassInfo>(`/classes/${classId}`)
      .then((info) => {
        setClassInfo(info)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [api, classId, cls.versions.class, setClassInfo])

  const info = cls.classInfo
  const staff = isStaff(info)
  const hasGraph = info ? GRAPH_STATUSES.includes(info.status) : false
  const tabs: { id: Tab; label: string }[] = []
  if (info) {
    if (!hasGraph && info.status !== 'review') tabs.push({ id: 'setup', label: 'Book' })
    if (info.status === 'review') tabs.push({ id: 'index', label: 'Index' })
    if (hasGraph) tabs.push({ id: 'graph', label: 'Graph' })
    if (info.status === 'frozen') tabs.push({ id: 'test', label: 'Test' })
    if (hasGraph) tabs.push({ id: 'dashboard', label: 'Dashboard' })
    if (staff) tabs.push({ id: 'members', label: 'Members' })
  }
  const active = tab && tabs.some((t) => t.id === tab) ? tab : tabs[0]?.id

  return (
    <div className="class-page">
      <div className="class-header">
        <button className="ghost" onClick={onBack}>
          ← Classes
        </button>
        <div>
          <h2>{info?.name ?? 'Loading…'}</h2>
          {info && (
            <div className="row small muted">
              <span className={`badge status-${info.status}`}>{STATUS_LABEL[info.status] ?? info.status}</span>
              <span>{info.book_title ?? 'No book yet'}</span>
              <span>·</span>
              <span>you are {info.role}</span>
              <span className={`dot ${connected ? 'on' : 'off'}`} title={connected ? 'Live' : 'Reconnecting…'} />
            </div>
          )}
        </div>
        <div className="spacer" />
        {cls.job && <span className="badge job">{cls.job}</span>}
        <nav className="tabs">
          {tabs.map((t) => (
            <button key={t.id} className={t.id === active ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      {error && <div className="error">{error}</div>}
      {info && (
        <div className="class-body">
          {active === 'setup' && <BookSetup info={info} />}
          {active === 'index' && <IndexEditor info={info} />}
          {active === 'graph' && <GraphTab info={info} />}
          {active === 'test' && <TestTab info={info} />}
          {active === 'dashboard' && <Dashboard info={info} />}
          {active === 'members' && <Members info={info} />}
        </div>
      )}
    </div>
  )
}
