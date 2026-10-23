import { useEffect, useState } from 'react'
import { isStaff, useApp } from '../lib/store'
import { useAction, useResource } from '../lib/hooks'
import { dateTime, pct } from '../lib/format'
import type { Attempt, ClassInfo, ItemAnswer, Test, TestItem } from '../lib/types'

type ItemDraft = Omit<TestItem, 'id' | 'node_title' | 'order'>

export default function TestTab({ info }: { info: ClassInfo }): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.test)
  const test = useResource(() => api.get<{ test: Test | null }>(`/classes/${info.id}/test`), [api, info.id, version])
  const action = useAction()
  const staff = isStaff(info)
  const t = test.data?.test ?? null

  const call = async (path: string): Promise<void> => {
    const r = await action.run(() => api.post<{ test: Test | null }>(`/classes/${info.id}/test/${path}`))
    if (r) test.setData(r)
  }

  if (test.error) return <div className="error">{test.error}</div>
  if (!test.data) return <div className="center muted">Loading…</div>

  if (!staff) return <StudentTest info={info} test={t} onChange={test.setData} />

  return (
    <div className="page">
      <div className="toolbar">
        <div>
          <h3>{t?.title ?? 'Final test'}</h3>
          {t && (
            <p className="muted small">
              <span className={`badge test-${t.status}`}>{t.status}</span> {t.items.length} items · covers {t.covered_nodes}/
              {t.total_nodes} nodes
            </p>
          )}
        </div>
        <div className="spacer" />
        {info.role === 'professor' && (!t || t.status === 'draft') && (
          <button onClick={() => void call('generate')} disabled={action.busy}>
            {t ? 'Regenerate with AI' : 'Generate test with AI'}
          </button>
        )}
        {info.role === 'professor' && t?.status === 'draft' && (
          <button className="primary" onClick={() => void call('publish')} disabled={action.busy}>
            Publish
          </button>
        )}
        {info.role === 'professor' && t?.status === 'published' && (
          <button className="danger" onClick={() => void call('close')} disabled={action.busy}>
            Close test
          </button>
        )}
      </div>
      {action.error && <div className="error">{action.error}</div>}
      {!t && <p className="muted">No test yet. The professor generates it from the frozen graph: every node gets at least one item.</p>}
      {t?.status === 'generating' && (
        <div className="notice row">
          <span className="spinner" /> The AI is writing the test…
        </div>
      )}
      {t?.status === 'draft' && <DraftEditor info={info} test={t} onChanged={() => void test.reload()} />}
      {t && (t.status === 'published' || t.status === 'closed') && <Attempts info={info} test={t} />}
    </div>
  )
}

function DraftEditor({ info, test, onChanged }: { info: ClassInfo; test: Test; onChanged: () => void }): JSX.Element {
  const graph = useApp((s) => s.cls.graph)
  const api = useApp((s) => s.api)
  const [nodes, setNodes] = useState(graph?.nodes ?? [])
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    if (!graph) void api.get<{ nodes: typeof nodes }>(`/classes/${info.id}/graph`).then((g) => setNodes(g.nodes))
  }, [api, graph, info.id])

  const covered = new Set(test.items.map((i) => i.node_id))
  const missing = nodes.filter((n) => !covered.has(n.id))
  return (
    <>
      {missing.length > 0 && (
        <div className="error">Nodes without an item (required before publishing): {missing.map((n) => n.title).join(', ')}</div>
      )}
      <div className="items">
        {test.items.map((item, i) => (
          <ItemEditor key={item.id} info={info} index={i} item={item} nodes={nodes} onChanged={onChanged} />
        ))}
      </div>
      {adding ? (
        <ItemEditor
          info={info}
          index={test.items.length}
          nodes={nodes}
          item={null}
          onChanged={() => {
            setAdding(false)
            onChanged()
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button onClick={() => setAdding(true)}>+ Add item</button>
      )}
    </>
  )
}

function ItemEditor({
  info,
  index,
  item,
  nodes,
  onChanged,
  onCancel
}: {
  info: ClassInfo
  index: number
  item: TestItem | null
  nodes: { id: number; title: string }[]
  onChanged: () => void
  onCancel?: () => void
}): JSX.Element {
  const api = useApp((s) => s.api)
  const initial: ItemDraft = item ?? {
    node_id: nodes[0]?.id ?? 0,
    kind: 'mcq',
    prompt: '',
    options: ['', '', '', ''],
    answer_index: 0,
    rubric: '',
    points: 1
  }
  const [d, setD] = useState<ItemDraft>(initial)
  const [dirty, setDirty] = useState(!item)
  const action = useAction()
  const set = (patch: Partial<ItemDraft>): void => {
    setD((x) => ({ ...x, ...patch }))
    setDirty(true)
  }

  const save = async (): Promise<void> => {
    const body = {
      node_id: d.node_id,
      kind: d.kind,
      prompt: d.prompt,
      options: d.kind === 'mcq' ? d.options.filter((o) => o.trim()) : [],
      answer_index: d.kind === 'mcq' ? d.answer_index : null,
      rubric: d.kind === 'open' ? d.rubric : '',
      points: d.points
    }
    const path = `/classes/${info.id}/test/items${item ? `/${item.id}` : ''}`
    const ok = await action.run(() => (item ? api.put(path, body) : api.post(path, body)))
    if (ok) {
      setDirty(false)
      onChanged()
    }
  }
  const remove = async (): Promise<void> => {
    if (!item) return
    const ok = await action.run(async () => {
      await api.del(`/classes/${info.id}/test/items/${item.id}`)
      return true
    })
    if (ok) onChanged()
  }

  return (
    <div className="card item-editor">
      <div className="row">
        <strong>#{index + 1}</strong>
        <select value={d.node_id} onChange={(e) => set({ node_id: Number(e.target.value) })}>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.title}
            </option>
          ))}
        </select>
        <select value={d.kind} onChange={(e) => set({ kind: e.target.value as 'mcq' | 'open' })}>
          <option value="mcq">Multiple choice</option>
          <option value="open">Open answer</option>
        </select>
        <label className="small">
          pts{' '}
          <input
            type="number"
            min={0.5}
            step={0.5}
            className="num"
            value={d.points}
            onChange={(e) => set({ points: Number(e.target.value) })}
          />
        </label>
        <div className="spacer" />
        {dirty && (
          <button className="primary small" onClick={() => void save()} disabled={action.busy}>
            Save
          </button>
        )}
        {item ? (
          <button className="icon danger" title="Delete" onClick={() => void remove()}>
            ✕
          </button>
        ) : (
          <button className="small" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <textarea rows={2} value={d.prompt} placeholder="Question" onChange={(e) => set({ prompt: e.target.value })} />
      {d.kind === 'mcq' ? (
        <div className="options-edit">
          {d.options.map((o, j) => (
            <div key={j} className="row">
              <input
                type="radio"
                name={`ans-${item?.id ?? 'new'}`}
                checked={d.answer_index === j}
                onChange={() => set({ answer_index: j })}
                title="Correct answer"
              />
              <input
                className="grow"
                value={o}
                placeholder={`Option ${j + 1}`}
                onChange={(e) => set({ options: d.options.map((x, k) => (k === j ? e.target.value : x)) })}
              />
              <button
                className="icon"
                onClick={() =>
                  set({
                    options: d.options.filter((_, k) => k !== j),
                    answer_index: d.answer_index === j ? 0 : (d.answer_index ?? 0) > j ? (d.answer_index ?? 1) - 1 : d.answer_index
                  })
                }
              >
                −
              </button>
            </div>
          ))}
          <button className="link small" onClick={() => set({ options: [...d.options, ''] })}>
            + option
          </button>
        </div>
      ) : (
        <textarea
          rows={2}
          value={d.rubric ?? ''}
          placeholder="Rubric: what a full-credit answer must contain"
          onChange={(e) => set({ rubric: e.target.value })}
        />
      )}
      {action.error && <div className="error">{action.error}</div>}
    </div>
  )
}

function Attempts({ info, test }: { info: ClassInfo; test: Test }): JSX.Element {
  const [open, setOpen] = useState<number | null>(null)
  const attempts = test.attempts ?? []
  return (
    <div className="two-col wide-left">
      <div className="card">
        <h4>Attempts ({attempts.length})</h4>
        {attempts.length === 0 && <p className="muted small">Nobody has taken the test yet.</p>}
        <table className="table">
          <thead>
            <tr>
              <th>Student</th>
              <th>Submitted</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {attempts.map((a) => (
              <tr key={a.id} className={open === a.id ? 'selected clickable' : 'clickable'} onClick={() => setOpen(a.id)}>
                <td>{a.student}</td>
                <td className="muted">{dateTime(a.submitted_at)}</td>
                <td>{a.pending ? <span className="muted">grading…</span> : pct(a.score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>{open !== null && <AttemptReview key={open} info={info} test={test} attemptId={open} staff />}</div>
    </div>
  )
}

function AttemptReview({
  info,
  test,
  attemptId,
  staff
}: {
  info: ClassInfo
  test: Test
  attemptId: number
  staff: boolean
}): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.test)
  const attempt = useResource(() => api.get<Attempt>(`/classes/${info.id}/test/attempts/${attemptId}`), [api, info.id, attemptId, version])
  if (attempt.error) return <div className="error">{attempt.error}</div>
  if (!attempt.data) return <p className="muted">Loading…</p>
  return <AttemptView info={info} test={test} attempt={attempt.data} staff={staff} onChanged={() => void attempt.reload()} />
}

function AttemptView({
  info,
  test,
  attempt,
  staff,
  onChanged
}: {
  info: ClassInfo
  test: Test
  attempt: Attempt
  staff: boolean
  onChanged?: () => void
}): JSX.Element {
  const byItem = new Map((attempt.answers ?? []).map((a) => [a.item_id, a]))
  return (
    <div className="card">
      <div className="row">
        <h4 className="grow">{staff ? attempt.student : 'Your result'}</h4>
        <span className="badge big">{attempt.pending ? 'grading…' : pct(attempt.score)}</span>
      </div>
      {test.items.map((item, i) => {
        const a = byItem.get(item.id)
        return (
          <div key={item.id} className="review-item">
            <p>
              <strong>{i + 1}.</strong> {item.prompt} <span className="muted small">({item.node_title})</span>
            </p>
            {item.kind === 'mcq' ? (
              <ul className="review-options">
                {item.options.map((o, j) => (
                  <li key={j} className={j === item.answer_index ? 'right' : a?.choice === j ? 'wrong' : ''}>
                    {a?.choice === j ? '● ' : '○ '}
                    {o}
                  </li>
                ))}
              </ul>
            ) : (
              <>
                <blockquote>{a?.text || <span className="muted">No answer</span>}</blockquote>
                {staff && item.rubric && <p className="small muted">Rubric: {item.rubric}</p>}
              </>
            )}
            {a && <AnswerGrade info={info} answer={a} staff={staff} onChanged={onChanged} />}
          </div>
        )
      })}
    </div>
  )
}

function AnswerGrade({
  info,
  answer,
  staff,
  onChanged
}: {
  info: ClassInfo
  answer: ItemAnswer
  staff: boolean
  onChanged?: () => void
}): JSX.Element {
  const api = useApp((s) => s.api)
  const [editing, setEditing] = useState(false)
  const [score, setScore] = useState(String(Math.round((answer.score ?? 0) * 100)))
  const [feedback, setFeedback] = useState(answer.feedback)
  const action = useAction()

  const save = async (): Promise<void> => {
    const ok = await action.run(() =>
      api.patch(`/classes/${info.id}/test/answers/${answer.id}`, { score: Number(score) / 100, feedback })
    )
    if (ok) {
      setEditing(false)
      onChanged?.()
    }
  }

  if (editing) {
    return (
      <div className="grade-edit">
        <label className="small">
          Score %{' '}
          <input type="number" min={0} max={100} className="num" value={score} onChange={(e) => setScore(e.target.value)} />
        </label>
        <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Feedback" />
        <div className="row">
          <button className="primary small" onClick={() => void save()} disabled={action.busy}>
            Save grade
          </button>
          <button className="small" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
        {action.error && <div className="error">{action.error}</div>}
      </div>
    )
  }
  return (
    <div className="grade small">
      {answer.score === null ? (
        <span className="muted">
          <span className="spinner tiny" /> grading…
        </span>
      ) : (
        <span className="badge">{pct(answer.score)}</span>
      )}
      {answer.graded_by && <span className="muted"> graded by {answer.graded_by}</span>}
      {answer.feedback && <span> — {answer.feedback}</span>}
      {staff && (
        <button className="link small" onClick={() => setEditing(true)}>
          override
        </button>
      )}
    </div>
  )
}

function StudentTest({
  info,
  test,
  onChange
}: {
  info: ClassInfo
  test: Test | null
  onChange: (data: { test: Test | null }) => void
}): JSX.Element {
  const api = useApp((s) => s.api)
  const [answers, setAnswers] = useState<Record<number, { choice: number | null; text: string }>>({})
  const action = useAction()

  if (!test) {
    return (
      <div className="page narrow">
        <div className="card">
          <h3>No test yet</h3>
          <p className="muted">The professor hasn't published the final test.</p>
        </div>
      </div>
    )
  }
  if (test.my_attempt) {
    return (
      <div className="page narrow">
        <AttemptView info={info} test={test} attempt={test.my_attempt} staff={false} />
      </div>
    )
  }
  if (test.status !== 'published') {
    return (
      <div className="page narrow">
        <div className="card">
          <h3>The test is closed</h3>
        </div>
      </div>
    )
  }

  const get = (id: number): { choice: number | null; text: string } => answers[id] ?? { choice: null, text: '' }
  const put = (id: number, patch: Partial<{ choice: number | null; text: string }>): void =>
    setAnswers((a) => ({ ...a, [id]: { ...get(id), ...patch } }))
  const unanswered = test.items.filter((i) => (i.kind === 'mcq' ? get(i.id).choice === null : !get(i.id).text.trim())).length

  const submit = async (): Promise<void> => {
    if (unanswered && !window.confirm(`${unanswered} item(s) are unanswered. Submit anyway?`)) return
    const body = { answers: test.items.map((i) => ({ item_id: i.id, ...get(i.id) })) }
    const r = await action.run(() => api.post<{ test: Test | null }>(`/classes/${info.id}/test/attempt`, body))
    if (r) onChange(r)
  }

  return (
    <div className="page narrow">
      <h3>{test.title}</h3>
      <p className="muted small">{test.items.length} items. You can submit only once.</p>
      {test.items.map((item, i) => (
        <div key={item.id} className="card quiz-q">
          <p>
            <strong>{i + 1}.</strong> {item.prompt}
          </p>
          {item.kind === 'mcq' ? (
            item.options.map((o, j) => (
              <label key={j} className={`option ${get(item.id).choice === j ? 'chosen' : ''}`}>
                <input type="radio" name={`t${item.id}`} checked={get(item.id).choice === j} onChange={() => put(item.id, { choice: j })} />
                {o}
              </label>
            ))
          ) : (
            <textarea rows={4} value={get(item.id).text} onChange={(e) => put(item.id, { text: e.target.value })} />
          )}
        </div>
      ))}
      {action.error && <div className="error">{action.error}</div>}
      <button className="primary" onClick={() => void submit()} disabled={action.busy}>
        Submit test
      </button>
    </div>
  )
}
