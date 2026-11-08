import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type CcProject } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { useWorkspace } from '../../workspace'
import { ils, type BlProduct, type BlService } from './types'

export default function BlCatalog() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [products, setProducts] = useState<BlProduct[] | null>(null)
  const [services, setServices] = useState<BlService[] | null>(null)
  const [projects, setProjects] = useState<CcProject[]>([])
  const [error, setError] = useState<unknown>(null)
  const [tab, setTab] = useState<'products' | 'services'>('products')
  const [editP, setEditP] = useState<BlProduct | null>(null)
  const [editS, setEditS] = useState<BlService | null>(null)
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlProduct[]>(`/billing/products${qs}`), api.get<BlService[]>(`/billing/services${qs}`), api.get<CcProject[]>('/cc/projects')])
    .then(([p, s, pr]) => { setProducts(p); setServices(s); setProjects(pr.filter(x => x.status === 'active')) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />

  async function saveProduct(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { name: fd.get('name'), description: fd.get('description'), price: Number(fd.get('price') || 0), has_light_user: fd.get('has_light_user') === 'on', light_user_price: Number(fd.get('light_user_price') || 0), project_id: String(fd.get('project_id') ?? '') }
    try { if (editP) await api.patch(`/billing/products/${editP.id}`, body); else await api.post('/billing/products', { workspace_id: fd.get('workspace_id') || ws, ...body }); setEditP(null); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function saveService(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { description: fd.get('description'), price: Number(fd.get('price') || 0), recurring: fd.get('recurring') === 'on' }
    try { if (editS) await api.patch(`/billing/services/${editS.id}`, body); else await api.post('/billing/services', { workspace_id: fd.get('workspace_id') || ws, ...body }); setEditS(null); (e.target as HTMLFormElement).reset(); load() } catch (err) { setError(err) }
  }
  async function remove(kind: 'products' | 'services', id: string) {
    if (!confirm('למחוק?')) return
    try { await api.del(`/billing/${kind}/${id}`); load() } catch (err) { setError(err) }
  }
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">מוצרים ושירותים</h1><p className="text-sm text-slate-500">מוצר מחויב לפי משתמשים בחודש (ואופציונלית משתמשי Light). שירות הוא סכום קבוע, חד-פעמי או מתחדש כל חודש.</p></div>
      <ErrorBox error={error} />
      <div className="flex gap-2">{(['products', 'services'] as const).map(k => <button key={k} className={`btn-secondary ${tab === k ? '!bg-slate-800 !text-white' : ''}`} onClick={() => setTab(k)}>{k === 'products' ? `מוצרים (${products?.length ?? 0})` : `שירותים (${services?.length ?? 0})`}</button>)}</div>
      {tab === 'products' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="מוצרים" className="lg:col-span-2">
            {!products ? <Spinner /> : products.length === 0 ? <Empty>אין מוצרים עדיין.</Empty> : (
              <Table head={['מוצר', 'מחיר למשתמש', 'Light', 'לקוחות', 'משתמשים', 'פרויקט', '']}>
                {products.map(p => (
                  <tr key={p.id}>
                    <td className="px-3 py-2 font-medium">{p.name}<div className="text-xs text-slate-500">{p.description}</div></td>
                    <td className="px-3 py-2 text-sm"><bdi>{ils(p.price)}</bdi></td>
                    <td className="px-3 py-2 text-sm">{p.has_light_user ? <bdi>{ils(p.light_user_price)}</bdi> : '—'}</td>
                    <td className="px-3 py-2 text-sm">{p.customers ?? 0}</td>
                    <td className="px-3 py-2 text-sm">{p.users ?? 0}{p.light ? <span className="text-xs text-slate-500"> + {p.light} Light</span> : ''}</td>
                    <td className="px-3 py-2 text-xs">{p.project_id ? <Link to={`/projects/${p.project_id}`} className="text-indigo-600">{projects.find(x => x.id === p.project_id)?.name ?? 'פרויקט'}</Link> : '—'}</td>
                    <td className="px-3 py-2 text-xs"><div className="flex gap-2"><button className="text-indigo-700" onClick={() => setEditP(p)}>עריכה</button><button className="text-rose-700" onClick={() => remove('products', p.id)}>מחק</button></div></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title={editP ? `עריכת ${editP.name}` : 'מוצר חדש'} actions={editP && <button className="text-xs text-slate-500" onClick={() => setEditP(null)}>ביטול</button>}>
            <form key={editP?.id ?? 'new'} onSubmit={saveProduct} className="space-y-3">
              {!current && !editP && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={ws}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
              <Field label="שם"><input className="input" name="name" defaultValue={editP?.name ?? ''} required /></Field>
              <Field label="תיאור"><input className="input" name="description" defaultValue={editP?.description ?? ''} /></Field>
              <Field label="מחיר למשתמש לחודש (₪)"><input className="input ltr" name="price" type="number" min={0} step="0.01" defaultValue={editP ? Number(editP.price) : 0} /></Field>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="has_light_user" defaultChecked={editP?.has_light_user ?? false} /> יש משתמש Light</label>
              <Field label="מחיר משתמש Light (₪)"><input className="input ltr" name="light_user_price" type="number" min={0} step="0.01" defaultValue={editP ? Number(editP.light_user_price) : 0} /></Field>
              <Field label="פרויקט במרכז הבקרה" hint="איפה הקוד והפריסה של המוצר"><select className="input" name="project_id" defaultValue={editP?.project_id ?? ''}><option value="">ללא</option>{projects.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
              <button className="btn-primary w-full justify-center">{editP ? 'שמירה' : 'הוספה'}</button>
            </form>
          </Card>
        </div>
      )}
      {tab === 'services' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="שירותים" className="lg:col-span-2">
            {!services ? <Spinner /> : services.length === 0 ? <Empty>אין שירותים עדיין.</Empty> : (
              <Table head={['שירות', 'מחיר', 'חיוב', '']}>
                {services.map(s => <tr key={s.id}><td className="px-3 py-2 font-medium">{s.description}</td><td className="px-3 py-2 text-sm"><bdi>{ils(s.price)}</bdi></td><td className="px-3 py-2"><span className={`badge ${s.recurring ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-600'}`}>{s.recurring ? 'מתחדש כל חודש' : 'חד-פעמי'}</span></td><td className="px-3 py-2 text-xs"><div className="flex gap-2"><button className="text-indigo-700" onClick={() => setEditS(s)}>עריכה</button><button className="text-rose-700" onClick={() => remove('services', s.id)}>מחק</button></div></td></tr>)}
              </Table>
            )}
          </Card>
          <Card title={editS ? 'עריכת שירות' : 'שירות חדש'} actions={editS && <button className="text-xs text-slate-500" onClick={() => setEditS(null)}>ביטול</button>}>
            <form key={editS?.id ?? 'new'} onSubmit={saveService} className="space-y-3">
              {!current && !editS && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={ws}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
              <Field label="תיאור"><input className="input" name="description" defaultValue={editS?.description ?? ''} required /></Field>
              <Field label="מחיר (₪)"><input className="input ltr" name="price" type="number" min={0} step="0.01" defaultValue={editS ? Number(editS.price) : 0} /></Field>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="recurring" defaultChecked={editS?.recurring ?? false} /> חיוב מתחדש כל חודש</label>
              <button className="btn-primary w-full justify-center">{editS ? 'שמירה' : 'הוספה'}</button>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
