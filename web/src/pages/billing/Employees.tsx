import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { employeeRole, hhmm, ils, type BlEmployee } from './types'

interface User { id: string; email: string; display_name: string; role: string }

export default function BlEmployees() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [items, setItems] = useState<BlEmployee[] | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [edit, setEdit] = useState<BlEmployee | null>(null)
  const [error, setError] = useState<unknown>(null)
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlEmployee[]>(`/billing/employees${qs}`), api.get<User[]>('/auth/users').catch(() => [] as User[])]).then(([e, u]) => { setItems(e); setUsers(u) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { name: fd.get('name'), email: fd.get('email'), phone: fd.get('phone'), position: fd.get('position'), role: fd.get('role'), hourly_rate: fd.get('hourly_rate') ? Number(fd.get('hourly_rate')) : undefined, user_id: String(fd.get('user_id') ?? ''), active: fd.get('active') === 'on' }
    try { if (edit) await api.patch(`/billing/employees/${edit.id}`, body); else await api.post('/billing/employees', { workspace_id: fd.get('workspace_id') || ws, ...body }); setEdit(null); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function remove(id: string) { if (!confirm('למחוק את העובד? קריאות ורישומי זמן ישמרו ללא מטפל.')) return; try { await api.del(`/billing/employees/${id}`); load() } catch (err) { setError(err) } }
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">עובדים</h1><p className="text-sm text-slate-500">מי מטפל בקריאות ורושם זמן. עובד יכול להיות מקושר למשתמש במערכת (כניסה דרך <Link to="/users" className="text-indigo-600">משתמשים</Link>) ולקבל תעריף שעה לחיוב.</p></div>
      <ErrorBox error={error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="עובדים" className="lg:col-span-2">
          {!items ? <Spinner /> : items.length === 0 ? <Empty>אין עובדים עדיין.</Empty> : (
            <Table head={['עובד', 'תפקיד', 'תעריף שעה', 'משתמש מערכת', 'שעות החודש', 'קריאות פתוחות', '']}>
              {items.map(e => (
                <tr key={e.id} className={e.active ? '' : 'opacity-50'}>
                  <td className="px-3 py-2 font-medium">{e.name}<div className="text-xs text-slate-500">{e.position}{e.email ? ` · ${e.email}` : ''}</div></td>
                  <td className="px-3 py-2 text-sm">{employeeRole[e.role] ?? e.role}</td>
                  <td className="px-3 py-2 text-sm">{e.hourly_rate ? <bdi>{ils(e.hourly_rate)}</bdi> : '—'}</td>
                  <td className="px-3 py-2 text-xs ltr">{e.user_email || '—'}</td>
                  <td className="px-3 py-2 text-sm">{hhmm(e.minutes_month)}</td>
                  <td className="px-3 py-2 text-sm">{e.open_tickets ?? 0}</td>
                  <td className="px-3 py-2 text-xs"><div className="flex gap-2"><button className="text-indigo-700" onClick={() => setEdit(e)}>עריכה</button><button className="text-rose-700" onClick={() => remove(e.id)}>מחק</button></div></td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title={edit ? `עריכת ${edit.name}` : 'עובד חדש'} actions={edit && <button className="text-xs text-slate-500" onClick={() => setEdit(null)}>ביטול</button>}>
          <form key={edit?.id ?? 'new'} onSubmit={save} className="space-y-3">
            {!current && !edit && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={ws}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
            <Field label="שם"><input className="input" name="name" defaultValue={edit?.name ?? ''} required /></Field>
            <Field label="תפקיד"><select className="input" name="role" defaultValue={edit?.role ?? 'support'}>{Object.entries(employeeRole).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="תפקיד / תיאור"><input className="input" name="position" defaultValue={edit?.position ?? ''} /></Field>
            <Field label="אימייל"><input className="input ltr" name="email" defaultValue={edit?.email ?? ''} /></Field>
            <Field label="טלפון"><input className="input ltr" name="phone" defaultValue={edit?.phone ?? ''} /></Field>
            <Field label="תעריף שעה (₪)"><input className="input ltr" name="hourly_rate" type="number" min={0} step="0.01" defaultValue={edit?.hourly_rate ?? ''} /></Field>
            <Field label="משתמש מערכת" hint="מי שנכנס למערכת ורושם זמן בשם העובד"><select className="input" name="user_id" defaultValue={edit?.user_id ?? ''}><option value="">ללא</option>{users.map(u => <option key={u.id} value={u.id}>{u.display_name || u.email}</option>)}</select></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="active" defaultChecked={edit?.active ?? true} /> פעיל</label>
            <button className="btn-primary w-full justify-center">{edit ? 'שמירה' : 'הוספה'}</button>
          </form>
        </Card>
      </div>
    </div>
  )
}
