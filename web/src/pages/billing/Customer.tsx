import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { fmtDate, metricLabel, qty, t, usageProvider } from '../../i18n'
import { BrandTile } from '../../components/brand'
import { chargeStatus, chargeTone, customerStatus, hhmm, ils, periodLabel, ticketStatus, ticketStatusTone, type BlCustomerDetail, type BlProduct, type BlService } from './types'

type Tab = 'subs' | 'tickets' | 'charges' | 'usage' | 'edit'

export default function BlCustomer() {
  const { id } = useParams()
  const [d, setD] = useState<BlCustomerDetail | null>(null)
  const [products, setProducts] = useState<BlProduct[]>([])
  const [services, setServices] = useState<BlService[]>([])
  const [error, setError] = useState<unknown>(null)
  const [tab, setTab] = useState<Tab>('subs')
  const [kind, setKind] = useState<'product' | 'service'>('product')
  const load = useCallback(() => api.get<BlCustomerDetail>(`/billing/customers/${id}/detail`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!d) return
    const ws = `?workspace_id=${d.customer.workspace_id}`
    Promise.all([api.get<BlProduct[]>(`/billing/products${ws}`), api.get<BlService[]>(`/billing/services${ws}`)]).then(([p, s]) => { setProducts(p); setServices(s) }).catch(setError)
  }, [d?.customer.workspace_id])
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const c = d.customer

  async function addSub(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body: Record<string, unknown> = { customer_id: id, kind, valid_from: fd.get('valid_from') || undefined, valid_until: fd.get('valid_until') || undefined }
    if (kind === 'product') { body.product_id = fd.get('product_id'); body.user_count = Number(fd.get('user_count') || 0); body.light_user_count = Number(fd.get('light_user_count') || 0) }
    else { body.service_id = fd.get('service_id'); body.quantity = Number(fd.get('quantity') || 1) }
    try { await api.post('/billing/subscriptions', body); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function endSub(subId: string) {
    try { await api.patch(`/billing/subscriptions/${subId}`, { valid_until: new Date().toISOString().slice(0, 10) }); load() } catch (err) { setError(err) }
  }
  async function removeSub(subId: string) {
    if (!confirm('למחוק את המנוי? אם כבר חויב, עדיף לסיים אותו עם תאריך.')) return
    try { await api.del(`/billing/subscriptions/${subId}`); load() } catch (err) { setError(err) }
  }
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      await api.patch(`/billing/customers/${id}`, { name: fd.get('name'), contact_person: fd.get('contact_person'), email: fd.get('email'), phone: fd.get('phone'), address: fd.get('address'), status: fd.get('status'), payment_method: fd.get('payment_method'), vat_id: fd.get('vat_id'), notes: fd.get('notes'), bill_hours: fd.get('bill_hours') === 'on', hourly_rate: fd.get('hourly_rate') ? Number(fd.get('hourly_rate')) : undefined })
      setTab('subs'); load()
    } catch (err) { setError(err) }
  }
  async function generate() {
    try { const r = await api.post<{ created: number; updated: number }>('/billing/charges/generate', { workspace_id: c.workspace_id, period: new Date().toISOString().slice(0, 7), customer_id: id }); alert(`נוצרו ${r.created}, עודכנו ${r.updated} חיובים לחודש הנוכחי`); load() } catch (err) { setError(err) }
  }
  const live = d.subscriptions.filter(s => !s.valid_until || s.valid_until >= new Date().toISOString().slice(0, 10))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to="/billing/customers" className="text-xs text-indigo-600">← לכל הלקוחות</Link>
          <h1 className="flex items-center gap-3 text-xl font-bold">{c.name} <span className="badge bg-slate-100 text-slate-700">{customerStatus[c.status] ?? c.status}</span>{c.bill_hours && <span className="badge bg-sky-100 text-sky-800">חיוב לפי שעות</span>}</h1>
          <p className="text-sm text-slate-500">{c.contact_person}{c.phone ? ` · ${c.phone}` : ''}{c.email ? ` · ${c.email}` : ''}{c.address ? ` · ${c.address}` : ''}</p>
        </div>
        <div className="flex gap-2"><Link to={`/billing/tickets?new=1&customer=${c.id}`} className="btn-secondary">קריאה חדשה</Link><button className="btn-primary" onClick={generate}>הפק חיוב לחודש הנוכחי</button></div>
      </div>
      <ErrorBox error={error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="משתמשים פעילים" value={live.filter(s => s.kind === 'product').reduce((a, s) => a + s.user_count, 0)} hint={`${live.length} מנויים`} />
        <Stat label="קריאות פתוחות" value={c.open_tickets ?? 0} tone={c.open_tickets ? 'amber' : 'slate'} />
        <Stat label="שעות טיפול החודש" value={hhmm(d.hours_month)} />
        <Stat label="ממתין לתשלום" value={ils(c.unpaid)} tone={c.unpaid ? 'rose' : 'slate'} />
      </div>
      <div className="flex flex-wrap gap-2">{([['subs', 'מנויים'], ['tickets', 'קריאות'], ['charges', 'חיובים'], ['usage', 'שימוש API'], ['edit', 'עריכה']] as [Tab, string][]).map(([k, l]) => <button key={k} className={`btn-secondary ${tab === k ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab(k)}>{l}</button>)}</div>

      {tab === 'subs' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="מנויים" className="lg:col-span-2">
            {d.subscriptions.length === 0 ? <Empty>אין מנויים. הוסף מוצר או שירות מהטופס.</Empty> : (
              <Table head={['מוצר / שירות', 'משתמשים', 'Light / כמות', 'מתאריך', 'עד תאריך', '']}>
                {d.subscriptions.map(s => (
                  <tr key={s.id} className={s.valid_until && s.valid_until < new Date().toISOString().slice(0, 10) ? 'opacity-50' : ''}>
                    <td className="px-3 py-2 font-medium">{s.kind === 'product' ? s.product_name : s.service_name}<div className="text-xs text-slate-500">{s.kind === 'product' ? 'מוצר' : 'שירות'}</div></td>
                    <td className="px-3 py-2 text-sm">{s.kind === 'product' ? s.user_count : '—'}</td>
                    <td className="px-3 py-2 text-sm">{s.kind === 'product' ? s.light_user_count : Number(s.quantity)}</td>
                    <td className="px-3 py-2 text-xs ltr">{String(s.valid_from).slice(0, 10)}</td>
                    <td className="px-3 py-2 text-xs ltr">{s.valid_until ? String(s.valid_until).slice(0, 10) : 'פעיל'}</td>
                    <td className="px-3 py-2 text-xs"><div className="flex gap-2">{!s.valid_until && <button className="text-amber-700" onClick={() => endSub(s.id)}>סיים היום</button>}<button className="text-rose-700" onClick={() => removeSub(s.id)}>מחק</button></div></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="הוספת מנוי">
            <form onSubmit={addSub} className="space-y-3">
              <div className="flex gap-2">{(['product', 'service'] as const).map(k => <button type="button" key={k} className={`btn-secondary flex-1 ${kind === k ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setKind(k)}>{k === 'product' ? 'מוצר' : 'שירות'}</button>)}</div>
              {kind === 'product' ? (
                <>
                  <Field label="מוצר"><select className="input" name="product_id" required>{products.map(p => <option key={p.id} value={p.id}>{p.name} · {ils(p.price)} למשתמש</option>)}</select></Field>
                  <div className="grid grid-cols-2 gap-2"><Field label="משתמשים"><input className="input ltr" name="user_count" type="number" min={0} defaultValue={1} /></Field><Field label="משתמשי Light"><input className="input ltr" name="light_user_count" type="number" min={0} defaultValue={0} /></Field></div>
                </>
              ) : (
                <>
                  <Field label="שירות"><select className="input" name="service_id" required>{services.map(s => <option key={s.id} value={s.id}>{s.description} · {ils(s.price)}{s.recurring ? ' / חודש' : ' חד-פעמי'}</option>)}</select></Field>
                  <Field label="כמות"><input className="input ltr" name="quantity" type="number" min={0} step="0.5" defaultValue={1} /></Field>
                </>
              )}
              <div className="grid grid-cols-2 gap-2"><Field label="מתאריך"><input className="input ltr" name="valid_from" type="date" defaultValue={new Date().toISOString().slice(0, 10)} /></Field><Field label="עד (אופציונלי)"><input className="input ltr" name="valid_until" type="date" /></Field></div>
              <button className="btn-primary w-full justify-center" disabled={kind === 'product' ? products.length === 0 : services.length === 0}>הוספה</button>
              {(kind === 'product' ? products.length === 0 : services.length === 0) && <p className="text-xs text-slate-500">אין {kind === 'product' ? 'מוצרים' : 'שירותים'} במרחב. <Link to="/billing/catalog" className="text-indigo-600">הוסף בקטלוג</Link>.</p>}
            </form>
          </Card>
        </div>
      )}

      {tab === 'tickets' && (
        <Card title="קריאות שירות">
          {d.tickets.length === 0 ? <Empty>אין קריאות ללקוח.</Empty> : (
            <Table head={['מספר', 'כותרת', 'מטפל', 'סטטוס', 'נפתחה']}>
              {d.tickets.map(tk => <tr key={tk.id}><td className="px-3 py-2 text-xs ltr">{tk.number_label ?? tk.number}</td><td className="px-3 py-2"><Link to={`/billing/tickets/${tk.id}`} className="font-medium text-indigo-700">{tk.title}</Link></td><td className="px-3 py-2 text-sm">{tk.employee_name || '—'}</td><td className="px-3 py-2"><span className={`badge ${ticketStatusTone[tk.status]}`}>{ticketStatus[tk.status] ?? tk.status}</span></td><td className="px-3 py-2 text-xs">{fmtDate(tk.opened_at)}</td></tr>)}
            </Table>
          )}
        </Card>
      )}

      {tab === 'charges' && (
        <Card title="חיובים">
          {d.charges.length === 0 ? <Empty>אין חיובים. "הפק חיוב לחודש הנוכחי" יוצר טיוטה מהמנויים.</Empty> : (
            <Table head={['תקופה', 'סטטוס', 'לפני מע"מ', 'סה"כ', 'הופק', 'שולם']}>
              {d.charges.map(ch => <tr key={ch.id}><td className="px-3 py-2"><Link to={`/billing/charges/${ch.id}`} className="font-medium text-indigo-700">{periodLabel(ch.period)}</Link></td><td className="px-3 py-2"><span className={`badge ${chargeTone[ch.status]}`}>{chargeStatus[ch.status]}</span></td><td className="px-3 py-2 text-sm"><bdi>{ils(ch.subtotal)}</bdi></td><td className="px-3 py-2 font-semibold"><bdi>{ils(ch.total)}</bdi></td><td className="px-3 py-2 text-xs">{ch.issued_at ? fmtDate(ch.issued_at) : '—'}</td><td className="px-3 py-2 text-xs">{ch.paid_at ? fmtDate(ch.paid_at) : '—'}</td></tr>)}
            </Table>
          )}
        </Card>
      )}

      {tab === 'usage' && (
        <Card title="שימוש ב-API החודש" actions={<Link to="/usage" className="text-xs text-indigo-600">דוח שימוש מלא</Link>}>
          {!d.usage_month ? <Empty>הלקוח לא מקושר ללקוח במדידת השימוש.</Empty> : d.usage_month.by_provider.length === 0 ? <Empty>אין דיווחי שימוש החודש.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">{d.usage_month.by_provider.map(p => <li key={p.provider} className="flex flex-wrap items-center gap-2 py-2"><BrandTile name={p.provider} size="sm" /> <span className="w-24 font-medium">{t(usageProvider, p.provider)}</span>{Object.entries(p.metrics).map(([k, v]) => <span key={k} className="badge bg-slate-100 text-slate-700"><bdi>{qty(v)}</bdi> {t(metricLabel, k)}</span>)}</li>)}</ul>
          )}
        </Card>
      )}

      {tab === 'edit' && (
        <Card title="עריכת לקוח">
          <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
            <Field label="שם"><input className="input" name="name" defaultValue={c.name} required /></Field>
            <Field label="איש קשר"><input className="input" name="contact_person" defaultValue={c.contact_person} /></Field>
            <Field label="אימייל"><input className="input ltr" name="email" defaultValue={c.email} /></Field>
            <Field label="טלפון"><input className="input ltr" name="phone" defaultValue={c.phone} /></Field>
            <Field label="כתובת"><input className="input" name="address" defaultValue={c.address} /></Field>
            <Field label="סטטוס"><select className="input" name="status" defaultValue={c.status}>{Object.entries(customerStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="אמצעי תשלום"><input className="input" name="payment_method" defaultValue={c.payment_method ?? ''} /></Field>
            <Field label="ח.פ. / ע.מ."><input className="input ltr" name="vat_id" defaultValue={c.vat_id ?? ''} /></Field>
            <Field label="תעריף שעה (₪)" hint="ריק = תעריף העובד או ברירת המחדל"><input className="input ltr" name="hourly_rate" type="number" min={0} step="0.01" defaultValue={c.hourly_rate ?? ''} /></Field>
            <label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" name="bill_hours" defaultChecked={c.bill_hours} /> לחייב שעות טיפול אוטומטית בחיוב החודשי</label>
            <Field label="הערות"><textarea className="input" name="notes" rows={2} defaultValue={c.notes ?? ''} /></Field>
            <div className="md:col-span-3"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}
    </div>
  )
}
