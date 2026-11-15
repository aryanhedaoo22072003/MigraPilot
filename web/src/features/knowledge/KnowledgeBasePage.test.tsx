import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type KnowledgeCandidate } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import KnowledgeBasePage from './KnowledgeBasePage'

vi.mock('../conversion/CodeEditor', () => ({
  SqlEditor: ({ value, readOnly }: { value: string; readOnly?: boolean }) => <textarea aria-label="Corrected SQL" value={value} readOnly={readOnly} />,
  SqlDiff: ({ original, modified }: { original: string; modified: string }) => <div aria-label="Knowledge SQL diff">{original}|{modified}</div>,
}))

const candidate: KnowledgeCandidate = {
  id: 1, project_id: 7, mapping_id: 3, owner_id: 1, source_autopsy_id: 3, original_shadow_run_id: 15,
  original_conversion_id: 4, corrected_conversion_id: 6, corrected_conversion_version: 3, passing_shadow_run_id: 19,
  diagnosis_category: 'EXPRESSION_MISMATCH', transformation_identifiers: ['EXP_NET'], affected_columns: ['net_amount'], signature_metadata: {},
  root_cause_summary: 'The migrated multiplier used 0.80 instead of 0.90.', suggested_corrective_actions: ['Correct the multiplier.'],
  proposed_sql: 'select amount * 0.90 as net_amount', verified_remediation_summary: 'Corrected multiplier passed the bounded fixture.', fixture_id: 'orders_discount_v1',
  verification_outcome: 'PASS', verification_scope: 'orders_discount_v1', verification_evidence: { matched_rows: 3, column_mismatches: 0 },
  status: 'published', reviewer_id: 1, review_notes: 'Reviewed evidence.', created_at: '2026-11-10T10:00:00Z', verified_at: '2026-11-10T11:00:00Z',
  approved_at: '2026-11-10T12:00:00Z', published_at: '2026-11-10T12:00:00Z', archived_at: null,
  events: [
    { id: 1, actor_id: 1, event_type: 'created', from_status: null, to_status: 'draft', notes: null, evidence_snapshot: null, created_at: '2026-11-10T10:00:00Z' },
    { id: 2, actor_id: 1, event_type: 'verified', from_status: 'draft', to_status: 'verified', notes: 'Passing run attached.', evidence_snapshot: { shadow_run_id: 19 }, created_at: '2026-11-10T11:00:00Z' },
    { id: 3, actor_id: 1, event_type: 'approve', from_status: 'verified', to_status: 'published', notes: 'Reviewed evidence.', evidence_snapshot: null, created_at: '2026-11-10T12:00:00Z' },
  ],
}

function setup(path = '/app/projects/7/knowledge?candidate=1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/app/projects/:id/knowledge" element={<KnowledgeBasePage />} /></Routes></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  vi.restoreAllMocks()
  useAuth.setState({ user: { id: 1, email: 'owner@example.com', role: 'engineer', created_at: '' }, token: 'test' })
  vi.spyOn(api, 'post').mockRejectedValue(new Error('Unexpected POST'))
  vi.spyOn(api, 'get').mockImplementation(async (url, config) => {
    if (url === '/projects/7/knowledge-candidates') {
      const status = (config?.params as { status?: string } | undefined)?.status
      return { data: { items: !status || status === 'published' ? [candidate] : [], total: !status || status === 'published' ? 1 : 0, limit: 20, offset: 0 } } as never
    }
    if (url === '/knowledge-candidates/1') return { data: candidate } as never
    if (url === '/conversions/4') return { data: { id: 4, mapping_id: 3, version: 1, generated_sql: 'select amount * 0.80 as net_amount', schema_yml: '', confidence: 80, confidence_reasons: [], risk_flags: [], model_used: 'gemini', created_at: '' } } as never
    if (url === '/conversions/6') return { data: { id: 6, mapping_id: 3, version: 3, generated_sql: 'select amount * 0.90 as net_amount', schema_yml: '', confidence: 90, confidence_reasons: [], risk_flags: [], model_used: 'gemini', created_at: '' } } as never
    if (url === '/shadow-runs/15') return { data: { comparison_result: 'FAIL' } } as never
    if (url === '/shadow-runs/19') return { data: { comparison_result: 'PASS' } } as never
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('KnowledgeBasePage', () => {
  it('renders published evidence, read-only SQL diff, and chronological audit without writes', async () => {
    setup()
    expect(await screen.findByText('Knowledge #1: Expression Mismatch')).toBeInTheDocument()
    expect(await screen.findByLabelText('Knowledge SQL diff')).toHaveTextContent('0.80')
    expect(screen.getByLabelText('Knowledge SQL diff')).toHaveTextContent('0.90')
    expect(screen.getByText('orders_discount_v1 / orders_discount_v1')).toBeInTheDocument()
    expect(screen.getByText('none → draft')).toBeInTheDocument()
    expect(screen.getByText('draft → verified')).toBeInTheDocument()
    expect(screen.getByText('verified → published')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('filters by status and keeps project-scoped requests', async () => {
    setup('/app/projects/7/knowledge')
    expect(await screen.findByText('Knowledge #1')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Knowledge status'), 'draft')
    expect(await screen.findByText(/No knowledge records/)).toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/projects/7/knowledge-candidates', expect.objectContaining({ params: expect.objectContaining({ status: 'draft' }) })))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('hides lifecycle writes from viewers', async () => {
    useAuth.setState({ user: { id: 2, email: 'viewer@example.com', role: 'viewer', created_at: '' } })
    setup()
    expect(await screen.findByText('Knowledge #1: Expression Mismatch')).toBeInTheDocument()
    expect(screen.queryByText('Review lifecycle')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })
})
