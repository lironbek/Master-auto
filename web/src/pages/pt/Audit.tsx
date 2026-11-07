import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AuditEvent } from '../../api'
import { Card, DecisionBadge, Empty, ErrorBox, Spinner, Table } from '../../components/ui'
import { auditAction, decision, fmtDate, t } from '../../i18n'

export default function Audit() {
  const [items, setItems] = useState<AuditEvent[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState('')

  useEffect(() => { api.get<AuditEvent[]>('/pt/audit?limit=500').then(setItems).catch(setError) }, [])
  const shown = items?.filter(e => !q || `${e.action} ${e.decision} ${e.detail} ${e.actor} ${e.run_id ?? ''}`.includes(q))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">ביקורת</h1><p className="text-sm text-slate-500">אירועים, מאשרים ומדיניות שהופעלה. היומן אינו מכיל סודות גולמיים.</p></div>
        <input className="input w-64" placeholder="סינון…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <ErrorBox error={error} />
      <Card>
        {!shown ? <Spinner /> : shown.length === 0 ? <Empty>אין אירועים.</Empty> : (
          <Table head={['זמן', 'מי', 'אירוע', 'החלטה', 'ריצה', 'פרטים']}>
            {shown.map(e => (
              <tr key={e.id}>
                <td className="px-3 py-2 text-xs whitespace-nowrap">{fmtDate(e.at)}</td>
                <td className="px-3 py-2 text-xs">{e.actor}</td>
                <td className="px-3 py-2 text-sm">{t(auditAction, e.action)}</td>
                <td className="px-3 py-2"><DecisionBadge value={e.decision} label={t(decision, e.decision)} /></td>
                <td className="px-3 py-2">{e.run_id ? <Link to={`/security/runs/${e.run_id}`} className="mono text-xs text-indigo-700">{e.run_id}</Link> : ''}</td>
                <td className="px-3 py-2"><span className="mono break-all text-xs text-slate-600">{e.detail}</span></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  )
}
