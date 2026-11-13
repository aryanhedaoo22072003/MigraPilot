import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type AutopsyDiagnosis, type AutopsyRecord, type ShadowRun } from '../../lib/api'
import AutopsyPanel from './AutopsyPanel'

vi.mock('../conversion/CodeEditor', () => ({
  SqlEditor: ({ value, readOnly }: { value: string; readOnly?: boolean }) => <textarea aria-label="Suggested SQL editor" value={value} readOnly={readOnly} />,
  SqlDiff: ({ original, modified }: { original: string; modified: string }) => <div aria-label="Autopsy SQL diff">ORIGINAL:{original}|MODIFIED:{modified}</div>,
}))

const failRun: ShadowRun = {
  id: 15, project_id: 7, mapping_id: 3, conversion_id: 4, fixture_id: 'orders_discount_v1', status: 'completed', comparison_result: 'FAIL',
  reference_row_count: 3, migrated_row_count: 3, matched_rows: 0, missing_rows: 0, unexpected_rows: 0,
  duplicate_key_mismatches: 0, column_mismatches: 3, null_mismatches: 0, numeric_precision_differences: 3,
  mismatch_samples: [], execution_time_ms: 40, error: null, created_at: '2026-11-09T18:40:00Z', started_at: '2026-11-09T18:40:01Z', completed_at: '2026-11-09T18:40:02Z',
}
const passRun: ShadowRun = { ...failRun, id: 8, project_id: 6, mapping_id: 2, conversion_id: 2, comparison_result: 'PASS', matched_rows: 3, column_mismatches: 0, numeric_precision_differences: 0 }
const run14: ShadowRun = { ...failRun, id: 14, created_at: '2026-11-09T18:30:00Z' }

const diagnosis: AutopsyDiagnosis = {
  summary: 'The migrated discount expression differs from PowerCenter.', diagnosis_category: 'EXPRESSION_MISMATCH',
  suspected_root_cause: 'PowerCenter uses AMOUNT * 0.90 while migrated SQL uses amount * 0.80.',
  observed_facts: ['NET_AMOUNT differs for matching keys.'], hypotheses: ['The multiplier was translated incorrectly.'],
  affected_transformations: ['EXP_NET'], affected_columns: ['NET_AMOUNT'],
  supporting_evidence: [{ reference: 'transformations.EXP_NET', observation: 'Original output expression is AMOUNT * 0.90.' }],
  confidence: 95, confidence_reasons: ['Expression metadata and SQL differ directly.'],
  suggested_corrective_actions: ['Review the EXP_NET multiplier.'], suggested_sql: 'select amount * 0.90 as net_amount from source_data',
  risks_and_limitations: ['Suggested SQL is unverified.'], recommended_verification_steps: ['Create a reviewed conversion and new Shadow Run.'],
  more_evidence_required: false,
}

function record(overrides: Partial<AutopsyRecord> = {}): AutopsyRecord {
  return {
    id: 3, shadow_run_id: 15, project_id: 7, mapping_id: 3, conversion_id: 4, status: 'completed',
    diagnosis_category: 'EXPRESSION_MISMATCH', diagnosis_json: diagnosis, confidence: 95,
    evidence: diagnosis.supporting_evidence, suggested_corrections: diagnosis.suggested_corrective_actions,
    suggested_sql: diagnosis.suggested_sql, suggested_sql_verified: false, model_used: 'gemini-3.5-flash',
    input_tokens: 100, output_tokens: 200, provider_error: null, created_at: '2026-11-09T19:10:00Z',
    started_at: '2026-11-09T19:10:01Z', completed_at: '2026-11-09T19:10:20Z', ...overrides,
  }
}

function setup(run: ShadowRun = failRun) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}><AutopsyPanel run={run} originalSql="select amount * 0.80 as net_amount from source_data" pollIntervalMs={10} maxPolls={4} /></QueryClientProvider>) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'post').mockRejectedValue(new Error('Unexpected POST'))
})
afterEach(() => vi.useRealTimers())

describe('AutopsyPanel', () => {
  it('keeps PASS runs successful without an Autopsy action or automatic POST', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    setup(passRun)
    expect(await screen.findByText(/No AI Autopsy required/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Analyze Failure' })).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows an explicit Analyze Failure action for FAIL with empty history and never posts on load', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    setup()
    expect(await screen.findByText('No AI Autopsy history')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze Failure' })).toBeEnabled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('accepts POST 202 and polls queued to running to completed exactly once', async () => {
    const queued = record({ id: 4, status: 'queued', diagnosis_category: null, diagnosis_json: null, confidence: null, evidence: [], suggested_corrections: [], suggested_sql: null, model_used: null, completed_at: null })
    const running = { ...queued, status: 'running' as const }
    const completed = record({ id: 4 })
    let detail = 0
    vi.spyOn(api, 'get').mockImplementation(async url => {
      if (url === '/shadow-runs/15/autopsies') return { data: [] } as never
      if (url === '/autopsies/4') return { data: detail++ === 0 ? running : completed } as never
      throw new Error(String(url))
    })
    const post = vi.mocked(api.post).mockResolvedValue({ data: queued })
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Analyze Failure' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(post).toHaveBeenCalledWith('/shadow-runs/15/autopsies')
    expect(await screen.findByText('AI analysis in progress')).toBeInTheDocument()
    expect(await screen.findByText('Expression Mismatch')).toBeInTheDocument()
    expect(detail).toBeGreaterThanOrEqual(2)
  })

  it('renders completed diagnosis, evidence, affected metadata, and read-only suggested SQL/diff', async () => {
    const completed = record()
    vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url === '/autopsies/3' ? completed : [completed] }) as never)
    setup()
    expect(await screen.findByText('Expression Mismatch')).toBeInTheDocument()
    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText(/PowerCenter uses AMOUNT \* 0.90/)).toBeInTheDocument()
    expect(screen.getByText('transformations.EXP_NET')).toBeInTheDocument()
    expect(screen.getByText('Original output expression is AMOUNT * 0.90.')).toBeInTheDocument()
    expect(screen.getByText('EXP_NET')).toBeInTheDocument()
    expect(screen.getByText('NET_AMOUNT')).toBeInTheDocument()
    const editor = screen.getByLabelText('Suggested SQL editor')
    expect(editor).toHaveAttribute('readonly')
    expect(editor).toHaveValue(diagnosis.suggested_sql)
    await userEvent.click(screen.getByRole('button', { name: 'Compare' }))
    expect(screen.getByLabelText('Autopsy SQL diff')).toHaveTextContent('ORIGINAL:select amount * 0.80')
    expect(screen.getByLabelText('Autopsy SQL diff')).toHaveTextContent('MODIFIED:select amount * 0.90')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('keeps the responsive report structure readable for long diagnosis content', async () => {
    const longText = 'A very long diagnostic observation '.repeat(20)
    const longReference = `transformations.EXP_NET.${'nested_expression_path.'.repeat(12)}NET_AMOUNT`
    const detailed = record({ diagnosis_json: { ...diagnosis, summary: longText, suspected_root_cause: longText, supporting_evidence: [{ reference: longReference, observation: longText }] }, evidence: [{ reference: longReference, observation: longText }] })
    vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url === '/autopsies/3' ? detailed : [detailed] }) as never)
    setup()
    expect(await screen.findByText(longReference)).toBeInTheDocument()
    expect(screen.getByLabelText('AI Autopsy').querySelector('.autopsy-layout')).toBeInTheDocument()
    expect(screen.getByLabelText('AI Autopsy').querySelector('.autopsy-report')).toBeInTheDocument()
    expect(screen.getByLabelText('Suggested SQL editor')).toHaveAttribute('readonly')
  })

  it('sorts history newest-first and preserves historical failed attempts without fake confidence', async () => {
    const one = record({ id: 1, status: 'failed', diagnosis_category: null, diagnosis_json: null, confidence: null, evidence: [], suggested_corrections: [], suggested_sql: null, model_used: null, provider_error: 'provider_request', completed_at: '2026-11-09T18:53:00Z' })
    const two = record({ id: 2, status: 'failed', diagnosis_category: null, diagnosis_json: null, confidence: null, evidence: [], suggested_corrections: [], suggested_sql: null, model_used: null, provider_error: 'task_soft_timeout', completed_at: '2026-11-09T19:04:00Z' })
    const three = record()
    vi.spyOn(api, 'get').mockImplementation(async url => {
      if (url === '/shadow-runs/15/autopsies') return { data: [one, three, two] } as never
      const id = Number(url.split('/').pop()); return { data: [one, two, three].find(item => item.id === id) } as never
    })
    setup()
    await screen.findByText('Expression Mismatch')
    const history = screen.getByLabelText('Autopsy history')
    const buttons = within(history).getAllByRole('button').filter(button => /Autopsy #/.test(button.textContent ?? ''))
    expect(buttons.map(button => button.textContent?.match(/Autopsy #(\d)/)?.[1])).toEqual(['3', '2', '1'])
    await userEvent.click(within(history).getByRole('button', { name: /Autopsy #2/ }))
    expect((await screen.findAllByText('AI analysis exceeded its execution limit.')).length).toBeGreaterThan(0)
    expect(screen.queryByText('95%')).not.toBeInTheDocument()
    expect(screen.getByText('task_soft_timeout')).toBeInTheDocument()
  })

  it('reloads history on HTTP 409 and shows backend 422/JWT/network errors safely', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    const conflict = new AxiosError('Conflict', '409', undefined, undefined, { data: { detail: 'Already active' }, status: 409, statusText: 'Conflict', headers: {}, config: {} as never })
    vi.mocked(api.post).mockRejectedValueOnce(conflict)
    const view = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Analyze Failure' }))
    expect(await screen.findByText(/already active/)).toBeInTheDocument()
    expect(get.mock.calls.filter(([url]) => url === '/shadow-runs/15/autopsies').length).toBeGreaterThan(1)
    view.unmount()

    const rejected = new AxiosError('Rejected', '422', undefined, undefined, { data: { detail: 'Shadow run has no diagnostic evidence' }, status: 422, statusText: 'Unprocessable', headers: {}, config: {} as never })
    vi.spyOn(api, 'get').mockResolvedValue({ data: [] } as never)
    vi.mocked(api.post).mockRejectedValueOnce(rejected)
    setup({ ...failRun, status: 'failed', comparison_result: null })
    await userEvent.click(await screen.findByRole('button', { name: 'Analyze Failure' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Shadow run has no diagnostic evidence')
    expect(api.post).toHaveBeenCalledTimes(2)
  })

  it('handles history authentication/network errors and null diagnosis fields', async () => {
    const unauthorized = new AxiosError('Unauthorized', '401', undefined, undefined, { data: { detail: 'Token expired' }, status: 401, statusText: 'Unauthorized', headers: {}, config: {} as never })
    vi.spyOn(api, 'get').mockRejectedValue(unauthorized)
    const first = setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Token expired')
    first.unmount()

    const sparse = record({ diagnosis_json: null, diagnosis_category: null, confidence: null, evidence: [], suggested_corrections: [], suggested_sql: null, model_used: null })
    vi.spyOn(api, 'get').mockImplementation(async url => ({ data: url === '/autopsies/3' ? sparse : [sparse] }) as never)
    setup()
    expect(await screen.findByText('This historical record completed without diagnosis details.')).toBeInTheDocument()
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0)
  })

  it('isolates run 14 and 15 history caches and ignores the old pending response', async () => {
    let resolveOld!: (value: unknown) => void
    vi.spyOn(api, 'get').mockImplementation(url => {
      if (url === '/shadow-runs/15/autopsies') return Promise.resolve({ data: [record()] }) as never
      if (url === '/autopsies/3') return new Promise(resolve => { resolveOld = resolve }) as never
      if (url === '/shadow-runs/14/autopsies') return Promise.resolve({ data: [] }) as never
      throw new Error(String(url))
    })
    const view = setup()
    await waitFor(() => expect(screen.getByText('Autopsy #3')).toBeInTheDocument())
    expect(view.client.getQueryData<AutopsyRecord[]>(['autopsies', 15])?.map(item => item.id)).toEqual([3])
    view.rerender(<QueryClientProvider client={view.client}><AutopsyPanel run={run14} originalSql="select correct" pollIntervalMs={10} maxPolls={2} /></QueryClientProvider>)
    expect(await screen.findByText('No AI Autopsy history')).toBeInTheDocument()
    await act(async () => { resolveOld({ data: record() }); await Promise.resolve() })
    expect(screen.queryByText(/PowerCenter uses AMOUNT/)).not.toBeInTheDocument()
    expect(view.client.getQueryData<AutopsyRecord[]>(['autopsies', 14])).toEqual([])
    expect(view.client.getQueryData<AutopsyRecord[]>(['autopsies', 15])?.map(item => item.id)).toEqual([3])
    view.rerender(<QueryClientProvider client={view.client}><AutopsyPanel run={failRun} originalSql="select correct" pollIntervalMs={10} maxPolls={2} /></QueryClientProvider>)
    expect(await screen.findByText('Autopsy #3')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('stops polling at failed and cleans up polling on unmount', async () => {
    const queued = record({ id: 5, status: 'queued', diagnosis_json: null, diagnosis_category: null, confidence: null, provider_error: null, completed_at: null })
    const failed = { ...queued, status: 'failed' as const, provider_error: 'provider_timeout', completed_at: '2026-11-09T19:15:00Z' }
    let calls = 0
    const get = vi.spyOn(api, 'get').mockImplementation(async url => {
      if (url === '/shadow-runs/15/autopsies') return { data: [queued] } as never
      if (url === '/autopsies/5') { calls += 1; return { data: failed } as never }
      throw new Error(String(url))
    })
    const view = setup()
    expect((await screen.findAllByText(/AI analysis timed out/)).length).toBeGreaterThan(0)
    const before = calls
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
    expect(calls).toBe(before)
    view.unmount()
    const total = get.mock.calls.length
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
    expect(get).toHaveBeenCalledTimes(total)
  })
})
