import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Clock, FileText, Receipt, Users, Wallet, Wrench } from 'lucide-react'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Spinner } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { Sparkline } from '../../components/charts'
import { fmtRel } from '../../i18n'
import { useWorkspace } from '../../workspace'
import { activityType, hhmm, ils, periodLabel, type BlOverview } from './types'

function Tile({ label, value, hint, icon, tint, spark, tone, to }: { label: string; value: string; hint?: string; icon: React.ReactNode; tint: string; spark?: number[]; tone?: 'teal' | 'violet' | 'amber' | 'rose' | 'sky'; to: string }) {
  return (
    <Link to={to} className="tile flex flex-col gap-3 transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between"><div className="text-sm font-semibold text-slate-700">{label}</div><span className={`icon-tile ${tint}`}>{icon}</span></div>
      <div className="flex items-end justify-between gap-2"><div className="text-2xl font-bold tracking-tight text-slate-900">{value}</div>{spark && <Sparkline values={spark} tone={tone} />}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </Link>
  )
}

export default function BillingDashboard() {
  const { workspaces, qs, loading } = useWorkspace()
  const [d, setD] = useState<BlOverview | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => { if (!loading && workspaces.length) api.get<BlOverview>(`/billing/overview${qs}`).then(setD).catch(setError) }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const cur = d.months[d.months.length - 1]
  const maxRev = Math.max(1, ...d.revenue, ...d.expenses)
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-extrabold tracking-tight">חיוב ושירות</h1><p className="text-sm text-slate-500">לקוחות, מנויים, קריאות שירות, שעות וחיובים חודשיים. {periodLabel(cur)}.</p></div>
        <div className="flex gap-2"><Link to="/billing/tickets?new=1" className="btn-primary">קריאה חדשה</Link><Link to="/billing/charges" className="btn-secondary">חיובים</Link></div>
      </div>
      <ErrorBox error={error} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="הכנסות החודש" value={ils(d.revenue_month)} hint={`${d.unpaid_count} חיובים פתוחים · ${ils(d.unpaid_total)}`} icon={<Wallet className="h-5 w-5" />} tint="bg-emerald-100 text-emerald-700" spark={d.revenue} tone="teal" to="/billing/charges" />
        <Tile label="הוצאות החודש" value={ils(d.expenses_month)} hint={d.revenue_month ? `רווח גולמי ${ils(d.revenue_month - d.expenses_month)}` : undefined} icon={<Receipt className="h-5 w-5" />} tint="bg-rose-100 text-rose-700" spark={d.expenses} tone="rose" to="/billing/expenses" />
        <Tile label="קריאות פתוחות" value={String(d.open_tickets)} hint={d.avg_resolution_minutes ? `ממוצע טיפול ${hhmm(d.avg_resolution_minutes)} שעות` : 'אין קריאות סגורות עדיין'} icon={<Wrench className="h-5 w-5" />} tint="bg-amber-100 text-amber-700" spark={d.tickets_opened} tone="amber" to="/billing/tickets?status=active" />
        <Tile label="שעות טיפול החודש" value={String(d.hours_month)} hint={`${d.customers} לקוחות פעילים`} icon={<Clock className="h-5 w-5" />} tint="bg-sky-100 text-sky-700" spark={d.hours} tone="sky" to="/billing/reports/hours" />
      </div>
      {d.drafts > 0 && <div className="flex items-center justify-between rounded-xl bg-indigo-50 px-4 py-2 text-sm text-indigo-900"><span><FileText className="mr-1 inline h-4 w-4" /> {d.drafts} חיובים בטיוטה ממתינים להפקה</span><Link to="/billing/charges?status=draft" className="font-semibold">לטיוטות ←</Link></div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="הכנסות מול הוצאות" className="lg:col-span-2">
          <div className="flex items-end gap-3" style={{ height: 160 }} role="img" aria-label="הכנסות והוצאות לפי חודש">
            {d.months.map((m, i) => (
              <div key={m} className="flex flex-1 flex-col items-center gap-1" title={`${periodLabel(m)}: הכנסות ${ils(d.revenue[i])}, הוצאות ${ils(d.expenses[i])}`}>
                <div className="flex w-full items-end justify-center gap-1" style={{ height: 130 }}>
                  <div className="w-2/5 rounded-t-md bg-emerald-400" style={{ height: Math.max(3, (d.revenue[i] / maxRev) * 126) }} />
                  <div className="w-2/5 rounded-t-md bg-rose-300" style={{ height: Math.max(3, (d.expenses[i] / maxRev) * 126) }} />
                </div>
                <span className="text-[10px] text-slate-500">{periodLabel(m).split(' ')[0]}</span>
              </div>
            ))}
          </div>
          <div className="mt-2 flex gap-4 text-xs text-slate-500"><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-emerald-400" /> הכנסות (חיובים)</span><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-rose-300" /> הוצאות</span></div>
        </Card>
        <Card title={<span className="flex items-center gap-2"><Users className="h-4 w-4 text-indigo-500" /> משתמשים לפי מוצר</span>}>
          {d.users_by_product.length === 0 ? <Empty>אין מנויים פעילים.</Empty> : (
            <ul className="space-y-2 text-sm">{d.users_by_product.map(p => { const max = d.users_by_product[0].users || 1; return (
              <li key={p.name}><div className="flex justify-between"><span>{p.name}</span><span className="font-semibold">{p.users}</span></div><div className="mt-1 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-indigo-400" style={{ width: `${Math.max(4, (p.users / max) * 100)}%` }} /></div></li>) })}</ul>
          )}
        </Card>
      </div>
      <Card title="פעילות אחרונה" actions={<Link to="/billing/activities" className="text-xs font-semibold text-indigo-600">הכול</Link>}>
        {d.recent.length === 0 ? <Empty>אין פעילות עדיין. פתח קריאת שירות ראשונה.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">{d.recent.map(a => (
            <li key={a.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="badge bg-slate-100 text-slate-700">{activityType[a.type]}</span>
              <Link to={`/billing/tickets/${a.ticket_id}`} className="font-medium text-indigo-700">{a.title}</Link>
              <span className="text-xs text-slate-500">{a.customer_name}{a.actor ? ` · ${a.actor}` : ''}{a.minutes ? ` · ${hhmm(a.minutes)}` : ''}</span>
              <span className="mr-auto text-xs text-slate-400">{fmtRel(a.at)}</span>
            </li>))}</ul>
        )}
      </Card>
    </div>
  )
}
