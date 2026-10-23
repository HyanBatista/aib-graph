import { useEffect, useState } from 'react'
import { isStaff, useApp } from '../lib/store'
import { useAction, useResource } from '../lib/hooks'
import { OUTCOME_LABEL, pct } from '../lib/format'
import type { ClassInfo, NodeDetail, Question, QuizResult } from '../lib/types'
import Markdown from './Markdown'

interface Props {
  info: ClassInfo
  nodeId: number
  onSelect: (id: number) => void
  onClose: () => void
}

export default function NodePanel({ info, nodeId, onSelect, onClose }: Props): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.node)
  const graph = useApp((s) => s.cls.graph)
  const node = useResource(() => api.get<NodeDetail>(`/classes/${info.id}/nodes/${nodeId}`), [api, info.id, nodeId, version])
  const staff = isStaff(info)
  const [tab, setTab] = useState<'lesson' | 'source'>('lesson')

  useEffect(() => {
    if (info.role === 'student') void api.post(`/classes/${info.id}/nodes/${nodeId}/open`).catch(() => undefined)
  }, [api, info.id, info.role, nodeId])

  const d = node.data
  const titleOf = (id: number | null): string => graph?.nodes.find((n) => n.id === id)?.title ?? 'another topic'

  return (
    <div className="panel-body node-panel">
      <div className="row">
        <div className="grow">
          {d?.parent_title && <div className="muted small">{d.parent_title}</div>}
          <h3 className="node-title">{d?.title ?? '…'}</h3>
        </div>
        <button className="icon" onClick={onClose} title="Close">
          ✕
        </button>
      </div>
      {node.error && <div className="error">{node.error}</div>}
      {d && !d.ready && (
        <div className="notice row">
          <span className="spinner" /> The AI is writing this lesson…
        </div>
      )}
      {d && d.ready && (
        <>
          {!staff && d.progress && <ChecklistBar detail={d} />}
          <div className="segmented">
            <button className={tab === 'lesson' ? 'active' : ''} onClick={() => setTab('lesson')}>
              Lesson
            </button>
            <button className={tab === 'source' ? 'active' : ''} onClick={() => setTab('source')}>
              Source pages {d.page_start}–{d.page_end}
            </button>
          </div>
          {tab === 'lesson' ? <Markdown>{d.lesson_md}</Markdown> : <SourcePages info={info} start={d.page_start} end={d.page_end} />}

          {d.quiz.length > 0 && <Quiz info={info} detail={d} onDone={() => void node.reload()} staff={staff} />}

          {info.role === 'student' && (
            <AskQuestion info={info} detail={d} titleOf={titleOf} onSelect={onSelect} onDone={() => void node.reload()} />
          )}
          {staff && <StaffNodeTools info={info} detail={d} titleOf={titleOf} onSelect={onSelect} onChanged={() => void node.reload()} />}
        </>
      )}
    </div>
  )
}

function ChecklistBar({ detail }: { detail: NodeDetail }): JSX.Element {
  const p = detail.progress
  return (
    <div className="checklist small">
      <span className={p?.quiz_score !== null && p?.quiz_score !== undefined ? 'ok' : ''}>✓ Quiz</span>
      <span className={p?.question_done ? 'ok' : ''}>✓ Question</span>
      <span className={p?.completed ? 'ok strong' : ''}>{p?.completed ? 'Node completed' : 'Not completed yet'}</span>
    </div>
  )
}

function SourcePages({ info, start, end }: { info: ClassInfo; start: number; end: number }): JSX.Element {
  const api = useApp((s) => s.api)
  const pages = useResource(
    () => api.get<{ pages: { number: number; text: string }[] }>(`/classes/${info.id}/book/pages?start=${start}&end=${end}`),
    [api, info.id, start, end]
  )
  if (pages.error) return <div className="error">{pages.error}</div>
  return (
    <div className="source-pages">
      {pages.data?.pages.map((p) => (
        <div key={p.number} className="source-page">
          <div className="muted small">Page {p.number}</div>
          <pre>{p.text || '(no text on this page)'}</pre>
        </div>
      )) ?? <p className="muted">Loading…</p>}
    </div>
  )
}

function Quiz({ info, detail, staff, onDone }: { info: ClassInfo; detail: NodeDetail; staff: boolean; onDone: () => void }): JSX.Element {
  const api = useApp((s) => s.api)
  const submitted = detail.progress?.quiz_score !== null && detail.progress?.quiz_score !== undefined
  const [answers, setAnswers] = useState<(number | null)[]>(
    submitted ? (detail.progress?.quiz_answers ?? []) : detail.quiz.map(() => null)
  )
  const [result, setResult] = useState<QuizResult | null>(null)
  const action = useAction()
  const locked = submitted || staff || Boolean(result)
  const reveal = submitted || staff || Boolean(result)

  const submit = async (): Promise<void> => {
    const r = await action.run(() => api.post<QuizResult>(`/classes/${info.id}/nodes/${detail.id}/quiz`, { answers }))
    if (r) {
      setResult(r)
      onDone()
    }
  }

  const score = result?.score ?? detail.progress?.quiz_score
  return (
    <div className="quiz">
      <div className="row">
        <h4 className="grow">Quiz</h4>
        {!staff && score !== null && score !== undefined && <span className="badge">Score {pct(score)}</span>}
      </div>
      {detail.quiz.map((q, i) => {
        const correct = result?.results[i]?.answer_index ?? q.answer_index
        const feedback = result?.results[i]?.feedback ?? q.feedback
        return (
          <div key={i} className="quiz-q">
            <p>
              <strong>{i + 1}.</strong> {q.prompt}
            </p>
            {q.options.map((opt, j) => {
              const chosen = answers[i] === j
              const cls = reveal && correct !== undefined ? (j === correct ? 'right' : chosen ? 'wrong' : '') : ''
              return (
                <label key={j} className={`option ${cls} ${chosen ? 'chosen' : ''}`}>
                  <input
                    type="radio"
                    name={`q${detail.id}-${i}`}
                    checked={chosen}
                    disabled={locked}
                    onChange={() => setAnswers((a) => a.map((v, k) => (k === i ? j : v)))}
                  />
                  {opt}
                </label>
              )
            })}
            {reveal && feedback && <p className="feedback small">{feedback}</p>}
          </div>
        )
      })}
      {!locked && (
        <button className="primary" onClick={() => void submit()} disabled={action.busy || answers.some((a) => a === null)}>
          Submit answers
        </button>
      )}
      {action.error && <div className="error">{action.error}</div>}
    </div>
  )
}

function OutcomeLine({ q, titleOf, onSelect }: { q: Question; titleOf: (id: number | null) => string; onSelect: (id: number) => void }): JSX.Element {
  const go = q.target_node_id ? (
    <button className="link" onClick={() => onSelect(q.target_node_id as number)}>
      {titleOf(q.target_node_id)}
    </button>
  ) : null
  switch (q.outcome) {
    case 'created_node':
      return <div className="outcome created">✦ Your question created a new node: {go}</div>
    case 'linked_existing':
      return <div className="outcome linked">↪ Your question is about a topic already in the graph: {go}</div>
    case 'answered_only':
      return <div className="outcome">Answered — this question didn't map to a new topic of the book.</div>
    case 'pending':
      return (
        <div className="outcome row">
          <span className="spinner tiny" /> Thinking about your question…
        </div>
      )
    default:
      return <div className="outcome">{OUTCOME_LABEL[q.outcome]}</div>
  }
}

function AskQuestion({
  info,
  detail,
  titleOf,
  onSelect,
  onDone
}: {
  info: ClassInfo
  detail: NodeDetail
  titleOf: (id: number | null) => string
  onSelect: (id: number) => void
  onDone: () => void
}): JSX.Element {
  const api = useApp((s) => s.api)
  const answered = useApp((s) => s.cls.answeredQuestion)
  const [text, setText] = useState('')
  const [question, setQuestion] = useState<Question | null>(detail.my_question)
  const action = useAction()

  useEffect(() => setQuestion(detail.my_question), [detail.my_question])
  useEffect(() => {
    if (answered && answered.node_id === detail.id) setQuestion(answered)
  }, [answered, detail.id])

  const ask = async (): Promise<void> => {
    const q = await action.run(() => api.post<Question>(`/classes/${info.id}/nodes/${detail.id}/question`, { text }))
    if (q) {
      setQuestion(q)
      setText('')
      onDone()
    }
  }

  return (
    <div className="ask">
      <h4>Your question</h4>
      {question ? (
        <>
          <blockquote>{question.text}</blockquote>
          {question.answer_md && <Markdown>{question.answer_md}</Markdown>}
          <OutcomeLine q={question} titleOf={titleOf} onSelect={onSelect} />
        </>
      ) : detail.can_ask ? (
        <>
          <p className="muted small">
            Ask one question about this topic — what you'd like to understand next. It may open a new node for the class.
          </p>
          <textarea
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. How do hash tables handle collisions?"
            data-testid="question-input"
          />
          <button className="primary" disabled={action.busy || text.trim().length < 5} onClick={() => void ask()}>
            {action.busy ? 'Asking…' : 'Ask'}
          </button>
          {action.error && <div className="error">{action.error}</div>}
        </>
      ) : (
        <p className="muted small">Questions are closed for this class.</p>
      )}
    </div>
  )
}

function StaffNodeTools({
  info,
  detail,
  titleOf,
  onSelect,
  onChanged
}: {
  info: ClassInfo
  detail: NodeDetail
  titleOf: (id: number | null) => string
  onSelect: (id: number) => void
  onChanged: () => void
}): JSX.Element {
  const api = useApp((s) => s.api)
  const action = useAction()
  const regenerate = async (): Promise<void> => {
    if (!window.confirm('Regenerate this lesson and quiz with the AI?')) return
    if (await action.run(() => api.post(`/classes/${info.id}/nodes/${detail.id}/regenerate`))) onChanged()
  }
  return (
    <div className="staff-tools">
      <div className="row">
        <h4 className="grow">Students' questions ({detail.questions.length})</h4>
        {info.status !== 'frozen' && (
          <button className="small" onClick={() => void regenerate()} disabled={action.busy}>
            Regenerate
          </button>
        )}
      </div>
      {action.error && <div className="error">{action.error}</div>}
      {detail.questions.length === 0 && <p className="muted small">No questions yet.</p>}
      <ul className="question-list">
        {detail.questions.map((q) => (
          <li key={q.id}>
            <div className="small muted">{q.student}</div>
            <div>{q.text}</div>
            <div className="small">
              <span className={`badge outcome-${q.outcome}`}>{OUTCOME_LABEL[q.outcome]}</span>
              {q.target_node_id && (
                <>
                  {' → '}
                  <button className="link small" onClick={() => onSelect(q.target_node_id as number)}>
                    {titleOf(q.target_node_id)}
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
