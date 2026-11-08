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
  const [imp, setImp] = useState<{ fetched: Record<string, number>; report: Record<string, { inserted: number; skipped: number; errors: number }> | null } | null>(null)
  const [impBusy, setImpBusy] = useState(false)
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
  async function importLegacy(e: FormEvent, dry: boolean) {
    e.preventDefault(); const fd = new FormData((e.target as HTMLElement).closest('form') as HTMLFormElement); setImpBusy(true)
    try {
      const r = await api.post<{ fetched: Record<string, number>; report: Record<string, { inserted: number; skipped: number; errors: number }> | null }>('/billing/import/supabase',
        { workspace_id: ws, supabase_url: fd.get('supabase_url'), anon_key: fd.get('anon_key'), email: fd.get('email'), password: fd.get('password'), dry_run: dry })
      setImp(r); setError(null)
    } catch (err) { setError(err) } finally { setImpBusy(false) }
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
      <Card title="ייבוא מהמערכת הישנה (Lovable + Supabase)">
        <p className="mb-3 text-sm text-slate-500">כתובת הפרויקט ומפתח ה-anon נמצאים בקוד האפליקציה הישנה (src/integrations/supabase/client.ts). ההתחברות היא במשתמש שלך במערכת הישנה. הפרטים לא נשמרים; אפשר להריץ שוב בכל עת ורק שורות חדשות ייכנסו.</p>
        <form onSubmit={e => importLegacy(e, false)} className="grid gap-3 md:grid-cols-4">
          <Field label="כתובת Supabase"><input className="input ltr" name="supabase_url" placeholder="https://xxxx.supabase.co" required /></Field>
          <Field label="מפתח anon"><input className="input ltr" name="anon_key" required /></Field>
          <Field label="אימייל במערכת הישנה"><input className="input ltr" name="email" type="email" required /></Field>
          <Field label="סיסמה"><input className="input ltr" name="password" type="password" required /></Field>
          <div className="md:col-span-4 flex gap-2">
            <button type="button" className="btn-secondary" disabled={impBusy} onClick={e => importLegacy(e as unknown as FormEvent, true)}>בדיקה (ספירה בלבד)</button>
            <button className="btn-primary" disabled={impBusy}>{impBusy ? 'מייבא…' : 'ייבוא'}</button>
          </div>
        </form>
        {imp && (
          <Table head={['טבלה', 'נמצאו במקור', 'נוספו', 'דולגו (כבר קיימים)', 'שגיאות']}>
            {Object.entries(imp.fetched).map(([k, n]) => <tr key={k}><td className="px-3 py-1.5 text-xs ltr">{k}</td><td className="px-3 py-1.5 text-xs">{n}</td><td className="px-3 py-1.5 text-xs">{imp.report?.[k]?.inserted ?? '—'}</td><td className="px-3 py-1.5 text-xs">{imp.report?.[k]?.skipped ?? '—'}</td><td className="px-3 py-1.5 text-xs">{imp.report?.[k]?.errors ? <span className="text-rose-700">{imp.report[k].errors}</span> : imp.report ? 0 : '—'}</td></tr>)}
          </Table>
        )}
      </Card>
    </div>
  )
}
