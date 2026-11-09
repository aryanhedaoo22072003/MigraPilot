import { useOutletContext, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, CheckCircle2, Clock3, Code2, DatabaseZap, FolderKanban, Plus, Rocket, Sparkles } from 'lucide-react'
import { api, getErrorMessage, type Project } from '../lib/api'
import { useAuth } from '../lib/auth'

type ShellContext = { openCreateProject: () => void }

export default function Dashboard() {
  const { openCreateProject } = useOutletContext<ShellContext>()
  const { user } = useAuth()
  const { data: projects = [], isLoading, isError, error, refetch } = useQuery({ queryKey: ['projects'], queryFn: async () => (await api.get<Project[]>('/projects')).data })
  const total = projects.length
  const name = user?.email?.split('@')[0] || 'Engineer'
  return <div>
    <div className="flex flex-wrap items-start justify-between gap-5"><div><span className="badge mb-4"><span className="h-1.5 w-1.5 rounded-full bg-green-400" /> Workspace active</span><h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">Good to see you, <span className="gradient-text">{name}.</span></h1><p className="mt-3 text-sm text-slate-400">Manage your ETL migration projects from a single intelligent workspace.</p></div><button onClick={openCreateProject} className="btn-primary sm:hidden"><Plus size={16} /> New project</button></div>
    <div className="mt-8 grid gap-4 md:grid-cols-3">
      {[
        { title: 'Migration projects', value: isLoading ? '—' : String(total), icon: FolderKanban, detail: 'Your active workspaces', tone: 'text-violet-300 bg-violet-400/10' },
        { title: 'Mappings converted', value: '—', icon: Code2, detail: 'Open a project to review versions', tone: 'text-cyan-300 bg-cyan-400/10' },
        { title: 'Pipelines verified', value: '—', icon: CheckCircle2, detail: 'Available after shadow runs', tone: 'text-emerald-300 bg-emerald-400/10' },
      ].map(item => <div key={item.title} className="panel min-h-[180px] p-6"><div className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-400">{item.title}</span><span className={`rounded-xl p-2.5 ${item.tone}`}><item.icon size={19} /></span></div><div className="mt-5 text-4xl font-extrabold">{item.value}</div><div className="mt-2 text-xs text-slate-500">{item.detail}</div></div>)}
    </div>
    <div className="mt-9 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
      <section className="panel min-w-0 p-6 sm:p-8"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-extrabold">Your migration projects</h2><p className="mt-2 text-xs text-slate-500">Projects are stored in PostgreSQL and accessible only to your account.</p></div>{total > 0 && <button className="btn-outline text-xs" onClick={openCreateProject}><Plus size={15} /> Add project</button>}</div>
        {isError && <div className="mt-6 rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-200"><p>{getErrorMessage(error)}</p><button className="mt-2 underline" onClick={() => refetch()}>Try again</button></div>}
        {isLoading && <div className="mt-8 h-40 animate-pulse rounded-2xl bg-slate-800/40" />}
        {!isLoading && !isError && projects.length === 0 && <div className="mt-8 rounded-2xl border border-dashed border-slate-700/90 bg-[#11182a] px-6 py-12 text-center"><span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-300"><Rocket size={29} /></span><h3 className="mt-6 text-lg font-extrabold">Your first migration starts here</h3><p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-slate-400">Create a workspace for your PowerCenter or ODI modernization initiative.</p><button className="btn-primary mt-7" onClick={openCreateProject}><Plus size={17} /> Create first project</button></div>}
        {!isLoading && !isError && projects.length > 0 && <div className="mt-7 space-y-3">{projects.map(project => <Link key={project.id} to={`/app/projects/${project.id}`} className="group flex items-center justify-between gap-3 rounded-2xl border border-slate-700/70 bg-[#121829] p-4 transition hover:border-violet-500/40 hover:bg-[#19203a]"><div className="flex min-w-0 items-center gap-4"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-400/15 text-violet-200"><DatabaseZap size={20} /></span><div className="min-w-0"><h3 className="truncate text-sm font-extrabold">{project.name}</h3><p className="mt-1 text-xs text-slate-500">{project.source_system} → {project.target_system}</p></div></div><ArrowRight className="shrink-0 text-slate-500 group-hover:text-violet-300" size={17} /></Link>)}</div>}
      </section>
      <section className="panel p-6 sm:p-8"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300"><Sparkles size={20} /></span><div><h2 className="text-lg font-extrabold">Product build progress</h2><p className="mt-1 text-xs text-slate-500">Current development milestones</p></div></div>
        <div className="mt-8 space-y-7">{[
          { title: 'SQL database & API', caption: 'PostgreSQL, FastAPI, authentication', done: true, icon: CheckCircle2 },
          { title: 'Project workspace', caption: 'Create, list and manage projects', done: true, icon: CheckCircle2 },
          { title: 'PowerCenter XML parser', caption: 'Parse mappings and transformation logic', done: true, icon: CheckCircle2 },
          { title: 'AI conversion workspace', caption: 'Generate, edit and compare dbt SQL versions', done: true, icon: CheckCircle2 },
          { title: 'Shadow validation', caption: 'Run and inspect isolated comparison reports', done: true, icon: CheckCircle2 },
          { title: 'AI Autopsy', caption: 'Diagnose shadow-run failures', done: false, icon: Clock3 },
        ].map((item, index, items) => <div key={item.title} className="relative flex gap-4">{index < items.length - 1 && <span className="absolute left-[13px] top-8 h-[44px] w-px bg-slate-700" />}<span className={`z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${item.done ? 'bg-emerald-400/10 text-emerald-300' : 'bg-slate-700/40 text-slate-500'}`}><item.icon size={16} /></span><div><h3 className="text-sm font-extrabold text-slate-200">{item.title}</h3><p className="mt-2 text-xs leading-5 text-slate-500">{item.caption}</p></div></div>)}</div>
        <div className="mt-8 flex items-center gap-2 rounded-xl border border-cyan-400/15 bg-cyan-500/5 px-4 py-3 text-xs text-cyan-200"><Activity size={16} /> Only working features are shown as complete.</div>
      </section>
    </div>
  </div>
}
