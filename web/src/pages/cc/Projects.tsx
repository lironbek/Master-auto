import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api, type CcProject, type Overview as OverviewData } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace, TonePill } from '../../components/cc'
import { environment, fmtDate, importance, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

export default function CcProjects() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [items, setItems] = useState<CcProject[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ workspace_id: '', name: '', description: '', owner: '', importance: 'normal', environment: 'unclassified', budget_usd: 0 })
  const [archived, setArchived] = useState(false)

  const load = () => api.get<OverviewData>(`/cc/overview${qs}`).then(d => setItems(d.projects)).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])

  async function create(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post('/cc/projects', { ...f, workspace_id: f.workspace_id || current?.id || workspaces[0].id })
      setOpen(false); setF({ ...f, name: '', description: '' }); load()
    } catch (err) { setError(err) }
  }

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold">פרויקטים</h1><p className="text-sm text-slate-500">שם, בעלים, סביבה, חיבורים, חריגה אחרונה וסשן אחרון</p></div>
        <button className="btn-primary" onClick={() => setOpen(v => !v)}><Plus className="h-4 w-4" /> פרויקט חדש</button>
      </div>
      <ErrorBox error={error} />
      {open && (
        <Card title="פרויקט חדש">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-3">
            <Field label="מרחב"><select className="input" value={f.workspace_id || current?.id || workspaces[0].id} onChange={e => setF({ ...f, workspace_id: e.target.value })}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
            <Field label="שם"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></Field>
            <Field label="בעלים"><input className="input" value={f.owner} onChange={e => setF({ ...f, owner: e.target.value })} /></Field>
            <Field label="תיאור"><input className="input" value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></Field>
            <Field label="חשיבות"><select className="input" value={f.importance} onChange={e => setF({ ...f, importance: e.target.value })}>{Object.entries(importance).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="סביבה"><select className="input" value={f.environment} onChange={e => setF({ ...f, environment: e.target.value })}>{Object.entries(environment).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="תקציב חודשי ($)"><input className="input ltr" type="number" min={0} value={f.budget_usd} onChange={e => setF({ ...f, budget_usd: Number(e.target.value) })} /></Field>
            <div className="flex items-end"><button className="btn-primary">יצירה</button></div>
          </form>
        </Card>
      )}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={archived} onChange={e => setArchived(e.target.checked)} /> הצג גם ארכיון</label>
      <Card>
        {!items ? <Spinner /> : items.length === 0 ? <Empty>אין פרויקטים במרחב הזה.</Empty> : (
          <Table head={['פרויקט', 'בעלים', 'סביבה', 'חשיבות', 'נכסים', 'מצב', 'סשן אחרון']}>
            {items.filter(p => archived || p.status === 'active').map(p => (
              <tr key={p.id}>
                <td className="px-3 py-2"><Link to={`/projects/${p.id}`} className="font-medium text-indigo-700">{p.name}</Link><div className="text-xs text-slate-500">{p.description}</div></td>
                <td className="px-3 py-2 text-sm">{p.owner || '—'}</td>
                <td className="px-3 py-2 text-xs">{t(environment, p.environment)}</td>
                <td className="px-3 py-2 text-xs">{t(importance, p.importance)}</td>
                <td className="px-3 py-2 text-xs">{p.asset_count ?? 0}</td>
                <td className="px-3 py-2"><TonePill tone={p.tone}>{p.last_failure ? p.last_failure.title : 'ללא כשל'}</TonePill></td>
                <td className="px-3 py-2 text-xs">{p.last_session ? <Link to={`/sessions/${p.last_session.id}`} className="text-indigo-700">{p.last_session.title}</Link> : '—'} {p.last_session && <span className="text-slate-400">{fmtDate(p.last_session.started_at)}</span>}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
