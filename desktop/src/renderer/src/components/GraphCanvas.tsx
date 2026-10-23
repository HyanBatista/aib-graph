import { memo, useEffect, useMemo } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps
} from '@xyflow/react'
import { heat, pct } from '../lib/format'
import type { Graph, GraphNode } from '../lib/types'

const WIDTH = 210
const HEIGHT = 64

export interface TopicData extends Record<string, unknown> {
  node: GraphNode
  staff: boolean
  highlighted: boolean
  failed: boolean
}

const STATE_COLOR = { new: 'var(--node-new)', in_progress: 'var(--node-progress)', completed: 'var(--node-done)' }

export function nodeColor(node: GraphNode, staff: boolean): string {
  if (staff) return node.visits ? heat(node.avg_score) : 'var(--node-empty)'
  return STATE_COLOR[node.my_state ?? 'new']
}

const TopicNode = memo(function TopicNode({ data, selected }: NodeProps<Node<TopicData>>) {
  const { node, staff, highlighted, failed } = data
  const color = nodeColor(node, staff)
  const subtitle = !node.ready
    ? failed
      ? 'generation failed'
      : 'generating…'
    : staff
      ? `${node.visits ?? 0} visits · avg ${pct(node.avg_score)}`
      : node.my_state === 'completed'
        ? `done · ${pct(node.my_score)}`
        : node.my_state === 'in_progress'
          ? 'in progress'
          : 'not started'
  return (
    <div
      className={[
        'topic-node',
        node.level === 0 ? 'chapter' : '',
        selected ? 'selected' : '',
        highlighted ? 'highlight' : '',
        node.ready ? '' : 'pending'
      ].join(' ')}
      style={{ borderLeftColor: color }}
      data-testid="graph-node"
    >
      <Handle type="target" position={Position.Top} />
      <div className="topic-title">{node.title}</div>
      <div className="topic-sub">
        {!node.ready && !failed && <span className="spinner tiny" />}
        {subtitle}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
})

const nodeTypes = { topic: TopicNode }

export function layout(graph: Graph): Record<number, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 70, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of graph.nodes) g.setNode(String(n.id), { width: WIDTH, height: HEIGHT })
  // Lay out along the edges that created each node, so the picture reads as a growth tree.
  for (const e of graph.edges) if (e.kind === 'growth') g.setEdge(String(e.src), String(e.dst))
  dagre.layout(g)
  const positions: Record<number, { x: number; y: number }> = {}
  for (const n of graph.nodes) {
    const p = g.node(String(n.id))
    positions[n.id] = { x: p.x - WIDTH / 2, y: p.y - HEIGHT / 2 }
  }
  return positions
}

interface Props {
  graph: Graph
  staff: boolean
  selectedId: number | null
  highlights: number[]
  failed: Record<number, string>
  onSelect: (id: number | null) => void
  onHighlightDone: (id: number) => void
}

export default function GraphCanvas({
  graph,
  staff,
  selectedId,
  highlights,
  failed,
  onSelect,
  onHighlightDone
}: Props): JSX.Element {
  const shapeKey = graph.nodes.map((n) => n.id).join(',') + '|' + graph.edges.map((e) => e.id).join(',')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const positions = useMemo(() => layout(graph), [shapeKey])

  useEffect(() => {
    if (!highlights.length) return
    const timers = highlights.map((id) => setTimeout(() => onHighlightDone(id), 4000))
    return () => timers.forEach(clearTimeout)
  }, [highlights, onHighlightDone])

  const nodes: Node<TopicData>[] = graph.nodes.map((n) => ({
    id: String(n.id),
    type: 'topic',
    position: positions[n.id] ?? { x: 0, y: 0 },
    selected: n.id === selectedId,
    data: { node: n, staff, highlighted: highlights.includes(n.id), failed: Boolean(failed[n.id]) }
  }))
  const edges: Edge[] = graph.edges.map((e) => ({
    id: String(e.id),
    source: String(e.src),
    target: String(e.dst),
    type: e.kind === 'growth' ? 'smoothstep' : 'default',
    animated: highlights.includes(e.dst),
    className: e.kind === 'link' ? 'edge-link' : 'edge-growth',
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 }
  }))

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, n) => onSelect(Number(n.id))}
      onPaneClick={() => onSelect(null)}
      nodesDraggable={false}
      nodesConnectable={false}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      minZoom={0.2}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={(n) => nodeColor((n.data as TopicData).node, staff)} />
    </ReactFlow>
  )
}
