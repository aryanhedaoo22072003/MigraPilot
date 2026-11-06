import { lazy, Suspense } from 'react'

const MonacoEditor = lazy(() => import('@monaco-editor/react').then(module => ({ default: module.Editor })))
const MonacoDiffEditor = lazy(() => import('@monaco-editor/react').then(module => ({ default: module.DiffEditor })))

const options = {
  minimap: { enabled: false },
  fontSize: 13,
  lineHeight: 21,
  lineNumbers: 'on' as const,
  wordWrap: 'on' as const,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  padding: { top: 14, bottom: 14 },
}

function LoadingEditor() {
  return <div className="grid h-full place-items-center bg-[#090e1b] text-xs font-bold text-slate-500">Loading editor…</div>
}

export function SqlEditor({ value, onChange, readOnly = false }: { value: string; onChange?: (value: string) => void; readOnly?: boolean }) {
  return <Suspense fallback={<LoadingEditor />}><MonacoEditor aria-label="SQL editor" language="sql" theme="vs-dark" value={value} onChange={next => onChange?.(next ?? '')} options={{ ...options, readOnly }} /></Suspense>
}

export function SqlDiff({ original, modified }: { original: string; modified: string }) {
  return <Suspense fallback={<LoadingEditor />}><MonacoDiffEditor language="sql" theme="vs-dark" original={original} modified={modified} options={{ ...options, readOnly: true, renderSideBySide: true }} /></Suspense>
}
