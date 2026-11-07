import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Play, Square } from 'lucide-react'
import { api, type Action, type AuditEvent, type Finding, type Run, type ScopeVersion } from '../../api'
import { TESTER_ROLES, useAuth } from '../../auth'
import { Card, DecisionBadge, Empty, ErrorBox, FindingStatusBadge, Mono, RunBadge, SeverityBadge, Spinner, Stat, Table } from '../../components/ui'
import { auditAction, decision, fmtDate, mode, modules as moduleLabels, t } from '../../i18n'

interface Detail { run: Run; scope_version: ScopeVersion | null; events: AuditEvent[]; actions: Action[]; findings: Finding[] }

export default function RunPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const { me } = useAuth()
  const canTest = TESTER_ROLES.includes(me?.user.role ?? '')
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const autostarted = useRef(false)

  const load = useCallback(() => api.get<Detail>(`/pt/runs/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])

  // Live refresh while the run is active (PRD section 14: ריצה חיה).
  useEffect(() => {
    if (!d || !['created', 'running'].includes(d.run.status)) return
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [d, load])

  const start = useCallback(async () => {
    setBusy(true); setError(null)
    try { await api.post(`/pt/runs/${id}/start`); await load() } catch (err) { setError(err) } finally { setBusy(false) }
  }, [id, load])

  useEffect(() => {
    if (d && params.get('autostart') === '1' && d.run.status === 'created' && !autostarted.current && canTest) {
      autostarted.current = true
      setParams({}, { replace: true })
      start()
    }
  }, [d, params, setParams, start, canTest])

  async function stop() {
    setBusy(true)
    try { await api.post(`/pt/runs/${id}/stop`); await load() } catch (err) { setError(err) } finally { setBusy(false) }
  }

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const { run, scope_version: sv } = d
  const budget = sv?.budget
  const used = run.budget_used

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link to={`/security/projects/${run.project_id}`} className="text-xs text-indigo-600">← לפרויקט</Link>
          <h1 className="flex items-center gap-3 text-xl font-bold">ריצה חיה <RunBadge value={run.status} /></h1>
          <p className="text-sm text-slate-500"><Mono>{run.id}</Mono> · {t(mode, run.mode)} · היקף v{sv?.version}</p>
        </div>
        {canTest && (
          <div className="flex gap-2">
            {run.status === 'created' && <button className="btn-primary" onClick={start} disabled={busy}><Play className="h-4 w-4" /> {busy ? 'מריץ…' : 'התחל ריצה'}</button>}
            {['created', 'running', 'paused'].includes(run.status) && <button className="btn-danger" onClick={stop} disabled={busy}><Square className="h-4 w-4" /> עצירה</button>}
          </div>
        )}
      </div>
      <ErrorBox error={error} />
      {busy && run.status !== 'completed' && <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-800">הריצה מתבצעת. כל פעולה עוברת מנוע מדיניות ואימות יעד לפני יציאה לרשת.</div>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="בקשות" value={`${used?.requests ?? 0} / ${budget?.max_requests ?? '—'}`} />
        <Stat label="זמן (שניות)" value={`${used?.elapsed_seconds ?? 0} / ${budget?.max_duration_seconds ?? '—'}`} />
        <Stat label="פעולות" value={d.actions.length} hint={run.summary ? `${run.summary.executed} בוצעו · ${run.summary.blocked} נחסמו` : undefined} />
        <Stat label="ממצאים" value={d.findings.length} tone={d.findings.length ? 'amber' : 'slate'} />
      </div>

      {sv && (
        <Card title="היקף הריצה">
          <div className="grid gap-2 text-sm md:grid-cols-3">
            <div><span className="text-xs text-slate-500">יעדים</span>{sv.targets.map((x, i) => <div key={i} className="mono text-xs">{x.scheme}://{x.host}:{x.ports.join(',')}{x.allowed_paths[0]}</div>)}</div>
            <div><span className="text-xs text-slate-500">מודולים</span><div className="text-xs">{sv.allowed_modules.map(m => t(moduleLabels, m)).join(', ')}</div></div>
            <div><span className="text-xs text-slate-500">עצירה</span><div className="text-xs">{run.stop_reason || '—'} {run.stopped_at && `· ${fmtDate(run.stopped_at)}`}</div></div>
          </div>
        </Card>
      )}

      <Card title="ציר אירועים">
        {d.events.length === 0 ? <Empty>{run.status === 'created' ? 'הריצה עדיין לא החלה.' : 'אין אירועים.'}</Empty> : (
          <ol className="relative space-y-3 border-r border-slate-200 pr-4">
            {d.events.map(e => (
              <li key={e.id} className="relative text-sm">
                <span className="absolute -right-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-indigo-400" />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400">{fmtDate(e.at)}</span>
                  <span className="font-medium">{t(auditAction, e.action)}</span>
                  <DecisionBadge value={e.decision} label={t(decision, e.decision)} />
                  <span className="text-xs text-slate-400">{e.actor}</span>
                </div>
                {e.detail && <div className="mono mt-0.5 break-all text-xs text-slate-600">{e.detail}</div>}
              </li>
            ))}
          </ol>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="פעולות שהוצעו">
          {d.actions.length === 0 ? <Empty>אין פעולות.</Empty> : (
            <Table head={['מודול', 'יעד', 'סיכון']}>
              {d.actions.map(a => <tr key={a.id}><td className="px-3 py-2 text-xs">{t(moduleLabels, a.module)}</td><td className="px-3 py-2"><Mono>{a.target_host}</Mono></td><td className="px-3 py-2 text-xs">{a.risk}</td></tr>)}
            </Table>
          )}
        </Card>
        <Card title="ממצאים מהריצה">
          {d.findings.length === 0 ? <Empty>לא נוצרו ממצאים. היעדר ממצאים אינו אישור שהמערכת מאובטחת.</Empty> : (
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
