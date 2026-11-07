import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Asset, type CcClient, type CcProjectDetail, type ProjectScan } from '../../api'
import { Card, Empty, ErrorBox, Field, Mono, Spinner, Stat, Table } from '../../components/ui'
import { EnvPill, EventRow, ExtLink, Facts, ResultPill, TonePill } from '../../components/cc'
import { assetKind, costKind, environment, fmtDate, importance, metricLabel, provider, qty, runStatusCc, sessionStatus, sessionTool, t, usageProvider, usd } from '../../i18n'

type Tab = 'summary' | 'build' | 'scans' | 'assets' | 'sessions' | 'tools' | 'costs' | 'agents' | 'security'
const tabs: [Tab, string][] = [['summary', 'סקירה'], ['build', 'איך הוא בנוי'], ['scans', 'סריקות'], ['assets', 'נכסים'], ['sessions', 'סשנים'], ['tools', 'כלים ומפתחות'], ['costs', 'עלויות'], ['agents', 'סוכנים'], ['security', 'סקרי אבטחה']]
const sevTone: Record<string, string> = { high: 'bg-rose-100 text-rose-800', medium: 'bg-amber-100 text-amber-800', low: 'bg-sky-100 text-sky-800', info: 'bg-slate-100 text-slate-600' }
const sevLabel: Record<string, string> = { high: 'גבוה', medium: 'בינוני', low: 'נמוך', info: 'מידע' }
const gradeTone: Record<string, string> = { A: 'bg-emerald-100 text-emerald-800', B: 'bg-amber-100 text-amber-800', C: 'bg-rose-100 text-rose-800' }

export default function CcProject() {
  const { id } = useParams()
  const [d, setD] = useState<CcProjectDetail | null>(null)
  const [tab, setTab] = useState<Tab>('summary')
  const [error, setError] = useState<unknown>(null)
  const [edit, setEdit] = useState(false)
  const [allAssets, setAllAssets] = useState<Asset[]>([])
  const [clients, setClients] = useState<CcClient[]>([])
  const [busy, setBusy] = useState<'profile' | 'scan' | null>(null)
  const [scan, setScan] = useState<ProjectScan | null>(null)

  const load = useCallback(() => api.get<CcProjectDetail>(`/cc/projects/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (d && tab === 'assets') api.get<Asset[]>(`/cc/assets?workspace_id=${d.project.workspace_id}`).then(setAllAssets).catch(setError) }, [d, tab])
  useEffect(() => { if (d && edit) api.get<CcClient[]>(`/cc/clients?workspace_id=${d.project.workspace_id}`).then(setClients).catch(setError) }, [d, edit])

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const p = d.project
  // Production state follows the newest production event (events are newest
  // first): an old failure must not outlive a later successful deploy.
  const latestProd = d.events.find(e => e.environment === 'production')
  const prodFail = latestProd && latestProd.result === 'failure' ? latestProd : undefined
  const lastProd = d.events.find(e => e.environment === 'production' && e.kind === 'deployment')

  async function save(e: FormEvent) {
    e.preventDefault()
    const fd = new FormData(e.target as HTMLFormElement)
    // default_key_id: "" clears the key (null would mean "no change" to the server)
    try { await api.patch(`/cc/projects/${id}`, { name: fd.get('name'), description: fd.get('description'), owner: fd.get('owner'), importance: fd.get('importance'), environment: fd.get('environment'), status: fd.get('status'), budget_usd: Number(fd.get('budget_usd')), default_key_id: String(fd.get('default_key_id') ?? ''), client_id: String(fd.get('client_id') ?? '') }); setEdit(false); load() } catch (err) { setError(err) }
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
  async function refreshProfile() {
    setBusy('profile'); setError(null)
    try { await api.post(`/cc/projects/${id}/profile`); await load() } catch (err) { setError(err) } finally { setBusy(null) }
  }
  async function runScan(kind: 'health' | 'code' = 'health') {
    setBusy('scan'); setError(null)
    try { const s = await api.post<ProjectScan>(`/cc/projects/${id}/scan?kind=${kind}`); setScan(s); await load() } catch (err) { setError(err) } finally { setBusy(null) }
  }
  async function openScan(scanId: string) {
    try { setScan(await api.get<ProjectScan>(`/cc/scans/${scanId}`)) } catch (err) { setError(err) }
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
          <h1 className="flex items-center gap-3 text-xl font-bold">{p.name} <TonePill tone={prodFail ? 'bad' : 'ok'}>{prodFail ? 'כשל בייצור' : 'ייצור תקין'}</TonePill>{d.project.last_scan_grade && <button className={`badge ${gradeTone[d.project.last_scan_grade] ?? 'bg-slate-100'}`} onClick={() => setTab('scans')}>סריקה {d.project.last_scan_grade}</button>}{p.status === 'archived' && <span className="badge bg-slate-200 text-slate-600">בארכיון</span>}</h1>
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
            <Field label="תקציב חודשי ($)"><input className="input ltr" type="number" min={0} step="0.01" name="budget_usd" defaultValue={p.budget_usd ?? 0} /></Field>
            <Field label="סטטוס"><select className="input" name="status" defaultValue={p.status}><option value="active">פעיל</option><option value="archived">ארכיון</option></select></Field>
            <Field label="לקוח" hint="שימוש ב-API שמדווח לפרויקט נזקף ללקוח הזה"><select className="input" name="client_id" defaultValue={p.client_id ?? ''}><option value="">ללא לקוח</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
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
          <Facts items={[['בעלים', p.owner || '—'], ['לקוח', d.client ? <Link to="/usage" className="text-indigo-700">{d.client.name}</Link> : 'ללא לקוח'], ['חשיבות', t(importance, p.importance)], ['סביבה', t(environment, p.environment)], ['פריסת ייצור אחרונה', lastProd ? <span>{fmtDate(lastProd.occurred_at)} <ResultPill value={lastProd.result} /></span> : 'אין דיווח']]} />
          {d.usage_month && Object.keys(d.usage_month.totals).length > 0 && (
            <Card title="שימוש החודש (API, הודעות, OCR)" actions={<Link to="/usage" className="text-xs text-indigo-600">שימוש לפי לקוח</Link>}>
              <div className="flex flex-wrap gap-2">{Object.entries(d.usage_month.totals).map(([m, v]) => <span key={m} className="badge bg-slate-100 text-slate-700"><bdi>{qty(v)}</bdi> {t(metricLabel, m)}</span>)}</div>
              <ul className="mt-3 divide-y divide-slate-100 text-sm">{d.usage_month.by_interface.map(i => <li key={`${i.interface}|${i.provider}`} className="flex flex-wrap items-center justify-between gap-2 py-1.5"><span><span className="mono text-xs">{i.interface || '—'}</span> · {t(usageProvider, i.provider)}</span><span className="flex flex-wrap gap-1">{Object.entries(i.metrics).map(([m, v]) => <span key={m} className="badge bg-slate-50 text-slate-600"><bdi>{qty(v)}</bdi> {t(metricLabel, m)}</span>)}</span></li>)}</ul>
            </Card>
          )}
          <Card title="פעילות הפרויקט">
            {d.events.length === 0 ? <Empty>אין פעילות. שייך נכסים לפרויקט כדי לראות פריסות וריצות.</Empty> : <ul className="divide-y divide-slate-100">{d.events.slice(0, 20).map(e => <EventRow key={e.id} e={e} />)}</ul>}
          </Card>
        </div>
      )}

      {tab === 'build' && (
        <div className="space-y-4">
          <Card title="איך הפרויקט בנוי" actions={<button className="btn-secondary" disabled={busy !== null} onClick={refreshProfile}>{busy === 'profile' ? 'אוסף…' : (d.profile?.at ? 'רענן פרופיל' : 'בנה פרופיל')}</button>}>
            {!d.profile?.summary ? <Empty>עדיין לא נבנה פרופיל. "בנה פרופיל" קורא מהספקים (קריאה בלבד) את המבנה של כל נכס: שפות, מסגרת, תלויות, CI, בדיקות, הגדרות Vercel, סכימת Supabase.</Empty> : (
              <>
                <pre className="whitespace-pre-wrap text-sm">{d.profile.summary.text}</pre>
                <div className="mt-3 flex flex-wrap gap-2">{d.profile.summary.integrations.map(i => <span key={i} className="badge bg-indigo-50 text-indigo-800">{i}</span>)}</div>
                <div className="mt-2 text-xs text-slate-400">עודכן {fmtDate(d.profile.at ?? undefined)}</div>
              </>
            )}
          </Card>
          {d.profile?.summary?.architecture && (() => {
            const arch = d.profile!.summary!.architecture!
            const roles: [string, string, string][] = [['frontend', 'צד לקוח', 'bg-sky-50 border-sky-200'], ['backend', 'צד שרת', 'bg-emerald-50 border-emerald-200'], ['database', 'מסד נתונים', 'bg-amber-50 border-amber-200'], ['functions', 'פונקציות', 'bg-violet-50 border-violet-200'], ['automation', 'אוטומציה', 'bg-slate-50 border-slate-200'], ['ci', 'CI', 'bg-slate-50 border-slate-200']]
            const byRole = (r: string) => arch.nodes.filter(n => n.role === r)
            return (
              <Card title="מפת הארכיטקטורה: מה יושב איפה">
                {arch.nodes.length === 0 ? <Empty>לא זוהו רכיבים. ודא שהריפוזיטוריז ופרויקטי ה-Vercel של הפרויקט משויכים אליו ושיש חיבורים חיים.</Empty> : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {roles.filter(([r]) => byRole(r).length).map(([r, label, tone]) => (
                      <div key={r} className={`rounded-xl border p-3 ${tone}`}>
                        <div className="mb-2 text-xs font-semibold text-slate-600">{label}</div>
                        <ul className="space-y-2">
                          {byRole(r).map(n => (
                            <li key={n.id} className="rounded-lg bg-white/80 p-2 text-sm">
                              <div className="flex flex-wrap items-center gap-2">
                                {n.repo ? <Link to={`/assets/${n.repo_asset_id}`} className="font-medium text-indigo-700"><bdi>{n.repo}</bdi></Link> : <span className="font-medium"><bdi>{n.path}</bdi></span>}
                                {n.repo && <span className="mono text-xs text-slate-600">/{n.path.replace(/^\/+/, '')}</span>}
                                {n.note && <span className="badge bg-slate-100 text-slate-700">{n.note}</span>}
                                {n.runtime && <span className="badge bg-slate-100 text-slate-500">{n.runtime}</span>}
                              </div>
                              {n.entrypoints.length > 0 && <div className="mt-1 text-xs text-slate-500">נקודות כניסה: <span className="mono">{n.entrypoints.slice(0, 4).join(', ')}</span></div>}
                              {Object.keys(n.scripts ?? {}).length > 0 && <div className="text-xs text-slate-500">סקריפטים: <span className="mono">{Object.entries(n.scripts).slice(0, 5).map(([k, v]) => `${k}: ${v}`).join(' · ')}</span></div>}
                              {n.runs_at.map(run => (
                                <div key={run.asset_id} className="mt-1 text-xs">
                                  <span className="text-slate-500">רץ ב-Vercel:</span> <Link to={`/assets/${run.asset_id}`} className="text-indigo-700">{run.name}</Link>
                                  {run.domains.slice(0, 2).map(dm => <ExtLink key={dm} href={`https://${dm}`}>{dm}</ExtLink>)}
                                  {run.branch && <span className="mono text-slate-500"> · {run.branch}</span>}
                                  {run.last_production && <span className={`badge ml-1 ${run.last_production.state === 'READY' ? 'bg-emerald-100 text-emerald-800' : run.last_production.state === 'ERROR' ? 'bg-rose-100 text-rose-800' : 'bg-slate-100'}`}>{run.last_production.state}</span>}
                                  {run.env_names.length > 0 && <div className="text-slate-500">משתני סביבה ({run.env_names.length}): <span className="mono">{run.env_names.slice(0, 12).join(', ')}{run.env_names.length > 12 ? '…' : ''}</span></div>}
                                </div>
                              ))}
                              {n.talks_to && n.talks_to.length > 0 && <div className="mt-1 flex flex-wrap gap-1 text-xs"><span className="text-slate-500">מדבר עם:</span>{n.talks_to.map(s => <span key={s} className="badge bg-indigo-50 text-indigo-800">{s}</span>)}</div>}
                              {n.tables && n.tables.length > 0 && <div className="mt-1 text-xs text-slate-500">טבלאות: <span className="mono">{n.tables.slice(0, 10).map(tb => tb.name).join(', ')}{n.tables.length > 10 ? ` +${n.tables.length - 10}` : ''}</span></div>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    {arch.services.length > 0 && (
                      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3 md:col-span-2">
                        <div className="mb-2 text-xs font-semibold text-slate-600">שירותים חיצוניים ומי משתמש בהם</div>
                        <ul className="grid gap-1 text-sm md:grid-cols-2">{arch.services.map(s => <li key={s.name}><span className="font-medium">{s.name}</span> <span className="text-xs text-slate-500">← {s.used_by.join(' · ')}</span></li>)}</ul>
                      </div>
                    )}
                    {arch.edges.length > 0 && (
                      <div className="rounded-xl border border-slate-200 p-3 md:col-span-2">
                        <div className="mb-2 text-xs font-semibold text-slate-600">קשרים</div>
                        <ul className="space-y-1 text-xs">{arch.edges.map((e, i) => <li key={i} className="mono"><bdi>{e.from}</bdi> → <bdi>{e.to}</bdi> <span className="text-slate-400">({e.kind})</span></li>)}</ul>
                      </div>
                    )}
                    {(arch.unlinked_vercel.length > 0 || arch.repos_without_layout.length > 0) && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 md:col-span-2">
                        {arch.unlinked_vercel.length > 0 && <div>פרויקטי Vercel שלא שויכו לרכיב (אין ריפו מקושר או הוא לא בפרויקט): {arch.unlinked_vercel.map(v => <Link key={v.asset_id} to={`/assets/${v.asset_id}`} className="ml-2 text-indigo-700">{v.name}</Link>)}</div>}
                        {arch.repos_without_layout.length > 0 && <div>ריפוזיטוריז בלי פרופיל (רענן פרופיל או בדוק חיבור): {arch.repos_without_layout.join(', ')}</div>}
                      </div>
                    )}
                  </div>
                )}
              </Card>
            )
          })()}
          {d.profile?.assets.filter(a => a.profile).map(a => {
            const p = a.profile!
            return (
              <Card key={a.id} title={`${t(provider, a.provider)} · ${a.name}`} actions={<Link to={`/assets/${a.id}`} className="text-xs text-indigo-600">עמוד הנכס</Link>}>
                {p.error ? <div className="text-sm text-rose-700">{p.error}</div> : a.provider === 'github' ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <Facts items={[['מסגרת', p.framework || '—'], ['ריצה', p.runtime || '—'], ['ענף', p.default_branch || '—'], ['קבצים', String(p.files ?? '—')], ['CI', p.workflows?.length ? p.workflows.join(', ') : 'אין'], ['בדיקות', p.has_tests ? 'יש' : 'אין'], ['מיגרציות SQL', String(p.migrations ?? 0)], ['דחיפה אחרונה', fmtDate(p.pushed_at)]]} />
                    <div className="space-y-2 text-sm">
                      <div><span className="text-xs text-slate-500">שפות:</span> {Object.entries(p.languages ?? {}).map(([k, v]) => `${k} ${Math.round(100 * v / Math.max(1, Object.values(p.languages ?? {}).reduce((s, x) => s + x, 0)))}%`).join(' · ') || '—'}</div>
                      <div><span className="text-xs text-slate-500">מבנה:</span> <span className="mono text-xs">{Object.entries(p.top_level ?? {}).slice(0, 14).map(([k, v]) => `${k} (${v})`).join(' · ')}</span></div>
                      <div><span className="text-xs text-slate-500">אינטגרציות:</span> {(p.integrations ?? []).join(', ') || '—'}</div>
                      <div><span className="text-xs text-slate-500">תלויות ({Object.keys(p.dependencies ?? {}).length}):</span> <span className="mono text-xs">{Object.keys(p.dependencies ?? {}).slice(0, 25).join(', ')}</span></div>
                      {p.env_files_committed?.length ? <div className="text-rose-700">קובץ env בריפו: {p.env_files_committed.join(', ')}</div> : null}
                      {p.readme_excerpt && <details className="text-xs text-slate-600"><summary className="cursor-pointer">README</summary><pre className="mt-1 whitespace-pre-wrap">{p.readme_excerpt}</pre></details>}
                    </div>
                  </div>
                ) : a.provider === 'vercel' ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <Facts items={[['מסגרת', p.framework || '—'], ['Node', p.node_version || '—'], ['תיקיית שורש', p.root_directory || '/'], ['ריפו מקושר', p.linked_repo || '—'], ['ענף ייצור', p.production_branch || '—'], ['הגנה', p.protection || '—'], ['פריסת ייצור אחרונה', p.last_production ? `${p.last_production.state} · ${fmtDate(p.last_production.at)}` : 'אין']]} />
                    <div className="space-y-2 text-sm">
                      <div><span className="text-xs text-slate-500">כתובות:</span> {(p.domains ?? []).map(dm => <ExtLink key={dm} href={`https://${dm}`}>{dm}</ExtLink>)}</div>
                      <div><span className="text-xs text-slate-500">משתני סביבה ({p.env_names?.length ?? 0}, שמות בלבד):</span> <span className="mono text-xs">{(p.env_names ?? []).join(', ')}</span></div>
                      {p.crons?.length ? <div><span className="text-xs text-slate-500">Cron:</span> <span className="mono text-xs">{p.crons.join(', ')}</span></div> : null}
                    </div>
                  </div>
                ) : a.provider === 'supabase' ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <Facts items={[['אזור', p.region || '—'], ['מצב', p.status || '—'], ['Postgres', p.postgres_version || '—'], ['טבלאות', String(p.tables?.length ?? 0)], ['Policies', String(p.policies ?? '—')]]} />
                    <div className="text-sm"><span className="text-xs text-slate-500">סכימה (public):</span>
                      <ul className="mt-1 max-h-64 overflow-auto text-xs">{(p.tables ?? []).map(tb => <li key={tb.name} className="flex justify-between border-b border-slate-100 py-0.5"><span className="mono">{tb.name}</span><span>{qty(tb.rows)} שורות · {tb.rls ? 'RLS' : <span className="text-rose-700">ללא RLS</span>}</span></li>)}</ul>
                    </div>
                  </div>
                ) : <Empty>אין פרופיל לסוג נכס זה.</Empty>}
              </Card>
            )
          })}
        </div>
      )}

      {tab === 'scans' && (
        <div className="space-y-4">
          <Card title="סריקות" actions={<span className="flex gap-2"><button className="btn-primary" disabled={busy !== null} onClick={() => runScan('health')}>{busy === 'scan' ? 'סורק…' : 'סריקת תקינות'}</button><button className="btn-secondary" disabled={busy !== null} onClick={() => runScan('code')}>סריקת קוד (Claude)</button></span>}>
            <p className="text-sm text-slate-600"><b>סריקת תקינות</b> בודקת כל נכס דרך החיבורים (קריאה בלבד): הגנת ענף, התראות Dependabot / סודות / קוד, קובצי env בריפו, בדיקות ו-CI, lockfile, פריסת ייצור אחרונה, סודות שמורים כ-plain ב-Vercel, טבלאות ללא RLS. <b>סריקת קוד</b> שולחת ל-Claude עד 25 קבצי מקור רלוונטיים לאבטחה מכל ריפו (אחרי השחרת סודות) ומחזירה ממצאים עם קובץ ושורה; דורשת מפתח Anthropic (מפתח ברירת המחדל של הפרויקט או מפתח השרת) והשימוש נזקף ללקוח של הפרויקט. כל סריקה נשמרת כדי להשוות לאורך זמן.</p>
            <div className="mt-3 flex flex-wrap gap-4 text-sm">
              {d.project.last_scan_grade && <span>תקינות: <span className={`badge ${gradeTone[d.project.last_scan_grade] ?? 'bg-slate-100'}`}>{d.project.last_scan_grade}</span> <span className="text-xs text-slate-400">{fmtDate(d.project.last_scan_at)}</span></span>}
              {d.project.last_code_scan_grade && <span>קוד: <span className={`badge ${gradeTone[d.project.last_code_scan_grade] ?? 'bg-slate-100'}`}>{d.project.last_code_scan_grade}</span> <span className="text-xs text-slate-400">{fmtDate(d.project.last_code_scan_at)}</span></span>}
            </div>
            <p className="mt-3 text-xs text-slate-500">סריקת אבטחה של האתר החי (כותרות, cookies, היקף מאושר) נעשית במודול <button className="text-indigo-700 underline" onClick={() => setTab('security')}>סקרי אבטחה</button>.</p>
          </Card>
          {(scan ?? d.last_scan) && (() => { const s = scan ?? d.last_scan!; return (
            <Card title={`ממצאים · ${s.kind === 'code' ? 'סריקת קוד' : 'סריקת תקינות'} · ${fmtDate(s.created_at)}`} actions={s.grade ? <span className={`badge ${gradeTone[s.grade] ?? 'bg-slate-100'}`}>ציון {s.grade}</span> : <span className="badge bg-rose-100 text-rose-800">נכשלה</span>}>
              <div className="mb-3 flex flex-wrap gap-2 text-xs">{Object.entries(s.counts ?? {}).map(([k, v]) => <span key={k} className={`badge ${sevTone[k]}`}>{sevLabel[k]} {v}</span>)}<span className="badge bg-slate-100">{s.assets ?? 0} נכסים</span>{s.files ? <span className="badge bg-slate-100">{s.files} קבצים</span> : null}{s.model ? <span className="mono badge bg-slate-100">{s.model}</span> : null}</div>
              {s.summary?.text && s.kind === 'code' && <pre className="mb-3 whitespace-pre-wrap text-sm text-slate-700">{s.summary.text}</pre>}
              {!s.findings?.length ? <Empty>אין ממצאים.</Empty> : (
                <ul className="divide-y divide-slate-100">{s.findings.map((f, i) => <li key={i} className="py-2 text-sm"><div className="flex flex-wrap items-center gap-2"><span className={`badge ${sevTone[f.severity]}`}>{sevLabel[f.severity]}</span><span className="font-medium">{f.title}</span><span className="text-xs text-slate-400">{f.asset_name}{f.file ? <> · <span className="mono">{f.file}{f.line ? `:${f.line}` : ''}</span></> : ` · ${t(provider, f.source)}`}</span></div>{f.detail && <div className="text-xs text-slate-600">{f.detail}</div>}{f.fix && <div className="text-xs text-emerald-800">תיקון: {f.fix}</div>}</li>)}</ul>
              )}
            </Card>
          ) })()}
          {d.scans && d.scans.length > 1 && (
            <Card title="היסטוריית סריקות">
              <ul className="divide-y divide-slate-100 text-sm">{d.scans.map(s => <li key={s.id} className="flex items-center justify-between py-1.5"><button className="text-indigo-700" onClick={() => openScan(s.id)}>{fmtDate(s.created_at)}</button><span className="flex gap-2 text-xs"><span className={`badge ${gradeTone[s.grade] ?? 'bg-slate-100'}`}>{s.grade}</span>{Object.entries(s.counts ?? {}).filter(([, v]) => v).map(([k, v]) => <span key={k} className={`badge ${sevTone[k]}`}>{sevLabel[k]} {v}</span>)}</span></li>)}</ul>
            </Card>
          )}
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
