import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { useAuth } from '../auth'
import { ErrorBox, Field } from '../components/ui'

export default function Login() {
  const { me, login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [org, setOrg] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  if (me) return <Navigate to="/" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      if (mode === 'login') await login(email, password)
      else await register(org, email, password, name)
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-md p-6">
        <div className="mb-6 flex items-center gap-3">
          <Shield className="h-8 w-8 text-indigo-600" />
          <div>
            <h1 className="text-lg font-bold">PT Agent</h1>
            <p className="text-xs text-slate-500">פלטפורמה לסקרי אבטחה ובדיקות חדירה מורשות</p>
          </div>
        </div>
        <div className="mb-4 flex rounded-lg bg-slate-100 p-1 text-sm">
          <button className={`flex-1 rounded-md py-1.5 ${mode === 'login' ? 'bg-white shadow font-semibold' : 'text-slate-600'}`} onClick={() => setMode('login')}>כניסה</button>
          <button className={`flex-1 rounded-md py-1.5 ${mode === 'register' ? 'bg-white shadow font-semibold' : 'text-slate-600'}`} onClick={() => setMode('register')}>פתיחת ארגון חדש</button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          {mode === 'register' && (
            <>
              <Field label="שם הארגון"><input className="input" value={org} onChange={e => setOrg(e.target.value)} required /></Field>
              <Field label="שם מלא"><input className="input" value={name} onChange={e => setName(e.target.value)} /></Field>
            </>
          )}
          <Field label="אימייל"><input className="input ltr" type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="username" /></Field>
          <Field label="סיסמה" hint={mode === 'register' ? 'לפחות 8 תווים' : undefined}>
            <input className="input ltr" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          </Field>
          <ErrorBox error={error} />
          <button className="btn-primary w-full justify-center" disabled={busy}>{mode === 'login' ? 'כניסה' : 'פתיחת ארגון וכניסה'}</button>
        </form>
        <p className="mt-4 text-xs text-slate-400">הרשאה לבדיקה אינה נובעת מעצם הזנת כתובת אתר. כל ריצה מחייבת חוזה בדיקה מאושר.</p>
      </div>
    </div>
  )
}
