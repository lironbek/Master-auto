import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, Plus, Wand2 } from 'lucide-react'
import { api, download } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtDate } from '../../i18n'
import { useWorkspace } from '../../workspace'
import { chargeStatus, chargeTone, currentPeriod, ils, periodLabel, type BlCharge, type BlCustomer } from './types'

export default function BlCharges() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<BlCharge[] | null>(null)
  const [customers, setCustomers] = useState<BlCustomer[]>([])
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')
  const [period, setPeriod] = useState(currentPeriod())
  const [manual, setManual] = useState(false)
  const status = params.get('status') ?? ''
  const filterPeriod = params.get('period') ?? ''
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlCharge[]>(`/billing/charges${qs}`), api.get<BlCustomer[]>(`/billing/customers${qs}`)]).then(([c, cu]) => { setItems(c); setCustomers(cu) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const setParam = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p) }
  async function generate() {
    if (!ws) return
    if (!confirm(`להפיק טיוטות חיוב לכל הלקוחות ל${periodLabel(period)}? חיובים שכבר הופקו לא ישתנו.`)) return
    try { const r = await api.post<{ created: number; updated: number; skipped_non_draft: number }>('/billing/charges/generate', { workspace_id: ws, period }); setNote(`נוצרו ${r.created} טיוטות, עודכנו ${r.updated}, ${r.skipped_non_draft} חיובים שכבר הופקו לא נגעו בהם.`); setError(null); setParam('period', period); load() } catch (err) { setError(err) }
  }
  async function createManual(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      const c = await api.post<BlCharge>('/billing/charges', { workspace_id: ws, customer_id: fd.get('customer_id'), period: fd.get('period'), notes: fd.get('notes'), lines: fd.get('description') ? [{ kind: 'manual', description: fd.get('description'), quantity: Number(fd.get('quantity') || 1), unit_price: Number(fd.get('unit_price') || 0) }] : [] })
      window.location.href = `/billing/charges/${c.id}`
    } catch (err) { setError(err) }
  }
  const periods = Array.from(new Set((items ?? []).map(c => c.period))).sort().reverse()
  const shown = (items ?? []).filter(c => (!status || c.status === status) && (!filterPeriod || c.period === filterPeriod))
  const sum = (f: (c: BlCharge) => boolean) => shown.filter(f).reduce((a, c) => a + Number(c.total), 0)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">חיובים</h1><p className="text-sm text-slate-500">הפקה חודשית מתוך המנויים, השירותים ושעות הטיפול. טיוטה אפשר לערוך, להוסיף שורות ואז להפיק, לסמן כשולם ולהדפיס.</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <input className="input w-36 ltr" type="month" value={period} onChange={e => setPeriod(e.target.value)} aria-label="תקופה להפקה" />
          <button className="btn-primary" onClick={generate} disabled={!ws}><Wand2 className="h-4 w-4" /> הפק טיוטות ל{periodLabel(period)}</button>
          <button className="btn-secondary" onClick={() => setManual(v => !v)}><Plus className="h-4 w-4" /> חיוב ידני</button>
          <button className="btn-secondary" onClick={() => ws && download(`/billing/exports/charges.xlsx?workspace_id=${ws}${filterPeriod ? `&period=${filterPeriod}` : ''}`, `charges_${filterPeriod || 'all'}.xlsx`)}><Download className="h-4 w-4" /> אקסל</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {note && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}
      {manual && (
        <Card title="חיוב ידני">
          <form onSubmit={createManual} className="grid gap-3 md:grid-cols-6">
            <Field label="לקוח"><select className="input" name="customer_id" required>{customers.filter(c => c.status !== 'closed').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="תקופה"><input className="input ltr" type="month" name="period" defaultValue={period} required /></Field>
            <Field label="שורה (אופציונלי)"><input className="input" name="description" placeholder="תיאור" /></Field>
            <Field label="כמות"><input className="input ltr" name="quantity" type="number" step="0.5" defaultValue={1} /></Field>
            <Field label="מחיר יחידה"><input className="input ltr" name="unit_price" type="number" step="0.01" defaultValue={0} /></Field>
            <div className="flex items-end"><button className="btn-primary">יצירת טיוטה</button></div>
            <Field label="הערות"><input className="input" name="notes" /></Field>
          </form>
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="טיוטות" value={shown.filter(c => c.status === 'draft').length} hint={ils(sum(c => c.status === 'draft'))} />
        <Stat label="הופקו, ממתינים לתשלום" value={shown.filter(c => c.status === 'issued').length} hint={ils(sum(c => c.status === 'issued'))} tone="amber" />
        <Stat label="שולמו" value={shown.filter(c => c.status === 'paid').length} hint={ils(sum(c => c.status === 'paid'))} tone="emerald" />
        <Stat label="סה״כ בסינון" value={ils(sum(c => c.status !== 'cancelled'))} />
      </div>
      <div className="flex flex-wrap gap-3">
        <select className="input w-44" value={filterPeriod} onChange={e => setParam('period', e.target.value)} aria-label="תקופה"><option value="">כל התקופות</option>{periods.map(p => <option key={p} value={p}>{periodLabel(p)}</option>)}</select>
        <div className="flex gap-1">{[['', 'הכול'], ['draft', 'טיוטות'], ['issued', 'הופקו'], ['paid', 'שולמו'], ['cancelled', 'בוטלו']].map(([k, l]) => <button key={k} className={`rounded-lg px-3 py-1.5 text-xs ${status === k ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'}`} onClick={() => setParam('status', k)}>{l}</button>)}</div>
      </div>
      <Card>
        {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין חיובים בסינון. "הפק טיוטות" יוצר חיוב לכל לקוח עם מנויים פעילים.</Empty> : (
          <Table head={['לקוח', 'תקופה', 'סטטוס', 'שורות', 'לפני מע"מ', 'סה"כ', 'הופק', 'שולם']}>
            {shown.map(c => (
              <tr key={c.id}>
                <td className="px-3 py-2"><Link to={`/billing/charges/${c.id}`} className="font-medium text-indigo-700">{c.customer_name}</Link></td>
                <td className="px-3 py-2 text-sm">{periodLabel(c.period)}</td>
                <td className="px-3 py-2"><span className={`badge ${chargeTone[c.status]}`}>{chargeStatus[c.status]}</span></td>
                <td className="px-3 py-2 text-sm">{c.lines ?? 0}</td>
                <td className="px-3 py-2 text-sm"><bdi>{ils(c.subtotal)}</bdi></td>
                <td className="px-3 py-2 font-semibold"><bdi>{ils(c.total)}</bdi></td>
                <td className="px-3 py-2 text-xs">{c.issued_at ? fmtDate(c.issued_at) : '—'}</td>
                <td className="px-3 py-2 text-xs">{c.paid_at ? fmtDate(c.paid_at) : '—'}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
