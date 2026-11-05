import axios from 'axios'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Code2, Database, FileJson2, GitBranch, RefreshCw, ShieldAlert, Trash2 } from 'lucide-react'
import LineageGraph from '../features/lineage/LineageGraph'
import { api, getErrorMessage, type Dashboard, type MappingDetail, type MappingSummary } from '../lib/api'

function Metric({ title, value, detail, icon: Icon }: { title: string; value: string; detail: string; icon: typeof Database }) {
  return <div className="panel p-5"><div className="flex items-center justify-between text-xs font-semibold text-slate-400"><span>{title}</span><Icon size={17} className="text-violet-300" /></div><div className="mt-4 text-3xl font-extrabold">{value}</div><div className="mt-1 text-[11px] text-slate-500">{detail}</div></div>
}

function LoadingGraph() {
  return <div className="lineage-loading" aria-label="Loading lineage"><div className="h-20 w-56 animate-pulse rounded-2xl bg-slate-800" /><div className="h-px w-20 bg-slate-700" /><div className="h-32 w-64 animate-pulse rounded-2xl bg-slate-800" /><div className="h-px w-20 bg-slate-700" /><div className="h-20 w-56 animate-pulse rounded-2xl bg-slate-800" /></div>
}

export default function ProjectWorkspace() {
  const { id, mappingId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const dashboard = useQuery({ queryKey: ['dashboard', id], queryFn: async () => (await api.get<Dashboard>(`/projects/${id}/dashboard`)).data, enabled: Boolean(id), retry: false })
  const mappings = useQuery({ queryKey: ['mappings', id], queryFn: async () => (await api.get<MappingSummary[]>(`/projects/${id}/mappings`)).data, enabled: Boolean(id), retry: false })
  const selectedId = mappingId ? Number(mappingId) : mappings.data?.[0]?.id
  const mapping = useQuery({ queryKey: ['mapping', selectedId], queryFn: async () => (await api.get<MappingDetail>(`/mappings/${selectedId}`)).data, enabled: Boolean(selectedId), retry: false })
  useEffect(() => {
    if (!mappingId && mappings.data?.[0] && id) navigate(`/app/projects/${id}/mappings/${mappings.data[0].id}`, { replace: true })
  }, [id, mappingId, mappings.data, navigate])
  const remove = useMutation({ mutationFn: async () => api.delete(`/projects/${id}`), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['projects'] }); navigate('/app') } })
  const topError = dashboard.error || mappings.error
  if (dashboard.isLoading || mappings.isLoading) return <div className="space-y-5"><div className="h-32 animate-pulse rounded-3xl bg-slate-900" /><div className="h-[560px] animate-pulse rounded-3xl bg-slate-900" /></div>
  if (topError || !dashboard.data) {
    const unauthorized = axios.isAxiosError(topError) && topError.response?.status === 401
    return <div className="panel mx-auto max-w-2xl p-9 text-center"><AlertTriangle className="mx-auto text-rose-300" /><h1 className="mt-4 text-xl font-extrabold">{unauthorized ? 'Your session has expired' : 'Project unavailable'}</h1><p role="alert" className="mt-3 text-sm text-slate-400">{getErrorMessage(topError)}</p><Link to={unauthorized ? '/login' : '/app'} className="btn-outline mt-6">{unauthorized ? 'Sign in again' : 'Back to dashboard'}</Link></div>
  }
  const data = dashboard.data
  return <div>
    <nav aria-label="Project breadcrumb" className="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500"><Link to="/app/projects" className="inline-flex items-center gap-2 hover:text-white"><ArrowLeft size={14} /> Projects</Link><span className="text-slate-700">/</span><Link to={`/app/projects/${id}`} className="hover:text-white">{data.project.name}</Link>{mapping.data && <><span className="text-slate-700">/</span><span aria-current="page" className="text-slate-300">{mapping.data.name}</span></>}</nav>
    <div className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><span className="badge"><span className="h-2 w-2 rounded-full bg-cyan-400" /> Interactive lineage</span><h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">{data.project.name}</h1><p className="mt-3 text-sm text-slate-400">{data.project.source_system} <ArrowRight className="mx-2 inline" size={14} /> {data.project.target_system}</p></div><button onClick={() => setConfirm(value => !value)} className="btn-outline border-rose-700/30 text-xs text-rose-200"><Trash2 size={14} /> Delete project</button></div>
    {confirm && <div className="mt-5 flex flex-wrap items-center gap-4 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm"><span>Delete this project and all related data permanently?</span><button className="rounded-lg bg-rose-600 px-3 py-2 font-bold text-white" disabled={remove.isPending} onClick={() => remove.mutate()}>Yes, delete</button><button onClick={() => setConfirm(false)}>Cancel</button>{remove.isError && <p className="text-rose-300">{getErrorMessage(remove.error)}</p>}</div>}
    <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric title="Total mappings" value={String(data.total_mappings)} detail="Parsed from PowerCenter" icon={FileJson2} /><Metric title="Parsed" value={String(data.parsed)} detail="Ready for lineage review" icon={GitBranch} /><Metric title="Converted" value={`${data.converted_percent}%`} detail="AI conversion not enabled" icon={Code2} /><Metric title="Verified" value={`${data.verified_percent}%`} detail="Validation phase pending" icon={CheckCircle2} /></div>
    <section className="mt-6 panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 px-5 py-4"><div><h2 className="text-base font-extrabold">ETL lineage canvas</h2><p className="mt-1 text-xs text-slate-500">Select a port to trace its upstream column dependencies.</p></div>{mappings.data?.length ? <label className="flex items-center gap-3 text-xs font-bold text-slate-400"><span className="hidden sm:inline">Mapping</span><select aria-label="Select mapping" className="input min-w-[250px] py-2 text-xs" value={selectedId || ''} onChange={event => navigate(`/app/projects/${id}/mappings/${event.target.value}`)}>{mappings.data.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}</div>
      {!mappings.data?.length ? <div className="flex min-h-[460px] flex-col items-center justify-center p-8 text-center"><span className="rounded-2xl bg-violet-500/10 p-4 text-violet-300"><GitBranch size={28} /></span><h3 className="mt-5 text-lg font-extrabold">No parsed mappings yet</h3><p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Upload a valid PowerCenter XML or ZIP through the Phase 2 API. Parsed mappings will appear here automatically.</p><button className="btn-outline mt-6" onClick={() => mappings.refetch()}><RefreshCw size={14} /> Check again</button></div>
      : mapping.isLoading ? <LoadingGraph />
      : mapping.isError || !mapping.data ? <div className="flex min-h-[460px] flex-col items-center justify-center p-8 text-center"><ShieldAlert size={28} className="text-rose-300" /><h3 className="mt-4 text-lg font-extrabold">Could not load lineage</h3><p role="alert" className="mt-2 text-sm text-slate-400">{getErrorMessage(mapping.error)}</p><button className="btn-outline mt-6" onClick={() => mapping.refetch()}><RefreshCw size={14} /> Retry</button></div>
      : <LineageGraph mapping={mapping.data} />}
    </section>
  </div>
}
