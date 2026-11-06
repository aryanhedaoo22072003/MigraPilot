import { describe, expect, it, vi } from 'vitest'
import type { MappingDetail } from '../../lib/api'
import { expressionDependencies, layoutLineage, NODE_WIDTH, traceUpstream, upstreamPortIds } from './graph'

const mapping: MappingDetail = {
  id: 2, project_id: 6, upload_id: 1, name: 'm_orders_expression_filter', description: null, status: 'parsed', created_at: '2026-11-01T00:00:00Z',
  transformations: [
    { id: 1, name: 'SRC', type: 'Source Definition', logic_json: {}, seq_order: 0, ports: [{ id: 11, name: 'AMOUNT', datatype: 'decimal', direction: 'OUT', expression: null }] },
    { id: 2, name: 'EXP', type: 'Expression', logic_json: {}, seq_order: 1, ports: [{ id: 20, name: 'AMOUNT', datatype: 'decimal', direction: 'IN', expression: null }, { id: 21, name: 'NET_AMOUNT', datatype: 'decimal', direction: 'OUT', expression: 'AMOUNT * .9' }] },
    { id: 3, name: 'FIL', type: 'Filter', logic_json: { table_attributes: { 'Filter Condition': 'AMOUNT > 0' } }, seq_order: 2, ports: [{ id: 31, name: 'AMOUNT', datatype: 'decimal', direction: 'INOUT', expression: null }] },
    { id: 4, name: 'TGT', type: 'Target Definition', logic_json: {}, seq_order: 3, ports: [{ id: 41, name: 'AMOUNT', datatype: 'decimal', direction: 'IN', expression: null }] },
  ],
  lineage_edges: [
    { id: 1, from_port_id: 11, to_port_id: 20, from_transformation: 'SRC', from_port: 'AMOUNT', to_transformation: 'EXP', to_port: 'AMOUNT' },
    { id: 2, from_port_id: 21, to_port_id: 31, from_transformation: 'EXP', from_port: 'NET_AMOUNT', to_transformation: 'FIL', to_port: 'AMOUNT' },
    { id: 3, from_port_id: 31, to_port_id: 41, from_transformation: 'FIL', from_port: 'AMOUNT', to_transformation: 'TGT', to_port: 'AMOUNT' },
  ],
}

describe('lineage graph', () => {
  it('walks every upstream port from a selected target column', () => {
    expect([...upstreamPortIds(mapping.lineage_edges, 41)]).toEqual([41, 31, 21])
    expect([...traceUpstream(mapping, 41).ports]).toEqual([41, 31, 21, 20, 11])
  })

  it('uses actual port ids as React Flow handles and lays nodes left-to-right', () => {
    const result = layoutLineage(mapping, 41, vi.fn(), vi.fn())
    expect(result.nodes).toHaveLength(4)
    expect(result.edges[0]).toMatchObject({ sourceHandle: 'p-11', targetHandle: 'p-20' })
    expect(result.edges.every(edge => edge.animated)).toBe(true)
    const x = result.nodes.map(node => node.position.x)
    expect(x).toEqual([...x].sort((a, b) => a - b))
    expect(NODE_WIDTH).toBe(280)
    expect(x[1] - x[0]).toBeLessThan(450)
  })

  it('marks unresolved expression identifiers unknown without inventing dependencies', () => {
    const transformation = { ...mapping.transformations[1], ports: [
      { id: 20, name: 'AMOUNT', datatype: 'decimal', direction: 'IN' as const, expression: null },
      { id: 21, name: 'NET_AMOUNT', datatype: 'decimal', direction: 'OUT' as const, expression: 'MISSING_RATE * AMOUNT' },
    ] }
    const analysis = expressionDependencies(transformation).get(21)
    expect([...analysis!.dependencies]).toEqual([20])
    expect(analysis!.unknown).toBe(true)
  })
})
