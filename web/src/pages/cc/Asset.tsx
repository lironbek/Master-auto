import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Asset, type CcEvent, type CcProject, type Connection } from '../../api'
import { Card, Empty, ErrorBox, Field, Mono, Spinner } from '../../components/ui'
import { ConnPill, EventRow, ExtLink, Facts } from '../../components/cc'
import { assetKind, environment, fmtDate, provider, t } from '../../i18n'
import { useAuth } from '../../auth'

interface Detail { asset: Asset; projects: (CcProject | null)[]; events: CcEvent[]; connection: Connection | null }

export default function AssetPage() {
  const { id } = useParams()
  const { me } = useAuth()
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const load = useCallback(() => api.get<Detail>(`/cc/assets/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const a = d.asset

  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.patch(`/cc/assets/${id}`, { description: fd.get('description'), environment: fd.get('environment'), importance: fd.get('importance') }); load() } catch (err) { setError(err) }
  }
  async function sourceAction(action: 'archive' | 'delete') {
    const verb = action === 'delete' ? 'למחוק לצמיתות' : 'לארכב'
    if (!window.confirm(`${verb} את ${a.name} ב-GitHub? ${action === 'delete' ? 'אין דרך חזרה.' : 'ניתן לבטל מ-GitHub.'}`)) return
    setBusy(action); setError(null); setNote('')
    try {
      const r = await api.post<{ action: string }>(`/cc/assets/${id}/source-action`, { action, confirm })
      setNote(r.action === 'delete' ? `הריפוזיטורי ${a.name} נמחק מ-GitHub ונרשם ביומן הביקורת.` : `הריפוזיטורי ${a.name} אורכב ב-GitHub.`)
      setConfirm(''); load()
    } catch (err) { setError(err) } finally { setBusy(null) }
  }
  const canAct = a.provider === 'github' && a.kind === 'repo' && !a.removed_at && me?.user.role === 'org_admin'
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><Link to="/assets" className="text-xs text-indigo-600">← לקטלוג</Link><h1 className="text-xl font-bold"><bdi>{a.name}</bdi></h1><p className="text-sm text-slate-500">{a.description || t(assetKind, a.kind)}</p></div>
        <ExtLink href={a.url} />
      </div>
      <ErrorBox error={error} />
      {note && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}
      {a.removed_at && <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{a.state === 'deleted' ? `הריפוזיטורי נמחק מהמקור דרך מרכז הבקרה (${fmtDate(a.removed_at)}). המידע האחרון נשמר להיסטוריה.` : `הנכס לא נמצא במקור בסנכרון המלא האחרון (${fmtDate(a.removed_at)}). המידע האחרון נשמר.`}</div>}
      <Facts items={[['סוג', t(assetKind, a.kind)], ['חשבון מקור', `${t(provider, a.provider)} · ${d.connection?.account_label ?? ''}`], ['מזהה במקור', <Mono>{a.external_id}</Mono>], ['סביבה', t(environment, a.environment)], ['מצב', <bdi>{a.state || '—'}</bdi>], ['עדכון במקור', fmtDate(a.source_updated_at)], ['נראה לאחרונה', fmtDate(a.last_seen_at)], ['פרויקטים', d.projects.filter(Boolean).length ? d.projects.filter(Boolean).map(p => <Link key={p!.id} to={`/projects/${p!.id}`} className="block text-indigo-700">{p!.name}</Link>) : <Link to="/inbox" className="text-indigo-700">טרם שויך · לתיבת המיון</Link>]]} />
      {a.meta && Object.keys(a.meta).length > 0 && <Facts items={Object.entries(a.meta).filter(([, v]) => v).map(([k, v]) => [k, <bdi>{String(v)}</bdi>])} />}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="פעילות שנקלטה" className="lg:col-span-2">
          {d.events.length === 0 ? <Empty>הנכס מופיע במלאי. אין אירועי פעילות זמינים עבורו{d.connection?.coverage && Object.values(d.connection.coverage).some(v => v !== 'full') ? ' (כיסוי חלקי בחיבור)' : ''}.</Empty> : <ul className="divide-y divide-slate-100">{d.events.map(e => <EventRow key={e.id} e={e} />)}</ul>}
        </Card>
        <div className="space-y-4">
          <Card title="עריכה">
            <form onSubmit={save} className="space-y-2">
              <Field label="מה הוא עושה (תיאור ידני, נשמר בסנכרון)"><input className="input" name="description" defaultValue={a.description} /></Field>
              <Field label="סביבה"><select className="input" name="environment" defaultValue={a.environment}>{Object.entries(environment).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="חשיבות"><select className="input" name="importance" defaultValue={a.importance ?? 'normal'}><option value="critical">קריטי</option><option value="high">גבוה</option><option value="normal">רגיל</option><option value="low">נמוך</option></select></Field>
              <button className="btn-primary w-full justify-center">שמירה</button>
            </form>
          </Card>
          {d.connection && <Card title="חיבור המקור"><div className="text-sm">{t(provider, d.connection.provider)} · {d.connection.account_label} <ConnPill value={d.connection.status} /></div><div className="mt-1 text-xs text-slate-500">סנכרון אחרון {fmtDate(d.connection.last_sync_at)}</div><Link to="/connections" className="mt-2 inline-block text-xs text-indigo-700">פרטי חיבור</Link></Card>}
          {canAct && (
            <Card title="פעולות על המקור (GitHub)" className="border-rose-200">
              <p className="text-xs text-slate-600">ארכוב הופך את הריפוזיטורי לקריאה בלבד וניתן לביטול מ-GitHub. מחיקה היא סופית. הטוקן של החיבור חייב הרשאת Administration: write (או delete_repo). כל פעולה נרשמת ביומן הביקורת.</p>
              <Field label={`הקלד את השם המלא לאישור: ${a.name}`}><input className="input ltr" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder={a.name} autoComplete="off" /></Field>
              <div className="mt-2 flex gap-2">
                <button className="btn-secondary" disabled={busy !== null || confirm.trim().toLowerCase() !== a.name.toLowerCase()} onClick={() => sourceAction('archive')}>{busy === 'archive' ? 'מארכב…' : 'ארכוב ב-GitHub'}</button>
                <button className="btn-secondary !border-rose-300 !text-rose-700" disabled={busy !== null || confirm.trim().toLowerCase() !== a.name.toLowerCase()} onClick={() => sourceAction('delete')}>{busy === 'delete' ? 'מוחק…' : 'מחיקה מ-GitHub'}</button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
