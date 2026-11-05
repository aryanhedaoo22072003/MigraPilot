import { AlertTriangle, Braces, CircleDot, X } from 'lucide-react'
import type { MappingTransformation } from '../../lib/api'
import { expressionDependencies } from './graph'

function Metadata({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata).filter(([, value]) => value !== null && value !== '' && !(Array.isArray(value) && !value.length))
  if (!entries.length) return <p className="text-xs text-slate-500">No additional metadata was exported.</p>
  return <dl className="space-y-3">{entries.map(([key, value]) => <div key={key} className="rounded-xl border border-slate-700/70 bg-slate-950/40 p-3"><dt className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-words text-xs leading-5 text-slate-300">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</dd></div>)}</dl>
}

export default function Inspector({ transformation, onClose }: { transformation: MappingTransformation; onClose: () => void }) {
  const inputs = transformation.ports.filter(port => port.direction === 'IN' || port.direction === 'INOUT')
  const outputs = transformation.ports.filter(port => port.direction === 'OUT' || port.direction === 'INOUT')
  const metadata = transformation.logic_json || {}
  const unknownExpressions = new Set([...expressionDependencies(transformation)].filter(([, value]) => value.unknown).map(([portId]) => portId))
  return <aside className="lineage-inspector" aria-label="Transformation inspector">
    <div className="flex items-start justify-between gap-4 border-b border-slate-800 p-5"><div><span className="text-[10px] font-extrabold uppercase tracking-[.2em] text-violet-300">{transformation.type}</span><h2 className="mt-2 break-words text-lg font-extrabold">{transformation.name}</h2></div><button aria-label="Close inspector" onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-slate-800 hover:text-white"><X size={17} /></button></div>
    <div className="lineage-inspector-scroll">
      <section><h3 className="inspector-heading"><CircleDot size={14} /> Input ports <span>{inputs.length}</span></h3><PortList ports={inputs} unknownExpressions={unknownExpressions} /></section>
      <section><h3 className="inspector-heading"><CircleDot size={14} /> Output ports <span>{outputs.length}</span></h3><PortList ports={outputs} unknownExpressions={unknownExpressions} /></section>
      <section><h3 className="inspector-heading"><Braces size={14} /> Metadata & diagnostics</h3><Metadata metadata={metadata} /></section>
    </div>
  </aside>
}

function PortList({ ports, unknownExpressions }: { ports: MappingTransformation['ports']; unknownExpressions: Set<number> }) {
  if (!ports.length) return <p className="text-xs text-slate-500">None</p>
  return <div className="space-y-2">{ports.map(port => <div key={port.id} className="rounded-xl border border-slate-700/70 bg-slate-950/40 p-3"><div className="flex items-center justify-between gap-3"><strong className="truncate text-xs text-slate-200">{port.name}</strong><span className="text-[10px] font-bold uppercase text-cyan-300">{port.datatype || 'unknown'}</span></div>{port.expression && <code className="mt-2 block whitespace-pre-wrap break-words rounded-lg bg-black/30 p-2 text-[11px] leading-5 text-amber-200">{port.expression}</code>}{unknownExpressions.has(port.id) && <p className="mt-2 flex items-center gap-1.5 text-[10px] leading-4 text-amber-300"><AlertTriangle size={12} /> Some expression dependencies are unknown; no inferred edge was created.</p>}</div>)}</div>
}
