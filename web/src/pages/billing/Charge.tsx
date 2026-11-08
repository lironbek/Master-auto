import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { api, openPrint } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { fmtDate } from '../../i18n'
import { chargeStatus, chargeTone, ils, lineKind, periodLabel, type BlCharge, type BlChargeLine, type BlCustomer } from './types'

interface Detail { charge: BlCharge; lines: BlChargeLine[]; customer: BlCustomer }

export default function BlChargePage() {
  const { id } = useParams()
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const load = useCallback(() => api.get<Detail>(`/billing/charges/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const c = d.charge
  const draft = c.status === 'draft'
  async function setStatus(status: string) {
    const msg: Record<string, string> = { issued: 'להפיק את החיוב? שעות הטיפול שבו יינעלו.', paid: 'לסמן כשולם?', cancelled: 'לבטל את החיוב?', draft: 'להחזיר לטיוטה?' }
    if (!confirm(msg[status])) return
    try { await api.patch(`/billing/charges/${id}`, { status }); load() } catch (err) { setError(err) }
  }
  async function addLine(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post(`/billing/charges/${id}/lines`, { kind: 'manual', description: fd.get('description'), quantity: Number(fd.get('quantity') || 1), unit_price: Number(fd.get('unit_price') || 0) }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function removeLine(lineId: string) { try { await api.del(`/billing/charges/${id}/lines/${lineId}`); load() } catch (err) { setError(err) } }
  async function saveMeta(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.patch(`/billing/charges/${id}`, { notes: fd.get('notes'), vat_pct: Number(fd.get('vat_pct')) }); load() } catch (err) { setError(err) }
  }
  async function regenerate() {
    if (!confirm('לחשב מחדש את השורות האוטומטיות מהמנויים והשעות? שורות ידניות נשמרות.')) return
    try { await api.post('/billing/charges/generate', { workspace_id: c.workspace_id, period: c.period, customer_id: c.customer_id }); load() } catch (err) { setError(err) }
  }
  async function remove() { if (!confirm('למחוק את הטיוטה?')) return; try { await api.del(`/billing/charges/${id}`); window.location.href = '/billing/charges' } catch (err) { setError(err) } }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to="/billing/charges" className="text-xs text-indigo-600">← לכל החיובים</Link>
          <h1 className="flex flex-wrap items-center gap-2 text-xl font-bold">חיוב {periodLabel(c.period)} · <Link to={`/billing/customers/${c.customer_id}`} className="text-indigo-700">{d.customer.name}</Link> <span className={`badge ${chargeTone[c.status]}`}>{chargeStatus[c.status]}</span></h1>
          <p className="text-sm text-slate-500">{c.source === 'auto' ? 'נוצר אוטומטית מהמנויים' : c.source === 'import' ? 'יובא מהמערכת הישנה' : 'חיוב ידני'}{c.issued_at ? ` · הופק ${fmtDate(c.issued_at)}` : ''}{c.paid_at ? ` · שולם ${fmtDate(c.paid_at)}` : ''}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={() => openPrint(`/billing/charges/${id}/print`)}><Printer className="h-4 w-4" /> הדפסה / PDF</button>
          {draft && <button className="btn-secondary" onClick={regenerate}>חשב מחדש</button>}
          {draft && <button className="btn-primary" onClick={() => setStatus('issued')}>הפק</button>}
          {c.status === 'issued' && <button className="btn-primary" onClick={() => setStatus('paid')}>סמן כשולם</button>}
          {c.status === 'paid' && <button className="btn-secondary" onClick={() => setStatus('issued')}>בטל סימון תשלום</button>}
          {c.status !== 'cancelled' && !draft && <button className="btn-secondary" onClick={() => setStatus('cancelled')}>בטל חיוב</button>}
          {(c.status === 'cancelled' || c.status === 'issued') && <button className="btn-secondary" onClick={() => setStatus('draft')}>החזר לטיוטה</button>}
          {(draft || c.status === 'cancelled') && <button className="btn-danger" onClick={remove}>מחק</button>}
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="לפני מע״מ" value={ils(c.subtotal)} />
        <Stat label={`מע״מ ${Number(c.vat_pct)}%`} value={ils(c.vat)} />
        <Stat label="סה״כ לתשלום" value={ils(c.total)} tone="indigo" />
        <Stat label="שורות" value={d.lines.length} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="שורות החיוב" className="lg:col-span-2">
          {d.lines.length === 0 ? <Empty>אין שורות. הוסף שורה ידנית או חשב מחדש מהמנויים.</Empty> : (
            <Table head={['סוג', 'תיאור', 'כמות', 'מחיר יחידה', 'סה"כ', '']}>
              {d.lines.map(l => (
                <tr key={l.id}>
                  <td className="px-3 py-2"><span className="badge bg-slate-100 text-slate-700">{lineKind[l.kind] ?? l.kind}</span></td>
                  <td className="px-3 py-2 text-sm">{l.description}</td>
                  <td className="px-3 py-2 text-sm ltr">{Number(l.quantity)}</td>
                  <td className="px-3 py-2 text-sm"><bdi>{ils(l.unit_price)}</bdi></td>
                  <td className="px-3 py-2 font-semibold"><bdi>{ils(l.total)}</bdi></td>
                  <td className="px-3 py-2 text-xs">{draft && <button className="text-rose-700" onClick={() => removeLine(l.id)}>הסר</button>}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <div className="space-y-4">
          {draft && (
            <Card title="שורה ידנית">
              <form onSubmit={addLine} className="space-y-3">
                <Field label="תיאור"><input className="input" name="description" required placeholder="הנחה / תוספת / עבודה מיוחדת" /></Field>
                <div className="grid grid-cols-2 gap-2"><Field label="כמות"><input className="input ltr" name="quantity" type="number" step="0.5" defaultValue={1} /></Field><Field label="מחיר יחידה" hint="שלילי = הנחה"><input className="input ltr" name="unit_price" type="number" step="0.01" defaultValue={0} /></Field></div>
                <button className="btn-primary w-full justify-center">הוספה</button>
              </form>
            </Card>
          )}
          <Card title="פרטים">
            <form onSubmit={saveMeta} className="space-y-3">
              <Field label="מע״מ %"><input className="input ltr" name="vat_pct" type="number" step="0.5" min={0} max={100} defaultValue={Number(c.vat_pct)} disabled={!draft} /></Field>
              <Field label="הערות (מודפסות בחיוב)"><textarea className="input" name="notes" rows={3} defaultValue={c.notes ?? ''} /></Field>
              <button className="btn-secondary w-full justify-center">שמירה</button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
