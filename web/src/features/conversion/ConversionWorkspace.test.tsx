import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConversionWorkspace from './ConversionWorkspace'
import { api, type Conversion, type MappingDetail } from '../../lib/api'

vi.mock('./CodeEditor', () => ({
  SqlEditor: ({ value, onChange, readOnly }: { value: string; onChange?: (value: string) => void; readOnly?: boolean }) => <textarea aria-label={readOnly ? 'Read only artifact' : 'SQL editor'} value={value} readOnly={readOnly} onChange={event => onChange?.(event.target.value)} />,
  SqlDiff: ({ original, modified }: { original: string; modified: string }) => <div aria-label="SQL diff">ORIGINAL:{original}|MODIFIED:{modified}</div>,
}))
vi.mock('../lineage/LineageGraph', () => ({ default: () => <div>Existing lineage graph</div> }))

const mapping: MappingDetail = {
  id: 2, project_id: 6, upload_id: 1, name: 'm_orders_expression_filter', description: null, status: 'converted', created_at: '2026-11-01T10:00:00Z',
  transformations: [], lineage_edges: [],
}
const v1: Conversion = {
  id: 1, mapping_id: 2, version: 1, generated_sql: 'select 1 as order_id', schema_yml: 'version: 2\nmodels: []', confidence: 82,
  confidence_reasons: ['Connectors resolved.'], risk_flags: [], model_used: 'gemini-3.5-flash', created_at: '2026-11-01T10:00:00Z',
}
const v2: Conversion = {
  ...v1, id: 2, version: 2, generated_sql: 'select 2 as order_id', confidence: 91, confidence_reasons: ['All transformations supported.'],
  risk_flags: [{ code: 'NULL_REVIEW', severity: 'medium', message: 'Review NULL behavior.', transformation: 'EXP', port: 'ORDER_ID' }], created_at: '2026-11-02T10:00:00Z',
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}><ConversionWorkspace mapping={mapping} /></QueryClientProvider>) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'post').mockRejectedValue(new Error('Unexpected POST'))
  vi.spyOn(api, 'get').mockImplementation(async url => {
    if (url === '/mappings/2/conversions') return { data: [v1, v2] } as never
    if (url === '/conversions/2') return { data: v2 } as never
    if (url === '/conversions/1') return { data: v1 } as never
    if (url === '/conversions/3') return { data: { ...v2, id: 3, version: 3, generated_sql: 'select 3 as order_id' } } as never
    if (url === '/conversions/4') return { data: { ...v2, id: 4, version: 4, generated_sql: 'select 4 as order_id' } } as never
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('ConversionWorkspace', () => {
  it('renders real version metadata, SQL, schema YAML, lineage, and a read-only diff', async () => {
    setup()
    expect(screen.getByText('Existing lineage graph')).toBeInTheDocument()
    expect(await screen.findByDisplayValue('select 2 as order_id')).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('Review NULL behavior.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'schema.yml' }))
    expect(screen.getByLabelText('Read only artifact')).toHaveValue('version: 2\nmodels: []')
    expect(screen.getByLabelText('Read only artifact')).toHaveAttribute('readonly')
    await userEvent.click(screen.getByTitle('Compare with previous version'))
    expect(await screen.findByLabelText('SQL diff')).toHaveTextContent('ORIGINAL:select 1 as order_id')
  })

  it('selects the highest version initially and preserves an intentional selection during refresh', async () => {
    const { client } = setup()
    expect(await screen.findByDisplayValue('select 2 as order_id')).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Select conversion version'), '1')
    expect(await screen.findByDisplayValue('select 1 as order_id')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('gemini-3.5-flash')).toBeInTheDocument()
    expect(screen.getAllByText(/Nov 1, 2026/).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('tab', { name: 'schema.yml' }))
    expect(screen.getByLabelText('Read only artifact')).toHaveValue(v1.schema_yml)

    await client.invalidateQueries({ queryKey: ['conversions', 2] })
    await waitFor(() => expect(screen.getByLabelText('Select conversion version')).toHaveValue('1'))
    expect(screen.getByText('AI version unchanged')).toBeInTheDocument()
  })

  it('keeps edits local, marks them unsaved, and warns before reset or version changes', async () => {
    setup()
    let editor = await screen.findByLabelText('SQL editor')
    expect(screen.getByText('AI version unchanged')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'schema.yml' }))
    expect(screen.getByText('AI version unchanged')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'model.sql' }))
    expect(screen.getByText('AI version unchanged')).toBeInTheDocument()
    editor = screen.getByLabelText('SQL editor')
    fireEvent.change(editor, { target: { value: 'select 99 as local_draft' } })
    expect(screen.getByText('Unsaved local edits')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()

    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByDisplayValue('select 99 as local_draft')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByDisplayValue('select 2 as order_id')).toBeInTheDocument()
    expect(confirm).toHaveBeenCalledWith('Discard your unsaved local SQL edits?')
  })

  it('generates and regenerates immutable versions without frontend retries', async () => {
    const v3 = { ...v2, id: 3, version: 3, generated_sql: 'select 3 as order_id' }
    const post = vi.mocked(api.post).mockResolvedValueOnce({ data: v3 }).mockResolvedValueOnce({ data: { ...v3, id: 4, version: 4 } })
    setup()
    await screen.findByDisplayValue('select 2 as order_id')

    await userEvent.click(screen.getByRole('button', { name: 'Generate SQL' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(post.mock.calls[0][0]).toBe('/mappings/2/convert')
    expect(post.mock.calls[0][2]).toMatchObject({ timeout: 130_000 })

    fireEvent.change(screen.getByLabelText('Regeneration feedback'), { target: { value: 'Use explicit casts.' } })
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate as new version' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    expect(post.mock.calls[1][0]).toBe('/conversions/3/regenerate')
    expect(post.mock.calls[1][1]).toEqual({ user_comment: 'Use explicit casts.' })
  })

  it('shows authentication and generation failures without automatic retry', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new AxiosError('Unauthorized', '401', undefined, undefined, { data: { detail: 'Not authenticated' }, status: 401, statusText: 'Unauthorized', headers: {}, config: {} as never }))
    const post = vi.mocked(api.post).mockRejectedValue(new AxiosError('Unavailable', '503', undefined, undefined, { data: { detail: 'AI conversion is not configured' }, status: 503, statusText: 'Unavailable', headers: {}, config: {} as never }))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Not authenticated')

    cleanup()
    vi.mocked(api.get).mockResolvedValueOnce({ data: [] } as never)
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Generate first version' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('AI conversion is not configured')
    expect(screen.getByRole('alert')).toHaveTextContent('No automatic retry was attempted')
    expect(post).toHaveBeenCalledTimes(1)
  })
})
