import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Bot, FileBarChart2, KanbanSquare, Map, MapPinned, Route } from 'lucide-react'
import { Link } from 'react-router-dom'
import { RecBadge, Stat, StageBadge } from '../components/ui'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago, fmtINR, scoreColor } from '../lib/format'

export default function ManagerHome() {
  const { user } = useAuth()
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: () => get('/api/dashboard') })
  const props = useQuery({ queryKey: ['properties', 'review'], queryFn: () => get('/api/properties?stage=submitted,info_requested') })
  const reports = useQuery({ queryKey: ['reports'], queryFn: () => get('/api/reports') })
  const top = useQuery({ queryKey: ['opportunity-top'], queryFn: () => get('/api/geo/opportunity/top?limit=8') })
  const d = dash.data || {}

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <div className="rounded-3xl bg-gradient-to-r from-savo-700 to-savo-600 p-5 text-white sm:p-6">
        <div className="text-sm text-savo-100">Good day, {user?.name.split(' ')[0]}</div>
        <h1 className="mt-1 text-2xl font-extrabold sm:text-3xl">Where should Chennai's next <span className="text-sun">Savomart</span> open?</h1>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/explore" className="btn-sun"><Map className="h-4 w-4" /> Explore an area</Link>
          <Link to="/pipeline" className="btn bg-white/15 text-white hover:bg-white/25"><KanbanSquare className="h-4 w-4" /> Review pipeline</Link>
          <Link to="/assistant" className="btn bg-white/15 text-white hover:bg-white/25"><Bot className="h-4 w-4" /> Ask the analyst</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Awaiting your review" value={d.awaiting_review ?? '—'} icon={<KanbanSquare className="h-3.5 w-3.5" />} sub="new properties" />
        <Stat label="Area reports" value={d.reports ?? '—'} icon={<FileBarChart2 className="h-3.5 w-3.5" />} sub={d.reports_running ? `${d.reports_running} running` : 'saved'} />
        <Stat label="Open missions" value={d.open_missions ?? '—'} icon={<MapPinned className="h-3.5 w-3.5" />} sub="executives scouting" />
        <Stat label="Active studies" value={d.studies_active ?? '—'} icon={<Route className="h-3.5 w-3.5" />} sub="catchment surveys" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">Needs a decision</h2>
            <Link to="/pipeline" className="text-sm font-semibold text-savo-700">Pipeline <ArrowRight className="inline h-4 w-4" /></Link>
          </div>
          {!props.data?.length && <div className="text-sm text-slate-500">Nothing waiting. 🎉</div>}
          <div className="divide-y divide-slate-100">
            {props.data?.slice(0, 6).map((p: any) => (
              <Link key={p.id} to={`/properties/${p.id}`} className="flex items-center gap-3 py-2.5 hover:bg-slate-50">
                {p.photo ? <img src={p.photo} className="h-12 w-12 rounded-xl object-cover" /> : <div className="h-12 w-12 rounded-xl bg-savo-100" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{p.title}</div>
                  <div className="text-xs text-slate-500">{p.code} · {p.locality} · {fmtINR(p.rent_monthly)}/mo · {p.submitted_by?.name} · {ago(p.created_at)}</div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="text-lg font-extrabold" style={{ color: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</span>
                  <div className="flex gap-1"><StageBadge stage={p.stage} /><RecBadge rec={p.recommendation} /></div>
                </div>
              </Link>
            ))}
          </div>
        </section>
        <section className="card p-4">
          <h2 className="mb-1 font-bold">Un-scouted opportunities</h2>
          <p className="mb-3 text-xs text-slate-500">Highest-scoring neighbourhoods with no report or property yet.</p>
          <div className="space-y-1">
            {top.data?.map((t: any) => (
              <Link key={t.h3} to="/explore" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-savo-50">
                <span className="w-9 rounded-md py-0.5 text-center text-xs font-bold text-white" style={{ background: scoreColor(t.score) }}>{Math.round(t.score)}</span>
                <span className="flex-1 truncate">{t.locality}</span>
                <span className="text-xs text-slate-400">{Math.round(t.population / 1000)}k</span>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <section className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">Recent area reports</h2>
          <Link to="/reports" className="text-sm font-semibold text-savo-700">All reports <ArrowRight className="inline h-4 w-4" /></Link>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {reports.data?.slice(0, 4).map((r: any) => (
            <Link key={r.id} to={`/reports/${r.id}`} className="rounded-2xl border border-slate-200 p-3 hover:border-savo-300">
              <div className="flex items-center justify-between">
                <span className="truncate font-semibold">{r.name}</span>
                <span className="font-extrabold" style={{ color: scoreColor(r.score) }}>{r.score ? Math.round(r.score) : '…'}</span>
              </div>
              <div className="text-xs text-slate-500">{r.band || r.status} · {ago(r.created_at)}</div>
            </Link>
          ))}
          {!reports.data?.length && <div className="text-sm text-slate-500">No reports yet.</div>}
        </div>
      </section>
    </div>
  )
}
