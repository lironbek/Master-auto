import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Alert } from '../../api'
import { Card, Empty, ErrorBox, Spinner, Table } from '../../components/ui'
import { alertKind, fmtDate, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

const tone: Record<string, string> = { open: 'bg-rose-100 text-rose-800', acknowledged: 'bg-emerald-100 text-emerald-800', snoozed: 'bg-slate-200 text-slate-600' }
const statusLabel: Record<string, string> = { open: 'פתוח', acknowledged: 'טופל', snoozed: 'מושהה' }

export default function Alerts() {
  const { qs, loading } = useWorkspace()
  const [items, setItems] = useState<Alert[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const load = () => api.get<Alert[]>(`/cc/alerts${qs}`).then(setItems).catch(setError)
  useEffect(() => { if (!loading) load() }, [qs, loading])
  async function act(id: string, action: string) { try { await api.post(`/cc/alerts/${id}`, { action }); load() } catch (err) { setError(err) } }
  const target = (a: Alert) => a.target_kind === 'asset' ? <Link to={`/assets/${a.target_id}`} className="text-indigo-700">נכס</Link> : a.target_kind === 'connection' ? <Link to="/connections" className="text-indigo-700">חיבור</Link> : a.target_id
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">התראות והיסטוריה</h1><p className="text-sm text-slate-500">כשל אחרון, כשלים חוזרים, עיכוב בסנכרון, שינויים בהרשאות. הכללים: כשל בייצור על נכס משויך, אין סנכרון תקין מעל 45 דקות, אובדן הרשאה.</p></div>
      <ErrorBox error={error} />
      <Card>
        {!items ? <Spinner /> : items.length === 0 ? <Empty>אין התראות.</Empty> : (
          <Table head={['זמן', 'סוג', 'הודעה', 'יעד', 'סטטוס', '']}>
            {items.map(a => <tr key={a.id}><td className="px-3 py-2 text-xs">{fmtDate(a.created_at)}</td><td className="px-3 py-2 text-sm">{t(alertKind, a.kind)}</td><td className="px-3 py-2 text-sm">{a.message}</td><td className="px-3 py-2 text-xs">{target(a)}</td><td className="px-3 py-2"><span className={`badge ${tone[a.status]}`}>{statusLabel[a.status]}</span></td><td className="px-3 py-2">{a.status === 'open' && <div className="flex gap-1"><button className="btn-secondary" onClick={() => act(a.id, 'acknowledge')}>אישור טיפול</button><button className="btn-secondary" onClick={() => act(a.id, 'snooze')}>השהיה</button></div>}</td></tr>)}
          </Table>
        )}
      </Card>
    </div>
  )
}
