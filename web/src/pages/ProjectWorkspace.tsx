import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, CheckCircle2, Code2, Database, FileJson2, Info, Plus, ShieldAlert, Trash2, Workflow } from 'lucide-react'
import { api, getErrorMessage, type Dashboard } from '../lib/api'

function Metric({ title, value, detail, icon: Icon }: { title: string; value: string; detail: string; icon: typeof Database }) {
  return <div className="panel p-6"><div className="flex items-center justify-between text-sm font-semibold text-slate-400"><span>{title}</span><Icon size={19} className="text-violet-300" /></div><div className="mt-5 text-4xl font-extrabold">{value}</div><div className="mt-2 text-xs text-slate-500">{detail}</div></div>
}

export default function ProjectWorkspace() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['dashboard', id], queryFn: async () => (await api.get<Dashboard>(`/projects/${id}/dashboard`)).data, enabled: Boolean(id) })
  const remove = useMutation({ mutationFn: async () => api.delete(`/projects/${id}`), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['projects'] }); navigate('/app') } })
  if (isLoading) return <div className="panel h-56 animate-pulse" />
  if (isError || !data) return <div className="panel p-8"><p role="alert" className="text-rose-300">{getErrorMessage(error)}</p><Link to="/app" className="btn-outline mt-6">Back to dashboard</Link></div>
  return <div>
    <Link to="/app" className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-white"><ArrowLeft size={14} /> All projects</Link>
    <div className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><span className="badge"><span className="h-2 w-2 rounded-full bg-cyan-400" /> Project workspace</span><h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">{data.project.name}</h1><p className="mt-3 text-sm text-slate-400">{data.project.source_system} <ArrowRight className="mx-2 inline" size={14} /> {data.project.target_system}</p></div><button onClick={() => setConfirm(v => !v)} className="btn-outline border-rose-700/30 text-xs text-rose-200"><Trash2 size={14} /> Delete project</button></div>
    {confirm && <div className="mt-5 flex flex-wrap items-center gap-4 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm"><span>Delete this project and all related data permanently?</span><button className="rounded-lg bg-rose-600 px-3 py-2 font-bold text-white" disabled={remove.isPending} onClick={() => remove.mutate()}>Yes, delete</button><button onClick={() => setConfirm(false)}>Cancel</button>{remove.isError && <p className="text-rose-300">{getErrorMessage(remove.error)}</p>}</div>}
    <div className="mt-8 grid gap-4 md:grid-cols-4"><Metric title="Total mappings" value={String(data.total_mappings)} detail="Stored in PostgreSQL" icon={FileJson2} /><Metric title="Converted" value={`${data.converted_percent}%`} detail="Based on mapping status" icon={Code2} /><Metric title="Verified" value={`${data.verified_percent}%`} detail="Passes validation checks" icon={CheckCircle2} /><Metric title="Failing" value={String(data.failing)} detail="Needs investigation" icon={ShieldAlert} /></div>
    <div className="mt-7 grid gap-5 lg:grid-cols-[1.25fr_1fr]"><section className="panel p-7"><div className="flex items-start gap-3"><span className="rounded-xl bg-violet-500/10 p-3 text-violet-300"><Workflow size={22} /></span><div><h2 className="text-lg font-extrabold">Migration pipeline</h2><p className="mt-2 text-sm text-slate-400">The PowerCenter parser and visual lineage canvas are the next build phase.</p></div></div><div className="mt-7 flex flex-wrap items-center justify-center gap-3 rounded-xl border border-dashed border-slate-700 bg-[#101728] px-4 py-12"><span className="badge">Legacy XML</span><ArrowRight size={17} className="text-slate-600" /><span className="badge">AI SQL</span><ArrowRight size={17} className="text-slate-600" /><span className="badge">Validation</span></div><div className="mt-5 flex items-center gap-2 text-xs text-slate-500"><Info size={14} /> Illustration only — conversion and verification are not enabled yet.</div></section>
      <section className="panel p-7"><h2 className="text-lg font-extrabold">Next: upload & parse</h2><p className="mt-3 text-sm leading-7 text-slate-400">Once the parser is implemented, this workspace will accept Informatica XML, extract transformations, and display source-to-target lineage.</p><div className="mt-8 flex items-center gap-2 rounded-xl border border-violet-400/15 bg-violet-500/10 p-4 text-sm text-violet-200"><Plus size={18} /> XML upload endpoint coming in Phase 2</div></section>
    </div>
  </div>
}
