import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type ShadowRun } from '../../lib/api'
import ShadowRunsPanel from './ShadowRunsPanel'

const base: ShadowRun = {
  id: 2, project_id: 6, mapping_id: 2, conversion_id: 2, fixture_id: 'orders_discount_v1', status: 'completed', comparison_result: 'PASS',
  reference_row_count: 3, migrated_row_count: 3, matched_rows: 3, missing_rows: 0, unexpected_rows: 0,
  duplicate_key_mismatches: 0, column_mismatches: 0, null_mismatches: 0, numeric_precision_differences: 0,
  mismatch_samples: [], execution_time_ms: 37, error: null, created_at: '2026-11-06T08:00:00Z', started_at: '2026-11-06T08:00:01Z', completed_at: '2026-11-06T08:00:02Z',
}

function setup(props = { conversionId: 2, version: 2, dirty: false }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}><ShadowRunsPanel {...props} pollIntervalMs={10} /></QueryClientProvider>) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'post').mockRejectedValue(new Error('Unexpected POST'))
})
afterEach(() => vi.useRealTimers())

describe('ShadowRunsPanel', () => {
  it('renders an empty history without implying a result', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    setup()
    expect(await screen.findByText('No validation runs')).toBeInTheDocument()
    expect(screen.queryByText('PASS')).not.toBeInTheDocument()
  })

  it('renders persisted PASS metrics and timestamps', async () => {
    vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url.includes('/shadow-runs/2') ? base : [base] }) as never)
    setup()
    expect(await screen.findByText('Reference and migrated output match')).toBeInTheDocument()
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText('37 ms')).toBeInTheDocument()
    expect(screen.getAllByText('PASS').length).toBeGreaterThan(0)
  })

  it('starts once, polls QUEUED to RUNNING to COMPLETED/PASS, and refreshes history', async () => {
    const queued = { ...base, id: 10, status: 'queued' as const, comparison_result: null, completed_at: null, execution_time_ms: null }
    const running = { ...queued, status: 'running' as const }
    let detailCalls = 0
    const get = vi.spyOn(api, 'get').mockImplementation(async url => {
      if (url === '/conversions/2/shadow-runs') return { data: [] } as never
      if (url === '/shadow-runs/10') return { data: detailCalls++ === 0 ? running : { ...base, id: 10 } } as never
      throw new Error(String(url))
    })
    const post = vi.mocked(api.post).mockResolvedValue({ data: queued })
    setup()
    await screen.findByText('No validation runs')
    fireEvent.click(screen.getByRole('button', { name: 'Run Validation' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(post).toHaveBeenCalledWith('/conversions/2/shadow-runs', { fixture_id: 'orders_discount_v1' })
    expect((await screen.findAllByText('RUNNING')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Validation in progress' })).toBeDisabled()
    await waitFor(() => expect(screen.getAllByText('PASS').length).toBeGreaterThan(0))
    expect(get.mock.calls.filter(([url]) => url === '/shadow-runs/10')).toHaveLength(2)
  })

  it('renders completed FAIL samples and execution failure as distinct states', async () => {
    const failedComparison = { ...base, comparison_result: 'FAIL' as const, matched_rows: 2, column_mismatches: 1, null_mismatches: 1, mismatch_samples: [{ key: [4], column: 'net_amount', expected: null, actual: '9.1' }] }
    const get = vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url.includes('/shadow-runs/2') ? failedComparison : [failedComparison] }) as never)
    const view = setup()
    expect(await screen.findByText('FAIL')).toBeInTheDocument()
    expect(await screen.findByText('Column mismatch · net_amount')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Column mismatch · net_amount'))
    expect(screen.getByText('Expected')).toBeInTheDocument()
    view.unmount()

    const executionFailure = { ...base, id: 3, status: 'failed' as const, comparison_result: null, error: 'execution_timeout: Shadow query exceeded its time limit' }
    get.mockImplementation(async url => ({ data: url.includes('/shadow-runs/3') ? executionFailure : [executionFailure] }) as never)
    setup()
    expect((await screen.findAllByText('EXECUTION FAILED')).length).toBeGreaterThan(0)
    expect(await screen.findByText(/execution_timeout/)).toBeInTheDocument()
    expect(screen.queryByText('PASS')).not.toBeInTheDocument()
  })

  it('surfaces JWT and network failures and does not retry the POST', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(new AxiosError('Unauthorized', '401', undefined, undefined, { data: { detail: 'Token expired' }, status: 401, statusText: 'Unauthorized', headers: {}, config: {} as never }))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Token expired')

    const post = vi.mocked(api.post).mockRejectedValue(new AxiosError('Network Error'))
    fireEvent.click(screen.getByRole('button', { name: 'Run Validation' }))
    expect(await screen.findByText(/Cannot connect to API/)).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('prevents duplicate submissions and warns that dirty SQL is not validated', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    let resolvePost!: (value: unknown) => void
    const post = vi.mocked(api.post).mockImplementation(() => new Promise(resolve => { resolvePost = resolve }) as never)
    setup({ conversionId: 2, version: 2, dirty: true })
    expect(await screen.findByText(/not the local draft/)).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Run Validation' })
    fireEvent.click(button); fireEvent.click(button)
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('button', { name: /Run Validation/ })).toBeDisabled()
    resolvePost({ data: { ...base, status: 'queued', comparison_result: null } })
  })

  it('switches history with the selected conversion and cleans up polling on unmount', async () => {
    const running = { ...base, status: 'running' as const, comparison_result: null }
    const get = vi.spyOn(api, 'get').mockImplementation(async url => {
      if (url === '/conversions/2/shadow-runs') return { data: [running] } as never
      if (url === '/conversions/1/shadow-runs') return { data: [] } as never
      if (url === '/shadow-runs/2') return { data: running } as never
      throw new Error(String(url))
    })
    const view = setup()
    await waitFor(() => expect(screen.getAllByText('RUNNING').length).toBeGreaterThan(0))
    view.rerender(<QueryClientProvider client={view.client}><ShadowRunsPanel conversionId={1} version={1} dirty={false} pollIntervalMs={10} /></QueryClientProvider>)
    expect(await screen.findByText('No validation runs')).toBeInTheDocument()
    view.unmount()
    const calls = get.mock.calls.length
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
    expect(get).toHaveBeenCalledTimes(calls)
  })
})
