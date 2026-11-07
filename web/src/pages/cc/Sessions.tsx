import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type CcProject, type WorkSession } from '../../api'
import { Card, Empty, ErrorBox, Spinner, Table } from '../../components/ui'
import { fmtDate, sessionStatus, sessionTool, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

const tone: Record<string, string> = { open: 'bg-emerald-100 text-emerald-800', waiting: 'bg-amber-100 text-amber-800', done: 'bg-slate-200 text-slate-700', cancelled: 'bg-slate-200 text-slate-500' }

export default function Sessions() {
  const { qs, loading } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<WorkSession[] | null>(null)
  const [projects, setProjects] = useState<Record<string, string>>({})
  const [error, setError] = useState<unknown>(null)
  const onlyOpen = params.get('filter') === 'open'

  useEffect(() => {
    if (loading) return
    Promise.all([api.get<WorkSession[]>(`/cc/sessions${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`)])
      .then(([s, p]) => { setItems(s); setProjects(Object.fromEntries(p.map(x => [x.id, x.name]))) }).catch(setError)
  }, [qs, loading])

  const shown = items?.filter(s => !onlyOpen || s.status === 'open')
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold">סשני עבודה</h1><p className="text-sm text-slate-500">פרקי עבודה המקבצים פעולות ותוצרים מהכלים השונים</p></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyOpen} onChange={e => setParams(e.target.checked ? { filter: 'open' } : {})} /> פתוחים בלבד</label>
      </div>
      <ErrorBox error={error} />
      <Card>
        {!shown ? <Spinner /> : shown.length === 0 ? <Empty>אין סשנים. פותחים סשן מתוך עמוד פרויקט.</Empty> : (
          <Table head={['סשן', 'פרויקט', 'כלי', 'אחראי', 'סטטוס', 'פעילות אחרונה', 'תוצר']}>
            {shown.map(s => (
              <tr key={s.id}>
                <td className="px-3 py-2"><Link to={`/sessions/${s.id}`} className="font-medium text-indigo-700">{s.title}</Link><div className="text-xs text-slate-500">{s.goal}</div></td>
                <td className="px-3 py-2 text-sm"><Link to={`/projects/${s.project_id}`} className="text-indigo-700">{projects[s.project_id] ?? s.project_id}</Link></td>
                <td className="px-3 py-2 text-xs">{t(sessionTool, s.tool)}</td>
                <td className="px-3 py-2 text-xs">{s.owner}</td>
                <td className="px-3 py-2"><span className={`badge ${tone[s.status]}`}>{t(sessionStatus, s.status)}</span>{s.idle && <span className="badge mr-1 bg-amber-100 text-amber-800">ללא פעילות לאחרונה</span>}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(s.last_activity_at)} · {s.event_count} אירועים</td>
                <td className="px-3 py-2 text-xs">{s.outcome || '—'}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
