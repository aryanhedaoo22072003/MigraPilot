import { GitMerge } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function Logo({ compact = false }: { compact?: boolean }) {
  return <Link to="/" className="inline-flex items-center gap-3 font-extrabold tracking-tight text-white">
    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-cyan-400 shadow-lg shadow-violet-500/20"><GitMerge size={21} strokeWidth={2.5} /></span>
    {!compact && <span className="text-xl">Migra<span className="text-azure">Pilot</span></span>}
  </Link>
}
