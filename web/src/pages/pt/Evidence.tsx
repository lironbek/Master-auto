import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AccessLog, type Evidence, type Project } from '../../api'
import { Card, Empty, ErrorBox, Mono, Spinner, Table } from '../../components/ui'
import { evidenceKind, fmtDate, t } from '../../i18n'

export default function EvidencePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [pid, setPid] = useState('')
  const [items, setItems] = useState<Evidence[] | null>(null)
  const [open, setOpen] = useState<{ evidence: Evidence; access_log: AccessLog[] } | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => { api.get<Project[]>('/pt/projects').then(p => { setProjects(p); if (p[0]) setPid(p[0].id) }).catch(setError) }, [])
  useEffect(() => { if (!pid) { setItems([]); return } api.get<Evidence[]>(`/pt/evidence?project_id=${pid}`).then(setItems).catch(setError) }, [pid])

  async function view(id: string) { try { setOpen(await api.get(`/pt/evidence/${id}`)) } catch (err) { setError(err) } }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">כספת ראיות</h1><p className="text-sm text-slate-500">ראיות מושחרות לפי פרויקט, תוקף שמירה ויומן צפייה</p></div>
        <select className="input w-64" value={pid} onChange={e => setPid(e.target.value)}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      </div>
      <ErrorBox error={error} />
      <Card>
        {!items ? <Spinner /> : items.length === 0 ? <Empty>אין ראיות בפרויקט הזה.</Empty> : (
          <Table head={['מזהה', 'סוג', 'ממצא', 'נתפס', 'מחיקה מתוזמנת', 'checksum', '']}>
            {items.map(e => (
              <tr key={e.id}>
                <td className="px-3 py-2"><Mono>{e.id}</Mono></td>
                <td className="px-3 py-2 text-xs">{t(evidenceKind, e.kind)}</td>
                <td className="px-3 py-2 text-xs">{e.finding_id ? <Link to={`/security/findings/${e.finding_id}`} className="text-indigo-700">{e.finding_id}</Link> : '—'}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(e.captured_at)}</td>
                <td className="px-3 py-2 text-xs">{fmtDate(e.delete_at)}</td>
                <td className="px-3 py-2"><Mono>{e.checksum.slice(0, 10)}…</Mono></td>
                <td className="px-3 py-2"><button className="btn-secondary" onClick={() => view(e.id)}>צפייה</button></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {open && (
        <Card title={<span>ראיה <Mono>{open.evidence.id}</Mono></span>} actions={<button className="btn-secondary" onClick={() => setOpen(null)}>סגירה</button>}>
          <pre className="max-h-80 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{open.evidence.redacted_source}</pre>
          <h3 className="mt-4 text-xs font-semibold text-slate-600">יומן גישה (ללא תוכן הראיה)</h3>
          <Table head={['זמן', 'מי', 'פעולה']}>
            {open.access_log.map((l, i) => <tr key={i}><td className="px-3 py-1 text-xs">{fmtDate(l.at)}</td><td className="px-3 py-1 text-xs">{l.actor}</td><td className="px-3 py-1 text-xs">{l.action}</td></tr>)}
          </Table>
        </Card>
      )}
    </div>
  )
}
