import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type AgentRun, type CcAgent, type CcProject } from '../../api'
import { Card, Empty, ErrorBox, Mono, Spinner } from '../../components/ui'
import { Facts } from '../../components/cc'
import { fmtDate, qty, runStatusCc, t, usd } from '../../i18n'

export default function AgentRunPage() {
  const { id } = useParams()
  const [d, setD] = useState<{ run: AgentRun; agent: CcAgent; project: CcProject } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const load = useCallback(() => api.get<{ run: AgentRun; agent: CcAgent; project: CcProject }>(`/cc/runs/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const r = d.run
  async function cancel() { try { await api.post(`/cc/runs/${id}/cancel`); load() } catch (err) { setError(err) } }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to="/agents" className="text-xs text-indigo-600">← מרכז הסוכנים</Link>
          <h1 className="text-xl font-bold">ריצת {d.agent?.name}</h1>
          <p className="text-sm text-slate-500"><Link to={`/projects/${r.project_id}`} className="text-indigo-700">{d.project?.name}</Link> · <Mono>{r.id}</Mono></p>
        </div>
        {['queued', 'running', 'awaiting_approval'].includes(r.status) && <button className="btn-danger" onClick={cancel}>ביטול</button>}
      </div>
      <ErrorBox error={error} />
      <Facts items={[['סטטוס', t(runStatusCc, r.status)], ['מודל', <Mono>{r.model ?? d.agent?.model}</Mono>], ['גרסת הגדרה', `v${(r as unknown as { config_version?: number }).config_version ?? d.agent?.version}`], ['מבקש', r.requested_by ?? '—'], ['התחלה', fmtDate(r.started_at)], ['סיום', fmtDate(r.finished_at)], ['טוקנים (קלט / פלט)', `${qty(r.usage?.input)} / ${qty(r.usage?.output)}`], ['עלות משוערת', usd(r.cost_usd ?? 0)]]} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="תוצר הריצה" className="lg:col-span-2">
          {r.error ? <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{r.error}</div> : r.result ? <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm">{r.result}</pre> : <Empty>אין תוצר עדיין.</Empty>}
        </Card>
        <Card title="כלים שנקראו">
          {!r.steps?.length ? <Empty>אין צעדים.</Empty> : <ol className="space-y-2 text-sm">{r.steps.map((s, i) => <li key={i} className="rounded border border-slate-200 p-2"><div className="mono text-xs text-indigo-700">{s.tool}</div><div className="text-xs text-slate-500">{fmtDate(s.at)} · {s.note}</div></li>)}</ol>}
          <p className="mt-3 text-xs text-slate-500">הסוכן קורא מהקטלוג בלבד. פעולות כתיבה דורשות יכולת ייעודית ואישור.</p>
        </Card>
      </div>
    </div>
  )
}
