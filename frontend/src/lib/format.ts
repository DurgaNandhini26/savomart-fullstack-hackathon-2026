export const fmtInt = (n?: number | null) => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'))
export const fmt1 = (n?: number | null) => (n == null ? '—' : (Math.round(n * 10) / 10).toLocaleString('en-IN'))
export const fmtINR = (n?: number | null) =>
  n == null ? '—' : '₹' + Math.round(n).toLocaleString('en-IN')
export const pct = (n?: number | null) => (n == null ? '—' : `${Math.round(n * 100)}%`)

export function ago(iso?: string | null) {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`
  return new Date(iso).toLocaleDateString('en-IN')
}

export const dateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export function scoreColor(s?: number | null) {
  if (s == null) return '#94a3b8'
  if (s >= 70) return '#16a34a'
  if (s >= 55) return '#782B90'
  if (s >= 40) return '#d97706'
  return '#dc2626'
}

// sequential purple ramp for choropleths (light -> brand purple)
export const RAMP = ['#f3e8f7', '#dcc0e6', '#bf8dd0', '#a060b7', '#782B90', '#4d1c60']
export function rampColor(v: number, min = 30, max = 90) {
  const t = Math.max(0, Math.min(0.9999, (v - min) / (max - min)))
  return RAMP[Math.floor(t * RAMP.length)]
}

export const REC_LABEL: Record<string, string> = { go: 'Go', consider: 'Consider', no_go: 'No-go' }
export const REC_STYLE: Record<string, string> = {
  go: 'bg-emerald-100 text-emerald-800',
  consider: 'bg-amber-100 text-amber-800',
  no_go: 'bg-rose-100 text-rose-800',
}

export const STAGE_STYLE: Record<string, string> = {
  submitted: 'bg-sky-100 text-sky-800',
  info_requested: 'bg-amber-100 text-amber-800',
  shortlisted: 'bg-savo-100 text-savo-800',
  site_visit: 'bg-indigo-100 text-indigo-800',
  catchment_study: 'bg-fuchsia-100 text-fuchsia-800',
  negotiation: 'bg-orange-100 text-orange-800',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-rose-100 text-rose-800',
  on_hold: 'bg-slate-200 text-slate-700',
  duplicate: 'bg-slate-200 text-slate-700',
}

export const STAGE_LABEL: Record<string, string> = {
  submitted: 'New',
  info_requested: 'Info requested',
  shortlisted: 'Shortlisted',
  site_visit: 'Site visit',
  catchment_study: 'Catchment study',
  negotiation: 'Negotiation',
  approved: 'Approved',
  rejected: 'Rejected',
  on_hold: 'On hold',
  duplicate: 'Duplicate',
}

export const STUDY_STATUS: Record<string, string> = {
  requested: 'bg-sky-100 text-sky-800',
  planned: 'bg-indigo-100 text-indigo-800',
  in_progress: 'bg-amber-100 text-amber-800',
  completed: 'bg-emerald-100 text-emerald-800',
  reused: 'bg-teal-100 text-teal-800',
  cancelled: 'bg-slate-200 text-slate-700',
}

export const uuid = () =>
  (crypto as any).randomUUID?.() ??
  'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
