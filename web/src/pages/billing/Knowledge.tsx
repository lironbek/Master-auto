import { useEffect, useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { api } from '../../api'
import { Card, Empty, ErrorBox, Field, Spinner } from '../../components/ui'
import { FirstWorkspace } from '../../components/cc'
import { fmtDate } from '../../i18n'
import { useWorkspace } from '../../workspace'
import type { BlKnowledge, BlProduct } from './types'

export default function BlKnowledgePage() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [items, setItems] = useState<BlKnowledge[] | null>(null)
  const [products, setProducts] = useState<BlProduct[]>([])
  const [error, setError] = useState<unknown>(null)
  const [q, setQ] = useState('')
  const [product, setProduct] = useState('')
  const [category, setCategory] = useState('')
  const [selected, setSelected] = useState<BlKnowledge | null>(null)
  const [edit, setEdit] = useState<BlKnowledge | null | 'new'>(null)
  const ws = current?.id || workspaces[0]?.id
  const load = () => Promise.all([api.get<BlKnowledge[]>(`/billing/knowledge${qs}`), api.get<BlProduct[]>(`/billing/products${qs}`)]).then(([k, p]) => { setItems(k); setProducts(p) }).catch(setError)
  useEffect(() => { if (!loading && workspaces.length) load() }, [qs, loading, workspaces.length])
  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  async function save(e: FormEvent) {
    e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement)
    const body = { title: fd.get('title'), content: fd.get('content'), category: fd.get('category'), product_id: String(fd.get('product_id') ?? ''), tags: String(fd.get('tags') ?? '').split(',').map(s => s.trim()).filter(Boolean) }
    try { if (edit && edit !== 'new') await api.patch(`/billing/knowledge/${edit.id}`, body); else await api.post('/billing/knowledge', { workspace_id: fd.get('workspace_id') || ws, ...body }); setEdit(null); load() } catch (err) { setError(err) }
  }
  async function remove(id: string) { if (!confirm('למחוק את המאמר?')) return; try { await api.del(`/billing/knowledge/${id}`); setSelected(null); load() } catch (err) { setError(err) } }
  const categories = Array.from(new Set((items ?? []).map(a => a.category).filter(Boolean)))
  const shown = (items ?? []).filter(a => (!product || a.product_id === product) && (!category || a.category === category) && (!q || `${a.title} ${a.content} ${(a.tags ?? []).join(' ')}`.toLowerCase().includes(q.toLowerCase())))
  const editing = edit && edit !== 'new' ? edit : null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">מאגר ידע</h1><p className="text-sm text-slate-500">פתרונות, נהלים והגדרות לפי מוצר, קטגוריה ותגיות. נשמר בבסיס הנתונים.</p></div>
        <button className="btn-primary" onClick={() => setEdit('new')}><Plus className="h-4 w-4" /> מאמר חדש</button>
      </div>
      <ErrorBox error={error} />
      {edit && (
        <Card title={editing ? 'עריכת מאמר' : 'מאמר חדש'} actions={<button className="text-xs text-slate-500" onClick={() => setEdit(null)}>ביטול</button>}>
          <form key={editing?.id ?? 'new'} onSubmit={save} className="grid gap-3 md:grid-cols-4">
            {!current && !editing && <Field label="מרחב"><select className="input" name="workspace_id" defaultValue={ws}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>}
            <Field label="כותרת"><input className="input" name="title" defaultValue={editing?.title ?? ''} required /></Field>
            <Field label="מוצר"><select className="input" name="product_id" defaultValue={editing?.product_id ?? ''}><option value="">כללי</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="קטגוריה"><input className="input" name="category" defaultValue={editing?.category ?? ''} list="kb-cats" /><datalist id="kb-cats">{categories.map(c => <option key={c} value={c} />)}</datalist></Field>
            <Field label="תגיות (מופרדות בפסיק)"><input className="input" name="tags" defaultValue={(editing?.tags ?? []).join(', ')} /></Field>
            <div className="md:col-span-4"><Field label="תוכן"><textarea className="input font-mono text-sm" name="content" rows={10} defaultValue={editing?.content ?? ''} /></Field></div>
            <div className="md:col-span-4"><button className="btn-primary">שמירה</button></div>
          </form>
        </Card>
      )}
      <Card>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="חיפוש"><input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="חפש במאגר הידע…" /></Field>
          <Field label="מוצר"><select className="input" value={product} onChange={e => setProduct(e.target.value)}><option value="">כל המוצרים</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="קטגוריה"><select className="input" value={category} onChange={e => setCategory(e.target.value)}><option value="">כל הקטגוריות</option>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select></Field>
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={`מאמרים (${shown.length})`}>
          {!items ? <Spinner /> : shown.length === 0 ? <Empty>אין מאמרים.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">{shown.map(a => <li key={a.id}><button className={`w-full py-2 text-right ${selected?.id === a.id ? 'font-semibold text-indigo-700' : ''}`} onClick={() => setSelected(a)}>{a.title}<div className="text-xs font-normal text-slate-500">{a.product_name || 'כללי'}{a.category ? ` · ${a.category}` : ''}</div></button></li>)}</ul>
          )}
        </Card>
        <Card title={selected?.title ?? 'בחר מאמר'} className="lg:col-span-2" actions={selected && <div className="flex gap-2 text-xs"><button className="text-indigo-700" onClick={() => setEdit(selected)}>עריכה</button><button className="text-rose-700" onClick={() => remove(selected.id)}>מחק</button></div>}>
          {!selected ? <Empty>בחר מאמר מהרשימה.</Empty> : (
            <div>
              <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500"><span>{selected.product_name || 'כללי'}</span>{selected.category && <span>· {selected.category}</span>}<span>· עודכן {fmtDate(selected.created_at)}</span>{(selected.tags ?? []).map(t => <span key={t} className="badge bg-indigo-50 text-indigo-700">{t}</span>)}</div>
              <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">{selected.content}</pre>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
