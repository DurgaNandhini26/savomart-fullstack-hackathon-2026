import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Circle, Loader2, ShieldCheck, Sparkles, X, XCircle } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { REC_LABEL, REC_STYLE, STAGE_LABEL, STAGE_STYLE, STUDY_STATUS, dateTime, scoreColor } from '../lib/format'

export function Spinner({ className = '' }: { className?: string }) {
  return <Loader2 className={clsx('animate-spin text-savo-600', className || 'h-5 w-5')} />
}

export function PageLoader({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-sm text-slate-500">
      <Spinner className="h-7 w-7" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = (error as Error)?.message || String(error)
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">{msg}</div>
      {onRetry && (
        <button className="font-semibold underline" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8 text-center">
      {icon && <div className="text-savo-400">{icon}</div>}
      <div className="font-semibold text-slate-700">{title}</div>
      {children && <div className="max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function ScoreRing({ score, size = 84, label }: { score?: number | null; size?: number; label?: string }) {
  const r = size / 2 - 7
  const c = 2 * Math.PI * r
  const v = Math.max(0, Math.min(100, score ?? 0))
  const color = scoreColor(score)
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#ede9f0" strokeWidth={7} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={7} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} style={{ transition: 'stroke-dashoffset .8s' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-extrabold leading-none" style={{ fontSize: size * 0.3, color }}>{score == null ? '—' : Math.round(score)}</div>
        {label && <div className="mt-0.5 text-[10px] font-semibold uppercase text-slate-400">{label}</div>}
      </div>
    </div>
  )
}

export function Bar({ value, color = '#782B90' }: { value: number; color?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: color }} />
    </div>
  )
}

export function PillarBars({ pillars }: { pillars: Record<string, { label: string; score: number; weight: number; description?: string; contribution?: number }> }) {
  return (
    <div className="space-y-3">
      {Object.entries(pillars).map(([k, p]) => (
        <div key={k} title={p.description}>
          <div className="mb-1 flex items-baseline justify-between text-sm">
            <span className="font-medium text-slate-700">
              {p.label} <span className="text-xs font-normal text-slate-400">× {Math.round(p.weight * 100)}%</span>
            </span>
            <span className="font-bold tabular-nums" style={{ color: scoreColor(p.score) }}>{Math.round(p.score)}</span>
          </div>
          <Bar value={p.score} color={scoreColor(p.score)} />
          {p.description && <div className="mt-0.5 text-xs text-slate-400">{p.description}</div>}
        </div>
      ))}
    </div>
  )
}

export const StageBadge = ({ stage }: { stage: string }) => (
  <span className={clsx('chip', STAGE_STYLE[stage] || 'bg-slate-100')}>{STAGE_LABEL[stage] || stage}</span>
)

export const RecBadge = ({ rec }: { rec?: string | null }) =>
  rec ? <span className={clsx('chip', REC_STYLE[rec])}>{REC_LABEL[rec]}</span> : <span className="chip bg-slate-100 text-slate-500">Evaluating…</span>

export const StudyBadge = ({ status }: { status: string }) => (
  <span className={clsx('chip capitalize', STUDY_STATUS[status] || 'bg-slate-100')}>{status.replace('_', ' ')}</span>
)

export function BandBadge({ band, score }: { band?: string | null; score?: number | null }) {
  if (!band) return null
  return (
    <span className="chip text-white" style={{ background: scoreColor(score) }}>
      {band}
    </span>
  )
}

/** Live checklist of a background job's steps. */
export function JobSteps({ job }: { job: any }) {
  if (!job) return null
  return (
    <div className="space-y-2">
      <div className="h-1.5 overflow-hidden rounded-full bg-savo-100">
        <div className="relative h-full bg-savo-600 transition-all duration-500" style={{ width: `${Math.max(4, job.progress * 100)}%` }}>
          {job.status === 'running' && <div className="shimmer absolute inset-0" />}
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {(job.steps || []).map((s: any) => (
          <li key={s.key} className="flex items-start gap-2">
            {s.status === 'done' && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />}
            {s.status === 'warning' && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />}
            {s.status === 'failed' && <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />}
            {s.status === 'running' && <Spinner className="mt-0.5 h-4 w-4 shrink-0" />}
            {s.status === 'pending' && <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />}
            <div>
              <span className={clsx(s.status === 'pending' && 'text-slate-400')}>{s.label}</span>
              {s.detail && <div className="text-xs text-slate-500">{s.detail}</div>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Shows how a narrative was produced and whether its numbers were verified. */
export function AIBadge({ meta }: { meta?: any }) {
  if (!meta) return null
  if (meta.mode === 'ai')
    return (
      <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" title={`${meta.provider} · ${meta.model}`}>
        <ShieldCheck className="h-3.5 w-3.5" /> AI-written · {meta.grounding?.numbers_cited ?? 0} figures verified against data
      </span>
    )
  return (
    <span className="chip bg-slate-100 text-slate-600" title={meta.reason}>
      <Sparkles className="h-3.5 w-3.5" /> Template narrative{meta.reason ? ` · ${meta.reason}` : ''}
    </span>
  )
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 backdrop-blur-[2px] sm:items-center" onClick={onClose}>
      <div className={clsx('max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-2xl sm:rounded-2xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">{title}</h3>
          <button onClick={onClose} className="rounded-full p-1 hover:bg-slate-100" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Stat({ label, value, sub, icon }: { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 truncate text-2xl font-extrabold text-slate-900 tabular-nums">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

export function DataVersions({ versions, created }: { versions?: Record<string, any>; created?: string }) {
  if (!versions) return null
  const rows = Object.entries(versions).filter(([k]) => k !== 'model')
  const label: Record<string, string> = {
    osm_pois: 'OSM points of interest', osm_roads: 'OSM road network', osm_places: 'OSM localities', osm_buildings: 'OSM buildings',
    stores: 'Savomart stores', pincodes: 'Pincode centroids', baseline: 'City baseline',
  }
  return (
    <div className="overflow-x-auto text-xs text-slate-500">
      <div className="mb-1 font-semibold text-slate-600">Data used {created && <>· report generated {dateTime(created)}</>}</div>
      <table className="w-full min-w-[520px]">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-t border-slate-100">
              <td className="py-1 pr-2">{label[k] || k}</td>
              <td className="py-1 pr-2 tabular-nums">{v.records?.toLocaleString('en-IN')} rows</td>
              <td className="py-1">
                {v.source_timestamp ? `OSM as of ${dateTime(v.source_timestamp)}` : `fetched ${dateTime(v.fetched_at)}`}
                {v.notes && <span className="text-slate-400"> · {v.notes}</span>}
              </td>
            </tr>
          ))}
          {versions.model && (
            <tr className="border-t border-slate-100">
              <td className="py-1 pr-2">Scoring model</td>
              <td className="py-1 pr-2">{versions.model.version}</td>
              <td className="py-1">Population calibrated to {versions.model.calibration_population?.toLocaleString('en-IN')} (Census 2011)</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export function Section({ title, children, right, className }: { title: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={clsx('card p-4 sm:p-5', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-bold text-slate-900">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

export function MockTag() {
  return <span className="chip bg-amber-100 text-[10px] uppercase text-amber-800" title="No open data exists for this; values are mock placeholders">Mock data</span>
}
