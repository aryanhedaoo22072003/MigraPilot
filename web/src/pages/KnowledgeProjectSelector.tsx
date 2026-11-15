import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, DatabaseZap, FolderKanban, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage, type Project } from '../lib/api'

export default function KnowledgeProjectSelector() {
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: async () => (await api.get<Project[]>('/projects')).data,
    retry: false,
  })

  return <div className="mx-auto max-w-5xl">
    <header>
      <span className="badge"><BookOpen size={14} /> Failure Knowledge Base</span>
      <h1 className="mt-5 text-3xl font-extrabold tracking-tight sm:text-4xl">Choose a project</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Knowledge records are isolated by project. Select one of your authorized projects to review its verified failure knowledge.</p>
    </header>

    {projects.isLoading && <div className="panel mt-8 flex min-h-48 items-center justify-center gap-3 text-sm text-slate-400"><LoaderCircle className="animate-spin text-violet-300" /> Loading your projects…</div>}
    {projects.isError && <div className="panel mt-8 p-6 text-sm text-rose-200" role="alert"><p>{getErrorMessage(projects.error)}</p><button className="btn-outline mt-4" onClick={() => projects.refetch()}>Try again</button></div>}
    {!projects.isLoading && !projects.isError && !projects.data?.length && <div className="panel mt-8 px-6 py-12 text-center"><FolderKanban className="mx-auto text-slate-500" size={32} /><h2 className="mt-5 text-lg font-extrabold">No projects available</h2><p className="mt-2 text-sm text-slate-500">Create a project before opening a project Knowledge Base.</p><Link className="btn-outline mt-6" to="/app/projects">Go to My Projects</Link></div>}
    {projects.data && projects.data.length > 0 && <section className="mt-8 grid gap-4 md:grid-cols-2" aria-label="Choose a project Knowledge Base">
      {projects.data.map(project => <article key={project.id} className="panel flex min-w-0 flex-col p-5">
        <div className="flex min-w-0 items-start gap-4"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-400/15 text-violet-200"><DatabaseZap size={20} /></span><div className="min-w-0"><h2 className="truncate text-base font-extrabold">{project.name}</h2><p className="mt-1 text-xs text-slate-500">{project.source_system} → {project.target_system}</p></div></div>
        <Link className="btn-outline mt-5 w-full justify-center" to={`/app/projects/${project.id}/knowledge`}>Open Knowledge Base <ArrowRight size={15} /></Link>
      </article>)}
    </section>}
  </div>
}
