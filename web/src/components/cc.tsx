// Shared control-center widgets: status pills, event rows, first-run workspace card.
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type CcEvent } from '../api'
import { useWorkspace } from '../workspace'
import { Card, ErrorBox, Field, Mono } from './ui'
import { connStatus, environment, eventKind, eventResult, fmtDate, t } from '../i18n'

const resTone: Record<string, string> = { success: 'bg-emerald-100 text-emerald-800', failure: 'bg-rose-100 text-rose-800', running: 'bg-indigo-100 text-indigo-800', cancelled: 'bg-slate-200 text-slate-600', unknown: 'bg-slate-100 text-slate-600' }
export function ResultPill({ value }: { value: string }) { return <span className={`badge ${resTone[value] ?? 'bg-slate-100'}`}>{t(eventResult, value)}</span> }

const envTone: Record<string, string> = { production: 'bg-violet-100 text-violet-800', preview: 'bg-sky-100 text-sky-800', development: 'bg-slate-100 text-slate-700', test: 'bg-amber-100 text-amber-800', unclassified: 'bg-slate-100 text-slate-500' }
export function EnvPill({ value }: { value: string }) { return <span className={`badge ${envTone[value] ?? 'bg-slate-100'}`}>{t(environment, value)}</span> }

const connTone: Record<string, string> = { ok: 'bg-emerald-100 text-emerald-800', partial: 'bg-amber-100 text-amber-800', rate_limited: 'bg-amber-100 text-amber-800', reauth: 'bg-rose-100 text-rose-800', disconnected: 'bg-slate-200 text-slate-600', new: 'bg-indigo-100 text-indigo-800', error: 'bg-amber-100 text-amber-800' }
export function ConnPill({ value }: { value: string }) { return <span className={`badge ${connTone[value] ?? 'bg-slate-100'}`}>{t(connStatus, value)}</span> }

export function TonePill({ tone, children }: { tone?: string; children: ReactNode }) {
  const c = tone === 'bad' ? 'bg-rose-100 text-rose-800' : tone === 'warn' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
  return <span className={`badge ${c}`}>{children}</span>
}

export function EventRow({ e, showProject = false }: { e: CcEvent; showProject?: boolean }) {
  return (
    <li className="flex flex-wrap items-center gap-2 py-2 text-sm">
      <span className="w-28 shrink-0 text-xs text-slate-400">{fmtDate(e.occurred_at)}</span>
      <span className="text-xs text-slate-500">{t(eventKind, e.kind)}</span>
      <span className="truncate font-medium">{e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-indigo-700 hover:underline">{e.title || e.external_id}</a> : (e.title || e.external_id)}</span>
      <EnvPill value={e.environment} /><ResultPill value={e.result} />
      {showProject && e.project_name && <span className="text-xs text-slate-500">· {e.project_name}</span>}
      {e.session_id && <Link to={`/sessions/${e.session_id}`} className="text-xs text-indigo-600">סשן</Link>}
      {e.asset_id && <Link to={`/assets/${e.asset_id}`} className="text-xs text-indigo-600">נכס</Link>}
    </li>
  )
}

export function ExtLink({ href, children }: { href: string; children?: ReactNode }) {
  if (!href) return null
  return <a href={href} target="_blank" rel="noopener noreferrer" className="btn-secondary">{children ?? 'פתח במקור'} ↗</a>
}

/** Shown when the organisation has no workspace yet (first run). If the
 * workspace list could not be loaded at all, the error is shown instead. */
export function FirstWorkspace() {
  const { reload, setCurrent, error: loadError } = useWorkspace()
  const [name, setName] = useState('')
  const [kind, setKind] = useState('personal')
  const [error, setError] = useState<unknown>(null)
  async function create(e: FormEvent) {
    e.preventDefault()
    try { const ws = await api.post<{ id: string }>('/cc/workspaces', { name, kind }); await reload(); setCurrent(ws.id) } catch (err) { setError(err) }
  }
  if (loadError) {
    return (
      <Card title="לא ניתן לטעון את המרחבים">
        <ErrorBox error={loadError} />
        <button className="btn-secondary mt-3" onClick={() => reload()}>נסה שוב</button>
      </Card>
    )
  }
  return (
    <Card title="ברוך הבא. נתחיל ממרחב עבודה">
      <p className="mb-3 text-sm text-slate-600">מרחב הוא גבול הרשאות ונתונים: כל החיבורים, הפרויקטים והסשנים שייכים למרחב אחד. דוגמאות: עבודה בקומקס, פרויקטים פרטיים, מרחב ללקוח.</p>
      <form onSubmit={create} className="grid gap-3 md:grid-cols-3">
        <Field label="שם המרחב"><input className="input" value={name} onChange={e => setName(e.target.value)} required placeholder="פרויקטים פרטיים" /></Field>
        <Field label="סוג"><select className="input" value={kind} onChange={e => setKind(e.target.value)}><option value="personal">פרטי</option><option value="work">עבודה</option><option value="client">לקוח</option><option value="trash">למחיקה</option></select></Field>
        <div className="flex items-end"><button className="btn-primary">יצירת מרחב</button></div>
      </form>
      <ErrorBox error={error} />
    </Card>
  )
}

export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(([k, v]) => <div key={k} className="rounded-lg border border-slate-200 bg-white p-3"><dt className="text-xs text-slate-500">{k}</dt><dd className="mt-1 text-sm font-semibold break-words">{v ?? '—'}</dd></div>)}
    </dl>
  )
}

export { Mono }
