import { useEffect, useState } from 'react'
import { useApp } from '../lib/store'
import { useAction, useResource } from '../lib/hooks'
import type { BookIndex, ClassInfo, SubtopicIn, TopicIn } from '../lib/types'

type Path = [number] | [number, number]

export function toTree(index: BookIndex): TopicIn[] {
  const roots = index.topics.filter((t) => t.parent_id === null)
  return roots.map((r) => ({
    title: r.title,
    summary: r.summary,
    page_start: r.page_start,
    page_end: r.page_end,
    subtopics: index.topics
      .filter((t) => t.parent_id === r.id)
      .map((s) => ({ title: s.title, summary: s.summary, page_start: s.page_start, page_end: s.page_end }))
  }))
}

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  const [item] = copy.splice(from, 1)
  copy.splice(to, 0, item)
  return copy
}

export default function IndexEditor({ info }: { info: ClassInfo }): JSX.Element {
  const api = useApp((s) => s.api)
  const version = useApp((s) => s.cls.versions.index)
  const index = useResource(() => api.get<BookIndex>(`/classes/${info.id}/index`), [api, info.id, version])
  const [tree, setTree] = useState<TopicIn[]>([])
  const [dirty, setDirty] = useState(false)
  const action = useAction()
  const isProfessor = info.role === 'professor'

  useEffect(() => {
    if (index.data && !dirty) setTree(toTree(index.data))
  }, [index.data, dirty])

  const update = (fn: (t: TopicIn[]) => TopicIn[]): void => {
    setTree((t) => fn(t))
    setDirty(true)
  }

  const edit = (path: Path, patch: Partial<SubtopicIn>): void =>
    update((t) =>
      t.map((topic, i) => {
        if (i !== path[0]) return topic
        if (path.length === 1) return { ...topic, ...patch }
        return { ...topic, subtopics: topic.subtopics.map((s, j) => (j === path[1] ? { ...s, ...patch } : s)) }
      })
    )

  const remove = (path: Path): void =>
    update((t) =>
      path.length === 1
        ? t.filter((_, i) => i !== path[0])
        : t.map((topic, i) => (i === path[0] ? { ...topic, subtopics: topic.subtopics.filter((_, j) => j !== path[1]) } : topic))
    )

  const shift = (path: Path, delta: number): void =>
    update((t) =>
      path.length === 1
        ? move(t, path[0], path[0] + delta)
        : t.map((topic, i) => (i === path[0] ? { ...topic, subtopics: move(topic.subtopics, path[1], path[1] + delta) } : topic))
    )

  const addTopic = (): void =>
    update((t) => [...t, { title: 'New topic', summary: '', page_start: 1, page_end: 1, subtopics: [] }])
  const addSub = (i: number): void =>
    update((t) =>
      t.map((topic, k) =>
        k === i
          ? {
              ...topic,
              subtopics: [
                ...topic.subtopics,
                { title: 'New subtopic', summary: '', page_start: topic.page_start, page_end: topic.page_end }
              ]
            }
          : topic
      )
    )

  const save = async (): Promise<boolean> => {
    const result = await action.run(() => api.put<BookIndex>(`/classes/${info.id}/index`, { topics: tree }))
    if (result) {
      setDirty(false)
      index.setData(result)
      return true
    }
    return false
  }

  const approve = async (): Promise<void> => {
    if (dirty && !(await save())) return
    await action.run(() => api.post(`/classes/${info.id}/index/approve`))
  }

  if (!isProfessor) {
    return (
      <div className="page narrow">
        <div className="card">
          <h3>The professor is reviewing the index</h3>
          <p className="muted">The graph will appear here as soon as the index is approved.</p>
        </div>
      </div>
    )
  }

  const total = tree.reduce((n, t) => n + 1 + t.subtopics.length, 0)
  const pageCount = index.data?.page_count ?? 1

  const row = (item: SubtopicIn, path: Path, count: number): JSX.Element => (
    <div className={path.length === 1 ? 'index-row topic' : 'index-row subtopic'}>
      <div className="index-main">
        <input className="index-title" value={item.title} onChange={(e) => edit(path, { title: e.target.value })} />
        <textarea
          rows={1}
          placeholder="Summary"
          value={item.summary}
          onChange={(e) => edit(path, { summary: e.target.value })}
        />
      </div>
      <label className="pages">
        pp.
        <input
          type="number"
          min={1}
          max={pageCount}
          value={item.page_start}
          onChange={(e) => edit(path, { page_start: Number(e.target.value) })}
        />
        –
        <input
          type="number"
          min={1}
          max={pageCount}
          value={item.page_end}
          onChange={(e) => edit(path, { page_end: Number(e.target.value) })}
        />
      </label>
      <div className="row tight">
        <button className="icon" title="Move up" disabled={path[path.length - 1] === 0} onClick={() => shift(path, -1)}>
          ↑
        </button>
        <button className="icon" title="Move down" disabled={path[path.length - 1] === count - 1} onClick={() => shift(path, 1)}>
          ↓
        </button>
        <button className="icon danger" title="Delete" onClick={() => remove(path)}>
          ✕
        </button>
      </div>
    </div>
  )

  return (
    <div className="page">
      <div className="toolbar">
        <div>
          <h3>Review the index</h3>
          <p className="muted small">
            {index.data?.book_title} · {pageCount} pages · {total} topics. Each topic and subtopic becomes one node; the
            graph is complete when all of them are covered.
          </p>
        </div>
        <div className="spacer" />
        <button onClick={() => void save()} disabled={!dirty || action.busy}>
          {dirty ? 'Save changes' : 'Saved'}
        </button>
        <button className="primary" onClick={() => void approve()} disabled={action.busy || tree.length === 0}>
          Approve &amp; build graph
        </button>
      </div>
      {(action.error || index.error) && <div className="error">{action.error || index.error}</div>}
      {info.status_detail && <div className="error">{info.status_detail}</div>}
      <div className="index-list">
        {tree.map((topic, i) => (
          <div key={i} className="card index-topic">
            {row(topic, [i], tree.length)}
            {topic.subtopics.map((s, j) => (
              <div key={j}>{row(s, [i, j], topic.subtopics.length)}</div>
            ))}
            <button className="link small" onClick={() => addSub(i)}>
              + subtopic
            </button>
          </div>
        ))}
      </div>
      <button onClick={addTopic}>+ Add topic</button>
    </div>
  )
}
