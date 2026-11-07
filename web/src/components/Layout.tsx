import { NavLink, Outlet } from 'react-router-dom'
import { Activity, BarChart3, Bell, Bot, Boxes, ClipboardList, Coins, FolderKanban, Inbox, LayoutDashboard, Link2, LogOut, Shield, ShieldCheck, Users, Vault } from 'lucide-react'
import { useAuth } from '../auth'
import { role, t } from '../i18n'
import { useWorkspace } from '../workspace'

type Item = { to: string; label: string; icon: typeof LayoutDashboard; end?: boolean }
const main: Item[] = [
  { to: '/', label: 'סקירה', icon: LayoutDashboard, end: true },
  { to: '/projects', label: 'פרויקטים', icon: FolderKanban },
  { to: '/sessions', label: 'סשנים', icon: Activity },
  { to: '/assets', label: 'קטלוג נכסים', icon: Boxes },
  { to: '/connections', label: 'חיבורים', icon: Link2 },
  { to: '/inbox', label: 'תיבת מיון', icon: Inbox },
  { to: '/costs', label: 'עלויות', icon: Coins },
  { to: '/usage', label: 'שימוש לפי לקוח', icon: BarChart3 },
  { to: '/agents', label: 'סוכנים', icon: Bot },
  { to: '/alerts', label: 'התראות', icon: Bell },
]
const security: Item[] = [
  { to: '/security', label: 'לוח סקרים', icon: ShieldCheck, end: true },
  { to: '/security/projects', label: 'פרויקטים והיקף', icon: FolderKanban },
  { to: '/security/runs', label: 'ריצות', icon: Activity },
  { to: '/security/findings', label: 'ממצאים', icon: ShieldCheck },
  { to: '/security/evidence', label: 'כספת ראיות', icon: Vault },
  { to: '/security/reports', label: 'דוחות', icon: ClipboardList },
  { to: '/security/audit', label: 'ביקורת', icon: ClipboardList },
]
const admin: Item[] = [{ to: '/users', label: 'משתמשים', icon: Users }]

function Nav({ items }: { items: Item[] }) {
  return <>{items.map(({ to, label, icon: Icon, end }) => (
    <NavLink key={to} to={to} end={end}
      className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-indigo-50 font-semibold text-indigo-700' : 'text-slate-700 hover:bg-slate-100'}`}>
      <Icon className="h-4 w-4" /> {label}
    </NavLink>))}</>
}

export default function Layout() {
  const { me, logout } = useAuth()
  const { workspaces, current, setCurrent } = useWorkspace()
  const selector = (
    <select className="input w-52" value={current?.id ?? ''} onChange={e => setCurrent(e.target.value || null)} aria-label="מרחב">
      <option value="">כל המרחבים</option>
      {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
    </select>
  )
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 flex-col border-l border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 px-5 py-4">
          <Shield className="h-6 w-6 text-indigo-600" />
          <div><div className="text-sm font-bold">מרכז הבקרה</div><div className="text-xs text-slate-500">פרויקטים, סשנים ואוטומציות</div></div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          <Nav items={main} />
          <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">סקרי אבטחה</div>
          <Nav items={security} />
          <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">ניהול</div>
          <Nav items={admin} />
        </nav>
        <div className="border-t border-slate-100 p-4 text-xs">
          <div className="font-medium text-slate-800">{me?.user.display_name || me?.user.email}</div>
          <div className="text-slate-500">{t(role, me?.user.role)} · {me?.organization.name}</div>
          <button onClick={logout} className="mt-3 flex items-center gap-2 text-slate-600 hover:text-rose-700"><LogOut className="h-4 w-4" /> יציאה</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2">
          <div className="flex items-center gap-2 font-bold md:hidden"><Shield className="h-5 w-5 text-indigo-600" /> מרכז הבקרה</div>
          <div className="hidden text-sm text-slate-500 md:block">מרחב עבודה</div>
          <div className="flex items-center gap-2">{selector}<button onClick={logout} className="text-sm text-slate-600 md:hidden">יציאה</button></div>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-2 py-1 md:hidden">
          {[...main, ...security, ...admin].map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `whitespace-nowrap rounded px-2 py-1 text-xs ${isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600'}`}>{label}</NavLink>
          ))}
        </nav>
        <div className="mx-auto max-w-7xl p-4 md:p-6"><Outlet /></div>
      </main>
    </div>
  )
}
