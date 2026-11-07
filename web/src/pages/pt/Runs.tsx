import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Project, type Run } from '../../api'
import { Card, Empty, ErrorBox, RunBadge, Spinner, Table } from '../../components/ui'
import { fmtDate, mode, t } from '../../i18n'

export default function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [projects, setProjects] = useState<Record<string, string>>({})
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    Promise.all([api.get<Run[]>('/pt/runs'), api.get<Project[]>('/pt/projects')])
      .then(([r, p]) => { setRuns(r.slice().reverse()); setProjects(Object.fromEntries(p.map(x => [x.id, x.name]))) })
      .catch(setError)
  }, [])

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">ריצות</h1><p className="text-sm text-slate-500">כל הריצות בארגון</p></div>
      <ErrorBox error={error} />
      <Card>
        {!runs ? <Spinner /> : runs.length === 0 ? <Empty>אין ריצות. הפעל ריצה מתוך גרסת היקף מאושרת בעמוד הפרויקט.</Empty> : (
          <Table head={['ריצה', 'פרויקט', 'מצב', 'סטטוס', 'נוצרה', 'סיכום']}>
            {runs.map(r => (
              <tr key={r.id}>
                <td className="px-3 py-2"><Link to={`/security/runs/${r.id}`} className="mono text-indigo-700">{r.id}</Link></td>
                <td className="px-3 py-2"><Link to={`/security/projects/${r.project_id}`} className="text-indigo-700">{projects[r.project_id] ?? r.project_id}</Link></td>
                <td className="px-3 py-2 text-xs">{t(mode, r.mode)}</td>
                <td className="px-3 py-2"><RunBadge value={r.status} /></td>
                <td className="px-3 py-2 text-xs">{fmtDate(r.created_at)}</td>
                <td className="px-3 py-2 text-xs">{r.summary ? `${r.summary.executed} בוצעו · ${r.summary.blocked} נחסמו · ${r.summary.findings} ממצאים` : '—'}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
