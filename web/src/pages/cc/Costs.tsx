import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type CcProject, type CostEntry, type ProviderKey } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { costKind, fmtDate, provider as providerLabels, qty, t, usd } from '../../i18n'
import { useWorkspace } from '../../workspace'

interface CostsData { entries: CostEntry[]; total_usd: number; includes_estimates: boolean; estimates_usd: number; tokens: number }

export default function Costs() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [data, setData] = useState<CostsData | null>(null)
  const [projects, setProjects] = useState<CcProject[]>([])
  const [keys, setKeys] = useState<ProviderKey[]>([])
  const [error, setError] = useState<unknown>(null)
  const [tab, setTab] = useState<'entries' | 'keys'>('entries')

  const load = () => Promise.all([api.get<CostsData>(`/cc/costs${qs}`), api.get<CcProject[]>(`/cc/projects${qs}`), api.get<ProviderKey[]>(`/cc/keys${qs}`)])
    .then(([c, p, k]) => { setData(c); setProjects(p); setKeys(k) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])

  async function addCost(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post('/cc/costs', { workspace_id: fd.get('workspace_id'), project_id: fd.get('project_id') || null, provider: fd.get('provider'), kind: fd.get('kind'), amount: Number(fd.get('amount')), currency: fd.get('currency'), period_start: fd.get('period_start') || null, period_end: fd.get('period_end') || null, note: fd.get('note'), source_ref: fd.get('source_ref') }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function addKey(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post('/cc/keys', { workspace_id: fd.get('workspace_id'), name: fd.get('name'), provider: fd.get('provider'), account_label: fd.get('account_label'), secret: fd.get('secret') }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function rotate(k: ProviderKey) {
    const secret = prompt(`מפתח חדש עבור ${k.name}. ישפיע על: פרויקטים ${k.used_by_projects?.join(', ') || '—'}; סוכנים ${k.used_by_agents?.join(', ') || '—'}`)
    if (!secret) return
    try { await api.post(`/cc/keys/${k.id}/rotate`, { secret }); load() } catch (err) { setError(err) }
  }

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  const pname = (id?: string | null) => projects.find(p => p.id === id)?.name ?? '—'
  const byProject: Record<string, number> = {}
  data?.entries.forEach(c => { const k = c.project_id ?? '_'; byProject[k] = (byProject[k] ?? 0) + Number(c.amount) })
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">עלויות ושימוש</h1><p className="text-sm text-slate-500">חיובים, הקצאות וצריכת טוקנים לפי פרויקט. סכום מאוחד מציין אם הוא כולל אומדנים.</p></div>
      <ErrorBox error={error} />
      {data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="סך משויך" value={usd(data.total_usd)} hint={data.includes_estimates ? `כולל אומדנים ${usd(data.estimates_usd)}` : 'ללא אומדנים'} tone="indigo" />
          <Stat label="טוקני AI מדווחים" value={qty(data.tokens)} />
          <Stat label="רשומות" value={data.entries.length} />
          <Stat label="מפתחות ספק" value={keys.length} />
        </div>
      )}
      <div className="flex gap-2"><button className={`btn-secondary ${tab === 'entries' ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab('entries')}>פירוט לפי שירות</button><button className={`btn-secondary ${tab === 'keys' ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab('keys')}>מפתחות וזהויות (9.2)</button></div>

      {tab === 'entries' && (
        <>
          <Card title="לפי פרויקט">
            {Object.keys(byProject).length === 0 ? <Empty>אין רשומות.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{Object.entries(byProject).map(([pid, amt]) => <li key={pid} className="flex items-center justify-between py-2">{pid === '_' ? <span>לא משויך לפרויקט</span> : <Link to={`/projects/${pid}`} className="text-indigo-700">{pname(pid)}</Link>}<bdi className="font-semibold">{usd(amt)}</bdi></li>)}</ul>}
          </Card>
          <Card title="רשומות">
            {!data ? <Spinner /> : data.entries.length === 0 ? <Empty>אין רשומות עלות.</Empty> : (
              <Table head={['ספק', 'פרויקט', 'סוג', 'סכום', 'תקופה', 'טוקנים', 'מקור / הערה', 'נקלט']}>
                {data.entries.slice().reverse().map(c => <tr key={c.id}><td className="px-3 py-2 text-sm">{t(providerLabels, c.provider)}</td><td className="px-3 py-2 text-xs">{pname(c.project_id)}</td><td className="px-3 py-2"><span className={`badge ${c.kind === 'estimate' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100'}`}>{t(costKind, c.kind)}</span></td><td className="px-3 py-2"><bdi>{usd(c.amount)}</bdi> {c.currency !== 'USD' && <span className="text-xs">{c.currency}</span>}</td><td className="px-3 py-2 text-xs">{c.period_start} – {c.period_end}</td><td className="px-3 py-2 text-xs">{c.tokens_in || c.tokens_out ? `${qty(c.tokens_in)} / ${qty(c.tokens_out)}${c.model ? ` · ${c.model}` : ''}` : '—'}</td><td className="px-3 py-2 text-xs">{c.note}{c.run_id && <Link to={`/agents/runs/${c.run_id}`} className="mr-1 text-indigo-700">ריצה</Link>}</td><td className="px-3 py-2 text-xs">{fmtDate(c.created_at)}</td></tr>)}
              </Table>
            )}
          </Card>
          <Card title="הוספת חיוב / הקצאה / מנוי">
            <form key={current?.id ?? 'all'} onSubmit={addCost} className="grid gap-3 md:grid-cols-4">
              <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={current?.id ?? workspaces[0].id}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
              <Field label="פרויקט"><select className="input" name="project_id"><option value="">לא משויך</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
              <Field label="ספק"><input className="input" name="provider" required placeholder="Vercel / OpenAI / Supabase" /></Field>
              <Field label="סוג"><select className="input" name="kind">{Object.entries(costKind).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="סכום"><input className="input ltr" name="amount" type="number" min={0} step="0.01" required /></Field>
              <Field label="מטבע"><input className="input ltr" name="currency" defaultValue="USD" /></Field>
              <Field label="מתאריך"><input className="input ltr" name="period_start" type="date" /></Field>
              <Field label="עד תאריך"><input className="input ltr" name="period_end" type="date" /></Field>
              <Field label="אסמכתה"><input className="input ltr" name="source_ref" placeholder="מספר חשבונית / קישור" /></Field>
              <Field label="הערה / כלל הקצאה"><input className="input" name="note" /></Field>
              <div className="flex items-end"><button className="btn-primary">הוספה</button></div>
            </form>
          </Card>
        </>
      )}

      {tab === 'keys' && (
        <>
          <Card title="מפתחות גישה לספקי AI">
            <p className="mb-2 text-xs text-slate-500">"מפתח גישה" מזהה איזה חשבון והרשאה משמשים את הפרויקט. "טוקני שימוש" הם יחידות מדידה לצריכה. המפתח האמיתי נשמר מוצפן בשרת; כאן רואים סיומת ממוסכת בלבד.</p>
            {keys.length === 0 ? <Empty>אין מפתחות.</Empty> : (
              <Table head={['שם', 'ספק', 'חשבון', 'סיומת', 'הרשאה', 'גרסה', 'בשימוש', '']}>
                {keys.map(k => <tr key={k.id}><td className="px-3 py-2 font-medium">{k.name}</td><td className="px-3 py-2 text-xs">{t(providerLabels, k.provider)}</td><td className="px-3 py-2 text-xs">{k.account_label || '—'}</td><td className="px-3 py-2"><span className="mono text-xs">{k.masked}</span></td><td className="px-3 py-2 text-xs">{k.scope}</td><td className="px-3 py-2 text-xs">v{k.version ?? 1}</td><td className="px-3 py-2 text-xs">{[...(k.used_by_projects ?? []), ...(k.used_by_agents ?? [])].join(', ') || '—'}</td><td className="px-3 py-2"><button className="btn-secondary" onClick={() => rotate(k)}>סבב מפתח</button></td></tr>)}
              </Table>
            )}
          </Card>
          <Card title="הוספת מפתח">
            <form key={current?.id ?? 'all'} onSubmit={addKey} className="grid gap-3 md:grid-cols-5">
              <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={current?.id ?? workspaces[0].id}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
              <Field label="שם"><input className="input" name="name" required placeholder="Anthropic · BuildFlow" /></Field>
              <Field label="ספק"><select className="input" name="provider"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option><option value="other">אחר</option></select></Field>
              <Field label="חשבון ספק"><input className="input" name="account_label" /></Field>
              <Field label="המפתח"><input className="input ltr" name="secret" type="password" required autoComplete="off" /></Field>
              <div className="md:col-span-5"><button className="btn-primary">שמירה מוצפנת</button></div>
            </form>
          </Card>
        </>
      )}
    </div>
  )
}
