import { describe, expect, it } from 'vitest'
import { applyEvent, initialClassState, type ClassState } from './events'
import type { ClassInfo, Graph, GraphNode } from './types'

const node = (id: number, topic: number, extra: Partial<GraphNode> = {}): GraphNode => ({
  id,
  topic_id: topic,
  title: `Topic ${topic}`,
  level: 1,
  parent_topic_id: null,
  ready: false,
  created_at: '2026-10-01T00:00:00Z',
  created_by_question_id: null,
  ...extra
})

function state(): ClassState {
  const graph: Graph = {
    status: 'growing',
    nodes: [node(1, 10, { ready: true, my_state: 'completed', avg_score: 0.8 })],
    edges: [],
    coverage: { covered: 1, total: 3 },
    uncovered: [
      { topic_id: 11, title: 'Topic 11', level: 1, state: 'available' },
      { topic_id: 12, title: 'Topic 12', level: 1, state: 'locked' }
    ]
  }
  const info = { id: 5, status: 'growing', status_detail: '', topics_covered: 1 } as ClassInfo
  return { ...initialClassState(5), graph, classInfo: info }
}

describe('applyEvent', () => {
  it('adds a created node with defaults, highlights it and updates coverage', () => {
    const next = applyEvent(state(), { event: 'node.created', payload: { class_id: 5, node: node(2, 11) } })
    expect(next.graph?.nodes).toHaveLength(2)
    expect(next.graph?.nodes[1]).toMatchObject({ id: 2, my_state: 'new', visits: 0, avg_score: null })
    expect(next.graph?.coverage.covered).toBe(2)
    expect(next.graph?.uncovered?.map((t) => t.topic_id)).toEqual([12])
    expect(next.highlights).toEqual([2])
    expect(next.classInfo?.topics_covered).toBe(2)
  })

  it('does not duplicate a node it already has', () => {
    const s = applyEvent(state(), { event: 'node.created', payload: { class_id: 5, node: node(2, 11) } })
    const again = applyEvent(s, { event: 'node.created', payload: { class_id: 5, node: node(2, 11) } })
    expect(again.graph?.nodes).toHaveLength(2)
    expect(again.graph?.coverage.covered).toBe(2)
  })

  it('marks a node ready and keeps per-user fields', () => {
    const next = applyEvent(state(), { event: 'node.ready', payload: { class_id: 5, node: node(1, 10, { ready: true }) } })
    expect(next.graph?.nodes[0]).toMatchObject({ ready: true, my_state: 'completed', avg_score: 0.8 })
    expect(next.versions.node).toBe(1)
  })

  it('adds edges once', () => {
    const edge = { id: 7, src: 1, dst: 2, kind: 'growth' as const, origin_question_id: 3 }
    const s = applyEvent(state(), { event: 'edge.created', payload: { class_id: 5, edge } })
    const again = applyEvent(s, { event: 'edge.created', payload: { class_id: 5, edge } })
    expect(again.graph?.edges).toEqual([edge])
  })

  it('updates status and bumps resources on class.status', () => {
    const next = applyEvent(state(), { event: 'class.status', payload: { class_id: 5, status: 'frozen', detail: '' } })
    expect(next.classInfo?.status).toBe('frozen')
    expect(next.graph?.status).toBe('frozen')
    expect(next.versions.class).toBe(1)
    expect(next.versions.graph).toBe(1)
  })

  it('stores the answered question and refreshes the node', () => {
    const question = { id: 3, node_id: 1, text: 'q', answer_md: 'a', outcome: 'created_node', resolved_topic_id: 11, target_node_id: 2, created_at: '' }
    const next = applyEvent(state(), { event: 'question.answered', payload: { class_id: 5, question } })
    expect(next.answeredQuestion).toEqual(question)
    expect(next.versions.node).toBe(1)
  })

  it('tracks node failures and clears them when ready', () => {
    const failed = applyEvent(state(), { event: 'node.failed', payload: { class_id: 5, node_id: 1, error: 'quota' } })
    expect(failed.failedNodes[1]).toBe('quota')
    const ok = applyEvent(failed, { event: 'node.ready', payload: { class_id: 5, node: node(1, 10, { ready: true }) } })
    expect(ok.failedNodes[1]).toBeUndefined()
  })

  it('bumps test and metrics versions on test events', () => {
    const next = applyEvent(state(), { event: 'test.published', payload: { class_id: 5 } })
    expect(next.versions.test).toBe(1)
    expect(next.versions.metrics).toBe(1)
  })

  it('ignores events of another class and unknown events', () => {
    const s = state()
    expect(applyEvent(s, { event: 'node.created', payload: { class_id: 99, node: node(2, 11) } })).toBe(s)
    expect(applyEvent(s, { event: 'something.else', payload: { class_id: 5 } })).toBe(s)
  })

  it('records job progress', () => {
    expect(applyEvent(state(), { event: 'job.progress', payload: { class_id: 5, message: 'Read 21 pages' } }).job).toBe(
      'Read 21 pages'
    )
  })
})
