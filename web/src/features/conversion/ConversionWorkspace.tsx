import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Clipboard, Code2, Download, GitCompareArrows, History, LoaderCircle, RefreshCw, RotateCcw, ShieldAlert, Sparkles } from 'lucide-react'
import LineageGraph from '../lineage/LineageGraph'
import { api, getErrorMessage, type Conversion, type ConversionSummary, type MappingDetail } from '../../lib/api'
import { SqlDiff, SqlEditor } from './CodeEditor'
import ShadowRunsPanel from '../validation/ShadowRunsPanel'

type WorkspaceTab = 'lineage' | 'conversion'
type ArtifactTab = 'sql' | 'schema'
type ConversionView = 'code' | 'validation'

function downloadText(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  URL.revokeObjectURL(url)
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export default function ConversionWorkspace({ mapping }: { mapping: MappingDetail }) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draftSql, setDraftSql] = useState('')
  const [draftVersionId, setDraftVersionId] = useState<number | null>(null)
  const selectionInitialized = useRef(false)
  const [feedback, setFeedback] = useState('')
  const [artifactTab, setArtifactTab] = useState<ArtifactTab>('sql')
  const [mobileTab, setMobileTab] = useState<WorkspaceTab>('lineage')
  const [leftPercent, setLeftPercent] = useState(52)
  const [showDiff, setShowDiff] = useState(false)
  const [copied, setCopied] = useState(false)
  const [conversionView, setConversionView] = useState<ConversionView>('code')

  const versions = useQuery({
    queryKey: ['conversions', mapping.id],
    queryFn: async () => (await api.get<ConversionSummary[]>(`/mappings/${mapping.id}/conversions`)).data,
    retry: false,
  })
  const orderedVersions = useMemo(
    () => [...(versions.data ?? [])].sort((left, right) => right.version - left.version || right.id - left.id),
    [versions.data],
  )
  useEffect(() => {
    selectionInitialized.current = false
    setSelectedId(null)
    setDraftSql('')
    setDraftVersionId(null)
    setFeedback('')
  }, [mapping.id])
  useEffect(() => {
    if (selectionInitialized.current || !orderedVersions.length) return
    selectionInitialized.current = true
    setSelectedId(orderedVersions[0].id)
  }, [orderedVersions])
  const selected = useQuery({
    queryKey: ['conversion', selectedId],
    queryFn: async () => (await api.get<Conversion>(`/conversions/${selectedId}`)).data,
    enabled: selectedId !== null,
    retry: false,
  })
  useEffect(() => {
    if (!selected.data) return
    setDraftSql(selected.data.generated_sql)
    setDraftVersionId(selected.data.id)
    setShowDiff(false)
  }, [selected.data])

  const dirty = Boolean(selected.data && draftVersionId === selected.data.id && draftSql !== selected.data.generated_sql)
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const canDiscard = useCallback(() => !dirty || window.confirm('Discard your unsaved local SQL edits?'), [dirty])
  const refreshVersions = useCallback(async (conversion: Conversion) => {
    await queryClient.invalidateQueries({ queryKey: ['conversions', mapping.id] })
    queryClient.setQueryData(['conversion', conversion.id], conversion)
    queryClient.invalidateQueries({ queryKey: ['dashboard', String(mapping.project_id)] })
    selectionInitialized.current = true
    setSelectedId(conversion.id)
    setMobileTab('conversion')
  }, [mapping.id, mapping.project_id, queryClient])
  const generate = useMutation({
    mutationFn: async () => (await api.post<Conversion>(`/mappings/${mapping.id}/convert`, undefined, { timeout: 130_000 })).data,
    onSuccess: refreshVersions,
  })
  const regenerate = useMutation({
    mutationFn: async () => (await api.post<Conversion>(`/conversions/${selectedId}/regenerate`, { user_comment: feedback }, { timeout: 130_000 })).data,
    onSuccess: conversion => { setFeedback(''); refreshVersions(conversion) },
  })
  const pending = generate.isPending || regenerate.isPending
  const mutationError = generate.error || regenerate.error

  const previous = useMemo(() => {
    if (!selected.data) return undefined
    return orderedVersions.find(item => item.version === selected.data!.version - 1)
  }, [selected.data, orderedVersions])
  const previousDetail = useQuery({
    queryKey: ['conversion', previous?.id],
    queryFn: async () => (await api.get<Conversion>(`/conversions/${previous!.id}`)).data,
    enabled: showDiff && Boolean(previous),
    retry: false,
  })

  const selectVersion = (id: number) => {
    if (id === selectedId || !canDiscard()) return
    selectionInitialized.current = true
    setSelectedId(id)
  }
  const startResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    const container = event.currentTarget.parentElement
    if (!container) return
    const bounds = container.getBoundingClientRect()
    const move = (moveEvent: PointerEvent) => setLeftPercent(Math.min(68, Math.max(35, ((moveEvent.clientX - bounds.left) / bounds.width) * 100)))
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }
  const runGenerate = () => { if (canDiscard() && !pending) generate.mutate() }
  const runRegenerate = () => { if (selectedId && feedback.trim().length >= 2 && canDiscard() && !pending) regenerate.mutate() }

  return <div className="conversion-workspace">
    <div className="conversion-mobile-tabs" role="tablist" aria-label="Conversion workspace views">
      <button role="tab" aria-selected={mobileTab === 'lineage'} onClick={() => setMobileTab('lineage')}><History size={14} /> Lineage</button>
      <button role="tab" aria-selected={mobileTab === 'conversion'} onClick={() => setMobileTab('conversion')}><Code2 size={14} /> SQL conversion</button>
    </div>
    <div className={`conversion-lineage ${mobileTab === 'lineage' ? 'is-mobile-active' : ''}`} style={{ width: `${leftPercent}%` }}><LineageGraph mapping={mapping} /></div>
    <button className="conversion-resizer" aria-label="Resize conversion panels" onPointerDown={startResize} />
    <section className={`conversion-editor-pane ${mobileTab === 'conversion' ? 'is-mobile-active' : ''}`} aria-label="SQL conversion workspace">
      <header className="conversion-header">
        <div><div className="flex items-center gap-2 text-xs font-extrabold text-violet-300"><Sparkles size={14} /> AI conversion</div><h2 className="mt-1 truncate text-sm font-extrabold">{mapping.name}</h2></div>
        <button className="btn-primary px-3 py-2 text-xs" disabled={pending} onClick={runGenerate}>{generate.isPending ? <LoaderCircle className="animate-spin" size={14} /> : <Sparkles size={14} />} Generate SQL</button>
      </header>

      {versions.isLoading ? <div className="conversion-state"><LoaderCircle className="animate-spin text-violet-300" /> Loading versions…</div>
      : versions.isError ? <div className="conversion-state text-rose-200"><ShieldAlert /><span role="alert">{getErrorMessage(versions.error)}</span><button className="btn-outline" onClick={() => versions.refetch()}>Retry</button></div>
      : !versions.data?.length ? <div className="conversion-empty"><Code2 size={30} /><h3>No AI versions yet</h3><p>Generate reviewed dbt SQL from this mapping. Nothing is executed automatically.</p><button className="btn-primary" disabled={pending} onClick={runGenerate}>Generate first version</button></div>
      : <>
        <div className="conversion-version-bar"><label><span>Version</span><select aria-label="Select conversion version" value={selectedId ?? ''} onChange={event => selectVersion(Number(event.target.value))}>{orderedVersions.map(item => <option key={item.id} value={item.id}>v{item.version} · {formatTime(item.created_at)}</option>)}</select></label><button className="conversion-icon-button" disabled={!previous} aria-pressed={showDiff} onClick={() => setShowDiff(value => !value)} title="Compare with previous version"><GitCompareArrows size={15} /> Diff</button></div>
        {selected.isError ? <div className="conversion-state text-rose-200"><ShieldAlert /><span role="alert">{getErrorMessage(selected.error)}</span><button className="btn-outline" onClick={() => selected.refetch()}>Retry</button></div>
        : selected.isLoading || !selected.data ? <div className="conversion-state"><LoaderCircle className="animate-spin" /> Loading generated artifacts…</div> : <>
          <div className="conversion-metadata">
            <div><span>Version</span><strong>v{selected.data.version}</strong></div><div><span>Advisory confidence</span><strong>{selected.data.confidence ?? '—'}{selected.data.confidence !== null ? '%' : ''}</strong></div><div><span>Model</span><strong>{selected.data.model_used ?? 'Unknown'}</strong></div><div><span>Created</span><strong>{formatTime(selected.data.created_at)}</strong></div>
          </div>
          <div className="conversion-mode-tabs" role="tablist" aria-label="Conversion and validation views"><button role="tab" aria-selected={conversionView === 'code'} onClick={() => setConversionView('code')}><Code2 size={13} /> Code & review</button><button role="tab" aria-selected={conversionView === 'validation'} onClick={() => setConversionView('validation')}><ShieldAlert size={13} /> Validation</button></div>
          {conversionView === 'code' ? <>
          <div className="conversion-artifact-tabs" role="tablist"><button role="tab" aria-selected={artifactTab === 'sql'} onClick={() => setArtifactTab('sql')}>model.sql</button><button role="tab" aria-selected={artifactTab === 'schema'} onClick={() => setArtifactTab('schema')}>schema.yml</button><span className={dirty ? 'text-amber-300' : 'text-emerald-300'}>{dirty ? 'Unsaved local edits' : 'AI version unchanged'}</span></div>
          <div className="conversion-editor-actions"><button onClick={() => copy(artifactTab === 'sql' ? draftSql : selected.data!.schema_yml ?? '')}>{copied ? <Check size={14} /> : <Clipboard size={14} />} {copied ? 'Copied' : 'Copy'}</button><button onClick={() => downloadText(`${mapping.name}${artifactTab === 'sql' ? `.v${selected.data!.version}.sql` : '.schema.yml'}`, artifactTab === 'sql' ? draftSql : selected.data!.schema_yml ?? '', 'text/plain')}><Download size={14} /> Download</button>{artifactTab === 'sql' && <button disabled={!dirty} onClick={() => { if (canDiscard()) setDraftSql(selected.data!.generated_sql) }}><RotateCcw size={14} /> Reset</button>}</div>
          <div className="conversion-editor-area">{showDiff && previous ? previousDetail.isLoading ? <div className="conversion-state">Loading comparison…</div> : previousDetail.data ? <SqlDiff original={previousDetail.data.generated_sql} modified={draftSql} /> : <div className="conversion-state text-rose-200">Could not load the previous version.</div> : artifactTab === 'sql' ? <SqlEditor value={draftSql} onChange={setDraftSql} /> : <SqlEditor value={selected.data.schema_yml ?? ''} readOnly />}</div>
          <div className="conversion-review-grid"><div><h3>Confidence reasons</h3>{selected.data.confidence_reasons.length ? <ul>{selected.data.confidence_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : <p>No reasons supplied.</p>}</div><div><h3>Risk flags</h3>{selected.data.risk_flags.length ? <ul>{selected.data.risk_flags.map((risk, index) => <li key={`${risk.code}-${index}`}><span className={`risk-${risk.severity}`}>{risk.severity}</span> {risk.message}</li>)}</ul> : <p>No risks reported.</p>}</div></div>
          <div className="conversion-feedback"><label htmlFor="regeneration-feedback">Regeneration feedback</label><textarea id="regeneration-feedback" value={feedback} onChange={event => setFeedback(event.target.value)} placeholder="For example: Use explicit numeric casts and preserve NULL semantics." /><button className="btn-outline" disabled={pending || feedback.trim().length < 2} onClick={runRegenerate}>{regenerate.isPending ? <LoaderCircle className="animate-spin" size={14} /> : <RefreshCw size={14} />} Regenerate as new version</button></div>
          </> : <ShadowRunsPanel conversionId={selected.data.id} version={selected.data.version} dirty={dirty} />}
        </>}
      </>}
      {mutationError && <div className="conversion-error" role="alert"><AlertTriangle size={17} /><div><strong>AI conversion failed</strong><p>{getErrorMessage(mutationError)} No automatic retry was attempted.</p></div></div>}
      <footer className="conversion-local-note">Editor changes stay in this browser only. They are not saved to PostgreSQL and never overwrite AI-generated versions.</footer>
    </section>
  </div>
}
