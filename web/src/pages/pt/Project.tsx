import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Play, Plus } from 'lucide-react'
import { api, type Authorization, type Finding, type Project, type Run, type ScopeVersion } from '../../api'
import { MANAGER_ROLES, TESTER_ROLES, useAuth } from '../../auth'
import { Card, Empty, ErrorBox, Field, FindingStatusBadge, Mono, RunBadge, ScopeBadge, SeverityBadge, Spinner, Table } from '../../components/ui'
import { fmtDate, mode as modeLabels, modules as moduleLabels, t } from '../../i18n'

interface Detail { project: Project; authorizations: Authorization[]; scope_versions: ScopeVersion[]; runs: Run[]; findings: Finding[] }

function toLocalInput(d: Date) { const p = (n: number) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}` }

export default function ProjectPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { me } = useAuth()
  const canManage = MANAGER_ROLES.includes(me?.user.role ?? '')
  const canTest = TESTER_ROLES.includes(me?.user.role ?? '')
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [tab, setTab] = useState<'none' | 'auth' | 'scope'>('none')

  const load = useCallback(() => api.get<Detail>(`/pt/projects/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])

  // --- authorization form (PRD section 4) ---
  const now = new Date()
  const [a, setA] = useState({ approver_name: '', approver_authority: '', document_reference: '', control_verified: false,
    valid_from: toLocalInput(now), valid_until: toLocalInput(new Date(now.getTime() + 7 * 864e5)) })
  async function createAuth(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post(`/pt/projects/${id}/authorizations`, { ...a, valid_from: new Date(a.valid_from).toISOString(), valid_until: new Date(a.valid_until).toISOString() })
      setTab('none'); load()
    } catch (err) { setError(err) }
  }

  // --- scope wizard (PRD sections 4, 5) ---
  const [s, setS] = useState({ authorization_id: '', environment: 'test', host: '', scheme: 'https', port: 443, path: '/',
    modules: ['passive.security_headers', 'passive.cookie_flags'], max_requests: 1000, max_duration_seconds: 1800, stop_conditions: 'חשיפה בלתי צפויה של מידע אמיתי; עלייה בשגיאות; בקשת בעל הנכס' })
  async function createScope(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post(`/pt/projects/${id}/scope-versions`, {
        authorization_id: s.authorization_id || d?.authorizations.at(-1)?.id,
        environment: s.environment,
        targets: [{ scheme: s.scheme, host: s.host.trim().toLowerCase(), ports: [Number(s.port)], allowed_paths: [s.path || '/'] }],
        allowed_modules: s.modules, allowed_modes: ['passive'],
        budget: { max_requests: Number(s.max_requests), max_duration_seconds: Number(s.max_duration_seconds), requests_per_second: 1, max_concurrency_per_host: 2, max_response_bytes: 5000000, max_model_cost_usd: 25 },
        stop_conditions: s.stop_conditions.split(';').map(x => x.trim()).filter(Boolean),
      })
      setTab('none'); load()
    } catch (err) { setError(err) }
  }

  async function approve(scopeId: string) { try { await api.post(`/pt/scope-versions/${scopeId}/approve`); load() } catch (err) { setError(err) } }
  async function startRun(scopeId: string) {
    try {
      const run = await api.post<Run>('/pt/runs', { scope_version_id: scopeId, mode: 'passive' })
      nav(`/security/runs/${run.id}?autostart=1`)
    } catch (err) { setError(err) }
  }

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const latestAuth = d.authorizations.at(-1)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link to="/security/projects" className="text-xs text-indigo-600">← פרויקטים</Link>
          <h1 className="text-xl font-bold">{d.project.name}</h1>
          <p className="text-sm text-slate-500">{d.project.description || <Mono>{d.project.id}</Mono>}</p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => setTab(tab === 'auth' ? 'none' : 'auth')}><Plus className="h-4 w-4" /> מסמך הרשאה</button>
            <button className="btn-primary" onClick={() => setTab(tab === 'scope' ? 'none' : 'scope')} disabled={!latestAuth}><Plus className="h-4 w-4" /> היקף בדיקה חדש</button>
          </div>
        )}
      </div>
      <ErrorBox error={error} />

      {tab === 'auth' && (
        <Card title="מסמך הרשאה (חוזה בדיקה, סעיף 4)">
          <form onSubmit={createAuth} className="grid gap-3 md:grid-cols-3">
            <Field label="מאשר"><input className="input" value={a.approver_name} onChange={e => setA({ ...a, approver_name: e.target.value })} required /></Field>
            <Field label="סמכות המאשר"><input className="input" placeholder="CISO / מנכ״ל / בעל הנכס" value={a.approver_authority} onChange={e => setA({ ...a, approver_authority: e.target.value })} required /></Field>
            <Field label="אסמכתא למסמך"><input className="input" value={a.document_reference} onChange={e => setA({ ...a, document_reference: e.target.value })} /></Field>
            <Field label="תוקף מ־"><input className="input ltr" type="datetime-local" value={a.valid_from} onChange={e => setA({ ...a, valid_from: e.target.value })} required /></Field>
            <Field label="תוקף עד"><input className="input ltr" type="datetime-local" value={a.valid_until} onChange={e => setA({ ...a, valid_until: e.target.value })} required /></Field>
            <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={a.control_verified} onChange={e => setA({ ...a, control_verified: e.target.checked })} /> אימות שליטה בוצע (DNS / קובץ)</label>
            <div className="md:col-span-3 text-xs text-slate-500">אימות שליטה אינו מחליף מסמך הרשאה. ריצה תיחסם מחוץ לחלון התוקף.</div>
            <div className="md:col-span-3"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}

      {tab === 'scope' && (
        <Card title="אשף היקף בדיקה (סעיפים 4-5)">
          <form onSubmit={createScope} className="grid gap-3 md:grid-cols-3">
            <Field label="מסמך הרשאה">
              <select className="input" value={s.authorization_id || latestAuth?.id} onChange={e => setS({ ...s, authorization_id: e.target.value })}>
                {d.authorizations.map(x => <option key={x.id} value={x.id}>{x.approver_name} · עד {fmtDate(x.valid_until)}</option>)}
              </select>
            </Field>
            <Field label="סביבה">
              <select className="input" value={s.environment} onChange={e => setS({ ...s, environment: e.target.value })}>
                <option value="test">בדיקות</option><option value="production">ייצור</option>
              </select>
            </Field>
            <Field label="מצב הפעלה"><input className="input" value={t(modeLabels, 'passive')} disabled /></Field>
            <Field label="סכמה"><select className="input ltr" value={s.scheme} onChange={e => setS({ ...s, scheme: e.target.value, port: e.target.value === 'https' ? 443 : 80 })}><option>https</option><option>http</option></select></Field>
            <Field label="שם מארח (מדויק, ללא תתי־דומיין משתמעים)"><input className="input ltr" placeholder="app.example.com" value={s.host} onChange={e => setS({ ...s, host: e.target.value })} required /></Field>
            <Field label="פורט"><input className="input ltr" type="number" value={s.port} onChange={e => setS({ ...s, port: Number(e.target.value) })} /></Field>
            <Field label="נתיב מותר"><input className="input ltr" value={s.path} onChange={e => setS({ ...s, path: e.target.value })} /></Field>
            <Field label="תקציב בקשות"><input className="input ltr" type="number" value={s.max_requests} onChange={e => setS({ ...s, max_requests: Number(e.target.value) })} /></Field>
            <Field label="משך מרבי (שניות)"><input className="input ltr" type="number" value={s.max_duration_seconds} onChange={e => setS({ ...s, max_duration_seconds: Number(e.target.value) })} /></Field>
            <div className="md:col-span-3">
              <span className="label">מודולים מאושרים</span>
              <div className="flex flex-wrap gap-3 text-sm">
                {Object.entries(moduleLabels).map(([k, label]) => (
                  <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={s.modules.includes(k)} onChange={e => setS({ ...s, modules: e.target.checked ? [...s.modules, k] : s.modules.filter(m => m !== k) })} /> {label}</label>
                ))}
              </div>
            </div>
            <Field label="תנאי עצירה (מופרדים ב־;)"><input className="input" value={s.stop_conditions} onChange={e => setS({ ...s, stop_conditions: e.target.value })} /></Field>
            <div className="md:col-span-3 text-xs text-slate-500">שינוי היקף לאחר אישור יוצר גרסה חדשה. ריצה קשורה לגרסה שאושרה.</div>
            <div className="md:col-span-3"><button className="btn-primary">יצירת גרסת היקף</button></div>
          </form>
        </Card>
      )}

      <Card title="מסמכי הרשאה">
        {d.authorizations.length === 0 ? <Empty>אין מסמך הרשאה. בלי מסמך הרשאה לא ניתן להגדיר היקף.</Empty> : (
          <Table head={['מאשר', 'סמכות', 'תוקף', 'אימות שליטה', 'אסמכתא']}>
            {d.authorizations.map(x => (
              <tr key={x.id}><td className="px-3 py-2">{x.approver_name}</td><td className="px-3 py-2">{x.approver_authority}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(x.valid_from)} – {fmtDate(x.valid_until)}</td>
                <td className="px-3 py-2">{x.control_verified ? <span className="badge bg-emerald-100 text-emerald-800">בוצע</span> : <span className="badge bg-slate-100">לא</span>}</td>
                <td className="px-3 py-2 text-xs">{x.document_reference || '—'}</td></tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="גרסאות היקף">
        {d.scope_versions.length === 0 ? <Empty>אין גרסאות היקף.</Empty> : (
          <Table head={['גרסה', 'סטטוס', 'יעדים', 'מודולים', 'תקציב', 'פעולות']}>
            {d.scope_versions.map(sv => (
              <tr key={sv.id}>
                <td className="px-3 py-2">v{sv.version} <span className="block text-xs text-slate-400">{fmtDate(sv.created_at)}</span></td>
                <td className="px-3 py-2"><ScopeBadge value={sv.status} /></td>
                <td className="px-3 py-2">{sv.targets.map((x, i) => <div key={i} className="mono text-xs">{x.scheme}://{x.host}:{x.ports.join(',')}{x.allowed_paths[0]}</div>)}</td>
                <td className="px-3 py-2 text-xs">{sv.allowed_modules.map(m => t(moduleLabels, m)).join(', ')}</td>
                <td className="px-3 py-2 text-xs">{sv.budget.max_requests} בקשות · {Math.round(sv.budget.max_duration_seconds / 60)} דק׳</td>
                <td className="px-3 py-2">
                  <div className="flex gap-2">
                    {sv.status === 'draft' && canManage && <button className="btn-secondary" onClick={() => approve(sv.id)}><CheckCircle2 className="h-4 w-4" /> אישור</button>}
                    {sv.status === 'approved' && canTest && <button className="btn-primary" onClick={() => startRun(sv.id)}><Play className="h-4 w-4" /> הפעלת ריצה</button>}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="ריצות">
          {d.runs.length === 0 ? <Empty>אין ריצות.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {d.runs.slice().reverse().map(r => (
                <li key={r.id} className="flex items-center justify-between py-2">
                  <Link to={`/security/runs/${r.id}`} className="mono text-indigo-700">{r.id}</Link>
                  <span className="text-xs text-slate-500">{fmtDate(r.created_at)}</span>
                  <RunBadge value={r.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="ממצאים">
          {d.findings.length === 0 ? <Empty>אין ממצאים.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {d.findings.map(f => (
                <li key={f.id} className="flex items-center justify-between gap-2 py-2">
                  <Link to={`/security/findings/${f.id}`} className="truncate text-indigo-700">{f.title}</Link>
                  <div className="flex gap-1"><SeverityBadge value={f.severity} /><FindingStatusBadge value={f.status} /></div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
