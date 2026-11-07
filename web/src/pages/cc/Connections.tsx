import { useEffect, useState, type FormEvent } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { api, type Connection, type Workspace } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { ConnPill, FirstWorkspace } from '../../components/cc'
import { coverage, fmtDate, provider, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

interface ProviderInfo { label: string; secret_label: string; fields: string[] }
const fieldLabels: Record<string, string> = { org: 'ארגון GitHub (ריק = החשבון שלי)', repos: 'ריפוזיטוריז לסנכרון (owner/name, מופרדים בפסיק; ריק = הכול)', team_id: 'Team ID ב-Vercel (ריק = חשבון אישי)', base_url: 'כתובת המופע (https://n8n.example.com)' }
const providerHints: Record<string, string> = { github: 'לסנכרון מספיקה קריאה (Contents, Metadata, Pull requests, Actions). כדי לארכב או למחוק ריפוזיטוריז מעמוד הנכס, הטוקן צריך גם Administration: Read and write.' }

export default function Connections() {
  const { workspaces, current, qs, loading, reload } = useWorkspace()
  const [items, setItems] = useState<Connection[] | null>(null)
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({})
  const [error, setError] = useState<unknown>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [f, setF] = useState<{ workspace_id: string; provider: string; account_label: string; secret: string; config: Record<string, string> }>({ workspace_id: '', provider: 'github', account_label: '', secret: '', config: {} })
  const [token, setToken] = useState<{ ws: Workspace; token: string } | null>(null)

  const load = () => api.get<Connection[]>(`/cc/connections${qs}`).then(setItems).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) { load(); api.get<Record<string, ProviderInfo>>('/cc/providers').then(setProviders).catch(setError) } }, [qs, loading, workspaces.length])

  async function create(e: FormEvent) {
    e.preventDefault(); setError(null)
    try {
      const r = await api.post<Connection>('/cc/connections', { ...f, workspace_id: f.workspace_id || current?.id || workspaces[0].id })
      setNote(r.status === 'ok' ? `החיבור ל-${t(provider, r.provider)} אומת. הרץ סנכרון כדי לייבא מלאי ו-30 יום של היסטוריה.` : `החיבור נשמר אבל האימות נכשל: ${r.last_error}`)
      setOpen(false); setF({ ...f, secret: '', account_label: '', config: {} }); load()
    } catch (err) { setError(err) }
  }
  async function sync(id: string) {
    setBusy(id); setError(null)
    try { const s = await api.post<{ assets: number; events: number; new_inbox: number; status: string; notes: string[] }>(`/cc/connections/${id}/sync`); setNote(`סנכרון ${t({ ok: 'הושלם', partial: 'חלקי' }, s.status)}: ${s.assets} נכסים, ${s.events} אירועים, ${s.new_inbox} חדשים בתיבת המיון. ${s.notes.join(' ')}`); load() } catch (err) { setError(err) } finally { setBusy(null) }
  }
  async function disconnect(id: string) { if (!confirm('לנתק את החיבור? הקליטה תיעצר והמידע האחרון יסומן כלא עדכני.')) return; try { await api.post(`/cc/connections/${id}/disconnect`); load() } catch (err) { setError(err) } }
  async function reportToken(ws: Workspace) { try { const r = await api.post<{ report_token: string }>(`/cc/workspaces/${ws.id}/report-token`); setToken({ ws, token: r.report_token }); reload() } catch (err) { setError(err) } }

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const pinfo = providers[f.provider]
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold">ניהול חיבורים</h1><p className="text-sm text-slate-500">כיסוי, הרשאות ועדכניות לכל חשבון ומופע</p></div>
        <button className="btn-primary" onClick={() => setOpen(v => !v)}><Plus className="h-4 w-4" /> חיבור חדש</button>
      </div>
      <ErrorBox error={error} />
      {note && <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900" role="status">{note}</div>}
      {open && (
        <Card title="חיבור ספק">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-2">
            <Field label="מרחב"><select className="input" value={f.workspace_id || current?.id || workspaces[0].id} onChange={e => setF({ ...f, workspace_id: e.target.value })}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
            <Field label="ספק"><select className="input" value={f.provider} onChange={e => setF({ ...f, provider: e.target.value, config: {} })}>{Object.entries(providers).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></Field>
            <Field label="שם החשבון (לתצוגה)"><input className="input" value={f.account_label} onChange={e => setF({ ...f, account_label: e.target.value })} placeholder="ארגון קומקס / חשבון פרטי" /></Field>
            <Field label={pinfo?.secret_label ?? 'Token'} hint="נשמר מוצפן בשרת. לא מוצג שוב."><input className="input ltr" type="password" value={f.secret} onChange={e => setF({ ...f, secret: e.target.value })} required autoComplete="off" /></Field>
            {(pinfo?.fields ?? []).map(k => <Field key={k} label={fieldLabels[k] ?? k}><input className="input ltr" value={f.config[k] ?? ''} onChange={e => setF({ ...f, config: { ...f.config, [k]: e.target.value } })} /></Field>)}
            <div className="md:col-span-2 text-xs text-slate-500">המוצר צורך קריאה בלבד: מטא-דאטה, PR ו-Actions ב-GitHub; פרויקטים ופריסות ב-Vercel; פרויקטים ב-Supabase; Workflows וריצות ב-n8n. אם הטוקן רחב מהנדרש, הפער מתועד.{providerHints[f.provider] ? ` ${providerHints[f.provider]}` : ''}</div>
            <div className="md:col-span-2"><button className="btn-primary">בדיקת הרשאה ושמירה</button></div>
          </form>
        </Card>
      )}
      <Card title="חיבורים מוגדרים">
        {!items ? <Spinner /> : items.length === 0 ? <Empty>אין חיבורים.</Empty> : (
          <Table head={['ספק', 'חשבון', 'כיסוי', 'מצב', 'סנכרון אחרון', 'ניסיון אחרון', '']}>
            {items.map(c => (
              <tr key={c.id}>
                <td className="px-3 py-2 font-medium">{t(provider, c.provider)}</td>
                <td className="px-3 py-2 text-sm">{c.account_label} <span className="mono text-xs text-slate-400">{c.secret_masked}</span></td>
                <td className="px-3 py-2 text-xs">{c.coverage ? Object.entries(c.coverage).map(([k, v]) => `${k}: ${t(coverage, v)}`).join(' · ') : (c.capabilities?.join(' · ') || '—')}{c.notes?.length ? <div className="text-amber-700">{c.notes.join(' ')}</div> : null}</td>
                <td className="px-3 py-2"><ConnPill value={c.status} />{c.freshness?.stale && ['ok', 'partial', 'error'].includes(c.status) && <span className="badge mr-1 bg-amber-100 text-amber-800">לא עדכני</span>}{c.last_error && <div className="mt-1 max-w-xs truncate text-xs text-rose-700" title={c.last_error}>{c.last_error}</div>}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(c.last_sync_at) || 'טרם'}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(c.last_attempt_at) || '—'}</td>
                <td className="px-3 py-2"><div className="flex gap-1"><button className="btn-secondary" onClick={() => sync(c.id)} disabled={busy === c.id || c.status === 'disconnected'}><RefreshCw className={`h-4 w-4 ${busy === c.id ? 'animate-spin' : ''}`} /> סנכרן</button><button className="btn-secondary" onClick={() => disconnect(c.id)} disabled={c.status === 'disconnected'}>נתק</button></div></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="מדווח חיצוני (שירות פרטי / Cron / בוט מקומי)">
        <p className="text-sm text-slate-600">שירות שאין לו API יכול לדווח על ריצה או heartbeat ישירות. כל מרחב מקבל טוקן דיווח; הבקשה נדחית בלי טוקן תקף, ודיווח חוזר עם אותו מזהה מוכר ככפילות.</p>
        <div className="mt-3 flex flex-wrap gap-2">{workspaces.map(w => <button key={w.id} className="btn-secondary" onClick={() => reportToken(w)}>צור/חדש טוקן ל-{w.name}</button>)}</div>
        {token && (
          <div className="mt-3 rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
            <div className="mb-1 text-slate-300">טוקן למרחב {token.ws.name} (מוצג פעם אחת):</div>
            <pre className="ltr whitespace-pre-wrap">{`curl -X POST ${location.origin}/api/cc/report \\
  -H "X-Report-Token: ${token.token}" -H "Content-Type: application/json" \\
  -d '{"workspace_id":"${token.ws.id}","service":"nightly-backup","external_id":"run-123","kind":"heartbeat","result":"success"}'`}</pre>
          </div>
        )}
      </Card>
    </div>
  )
}
