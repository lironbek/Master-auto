import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { customerStatus, ils, type BlCustomer } from './types'

const statusTone: Record<string, string> = { active: 'bg-emerald-100 text-emerald-800', frozen: 'bg-amber-100 text-amber-800', closed: 'bg-slate-200 text-slate-600' }

export default function BlCustomers() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [items, setItems] = useState<BlCustomer[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [showClosed, setShowClosed] = useState(false)
  const load = () => api.get<BlCustomer[]>(`/billing/customers${qs}`).then(setItems).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  async function create(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      await api.post('/billing/customers', { workspace_id: fd.get('workspace_id') || current?.id || workspaces[0].id, name: fd.get('name'), contact_person: fd.get('contact_person'), email: fd.get('email'), phone: fd.get('phone'), address: fd.get('address'), payment_method: fd.get('payment_method'), vat_id: fd.get('vat_id') })
      setOpen(false); load()
    } catch (err) { setError(err) }
  }
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const shown = (items ?? []).filter(c => (showClosed || c.status !== 'closed') && (!q || `${c.name} ${c.email} ${c.contact_person} ${c.phone}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">לקוחות</h1><p className="text-sm text-slate-500">כל לקוח הוא גם לקוח במדידת השימוש, כך שחיובים, קריאות ושימוש ב-API מופיעים במקום אחד.</p></div>
        <button className="btn-primary" onClick={() => setOpen(v => !v)}><Plus className="h-4 w-4" /> לקוח חדש</button>
      </div>
      <ErrorBox error={error} />
      {open && (
        <Card title="לקוח חדש">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
            {!current && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={workspaces[0].id}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
            <Field label="שם"><input className="input" name="name" required /></Field>
            <Field label="איש קשר"><input className="input" name="contact_person" /></Field>
            <Field label="אימייל"><input className="input ltr" name="email" type="email" /></Field>
            <Field label="טלפון"><input className="input ltr" name="phone" /></Field>
            <Field label="כתובת"><input className="input" name="address" /></Field>
            <Field label="אמצעי תשלום"><input className="input" name="payment_method" placeholder="הוראת קבע / אשראי / העברה" /></Field>
            <Field label="ח.פ. / ע.מ."><input className="input ltr" name="vat_id" /></Field>
            <div className="flex items-end"><button className="btn-primary">יצירה</button></div>
          </form>
        </Card>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <input className="input w-72" placeholder="חיפוש לפי שם, אימייל, איש קשר…" value={q} onChange={e => setQ(e.target.value)} />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)} /> הצג גם סגורים</label>
      </div>
      <Card>
        {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין לקוחות. הוסף לקוח או הרץ את הייבוא מהמערכת הישנה.</Empty> : (
          <Table head={['לקוח', 'איש קשר', 'מנויים', 'משתמשים', 'קריאות פתוחות', 'ממתין לתשלום', 'סטטוס']}>
            {shown.map(c => (
              <tr key={c.id}>
                <td className="px-3 py-2"><Link to={`/billing/customers/${c.id}`} className="font-medium text-indigo-700">{c.name}</Link><div className="text-xs text-slate-500 ltr">{c.email}</div></td>
                <td className="px-3 py-2 text-sm">{c.contact_person || '—'}<div className="text-xs text-slate-500 ltr">{c.phone}</div></td>
                <td className="px-3 py-2 text-sm">{c.subscriptions ?? 0}</td>
                <td className="px-3 py-2 text-sm">{c.users ?? 0}</td>
                <td className="px-3 py-2 text-sm">{c.open_tickets ? <span className="badge bg-amber-100 text-amber-800">{c.open_tickets}</span> : '0'}</td>
                <td className="px-3 py-2 text-sm">{c.unpaid ? <span className="font-semibold text-rose-700">{ils(c.unpaid)}</span> : '—'}</td>
                <td className="px-3 py-2"><span className={`badge ${statusTone[c.status] ?? 'bg-slate-100'}`}>{customerStatus[c.status] ?? c.status}</span></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
