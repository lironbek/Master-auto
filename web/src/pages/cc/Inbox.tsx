import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type CcProject, type InboxItem } from '../../api'
import { Card, Empty, ErrorBox, Spinner } from '../../components/ui'
import { EnvPill } from '../../components/cc'
import { assetKind, fmtDate, inboxKind, provider, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

export default function InboxPage() {
  const { qs, loading } = useWorkspace()
  const [items, setItems] = useState<InboxItem[] | null>(null)
  const [projects, setProjects] = useState<CcProject[]>([])
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [newName, setNewName] = useState<Record<string, string>>({})

  const load = () => Promise.all([api.get<InboxItem[]>(`/cc/inbox${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`)]).then(([i, p]) => { setItems(i); setProjects(p) }).catch(setError)
  useEffect(() => { if (!loading) load() }, [qs, loading])

  async function act(item: InboxItem, action: string) {
    try {
      const body: Record<string, string | undefined> = { action }
      if (action === 'assign') body.project_id = choice[item.id] || item.suggested_project_id || undefined
      if (action === 'create_project') body.project_name = newName[item.id]
      const r = await api.post<{ ok: boolean; project_id?: string }>(`/cc/inbox/${item.id}`, body)
      setNote(action === 'dismiss' ? 'ההצעה נדחתה.' : `הנכס שויך${r.project_id ? ` לפרויקט ${projects.find(p => p.id === r.project_id)?.name ?? newName[item.id] ?? ''}` : ''}.`)
      load()
    } catch (err) { setError(err) }
  }

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">תיבת מיון</h1><p className="text-sm text-slate-500">נכסים חדשים, חוסר התאמה, כפילות אפשרית ומקור שנעלם. כאן משייכים נכסים לפרויקטים.</p></div>
      <ErrorBox error={error} />
      {note && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}
      <Card>
        {!items ? <Spinner /> : items.length === 0 ? <Empty>תיבת המיון ריקה.</Empty> : (
          <ul className="divide-y divide-slate-100">
            {items.map(i => {
              const wsProjects = projects.filter(p => p.workspace_id === i.workspace_id && p.status === 'active')
              const suggested = wsProjects.find(p => p.id === i.suggested_project_id)
              return (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2"><span className="badge bg-indigo-100 text-indigo-800">{t(inboxKind, i.kind)}</span>{i.asset && <Link to={`/assets/${i.asset.id}`} className="font-medium text-indigo-700"><bdi>{i.asset.name}</bdi></Link>}{i.asset && <EnvPill value={i.asset.environment} />}</div>
                    <div className="text-xs text-slate-500">{i.asset ? `${t(assetKind, i.asset.kind)} · ${t(provider, i.asset.provider)}` : ''} · {i.reason} · {fmtDate(i.created_at)}{suggested && <span className="text-emerald-700"> · מוצע: {suggested.name}</span>}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select className="input w-44" value={choice[i.id] ?? i.suggested_project_id ?? ''} onChange={e => setChoice({ ...choice, [i.id]: e.target.value })}>
                      <option value="">בחר פרויקט…</option>{wsProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <button className="btn-primary" disabled={!(choice[i.id] || i.suggested_project_id)} onClick={() => act(i, 'assign')}>שייך</button>
                    <input className="input w-40" placeholder="פרויקט חדש…" value={newName[i.id] ?? ''} onChange={e => setNewName({ ...newName, [i.id]: e.target.value })} />
                    <button className="btn-secondary" disabled={!newName[i.id]} onClick={() => act(i, 'create_project')}>צור ושייך</button>
                    <button className="btn-secondary" onClick={() => act(i, 'mark_shared')}>נכס משותף</button>
                    <button className="btn-secondary" onClick={() => act(i, 'dismiss')}>דחה</button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
