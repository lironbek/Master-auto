import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Archive, Check, FolderKanban, Link2, Boxes, Pencil, Plus, X } from 'lucide-react'
import { api, type CcProject, type Workspace } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner } from '../../components/ui'
import { TonePill } from '../../components/cc'
import { t, workspaceKind } from '../../i18n'
import { useWorkspace } from '../../workspace'

const kindTint: Record<string, string> = { personal: 'bg-teal-100 text-teal-700', work: 'bg-indigo-100 text-indigo-700', client: 'bg-amber-100 text-amber-700', trash: 'bg-rose-100 text-rose-700' }

/** Workspaces are the categories projects are filed under (Comax, private, a
 * client, "to delete"). This page creates and renames them, archives empty
 * ones, and lets every project be re-filed with one select. */
export default function Workspaces() {
  const { workspaces, reload, loading } = useWorkspace()
  const [projects, setProjects] = useState<CcProject[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')
  const [f, setF] = useState({ name: '', kind: 'work' })
  const [editing, setEditing] = useState<{ id: string; name: string; kind: string } | null>(null)
  const [filter, setFilter] = useState('')

  const load = () => api.get<CcProject[]>('/cc/projects').then(setProjects).catch(setError)
  useEffect(() => { if (!loading) load() }, [loading])

  async function create(e: FormEvent) {
    e.preventDefault()
    try { await api.post('/cc/workspaces', f); setF({ name: '', kind: 'work' }); await reload(); setNote(`המרחב "${f.name}" נוצר.`) } catch (err) { setError(err) }
  }
  async function save() {
    if (!editing) return
    try { await api.patch(`/cc/workspaces/${editing.id}`, { name: editing.name, kind: editing.kind }); setEditing(null); await reload() } catch (err) { setError(err) }
  }
  async function archive(w: Workspace) {
    if (!confirm(`לארכב את המרחב "${w.name}"? המרחב ייעלם מהרשימות; הנתונים נשמרים.`)) return
    try { await api.del(`/cc/workspaces/${w.id}`); await reload(); setNote(`המרחב "${w.name}" אורכב.`) } catch (err) { setError(err) }
  }
  async function move(p: CcProject, wsId: string) {
    if (!wsId || wsId === p.workspace_id) return
    try {
      const r = await api.post<{ moved: number; cleared: string[] }>(`/cc/projects/${p.id}/move`, { workspace_id: wsId })
      const target = workspaces.find(w => w.id === wsId)?.name ?? ''
      setNote(`"${p.name}" סווג למרחב "${target}".${r.cleared.length ? ' הלקוח / מפתח ברירת המחדל אופסו כי הם שייכים למרחב הקודם.' : ''}`)
      setError(null); await Promise.all([load(), reload()])
    } catch (err) { setError(err) }
  }

  if (loading) return <Spinner />
  const wsName = (id: string) => workspaces.find(w => w.id === id)?.name ?? '—'
  const shown = (projects ?? []).filter(p => p.status === 'active' && (!filter || p.workspace_id === filter))
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold">מרחבים</h1>
        <p className="text-sm text-slate-500">מרחב הוא הקטגוריה שבה פרויקט מסווג: Comax, פרטי, לקוח, למחיקה. חיבורים ונכסים נשארים במרחב שבו חוברו; פרויקט אפשר להעביר בין מרחבים בכל רגע, והנכסים המשויכים לו נשארים משויכים.</p>
      </div>
      <ErrorBox error={error} />
      {note && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">{note}</div>}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {workspaces.map(w => (
          <div key={w.id} className="tile space-y-3">
            {editing?.id === w.id ? (
              <div className="space-y-2">
                <input className="input" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} aria-label="שם המרחב" />
                <select className="input" value={editing.kind} onChange={e => setEditing({ ...editing, kind: e.target.value })} aria-label="סוג">{Object.entries(workspaceKind).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                <div className="flex gap-2"><button className="btn-primary" onClick={save}><Check className="h-4 w-4" /> שמירה</button><button className="btn-secondary" onClick={() => setEditing(null)}><X className="h-4 w-4" /></button></div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-base font-bold text-slate-900">{w.name}</div>
                  <span className={`chip mt-1 ${kindTint[w.kind] ?? 'bg-slate-100 text-slate-600'}`}>{t(workspaceKind, w.kind)}</span>
                </div>
                <div className="flex gap-1">
                  <button className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100" title="שינוי שם" onClick={() => setEditing({ id: w.id, name: w.name, kind: w.kind })}><Pencil className="h-4 w-4" /></button>
                  <button className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-rose-50 hover:text-rose-700" title="ארכוב (רק כשהמרחב ריק)" onClick={() => archive(w)}><Archive className="h-4 w-4" /></button>
                </div>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 text-center text-xs text-slate-500">
              <button className="rounded-lg bg-slate-50 py-2 hover:bg-white" onClick={() => setFilter(filter === w.id ? '' : w.id)}><FolderKanban className="mx-auto mb-1 h-4 w-4 text-teal-600" /><span className="block text-base font-bold text-slate-900">{w.projects ?? 0}</span>פרויקטים</button>
              <Link to="/connections" className="rounded-lg bg-slate-50 py-2 hover:bg-white"><Link2 className="mx-auto mb-1 h-4 w-4 text-amber-600" /><span className="block text-base font-bold text-slate-900">{w.connections ?? 0}</span>חיבורים</Link>
              <Link to="/assets" className="rounded-lg bg-slate-50 py-2 hover:bg-white"><Boxes className="mx-auto mb-1 h-4 w-4 text-violet-600" /><span className="block text-base font-bold text-slate-900">{w.assets ?? 0}</span>נכסים</Link>
            </div>
          </div>
        ))}
        <form onSubmit={create} className="tile space-y-2 border-dashed">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Plus className="h-4 w-4" /> מרחב חדש</div>
          <Field label="שם"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Corewise" required /></Field>
          <Field label="סוג"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })}>{Object.entries(workspaceKind).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <button className="btn-primary w-full justify-center">יצירה</button>
        </form>
      </div>

      <Card title={<span>סיווג פרויקטים למרחבים{filter && <span className="mr-2 text-xs font-normal text-slate-500">· מסונן: {wsName(filter)} <button className="text-indigo-600" onClick={() => setFilter('')}>הצג הכול</button></span>}</span>}>
        {!projects ? <Spinner /> : shown.length === 0 ? <Empty>אין פרויקטים פעילים{filter ? ' במרחב הזה' : ''}.</Empty> : (
          <ul className="divide-y divide-slate-100">
            {shown.map(p => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
                <div className="min-w-0">
                  <Link to={`/projects/${p.id}`} className="font-semibold text-indigo-700">{p.name}</Link>
                  <span className="mr-2 text-xs text-slate-500">{p.description}</span>
                  <div className="text-xs text-slate-400">כרגע: {wsName(p.workspace_id)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {p.tone && <TonePill tone={p.tone}>{p.tone === 'bad' ? 'כשל' : p.tone === 'warn' ? 'לבדיקה' : 'תקין'}</TonePill>}
                  <select className="input w-48" value={p.workspace_id} onChange={e => move(p, e.target.value)} aria-label={`מרחב עבור ${p.name}`}>
                    {workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
