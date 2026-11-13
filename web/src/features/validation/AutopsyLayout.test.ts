import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('AI Autopsy responsive layout styles', () => {
  it('uses the actual report container width and stacks nested panels when constrained', () => {
    const css = readFileSync(`${process.cwd()}/src/index.css`, 'utf8')
    expect(css).toContain('.shadow-report { min-width: 0;')
    expect(css).toContain('container-type: inline-size')
    expect(css).toMatch(/@container \(max-width: 720px\)[\s\S]*?\.autopsy-layout \{ grid-template-columns: minmax\(0,1fr\)/)
    expect(css).toContain('.autopsy-sql-editor { width: 100%; min-width: 0;')
    expect(css).toContain('overflow-wrap: anywhere')
  })
})
