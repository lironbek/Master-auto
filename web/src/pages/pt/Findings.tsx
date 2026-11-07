import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Finding, type Project } from '../../api'
import { Card, ConfidenceBadge, Empty, ErrorBox, FindingStatusBadge, Mono, SeverityBadge, Spinner, Table } from '../../components/ui'
import { fmtDate } from '../../i18n'

const order = { critical: 0, high: 1, medium: 2, low: 3 }

export default function Findings() {
  const [items, setItems] = useState<Finding[] | null>(null)
  const [projects, setProjects] = useState<Record<string, string>>({})
  const [error, setError] = useState<unknown>(null)
  const [onlyOpen, setOnlyOpen] = useState(true)

  useEffect(() => {
    Promise.all([api.get<Finding[]>('/pt/findings'), api.get<Project[]>('/pt/projects')])
      .then(([f, p]) => { setItems(f.sort((a, b) => order[a.severity] - order[b.severity])); setProjects(Object.fromEntries(p.map(x => [x.id, x.name]))) })
      .catch(setError)
  }, [])

  const shown = items?.filter(f => !onlyOpen || !['fixed', 'accepted_risk', 'false_positive'].includes(f.status))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold">ממצאים</h1><p className="text-sm text-slate-500">ראיות, השפעה, תיקון והיסטוריה</p></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyOpen} onChange={e => setOnlyOpen(e.target.checked)} /> פתוחים בלבד</label>
      </div>
      <ErrorBox error={error} />
      <Card>
        {!shown ? <Spinner /> : shown.length === 0 ? <Empty>אין ממצאים להצגה.</Empty> : (
          <Table head={['כותרת', 'פרויקט', 'נכס', 'חומרה', 'ביטחון', 'סטטוס', 'נוצר']}>
            {shown.map(f => (
              <tr key={f.id}>
                <td className="px-3 py-2"><Link to={`/security/findings/${f.id}`} className="text-indigo-700">{f.title}</Link></td>
                <td className="px-3 py-2 text-xs">{projects[f.project_id] ?? f.project_id}</td>
                <td className="px-3 py-2"><Mono>{f.asset_path}</Mono></td>
                <td className="px-3 py-2"><SeverityBadge value={f.severity} /></td>
                <td className="px-3 py-2"><ConfidenceBadge value={f.confidence} /></td>
                <td className="px-3 py-2"><FindingStatusBadge value={f.status} /></td>
                <td className="px-3 py-2 text-xs">{fmtDate(f.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
