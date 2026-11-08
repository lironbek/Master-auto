import { useEffect, useState, type FormEvent } from 'react'
import { Download } from 'lucide-react'
import { api, download } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Stat, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { expenseCategory, ils, today, type BlExpense } from './types'

export default function BlExpenses() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [items, setItems] = useState<BlExpense[] | null>(null)
  const [edit, setEdit] = useState<BlExpense | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [f, setF] = useState({ q: '', category: '', recurring: '', from: '', to: '' })
  const ws = current?.id || workspaces[0]?.id
  const load = () => api.get<BlExpense[]>(`/billing/expenses${qs}`).then(setItems).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { name: fd.get('name'), amount: Number(fd.get('amount') || 0), currency: fd.get('currency'), category: fd.get('category'), expense_date: fd.get('expense_date'), description: fd.get('description'), recurring: fd.get('recurring') === 'on', rate: fd.get('rate') ? Number(fd.get('rate')) : undefined }
    try { if (edit) await api.patch(`/billing/expenses/${edit.id}`, body); else await api.post('/billing/expenses', { workspace_id: fd.get('workspace_id') || ws, ...body }); setEdit(null); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function remove(id: string) { if (!confirm('למחוק את ההוצאה?')) return; try { await api.del(`/billing/expenses/${id}`); load() } catch (err) { setError(err) } }
  const shown = (items ?? []).filter(x => (!f.q || `${x.name} ${x.description}`.toLowerCase().includes(f.q.toLowerCase())) && (!f.category || x.category === f.category)
    && (!f.recurring || String(x.recurring) === f.recurring) && (!f.from || x.expense_date >= f.from) && (!f.to || x.expense_date <= f.to))
    .sort((a, b) => String(b.expense_date).localeCompare(String(a.expense_date)))
  const total = shown.reduce((a, x) => a + Number(x.amount_ils), 0)
  const month = today().slice(0, 7)
  const monthTotal = (items ?? []).filter(x => String(x.expense_date).startsWith(month)).reduce((a, x) => a + Number(x.amount_ils), 0)
  const recurring = (items ?? []).filter(x => x.recurring).reduce((a, x) => a + Number(x.amount_ils), 0)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">הוצאות</h1><p className="text-sm text-slate-500">הוצאות העסק בכל מטבע, מומרות לש"ח לפי שער היום (או שער ידני). הוצאות ענן שהמערכת אוספת מופיעות בדף <a href="/costs" className="text-indigo-600">עלויות</a>.</p></div>
        <button className="btn-secondary" onClick={() => ws && download(`/billing/exports/expenses.xlsx?workspace_id=${ws}`, 'expenses.xlsx')}><Download className="h-4 w-4" /> אקסל</button>
      </div>
      <ErrorBox error={error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="סה״כ בסינון" value={ils(total)} hint={`${shown.length} הוצאות`} />
        <Stat label="החודש" value={ils(monthTotal)} tone="rose" />
        <Stat label="הוצאות חוזרות (חודשי)" value={ils(recurring)} />
        <Stat label="קטגוריה גדולה" value={(() => { const m: Record<string, number> = {}; shown.forEach(x => { m[x.category] = (m[x.category] ?? 0) + Number(x.amount_ils) }); const top = Object.entries(m).sort((a, b) => b[1] - a[1])[0]; return top ? expenseCategory[top[0]] ?? top[0] : '—' })()} />
      </div>
      <Card>
        <div className="grid gap-3 md:grid-cols-5">
          <Field label="חיפוש"><input className="input" value={f.q} onChange={e => setF({ ...f, q: e.target.value })} /></Field>
          <Field label="קטגוריה"><select className="input" value={f.category} onChange={e => setF({ ...f, category: e.target.value })}><option value="">הכול</option>{Object.entries(expenseCategory).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="חוזרת"><select className="input" value={f.recurring} onChange={e => setF({ ...f, recurring: e.target.value })}><option value="">הכול</option><option value="true">כן</option><option value="false">לא</option></select></Field>
          <Field label="מתאריך"><input className="input ltr" type="date" value={f.from} onChange={e => setF({ ...f, from: e.target.value })} /></Field>
          <Field label="עד תאריך"><input className="input ltr" type="date" value={f.to} onChange={e => setF({ ...f, to: e.target.value })} /></Field>
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="הוצאות" className="lg:col-span-2">
          {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין הוצאות.</Empty> : (
            <Table head={['תאריך', 'הוצאה', 'קטגוריה', 'סכום', 'בש"ח', 'חוזרת', '']}>
              {shown.map(x => (
                <tr key={x.id}>
                  <td className="px-3 py-2 text-xs ltr">{String(x.expense_date).slice(0, 10)}</td>
                  <td className="px-3 py-2 font-medium">{x.name}<div className="text-xs text-slate-500">{x.description}</div></td>
                  <td className="px-3 py-2 text-xs">{expenseCategory[x.category] ?? x.category}</td>
                  <td className="px-3 py-2 text-sm"><bdi>{Number(x.amount).toLocaleString('he-IL')} {x.currency}</bdi>{x.currency !== 'ILS' && <div className="text-[10px] text-slate-400">שער {Number(x.rate_used)}{x.rate_source === 'manual' ? ' (ידני)' : ''}</div>}</td>
                  <td className="px-3 py-2 font-semibold"><bdi>{ils(x.amount_ils)}</bdi></td>
                  <td className="px-3 py-2 text-xs">{x.recurring ? 'כן' : 'לא'}</td>
                  <td className="px-3 py-2 text-xs"><div className="flex gap-2"><button className="text-indigo-700" onClick={() => setEdit(x)}>עריכה</button><button className="text-rose-700" onClick={() => remove(x.id)}>מחק</button></div></td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title={edit ? 'עריכת הוצאה' : 'הוצאה חדשה'} actions={edit && <button className="text-xs text-slate-500" onClick={() => setEdit(null)}>ביטול</button>}>
          <form key={edit?.id ?? 'new'} onSubmit={save} className="space-y-3">
            {!current && !edit && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={ws}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
            <Field label="שם"><input className="input" name="name" defaultValue={edit?.name ?? ''} required /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="סכום"><input className="input ltr" name="amount" type="number" min={0} step="0.01" defaultValue={edit ? Number(edit.amount) : ''} required /></Field>
              <Field label="מטבע"><select className="input" name="currency" defaultValue={edit?.currency ?? 'ILS'}><option>ILS</option><option>USD</option><option>EUR</option></select></Field>
            </div>
            <Field label="קטגוריה"><select className="input" name="category" defaultValue={edit?.category ?? 'software'}>{Object.entries(expenseCategory).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="תאריך"><input className="input ltr" name="expense_date" type="date" defaultValue={edit ? String(edit.expense_date).slice(0, 10) : today()} /></Field>
            <Field label="שער ידני (אופציונלי)" hint="ריק = שער היום לפי טבלת השערים"><input className="input ltr" name="rate" type="number" min={0} step="0.0001" /></Field>
            <Field label="תיאור"><input className="input" name="description" defaultValue={edit?.description ?? ''} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="recurring" defaultChecked={edit?.recurring ?? false} /> הוצאה חוזרת</label>
            <button className="btn-primary w-full justify-center">{edit ? 'שמירה' : 'הוספה'}</button>
          </form>
        </Card>
      </div>
    </div>
  )
}
