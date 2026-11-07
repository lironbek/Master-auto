import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowLeft, Bot, Boxes, Cloud, FolderKanban, Globe, Inbox, Link2, MessageCircle, Rocket, Search, Send, Sparkles, Wand2 } from 'lucide-react'
import { api, type CcProject, type Overview as OverviewData, type OverviewStats } from '../../api'
import { Card, Empty, ErrorBox, Spinner } from '../../components/ui'
import { BrandIcon, BrandTile, hasBrand } from '../../components/brand'
import { DayBars, Donut, Sparkline } from '../../components/charts'
import { EventRow, FirstWorkspace } from '../../components/cc'
import { alertKind, fmtDate, fmtRel, provider, qty, t } from '../../i18n'
import { useWorkspace } from '../../workspace'

const EMPTY_STATS: OverviewStats = {
  activity: [], this_week: { events: 0, deployments: 0, failures: 0 }, prev_week: { events: 0, deployments: 0, failures: 0 },
  usage_month: { messages: 0, recipients: 0, ai_requests: 0 }, usage_prev_month: { messages: 0, recipients: 0, ai_requests: 0 },
  usage_by_provider: {}, usage_daily: [], assets_by_provider: {},
}

function Delta({ now, before, invert = false, suffix = 'מהשבוע הקודם' }: { now: number; before: number; invert?: boolean; suffix?: string }) {
  if (!before && !now) return <span className="chip-flat">אין נתונים קודמים</span>
  if (!before) return <span className="chip-up">חדש</span>
  const pct = Math.round(((now - before) / before) * 100)
  const good = invert ? pct <= 0 : pct >= 0
  const cls = pct === 0 ? 'chip-flat' : good ? 'chip-up' : 'chip-down'
  return <span className={cls}>{pct > 0 ? '+' : ''}{pct}% <span className="font-normal opacity-70">{suffix}</span></span>
}

function StatTile({ label, value, icon, tint, tone, spark, delta, to }: { label: string; value: ReactNode; icon: ReactNode; tint: string; tone: 'teal' | 'violet' | 'amber' | 'sky'; spark: number[]; delta: ReactNode; to: string }) {
  return (
    <Link to={to} className="tile flex flex-col gap-3 transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-slate-700">{label}</div>
        <span className={`icon-tile ${tint}`}>{icon}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="text-3xl font-bold tracking-tight text-slate-900">{value}</div>
        <Sparkline values={spark} tone={tone} />
      </div>
      <div>{delta}</div>
    </Link>
  )
}

const providerMeta: Record<string, { icon: ReactNode; tint: string; label: string }> = {
  reporter: { icon: <Send className="h-4 w-4" />, tint: 'bg-indigo-500 text-white', label: 'דיווח חיצוני' },
  ocr: { icon: <Search className="h-4 w-4" />, tint: 'bg-violet-500 text-white', label: 'OCR' },
  sms: { icon: <MessageCircle className="h-4 w-4" />, tint: 'bg-sky-500 text-white', label: 'SMS' },
}
const brandLabel: Record<string, string> = { whatsapp: 'WhatsApp', telegram: 'Telegram', github: 'GitHub', vercel: 'Vercel', supabase: 'Supabase', n8n: 'n8n', claude: 'Claude', anthropic: 'Claude', gemini: 'Gemini', openai: 'OpenAI', email: 'Gmail', gmail: 'Gmail' }
function ProviderBadge({ name, count, size = 'md' }: { name: string; count?: number; size?: 'sm' | 'md' }) {
  const label = brandLabel[name] ?? providerMeta[name]?.label ?? t(provider, name)
  const generic = providerMeta[name] ?? { icon: <Cloud className="h-4 w-4" />, tint: 'bg-slate-400 text-white' }
  const tile = hasBrand(name)
    ? <BrandTile name={name} size={size === 'sm' ? 'sm' : 'md'} title={label} />
    : <span className={`grid shrink-0 place-items-center ${size === 'sm' ? 'h-6 w-6 rounded-md' : 'h-8 w-8 rounded-lg'} ${generic.tint}`} title={label}>{generic.icon}</span>
  if (size === 'sm') return tile
  return (
    <div className="flex items-center gap-2 rounded-xl bg-white/90 px-3 py-2 shadow-sm ring-1 ring-white">
      {tile}
      <div className="leading-tight"><div className="text-xs font-semibold text-slate-800">{label}</div>{count !== undefined && <div className="text-[11px] text-slate-500">{qty(count)} נכסים</div>}</div>
    </div>
  )
}

function ProjectCard({ p }: { p: CcProject }) {
  const tone = p.tone === 'bad' ? { chip: 'bg-rose-50 text-rose-700', text: 'כשל בייצור', tile: 'bg-rose-100 text-rose-600' }
    : p.tone === 'warn' ? { chip: 'bg-amber-50 text-amber-700', text: 'דורש בדיקה', tile: 'bg-amber-100 text-amber-700' }
    : { chip: 'bg-emerald-50 text-emerald-700', text: 'פעיל', tile: 'bg-teal-100 text-teal-700' }
  return (
    <Link to={`/projects/${p.id}`} className="tile flex items-start gap-3 transition hover:-translate-y-0.5 hover:shadow-md">
      <span className={`icon-tile ${tone.tile}`}><FolderKanban className="h-5 w-5" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="truncate text-sm font-bold text-slate-900">{p.name}</div>
          <span className={`chip whitespace-nowrap ${tone.chip}`}>{tone.text}</span>
        </div>
        <div className="truncate text-xs text-slate-500">{p.description || `${p.asset_count ?? 0} נכסים משויכים`}</div>
        <div className="mt-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">{(p.providers ?? []).map(x => <ProviderBadge key={x} name={x} size="sm" />)}</div>
          <span className="text-[11px] text-slate-400">{p.last_activity_at ? fmtRel(p.last_activity_at) : p.last_session ? `סשן: ${p.last_session.title}` : 'אין פעילות עדיין'}</span>
        </div>
      </div>
    </Link>
  )
}

export default function Overview() {
  const { workspaces, current, qs, loading } = useWorkspace()
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    if (loading || workspaces.length === 0) return
    let alive = true
    const load = () => api.get<OverviewData>(`/cc/overview${qs}`).then(d => { if (alive) { setData(d); setError(null) } }).catch(err => alive && setError(err))
    load()
    const id = setInterval(load, 30_000)
    return () => { alive = false; clearInterval(id) }
  }, [qs, loading, workspaces.length])

  if (loading) return <Spinner />
  if (workspaces.length === 0) return <FirstWorkspace />
  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Spinner />

  const st = data.stats ?? EMPTY_STATS
  const active = data.projects.filter(p => p.status === 'active')
  const ok = active.filter(p => p.tone === 'ok').length, warn = active.filter(p => p.tone === 'warn').length, bad = active.filter(p => p.tone === 'bad').length
  const stale = data.connections.filter(c => c.freshness?.stale && ['ok', 'partial', 'error'].includes(c.status))
  const live = data.connections.filter(c => ['ok', 'partial'].includes(c.status)).length
  const week = st.activity.slice(-7), prevWeek = st.activity.slice(0, 7)
  const spark = (f: (d: typeof week[number]) => number) => st.activity.map(f)
  const providers = Object.entries(st.assets_by_provider).sort((a, b) => b[1] - a[1])
  const usageProviders = Object.entries(st.usage_by_provider).sort((a, b) => b[1] - a[1]).slice(0, 4)
  const sortedProjects = [...active].sort((a, b) => String(b.last_activity_at ?? '').localeCompare(String(a.last_activity_at ?? '')))
  const agentsCount = data.assets_by_kind.bot ?? 0
  const workflows = (data.assets_by_kind.workflow ?? 0) + (data.assets_by_kind.service ?? 0)

  return (
    <div className="space-y-5">
      <ErrorBox error={error} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-4">
          <span className="grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-indigo-400 via-sky-400 to-teal-300 text-white shadow-lg"><Bot className="h-9 w-9" /></span>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">מרכז בקרה</h1>
            <p className="text-sm text-slate-500">{current ? current.name : 'כל המרחבים'} · כל הפרויקטים, האוטומציות והבוטים במקום אחד</p>
          </div>
        </div>
        <div className="chip bg-white/80 text-slate-600 ring-1 ring-white">מתעדכן כל 30 שניות · {fmtDate(new Date().toISOString())}</div>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <Link to="/projects" className="hero relative flex items-center justify-between gap-4 overflow-hidden lg:col-span-1 lg:order-last">
          <div className="absolute -left-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
          <div className="relative">
            <div className="text-5xl font-extrabold leading-none">{active.length}</div>
            <div className="mt-2 flex items-center gap-2"><span className="chip bg-white/25 text-white"><Sparkles className="h-3.5 w-3.5" /> פעילים</span></div>
            <div className="mt-2 text-sm font-semibold">פרויקטים ואוטומציות</div>
            <div className="mt-1 text-xs text-white/80">{ok} תקינים · {warn} לבדיקה · {bad} בכשל</div>
          </div>
          <Donut parts={[{ value: ok, color: '#ffffff', label: 'תקין' }, { value: warn, color: '#fde68a', label: 'דורש בדיקה' }, { value: bad, color: '#fda4af', label: 'כשל' }]} size={104} thickness={12}>
            <span className="text-sm font-bold">{active.length ? Math.round((ok / active.length) * 100) : 0}%</span>
          </Donut>
        </Link>
        <StatTile label="הודעות שנשלחו (30 יום)" value={qty(Math.round(st.usage_month.messages))} icon={<BrandIcon name="whatsapp" className="h-5 w-5" />} tint="bg-[#25D366] text-white" tone="teal"
          spark={st.usage_daily.map(d => d.messages)} delta={<Delta now={st.usage_month.messages} before={st.usage_prev_month.messages} suffix="מ-30 הימים הקודמים" />} to="/usage" />
        <StatTile label="קריאות AI (30 יום)" value={qty(Math.round(st.usage_month.ai_requests))} icon={<BrandIcon name="claude" className="h-5 w-5" />} tint="bg-[#D97757] text-white" tone="violet"
          spark={st.usage_daily.map(d => d.ai_requests)} delta={<Delta now={st.usage_month.ai_requests} before={st.usage_prev_month.ai_requests} suffix="מ-30 הימים הקודמים" />} to="/usage" />
        <StatTile label="פריסות השבוע" value={qty(st.this_week.deployments)} icon={<Rocket className="h-5 w-5" />} tint="bg-amber-100 text-amber-700" tone="amber"
          spark={spark(d => d.deployments)} delta={<Delta now={st.this_week.deployments} before={st.prev_week.deployments} />} to="/sessions" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={<span className="flex items-center gap-2"><Boxes className="h-4 w-4 text-indigo-500" /> מה קיים</span>} actions={<Link to="/assets" className="text-xs font-semibold text-indigo-600">הכול</Link>}>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'פרויקטים', value: active.length, icon: <FolderKanban className="h-5 w-5" />, tint: 'bg-teal-100 text-teal-700', to: '/projects' },
              { label: 'ריפוזיטוריז', value: data.assets_by_kind.repo ?? 0, icon: <BrandIcon name="github" className="h-5 w-5" />, tint: 'bg-slate-200 text-slate-800', to: '/assets' },
              { label: 'אינטגרציות', value: live, icon: <Link2 className="h-5 w-5" />, tint: 'bg-amber-100 text-amber-700', to: '/connections' },
              { label: 'בוטים ואוטומציות', value: agentsCount + workflows, icon: <Bot className="h-5 w-5" />, tint: 'bg-violet-100 text-violet-700', to: '/agents' },
            ].map(x => (
              <Link key={x.label} to={x.to} className="flex items-center gap-3 rounded-xl bg-slate-50/80 p-3 ring-1 ring-white transition hover:bg-white">
                <span className={`icon-tile ${x.tint}`}>{x.icon}</span>
                <div><div className="text-xs text-slate-500">{x.label}</div><div className="text-xl font-bold text-slate-900">{qty(x.value)}</div></div>
              </Link>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between rounded-xl bg-indigo-50/70 px-3 py-2 text-xs text-indigo-800">
            <span><Inbox className="mr-1 inline h-3.5 w-3.5" /> {data.inbox_open} ממתינים למיון · {data.unassigned} נכסים ללא פרויקט</span>
            <Link to="/inbox" className="font-semibold">למיון ←</Link>
          </div>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Activity className="h-4 w-4 text-teal-600" /> מה כל אחד עושה</span>}>
          <ol className="relative space-y-3 text-sm">
            {[
              { step: 'קבלה', title: 'מקבל מידע', detail: 'GitHub, Vercel, Supabase ודיווחי שימוש מהאפליקציות', icon: <Inbox className="h-4 w-4" />, tint: 'bg-sky-100 text-sky-700' },
              { step: 'עיבוד', title: 'מעבד ומבצע', detail: 'סיווג לפרויקטים, פרופיל ארכיטקטורה, סריקות בריאות וקוד', icon: <Wand2 className="h-4 w-4" />, tint: 'bg-violet-100 text-violet-700' },
              { step: 'שליחה', title: 'שולח תוצאה', detail: 'התראות, סיכומי סוכן, דוחות שימוש לפי לקוח', icon: <Send className="h-4 w-4" />, tint: 'bg-teal-100 text-teal-700' },
            ].map((s, i) => (
              <li key={s.step} className="flex items-center gap-3">
                <span className={`icon-tile ${s.tint}`}>{s.icon}</span>
                <div className="flex-1"><div className="font-semibold text-slate-800">{s.title}</div><div className="text-xs text-slate-500">{s.detail}</div></div>
                <span className={`chip ${i === 0 ? 'bg-sky-50 text-sky-700' : i === 1 ? 'bg-violet-50 text-violet-700' : 'bg-teal-50 text-teal-700'}`}>{s.step}</span>
              </li>
            ))}
          </ol>
          {usageProviders.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="mb-2 text-xs font-semibold text-slate-500">ערוצים ב-30 הימים האחרונים</div>
              <div className="flex flex-wrap gap-2">{usageProviders.map(([k, v]) => <span key={k} className="chip bg-slate-50 text-slate-700 ring-1 ring-slate-100"><ProviderBadge name={k} size="sm" /> {qty(Math.round(v))}</span>)}</div>
            </div>
          )}
        </Card>

        <Card title={<span className="flex items-center gap-2"><Globe className="h-4 w-4 text-sky-600" /> איפה הוא חי</span>} actions={<Link to="/connections" className="text-xs font-semibold text-indigo-600">אינטגרציות</Link>}>
          <div className="relative min-h-[150px] overflow-hidden rounded-xl bg-gradient-to-br from-sky-50 via-teal-50 to-indigo-50 p-3">
            <div className="absolute -right-6 -top-6 h-28 w-28 rounded-full bg-teal-200/40" />
            <div className="absolute -bottom-8 left-4 h-24 w-24 rounded-full bg-indigo-200/40" />
            <div className="absolute right-1/3 top-1/2 h-16 w-16 rounded-full bg-sky-200/40" />
            {providers.length === 0 ? <Empty>חבר GitHub, Vercel או Supabase כדי לראות איפה הפרויקטים רצים.</Empty> : (
              <div className="relative flex flex-wrap gap-2">{providers.map(([k, v]) => <ProviderBadge key={k} name={k} count={v} />)}</div>
            )}
          </div>
          {stale.length > 0 && <div className="mt-2 flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800"><AlertTriangle className="h-3.5 w-3.5" /> {stale.map(c => t(provider, c.provider)).join(', ')}: הפיד לא עדכני מעל 45 דקות</div>}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="space-y-3 lg:col-span-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-800">הפרויקטים והאוטומציות שלך</h2>
            <Link to="/projects" className="flex items-center gap-1 text-xs font-semibold text-indigo-600">הצג הכל <ArrowLeft className="h-3.5 w-3.5" /></Link>
          </div>
          {sortedProjects.length === 0 ? <Empty>אין פרויקטים. צור פרויקט או שייך נכסים מתיבת המיון.</Empty> : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{sortedProjects.slice(0, 9).map(p => <ProjectCard key={p.id} p={p} />)}</div>
          )}
        </div>
        <Card title="פעילות בשבועיים האחרונים" className="self-start">
          <div className="mb-3 flex items-end justify-between">
            <div><div className="text-2xl font-bold text-slate-900">{qty(st.this_week.events)}</div><div className="text-xs text-slate-500">אירועים השבוע</div></div>
            <Delta now={st.this_week.events} before={st.prev_week.events} suffix="" />
          </div>
          {st.activity.length ? <DayBars days={st.activity} /> : <Empty>אין אירועים עדיין.</Empty>}
          <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-rose-400" /> {st.this_week.failures} כשלים השבוע</span>
            <span>{prevWeek.reduce((a, d) => a + d.total, 0)} בשבוע הקודם</span>
          </div>
        </Card>
      </div>

      {(data.critical_alerts.length > 0 || data.open_sessions.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.critical_alerts.length > 0 && (
            <Card title={<span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-rose-500" /> דורש תשומת לב</span>} actions={<Link to="/alerts" className="text-xs font-semibold text-indigo-600">התראות</Link>}>
              <ul className="space-y-2 text-sm">
                {data.critical_alerts.slice(0, 6).map(a => (
                  <li key={a.id} className="rounded-xl bg-rose-50/80 px-3 py-2">
                    <div className="text-xs font-semibold text-rose-800">{t(alertKind, a.kind)}</div>
                    <div className="text-slate-700">{a.message}</div>
                    <div className="text-xs text-slate-400">{fmtRel(a.created_at)}</div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {data.open_sessions.length > 0 && (
            <Card title="סשנים פתוחים" actions={<Link to="/sessions" className="text-xs font-semibold text-indigo-600">הכול</Link>}>
              <ul className="divide-y divide-slate-100 text-sm">
                {data.open_sessions.map(s => <li key={s.id} className="flex items-center justify-between py-2"><Link to={`/sessions/${s.id}`} className="font-medium text-indigo-700">{s.title}</Link><span className="text-xs text-slate-500">{fmtRel(s.last_activity_at || s.started_at)}</span></li>)}
              </ul>
            </Card>
          )}
        </div>
      )}

      <Card title="פעילות אחרונה">
        {data.recent_events.length === 0 ? <Empty>אין אירועים עדיין. אחרי סנכרון ראשון יופיעו כאן פריסות, ריצות ו-PRs.</Empty> : <ul className="divide-y divide-slate-100">{data.recent_events.slice(0, 10).map(e => <EventRow key={e.id} e={e} showProject />)}</ul>}
      </Card>
    </div>
  )
}
