import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Asset, type CcProjectDetail } from '../../api'
import { Card, Empty, ErrorBox, Field, Mono, Spinner, Stat, Table } from '../../components/ui'
import { EnvPill, EventRow, ExtLink, Facts, ResultPill, TonePill } from '../../components/cc'
import { assetKind, costKind, environment, fmtDate, importance, provider, qty, runStatusCc, sessionStatus, sessionTool, t, usd } from '../../i18n'

type Tab = 'summary' | 'assets' | 'sessions' | 'tools' | 'costs' | 'agents' | 'security'
const tabs: [Tab, string][] = [['summary', 'סקירה'], ['assets', 'נכסים'], ['sessions', 'סשנים'], ['tools', 'כלים ומפתחות'], ['costs', 'עלויות'], ['agents', 'סוכנים'], ['security', 'סקרי אבטחה']]

export default function CcProject() {
  const { id } = useParams()
  const [d, setD] = useState<CcProjectDetail | null>(null)
  const [tab, setTab] = useState<Tab>('summary')
  const [error, setError] = useState<unknown>(null)
  const [edit, setEdit] = useState(false)
  const [allAssets, setAllAssets] = useState<Asset[]>([])

  const load = useCallback(() => api.get<CcProjectDetail>(`/cc/projects/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (d && tab === 'assets') api.get<Asset[]>(`/cc/assets?workspace_id=${d.project.workspace_id}`).then(setAllAssets).catch(setError) }, [d, tab])

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const p = d.project
  const prodFail = d.events.find(e => e.result === 'failure' && e.environment === 'production')
  const lastProd = d.events.find(e => e.environment === 'production' && e.kind === 'deployment')

  async function save(e: FormEvent) {
    e.preventDefault()
    const fd = new FormData(e.target as HTMLFormElement)
    try { await api.patch(`/cc/projects/${id}`, { name: fd.get('name'), description: fd.get('description'), owner: fd.get('owner'), importance: fd.get('importance'), environment: fd.get('environment'), budget_usd: Number(fd.get('budget_usd')), default_key_id: fd.get('default_key_id') || null }); setEdit(false); load() } catch (err) { setError(err) }
  }
  async function assign(assetId: string) { try { await api.post(`/cc/projects/${id}/assets`, { asset_id: assetId }); load() } catch (err) { setError(err) } }
  async function unassign(assetId: string) { try { await api.del(`/cc/projects/${id}/assets/${assetId}`); load() } catch (err) { setError(err) } }
  async function newSession(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.post('/cc/sessions', { project_id: id, title: fd.get('title'), goal: fd.get('goal'), tool: fd.get('tool') }); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function runAgent(agentId: string) {
    try { const r = await api.post<{ id: string }>(`/cc/agents/${agentId}/runs`, { project_id: id, idempotency_key: `${agentId}:${Date.now()}` }); window.location.hash = ''; load(); window.location.assign(`/agents/runs/${r.id}`) } catch (err) { setError(err) }
  }
  async function linkPt(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try {
      let ptId = String(fd.get('pt_project_id') || '')
      if (!ptId) { const created = await api.post<{ id: string }>('/pt/projects', { name: p.name, description: `סקר אבטחה עבור ${p.name}` }); ptId = created.id }
      await api.post(`/cc/projects/${id}/pt`, { pt_project_id: ptId }); load()
    } catch (err) { setError(err) }
  }

  const assigned = new Set(d.assets.map(a => a.id))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to="/projects" className="text-xs text-indigo-600">← לכל הפרויקטים</Link>
          <h1 className="flex items-center gap-3 text-xl font-bold">{p.name} <TonePill tone={prodFail ? 'bad' : 'ok'}>{prodFail ? 'כשל בייצור' : 'ייצור תקין'}</TonePill></h1>
          <p className="text-sm text-slate-500">{p.description || <Mono>{p.id}</Mono>}</p>
        </div>
        <button className="btn-secondary" onClick={() => setEdit(v => !v)}>עריכה</button>
      </div>
      <ErrorBox error={error} />
      {edit && (
        <Card title="עריכת פרויקט">
          <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
            <Field label="שם"><input className="input" name="name" defaultValue={p.name} required /></Field>
            <Field label="בעלים"><input className="input" name="owner" defaultValue={p.owner} /></Field>
            <Field label="תיאור"><input className="input" name="description" defaultValue={p.description} /></Field>
            <Field label="חשיבות"><select className="input" name="importance" defaultValue={p.importance}>{Object.entries(importance).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="סביבה"><select className="input" name="environment" defaultValue={p.environment}>{Object.entries(environment).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="תקציב חודשי ($)"><input className="input ltr" type="number" name="budget_usd" defaultValue={p.budget_usd ?? 0} /></Field>
            <Field label="מפתח AI ברירת מחדל"><select className="input" name="default_key_id" defaultValue={p.default_key_id ?? ''}><option value="">ללא</option>{d.keys.map(k => <option key={k.id} value={k.id}>{k.name} · {k.masked}</option>)}</select></Field>
            <div className="md:col-span-3 text-xs text-slate-500">שינוי מרחב מתבצע דרך אשף העברה נפרד. סודות והרשאות לא עוברים עם השיוך.</div>
            <div className="md:col-span-3"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">{tabs.map(([k, label]) => <button key={k} className={`btn-secondary ${tab === k ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab(k)}>{label}</button>)}</div>

      {tab === 'summary' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="נכסים" value={d.assets.length} />
            <Stat label="הוצאות החודש" value={usd(d.cost_month_usd)} hint={p.budget_usd ? `תקציב ${usd(p.budget_usd)} · ניצול ${Math.round(100 * d.cost_month_usd / p.budget_usd)}%` : 'ללא תקציב'} tone={p.budget_usd && d.cost_month_usd > p.budget_usd ? 'rose' : 'slate'} />
            <Stat label="סשנים פתוחים" value={d.sessions.filter(s => s.status === 'open').length} />
            <Stat label="ריצות סוכן" value={d.runs.length} />
          </div>
          <Facts items={[['בעלים', p.owner || '—'], ['חשיבות', t(importance, p.importance)], ['סביבה', t(environment, p.environment)], ['פריסת ייצור אחרונה', lastProd ? <span>{fmtDate(lastProd.occurred_at)} <ResultPill value={lastProd.result} /></span> : 'אין דיווח']]} />
          <Card title="פעילות הפרויקט">
            {d.events.length === 0 ? <Empty>אין פעילות. שייך נכסים לפרויקט כדי לראות פריסות וריצות.</Empty> : <ul className="divide-y divide-slate-100">{d.events.slice(0, 20).map(e => <EventRow key={e.id} e={e} />)}</ul>}
          </Card>
        </div>
      )}

      {tab === 'assets' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="נכסים בפרויקט">
            {d.assets.length === 0 ? <Empty>אין נכסים משויכים.</Empty> : (
              <Table head={['נכס', 'סוג', 'סביבה', 'מצב', '']}>
                {d.assets.map(a => <tr key={a.id}><td className="px-3 py-2"><Link to={`/assets/${a.id}`} className="text-indigo-700"><bdi>{a.name}</bdi></Link><div className="text-xs text-slate-500">{a.description}</div></td><td className="px-3 py-2 text-xs">{t(assetKind, a.kind)} · {t(provider, a.provider)}</td><td className="px-3 py-2"><EnvPill value={a.environment} /></td><td className="px-3 py-2 text-xs"><bdi>{a.state}</bdi></td><td className="px-3 py-2"><button className="text-xs text-rose-700" onClick={() => unassign(a.id)}>הסר שיוך</button></td></tr>)}
              </Table>
            )}
          </Card>
          <Card title="שיוך נכס מהקטלוג">
            {allAssets.filter(a => !assigned.has(a.id)).length === 0 ? <Empty>כל הנכסים במרחב כבר משויכים, או שאין חיבורים.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">
                {allAssets.filter(a => !assigned.has(a.id)).map(a => <li key={a.id} className="flex items-center justify-between py-2"><span><bdi>{a.name}</bdi> <span className="text-xs text-slate-500">{t(assetKind, a.kind)}</span></span><button className="btn-secondary" onClick={() => assign(a.id)}>שייך</button></li>)}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'sessions' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="סשן חדש">
            <form onSubmit={newSession} className="space-y-3">
              <Field label="כותרת"><input className="input" name="title" required /></Field>
              <Field label="מטרה"><input className="input" name="goal" /></Field>
              <Field label="כלי עבודה"><select className="input" name="tool">{Object.entries(sessionTool).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <button className="btn-primary w-full justify-center">פתיחת סשן</button>
            </form>
          </Card>
          <Card title="סשנים בפרויקט" className="lg:col-span-2">
            {d.sessions.length === 0 ? <Empty>אין סשנים.</Empty> : (
              <Table head={['כותרת', 'כלי', 'סטטוס', 'התחלה', 'תוצר']}>
                {d.sessions.slice().reverse().map(s => <tr key={s.id}><td className="px-3 py-2"><Link to={`/sessions/${s.id}`} className="text-indigo-700">{s.title}</Link><div className="text-xs text-slate-500">{s.goal}</div></td><td className="px-3 py-2 text-xs">{t(sessionTool, s.tool)}</td><td className="px-3 py-2 text-xs">{t(sessionStatus, s.status)}</td><td className="px-3 py-2 text-xs">{fmtDate(s.started_at)}</td><td className="px-3 py-2 text-xs">{s.outcome || '—'}</td></tr>)}
              </Table>
            )}
          </Card>
        </div>
      )}

      {tab === 'tools' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="כלים מחוברים לפרויקט">
            {d.connections.length === 0 ? <Empty>אין כלים. שייך נכסים מחיבור כדי לראות אותו כאן.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">
                {Array.from(new Map(d.connections.map(c => [c.id, c])).values()).map(c => <li key={c.id} className="flex items-center justify-between py-2"><span>{t(provider, c.provider)} · {c.account_label}</span><span className="text-xs text-slate-500">{c.capabilities?.join(' · ')} · <Link to="/connections" className="text-indigo-700">פרטי חיבור</Link></span></li>)}
              </ul>
            )}
            <h3 className="mt-4 text-xs font-semibold text-slate-600">קישורי מקור</h3>
            <div className="mt-2 flex flex-wrap gap-2">{d.assets.filter(a => a.url).map(a => <ExtLink key={a.id} href={a.url}>{a.name}</ExtLink>)}</div>
          </Card>
          <Card title="מפתח AI של הפרויקט">
            {p.default_key_id ? (() => { const k = d.keys.find(x => x.id === p.default_key_id); return k ? <Facts items={[['שם', k.name], ['חשבון', k.account_label || '—'], ['סיומת', <Mono>{k.masked}</Mono>], ['הרשאה', k.scope]]} /> : <Empty>המפתח שנבחר אינו קיים עוד.</Empty> })() : <Empty>לא נבחר מפתח ברירת מחדל. אפשר לבחור ב"עריכה".</Empty>}
            <p className="mt-3 text-xs text-slate-500">המפתח האמיתי נשמר מוצפן בשרת. ריצה מאמתת מחדש את היקף המפתח לפני הפעלה.</p>
          </Card>
        </div>
      )}

      {tab === 'costs' && (
        <Card title="עלויות הפרויקט">
          <Facts items={[['תקופה', 'חודש נוכחי'], ['סך משויך החודש', usd(d.cost_month_usd)], ['תקציב', p.budget_usd ? usd(p.budget_usd) : 'ללא'], ['רשומות', d.costs.length]]} />
          <div className="mt-4">
            {d.costs.length === 0 ? <Empty>אין רשומות עלות. ריצות סוכן יוצרות אומדן אוטומטית; חיובים מדווחים נוספים במסך העלויות.</Empty> : (
              <Table head={['ספק', 'סוג', 'סכום', 'תקופה', 'טוקנים', 'הערה']}>
                {d.costs.slice().reverse().map(c => <tr key={c.id}><td className="px-3 py-2 text-sm">{c.provider}</td><td className="px-3 py-2 text-xs">{t(costKind, c.kind)}</td><td className="px-3 py-2"><bdi>{usd(c.amount)}</bdi></td><td className="px-3 py-2 text-xs">{c.period_start} – {c.period_end}</td><td className="px-3 py-2 text-xs">{c.tokens_in || c.tokens_out ? `${qty(c.tokens_in)} / ${qty(c.tokens_out)}` : '—'}</td><td className="px-3 py-2 text-xs">{c.note}</td></tr>)}
              </Table>
            )}
          </div>
        </Card>
      )}

      {tab === 'agents' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="סוכנים זמינים לפרויקט" actions={<Link to="/agents" className="text-xs text-indigo-600">מרכז הסוכנים</Link>}>
            {d.agents.length === 0 ? <Empty>אין סוכנים. צור סוכן במרכז הסוכנים.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">
                {d.agents.map(a => <li key={a.id} className="flex items-center justify-between py-2"><span>{a.name} <span className="text-xs text-slate-500">{a.project_id ? 'ייעודי' : 'כללי'} · {a.model} · v{a.version}</span></span><button className="btn-primary" disabled={!a.enabled} onClick={() => runAgent(a.id)}>הפעל</button></li>)}
              </ul>
            )}
          </Card>
          <Card title="ריצות אחרונות">
            {d.runs.length === 0 ? <Empty>אין ריצות.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">
                {d.runs.slice().reverse().map(r => <li key={r.id} className="flex items-center justify-between py-2"><Link to={`/agents/runs/${r.id}`} className="text-indigo-700">{r.agent_name ?? r.agent_id}</Link><span className="text-xs text-slate-500">{fmtDate(r.created_at)} · {t(runStatusCc, r.status)} · {usd(r.cost_usd ?? 0)}</span></li>)}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'security' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="סקרי אבטחה מקושרים">
            {d.pt_projects.length === 0 ? <Empty>אין סקר אבטחה מקושר לפרויקט הזה.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">{d.pt_projects.map(x => <li key={x.id} className="flex items-center justify-between py-2"><Link to={`/security/projects/${x.id}`} className="text-indigo-700">{x.name}</Link><span className="text-xs text-slate-500">{fmtDate(x.created_at)}</span></li>)}</ul>
            )}
          </Card>
          <Card title="קישור סקר">
            <form onSubmit={linkPt} className="space-y-3">
              <Field label="מזהה פרויקט סקר קיים (ריק = יצירת סקר חדש בשם הפרויקט)"><input className="input ltr" name="pt_project_id" placeholder="prj_…" /></Field>
              <button className="btn-primary">קישור</button>
            </form>
            <p className="mt-3 text-xs text-slate-500">הסקר עצמו מנוהל במודול "סקרי אבטחה": מסמך הרשאה, היקף, ריצה, ממצאים ודוחות.</p>
          </Card>
        </div>
      )}
    </div>
  )
}
