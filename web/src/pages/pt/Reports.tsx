import { useEffect, useState } from 'react'
import { FileDown } from 'lucide-react'
import { api, type Project, type Report, type Run } from '../../api'
import { TESTER_ROLES, useAuth } from '../../auth'
import { Card, Empty, ErrorBox, Mono, Spinner, Table } from '../../components/ui'
import { fmtDate } from '../../i18n'

export default function Reports() {
  const { me } = useAuth()
  const canTest = TESTER_ROLES.includes(me?.user.role ?? '')
  const [projects, setProjects] = useState<Project[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [reports, setReports] = useState<Report[] | null>(null)
  const [runId, setRunId] = useState('')
  const [fmt, setFmt] = useState<'markdown' | 'json'>('markdown')
  const [open, setOpen] = useState<Report | null>(null)
  const [error, setError] = useState<unknown>(null)

  const load = () => Promise.all([api.get<Project[]>('/pt/projects'), api.get<Run[]>('/pt/runs'), api.get<Report[]>('/pt/reports')])
    .then(([p, r, rep]) => { setProjects(p); setRuns(r); setReports(rep.slice().reverse()) }).catch(setError)
  useEffect(() => { load() }, [])

  async function generate() { try { const r = await api.post<Report>('/pt/reports', { run_id: runId, fmt }); setOpen(r); load() } catch (err) { setError(err) } }
  async function view(id: string) { try { setOpen(await api.get<Report>(`/pt/reports/${id}`)) } catch (err) { setError(err) } }
  function download(r: Report) {
    const blob = new Blob([r.content ?? ''], { type: r.format === 'json' ? 'application/json' : 'text/markdown' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${r.id}.${r.format === 'json' ? 'json' : 'md'}`; a.click()
  }
  const pname = (id: string) => projects.find(p => p.id === id)?.name ?? id

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">דוחות</h1><p className="text-sm text-slate-500">הפקה מראיות קיימות בלבד, גרסאות והורדה</p></div>
      <ErrorBox error={error} />
      {canTest && (
        <Card title="הפקת דוח">
          <div className="grid gap-3 md:grid-cols-4">
            <select className="input md:col-span-2" value={runId} onChange={e => setRunId(e.target.value)}>
              <option value="">בחר ריצה…</option>
              {runs.slice().reverse().map(r => <option key={r.id} value={r.id}>{pname(r.project_id)} · {r.id} · {r.status}</option>)}
            </select>
            <select className="input" value={fmt} onChange={e => setFmt(e.target.value as 'markdown' | 'json')}><option value="markdown">Markdown</option><option value="json">JSON</option></select>
            <button className="btn-primary justify-center" onClick={generate} disabled={!runId}>הפקה</button>
          </div>
        </Card>
      )}
      <Card title="גרסאות דוח">
        {!reports ? <Spinner /> : reports.length === 0 ? <Empty>אין דוחות.</Empty> : (
          <Table head={['מזהה', 'פרויקט', 'ריצה', 'פורמט', 'ממצאים', 'הופק', '']}>
            {reports.map(r => (
              <tr key={r.id}>
                <td className="px-3 py-2"><Mono>{r.id}</Mono></td>
                <td className="px-3 py-2 text-xs">{pname(r.project_id)}</td>
                <td className="px-3 py-2"><Mono>{r.run_id}</Mono></td>
                <td className="px-3 py-2 text-xs">{r.format}</td>
                <td className="px-3 py-2 text-xs">{r.finding_ids.length}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(r.created_at)} · {r.created_by}</td>
                <td className="px-3 py-2"><button className="btn-secondary" onClick={() => view(r.id)}>צפייה</button></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {open && (
        <Card title={<span>דוח <Mono>{open.id}</Mono></span>} actions={<><button className="btn-secondary" onClick={() => download(open)}><FileDown className="h-4 w-4" /> הורדה</button><button className="btn-secondary" onClick={() => setOpen(null)}>סגירה</button></>}>
          <pre className="ltr max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-4 text-xs">{open.content}</pre>
        </Card>
      )}
    </div>
  )
}
