import { useQuery } from '@tanstack/react-query'
import { Recycle, Route } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Empty, ErrorBox, PageLoader, Stat, StudyBadge } from '../components/ui'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago, fmt1, pct } from '../lib/format'

const PRIORITY: Record<string, string> = { high: 'bg-rose-100 text-rose-700', normal: 'bg-slate-100 text-slate-600', low: 'bg-slate-50 text-slate-400' }

export default function Studies() {
  const { user } = useAuth()
  const sm = user?.role === 'survey_manager'
  const { data, isLoading, error } = useQuery({ queryKey: ['studies'], queryFn: () => get('/api/studies'), refetchInterval: 10000 })
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: () => get('/api/dashboard'), enabled: sm })
  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const groups: [string, (s: any) => boolean][] = [
    ['Incoming requests — need planning', (s) => s.status === 'requested'],
    ['In the field', (s) => ['planned', 'in_progress'].includes(s.status)],
    ['Completed & reused', (s) => ['completed', 'reused'].includes(s.status)],
  ]

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="h-page">Catchment studies</h1>
        <p className="text-sm text-slate-500">{sm ? 'Split each request into fair work units, assign your team and track progress lane by lane.' : 'Ground-truth surveys requested for properties and areas.'}</p>
      </div>
      {sm && dash.data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="New requests" value={dash.data.new_requests} />
          <Stat label="In the field" value={dash.data.in_progress} />
          <Stat label="Unassigned units" value={dash.data.unassigned_units} />
          <Stat label="Completed" value={dash.data.completed} />
        </div>
      )}
      {!data?.length && <Empty icon={<Route className="h-10 w-10" />} title="No catchment studies yet">BD managers request studies from a property or an area report.</Empty>}
      {groups.map(([title, fn]) => {
        const rows = (data || []).filter(fn)
        if (!rows.length) return null
        return (
          <section key={title}>
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">{title} ({rows.length})</h2>
            <div className="space-y-2">
              {rows.map((s: any) => (
                <Link key={s.id} to={`/studies/${s.id}`} className="card flex flex-wrap items-center gap-3 p-3 hover:border-savo-300">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-savo-100 font-extrabold text-savo-700">{s.code.split('-')[1]}</div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{s.title}</div>
                    <div className="text-xs text-slate-500">
                      {s.code} · {s.target_type === 'property' ? `${s.radius_m} m around property` : 'analysed area'} · {s.n_cells} cells to survey
                      {s.reused.length > 0 && <> · <Recycle className="inline h-3 w-3 text-teal-600" /> reuses {s.reused.map((r: any) => r.code).join(', ')}</>}
                      {' '}· by {s.requested_by?.name} {ago(s.created_at)}{s.due_date && ` · due ${s.due_date}`}
                    </div>
                  </div>
                  {s.units > 0 && (
                    <div className="w-32">
                      <div className="flex justify-between text-xs text-slate-500"><span>{s.units} units</span><span>{pct(s.progress)}</span></div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-savo-600" style={{ width: `${s.progress * 100}%` }} /></div>
                      <div className="text-[10px] text-slate-400">{fmt1(s.lane_km)} lane-km</div>
                    </div>
                  )}
                  <span className={`chip capitalize ${PRIORITY[s.priority]}`}>{s.priority}</span>
                  <StudyBadge status={s.status} />
                </Link>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
