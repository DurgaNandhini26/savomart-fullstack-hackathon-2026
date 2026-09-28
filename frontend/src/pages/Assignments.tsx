import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ClipboardList } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Empty, ErrorBox, PageLoader } from '../components/ui'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmt1 } from '../lib/format'
import { useOutbox } from '../lib/offline'

export default function Assignments() {
  const { user } = useAuth()
  const outbox = useOutbox()
  const { data, isLoading, error } = useQuery({ queryKey: ['my-assignments'], queryFn: () => get('/api/my/assignments'), refetchInterval: 20000 })
  if (isLoading && !data) return <PageLoader />
  const active = (data || []).filter((u: any) => u.status !== 'done')
  const done = (data || []).filter((u: any) => u.status === 'done')

  const Row = ({ u }: { u: any }) => {
    const queued = outbox.filter((o) => o.kind === 'observation' && o.payload.work_unit_id === u.id).length
    const pctDone = u.lane_count ? (u.lanes_done + queued) / u.lane_count : 0
    return (
      <Link to={`/survey/${u.id}`} className="card flex items-center gap-3 p-4">
        <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl" style={{ background: `${u.color}22` }}>
          <span className="text-lg font-extrabold" style={{ color: u.color }}>{Math.round(pctDone * 100)}%</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-bold">{u.study.code} · {u.name}</div>
          <div className="truncate text-sm text-slate-500">{u.study.title}</div>
          <div className="text-xs text-slate-500">{u.lanes_done + queued}/{u.lane_count} lanes · {fmt1(u.lane_km)} km{u.due_date && ` · due ${u.due_date}`}{queued > 0 && ` · ${queued} waiting to sync`}</div>
        </div>
        {u.study.priority === 'high' && <span className="chip bg-rose-100 text-rose-700">High</span>}
        <ChevronRight className="h-5 w-5 text-slate-400" />
      </Link>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="h-page">Vanakkam, {user?.name.split(' ')[0]}</h1>
        <p className="text-sm text-slate-500">Your survey assignments. Work keeps saving on your phone even without signal.</p>
      </div>
      {error && !data && <ErrorBox error={error} />}
      {!data?.length && !error && <Empty icon={<ClipboardList className="h-10 w-10" />} title="No assignments yet">Your survey manager will assign you a sector of lanes to survey.</Empty>}
      {active.length > 0 && <div className="space-y-2">{active.map((u: any) => <Row key={u.id} u={u} />)}</div>}
      {done.length > 0 && (
        <>
          <h2 className="pt-2 text-sm font-bold uppercase text-slate-500">Completed</h2>
          <div className="space-y-2 opacity-70">{done.map((u: any) => <Row key={u.id} u={u} />)}</div>
        </>
      )}
    </div>
  )
}
