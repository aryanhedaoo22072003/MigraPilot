import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, useNodesInitialized, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Focus, GitBranch, RotateCcw } from 'lucide-react'
import type { MappingDetail, MappingTransformation } from '../../lib/api'
import EtlNode from './EtlNode'
import Inspector from './Inspector'
import { layoutLineage, type LineageNodeData } from './graph'

const nodeTypes = { etlNode: EtlNode }

function Canvas({ mapping }: { mapping: MappingDetail }) {
  const [selected, setSelected] = useState<MappingTransformation | null>(null)
  const [selectedPortId, setSelectedPortId] = useState<number | null>(null)
  const [panelWidth, setPanelWidth] = useState(380)
  const graphPaneRef = useRef<HTMLDivElement>(null)
  const nodesInitialized = useNodesInitialized()
  const { fitView } = useReactFlow()
  const inspect = useCallback((transformation: MappingTransformation) => setSelected(transformation), [])
  const selectPort = useCallback((portId: number) => setSelectedPortId(current => current === portId ? null : portId), [])
  const { nodes, edges, highlighted, unknownPorts } = useMemo(() => layoutLineage(mapping, selectedPortId, inspect, selectPort), [mapping, selectedPortId, inspect, selectPort])
  const fit = useCallback(() => fitView({ padding: 0.1, duration: 350, minZoom: 0.34, maxZoom: 1.08 }), [fitView])
  useEffect(() => {
    if (!nodesInitialized) return
    const frame = requestAnimationFrame(fit)
    return () => cancelAnimationFrame(frame)
  }, [nodesInitialized, selected, panelWidth, fit])
  useEffect(() => {
    if (!nodesInitialized || !graphPaneRef.current || typeof ResizeObserver === 'undefined') return
    let frame = 0
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(fit)
    })
    observer.observe(graphPaneRef.current)
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [fit, nodesInitialized])
  const startResize = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = panelWidth
    const move = (moveEvent: PointerEvent) => setPanelWidth(Math.min(560, Math.max(320, startWidth + startX - moveEvent.clientX)))
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      document.body.classList.remove('is-resizing-panel')
    }
    document.body.classList.add('is-resizing-panel')
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }, [panelWidth])
  const minimapColor = useCallback((node: { data?: Partial<LineageNodeData> }) => {
    const type = node.data?.transformation?.type
    if (type === 'Source Definition') return '#42d4ec'
    if (type === 'Target Definition') return '#53d49e'
    if (type === 'Filter') return '#f0b95d'
    return '#9887ff'
  }, [])
  return <div className="lineage-shell">
    <div className="lineage-toolbar"><div className="flex flex-wrap items-center gap-2"><GitBranch size={15} className="text-violet-300" /><span>{mapping.transformations.length} nodes</span><span className="text-slate-700">•</span><span>{mapping.lineage_edges.length} edges</span>{selectedPortId && <><span className="text-slate-700">•</span><span className="text-cyan-300">{highlighted.size} upstream ports</span>{unknownPorts.size > 0 && <span className="lineage-unknown-summary">{unknownPorts.size} unknown</span>}</>}</div><div className="flex gap-2"><button onClick={() => setSelectedPortId(null)} disabled={!selectedPortId}><RotateCcw size={13} /> Clear lineage</button><button onClick={fit}><Focus size={13} /> Fit</button></div></div>
    <div className="lineage-content">
      <div className="lineage-graph-pane" ref={graphPaneRef}><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.1, minZoom: 0.34, maxZoom: 1.08 }} minZoom={0.28} maxZoom={1.8} nodesDraggable panOnScroll selectionOnDrag proOptions={{ hideAttribution: true }} aria-label="ETL lineage graph">
        <Background color="#34415f" gap={28} size={1.2} /><Controls position="bottom-left" showInteractive={false} /><MiniMap position="bottom-right" pannable zoomable nodeColor={minimapColor} nodeStrokeColor="#dbe7ff" nodeStrokeWidth={2} maskColor="rgba(5,9,18,.58)" />
      </ReactFlow></div>
      {selected && <div className="lineage-panel-wrap" style={{ width: panelWidth }}><button type="button" className="lineage-panel-resizer" aria-label="Resize inspector" onPointerDown={startResize} /><Inspector transformation={selected} onClose={() => setSelected(null)} /></div>}
    </div>
  </div>
}

export default function LineageGraph({ mapping }: { mapping: MappingDetail }) {
  return <ReactFlowProvider><Canvas mapping={mapping} /></ReactFlowProvider>
}
