import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api, type Project } from '../../api'
import { MANAGER_ROLES, useAuth } from '../../auth'
import { Card, Empty, ErrorBox, Field, Spinner } from '../../components/ui'
import { fmtDate } from '../../i18n'

export default function Projects() {
  const { me } = useAuth()
  const canManage = MANAGER_ROLES.includes(me?.user.role ?? '')
  const [items, setItems] = useState<Project[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')

  const load = () => api.get<Project[]>('/pt/projects').then(setItems).catch(setError)
  useEffect(() => { load() }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    try {
      await api.post('/pt/projects', { name, description: desc })
      setName(''); setDesc(''); setOpen(false); load()
    } catch (err) { setError(err) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">פרויקטים והיקף</h1>
          <p className="text-sm text-slate-500">בעלות, חוזי בדיקה, יעדים והחרגות</p>
        </div>
        {canManage && <button className="btn-primary" onClick={() => setOpen(v => !v)}><Plus className="h-4 w-4" /> פרויקט חדש</button>}
      </div>
      <ErrorBox error={error} />
      {open && (
        <Card title="פרויקט חדש">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-3">
            <Field label="שם"><input className="input" value={name} onChange={e => setName(e.target.value)} required /></Field>
            <Field label="תיאור"><input className="input" value={desc} onChange={e => setDesc(e.target.value)} /></Field>
            <div className="flex items-end"><button className="btn-primary">יצירה</button></div>
          </form>
        </Card>
      )}
      {!items ? <Spinner /> : items.length === 0 ? <Empty>אין פרויקטים עדיין.</Empty> : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map(p => (
            <Link key={p.id} to={`/security/projects/${p.id}`} className="card p-4 hover:border-indigo-300">
              <div className="font-semibold">{p.name}</div>
              <div className="text-sm text-slate-500">{p.description || '—'}</div>
              <div className="mt-2 text-xs text-slate-400">נוצר {fmtDate(p.created_at)} · <span className="mono">{p.id}</span></div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
