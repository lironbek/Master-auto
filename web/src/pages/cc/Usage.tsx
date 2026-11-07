import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type CcClient, type UsageReport } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtDate, metricLabel, provider as providerLabels, qty, t, usageProvider } from '../../i18n'
import { useWorkspace } from '../../workspace'

const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01` }
const today = () => new Date().toISOString().slice(0, 10)

function Metrics({ m }: { m: Record<string, number> }) {
  const keys = Object.keys(m)
  if (keys.length === 0) return <span className="text-slate-400">—</span>
  return <span className="flex flex-wrap gap-1">{keys.map(k => <span key={k} className="badge bg-slate-100 text-slate-700"><bdi>{qty(m[k])}</bdi> {t(metricLabel, k)}</span>)}</span>
}

export default function Usage() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [data, setData] = useState<UsageReport | null>(null)
  const [clients, setClients] = useState<CcClient[]>([])
  const [error, setError] = useState<unknown>(null)
  const [f, setF] = useState({ client_id: '', provider: '', from: monthStart(), to: today() })
  const [tab, setTab] = useState<'clients' | 'interfaces' | 'entries' | 'manage'>('clients')

  const load = () => {
    const p = new URLSearchParams(qs.replace('?', ''))
    if (f.client_id) p.set('client_id', f.client_id)
    if (f.provider) p.set('provider', f.provider)
    if (f.from) p.set('from', f.from)
    if (f.to) p.set('to', f.to)
    return Promise.all([api.get<UsageReport>(`/cc/usage?${p}`), api.get<CcClient[]>(`/cc/clients${qs}`)])
      .then(([u, c]) => { setData(u); setClients(c); setError(null) }).catch(setError)
  }
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length, f.client_id, f.provider, f.from, f.to])

  async function addClient(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post('/cc/clients', { workspace_id: fd.get('workspace_id'), name: fd.get('name'), external_ref: fd.get('external_ref'), notes: fd.get('notes') }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const tot = data?.totals ?? {}
  const tokens = (tot.tokens_in ?? 0) + (tot.tokens_out ?? 0) + (tot.tokens_cached ?? 0)
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">שימוש לפי לקוח</h1><p className="text-sm text-slate-500">כמה קריאות API, טוקנים, עמודי OCR והודעות WhatsApp נצרכו, לפי לקוח, ספק וממשק. הנתונים מגיעים מהאינטגרציות שמבצעות את הקריאות (n8n, בוטים, אפליקציות) ומריצות הסוכנים כאן.</p></div>
      <ErrorBox error={error} />
      <Card>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="לקוח"><select className="input" value={f.client_id} onChange={e => setF({ ...f, client_id: e.target.value })}><option value="">כל הלקוחות</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="ספק / API"><select className="input" value={f.provider} onChange={e => setF({ ...f, provider: e.target.value })}><option value="">כל הספקים</option>{(data?.providers ?? []).map(p => <option key={p} value={p}>{t(usageProvider, p)}</option>)}</select></Field>
          <Field label="מתאריך"><input className="input ltr" type="date" value={f.from} onChange={e => setF({ ...f, from: e.target.value })} /></Field>
          <Field label="עד תאריך"><input className="input ltr" type="date" value={f.to} onChange={e => setF({ ...f, to: e.target.value })} /></Field>
        </div>
      </Card>
      {data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="קריאות API" value={qty(tot.requests ?? 0)} tone="indigo" />
          <Stat label="טוקנים" value={qty(tokens)} hint={`קלט ${qty(tot.tokens_in ?? 0)} · פלט ${qty(tot.tokens_out ?? 0)}`} />
          <Stat label="הודעות" value={qty(tot.messages ?? 0)} hint={`ל-${qty(tot.recipients ?? 0)} נמענים`} tone="amber" />
          <Stat label="עמודי OCR" value={qty(tot.pages ?? 0)} />
          <Stat label="רשומות" value={qty(data.entries_total)} hint={`${clients.length} לקוחות`} />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {([['clients', 'לפי לקוח'], ['interfaces', 'לפי ממשק'], ['entries', 'רשומות אחרונות'], ['manage', 'ניהול לקוחות']] as const).map(([k, label]) => <button key={k} className={`btn-secondary ${tab === k ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
      </div>

      {tab === 'clients' && (
        <Card title="שימוש לפי לקוח">
          {!data ? <Spinner /> : data.by_client.length === 0 ? <Empty>אין שימוש מדווח בתקופה. חבר את האינטגרציות לדיווח (ראה "ניהול לקוחות").</Empty> : (
            <Table head={['לקוח', 'סך הכול', 'לפי ספק', 'לפי ממשק', 'רשומות']}>
              {data.by_client.map(c => <tr key={c.client_id ?? '_'}>
                <td className="px-3 py-2 font-medium">{c.client_name}</td>
                <td className="px-3 py-2"><Metrics m={c.metrics} /></td>
                <td className="px-3 py-2 text-xs">{Object.entries(c.providers).map(([p, m]) => <div key={p} className="flex items-center gap-2 py-0.5"><span className="w-20 shrink-0 font-medium">{t(usageProvider, p)}</span><Metrics m={m} /></div>)}</td>
                <td className="px-3 py-2 text-xs">{Object.entries(c.interfaces).map(([i, m]) => <div key={i} className="flex items-center gap-2 py-0.5"><span className="mono w-32 shrink-0 truncate" title={i}>{i || '—'}</span><Metrics m={m} /></div>)}</td>
                <td className="px-3 py-2 text-xs">{c.entries}</td>
              </tr>)}
            </Table>
          )}
        </Card>
      )}

      {tab === 'interfaces' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="לפי ממשק (מי ביצע את הקריאות)">
            {!data ? <Spinner /> : data.by_interface.length === 0 ? <Empty>אין נתונים.</Empty> : (
              <Table head={['ממשק', 'ספק', 'כמויות', 'רשומות']}>
                {data.by_interface.map(i => <tr key={`${i.interface}|${i.provider}`}><td className="px-3 py-2"><span className="mono text-xs">{i.interface || '—'}</span></td><td className="px-3 py-2 text-xs">{t(usageProvider, i.provider)}</td><td className="px-3 py-2"><Metrics m={i.metrics} /></td><td className="px-3 py-2 text-xs">{i.entries}</td></tr>)}
              </Table>
            )}
          </Card>
          <Card title="לפי ספק">
            {!data ? <Spinner /> : data.by_provider.length === 0 ? <Empty>אין נתונים.</Empty> : (
              <Table head={['ספק / API', 'כמויות', 'רשומות']}>
                {data.by_provider.map(p => <tr key={p.provider}><td className="px-3 py-2 font-medium">{t(usageProvider, p.provider)}</td><td className="px-3 py-2"><Metrics m={p.metrics} /></td><td className="px-3 py-2 text-xs">{p.entries}</td></tr>)}
              </Table>
            )}
            <h3 className="mt-4 text-xs font-semibold text-slate-600">לפי פרויקט</h3>
            {data && data.by_project.length > 0 && (
              <ul className="mt-2 divide-y divide-slate-100 text-sm">{data.by_project.map(p => <li key={p.project_id ?? '_'} className="flex items-center justify-between py-1.5">{p.project_id ? <Link to={`/projects/${p.project_id}`} className="text-indigo-700">{p.project_name}</Link> : <span>{p.project_name}</span>}<Metrics m={p.metrics} /></li>)}</ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'entries' && (
        <Card title="רשומות אחרונות">
          {!data ? <Spinner /> : data.entries.length === 0 ? <Empty>אין רשומות.</Empty> : (
            <Table head={['זמן', 'לקוח', 'ספק', 'מדד', 'כמות', 'ממשק', 'מודל', 'פרויקט']}>
              {data.entries.map(e => <tr key={e.id}><td className="px-3 py-2 text-xs whitespace-nowrap">{fmtDate(e.occurred_at)}</td><td className="px-3 py-2 text-sm">{e.client_name || '—'}</td><td className="px-3 py-2 text-xs">{t(usageProvider, e.provider)}</td><td className="px-3 py-2 text-xs">{t(metricLabel, e.metric)}</td><td className="px-3 py-2"><bdi>{qty(Number(e.quantity))}</bdi> <span className="text-xs text-slate-400">{e.unit}</span></td><td className="px-3 py-2"><span className="mono text-xs">{e.interface || '—'}</span></td><td className="px-3 py-2"><span className="mono text-xs">{e.model || '—'}</span></td><td className="px-3 py-2 text-xs">{e.project_id ? <Link to={`/projects/${e.project_id}`} className="text-indigo-700">{e.project_name}</Link> : '—'}</td></tr>)}
            </Table>
          )}
        </Card>
      )}

      {tab === 'manage' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="לקוחות">
            {clients.length === 0 ? <Empty>אין לקוחות. לקוח נוצר גם אוטומטית בדיווח הראשון בשמו.</Empty> : (
              <Table head={['שם', 'מזהה חיצוני', 'פרויקטים', 'נוצר']}>
                {clients.map(c => <tr key={c.id}><td className="px-3 py-2 font-medium">{c.name}</td><td className="px-3 py-2"><span className="mono text-xs">{c.external_ref || '—'}</span></td><td className="px-3 py-2 text-xs">{c.projects?.length ? c.projects.map(p => <Link key={p.id} to={`/projects/${p.id}`} className="ml-2 text-indigo-700">{p.name}</Link>) : 'שייך פרויקט מעמוד הפרויקט (עריכה → לקוח)'}</td><td className="px-3 py-2 text-xs">{fmtDate(c.created_at)}</td></tr>)}
              </Table>
            )}
            <form key={current?.id ?? 'all'} onSubmit={addClient} className="mt-4 grid gap-3 md:grid-cols-4">
              <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={current?.id ?? workspaces[0].id}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
              <Field label="שם הלקוח"><input className="input" name="name" required /></Field>
              <Field label="מזהה חיצוני (CRM)"><input className="input ltr" name="external_ref" /></Field>
              <Field label="הערות"><input className="input" name="notes" /></Field>
              <div className="md:col-span-4"><button className="btn-primary">הוספת לקוח</button></div>
            </form>
          </Card>
          <Card title="איך האינטגרציות מדווחות">
            <p className="text-sm text-slate-600">כל קריאת API שבוצעה עבור לקוח מדווחת כרשומה: ספק, מדד, כמות, הממשק שביצע, שם הלקוח. הטוקן הוא טוקן הדיווח של המרחב (מסך "חיבורים"). דיווח חוזר עם אותו <span className="mono">external_id</span> מזוהה ככפילות.</p>
            <pre className="ltr mt-3 whitespace-pre-wrap rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{`POST ${location.origin}/api/cc/usage
X-Report-Token: <token>
{
  "workspace_id": "${current?.id ?? workspaces[0].id}",
  "entries": [
    {"provider": "whatsapp", "metric": "messages", "quantity": 12, "recipients": 5,
     "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "wa-run-123"},
    {"provider": "gemini", "metric": "requests", "quantity": 30, "model": "gemini-2.5-pro",
     "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "gm-run-123"},
    {"provider": "ocr", "metric": "pages", "quantity": 40, "interface": "app/crm", "client": "לקוח ב"}
  ]
}`}</pre>
            <p className="mt-3 text-xs text-slate-500">ספקים: {(data?.providers ?? []).map(p => t(usageProvider, p)).join(' · ')}. מדדים: {(data?.metrics ?? []).map(m => t(metricLabel, m)).join(' · ')}. ריצות סוכנים במערכת מדווחות אוטומטית (קריאות וטוקנים) ללקוח של הפרויקט.</p>
            <p className="mt-2 text-xs text-slate-500">ב-n8n: צומת HTTP Request אחרי כל קריאת API, עם הכותרת X-Report-Token וה-body למעלה. <Link to="/connections" className="text-indigo-700">טוקן דיווח</Link> · {t(providerLabels, 'n8n')}</p>
          </Card>
        </div>
      )}
    </div>
  )
}
