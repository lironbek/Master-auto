import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Evidence, type Finding } from '../../api'
import { Card, ConfidenceBadge, Empty, ErrorBox, FindingStatusBadge, Mono, SeverityBadge, Spinner } from '../../components/ui'
import { evidenceKind, findingStatus, findingTransitions, fmtDate, t } from '../../i18n'

export default function FindingPage() {
  const { id } = useParams()
  const [d, setD] = useState<{ finding: Finding; evidence: Evidence[] } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [note, setNote] = useState('')

  const load = useCallback(() => api.get<{ finding: Finding; evidence: Evidence[] }>(`/pt/findings/${id}`).then(setD).catch(setError), [id])
  useEffect(() => { load() }, [load])

  async function change(status: string) {
    try { await api.post(`/pt/findings/${id}/status`, { status, note }); setNote(''); load() } catch (err) { setError(err) }
  }

  if (error && !d) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const f = d.finding
  const next = findingTransitions[f.status] ?? []
  const Row = ({ label, value }: { label: string; value?: string }) => value ? <div><dt className="text-xs text-slate-500">{label}</dt><dd className="text-sm">{value}</dd></div> : null

  return (
    <div className="space-y-4">
      <div>
        <Link to={`/security/runs/${f.run_id}`} className="text-xs text-indigo-600">← לריצה</Link>
        <h1 className="text-xl font-bold">{f.title}</h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <Mono>{f.id}</Mono> <SeverityBadge value={f.severity} /> <ConfidenceBadge value={f.confidence} /> <FindingStatusBadge value={f.status} />
          <span className="text-xs text-slate-400">{fmtDate(f.created_at)}</span>
        </div>
      </div>
      <ErrorBox error={error} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="פרטי הממצא (סעיף 12)" className="lg:col-span-2">
          <dl className="grid gap-3 md:grid-cols-2">
            <div><dt className="text-xs text-slate-500">נכס ונתיב</dt><dd><Mono>{f.asset_path}</Mono></dd></div>
            <Row label="קטגוריה" value={f.category} />
            <Row label="תנאים מקדימים" value={f.preconditions} />
            <Row label="תוצאה צפויה" value={f.expected_result} />
            <Row label="תוצאה בפועל" value={f.actual_result} />
            <div className="md:col-span-2 rounded-lg bg-emerald-50 p-3"><dt className="text-xs font-medium text-emerald-800">השפעה שהוכחה</dt><dd className="text-sm">{f.proven_impact || '—'}</dd></div>
            <div className="md:col-span-2 rounded-lg bg-amber-50 p-3"><dt className="text-xs font-medium text-amber-800">השפעה משוערת (לא הוכחה)</dt><dd className="text-sm">{f.inferred_impact || '—'}</dd></div>
            <Row label="שחזור" value={f.reproduction} />
            <Row label="תיקון" value={f.remediation} />
            <Row label="מגבלות" value={f.limitations} />
          </dl>
        </Card>

        <Card title="מעקב">
          <div className="text-xs text-slate-500">סטטוס נוכחי</div>
          <div className="mb-3"><FindingStatusBadge value={f.status} /></div>
          {next.length === 0 ? <Empty>הממצא סגור.</Empty> : (
            <div className="space-y-2">
              <input className="input" placeholder="הערה (לא חובה)" value={note} onChange={e => setNote(e.target.value)} />
              {next.map(s => <button key={s} className="btn-secondary w-full justify-center" onClick={() => change(s)}>→ {t(findingStatus, s)}</button>)}
            </div>
          )}
        </Card>
      </div>

      <Card title="כרטיסי ראיה (מושחרים)">
        {d.evidence.length === 0 ? <Empty>אין ראיות מקושרות.</Empty> : (
          <div className="space-y-3">
            {d.evidence.map(e => (
              <div key={e.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <Mono>{e.id}</Mono> · {t(evidenceKind, e.kind)} · {fmtDate(e.captured_at)} · מדיניות השחרה {e.redaction_policy_version}
                  {e.redacted_fingerprint && <span>· טביעת HMAC <Mono>{e.redacted_fingerprint.slice(0, 12)}…</Mono></span>}
                </div>
                <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{e.redacted_source}</pre>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
