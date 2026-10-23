import { useCallback, useEffect, useState } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { isStaff, useApp } from '../lib/store'
import { useAction } from '../lib/hooks'
import { heat } from '../lib/format'
import type { ClassInfo, Graph } from '../lib/types'
import GraphCanvas from './GraphCanvas'
import NodePanel from './NodePanel'

export default function GraphTab({ info }: { info: ClassInfo }): JSX.Element {
  const { api, setGraph, clearHighlight } = useApp()
  const graph = useApp((s) => s.cls.graph)
  const version = useApp((s) => s.cls.versions.graph)
  const highlights = useApp((s) => s.cls.highlights)
  const failed = useApp((s) => s.cls.failedNodes)
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const action = useAction()
  const staff = isStaff(info)

  useEffect(() => {
    api
      .get<Graph>(`/classes/${info.id}/graph`)
      .then((g) => {
        setGraph(g)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [api, info.id, version, setGraph])

  const onHighlightDone = useCallback((id: number) => clearHighlight(id), [clearHighlight])

  const freeze = async (): Promise<void> => {
    if (!window.confirm('Freeze the graph? Students will no longer be able to ask questions or grow the graph.')) return
    await action.run(() => api.post(`/classes/${info.id}/freeze`))
  }

  const exportEgf = async (): Promise<void> => {
    await action.run(async () => {
      const res = await api.raw('GET', `/classes/${info.id}/export.egf`)
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'course.egf'
      await window.aib.saveFile(name, await res.text())
    })
  }

  const expand = (topicId: number): Promise<unknown> =>
    action.run(() => api.post(`/classes/${info.id}/topics/${topicId}/expand`))

  if (error) return <div className="error">{error}</div>
  if (!graph) return <div className="center muted">Loading graph…</div>

  const { covered, total } = graph.coverage
  return (
    <div className="graph-layout">
      <section className="graph-area">
        <div className="graph-toolbar">
          <div className="coverage" title="Index topics that already have a node">
            <span className="small">
              <strong>{covered}</strong>/{total} topics covered
            </span>
            <div className="progress">
              <div style={{ width: `${total ? (100 * covered) / total : 0}%` }} />
            </div>
          </div>
          <Legend staff={staff} />
          <div className="spacer" />
          {staff && (
            <button onClick={() => void exportEgf()} disabled={action.busy}>
              Export .egf
            </button>
          )}
          {info.role === 'professor' && info.status !== 'frozen' && (
            <button className="danger" onClick={() => void freeze()} disabled={action.busy}>
              Freeze graph
            </button>
          )}
        </div>
        {action.error && <div className="error">{action.error}</div>}
        {info.status === 'complete' && (
          <div className="notice">All topics of the book are covered. The graph is complete.</div>
        )}
        {info.status === 'frozen' && <div className="notice">The graph is frozen.</div>}
        <div className="graph-canvas" data-testid="graph-canvas">
          <ReactFlowProvider>
            <GraphCanvas
              graph={graph}
              staff={staff}
              selectedId={selected}
              highlights={highlights}
              failed={failed}
              onSelect={setSelected}
              onHighlightDone={onHighlightDone}
            />
          </ReactFlowProvider>
        </div>
      </section>
      <aside className="side-panel">
        {selected !== null ? (
          <NodePanel key={selected} info={info} nodeId={selected} onSelect={setSelected} onClose={() => setSelected(null)} />
        ) : (
          <Overview info={info} graph={graph} staff={staff} onExpand={expand} busy={action.busy} />
        )}
      </aside>
    </div>
  )
}

function Legend({ staff }: { staff: boolean }): JSX.Element {
  return staff ? (
    <div className="legend small muted">
      <span className="swatch" style={{ background: heat(0) }} /> low avg
      <span className="swatch" style={{ background: heat(0.5) }} />
      <span className="swatch" style={{ background: heat(1) }} /> high avg
      <span className="line dashed" /> link
    </div>
  ) : (
    <div className="legend small muted">
      <span className="swatch" style={{ background: 'var(--node-new)' }} /> new
      <span className="swatch" style={{ background: 'var(--node-progress)' }} /> in progress
      <span className="swatch" style={{ background: 'var(--node-done)' }} /> done
    </div>
  )
}

function Overview({
  info,
  graph,
  staff,
  onExpand,
  busy
}: {
  info: ClassInfo
  graph: Graph
  staff: boolean
  onExpand: (topicId: number) => Promise<unknown>
  busy: boolean
}): JSX.Element {
  const mine = graph.nodes.filter((n) => n.my_state === 'completed').length
  return (
    <div className="panel-body">
      <h3>How it works</h3>
      <p className="muted small">
        Each node is one topic of the book. Open a node, read the lesson, answer the quiz and ask <strong>one
        question</strong>. If your question is about a topic nobody has reached yet, it creates a new node for the
        whole class.
      </p>
      {!staff && (
        <p>
          You completed <strong>{mine}</strong> of {graph.nodes.length} nodes.
        </p>
      )}
      {staff && graph.uncovered && (
        <>
          <h4>Uncovered topics ({graph.uncovered.length})</h4>
          {graph.uncovered.length === 0 && <p className="muted small">Every topic has a node.</p>}
          <ul className="uncovered">
            {graph.uncovered.map((t) => (
              <li key={t.topic_id} className={t.level ? 'sub' : ''}>
                <span className={`badge state-${t.state}`}>{t.state}</span>
                <span className="grow">{t.title}</span>
                {info.status === 'growing' && (
                  <button className="small" disabled={busy} onClick={() => void onExpand(t.topic_id)}>
                    Expand
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p className="muted small">
            “Expand” creates a node without waiting for a student question, linked from its prerequisite.
          </p>
        </>
      )}
    </div>
  )
}
