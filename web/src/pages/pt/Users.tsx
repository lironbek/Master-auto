import { useEffect, useState, type FormEvent } from 'react'
import { api, type Role } from '../../api'
import { useAuth } from '../../auth'
import { Card, Empty, ErrorBox, Field, Spinner, Table } from '../../components/ui'
import { role as roleLabels, t } from '../../i18n'

interface U { id: string; email: string; display_name: string; role: string }

export default function UsersPage() {
  const { me } = useAuth()
  const isAdmin = me?.user.role === 'org_admin'
  const [items, setItems] = useState<U[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [f, setF] = useState({ email: '', password: '', display_name: '', role: 'pt_tester' as Role })

  const load = () => api.get<U[]>('/auth/users').then(setItems).catch(setError)
  useEffect(() => { load() }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    try { await api.post('/auth/users', f); setF({ email: '', password: '', display_name: '', role: 'pt_tester' }); load() } catch (err) { setError(err) }
  }

  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-bold">משתמשים ותפקידים</h1><p className="text-sm text-slate-500">תפקידים לפי סעיף 3: מנהל ארגון, מנהל סקר, בודק PT, מפתח, הנהלה, מבקר, לקוח</p></div>
      <ErrorBox error={error} />
      {isAdmin && (
        <Card title="הוספת משתמש">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-5">
            <Field label="אימייל"><input className="input ltr" type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required /></Field>
            <Field label="שם"><input className="input" value={f.display_name} onChange={e => setF({ ...f, display_name: e.target.value })} /></Field>
            <Field label="סיסמה זמנית"><input className="input ltr" type="text" minLength={8} value={f.password} onChange={e => setF({ ...f, password: e.target.value })} required /></Field>
            <Field label="תפקיד">
              <select className="input" value={f.role} onChange={e => setF({ ...f, role: e.target.value as Role })}>
                {Object.entries(roleLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <div className="flex items-end"><button className="btn-primary">הוספה</button></div>
          </form>
        </Card>
      )}
      <Card title="משתמשי הארגון">
        {!items ? <Spinner /> : items.length === 0 ? <Empty>אין משתמשים.</Empty> : (
          <Table head={['שם', 'אימייל', 'תפקיד']}>
            {items.map(u => <tr key={u.id}><td className="px-3 py-2">{u.display_name || '—'}</td><td className="px-3 py-2"><span className="ltr text-xs">{u.email}</span></td><td className="px-3 py-2 text-sm">{t(roleLabels, u.role)}</td></tr>)}
          </Table>
        )}
      </Card>
    </div>
  )
}
