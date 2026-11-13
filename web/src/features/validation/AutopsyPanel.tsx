import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { AlertTriangle, BrainCircuit, Check, ChevronDown, Clipboard, Clock3, GitCompareArrows, LoaderCircle, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import {
  getAutopsy, getErrorMessage, listAutopsies, startAutopsy,
  type AutopsyDiagnosisCategory, type AutopsyRecord, type ShadowRun,
} from '../../lib/api'
import { SqlDiff, SqlEditor } from '../conversion/CodeEditor'

const isActive = (item?: AutopsyRecord) => item?.status === 'queued' || item?.status === 'running'

function formatTime(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

export function humanizeCategory(value: AutopsyDiagnosisCategory | null | undefined) {
  if (!value) return 'Not available'
  if (value === 'UNKNOWN') return 'Unknown'
  return value.split('_').map(word => word === 'NULL' || word === 'SQL' ? word : `${word[0]}${word.slice(1).toLowerCase()}`).join(' ')
}

function failureMessage(error: string | null) {
  if (error === 'provider_timeout') return 'AI analysis timed out. Your Shadow Run results are unchanged.'
  if (error === 'provider_request') return 'AI provider could not complete this request.'
  if (error === 'task_soft_timeout') return 'AI analysis exceeded its execution limit.'
  if (error === 'provider_quota') return 'AI provider quota is temporarily unavailable.'
  if (error === 'provider_authentication') return 'AI provider authentication failed on the server.'
  if (error === 'worker_interrupted_stale') return 'The AI worker stopped before analysis completed.'
  return 'AI analysis did not complete. Your Shadow Run results are unchanged.'
}

function AutopsyBadge({ item }: { item: AutopsyRecord }) {
  return <span className={`autopsy-status autopsy-${item.status}`}>{isActive(item) && <LoaderCircle size={11} className="animate-spin" />}{item.status.toUpperCase()}</span>
}

function ListSection({ title, values, tone = 'default' }: { title: string; values?: string[] | null; tone?: 'default' | 'hypothesis' | 'warning' }) {
  if (!values?.length) return null
  return <details className={`autopsy-disclosure autopsy-${tone}`} open>
    <summary>{title}<ChevronDown size={14} /></summary>
    <ol>{values.map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}</ol>
  </details>
}

export default function AutopsyPanel({
  run, originalSql, pollIntervalMs = 3500, maxPolls = 40,
}: { run: ShadowRun; originalSql: string; pollIntervalMs?: number; maxPolls?: number }) {
  const queryClient = useQueryClient()
  const [selection, setSelection] = useState<{ runId: number; autopsyId: number } | null>(null)
  const [showDiff, setShowDiff] = useState(false)
  const [copied, setCopied] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const submitting = useRef(false)
  const pollCount = useRef(0)
  const terminalRefresh = useRef<number | null>(null)

  const history = useQuery({
    queryKey: ['autopsies', run.id],
    queryFn: () => listAutopsies(run.id),
    retry: false,
  })
  const ordered = useMemo(() => Array.isArray(history.data)
    ? history.data
      .filter(item => item.shadow_run_id === run.id)
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)
    : [], [history.data, run.id])
  const selectedId = selection?.runId === run.id ? selection.autopsyId : null

  useEffect(() => {
    setSelection(null)
    setShowDiff(false)
    setNotice(null)
    pollCount.current = 0
    terminalRefresh.current = null
  }, [run.id])
  useEffect(() => {
    if (selectedId !== null || !ordered.length) return
    const preferred = ordered.find(item => item.status === 'completed') ?? ordered.find(isActive) ?? ordered[0]
    setSelection({ runId: run.id, autopsyId: preferred.id })
  }, [ordered, run.id, selectedId])

  const report = useQuery({
    queryKey: ['autopsy', run.id, selectedId],
    queryFn: () => getAutopsy(selectedId!),
    enabled: selectedId !== null,
    retry: false,
    refetchInterval: query => {
      if (!isActive(query.state.data) || pollCount.current >= maxPolls) return false
      pollCount.current += 1
      return pollIntervalMs
    },
    refetchIntervalInBackground: false,
  })
  useEffect(() => {
    const item = report.data
    if (!item || item.shadow_run_id !== run.id || isActive(item) || terminalRefresh.current === item.id) return
    terminalRefresh.current = item.id
    queryClient.invalidateQueries({ queryKey: ['autopsies', run.id] })
  }, [queryClient, report.data, run.id])

  const start = useMutation({
    mutationFn: (shadowRunId: number) => startAutopsy(shadowRunId),
    retry: false,
    onSuccess: item => {
      setNotice(null)
      pollCount.current = 0
      terminalRefresh.current = null
      queryClient.setQueryData(['autopsy', item.shadow_run_id, item.id], item)
      setSelection({ runId: item.shadow_run_id, autopsyId: item.id })
      queryClient.invalidateQueries({ queryKey: ['autopsies', item.shadow_run_id] })
    },
    onError: async (error, shadowRunId) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setNotice('An AI analysis is already active. Its latest status has been loaded.')
        await queryClient.invalidateQueries({ queryKey: ['autopsies', shadowRunId] })
      }
    },
    onSettled: () => { submitting.current = false },
  })

  const detail = report.data?.shadow_run_id === run.id ? report.data : undefined
  const item = detail ?? ordered.find(entry => entry.id === selectedId)
  const diagnosis = item?.diagnosis_json
  const category = item?.diagnosis_category ?? diagnosis?.diagnosis_category
  const confidence = item?.confidence ?? diagnosis?.confidence
  const evidence = item?.evidence?.length ? item.evidence : diagnosis?.supporting_evidence ?? []
  const suggestedSql = item?.suggested_sql ?? diagnosis?.suggested_sql ?? null
  const actions = item?.suggested_corrections?.length ? item.suggested_corrections : diagnosis?.suggested_corrective_actions
  const hasActiveOrCompleted = ordered.some(entry => isActive(entry) || entry.status === 'completed')
  const eligibleCandidate = (run.status === 'completed' && run.comparison_result === 'FAIL') || run.status === 'failed'
  const canAnalyze = eligibleCandidate && !hasActiveOrCompleted && !start.isPending
  const pollLimitReached = Boolean(item && isActive(item) && pollCount.current >= maxPolls)

  const analyze = () => {
    if (!canAnalyze || submitting.current) return
    submitting.current = true
    setNotice(null)
    start.mutate(run.id)
  }
  const copySql = async () => {
    if (!suggestedSql) return
    await navigator.clipboard.writeText(suggestedSql)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }

  return <section className="autopsy-panel" aria-label="AI Autopsy">
    <header className="autopsy-heading">
      <div><span><BrainCircuit size={14} /> AI Autopsy</span><h4>Failure diagnosis</h4><p>AI-generated diagnosis is advisory. Suggested corrections are never executed or applied automatically.</p></div>
      {canAnalyze && <button className="btn-primary" onClick={analyze} disabled={start.isPending}>{start.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Search size={14} />} Analyze Failure</button>}
    </header>

    {run.status === 'completed' && run.comparison_result === 'PASS' && <div className="autopsy-neutral"><Check size={15} /> No AI Autopsy required for this matching Shadow Run.</div>}
    {(run.status === 'queued' || run.status === 'running') && <div className="autopsy-neutral"><Clock3 size={15} /> Validation must finish before a failure can be analyzed.</div>}
    {notice && <div className="autopsy-notice" role="status">{notice}</div>}
    {start.isError && !(axios.isAxiosError(start.error) && start.error.response?.status === 409) && <div className="autopsy-error" role="alert"><ShieldAlert size={15} /><div><strong>Could not start AI analysis</strong><p>{getErrorMessage(start.error)} No automatic retry was attempted.</p></div></div>}

    <div className="autopsy-layout">
      <aside className="autopsy-history" aria-label="Autopsy history">
        <div className="shadow-section-title"><span>Autopsy history</span><button aria-label="Refresh Autopsy history" onClick={() => history.refetch()}><RefreshCw size={13} /></button></div>
        {history.isLoading ? <div className="shadow-skeleton" aria-label="Loading Autopsy history"><i /><i /></div>
        : history.isError ? <div className="shadow-inline-error" role="alert">{getErrorMessage(history.error)} <button onClick={() => history.refetch()}>Retry</button></div>
        : !ordered.length ? <div className="autopsy-empty"><BrainCircuit size={19} /><strong>No AI Autopsy history</strong><span>A new analysis always requires an explicit click.</span></div>
        : <div className="autopsy-history-list">{ordered.map(entry => <button key={entry.id} className={selectedId === entry.id ? 'is-selected' : ''} onClick={() => { pollCount.current = 0; setSelection({ runId: run.id, autopsyId: entry.id }); setShowDiff(false) }}><span><strong>Autopsy #{entry.id}</strong><AutopsyBadge item={entry} /></span><small>{humanizeCategory(entry.diagnosis_category)}{entry.confidence !== null ? ` · ${entry.confidence}%` : ''}</small><small>{entry.model_used ?? entry.provider_error ?? 'No model metadata'} · {formatTime(entry.created_at)}</small></button>)}</div>}
      </aside>

      <div className="autopsy-report" aria-live="polite">
        {selectedId === null ? <div className="autopsy-empty"><BrainCircuit size={24} /><strong>{eligibleCandidate ? 'No diagnosis selected' : 'Analysis unavailable'}</strong><span>{eligibleCandidate ? 'Select a historical diagnosis or explicitly start one.' : 'This Shadow Run has no diagnosable failure.'}</span></div>
        : report.isLoading ? <div className="autopsy-empty"><LoaderCircle className="animate-spin" /> Loading AI diagnosis…</div>
        : report.isError ? <div className="autopsy-error" role="alert"><ShieldAlert size={15} /><div><strong>Could not load AI diagnosis</strong><p>{getErrorMessage(report.error)}</p><button className="btn-outline" onClick={() => report.refetch()}>Retry</button></div></div>
        : item ? <>
          <div className="autopsy-overview">
            <div><AutopsyBadge item={item} /><h5>{humanizeCategory(category)}</h5><p>{diagnosis?.summary ?? (item.status === 'failed' ? failureMessage(item.provider_error) : 'The structured diagnosis is not available yet.')}</p></div>
            <dl><div><dt>AI-reported confidence</dt><dd>{confidence === null || confidence === undefined ? '—' : `${confidence}%`}</dd></div><div><dt>Model</dt><dd>{item.model_used ?? '—'}</dd></div><div><dt>Completed</dt><dd>{formatTime(item.completed_at)}</dd></div></dl>
          </div>
          {isActive(item) && <div className="autopsy-progress"><LoaderCircle size={16} className="animate-spin" /><div><strong>{item.status === 'queued' ? 'AI analysis queued' : 'AI analysis in progress'}</strong><p>Polling is read-only and will stop when the backend reports a terminal state.</p></div></div>}
          {pollLimitReached && <div className="autopsy-notice"><span>Automatic polling paused after the bounded wait. The analysis may still be active.</span><button className="btn-outline" onClick={() => { pollCount.current = 0; report.refetch() }}>Refresh status</button></div>}
          {item.status === 'failed' && <div className="autopsy-error" role="alert"><AlertTriangle size={15} /><div><strong>AI analysis failed</strong><p>{failureMessage(item.provider_error)}</p><code>{item.provider_error ?? 'unknown_failure'}</code></div></div>}
          {item.status === 'completed' && diagnosis && <>
            <div className="autopsy-root-cause"><span>Suspected root cause</span><p>{diagnosis.suspected_root_cause || 'Not supplied.'}</p></div>
            <div className="autopsy-tags"><div><span>Affected transformations</span>{diagnosis.affected_transformations?.length ? diagnosis.affected_transformations.map(value => <code key={value}>{value}</code>) : <em>None supplied</em>}</div><div><span>Affected columns</span>{diagnosis.affected_columns?.length ? diagnosis.affected_columns.map(value => <code key={value}>{value}</code>) : <em>None supplied</em>}</div></div>
            <ListSection title="Observed facts" values={diagnosis.observed_facts} />
            <ListSection title="AI hypotheses" values={diagnosis.hypotheses} tone="hypothesis" />
            {evidence.length > 0 && <details className="autopsy-disclosure" open><summary>Supporting evidence <ChevronDown size={14} /></summary><div className="autopsy-evidence">{evidence.map((entry, index) => <div key={`${entry.reference}-${index}`}><span>Reference</span><code>{entry.reference}</code><span>Observation</span><p>{entry.observation}</p></div>)}</div></details>}
            <ListSection title="Confidence reasons" values={diagnosis.confidence_reasons} />
            <ListSection title="Suggested corrective actions" values={actions} />
            <ListSection title="Risks and limitations" values={diagnosis.risks_and_limitations} tone="warning" />
            <ListSection title="Recommended verification steps" values={diagnosis.recommended_verification_steps} />
            {diagnosis.more_evidence_required && <div className="autopsy-notice"><AlertTriangle size={14} /> More evidence is required before relying on this hypothesis.</div>}
            {suggestedSql && <section className="autopsy-sql" aria-label="AI Suggested SQL"><header><div><strong>AI Suggested SQL</strong><span className={item.suggested_sql_verified ? 'is-verified' : 'is-unverified'}>{item.suggested_sql_verified ? 'Verified' : 'Unverified'}</span></div><div><button onClick={copySql}>{copied ? <Check size={13} /> : <Clipboard size={13} />}{copied ? 'Copied' : 'Copy'}</button><button aria-pressed={showDiff} onClick={() => setShowDiff(value => !value)}><GitCompareArrows size={13} />{showDiff ? 'SQL only' : 'Compare'}</button></div></header><p>Review manually. Create a separate reviewed conversion version and Shadow Run before trusting this suggestion.</p><div className="autopsy-sql-editor">{showDiff ? <SqlDiff original={originalSql} modified={suggestedSql} /> : <SqlEditor value={suggestedSql} readOnly />}</div></section>}
          </>}
          {item.status === 'completed' && !diagnosis && <div className="autopsy-notice">This historical record completed without diagnosis details.</div>}
        </> : null}
      </div>
    </div>
  </section>
}
