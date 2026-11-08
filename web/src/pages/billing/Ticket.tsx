import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Copy, Link2, Trash2 } from 'lucide-react'
import { api } from '../../api'
import { BrandIcon } from '../../components/brand'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { fmtDate } from '../../i18n'
import { hhmm, priorityTone, ticketPriority, ticketStatus, ticketStatusTone, today, type BlCustomer, type BlEmployee, type BlExternalUpdate, type BlProduct, type BlTicket, type BlTimeEntry } from './types'

interface Detail { ticket: BlTicket; time_entries: BlTimeEntry[]; external_updates: BlExternalUpdate[] }

export default function BlTicketPage() {
  const { id } = useParams()
  const [d, setD] = useState<Detail | null>(null)
  const [employees, setEmployees] = useState<BlEmployee[]>([])
  const [customers, setCustomers] = useState<BlCustomer[]>([])
  const [products, setProducts] = useState<BlProduct[]>([])
  const [error, setError] = useState<unknown>(null)
  const [edit, setEdit] = useState(false)
  const [link, setLink] = useState<{ url: string; token: string } | null>(null)
  const [editing, setEditing] = useState<BlTimeEntry | null>(null)
  const load = useCallback(() => api.get<Detail>(`/billing/tickets/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!d) return
    const ws = `?workspace_id=${d.ticket.workspace_id}`
    Promise.all([api.get<BlEmployee[]>(`/billing/employees${ws}`), api.get<BlCustomer[]>(`/billing/customers${ws}`), api.get<BlProduct[]>(`/billing/products${ws}`)]).then(([e, c, p]) => { setEmployees(e); setCustomers(c); setProducts(p) }).catch(setError)
  }, [d?.ticket.workspace_id])
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const t = d.ticket

  async function setStatus(status: string) { try { await api.patch(`/billing/tickets/${id}`, { status }); load() } catch (err) { setError(err) } }
  async function addTime(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { employee_id: fd.get('employee_id') || null, description: fd.get('description'), minutes: Number(fd.get('minutes') || 0), entry_date: fd.get('entry_date') }
    try { if (editing) await api.patch(`/billing/time/${editing.id}`, body); else await api.post(`/billing/tickets/${id}/time`, body); setEditing(null); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function removeTime(teId: string) { if (!confirm('למחוק את רישום הזמן?')) return; try { await api.del(`/billing/time/${teId}`); load() } catch (err) { setError(err) } }
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      await api.patch(`/billing/tickets/${id}`, { title: fd.get('title'), description: fd.get('description'), customer_id: fd.get('customer_id'), product_id: String(fd.get('product_id') ?? ''), employee_id: String(fd.get('employee_id') ?? ''), priority: fd.get('priority'), status: fd.get('status'), contact_person: fd.get('contact_person'), contact_phone: fd.get('contact_phone'), group_name: fd.get('group_name'), image_url: fd.get('image_url'), opened_at: fd.get('opened_at') ? new Date(String(fd.get('opened_at'))).toISOString() : undefined })
      setEdit(false); load()
    } catch (err) { setError(err) }
  }
  async function remove() { if (!confirm('למחוק את הקריאה וכל רישומי הזמן שלה?')) return; try { await api.del(`/billing/tickets/${id}`); window.location.href = '/billing/tickets' } catch (err) { setError(err) } }
  async function makeLink() { try { setLink(await api.post<{ url: string; token: string }>(`/billing/tickets/${id}/external-link`)) } catch (err) { setError(err) } }
  const linkUrl = link ? (link.url.startsWith('http') ? link.url : `${window.location.origin}/u/${link.token}`) : ''
  const waText = link ? `שלום ${t.contact_person || ''}, לעדכון על הטיפול בקריאה ${t.number_label} (${t.title}) אפשר להיכנס לקישור: ${linkUrl}` : ''
  const total = d.time_entries.reduce((a, e) => a + e.minutes, 0)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to="/billing/tickets" className="text-xs text-indigo-600">← לכל הקריאות</Link>
          <h1 className="flex flex-wrap items-center gap-2 text-xl font-bold"><span className="ltr text-slate-400">{t.number_label}</span> {t.title} <span className={`badge ${ticketStatusTone[t.status]}`}>{ticketStatus[t.status]}</span><span className={`badge ${priorityTone[t.priority]}`}>{ticketPriority[t.priority]}</span></h1>
          <p className="text-sm text-slate-500"><Link to={`/billing/customers/${t.customer_id}`} className="text-indigo-700">{t.customer_name}</Link>{t.product_name ? ` · ${t.product_name}` : ''}{t.contact_person ? ` · ${t.contact_person}` : ''}{t.contact_phone ? ` · ${t.contact_phone}` : ''}{t.group_name ? ` · ${t.group_name}` : ''} · נפתחה {fmtDate(t.opened_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {t.status !== 'resolved' && t.status !== 'closed' && <button className="btn-secondary" onClick={() => setStatus('resolved')}>סמן כנפתרה</button>}
          {t.status !== 'closed' && <button className="btn-secondary" onClick={() => setStatus('closed')}>סגור</button>}
          {(t.status === 'resolved' || t.status === 'closed') && <button className="btn-secondary" onClick={() => setStatus('in_progress')}>פתח מחדש</button>}
          <button className="btn-secondary" onClick={() => setEdit(v => !v)}>עריכה</button>
          <button className="btn-danger" onClick={remove}><Trash2 className="h-4 w-4" /></button>
        </div>
      </div>
      <ErrorBox error={error} />
      {t.description && <Card><p className="whitespace-pre-wrap text-sm text-slate-700">{t.description}</p>{t.image_url && <a href={t.image_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs text-indigo-600">תמונה מצורפת ↗</a>}</Card>}
      {edit && (
        <Card title="עריכת קריאה">
          <form onSubmit={save} className="grid gap-3 md:grid-cols-4">
            <Field label="כותרת"><input className="input" name="title" defaultValue={t.title} required /></Field>
            <Field label="לקוח"><select className="input" name="customer_id" defaultValue={t.customer_id}>{customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="מוצר"><select className="input" name="product_id" defaultValue={t.product_id ?? ''}><option value="">ללא</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="מטפל"><select className="input" name="employee_id" defaultValue={t.employee_id ?? ''}><option value="">לא שויך</option>{employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></Field>
            <Field label="סטטוס"><select className="input" name="status" defaultValue={t.status}>{Object.entries(ticketStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="עדיפות"><select className="input" name="priority" defaultValue={t.priority}>{Object.entries(ticketPriority).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="איש קשר"><input className="input" name="contact_person" defaultValue={t.contact_person} /></Field>
            <Field label="טלפון"><input className="input ltr" name="contact_phone" defaultValue={t.contact_phone} /></Field>
            <Field label="קבוצה"><input className="input" name="group_name" defaultValue={t.group_name} /></Field>
            <Field label="תאריך פתיחה"><input className="input ltr" name="opened_at" type="datetime-local" defaultValue={t.opened_at ? new Date(new Date(t.opened_at).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''} /></Field>
            <Field label="קישור לתמונה"><input className="input ltr" name="image_url" defaultValue={t.image_url} /></Field>
            <Field label="תיאור"><textarea className="input" name="description" rows={2} defaultValue={t.description} /></Field>
            <div className="md:col-span-4"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="סה״כ זמן טיפול" value={hhmm(total)} hint={`${d.time_entries.length} רישומים`} />
        <Stat label="מטפל" value={t.employee_name || '—'} />
        <Stat label="עדכונים מהלקוח" value={d.external_updates.length} />
        <Stat label="חויב" value={d.time_entries.some(e => e.billed_charge_id) ? 'חלקית / כן' : 'טרם'} tone={d.time_entries.some(e => e.billed_charge_id) ? 'emerald' : 'slate'} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="רישומי זמן" className="lg:col-span-2">
          {d.time_entries.length === 0 ? <Empty>אין רישומי זמן. הוסף מהטופס.</Empty> : (
            <Table head={['תאריך', 'מטפל', 'תיאור', 'זמן', '']}>
              {d.time_entries.map(e => (
                <tr key={e.id}>
                  <td className="px-3 py-2 text-xs ltr">{String(e.entry_date).slice(0, 10)}</td>
                  <td className="px-3 py-2 text-sm">{e.employee_name || '—'}</td>
                  <td className="px-3 py-2 text-sm">{e.description}{e.billed_charge_id && <Link to={`/billing/charges/${e.billed_charge_id}`} className="badge mr-2 bg-emerald-100 text-emerald-800">חויב</Link>}</td>
                  <td className="px-3 py-2 text-sm ltr">{hhmm(e.minutes)}</td>
                  <td className="px-3 py-2 text-xs">{!e.billed_charge_id && <div className="flex gap-2"><button className="text-indigo-700" onClick={() => setEditing(e)}>עריכה</button><button className="text-rose-700" onClick={() => removeTime(e.id)}>מחק</button></div>}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title={editing ? 'עריכת רישום' : 'רישום זמן'} actions={editing && <button className="text-xs text-slate-500" onClick={() => setEditing(null)}>ביטול</button>}>
          <form key={editing?.id ?? 'new'} onSubmit={addTime} className="space-y-3">
            <Field label="מטפל"><select className="input" name="employee_id" defaultValue={editing?.employee_id ?? t.employee_id ?? ''}><option value="">לא שויך</option>{employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="דקות"><input className="input ltr" name="minutes" type="number" min={0} step={5} defaultValue={editing?.minutes ?? 30} required /></Field>
              <Field label="תאריך"><input className="input ltr" name="entry_date" type="date" defaultValue={editing ? String(editing.entry_date).slice(0, 10) : today()} /></Field>
            </div>
            <Field label="תיאור הטיפול"><textarea className="input" name="description" rows={3} defaultValue={editing?.description ?? ''} placeholder="מה נעשה, אילו פעולות ננקטו" /></Field>
            <button className="btn-primary w-full justify-center">{editing ? 'שמירה' : 'הוסף רישום'}</button>
          </form>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="עדכונים מהלקוח" className="lg:col-span-2">
          {d.external_updates.length === 0 ? <Empty>הלקוח עדיין לא דיווח דרך הקישור החיצוני.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">{d.external_updates.map(u => <li key={u.id} className="py-2"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{u.contact_name}</span>{u.contact_phone && <span className="text-xs text-slate-500 ltr">{u.contact_phone}</span>}<span className="text-xs text-slate-400">{String(u.update_date).slice(0, 10)}</span>{u.minutes ? <span className="badge bg-sky-100 text-sky-800">{hhmm(u.minutes)}</span> : null}</div><div className="whitespace-pre-wrap text-slate-700">{u.content}</div></li>)}</ul>
          )}
        </Card>
        <Card title={<span className="flex items-center gap-2"><Link2 className="h-4 w-4 text-indigo-500" /> קישור עדכון ללקוח</span>}>
          <p className="mb-3 text-xs text-slate-500">קישור חתום, תקף 90 יום, שמאפשר ללקוח לדווח מה טופל ומתי בלי להתחבר.</p>
          {!link ? <button className="btn-primary w-full justify-center" onClick={makeLink}>צור קישור</button> : (
            <div className="space-y-2">
              <input className="input ltr text-xs" readOnly value={linkUrl} onFocus={e => e.currentTarget.select()} />
              <div className="flex gap-2">
                <button className="btn-secondary flex-1 justify-center" onClick={() => navigator.clipboard?.writeText(linkUrl)}><Copy className="h-4 w-4" /> העתק</button>
                <a className="btn flex-1 justify-center bg-[#25D366] text-white hover:opacity-90" href={`https://wa.me/${(t.contact_phone || '').replace(/\D/g, '').replace(/^0/, '972')}?text=${encodeURIComponent(waText)}`} target="_blank" rel="noopener noreferrer"><BrandIcon name="whatsapp" className="h-4 w-4" /> שלח בוואטסאפ</a>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
