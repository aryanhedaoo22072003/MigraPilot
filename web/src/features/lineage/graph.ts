import dagre from '@dagrejs/dagre'
import type { Edge, Node } from '@xyflow/react'
import type { LineageEdge, MappingDetail, MappingTransformation } from '../../lib/api'

export type LineageNodeData = {
  transformation: MappingTransformation
  selectedPortId: number | null
  highlightedPortIds: Set<number>
  unknownPortIds: Set<number>
  onInspect: (transformation: MappingTransformation) => void
  onPortSelect: (portId: number) => void
}

const NODE_WIDTH = 320

const RESERVED_WORDS = new Set(['AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE', 'IS', 'IN', 'LIKE', 'BETWEEN', 'THEN', 'ELSE', 'END'])

export type ExpressionDependency = { dependencies: Set<number>; unknown: boolean }

export function expressionDependencies(transformation: MappingTransformation): Map<number, ExpressionDependency> {
  const portsByName = new Map(transformation.ports.map(port => [port.name.toUpperCase(), port.id]))
  const result = new Map<number, ExpressionDependency>()
  for (const port of transformation.ports) {
    if (!port.expression?.trim()) continue
    let unknown = false
    let cleaned = port.expression.replace(/'(?:''|[^'])*'/g, ' ')
    if ((cleaned.match(/\(/g) || []).length !== (cleaned.match(/\)/g) || []).length) unknown = true
    if (/[^A-Za-z0-9_$\s(),.+\-*/%<>=!|&]/.test(cleaned)) unknown = true
    const dependencies = new Set<number>()
    const identifiers = [...cleaned.matchAll(/[A-Za-z_$][A-Za-z0-9_$]*/g)]
    for (const match of identifiers) {
      const identifier = match[0].toUpperCase()
      const dependency = portsByName.get(identifier)
      if (dependency !== undefined && dependency !== port.id) {
        dependencies.add(dependency)
        continue
      }
      const remainder = cleaned.slice((match.index || 0) + match[0].length)
      const functionName = /^\s*\(/.test(remainder)
      if (!functionName && !RESERVED_WORDS.has(identifier) && dependency === undefined) unknown = true
    }
    result.set(port.id, { dependencies, unknown })
  }
  return result
}

export function traceUpstream(mapping: MappingDetail, targetPortId: number): { ports: Set<number>; unknownPorts: Set<number> } {
  const ports = new Set<number>([targetPortId])
  const unknownPorts = new Set<number>()
  const queue = [targetPortId]
  const expressions = new Map<number, ExpressionDependency>()
  mapping.transformations.forEach(transformation => expressionDependencies(transformation).forEach((value, key) => expressions.set(key, value)))
  while (queue.length) {
    const current = queue.shift()!
    const expression = expressions.get(current)
    if (expression?.unknown) unknownPorts.add(current)
    const candidates = [
      ...mapping.lineage_edges.filter(edge => edge.to_port_id === current).map(edge => edge.from_port_id),
      ...(expression ? expression.dependencies : []),
    ]
    for (const dependency of candidates) {
      if (!ports.has(dependency)) {
        ports.add(dependency)
        queue.push(dependency)
      }
    }
  }
  return { ports, unknownPorts }
}

export function upstreamPortIds(edges: LineageEdge[], targetPortId: number): Set<number> {
  const upstream = new Set<number>([targetPortId])
  const queue = [targetPortId]
  while (queue.length) {
    const current = queue.shift()!
    for (const edge of edges) {
      if (edge.to_port_id === current && !upstream.has(edge.from_port_id)) {
        upstream.add(edge.from_port_id)
        queue.push(edge.from_port_id)
      }
    }
  }
  return upstream
}

export function layoutLineage(
  mapping: MappingDetail,
  selectedPortId: number | null,
  onInspect: LineageNodeData['onInspect'],
  onPortSelect: LineageNodeData['onPortSelect'],
): { nodes: Node<LineageNodeData>[]; edges: Edge[]; highlighted: Set<number>; unknownPorts: Set<number> } {
  const trace = selectedPortId ? traceUpstream(mapping, selectedPortId) : { ports: new Set<number>(), unknownPorts: new Set<number>() }
  const highlighted = trace.ports
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: 'LR', ranksep: 150, nodesep: 68, marginx: 48, marginy: 42 })
  const portOwner = new Map<number, number>()
  mapping.transformations.forEach(transformation => {
    const height = Math.max(150, 94 + transformation.ports.length * 36)
    graph.setNode(String(transformation.id), { width: NODE_WIDTH, height })
    transformation.ports.forEach(port => portOwner.set(port.id, transformation.id))
  })
  mapping.lineage_edges.forEach(edge => {
    const source = portOwner.get(edge.from_port_id)
    const target = portOwner.get(edge.to_port_id)
    if (source && target) graph.setEdge(String(source), String(target))
  })
  dagre.layout(graph)
  const nodes: Node<LineageNodeData>[] = mapping.transformations.map(transformation => {
    const position = graph.node(String(transformation.id))
    return {
      id: String(transformation.id), type: 'etlNode',
      position: { x: position.x - NODE_WIDTH / 2, y: position.y - position.height / 2 },
      data: { transformation, selectedPortId, highlightedPortIds: highlighted, unknownPortIds: trace.unknownPorts, onInspect, onPortSelect },
    }
  })
  const edges: Edge[] = mapping.lineage_edges.map(edge => {
    const active = selectedPortId !== null && highlighted.has(edge.from_port_id) && highlighted.has(edge.to_port_id)
    return {
      id: String(edge.id), source: String(portOwner.get(edge.from_port_id)), target: String(portOwner.get(edge.to_port_id)),
      sourceHandle: `p-${edge.from_port_id}`, targetHandle: `p-${edge.to_port_id}`, type: 'smoothstep', animated: active,
      className: active ? 'lineage-edge-active' : selectedPortId ? 'lineage-edge-muted' : 'lineage-edge-default',
      style: { strokeWidth: active ? 3.2 : 2.1 },
    }
  })
  return { nodes, edges, highlighted, unknownPorts: trace.unknownPorts }
}
