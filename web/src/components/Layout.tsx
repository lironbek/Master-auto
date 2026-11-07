import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, Bell, Bot, Boxes, ClipboardList, Coins, Eye, FolderKanban, Inbox, LayoutDashboard, Link2, LogOut, Search, Shield, ShieldCheck, Sparkles, Users, Vault } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { role, t } from '../i18n'
import { useWorkspace } from '../workspace'

type Item = { to: string; label: string; icon: typeof LayoutDashboard; end?: boolean; tint: string }
const main: Item[] = [
  { to: '/', label: 'לוח בקרה', icon: LayoutDashboard, end: true, tint: 'bg-indigo-100 text-indigo-600' },
  { to: '/projects', label: 'פרויקטים', icon: FolderKanban, tint: 'bg-teal-100 text-teal-700' },
  { to: '/sessions', label: 'סשנים', icon: Activity, tint: 'bg-sky-100 text-sky-700' },
  { to: '/assets', label: 'קטלוג נכסים', icon: Boxes, tint: 'bg-violet-100 text-violet-700' },
  { to: '/connections', label: 'אינטגרציות', icon: Link2, tint: 'bg-amber-100 text-amber-700' },
  { to: '/inbox', label: 'תיבת מיון', icon: Inbox, tint: 'bg-rose-100 text-rose-600' },
  { to: '/costs', label: 'עלויות', icon: Coins, tint: 'bg-emerald-100 text-emerald-700' },
  { to: '/usage', label: 'אנליטיקות', icon: BarChart3, tint: 'bg-fuchsia-100 text-fuchsia-700' },
  { to: '/agents', label: 'סוכנים ובוטים', icon: Bot, tint: 'bg-cyan-100 text-cyan-700' },
  { to: '/alerts', label: 'התראות', icon: Bell, tint: 'bg-orange-100 text-orange-600' },
]
const security: Item[] = [
  { to: '/security', label: 'לוח סקרים', icon: ShieldCheck, end: true, tint: 'bg-indigo-100 text-indigo-600' },
  { to: '/security/projects', label: 'פרויקטים והיקף', icon: FolderKanban, tint: 'bg-teal-100 text-teal-700' },
  { to: '/security/runs', label: 'ריצות', icon: Activity, tint: 'bg-sky-100 text-sky-700' },
  { to: '/security/findings', label: 'ממצאים', icon: ShieldCheck, tint: 'bg-rose-100 text-rose-600' },
  { to: '/security/evidence', label: 'כספת ראיות', icon: Vault, tint: 'bg-violet-100 text-violet-700' },
  { to: '/security/reports', label: 'דוחות', icon: ClipboardList, tint: 'bg-amber-100 text-amber-700' },
  { to: '/security/audit', label: 'ביקורת', icon: ClipboardList, tint: 'bg-slate-100 text-slate-600' },
]
const admin: Item[] = [{ to: '/users', label: 'משתמשים', icon: Users, tint: 'bg-emerald-100 text-emerald-700' }]

function Nav({ items }: { items: Item[] }) {
  return <>{items.map(({ to, label, icon: Icon, end, tint }) => (
    <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}>
      <span className={`grid h-8 w-8 place-items-center rounded-lg ${tint}`}><Icon className="h-4 w-4" /></span> {label}
    </NavLink>))}</>
}

function initials(name: string): string {
  return name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(s => s[0]?.toUpperCase() ?? '').join('') || '?'
}

export default function Layout() {
  const { me, logout } = useAuth()
  const { workspaces, current, setCurrent } = useWorkspace()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [alertCount, setAlertCount] = useState(0)
  useEffect(() => {
    let alive = true
    api.get<{ id: string; status: string }[]>('/cc/alerts').then(rows => alive && setAlertCount(rows.filter(a => a.status === 'open').length)).catch(() => {})
    return () => { alive = false }
  }, [current?.id])
  const viewer = me?.user.role === 'auditor' || me?.user.role === 'client' || me?.user.role === 'executive'
  const name = me?.user.display_name || me?.user.email || ''
  const selector = (
    <select className="input w-44 rounded-xl border-white/70 bg-white/80" value={current?.id ?? ''} onChange={e => setCurrent(e.target.value || null)} aria-label="מרחב">
      <option value="">כל המרחבים</option>
      {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
    </select>
  )
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 flex-col border-l border-white/60 bg-white/60 backdrop-blur md:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-teal-400 text-white shadow-md"><Shield className="h-5 w-5" /></span>
          <div><div className="text-base font-bold">מרכז הבקרה</div><div className="text-xs text-slate-500">כל הפרויקטים במקום אחד</div></div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          <Nav items={main} />
          <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">סקרי אבטחה</div>
          <Nav items={security} />
          <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">ניהול</div>
          <Nav items={admin} />
        </nav>
        <div className="m-3 rounded-2xl bg-gradient-to-br from-indigo-50 to-teal-50 p-4 ring-1 ring-white">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Sparkles className="h-4 w-4 text-indigo-500" /> צריכים עזרה?</div>
          <p className="mt-1 text-xs text-slate-500">הסוכנים יכולים לסכם, לסרוק ולהציע פעולות על כל פרויקט.</p>
          <NavLink to="/agents" className="mt-2 inline-block text-xs font-semibold text-indigo-600">← לסוכנים</NavLink>
        </div>
        <div className="border-t border-white/70 p-4 text-xs">
          <div className="font-medium text-slate-800">{name}</div>
          <div className="text-slate-500">{t(role, me?.user.role)} · {me?.organization.name}</div>
          <button onClick={logout} className="mt-3 flex items-center gap-2 text-slate-600 hover:text-rose-700"><LogOut className="h-4 w-4" /> יציאה</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
          <div className="flex items-center gap-2 font-bold md:hidden"><Shield className="h-5 w-5 text-indigo-600" /> מרכז הבקרה</div>
          <form className="relative hidden w-full max-w-md md:block" onSubmit={e => { e.preventDefault(); if (q.trim()) nav(`/assets?q=${encodeURIComponent(q.trim())}`) }}>
            <Search className="pointer-events-none absolute right-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input rounded-xl border-white/70 bg-white/80 pr-9" placeholder="חיפוש פרויקט, ריפו או שירות…" value={q} onChange={e => setQ(e.target.value)} aria-label="חיפוש" />
          </form>
          <div className="flex items-center gap-2">
            {selector}
            {viewer && <span className="chip hidden bg-white/80 text-slate-600 ring-1 ring-white md:inline-flex"><Eye className="h-3.5 w-3.5" /> צפייה בלבד</span>}
            <NavLink to="/alerts" className="relative grid h-10 w-10 place-items-center rounded-xl bg-white/80 text-slate-600 ring-1 ring-white" aria-label="התראות">
              <Bell className="h-4 w-4" />
              {alertCount > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white" />}
            </NavLink>
            <span className="hidden h-10 w-10 place-items-center rounded-full bg-gradient-to-br from-violet-400 to-indigo-500 text-sm font-bold text-white md:grid" title={name}>{initials(name)}</span>
            <button onClick={logout} className="text-sm text-slate-600 md:hidden">יציאה</button>
          </div>
        </header>
        <nav className="flex gap-1 overflow-x-auto px-2 py-1 md:hidden">
          {[...main, ...security, ...admin].map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `whitespace-nowrap rounded-lg px-2 py-1 text-xs ${isActive ? 'bg-white font-semibold text-indigo-700 shadow-sm' : 'text-slate-600'}`}>{label}</NavLink>
          ))}
        </nav>
        <div className="mx-auto max-w-7xl p-4 md:p-6"><Outlet /></div>
      </main>
    </div>
  )
}
