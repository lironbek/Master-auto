import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Printer } from 'lucide-react'
import { api, download, openPrint } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { hhmm, monthStart, today, type BlCustomer, type BlHoursReport } from './types'

export default function BlHoursReport() {
  const { workspaces, current, loading } = useWorkspace()
  const [customers, setCustomers] = useState<BlCustomer[]>([])
  const [rep, setRep] = useState<BlHoursReport | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [f, setF] = useState({ customer_id: '', from: monthStart(), to: today() })
  const ws = current?.id || workspaces[0]?.id
  useEffect(() => { if (ws) api.get<BlCustomer[]>(`/billing/customers?workspace_id=${ws}`).then(setCustomers).catch(setError) }, [ws])
  const query = () => `workspace_id=${ws}&from=${f.from}&to=${f.to}${f.customer_id ? `&customer_id=${f.customer_id}` : ''}`
  useEffect(() => { if (ws) api.get<BlHoursReport>(`/billing/reports/hours?${query()}`).then(setRep).catch(setError) }, [ws, f.customer_id, f.from, f.to])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">דוח שעות טיפול</h1><p className="text-sm text-slate-500">רישומי הזמן של לקוח בטווח תאריכים, לפי קריאה ולפי מטפל. להדפסה, ל-PDF ולאקסל.</p></div>
        <div className="flex gap-2"><button className="btn-secondary" onClick={() => openPrint(`/billing/reports/hours?${query()}&format=html`)}><Printer className="h-4 w-4" /> הדפסה / PDF</button><button className="btn-secondary" onClick={() => download(`/billing/reports/hours?${query()}&format=xlsx`, `hours_${f.from}_${f.to}.xlsx`)}><Download className="h-4 w-4" /> אקסל</button></div>
      </div>
      <ErrorBox error={error} />
      <Card>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="לקוח"><select className="input" value={f.customer_id} onChange={e => setF({ ...f, customer_id: e.target.value })}><option value="">כל הלקוחות</option>{customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="מתאריך"><input className="input ltr" type="date" value={f.from} onChange={e => setF({ ...f, from: e.target.value })} /></Field>
          <Field label="עד תאריך"><input className="input ltr" type="date" value={f.to} onChange={e => setF({ ...f, to: e.target.value })} /></Field>
        </div>
      </Card>
      {!rep ? <Spinner /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="סה״כ שעות" value={hhmm(rep.total_minutes)} tone="indigo" />
            <Stat label="רישומים" value={rep.entries.length} />
            <Stat label="קריאות" value={rep.by_ticket.length} />
            <Stat label="טרם חויב" value={hhmm(rep.entries.filter(e => !e.billed).reduce((a, e) => a + e.minutes, 0))} tone="amber" />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="רישומי זמן" className="lg:col-span-2">
              {rep.entries.length === 0 ? <Empty>אין רישומי זמן בטווח.</Empty> : (
                <Table head={['תאריך', 'קריאה', 'לקוח', 'מטפל', 'תיאור', 'זמן', '']}>
                  {rep.entries.map(e => <tr key={e.id}><td className="px-3 py-2 text-xs ltr">{e.entry_date}</td><td className="px-3 py-2 text-sm"><Link to={`/billing/tickets/${e.ticket_id}`} className="text-indigo-700">{e.ticket_title}</Link></td><td className="px-3 py-2 text-sm">{e.customer_name}</td><td className="px-3 py-2 text-sm">{e.employee_name || '—'}</td><td className="px-3 py-2 text-sm">{e.description}</td><td className="px-3 py-2 text-sm ltr">{hhmm(e.minutes)}</td><td className="px-3 py-2 text-xs">{e.billed && <span className="badge bg-emerald-100 text-emerald-800">חויב</span>}</td></tr>)}
                </Table>
              )}
            </Card>
            <div className="space-y-4">
              <Card title="לפי מטפל">{rep.by_employee.length === 0 ? <Empty>—</Empty> : <ul className="divide-y divide-slate-100 text-sm">{rep.by_employee.map(x => <li key={x.employee_name} className="flex justify-between py-1.5"><span>{x.employee_name}</span><span className="font-semibold ltr">{hhmm(x.minutes)}</span></li>)}</ul>}</Card>
              <Card title="לפי קריאה">{rep.by_ticket.length === 0 ? <Empty>—</Empty> : <ul className="divide-y divide-slate-100 text-sm">{rep.by_ticket.slice(0, 15).map(x => <li key={x.ticket_id} className="flex justify-between gap-2 py-1.5"><Link to={`/billing/tickets/${x.ticket_id}`} className="truncate text-indigo-700">{x.ticket_title}</Link><span className="font-semibold ltr">{hhmm(x.minutes)}</span></li>)}</ul>}</Card>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
