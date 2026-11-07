import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Overview as OverviewData } from '../../api'
import { Card, Empty, ErrorBox, Spinner, Stat } from '../../components/ui'
import { ConnPill, EventRow, FirstWorkspace, TonePill } from '../../components/cc'
import { alertKind, assetKind, fmtDate, provider, sessionStatus, sessionTool, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

export default function Overview() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    if (loading || workspaces.length === 0) return
    let alive = true
    const load = () => api.get<OverviewData>(`/cc/overview${qs}`).then(d => { if (alive) { setData(d); setError(null) } }).catch(err => alive && setError(err))
    load()
    const id = setInterval(load, 30_000)
    return () => { alive = false; clearInterval(id) }
  }, [qs, loading, workspaces.length])

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Spinner />

  const active = data.projects.filter(p => p.status === 'active')
  const stale = data.connections.filter(c => c.freshness?.stale && ['ok', 'partial', 'error'].includes(c.status))
  return (
    <div className="space-y-6">
      <ErrorBox error={error} />
      <section className="rounded-2xl bg-gradient-to-l from-slate-900 to-sky-900 p-6 text-white">
        <div className="text-xs font-semibold text-teal-300">{current ? current.name : 'כל המרחבים'}</div>
        <h1 className="mt-1 text-2xl font-bold">מרכז הבקרה</h1>
        <p className="text-sm text-slate-200">הפרויקטים, סשני העבודה והאוטומציות שלך במקום אחד. תוך פחות מדקה: מה קיים, מה כל רכיב עושה, איפה הוא רץ ומתי התקבל ממנו מידע.</p>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Link to="/projects" className="contents"><Stat label="פרויקטים פעילים" value={active.length} tone="indigo" /></Link>
        <Link to="/assets" className="contents"><Stat label="נכסים בקטלוג" value={data.assets_total} hint={Object.entries(data.assets_by_kind).map(([k, v]) => `${t(assetKind, k)} ${v}`).join(' · ') || 'אין נכסים עדיין'} /></Link>
        <Link to="/sessions" className="contents"><Stat label="סשנים פתוחים" value={data.open_sessions.length} tone="amber" /></Link>
        <Link to="/inbox" className="contents"><Stat label="ממתינים לשיוך" value={data.inbox_open} hint={`${data.unassigned} נכסים ללא פרויקט`} tone={data.inbox_open ? 'rose' : 'slate'} /></Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card title="הפרויקטים שלי" className="lg:col-span-3" actions={<Link to="/projects" className="text-xs text-indigo-600">הכול</Link>}>
          {active.length === 0 ? <Empty>אין פרויקטים. צור פרויקט או שייך נכסים מתיבת המיון.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {active.map(p => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <div className="min-w-0">
                    <Link to={`/projects/${p.id}`} className="font-semibold text-indigo-700">{p.name}</Link>
                    <div className="truncate text-xs text-slate-500">{p.description || '—'} · {p.asset_count ?? 0} נכסים{p.last_session ? ` · סשן אחרון: ${p.last_session.title}` : ''}</div>
                  </div>
                  <TonePill tone={p.tone}>{p.tone === 'bad' ? 'כשל בייצור' : p.tone === 'warn' ? 'דורש בדיקה' : 'תקין'}</TonePill>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="דורש תשומת לב" className="lg:col-span-2" actions={<Link to="/alerts" className="text-xs text-indigo-600">התראות</Link>}>
          {data.critical_alerts.length === 0 && stale.length === 0 ? <Empty>אין חריגות פתוחות.</Empty> : (
            <ul className="space-y-2 text-sm">
              {data.critical_alerts.slice(0, 8).map(a => (
                <li key={a.id} className="rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
                  <div className="text-xs font-semibold text-rose-800">{t(alertKind, a.kind)}</div>
                  <div className="text-slate-700">{a.message}</div>
                  <div className="text-xs text-slate-400">{fmtDate(a.created_at)}</div>
                </li>
              ))}
              {stale.map(c => <li key={c.id} className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-amber-900">הפיד של {t(provider, c.provider)} אינו עדכני (אין סנכרון תקין מעל 45 דקות)</li>)}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="סשנים פתוחים" actions={<Link to="/sessions" className="text-xs text-indigo-600">הכול</Link>}>
          {data.open_sessions.length === 0 ? <Empty>אין סשנים פתוחים.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {data.open_sessions.map(s => <li key={s.id} className="flex items-center justify-between py-2"><Link to={`/sessions/${s.id}`} className="text-indigo-700">{s.title}</Link><span className="text-xs text-slate-500">{t(sessionTool, s.tool)} · {t(sessionStatus, s.status)}</span></li>)}
            </ul>
          )}
        </Card>
        <Card title="חיבורים" actions={<Link to="/connections" className="text-xs text-indigo-600">ניהול</Link>}>
          {data.connections.length === 0 ? <Empty>אין חיבורים. חבר GitHub, Vercel, Supabase או n8n כדי למלא את הקטלוג.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {data.connections.map(c => <li key={c.id} className="flex items-center justify-between py-2"><span>{t(provider, c.provider)} · {c.account_label}</span><span className="flex items-center gap-2 text-xs text-slate-500">{c.last_sync_at ? fmtDate(c.last_sync_at) : 'טרם סונכרן'} <ConnPill value={c.status} /></span></li>)}
            </ul>
          )}
        </Card>
      </div>

      <Card title="פעילות אחרונה">
        {data.recent_events.length === 0 ? <Empty>אין אירועים עדיין. אחרי סנכרון ראשון יופיעו כאן פריסות, ריצות ו-PRs.</Empty> : <ul className="divide-y divide-slate-100">{data.recent_events.map(e => <EventRow key={e.id} e={e} showProject />)}</ul>}
      </Card>
    </div>
  )
}
