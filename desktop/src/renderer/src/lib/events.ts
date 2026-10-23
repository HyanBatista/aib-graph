import type { ClassInfo, ClassStatus, Graph, GraphEdge, GraphNode, Question, ServerEvent } from './types'

/** Data that components refetch when a version number changes. */
export type Resource = 'graph' | 'index' | 'test' | 'metrics' | 'members' | 'class' | 'node'

export interface ClassState {
  classId: number | null
  classInfo: ClassInfo | null
  graph: Graph | null
  versions: Record<Resource, number>
  /** Node ids that just arrived over the websocket, for a highlight animation. */
  highlights: number[]
  answeredQuestion: Question | null
  job: string | null
  failedNodes: Record<number, string>
}

export const emptyVersions = (): Record<Resource, number> => ({
  graph: 0,
  index: 0,
  test: 0,
  metrics: 0,
  members: 0,
  class: 0,
  node: 0
})

export const initialClassState = (classId: number | null = null): ClassState => ({
  classId,
  classInfo: null,
  graph: null,
  versions: emptyVersions(),
  highlights: [],
  answeredQuestion: null,
  job: null,
  failedNodes: {}
})

function bump(state: ClassState, ...resources: Resource[]): ClassState['versions'] {
  const versions = { ...state.versions }
  for (const r of resources) versions[r] += 1
  return versions
}

function withNode(graph: Graph, node: GraphNode): Graph {
  const existing = graph.nodes.find((n) => n.id === node.id)
  if (existing) {
    return { ...graph, nodes: graph.nodes.map((n) => (n.id === node.id ? { ...n, ...node } : n)) }
  }
  const fresh: GraphNode = { avg_score: null, visits: 0, my_state: 'new', my_score: null, created_by: null, ...node }
  const uncovered = graph.uncovered?.filter((t) => t.topic_id !== node.topic_id)
  return {
    ...graph,
    nodes: [...graph.nodes, fresh],
    coverage: { ...graph.coverage, covered: graph.coverage.covered + 1 },
    ...(uncovered ? { uncovered } : {})
  }
}

function withEdge(graph: Graph, edge: GraphEdge): Graph {
  if (graph.edges.some((e) => e.id === edge.id || (e.src === edge.src && e.dst === edge.dst))) return graph
  return { ...graph, edges: [...graph.edges, edge] }
}

/** Apply one websocket event to the class state. Pure, so it is unit-tested. */
export function applyEvent(state: ClassState, msg: ServerEvent): ClassState {
  const p = msg.payload ?? {}
  if (p.class_id !== undefined && state.classId !== null && p.class_id !== state.classId) return state

  switch (msg.event) {
    case 'node.created': {
      const node = p.node as GraphNode
      return {
        ...state,
        graph: state.graph ? withNode(state.graph, node) : state.graph,
        highlights: [...state.highlights.filter((id) => id !== node.id), node.id],
        classInfo: state.classInfo
          ? { ...state.classInfo, topics_covered: state.classInfo.topics_covered + 1 }
          : state.classInfo,
        versions: bump(state, 'metrics')
      }
    }
    case 'node.ready': {
      const node = p.node as GraphNode
      const failedNodes = { ...state.failedNodes }
      delete failedNodes[node.id]
      return {
        ...state,
        graph: state.graph ? withNode(state.graph, node) : state.graph,
        failedNodes,
        versions: bump(state, 'node')
      }
    }
    case 'node.failed':
      return { ...state, failedNodes: { ...state.failedNodes, [p.node_id as number]: String(p.error ?? 'failed') } }
    case 'edge.created':
      return { ...state, graph: state.graph ? withEdge(state.graph, p.edge as GraphEdge) : state.graph }
    case 'question.answered':
      return { ...state, answeredQuestion: p.question as Question, versions: bump(state, 'node', 'graph') }
    case 'class.status': {
      const status = p.status as ClassStatus
      return {
        ...state,
        classInfo: state.classInfo
          ? { ...state.classInfo, status, status_detail: String(p.detail ?? '') }
          : state.classInfo,
        graph: state.graph ? { ...state.graph, status } : state.graph,
        job: status === 'review' || status === 'growing' ? null : state.job,
        versions: bump(state, 'class', 'graph', 'index')
      }
    }
    case 'index.ready':
      return { ...state, job: null, versions: bump(state, 'index', 'class') }
    case 'graph.completed':
    case 'graph.frozen':
      return { ...state, versions: bump(state, 'class', 'graph', 'test') }
    case 'test.generated':
    case 'test.published':
    case 'test.closed':
    case 'test.graded':
      return { ...state, versions: bump(state, 'test', 'metrics') }
    case 'metrics.changed':
      return { ...state, versions: bump(state, 'metrics') }
    case 'members.changed':
      return { ...state, versions: bump(state, 'members', 'class') }
    case 'job.progress':
      return { ...state, job: String(p.message ?? '') }
    default:
      return state
  }
}
