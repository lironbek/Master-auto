import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Asset, type CcProject } from '../../api'
import { Card, Empty, ErrorBox, Spinner, Table } from '../../components/ui'
import { EnvPill } from '../../components/cc'
import { assetKind, fmtDate, provider, t } from '../../i18n'
import { useWorkspace } from '../../workspace'
import { useAuth } from '../../auth'

export default function Assets() {
  const { qs, loading } = useWorkspace()
  const { me } = useAuth()
  const [items, setItems] = useState<Asset[] | null>(null)
  const [projects, setProjects] = useState<Record<string, string>>({})
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')

  const load = () => Promise.all([api.get<Asset[]>(`/cc/assets${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`)])
    .then(([a, p]) => { setItems(a); setProjects(Object.fromEntries(p.map(x => [x.id, x.name]))) }).catch(setError)
  useEffect(() => { if (!loading) load() }, [qs, loading])

  // Direct, audited write-back to GitHub: archive or delete a repository. The
  // full name is typed as confirmation; the server re-checks admin role + token.
  async function sourceAction(a: Asset, action: 'archive' | 'delete') {
    const typed = window.prompt(`${action === 'delete' ? 'מחיקה סופית' : 'ארכוב'} של ${a.name} ב-GitHub.\nהקלד את השם המלא לאישור:`)
    if (typed === null) return
    setBusy(a.id); setError(null); setNote('')
    try {
      await api.post(`/cc/assets/${a.id}/source-action`, { action, confirm: typed })
      setNote(action === 'delete' ? `${a.name} נמחק מ-GitHub ונרשם ביומן הביקורת.` : `${a.name} אורכב ב-GitHub.`)
      load()
    } catch (err) { setError(err) } finally { setBusy(null) }
  }
  const isAdmin = me?.user.role === 'org_admin'

  const shown = items?.filter(a => (!kind || a.kind === kind) && (!q || `${a.name} ${a.description} ${a.provider} ${a.external_id}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">קטלוג נכסים</h1><p className="text-sm text-slate-500">מה קיים, מה הוא עושה ואיפה הוא רץ</p></div>
        <div className="flex gap-2">
          <select className="input w-44" value={kind} onChange={e => setKind(e.target.value)}><option value="">כל הסוגים</option>{Object.entries(assetKind).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <input className="input w-56" placeholder="חיפוש לפי שם, ספק או מזהה" value={q} onChange={e => setQ(e.target.value)} />
        </div>
      </div>
      <ErrorBox error={error} />
      {note && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}
      {isAdmin && <p className="text-xs text-slate-500">ריפוזיטוריז של GitHub אפשר לארכב או למחוק ישירות מכאן (עמודת "פעולות"). הפעולה דורשת הקלדת השם המלא, טוקן חיבור עם Administration: write, ונרשמת ביומן הביקורת.</p>}
      <Card>
        {!shown ? <Spinner /> : shown.length === 0 ? <Empty>אין נכסים. חבר ספק במסך "חיבורים" והרץ סנכרון.</Empty> : (
          <Table head={['נכס', 'מה הוא עושה', 'איפה הוא חי', 'סביבה', 'מצב', 'פרויקט', 'עדכון אחרון', 'פעולות']}>
            {shown.map(a => (
              <tr key={a.id}>
                <td className="px-3 py-2"><Link to={`/assets/${a.id}`} className="font-medium text-indigo-700"><bdi>{a.name}</bdi></Link><div className="text-xs text-slate-400">{t(assetKind, a.kind)}</div></td>
                <td className="px-3 py-2 text-xs text-slate-600">{a.description || '—'}</td>
                <td className="px-3 py-2 text-xs"><bdi>{t(provider, a.provider)}</bdi></td>
                <td className="px-3 py-2"><EnvPill value={a.environment} /></td>
                <td className="px-3 py-2 text-xs"><bdi>{a.state || '—'}</bdi></td>
                <td className="px-3 py-2 text-xs">{a.project_ids?.length ? a.project_ids.map(p => <Link key={p} to={`/projects/${p}`} className="ml-1 text-indigo-700">{projects[p] ?? p}</Link>) : <span className="badge bg-indigo-100 text-indigo-800">טרם שויך</span>}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(a.source_updated_at || a.last_seen_at)}</td>
                <td className="px-3 py-2 text-xs whitespace-nowrap">{isAdmin && a.provider === 'github' && a.kind === 'repo' && !a.removed_at ? (
                  <span className="flex gap-2"><button className="text-slate-600 hover:underline" disabled={busy === a.id} onClick={() => sourceAction(a, 'archive')}>ארכוב</button><button className="text-rose-700 hover:underline" disabled={busy === a.id} onClick={() => sourceAction(a, 'delete')}>{busy === a.id ? '…' : 'מחיקה'}</button></span>
                ) : '—'}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
