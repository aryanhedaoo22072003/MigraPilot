import type { ReactNode } from 'react'
import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MappingDetail } from '../../lib/api'

const fitView = vi.fn()
let resizeCallback: ResizeObserverCallback

vi.mock('@xyflow/react', () => ({
  ReactFlowProvider: ({ children }: { children: ReactNode }) => children,
  ReactFlow: ({ children, fitViewOptions }: { children: ReactNode; fitViewOptions: unknown }) => <div data-testid="flow" data-fit-options={JSON.stringify(fitViewOptions)}>{children}</div>,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  Handle: () => null,
  Position: { Left: 'left', Right: 'right' },
  useNodesInitialized: () => true,
  useReactFlow: () => ({ fitView }),
}))

import LineageGraph from './LineageGraph'

const mapping: MappingDetail = {
  id: 2, project_id: 6, upload_id: 1, name: 'mapping', description: null, status: 'parsed', created_at: '2026-11-01T00:00:00Z',
  transformations: [{ id: 1, name: 'SRC', type: 'Source Definition', logic_json: {}, seq_order: 0, ports: [] }],
  lineage_edges: [],
}

describe('LineageGraph viewport', () => {
  beforeEach(() => {
    fitView.mockReset().mockResolvedValue(true)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resizeCallback = callback }
      observe() {}
      disconnect() {}
      unobserve() {}
    })
  })

  it('fits measured nodes initially and refits when the graph pane is resized', async () => {
    const view = render(<LineageGraph mapping={mapping} />)
    await waitFor(() => expect(fitView).toHaveBeenCalled())
    expect(JSON.parse(view.getByTestId('flow').dataset.fitOptions!)).toMatchObject({ padding: 0.1, maxZoom: 1.08 })
    const calls = fitView.mock.calls.length

    act(() => resizeCallback([], {} as ResizeObserver))
    expect(fitView.mock.calls.length).toBeGreaterThan(calls)
    expect(fitView).toHaveBeenLastCalledWith(expect.objectContaining({ padding: 0.1, maxZoom: 1.08 }))
  })
})
