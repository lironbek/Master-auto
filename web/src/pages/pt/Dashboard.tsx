import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Dashboard as DashboardData } from '../../api'
import { Card, DecisionBadge, Empty, ErrorBox, RunBadge, SeverityBadge, Spinner, Stat } from '../../components/ui'
import { auditAction, decision, fmtDate, t } from '../../i18n'

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let alive = true
    const load = () => api.get<DashboardData>('/pt/dashboard').then(d => { if (alive) { setData(d); setError(null) } }).catch(err => alive && setError(err))
    load()
    const id = setInterval(load, 10_000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Spinner />

  const sev = data.findings.by_severity
  return (
    <div className="space-y-6">
      <ErrorBox error={error} />
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold">לוח בקרה</h1>
          <p className="text-sm text-slate-500">פרויקטים, ריצות, סיכונים והתקדמות</p>
        </div>
        <span className="text-xs text-slate-400">אחסון: <span className="mono">{data.storage}</span></span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="פרויקטים" value={data.projects} tone="indigo" />
        <Stat label="ריצות" value={data.runs.total} hint={Object.entries(data.runs.by_status).map(([k, v]) => `${t({ created: 'נוצרו', running: 'רצות', stopped: 'נעצרו', completed: 'הושלמו', paused: 'מושהות', failed: 'נכשלו' }, k)} ${v}`).join(' · ')} />
        <Stat label="ממצאים פתוחים" value={data.findings.open} hint={`מתוך ${data.findings.total}`} tone="amber" />
        <Stat label="קריטיים / גבוהים" value={(sev.critical ?? 0) + (sev.high ?? 0)} tone="rose" hint={`בינוניים ${sev.medium ?? 0} · נמוכים ${sev.low ?? 0}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="ריצות אחרונות" actions={<Link to="/security/runs" className="text-xs text-indigo-600">הכול</Link>}>
          {data.recent_runs.length === 0 ? <Empty>עדיין אין ריצות. צור פרויקט, הגדר היקף, אשר אותו והפעל ריצה.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {data.recent_runs.map(r => (
                <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                  <Link to={`/security/runs/${r.id}`} className="mono text-indigo-700">{r.id}</Link>
                  <span className="text-xs text-slate-500">{fmtDate(r.created_at)}</span>
                  <RunBadge value={r.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="ממצאים אחרונים" actions={<Link to="/security/findings" className="text-xs text-indigo-600">הכול</Link>}>
          {data.recent_findings.length === 0 ? <Empty>אין ממצאים. היעדר ממצאים אינו אישור שהמערכת מאובטחת.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {data.recent_findings.map(f => (
                <li key={f.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <Link to={`/security/findings/${f.id}`} className="truncate text-indigo-700">{f.title}</Link>
                  <SeverityBadge value={f.severity} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="אירועים אחרונים" actions={<Link to="/security/audit" className="text-xs text-indigo-600">יומן מלא</Link>}>
        {data.recent_events.length === 0 ? <Empty>אין אירועים.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {data.recent_events.map(e => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="w-32 shrink-0 text-xs text-slate-400">{fmtDate(e.at)}</span>
                <span className="font-medium">{t(auditAction, e.action)}</span>
                <DecisionBadge value={e.decision} label={t(decision, e.decision)} />
                <span className="mono truncate text-slate-500">{e.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
