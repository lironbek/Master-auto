import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { confidence, findingStatus, runStatus, scopeStatus, severity, t } from '../i18n'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone = 'slate' }: { label: string; value: ReactNode; hint?: string; tone?: 'slate' | 'indigo' | 'rose' | 'amber' | 'emerald' }) {
  const tones = { slate: 'text-slate-900', indigo: 'text-indigo-700', rose: 'text-rose-700', amber: 'text-amber-700', emerald: 'text-emerald-700' }
  return (
    <div className="card p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${tones[tone]}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  )
}

const sevTone: Record<string, string> = { low: 'bg-slate-100 text-slate-700', medium: 'bg-amber-100 text-amber-800', high: 'bg-orange-100 text-orange-800', critical: 'bg-rose-100 text-rose-800' }
export function SeverityBadge({ value }: { value: string }) { return <span className={`badge ${sevTone[value] ?? 'bg-slate-100'}`}>{t(severity, value)}</span> }

const runTone: Record<string, string> = { created: 'bg-slate-100 text-slate-700', running: 'bg-indigo-100 text-indigo-800', paused: 'bg-amber-100 text-amber-800', stopped: 'bg-rose-100 text-rose-800', completed: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-800' }
export function RunBadge({ value }: { value: string }) { return <span className={`badge ${runTone[value] ?? 'bg-slate-100'}`}>{t(runStatus, value)}</span> }

const scopeTone: Record<string, string> = { draft: 'bg-slate-100 text-slate-700', approved: 'bg-emerald-100 text-emerald-800', superseded: 'bg-slate-200 text-slate-500' }
export function ScopeBadge({ value }: { value: string }) { return <span className={`badge ${scopeTone[value] ?? 'bg-slate-100'}`}>{t(scopeStatus, value)}</span> }

const fsTone: Record<string, string> = { new: 'bg-indigo-100 text-indigo-800', in_review: 'bg-sky-100 text-sky-800', approved: 'bg-violet-100 text-violet-800', in_progress: 'bg-amber-100 text-amber-800', awaiting_retest: 'bg-amber-100 text-amber-800', fixed: 'bg-emerald-100 text-emerald-800', accepted_risk: 'bg-slate-200 text-slate-700', false_positive: 'bg-slate-200 text-slate-500' }
export function FindingStatusBadge({ value }: { value: string }) { return <span className={`badge ${fsTone[value] ?? 'bg-slate-100'}`}>{t(findingStatus, value)}</span> }

const confTone: Record<string, string> = { verified: 'bg-emerald-100 text-emerald-800', suspected: 'bg-amber-100 text-amber-800', needs_manual: 'bg-sky-100 text-sky-800' }
export function ConfidenceBadge({ value }: { value: string }) { return <span className={`badge ${confTone[value] ?? 'bg-slate-100'}`}>{t(confidence, value)}</span> }

const decTone: Record<string, string> = { allow: 'bg-emerald-100 text-emerald-800', ok: 'bg-emerald-100 text-emerald-800', block: 'bg-rose-100 text-rose-800', blocked: 'bg-rose-100 text-rose-800', require_approval: 'bg-amber-100 text-amber-800', halt: 'bg-rose-100 text-rose-800', error: 'bg-rose-100 text-rose-800', ignored_injection: 'bg-violet-100 text-violet-800' }
export function DecisionBadge({ value, label }: { value: string; label: string }) { return value ? <span className={`badge ${decTone[value] ?? 'bg-slate-100 text-slate-700'}`}>{label}</span> : null }

export function Spinner({ label = 'טוען…' }: { label?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> {label}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{children}</div>
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null
  const msg = error instanceof Error ? error.message : String(error)
  return <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{msg}</div>
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  )
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="text-right text-xs text-slate-500">{head.map((h, i) => <th key={i} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  )
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`mono text-xs ${className}`}>{children}</span>
}
