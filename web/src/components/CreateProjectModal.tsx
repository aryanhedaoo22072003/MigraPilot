import { useState } from 'react'
import { ArrowRight, FolderPlus, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage, type NewProject, type Project } from '../lib/api'

export default function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<NewProject>({ name: '', source_system: 'powercenter', target_system: 'dbt_postgres' })
  const mutation = useMutation({
    mutationFn: async (data: NewProject) => (await api.post<Project>('/projects', data)).data,
    onSuccess: project => { queryClient.invalidateQueries({ queryKey: ['projects'] }); onClose(); navigate(`/app/projects/${project.id}`) },
  })
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4 py-6" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <div role="dialog" aria-modal="true" aria-label="Create migration project" className="w-full max-w-[530px] rounded-[24px] border border-slate-700 bg-[#151a2c] p-7 shadow-2xl">
      <div className="flex items-start justify-between"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-400/15 text-violet-300"><FolderPlus size={21} /></span><button aria-label="Close" className="text-slate-500 hover:text-white" onClick={onClose}><X size={20} /></button></div>
      <h2 className="mt-5 text-2xl font-extrabold">Create migration project</h2><p className="mt-2 text-sm leading-6 text-slate-400">Organize your legacy-to-modern migration inside one secure workspace.</p>
      <form className="mt-7 space-y-5" onSubmit={e => { e.preventDefault(); mutation.mutate(form) }}>
        <label className="block text-sm font-semibold text-slate-300">Project name<input className="input mt-2" required minLength={2} maxLength={200} placeholder="e.g. Finance PowerCenter Modernization" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
        <label className="block text-sm font-semibold text-slate-300">Source system<select className="input mt-2" value={form.source_system} onChange={e => setForm({ ...form, source_system: e.target.value })}><option value="powercenter">Informatica PowerCenter</option><option value="odi">Oracle Data Integrator (future parser)</option></select></label>
        <label className="block text-sm font-semibold text-slate-300">Target system<select className="input mt-2" value={form.target_system} onChange={e => setForm({ ...form, target_system: e.target.value })}><option value="dbt_postgres">dbt + PostgreSQL</option><option value="dbt_snowflake">dbt + Snowflake (future support)</option><option value="dbt_bigquery">dbt + BigQuery (future support)</option></select></label>
        {mutation.isError && <p role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">{getErrorMessage(mutation.error)}</p>}
        <div className="flex justify-end gap-3 pt-2"><button type="button" className="btn-outline" onClick={onClose}>Cancel</button><button type="submit" className="btn-primary" disabled={mutation.isPending || !form.name.trim()}>{mutation.isPending ? 'Creating…' : 'Create project'} <ArrowRight size={16} /></button></div>
      </form>
    </div>
  </div>
}
