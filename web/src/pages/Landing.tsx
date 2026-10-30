import { ArrowRight, ArrowUpRight, BrainCircuit, CheckCircle2, ChevronRight, Database, GitBranchPlus, Layers3, ScanSearch, ShieldCheck, Sparkles, TerminalSquare, Workflow, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import Logo from '../components/Logo'
import { useAuth } from '../lib/auth'

const features = [
  { icon: Workflow, name: 'Visual lineage', description: 'Understand every transformation from source columns to target tables.', phase: 'Planned' },
  { icon: BrainCircuit, name: 'AI-powered conversion', description: 'Turn complex PowerCenter mappings into readable, reviewable dbt SQL.', phase: 'Planned' },
  { icon: ScanSearch, name: 'AI Autopsy', description: 'Find the exact cause of broken runs and mismatched columns.', phase: 'Planned' },
  { icon: ShieldCheck, name: 'Data verification', description: 'Back every migration with real row counts, checksums and diffs.', phase: 'Planned' },
]

export default function Landing() {
  const { token } = useAuth()
  return <div className="min-h-screen overflow-hidden bg-night-950">
    <div className="pointer-events-none absolute inset-x-0 top-0 h-[760px] subtle-grid [mask-image:linear-gradient(to_bottom,black,transparent)]" />
    <div className="orb left-[20%] top-[60px] h-[330px] w-[330px] bg-violet-600" />
    <div className="orb right-[5%] top-[140px] h-[350px] w-[350px] bg-cyan-600" />
    <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-7 lg:px-10">
      <Logo />
      <nav className="hidden items-center gap-9 text-sm font-semibold text-slate-400 md:flex"><a href="#platform" className="hover:text-white">Platform</a><a href="#features" className="hover:text-white">Features</a><a href="#technology" className="hover:text-white">Technology</a></nav>
      <Link to={token ? '/app' : '/login'} className="btn-outline text-sm">{token ? 'Open Workspace' : 'Sign in'} <ArrowUpRight size={15} /></Link>
    </header>

    <main className="relative z-10 mx-auto max-w-7xl px-6 pb-32 pt-16 lg:px-10 lg:pt-24">
      <div className="mx-auto max-w-[820px] text-center">
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .5 }}>
          <span className="badge border-violet-400/30 bg-violet-500/10 text-violet-200"><Sparkles size={13} /> Introducing MigraPilot · Phase 1 foundation</span>
          <h1 className="mt-7 text-5xl font-extrabold leading-[1.14] tracking-[-.055em] sm:text-6xl lg:text-[78px]">Legacy ETL deserves a <span className="gradient-text">smarter future.</span></h1>
          <p className="mx-auto mt-7 max-w-[650px] text-base leading-8 text-slate-400 sm:text-lg">The AI-powered migration copilot we're building to convert legacy pipelines, verify every result, and explain exactly what breaks.</p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4"><Link className="btn-primary" to={token ? '/app' : '/register'}>Start your workspace <ArrowRight size={18} /></Link><a className="btn-outline" href="#platform">Explore the vision <ChevronRight size={18} /></a></div>
        </motion.div>
      </div>

      <motion.section id="platform" initial={{ opacity: 0, y: 22 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="relative mx-auto mt-24 max-w-[1040px] overflow-hidden rounded-[26px] border border-slate-600/30 bg-[#0e1426] p-4 shadow-[0_30px_110px_rgba(0,0,0,.55)] sm:p-6">
        <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-violet-400/80 to-transparent" />
        <div className="flex flex-col justify-between gap-4 border-b border-slate-700/50 pb-5 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300"><Layers3 size={18} /></span><div><h2 className="text-sm font-bold">Migration pipeline overview</h2><p className="mt-1 text-xs text-slate-500">Product vision · illustrative preview</p></div></div>
          <span className="badge w-fit"><span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> Features under development</span>
        </div>
        <div className="grid gap-3 py-7 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] md:items-center">
          {[
            { icon: Database, title: 'PowerCenter', sub: 'Legacy XML', number: '01' },
            { icon: BrainCircuit, title: 'AI Converter', sub: 'dbt + SQL', number: '02' },
            { icon: GitBranchPlus, title: 'Shadow Run', sub: 'Compare outputs', number: '03' },
            { icon: CheckCircle2, title: 'Verified', sub: 'Ready to ship', number: '04' },
          ].map((step, i) => <div className="contents" key={step.number}>
            {i !== 0 && <div className="hidden text-violet-400 md:block"><ArrowRight size={18} /></div>}
            <div className="flex items-center gap-3 rounded-2xl border border-slate-700/60 bg-[#161d34] p-4 md:min-h-[145px] md:flex-col md:items-start md:justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/25 to-cyan-500/15 text-cyan-200"><step.icon size={20} /></span><div><h3 className="text-sm font-bold text-white">{step.title}</h3><p className="mt-1 text-xs text-slate-400">{step.sub}</p></div></div>
          </div>)}
        </div>
        <div className="flex flex-wrap gap-3 border-t border-slate-700/50 pt-4 text-xs text-slate-500"><span>Designed for engineering teams</span><span>•</span><span>Traceable code generation</span><span>•</span><span>Evidence-backed comparisons</span></div>
      </motion.section>

      <section id="features" className="pt-28"><div className="max-w-xl"><p className="text-xs font-extrabold uppercase tracking-[.25em] text-azure">The roadmap</p><h2 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">One workspace. Every migration step.</h2><p className="mt-4 text-slate-400">We're building the complete ETL migration loop, not just a SQL generator.</p></div>
        <div className="mt-9 grid gap-4 md:grid-cols-2">{features.map(f => <div key={f.name} className="panel p-7"><span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-400/10 text-violet-300"><f.icon size={23} /></span><div className="mt-6 flex items-center justify-between"><h3 className="text-lg font-extrabold">{f.name}</h3><span className="text-xs text-slate-500">{f.phase}</span></div><p className="mt-3 max-w-md text-sm leading-7 text-slate-400">{f.description}</p></div>)}</div>
      </section>
      <section id="technology" className="mt-24 flex flex-col items-start justify-between gap-6 rounded-[28px] border border-violet-400/20 bg-gradient-to-r from-violet-500/10 to-cyan-500/5 p-8 sm:flex-row sm:items-center sm:p-11"><div><span className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[.2em] text-azure"><TerminalSquare size={17} /> Developer-first architecture</span><h2 className="mt-3 text-2xl font-extrabold">PostgreSQL. FastAPI. React. AI.</h2><p className="mt-3 max-w-lg text-sm leading-7 text-slate-400">Real SQL storage, typed APIs and a provider-agnostic AI layer built for ETL modernization.</p></div><Link to={token ? '/app' : '/register'} className="btn-primary shrink-0">Open your workspace <Zap size={16} /></Link></section>
    </main>
    <footer className="border-t border-slate-800 py-8 text-center text-xs text-slate-500">© {new Date().getFullYear()} MigraPilot · Convert it. Prove it. Fix it.</footer>
  </div>
}
