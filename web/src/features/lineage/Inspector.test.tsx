import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Inspector from './Inspector'

describe('transformation inspector', () => {
  it('shows ports, expressions, filter metadata and diagnostics', () => {
    render(<Inspector onClose={vi.fn()} transformation={{
      id: 3, name: 'FIL_POSITIVE', type: 'Filter', seq_order: 2,
      ports: [
        { id: 3, name: 'AMOUNT', datatype: 'decimal', direction: 'IN', expression: null },
        { id: 1, name: 'NET_AMOUNT', datatype: 'decimal', direction: 'INOUT', expression: 'AMOUNT * 0.90' },
        { id: 2, name: 'FLAG', datatype: 'string', direction: 'OUT', expression: "IIF(NET_AMOUNT > 0, 'Y', 'N')" },
      ],
      logic_json: { table_attributes: { 'Filter Condition': 'NET_AMOUNT > 0' }, diagnostics: ['Reviewed export'] },
    }} />)
    expect(screen.getByText('FIL_POSITIVE')).toBeInTheDocument()
    expect(screen.getAllByText('NET_AMOUNT')).toHaveLength(2)
    expect(screen.getAllByText('AMOUNT * 0.90')).toHaveLength(2)
    expect(screen.getByText(/Filter Condition/)).toBeInTheDocument()
    expect(screen.getByText(/Reviewed export/)).toBeInTheDocument()
  })

  it('warns when an expression dependency cannot be resolved', () => {
    render(<Inspector onClose={vi.fn()} transformation={{
      id: 4, name: 'EXP_UNKNOWN', type: 'Expression', seq_order: 1, logic_json: {},
      ports: [{ id: 10, name: 'RESULT', datatype: 'decimal', direction: 'OUT', expression: 'MISSING_COLUMN + 1' }],
    }} />)
    expect(screen.getByText(/dependencies are unknown/)).toBeInTheDocument()
  })
})
