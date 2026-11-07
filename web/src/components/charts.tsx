// Small inline SVG charts for the dashboard: sparkline, donut, daily bars.
// Single series each, so no legend; values are announced in <title> tooltips.
import { useId } from 'react'

type Tone = 'teal' | 'violet' | 'amber' | 'rose' | 'sky'
const stroke: Record<Tone, string> = { teal: '#0d9488', violet: '#7c3aed', amber: '#d97706', rose: '#e11d48', sky: '#0284c7' }

export function Sparkline({ values, tone = 'teal', height = 36, width = 120 }: { values: number[]; tone?: Tone; height?: number; width?: number }) {
  const id = useId()
  const n = values.length
  if (n < 2) return <svg width={width} height={height} aria-hidden="true" />
  const max = Math.max(1, ...values)
  const step = width / (n - 1)
  const pts = values.map((v, i) => [i * step, height - 3 - (v / max) * (height - 6)] as const)
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${width},${height} L0,${height} Z`
  const last = pts[n - 1]
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible" role="img" aria-label={`מגמה: ${values.join(', ')}`}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={stroke[tone]} stopOpacity="0.28" />
          <stop offset="1" stopColor={stroke[tone]} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke[tone]} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="3.5" fill="#fff" stroke={stroke[tone]} strokeWidth="2" />
    </svg>
  )
}

/** Share of a whole. Segments carry a label (status colours are never colour-alone). */
export function Donut({ parts, size = 112, thickness = 14, children }: { parts: { value: number; color: string; label: string }[]; size?: number; thickness?: number; children?: React.ReactNode }) {
  const total = parts.reduce((a, p) => a + p.value, 0)
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={thickness} />
        {total > 0 && parts.filter(p => p.value > 0).map((p, i) => {
          const len = (p.value / total) * c
          const el = (
            <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={p.color} strokeWidth={thickness}
              strokeDasharray={`${Math.max(0, len - 2)} ${c - Math.max(0, len - 2) + 2}`} strokeDashoffset={-offset} strokeLinecap="butt">
              <title>{`${p.label}: ${p.value}`}</title>
            </circle>
          )
          offset += len
          return el
        })}
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  )
}

/** Daily activity bars for the last N days; failures drawn as a darker cap. */
export function DayBars({ days, height = 96 }: { days: { date: string; total: number; failures: number }[]; height?: number }) {
  const max = Math.max(1, ...days.map(d => d.total))
  const labels = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳']
  return (
    <div className="flex items-end gap-1.5" style={{ height }} role="img" aria-label="אירועים ליום בשבועיים האחרונים">
      {days.map(d => {
        const h = Math.max(4, Math.round((d.total / max) * (height - 22)))
        const f = d.total ? Math.round((d.failures / d.total) * h) : 0
        const dt = new Date(d.date + 'T00:00:00')
        return (
          <div key={d.date} className="group flex flex-1 flex-col items-center justify-end gap-1" title={`${dt.toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric' })}: ${d.total} אירועים, ${d.failures} כשלים`}>
            <div className="w-full overflow-hidden rounded-md bg-teal-200/80 transition group-hover:bg-teal-300" style={{ height: h }}>
              {f > 0 && <div className="w-full bg-rose-400" style={{ height: f }} />}
            </div>
            <span className="text-[10px] text-slate-400">{labels[dt.getDay()]}</span>
          </div>
        )
      })}
    </div>
  )
}
