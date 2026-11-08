import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtRel } from '../../i18n'
import { useWorkspace } from '../../workspace'
import { activityType, hhmm, type BlActivity } from './types'

const tone: Record<string, string> = { ticket: 'bg-sky-100 text-sky-800', time_entry: 'bg-emerald-100 text-emerald-800', external_update: 'bg-violet-100 text-violet-800' }

export default function BlActivities() {
  const { workspaces, qs, loading } = useWorkspace()
  const [items, setItems] = useState<BlActivity[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  useEffect(() => { if (!loading && workspaces.length) api.get<BlActivity[]>(`/billing/activities${qs}${qs ? '&' : '?'}limit=500`).then(setItems).catch(setError) }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const shown = (items ?? []).filter(a => (!type || a.type === type) && (!q || `${a.title} ${a.customer_name} ${a.actor} ${a.detail}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">רשימת פעילויות</h1><p className="text-sm text-slate-500">פיד אחד של קריאות שנפתחו, רישומי זמן ודיווחים שהלקוחות שלחו.</p></div>
      <ErrorBox error={error} />
      <Card>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="חיפוש"><input className="input" value={q} onChange={e => setQ(e.target.value)} /></Field>
          <Field label="סוג"><select className="input" value={type} onChange={e => setType(e.target.value)}><option value="">הכול</option>{Object.entries(activityType).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <div className="flex items-end text-sm text-slate-500">{shown.length} פעילויות</div>
        </div>
      </Card>
      <Card>
        {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין פעילויות.</Empty> : (
          <ul className="divide-y divide-slate-100">{shown.map(a => (
            <li key={a.id} className="flex flex-wrap items-start gap-3 py-3 text-sm">
              <span className={`badge mt-0.5 ${tone[a.type]}`}>{activityType[a.type]}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><Link to={`/billing/tickets/${a.ticket_id}`} className="font-semibold text-indigo-700">{a.title}</Link><span className="text-xs text-slate-500">{a.customer_name}</span>{a.actor && <span className="text-xs text-slate-500">· {a.actor}</span>}{a.minutes ? <span className="badge bg-slate-100 text-slate-700">{hhmm(a.minutes)}</span> : null}</div>
                {a.detail && <div className="mt-0.5 line-clamp-2 text-slate-600">{a.detail}</div>}
              </div>
              <span className="text-xs text-slate-400">{fmtRel(a.at)}</span>
            </li>))}</ul>
        )}
      </Card>
    </div>
  )
}
