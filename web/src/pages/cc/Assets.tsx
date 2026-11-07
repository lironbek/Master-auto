import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Asset, type CcProject } from '../../api'
import { Card, Empty, ErrorBox, Spinner, Table } from '../../components/ui'
import { EnvPill } from '../../components/cc'
import { assetKind, fmtDate, provider, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

export default function Assets() {
  const { qs, loading } = useWorkspace()
  const [items, setItems] = useState<Asset[] | null>(null)
  const [projects, setProjects] = useState<Record<string, string>>({})
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')

  useEffect(() => {
    if (loading) return
    Promise.all([api.get<Asset[]>(`/cc/assets${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`)])
      .then(([a, p]) => { setItems(a); setProjects(Object.fromEntries(p.map(x => [x.id, x.name]))) }).catch(setError)
  }, [qs, loading])

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
      <Card>
        {!shown ? <Spinner /> : shown.length === 0 ? <Empty>אין נכסים. חבר ספק במסך "חיבורים" והרץ סנכרון.</Empty> : (
          <Table head={['נכס', 'מה הוא עושה', 'איפה הוא חי', 'סביבה', 'מצב', 'פרויקט', 'עדכון אחרון']}>
            {shown.map(a => (
              <tr key={a.id}>
                <td className="px-3 py-2"><Link to={`/assets/${a.id}`} className="font-medium text-indigo-700"><bdi>{a.name}</bdi></Link><div className="text-xs text-slate-400">{t(assetKind, a.kind)}</div></td>
                <td className="px-3 py-2 text-xs text-slate-600">{a.description || '—'}</td>
                <td className="px-3 py-2 text-xs"><bdi>{t(provider, a.provider)}</bdi></td>
                <td className="px-3 py-2"><EnvPill value={a.environment} /></td>
                <td className="px-3 py-2 text-xs"><bdi>{a.state || '—'}</bdi></td>
                <td className="px-3 py-2 text-xs">{a.project_ids?.length ? a.project_ids.map(p => <Link key={p} to={`/projects/${p}`} className="ml-1 text-indigo-700">{projects[p] ?? p}</Link>) : <span className="badge bg-indigo-100 text-indigo-800">טרם שויך</span>}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(a.source_updated_at || a.last_seen_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
