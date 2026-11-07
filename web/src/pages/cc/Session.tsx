import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type AgentRun, type CcEvent, type CcProject, type WorkSession } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner } from '../../components/ui'
import { EventRow, Facts } from '../../components/cc'
import { fmtDate, runStatusCc, sessionStatus, sessionTool, t } from '../../i18n'

interface Detail { session: WorkSession; project: CcProject; events: CcEvent[]; suggested_events: CcEvent[]; runs: AgentRun[] }

export default function SessionPage() {
  const { id } = useParams()
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const load = useCallback(() => api.get<Detail>(`/cc/sessions/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const s = d.session

  async function setStatus(status: string) { try { await api.patch(`/cc/sessions/${id}`, { status }); load() } catch (err) { setError(err) } }
  async function close(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    try { await api.patch(`/cc/sessions/${id}`, { status: 'done', outcome: fd.get('outcome'), follow_up: fd.get('follow_up'), links: String(fd.get('links') || '').split('\n').map(x => x.trim()).filter(Boolean) }); load() } catch (err) { setError(err) }
  }
  async function link(eventId: string) { try { await api.post(`/cc/sessions/${id}/events`, { event_id: eventId }); load() } catch (err) { setError(err) } }

  return (
    <div className="space-y-4">
      <div>
        <Link to={`/projects/${s.project_id}`} className="text-xs text-indigo-600">← לפרויקט {d.project?.name}</Link>
        <h1 className="text-xl font-bold">{s.title}</h1>
        <p className="text-sm text-slate-500">{s.goal}</p>
      </div>
      <ErrorBox error={error} />
      <Facts items={[['סטטוס', t(sessionStatus, s.status)], ['כלי עבודה', t(sessionTool, s.tool)], ['אחראי', s.owner], ['התחלה', fmtDate(s.started_at)], ['סיום', fmtDate(s.ended_at) || '—'], ['תוצר', s.outcome || '—'], ['המשך טיפול', s.follow_up || '—'], ['קישורים', s.links?.length ? s.links.map(l => <a key={l} href={l} className="block text-indigo-700 ltr" target="_blank" rel="noopener noreferrer">{l}</a>) : '—']]} />
      <div className="flex flex-wrap gap-2">
        {s.status === 'open' && <button className="btn-secondary" onClick={() => setStatus('waiting')}>סמן כממתין</button>}
        {s.status === 'waiting' && <button className="btn-secondary" onClick={() => setStatus('open')}>חזרה לפתוח</button>}
        {(s.status === 'done' || s.status === 'cancelled') && <button className="btn-secondary" onClick={() => setStatus('open')}>פתח מחדש</button>}
        {(s.status === 'open' || s.status === 'waiting') && <button className="btn-danger" onClick={() => setStatus('cancelled')}>ביטול סשן</button>}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="ציר הפעילות" className="lg:col-span-2">
          {d.events.length === 0 ? <Empty>אין אירועים משויכים. בחר מההצעות משמאל או חכה לדיווח עם מזהה סשן.</Empty> : <ul className="divide-y divide-slate-100 border-r-2 border-teal-200 pr-3">{d.events.map(e => <EventRow key={e.id} e={e} />)}</ul>}
          {d.runs.length > 0 && <div className="mt-4"><h3 className="text-xs font-semibold text-slate-600">ריצות סוכן בסשן</h3><ul className="text-sm">{d.runs.map(r => <li key={r.id}><Link to={`/agents/runs/${r.id}`} className="text-indigo-700">{r.agent_name}</Link> · {t(runStatusCc, r.status)}</li>)}</ul></div>}
        </Card>
        <div className="space-y-4">
          <Card title="הצעות שיוך">
            <p className="mb-2 text-xs text-slate-500">אירועי הפרויקט ללא מזהה סשן חד-משמעי. שיוך ידני בלבד.</p>
            {d.suggested_events.length === 0 ? <Empty>אין הצעות.</Empty> : (
              <ul className="divide-y divide-slate-100 text-sm">{d.suggested_events.map(e => <li key={e.id} className="flex items-center justify-between gap-2 py-2"><span className="truncate">{e.title}</span><button className="btn-secondary" onClick={() => link(e.id)}>שייך</button></li>)}</ul>
            )}
          </Card>
          {(s.status === 'open' || s.status === 'waiting') && (
            <Card title="סגירת הסשן">
              <form onSubmit={close} className="space-y-2">
                <Field label="תוצר"><input className="input" name="outcome" placeholder="PR #42 / דוח / החלטה" /></Field>
                <Field label="קישורים (שורה לכל קישור)"><textarea className="input ltr" name="links" rows={2} /></Field>
                <Field label="המשך טיפול"><input className="input" name="follow_up" /></Field>
                <button className="btn-primary w-full justify-center">סמן כהושלם</button>
              </form>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
