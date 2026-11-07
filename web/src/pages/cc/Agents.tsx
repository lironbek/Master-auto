import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api, type AgentRun, type CcAgent, type CcProject, type ProviderKey } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtDate, runStatusCc, t, usd } from '../../i18n'
import { useWorkspace } from '../../workspace'

const MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']

export default function Agents() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const nav = useNavigate()
  const [agents, setAgents] = useState<CcAgent[] | null>(null)
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [projects, setProjects] = useState<CcProject[]>([])
  const [keys, setKeys] = useState<ProviderKey[]>([])
  const [error, setError] = useState<unknown>(null)
  const [editing, setEditing] = useState<Partial<CcAgent> | null>(null)
  const [runFor, setRunFor] = useState<Record<string, string>>({})

  const load = () => Promise.all([api.get<CcAgent[]>(`/cc/agents${qs}`), api.get<AgentRun[]>(`/cc/runs${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`), api.get<ProviderKey[]>(`/cc/keys${qs}`)])
    .then(([a, r, p, k]) => { setAgents(a); setRuns(r); setProjects(p); setKeys(k) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])

  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { workspace_id: fd.get('workspace_id'), project_id: fd.get('project_id') || null, name: fd.get('name'), instructions: fd.get('instructions'), owner: editing?.owner ?? '', provider: 'anthropic', model: fd.get('model'), key_id: fd.get('key_id') || null, tools: ['catalog.read'], allowed_projects: Array.from(fd.getAll('allowed_projects')).map(String), limits: { max_steps: Number(fd.get('max_steps')), max_seconds: Number(fd.get('max_seconds')), max_tokens: Number(fd.get('max_tokens')), max_cost_usd: Math.max(0, Number(fd.get('max_cost_usd'))) }, approval_rule: 'read_only', enabled: fd.get('enabled') === 'on' }
    try { if (editing?.id) await api.patch(`/cc/agents/${editing.id}`, body); else await api.post('/cc/agents', body); setEditing(null); load() } catch (err) { setError(err) }
  }
  async function run(a: CcAgent) {
    const pid = a.project_id || runFor[a.id]
    if (!pid) { setError(new Error('בחר פרויקט להרצה')); return }
    try { const r = await api.post<AgentRun>(`/cc/agents/${a.id}/runs`, { project_id: pid, idempotency_key: `${a.id}:${pid}:${Math.floor(Date.now() / 5000)}` }); nav(`/agents/runs/${r.id}`) } catch (err) { setError(err) }
  }

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const wsId = editing?.workspace_id || current?.id || workspaces[0].id
  const wsProjects = projects.filter(p => p.workspace_id === wsId)
  const wsKeys = keys.filter(k => k.workspace_id === wsId)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold">מרכז הסוכנים</h1><p className="text-sm text-slate-500">סוכנים כלליים במרחב וסוכנים ייעודיים לפרויקט. ברירת מחדל: פעולות קריאה בלבד.</p></div>
        <button className="btn-primary" onClick={() => setEditing({})}><Plus className="h-4 w-4" /> סוכן חדש</button>
      </div>
      <ErrorBox error={error} />
      {editing && (
        <Card title={editing.id ? `עריכת ${editing.name}` : 'הגדרת סוכן'} actions={<button className="btn-secondary" onClick={() => setEditing(null)}>ביטול</button>}>
          <form key={editing.id ?? current?.id ?? 'new'} onSubmit={save} className="grid gap-3 md:grid-cols-3">
            <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={wsId} disabled={!!editing.id} onChange={e => setEditing({ ...editing, workspace_id: e.target.value })}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>{editing.id && <input type="hidden" name="workspace_id" value={editing.workspace_id} />}</Field>
            <Field label="שם"><input className="input" name="name" defaultValue={editing.name} required maxLength={80} /></Field>
            <Field label="שיוך"><select className="input" name="project_id" defaultValue={editing.project_id ?? ''}><option value="">סוכן כללי במרחב</option>{wsProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="הוראות משימה" ><textarea className="input md:col-span-3" name="instructions" rows={3} defaultValue={editing.instructions} maxLength={4000} placeholder="סכם חריגות, פריסות אחרונות ועלויות של הפרויקט." /></Field>
            <Field label="מודל"><select className="input ltr" name="model" defaultValue={editing.model ?? MODELS[0]}>{MODELS.map(m => <option key={m}>{m}</option>)}</select></Field>
            <Field label="מפתח ספק" hint="ריק = מפתח הסביבה אם קיים, אחרת סיכום דטרמיניסטי"><select className="input" name="key_id" defaultValue={editing.key_id ?? ''}><option value="">ללא</option>{wsKeys.map(k => <option key={k.id} value={k.id}>{k.name} · {k.masked}</option>)}</select></Field>
            <div className="md:col-span-3"><span className="label">פרויקטים מותרים לסוכן כללי (ריק = כל הפרויקטים במרחב)</span><div className="flex flex-wrap gap-3 text-sm">{wsProjects.map(p => <label key={p.id} className="flex items-center gap-1"><input type="checkbox" name="allowed_projects" value={p.id} defaultChecked={editing.allowed_projects?.includes(p.id)} /> {p.name}</label>)}</div></div>
            <Field label="מגבלת צעדים"><input className="input ltr" type="number" name="max_steps" defaultValue={editing.limits?.max_steps ?? 10} /></Field>
            <Field label="מגבלת זמן (שניות)"><input className="input ltr" type="number" name="max_seconds" defaultValue={editing.limits?.max_seconds ?? 120} /></Field>
            <Field label="מגבלת טוקנים"><input className="input ltr" type="number" name="max_tokens" defaultValue={editing.limits?.max_tokens ?? 20000} /></Field>
            <Field label="תקרת עלות לריצה ($)"><input className="input ltr" type="number" min={0} step="0.01" name="max_cost_usd" defaultValue={editing.limits?.max_cost_usd ?? 1} /></Field>
            <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" name="enabled" defaultChecked={editing.enabled ?? true} /> פעיל</label>
            <div className="md:col-span-3 text-xs text-slate-500">פעולה שמשנה מערכת חיצונית דורשת יכולת ייעודית ואישור של הפעולה והיעד. המודל אינו יכול להרחיב את היקף ההרשאה. שמירה יוצרת גרסת הגדרה.</div>
            <div className="md:col-span-3"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}
      <Card title="סוכנים">
        {!agents ? <Spinner /> : agents.length === 0 ? <Empty>אין סוכנים.</Empty> : (
          <Table head={['שם', 'שיוך', 'מודל', 'מפתח', 'מצב', 'גרסה', 'הרצה', '']}>
            {agents.map(a => <tr key={a.id}>
              <td className="px-3 py-2 font-medium">{a.name}<div className="text-xs text-slate-500">{a.instructions?.slice(0, 80)}</div></td>
              <td className="px-3 py-2 text-xs">{a.project_id ? `ייעודי: ${projects.find(p => p.id === a.project_id)?.name ?? a.project_id}` : 'כללי במרחב'}</td>
              <td className="px-3 py-2"><span className="mono text-xs">{a.model}</span></td>
              <td className="px-3 py-2 text-xs">{keys.find(k => k.id === a.key_id)?.name ?? 'סביבה / ללא'}</td>
              <td className="px-3 py-2"><span className={`badge ${a.enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>{a.enabled ? 'פעיל' : 'מושהה'}</span></td>
              <td className="px-3 py-2 text-xs">v{a.version}</td>
              <td className="px-3 py-2"><div className="flex gap-1">{!a.project_id && <select className="input w-40" value={runFor[a.id] ?? ''} onChange={e => setRunFor({ ...runFor, [a.id]: e.target.value })}><option value="">פרויקט…</option>{projects.filter(p => p.workspace_id === a.workspace_id && (!a.allowed_projects?.length || a.allowed_projects.includes(p.id))).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}<button className="btn-primary" disabled={!a.enabled} onClick={() => run(a)}>הפעל</button></div></td>
              <td className="px-3 py-2"><button className="btn-secondary" onClick={() => setEditing(a)}>עריכה</button></td>
            </tr>)}
          </Table>
        )}
      </Card>
      <Card title="היסטוריית ריצות">
        {runs.length === 0 ? <Empty>אין ריצות.</Empty> : (
          <Table head={['ריצה', 'סוכן', 'פרויקט', 'סטטוס', 'עלות', 'התחלה', '']}>
            {runs.map(r => <tr key={r.id}><td className="px-3 py-2"><span className="mono text-xs">{r.id}</span></td><td className="px-3 py-2 text-sm">{r.agent_name}</td><td className="px-3 py-2 text-xs">{projects.find(p => p.id === r.project_id)?.name ?? r.project_id}</td><td className="px-3 py-2"><span className={`badge ${r.status === 'completed' ? 'bg-emerald-100 text-emerald-800' : r.status === 'failed' ? 'bg-rose-100 text-rose-800' : 'bg-slate-100'}`}>{t(runStatusCc, r.status)}</span></td><td className="px-3 py-2 text-xs"><bdi>{usd(r.cost_usd ?? 0)}</bdi></td><td className="px-3 py-2 text-xs">{fmtDate(r.created_at)}</td><td className="px-3 py-2"><Link to={`/agents/runs/${r.id}`} className="text-xs text-indigo-700">לתוצאה</Link></td></tr>)}
          </Table>
        )}
      </Card>
    </div>
  )
}
