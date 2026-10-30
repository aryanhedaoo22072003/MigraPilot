import { useState } from 'react'
import { ArrowRight, LockKeyhole, Mail, ShieldCheck, Sparkles } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import { api, getErrorMessage, type TokenResponse } from '../lib/api'
import { useAuth } from '../lib/auth'

export default function Auth({ mode }: { mode: 'login' | 'register' }) {
  const { token, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  if (token) return <Navigate to="/app" replace />
  const register = mode === 'register'
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(''); setSubmitting(true)
    try {
      const { data } = await api.post<TokenResponse>(`/auth/${register ? 'register' : 'login'}`, { email, password })
      login(data); navigate('/app', { replace: true })
    } catch (err) { setError(getErrorMessage(err)) }
    finally { setSubmitting(false) }
  }
  return <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-night-950 px-5 py-16 subtle-grid">
    <div className="orb -left-20 top-28 h-96 w-96 bg-violet-600" /><div className="orb bottom-0 right-0 h-96 w-96 bg-cyan-600" />
    <Link to="/" className="absolute left-7 top-7 text-sm text-slate-400 hover:text-white">← Back home</Link>
    <div className="relative z-10 w-full max-w-[455px] rounded-[28px] border border-slate-700/50 bg-[#101626]/95 p-7 shadow-2xl sm:p-10">
      <div className="flex justify-center"><Logo /></div><div className="mt-9 text-center"><span className="badge"><Sparkles size={13} /> Your migration workspace</span><h1 className="mt-5 text-3xl font-extrabold">{register ? 'Create your account' : 'Welcome back'}</h1><p className="mt-3 text-sm text-slate-400">{register ? 'Start your journey to smarter ETL migrations.' : 'Sign in to continue your migration projects.'}</p></div>
      <form className="mt-9 space-y-5" onSubmit={submit}>
        <label className="block text-sm font-semibold text-slate-300"><span className="mb-2 flex items-center gap-2"><Mail size={15} /> Email address</span><input className="input mt-1" type="email" required autoComplete="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label className="block text-sm font-semibold text-slate-300"><span className="mb-2 flex items-center gap-2"><LockKeyhole size={15} /> Password</span><input className="input mt-1" type="password" required minLength={register ? 8 : undefined} autoComplete={register ? 'new-password' : 'current-password'} placeholder={register ? 'Minimum 8 characters' : 'Your password'} value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <div role="alert" className="rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
        <button type="submit" disabled={submitting} className="btn-primary w-full">{submitting ? 'Please wait…' : register ? 'Create account' : 'Sign in'} <ArrowRight size={17} /></button>
      </form>
      <p className="mt-7 text-center text-sm text-slate-400">{register ? 'Already have an account?' : 'New to MigraPilot?'} <Link className="font-bold text-lilac hover:text-white" to={register ? '/login' : '/register'}>{register ? 'Sign in' : 'Create account'}</Link></p>
      <div className="mt-8 flex items-center justify-center gap-2 border-t border-slate-800 pt-6 text-xs text-slate-500"><ShieldCheck size={15} /> Your projects stay private to your account</div>
    </div>
  </div>
}
