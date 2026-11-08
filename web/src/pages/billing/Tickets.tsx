import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Printer } from 'lucide-react'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtDate } from '../../i18n'
import { useWorkspace } from '../../workspace'
import { hhmm, priorityTone, ticketPriority, ticketStatus, ticketStatusTone, type BlCustomer, type BlEmployee, type BlProduct, type BlTicket } from './types'

export default function BlTickets() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<BlTicket[] | null>(null)
  const [customers, setCustomers] = useState<BlCustomer[]>([])
  const [products, setProducts] = useState<BlProduct[]>([])
  const [employees, setEmployees] = useState<BlEmployee[]>([])
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState('')
  const status = params.get('status') ?? 'active'
  const open = params.get('new') === '1'
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlTicket[]>(`/billing/tickets${qs}`), api.get<BlCustomer[]>(`/billing/customers${qs}`), api.get<BlProduct[]>(`/billing/products${qs}`), api.get<BlEmployee[]>(`/billing/employees${qs}`)])
    .then(([t, c, p, e]) => { setItems(t); setCustomers(c); setProducts(p); setEmployees(e.filter(x => x.active)) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const setOpen = (v: boolean) => { const p = new URLSearchParams(params); if (v) p.set('new', '1'); else { p.delete('new'); p.delete('customer') }; setParams(p) }
  const setStatus = (s: string) => { const p = new URLSearchParams(params); p.set('status', s); setParams(p) }
  async function create(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const cust = customers.find(c => c.id === fd.get('customer_id'))
    try {
      await api.post('/billing/tickets', { workspace_id: cust?.workspace_id || ws, customer_id: fd.get('customer_id'), product_id: fd.get('product_id') || null, employee_id: fd.get('employee_id') || null, title: fd.get('title'), description: fd.get('description'),
        priority: fd.get('priority'), contact_person: fd.get('contact_person'), contact_phone: fd.get('contact_phone'), group_name: fd.get('group_name'), image_url: fd.get('image_url'),
        opened_at: fd.get('opened_at') ? new Date(String(fd.get('opened_at'))).toISOString() : undefined, initial_minutes: Number(fd.get('initial_minutes') || 0) })
      setOpen(false); load()
    } catch (err) { setError(err) }
  }
  const shown = (items ?? []).filter(t => (status === 'all' || (status === 'active' ? ['open', 'in_progress'].includes(t.status) : t.status === status)) && (!q || `${t.title} ${t.customer_name} ${t.number_label} ${t.contact_person}`.toLowerCase().includes(q.toLowerCase())))
  const totalMin = shown.reduce((a, t) => a + (t.minutes ?? 0), 0)
  function printList() {
    const rows = shown.map(t => `<tr><td>${t.number_label}</td><td>${t.customer_name}</td><td>${t.title}</td><td>${t.contact_person} ${t.contact_phone}</td><td>${ticketStatus[t.status]}</td><td>${ticketPriority[t.priority]}</td><td>${t.employee_name ?? ''}</td><td>${fmtDate(t.opened_at)}</td><td>${hhmm(t.minutes)}</td></tr>`).join('')
    const w = window.open('', '_blank'); if (!w) return
    w.document.write(`<!doctype html><html dir="rtl" lang="he"><head><meta charset="utf-8"><title>דוח קריאות שירות</title><style>body{font-family:Heebo,Arial;padding:24px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{border-bottom:1px solid #ddd;padding:6px;text-align:right}th{background:#f1f5f9}</style></head><body><h1>דוח קריאות שירות</h1><p>${shown.length} קריאות · סה"כ זמן ${hhmm(totalMin)}</p><table><thead><tr><th>מספר</th><th>לקוח</th><th>כותרת</th><th>איש קשר</th><th>סטטוס</th><th>עדיפות</th><th>מטפל</th><th>נפתחה</th><th>זמן</th></tr></thead><tbody>${rows}</tbody></table><script>window.print()</script></body></html>`)
    w.document.close()
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">קריאות שירות</h1><p className="text-sm text-slate-500">כל קריאה צוברת רישומי זמן, ולקוח יכול לדווח בעצמו דרך קישור חיצוני. שעות טיפול נכנסות לדוח השעות ולחיוב.</p></div>
        <div className="flex gap-2"><button className="btn-secondary" onClick={printList}><Printer className="h-4 w-4" /> הדפסה</button><button className="btn-primary" onClick={() => setOpen(!open)}><Plus className="h-4 w-4" /> קריאה חדשה</button></div>
      </div>
      <ErrorBox error={error} />
      {open && (
        <Card title="קריאה חדשה">
          {customers.length === 0 ? <Empty>אין לקוחות במרחב. <Link to="/billing/customers" className="text-indigo-600">הוסף לקוח</Link> קודם.</Empty> : (
            <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
              <Field label="לקוח"><select className="input" name="customer_id" defaultValue={params.get('customer') ?? customers[0].id} required>{customers.filter(c => c.status !== 'closed').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
              <Field label="מוצר"><select className="input" name="product_id" defaultValue=""><option value="">ללא</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
              <Field label="מטפל"><select className="input" name="employee_id" defaultValue={employees[0]?.id ?? ''}><option value="">לא שויך</option>{employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></Field>
              <Field label="תאריך פתיחה"><input className="input ltr" name="opened_at" type="datetime-local" defaultValue={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)} /></Field>
              <Field label="כותרת"><input className="input" name="title" required /></Field>
              <Field label="איש קשר"><input className="input" name="contact_person" /></Field>
              <Field label="טלפון"><input className="input ltr" name="contact_phone" /></Field>
              <Field label="קבוצה" hint="למשל: בנק שעות, פרויקט, תקלה"><input className="input" name="group_name" /></Field>
              <Field label="עדיפות"><select className="input" name="priority" defaultValue="medium">{Object.entries(ticketPriority).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="זמן ראשוני (דקות)"><input className="input ltr" name="initial_minutes" type="number" min={0} defaultValue={0} /></Field>
              <Field label="קישור לתמונה" hint="כתובת של צילום מסך / תמונה"><input className="input ltr" name="image_url" /></Field>
              <Field label="תיאור"><textarea className="input" name="description" rows={2} /></Field>
              <div className="md:col-span-4 flex gap-2"><button className="btn-primary">פתיחת קריאה</button><button type="button" className="btn-secondary" onClick={() => setOpen(false)}>ביטול</button></div>
            </form>
          )}
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="בסינון" value={shown.length} />
        <Stat label="פעילות" value={(items ?? []).filter(t => ['open', 'in_progress'].includes(t.status)).length} tone="amber" />
        <Stat label="נפתרו / נסגרו" value={(items ?? []).filter(t => ['resolved', 'closed'].includes(t.status)).length} tone="emerald" />
        <Stat label="זמן טיפול בסינון" value={hhmm(totalMin)} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <input className="input w-72" placeholder="חיפוש לפי לקוח, כותרת, מספר…" value={q} onChange={e => setQ(e.target.value)} />
        <div className="flex gap-1">{[['active', 'פעילות'], ['open', 'פתוחות'], ['in_progress', 'בטיפול'], ['resolved', 'נפתרו'], ['closed', 'סגורות'], ['all', 'הכול']].map(([k, l]) => <button key={k} className={`rounded-lg px-3 py-1.5 text-xs ${status === k ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'}`} onClick={() => setStatus(k)}>{l}</button>)}</div>
      </div>
      <Card>
        {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין קריאות בסינון הזה.</Empty> : (
          <Table head={['מספר', 'לקוח', 'כותרת', 'מטפל', 'עדיפות', 'סטטוס', 'זמן', 'נפתחה']}>
            {shown.map(t => (
              <tr key={t.id}>
                <td className="px-3 py-2 text-xs ltr"><Link to={`/billing/tickets/${t.id}`} className="text-indigo-700">{t.number_label}</Link></td>
                <td className="px-3 py-2 text-sm"><Link to={`/billing/customers/${t.customer_id}`} className="text-slate-800">{t.customer_name}</Link></td>
                <td className="px-3 py-2"><Link to={`/billing/tickets/${t.id}`} className="font-medium text-indigo-700">{t.title}</Link>{t.group_name && <span className="badge mr-2 bg-slate-100 text-slate-600">{t.group_name}</span>}<div className="truncate text-xs text-slate-500" style={{ maxWidth: 360 }}>{t.description}</div></td>
                <td className="px-3 py-2 text-sm">{t.employee_name || '—'}</td>
                <td className="px-3 py-2"><span className={`badge ${priorityTone[t.priority]}`}>{ticketPriority[t.priority]}</span></td>
                <td className="px-3 py-2"><span className={`badge ${ticketStatusTone[t.status]}`}>{ticketStatus[t.status]}</span></td>
                <td className="px-3 py-2 text-sm ltr">{hhmm(t.minutes)}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(t.opened_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
