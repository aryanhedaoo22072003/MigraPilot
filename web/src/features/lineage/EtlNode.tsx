import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Braces, Database, Filter, GitMerge, ListFilter, Route, Search, Sigma, SortAsc, UploadCloud } from 'lucide-react'
import type { LineageNodeData } from './graph'

const styles: Record<string, { color: string; icon: typeof Database; label: string }> = {
  'Source Definition': { color: 'cyan', icon: Database, label: 'Source' },
  'Target Definition': { color: 'emerald', icon: UploadCloud, label: 'Target' },
  Expression: { color: 'violet', icon: Braces, label: 'Expression' },
  Filter: { color: 'amber', icon: Filter, label: 'Filter' },
  Joiner: { color: 'blue', icon: GitMerge, label: 'Joiner' },
  Lookup: { color: 'fuchsia', icon: Search, label: 'Lookup' },
  Aggregator: { color: 'orange', icon: Sigma, label: 'Aggregator' },
  Router: { color: 'sky', icon: Route, label: 'Router' },
  Sorter: { color: 'indigo', icon: SortAsc, label: 'Sorter' },
  'Update Strategy': { color: 'rose', icon: ListFilter, label: 'Update Strategy' },
}

export default function EtlNode({ data }: NodeProps & { data: LineageNodeData }) {
  const { transformation, selectedPortId, highlightedPortIds, unknownPortIds, onInspect, onPortSelect } = data
  const style = styles[transformation.type] ?? { color: 'slate', icon: Braces, label: transformation.type }
  const Icon = style.icon
  return <article className={`etl-node etl-${style.color}`} onClick={() => onInspect(transformation)} data-testid={`node-${transformation.name}`}>
    <header><span className="etl-node-icon"><Icon size={16} /></span><div className="min-w-0"><span>{style.label}</span><h3 title={transformation.name}>{transformation.name}</h3></div></header>
    <div className="etl-ports">
      {transformation.ports.map(port => {
        const highlighted = highlightedPortIds.has(port.id)
        const selected = selectedPortId === port.id
        const unknown = unknownPortIds.has(port.id)
        return <button key={port.id} type="button" className={`etl-port nodrag ${highlighted ? 'is-upstream' : ''} ${selected ? 'is-selected' : ''} ${unknown ? 'has-unknown' : ''}`} onClick={event => { event.stopPropagation(); onPortSelect(port.id) }} title={unknown ? `Some expression dependencies are unknown: ${port.expression}` : port.expression || `${port.direction || 'Port'} · ${port.datatype || 'unknown type'}`}>
          <Handle id={`p-${port.id}`} type="target" position={Position.Left} className="etl-handle etl-handle-in" />
          <span className="etl-port-direction">{port.direction || '—'}</span><span className="etl-port-name">{port.name}{unknown && <span className="etl-unknown" aria-label="Unknown expression dependency">?</span>}</span><span className="etl-port-type">{port.datatype || '—'}</span>
          <Handle id={`p-${port.id}`} type="source" position={Position.Right} className="etl-handle etl-handle-out" />
        </button>
      })}
    </div>
  </article>
}
