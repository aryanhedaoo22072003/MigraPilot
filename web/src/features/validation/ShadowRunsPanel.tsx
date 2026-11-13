import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock3, FlaskConical, LoaderCircle, Play, RefreshCw, ShieldAlert, XCircle } from 'lucide-react'
import { api, getErrorMessage, type ShadowMismatchSample, type ShadowRun } from '../../lib/api'
import AutopsyPanel from './AutopsyPanel'

const FIXTURE_ID = 'orders_discount_v1'
const active = (run?: ShadowRun) => run?.status === 'queued' || run?.status === 'running'

function formatTime(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

function StatusBadge({ run }: { run: ShadowRun }) {
  const outcome = run.status === 'completed' ? run.comparison_result : run.status
  const label = outcome === 'PASS' ? 'PASS' : outcome === 'FAIL' ? 'FAIL' : run.status === 'failed' ? 'EXECUTION FAILED' : run.status.toUpperCase()
  return <span className={`shadow-status shadow-${String(outcome).toLowerCase()}`}>{active(run) && <LoaderCircle size={12} className="animate-spin" />}{label}</span>
}

const metrics: Array<[keyof ShadowRun, string]> = [
  ['reference_row_count', 'Reference rows'], ['migrated_row_count', 'Migrated rows'], ['matched_rows', 'Matched'],
  ['missing_rows', 'Missing'], ['unexpected_rows', 'Unexpected'], ['duplicate_key_mismatches', 'Duplicate keys'],
  ['column_mismatches', 'Column mismatches'], ['null_mismatches', 'NULL mismatches'], ['numeric_precision_differences', 'Numeric differences'],
]

function sampleLabel(sample: ShadowMismatchSample) {
  if (sample.kind === 'missing') return 'Missing row'
  if (sample.kind === 'unexpected') return 'Unexpected row'
  if (sample.kind === 'duplicate') return 'Duplicate key'
  if (sample.column) return `Column mismatch · ${sample.column}`
  return 'Mismatch detail'
}

export default function ShadowRunsPanel({ conversionId, version, dirty, originalSql = '', pollIntervalMs = 3000 }: { conversionId: number; version: number; dirty: boolean; originalSql?: string; pollIntervalMs?: number }) {
  const queryClient = useQueryClient()
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const terminalRefresh = useRef<number | null>(null)
  const submitting = useRef(false)
  const history = useQuery({
    queryKey: ['shadow-runs', conversionId],
    queryFn: async () => (await api.get<ShadowRun[]>(`/conversions/${conversionId}/shadow-runs`)).data,
    retry: false,
  })
  const ordered = useMemo(() => [...(history.data ?? [])].sort((a, b) => b.id - a.id), [history.data])
  useEffect(() => { setSelectedRunId(null); terminalRefresh.current = null }, [conversionId])
  useEffect(() => { if (selectedRunId === null && ordered.length) setSelectedRunId(ordered[0].id) }, [ordered, selectedRunId])
  const report = useQuery({
    queryKey: ['shadow-run', selectedRunId],
    queryFn: async () => (await api.get<ShadowRun>(`/shadow-runs/${selectedRunId}`)).data,
    enabled: selectedRunId !== null,
    retry: false,
    refetchInterval: query => active(query.state.data) ? pollIntervalMs : false,
    refetchIntervalInBackground: false,
  })
  useEffect(() => {
    if (!report.data || active(report.data) || terminalRefresh.current === report.data.id) return
    terminalRefresh.current = report.data.id
    queryClient.invalidateQueries({ queryKey: ['shadow-runs', conversionId] })
  }, [conversionId, queryClient, report.data])
  const start = useMutation({
    mutationFn: async () => (await api.post<ShadowRun>(`/conversions/${conversionId}/shadow-runs`, { fixture_id: FIXTURE_ID })).data,
    retry: false,
    onSuccess: run => {
      terminalRefresh.current = null
      queryClient.setQueryData(['shadow-run', run.id], run)
      setSelectedRunId(run.id)
      queryClient.invalidateQueries({ queryKey: ['shadow-runs', conversionId] })
    },
    onSettled: () => { submitting.current = false },
  })
  const run = report.data
  const submissionBlocked = start.isPending || active(run)

  return <div className="shadow-panel">
    <div className="shadow-heading">
      <div><span><FlaskConical size={14} /> Isolated validation</span><h3>Shadow Runs · saved v{version}</h3><p>Executes the immutable saved SQL against the controlled <code>{FIXTURE_ID}</code> fixture. Generated SQL is never run against the application database.</p></div>
      <button className="btn-primary" disabled={submissionBlocked} onClick={() => { if (submitting.current || submissionBlocked) return; submitting.current = true; start.mutate() }}>{start.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Play size={14} />}{active(run) ? 'Validation in progress' : 'Run Validation'}</button>
    </div>
    {dirty && <div className="shadow-draft-warning" role="note"><AlertTriangle size={15} /><span>Your editor has unsaved local changes. Validation will use saved conversion v{version}, not the local draft.</span></div>}
    {start.isError && <div className="shadow-error" role="alert"><ShieldAlert size={16} /><div><strong>Could not start validation</strong><p>{getErrorMessage(start.error)} No automatic retry was attempted.</p></div></div>}

    <div className="shadow-layout">
      <aside className="shadow-history" aria-label="Shadow run history">
        <div className="shadow-section-title"><span>Run history</span><button onClick={() => history.refetch()} aria-label="Refresh shadow run history"><RefreshCw size={13} /></button></div>
        {history.isLoading ? <div className="shadow-skeleton" aria-label="Loading validation history"><i /><i /><i /></div>
        : history.isError ? <div className="shadow-inline-error" role="alert">{getErrorMessage(history.error)}</div>
        : !ordered.length ? <div className="shadow-empty"><Clock3 size={20} /><strong>No validation runs</strong><span>Run the selected saved version to create the first report.</span></div>
        : <div className="shadow-history-list">{ordered.map(item => <button key={item.id} className={selectedRunId === item.id ? 'is-selected' : ''} onClick={() => setSelectedRunId(item.id)}><span><strong>Run #{item.id}</strong><StatusBadge run={item} /></span><small>{item.fixture_id}</small><small>{formatTime(item.created_at)} · {item.execution_time_ms === null ? '—' : `${item.execution_time_ms} ms`}</small></button>)}</div>}
      </aside>

      <section className="shadow-report" aria-label="Shadow run comparison report">
        {selectedRunId === null ? <div className="shadow-empty shadow-report-empty"><FlaskConical size={24} /><strong>Select or start a run</strong><span>Persisted comparison details will appear here.</span></div>
        : report.isLoading ? <div className="shadow-report-loading"><LoaderCircle className="animate-spin" /> Loading comparison report…</div>
        : report.isError ? <div className="shadow-error" role="alert"><ShieldAlert size={16} /><div><strong>Could not load report</strong><p>{getErrorMessage(report.error)}</p></div></div>
        : run ? <>
          <div className="shadow-report-header" aria-live="polite"><div>{run.status === 'completed' && run.comparison_result === 'PASS' ? <CheckCircle2 className="text-emerald-300" /> : run.status === 'completed' && run.comparison_result === 'FAIL' ? <XCircle className="text-amber-300" /> : run.status === 'failed' ? <ShieldAlert className="text-rose-300" /> : <LoaderCircle className="animate-spin text-cyan-300" />}<div><h4>Shadow Run #{run.id}</h4><p>Created {formatTime(run.created_at)}</p></div></div><StatusBadge run={run} /></div>
          {active(run) && <div className="shadow-progress"><span /><p>{run.status === 'queued' ? 'Waiting for an isolated worker…' : 'Executing and comparing controlled fixture results…'}</p></div>}
          {run.status === 'failed' && <div className="shadow-execution-failed"><strong>Execution failed</strong><p>{run.error || 'The sandbox could not complete this run.'}</p></div>}
          {run.status === 'completed' && <>
            <div className="shadow-metrics">{metrics.map(([key, label]) => <div key={key}><span>{label}</span><strong>{run[key] as number ?? '—'}</strong></div>)}</div>
            <div className="shadow-timing"><span>Started <strong>{formatTime(run.started_at)}</strong></span><span>Completed <strong>{formatTime(run.completed_at)}</strong></span><span>Execution <strong>{run.execution_time_ms === null ? '—' : `${run.execution_time_ms} ms`}</strong></span></div>
            {run.comparison_result === 'PASS' ? <div className="shadow-pass-summary"><CheckCircle2 size={18} /><div><strong>Reference and migrated output match</strong><p>All {run.matched_rows ?? 0} business-key rows matched within the configured decimal tolerance.</p></div></div>
            : <div className="shadow-mismatches"><div className="shadow-section-title"><span>Mismatch explorer</span><small>{run.mismatch_samples.length} bounded samples</small></div>{run.mismatch_samples.length ? run.mismatch_samples.map((sample, index) => <details key={index}><summary><span>{sampleLabel(sample)}</span><code>{sample.key?.map(String).join(' · ') || `sample ${index + 1}`}</code></summary><dl>{sample.kind && <><dt>Kind</dt><dd>{sample.kind}</dd></>}{sample.column && <><dt>Column</dt><dd>{sample.column}</dd></>} {'expected' in sample && <><dt>Expected</dt><dd>{String(sample.expected ?? 'NULL')}</dd></>} {'actual' in sample && <><dt>Actual</dt><dd>{String(sample.actual ?? 'NULL')}</dd></>}</dl></details>) : <p className="shadow-no-samples">Mismatch counters were returned without row samples.</p>}</div>}
          </>}
          <AutopsyPanel key={run.id} run={run} originalSql={originalSql} />
        </> : null}
      </section>
    </div>
  </div>
}
