import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, Wrench } from 'lucide-react'

// Public page (no login): a customer reports what was done on a service ticket
// through a signed, expiring link. Talks to /api/billing/public/<token>.
interface Pub { ticket: { number_label: string; title: string; status: string; opened_at: string; customer_name: string }; business: { name?: string; phone?: string }; updates: { contact_name: string; content: string; minutes?: number | null; update_date: string }[] }
const statusHe: Record<string, string> = { open: 'פתוחה', in_progress: 'בטיפול', resolved: 'נפתרה', closed: 'סגורה' }

export default function ExternalUpdate() {
  const { token } = useParams()
  const [d, setD] = useState<Pub | null>(null)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = () => fetch(`/api/billing/public/${token}`).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || 'שגיאה'); return r.json() }).then(setD).catch(e => setError(e.message))
  useEffect(() => { load() }, [token])
  async function submit(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement); setBusy(true)
    try {
      const r = await fetch(`/api/billing/public/${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contact_name: fd.get('contact_name'), contact_phone: fd.get('contact_phone'), content: fd.get('content'), minutes: fd.get('minutes') ? Number(fd.get('minutes')) : null, update_date: fd.get('update_date') }) })
      if (!r.ok) throw new Error((await r.json()).detail || 'שגיאה')
      setDone(true); load()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="min-h-screen p-4 md:p-8">
      <div className="mx-auto max-w-xl space-y-4">
        <div className="flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-teal-400 text-white"><Wrench className="h-6 w-6" /></span><div><div className="text-lg font-bold">{d?.business.name || 'עדכון קריאת שירות'}</div><div className="text-sm text-slate-500">דיווח על טיפול בקריאה</div></div></div>
        {error && !d && <div className="card p-6 text-center text-rose-700">{error}</div>}
        {d && (
          <>
            <div className="card p-5">
              <div className="text-xs text-slate-500 ltr text-right">{d.ticket.number_label}</div>
              <div className="text-lg font-bold">{d.ticket.title}</div>
              <div className="text-sm text-slate-500">{d.ticket.customer_name} · {statusHe[d.ticket.status] ?? d.ticket.status} · נפתחה {new Date(d.ticket.opened_at).toLocaleDateString('he-IL')}</div>
            </div>
            {done ? (
              <div className="card flex items-center gap-3 p-5 text-emerald-800"><CheckCircle2 className="h-6 w-6" /><div><div className="font-semibold">תודה, העדכון התקבל.</div><button className="text-sm text-indigo-600" onClick={() => setDone(false)}>שליחת עדכון נוסף</button></div></div>
            ) : (
              <form onSubmit={submit} className="card space-y-3 p-5">
                {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>}
                <label className="block"><span className="label">תאריך הטיפול *</span><input className="input ltr" name="update_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block"><span className="label">מטפל *</span><input className="input" name="contact_name" required placeholder="שם" /></label>
                  <label className="block"><span className="label">טלפון</span><input className="input ltr" name="contact_phone" /></label>
                </div>
                <label className="block"><span className="label">זמן טיפול (בדקות)</span><input className="input ltr" name="minutes" type="number" min={0} step={5} /></label>
                <label className="block"><span className="label">מה נעשה *</span><textarea className="input" name="content" rows={4} required placeholder="תיאור הטיפול והפעולות שננקטו" /></label>
                <button className="btn-primary w-full justify-center" disabled={busy}>שליחת עדכון</button>
              </form>
            )}
            {d.updates.length > 0 && (
              <div className="card p-5"><div className="mb-2 text-sm font-semibold">עדכונים קודמים</div><ul className="divide-y divide-slate-100 text-sm">{d.updates.map((u, i) => <li key={i} className="py-2"><div className="text-xs text-slate-500">{u.update_date} · {u.contact_name}{u.minutes ? ` · ${u.minutes} דק'` : ''}</div><div className="whitespace-pre-wrap">{u.content}</div></li>)}</ul></div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
