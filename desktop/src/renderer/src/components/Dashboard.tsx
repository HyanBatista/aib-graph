import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'
import { isStaff, useApp } from '../lib/store'
import { useResource } from '../lib/hooks'
import { OUTCOME_LABEL, date, dateTime, pct, seq } from '../lib/format'
import type { ClassInfo, ClassMetrics, StudentMetrics } from '../lib/types'

const AXIS = { stroke: 'var(--text-muted)', fontSize: 12 }
const GRID = <CartesianGrid stroke="var(--grid)" vertical={false} />
const TOOLTIP_STYLE = {
  contentStyle: { background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' },
  labelStyle: { color: 'var(--text)' },
  cursor: { fill: 'var(--hover)' }
}

export default function Dashboard({ info }: { info: ClassInfo }): JSX.Element {
  const user = useApp((s) => s.user)
  const [student, setStudent] = useState<number | null>(null)
  if (!isStaff(info)) return <StudentDashboard info={info} studentId={user?.id ?? 0} />
  if (student !== null) {
    return (
      <div>
        <button className="ghost" onClick={() => setStudent(null)}>
          ← Class dashboard
        </button>
        <StudentDashboard info={info} studentId={student} />
      </div>
    )
  }
  return <ClassDashboard info={info} onStudent={setStudent} />
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }): JSX.Element {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {hint && <div className="tile-hint">{hint}</div>}
    </div>
  )
}

function ChartCard({ title, children, height = 240 }: { title: string; children: JSX.Element; height?: number }): JSX.Element {
  return (
    <div className="card chart-card">
      <h4>{title}</h4>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ClassDashboard({ info, onStudent }: { info: ClassInfo; onStudent: (id: number) => void }): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.metrics)
  const m = useResource(() => api.get<ClassMetrics>(`/classes/${info.id}/metrics`), [api, info.id, version])
  if (m.error) return <div className="error">{m.error}</div>
  if (!m.data) return <div className="center muted">Loading…</div>
  const d = m.data
  const s = d.summary

  const hardest = [...d.per_node]
    .filter((n) => n.avg_score !== null)
    .sort((a, b) => (a.avg_score ?? 0) - (b.avg_score ?? 0))
    .map((n) => ({ ...n, avg: Math.round((n.avg_score ?? 0) * 100) }))
  const outcomes = Object.entries(d.question_outcomes).map(([k, v]) => ({ name: OUTCOME_LABEL[k] ?? k, count: v }))
  const growth = d.growth.map((g) => ({ ...g, label: date(g.date) }))

  return (
    <div className="page dashboard">
      <div className="tiles">
        <Tile label="Students" value={s.students} />
        <Tile label="Coverage" value={pct(s.coverage)} hint={`${s.nodes}/${s.topics_total} topics`} />
        <Tile label="Avg quiz" value={pct(s.avg_quiz)} />
        <Tile label="Completion" value={pct(s.completion_rate)} hint="student × node" />
        <Tile label="Questions" value={s.questions} hint={`${d.question_outcomes.created_node ?? 0} created nodes`} />
        <Tile
          label="Test avg"
          value={pct(d.test.avg_score)}
          hint={d.test.status ? `${d.test.attempts} attempts · ${d.test.status}` : 'no test yet'}
        />
      </div>

      <div className="two-col">
        <ChartCard title="Graph growth (nodes)">
          <LineChart data={growth} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip {...TOOLTIP_STYLE} cursor={{ stroke: 'var(--text-muted)' }} />
            <Line type="monotone" dataKey="nodes" name="Nodes" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4 }} />
          </LineChart>
        </ChartCard>
        <ChartCard title="Questions by outcome">
          <BarChart data={outcomes} layout="vertical" margin={{ top: 8, right: 24, left: 40, bottom: 0 }}>
            <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} tickLine={false} axisLine={false} width={150} />
            <Tooltip {...TOOLTIP_STYLE} />
            <Bar dataKey="count" name="Questions" fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={18} label={{ position: 'right', fill: 'var(--text-muted)', fontSize: 12 }} />
          </BarChart>
        </ChartCard>
      </div>

      <ChartCard title="Average quiz score per node — hardest first" height={Math.max(200, hardest.length * 26)}>
        <BarChart data={hardest} layout="vertical" margin={{ top: 4, right: 40, left: 40, bottom: 0 }}>
          <XAxis type="number" domain={[0, 100]} unit="%" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="title" tick={AXIS} tickLine={false} axisLine={false} width={220} interval={0} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${v}%`, 'Avg score']} />
          <Bar dataKey="avg" fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={14} />
        </BarChart>
      </ChartCard>

      <div className="card">
        <h4>Participation</h4>
        <table className="table">
          <thead>
            <tr>
              <th>Student</th>
              <th className="num">Visited</th>
              <th className="num">Completed</th>
              <th className="num">Avg quiz</th>
              <th className="num">Questions</th>
              <th className="num">Nodes created</th>
              <th className="num">Test</th>
            </tr>
          </thead>
          <tbody>
            {d.participation.map((p) => (
              <tr key={p.student_id} className="clickable" onClick={() => onStudent(p.student_id)} title="Open student dashboard">
                <td>{p.name}</td>
                <td className="num">{p.visited}</td>
                <td className="num">{p.completed}</td>
                <td className="num">{pct(p.avg_score)}</td>
                <td className="num">{p.questions}</td>
                <td className="num">{p.nodes_created}</td>
                <td className="num">{pct(p.test_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {d.test.status && (
        <ChartCard title="Test score distribution">
          <BarChart data={d.test.distribution} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="bucket" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip {...TOOLTIP_STYLE} />
            <Bar dataKey="count" name="Students" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
      )}

      <MasteryHeatmap metrics={d} onStudent={onStudent} />
    </div>
  )
}

function MasteryHeatmap({ metrics, onStudent }: { metrics: ClassMetrics; onStudent: (id: number) => void }): JSX.Element {
  const score = new Map(metrics.mastery.map((c) => [`${c.student_id}:${c.node_id}`, c.score]))
  return (
    <div className="card">
      <h4>Quiz score by topic and student</h4>
      <div className="heatmap-wrap">
        <table className="heatmap">
          <thead>
            <tr>
              <th />
              {metrics.participation.map((p) => (
                <th key={p.student_id}>
                  <button className="link small" onClick={() => onStudent(p.student_id)}>
                    {p.name.split(' ')[0]}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.per_node.map((n) => (
              <tr key={n.node_id}>
                <th className="row-head">{n.title}</th>
                {metrics.participation.map((p) => {
                  const v = score.get(`${p.student_id}:${n.node_id}`)
                  return (
                    <td
                      key={p.student_id}
                      style={{ background: seq(v) }}
                      className={v !== undefined && v > 0.6 ? 'dark-cell' : ''}
                      title={`${p.name} · ${n.title}: ${v === undefined ? 'not taken' : pct(v)}`}
                    >
                      {v === undefined ? '' : Math.round(v * 100)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Darker = higher score; empty = quiz not taken. Values in %.</p>
    </div>
  )
}

function StudentDashboard({ info, studentId }: { info: ClassInfo; studentId: number }): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.metrics)
  const m = useResource(
    () => api.get<StudentMetrics>(`/classes/${info.id}/metrics/students/${studentId}`),
    [api, info.id, studentId, version]
  )
  if (m.error) return <div className="error">{m.error}</div>
  if (!m.data) return <div className="center muted">Loading…</div>
  const d = m.data
  const s = d.summary
  const rows = d.per_node
    .filter((n) => n.quiz_score !== null || n.class_avg !== null)
    .map((n) => ({
      title: n.title,
      mine: n.quiz_score === null ? null : Math.round(n.quiz_score * 100),
      cls: n.class_avg === null ? null : Math.round(n.class_avg * 100)
    }))

  return (
    <div className="page dashboard">
      <h3>{d.student.name}</h3>
      <div className="tiles">
        <Tile label="Completed" value={`${s.completed}/${s.nodes_total}`} hint={`${s.visited} visited`} />
        <Tile label="Avg quiz" value={pct(s.avg_score)} />
        <Tile label="Questions" value={s.questions} />
        <Tile label="Nodes created" value={s.nodes_created} hint="by your questions" />
        <Tile label="Final test" value={pct(s.test_score)} />
      </div>

      <ChartCard title="Quiz score vs class average" height={Math.max(220, rows.length * 34)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 40, bottom: 0 }} barGap={2}>
          <XAxis type="number" domain={[0, 100]} unit="%" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="title" tick={AXIS} tickLine={false} axisLine={false} width={220} interval={0} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v) => (v === null ? '—' : `${v}%`)} />
          <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-muted)' }} />
          <Bar dataKey="mine" name={info.role === 'student' ? 'You' : 'Student'} fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={10} />
          <Bar dataKey="cls" name="Class average" fill="var(--series-2)" radius={[0, 4, 4, 0]} barSize={10} />
        </BarChart>
      </ChartCard>

      <div className="two-col">
        <div className="card">
          <h4>Topic mastery</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Topic</th>
                <th>State</th>
                <th className="num">Mastery</th>
              </tr>
            </thead>
            <tbody>
              {d.per_node.map((n) => (
                <tr key={n.node_id}>
                  <td>{n.title}</td>
                  <td>
                    <span className={`badge my-${n.state}`}>{n.state.replace('_', ' ')}</span>
                  </td>
                  <td className="num">
                    <div className="meter" title={pct(n.mastery)}>
                      <div style={{ width: `${(n.mastery ?? 0) * 100}%` }} />
                    </div>
                    {pct(n.mastery)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h4>Questions asked</h4>
          {d.questions.length === 0 && <p className="muted small">No questions yet.</p>}
          <ul className="question-list">
            {d.questions.map((q) => (
              <li key={q.id}>
                <div className="small muted">
                  {q.node_title} · {dateTime(q.created_at)}
                </div>
                <div>{q.text}</div>
                <div className="small">
                  <span className={`badge outcome-${q.outcome}`}>{OUTCOME_LABEL[q.outcome]}</span>
                  {q.target_title && <span className="muted"> → {q.target_title}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
