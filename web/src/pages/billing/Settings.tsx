import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { today, type BlSettings } from './types'

interface Fx { id: string; currency: string; rate_date: string; rate: number | string }

export default function BlSettingsPage() {
  const { workspaces, current, loading } = useWorkspace()
  const [s, setS] = useState<BlSettings | null>(null)
  const [fx, setFx] = useState<Fx[]>([])
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlSettings>(`/billing/settings?workspace_id=${ws}`), api.get<Fx[]>('/billing/fx')]).then(([a, b]) => { setS(a); setFx(b) }).catch(setError)
  useEffect(() => { if (ws) load() }, [ws])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      await api.put(`/billing/settings?workspace_id=${ws}`, { vat_pct: Number(fd.get('vat_pct')), hourly_rate: Number(fd.get('hourly_rate')), ticket_prefix: fd.get('ticket_prefix'), fx_defaults: { USD: Number(fd.get('usd')), EUR: Number(fd.get('eur')) },
        business: { name: fd.get('b_name'), address: fd.get('b_address'), vat_id: fd.get('b_vat'), phone: fd.get('b_phone'), email: fd.get('b_email') } })
      setNote('ההגדרות נשמרו.'); load()
    } catch (err) { setError(err) }
  }
  async function addFx(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post('/billing/fx', { currency: fd.get('currency'), rate_date: fd.get('rate_date'), rate: Number(fd.get('rate')) }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">הגדרות חיוב</h1><p className="text-sm text-slate-500">מע"מ, תעריף שעה ברירת מחדל, פרטי העסק שמודפסים בחיוב, ושערי מטבע להמרת הוצאות. ההגדרות הן לכל מרחב ({current?.name ?? workspaces[0]?.name}).</p></div>
      <ErrorBox error={error} />
      {note && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}
      {!s ? <Spinner /> : (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="חיוב" className="lg:col-span-2">
            <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
              <Field label="מע״מ %"><input className="input ltr" name="vat_pct" type="number" step="0.5" min={0} max={100} defaultValue={s.vat_pct} /></Field>
              <Field label="תעריף שעה ברירת מחדל (₪)" hint="כשאין תעריף ללקוח או לעובד"><input className="input ltr" name="hourly_rate" type="number" step="0.01" min={0} defaultValue={s.hourly_rate} /></Field>
              <Field label="קידומת מספר קריאה"><input className="input ltr" name="ticket_prefix" defaultValue={s.ticket_prefix} maxLength={10} /></Field>
              <Field label="שער ברירת מחדל USD"><input className="input ltr" name="usd" type="number" step="0.0001" defaultValue={s.fx_defaults.USD} /></Field>
              <Field label="שער ברירת מחדל EUR"><input className="input ltr" name="eur" type="number" step="0.0001" defaultValue={s.fx_defaults.EUR} /></Field>
              <div className="md:col-span-3 mt-2 text-sm font-semibold text-slate-700">פרטי העסק (מודפסים בחיוב ובדוחות)</div>
              <Field label="שם העסק"><input className="input" name="b_name" defaultValue={s.business.name ?? ''} /></Field>
              <Field label="ח.פ. / ע.מ."><input className="input ltr" name="b_vat" defaultValue={s.business.vat_id ?? ''} /></Field>
              <Field label="טלפון"><input className="input ltr" name="b_phone" defaultValue={s.business.phone ?? ''} /></Field>
              <Field label="אימייל"><input className="input ltr" name="b_email" defaultValue={s.business.email ?? ''} /></Field>
              <Field label="כתובת"><input className="input" name="b_address" defaultValue={s.business.address ?? ''} /></Field>
              <div className="md:col-span-3"><button className="btn-primary">שמירה</button></div>
            </form>
          </Card>
          <Card title="שערי מטבע">
            <form onSubmit={addFx} className="mb-3 grid grid-cols-3 gap-2">
              <Field label="מטבע"><select className="input" name="currency"><option>USD</option><option>EUR</option></select></Field>
              <Field label="תאריך"><input className="input ltr" name="rate_date" type="date" defaultValue={today()} /></Field>
              <Field label="שער"><input className="input ltr" name="rate" type="number" step="0.0001" required /></Field>
              <div className="col-span-3"><button className="btn-secondary w-full justify-center">הוסף שער</button></div>
            </form>
            {fx.length === 0 ? <Empty>אין שערים. עד שיוזנו, ההמרה לפי ברירת המחדל.</Empty> : (
              <Table head={['תאריך', 'מטבע', 'שער']}>{fx.slice(0, 20).map(r => <tr key={r.id}><td className="px-3 py-1.5 text-xs ltr">{String(r.rate_date).slice(0, 10)}</td><td className="px-3 py-1.5 text-xs">{r.currency}</td><td className="px-3 py-1.5 text-xs ltr">{Number(r.rate)}</td></tr>)}</Table>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
