import { useState } from 'react'
import { Activity, ArrowLeft, ChevronDown, FolderKanban, Github, LayoutDashboard, LogOut, Menu, Plus, Settings2, Sparkles, X } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import Logo from './Logo'
import CreateProjectModal from './CreateProjectModal'

export default function Shell() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const projectMatch = location.pathname.match(/^\/app\/projects\/(\d+)(?:\/mappings\/(\d+))?/)
  const lineageActive = Boolean(projectMatch)
  const lineageHref = lineageActive ? location.pathname : '/app/projects'
  const breadcrumbs = location.pathname === '/app'
    ? [{ label: 'Overview', href: '/app' }]
    : location.pathname === '/app/projects'
      ? [{ label: 'Projects', href: '/app/projects' }]
      : projectMatch
        ? [{ label: 'Projects', href: '/app/projects' }, { label: `Project ${projectMatch[1]}`, href: `/app/projects/${projectMatch[1]}` }, ...(projectMatch[2] ? [{ label: `Mapping ${projectMatch[2]}`, href: location.pathname }] : [])]
        : [{ label: 'Workspace', href: '/app' }]
  const navItem = ({ isActive }: { isActive: boolean }) => `flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-semibold transition ${isActive ? 'bg-violet-400/10 text-violet-200' : 'text-slate-400 hover:bg-[#1b2135] hover:text-slate-100'}`
  return <div className="min-h-screen bg-night-950">
    <div className="flex min-h-screen">
      <aside className={`${menuOpen ? 'fixed inset-y-0 left-0 z-40 flex' : 'hidden'} w-[260px] shrink-0 flex-col border-r border-slate-800/80 bg-[#0d1221] px-4 py-6 lg:sticky lg:top-0 lg:flex lg:h-screen`}>
        <div className="flex items-center justify-between px-3"><Logo /><button aria-label="Close navigation" className="text-slate-400 lg:hidden" onClick={() => setMenuOpen(false)}><X size={21} /></button></div>
        <div className="mt-10 px-3 text-[10px] font-extrabold uppercase tracking-[.25em] text-slate-600">Workspace</div>
        <nav className="mt-4 space-y-1">
          <NavLink end to="/app" onClick={() => setMenuOpen(false)} className={navItem}><LayoutDashboard size={18} /> Overview</NavLink>
          <NavLink end to="/app/projects" onClick={() => setMenuOpen(false)} className={navItem}><FolderKanban size={18} /> My Projects</NavLink>
          <Link to={lineageHref} onClick={() => setMenuOpen(false)} className={`flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-semibold transition ${lineageActive ? 'bg-violet-400/10 text-violet-200' : 'text-slate-400 hover:bg-[#1b2135] hover:text-slate-100'}`}><Activity size={18} /> ETL Lineage</Link>
        </nav>
        <div className="mt-10 px-3 text-[10px] font-extrabold uppercase tracking-[.25em] text-slate-600">Coming next</div>
        <div className="mt-4 space-y-1 text-sm">
          <div className="flex items-center gap-3 px-3.5 py-3 text-slate-600"><Sparkles size={18} /> AI Autopsy</div>
          <div className="flex items-center gap-3 px-3.5 py-3 text-slate-600"><Settings2 size={18} /> Connections</div>
        </div>
        <div className="mt-auto space-y-4 px-2">
          <div className="rounded-2xl border border-violet-400/15 bg-gradient-to-br from-violet-500/15 to-cyan-500/5 p-4"><div className="flex items-center gap-2 text-xs font-extrabold text-violet-300"><Sparkles size={14} /> Phase 3 active</div><p className="mt-2 text-xs leading-5 text-slate-400">PowerCenter parsing and interactive lineage are ready.</p></div>
          <Link to="/" className="flex items-center gap-2 px-2 text-xs text-slate-500 hover:text-white"><ArrowLeft size={14} /> Back to website</Link>
        </div>
      </aside>
      {menuOpen && <button aria-label="Close menu overlay" className="fixed inset-0 z-30 bg-black/70 lg:hidden" onClick={() => setMenuOpen(false)} />}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex min-h-[78px] items-center justify-between gap-4 border-b border-slate-800/70 bg-[#0c1120]/90 px-5 backdrop-blur-xl sm:px-8 lg:px-10">
          <div className="flex min-w-0 items-center gap-4"><button aria-label="Open navigation" className="text-slate-300 lg:hidden" onClick={() => setMenuOpen(true)}><Menu /></button><nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 overflow-hidden text-sm font-semibold"><Link to="/app" className="hidden text-slate-500 hover:text-slate-200 sm:inline">Migration workspace</Link>{breadcrumbs.map((crumb, index) => <span key={crumb.href} className="flex min-w-0 items-center gap-2"><span className="text-slate-700">/</span><Link to={crumb.href} aria-current={index === breadcrumbs.length - 1 ? 'page' : undefined} className={`truncate ${index === breadcrumbs.length - 1 ? 'text-slate-200' : 'text-slate-500 hover:text-slate-200'}`}>{crumb.label}</Link></span>)}</nav></div>
          <div className="flex items-center gap-3"><button className="btn-primary hidden text-xs sm:flex" onClick={() => setCreateOpen(true)}><Plus size={15} /> New project</button><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/20 text-sm font-extrabold text-violet-200">{user?.email?.[0]?.toUpperCase() || '?'}</div><span className="hidden max-w-[160px] truncate text-xs font-semibold text-slate-300 xl:inline">{user?.email}</span><ChevronDown size={14} className="hidden text-slate-500 xl:inline" /><button onClick={() => { logout(); navigate('/login') }} className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-800 hover:text-white" title="Sign out" aria-label="Sign out"><LogOut size={17} /></button></div>
        </header>
        <main className="mx-auto max-w-[1500px] px-5 py-9 sm:px-8 lg:px-10"><Outlet context={{ openCreateProject: () => setCreateOpen(true) }} /></main>
        <footer className="mx-auto flex max-w-[1500px] flex-wrap justify-between gap-3 px-5 pb-8 text-xs text-slate-600 sm:px-8 lg:px-10"><span>MigraPilot · PostgreSQL + FastAPI</span><span className="flex items-center gap-2"><Github size={13} /> Phase 3 lineage</span></footer>
      </div>
    </div>
    {createOpen && <CreateProjectModal onClose={() => setCreateOpen(false)} />}
  </div>
}
