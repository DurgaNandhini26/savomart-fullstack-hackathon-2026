import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { CalendarDays, MapPinned, Navigation, PlusCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { FitBounds, MapView, Marker } from '../components/Map'
import { Empty, ErrorBox, PageLoader } from '../components/ui'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago } from '../lib/format'

const STATUS: Record<string, string> = { open: 'bg-sky-100 text-sky-800', in_progress: 'bg-amber-100 text-amber-800', done: 'bg-emerald-100 text-emerald-800', cancelled: 'bg-slate-200 text-slate-600' }

export default function Missions() {
  const { user } = useAuth()
  const exec = user?.role === 'bd_exec'
  const { data, isLoading, error } = useQuery({ queryKey: ['missions'], queryFn: () => get('/api/missions') })
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: () => get('/api/dashboard'), enabled: exec })
  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const open = (data || []).filter((m: any) => ['open', 'in_progress'].includes(m.status))

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="h-page">{exec ? `Hi ${user?.name.split(' ')[0]} 👋` : 'Scouting missions'}</h1>
          <p className="text-sm text-slate-500">{exec ? `${open.length} active mission${open.length === 1 ? '' : 's'}` : 'Where executives have been sent, and what they found'}</p>
        </div>
        {exec && <Link to="/properties/new" className="btn-primary"><PlusCircle className="h-4 w-4" /> Add property</Link>}
      </div>
      {exec && dash.data?.info_requested > 0 && (
        <Link to="/my-properties" className="block rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
          ⚠ {dash.data.info_requested} propert{dash.data.info_requested === 1 ? 'y needs' : 'ies need'} more information from you →
        </Link>
      )}
      {!data?.length && (
        <Empty icon={<MapPinned className="h-10 w-10" />} title="No missions yet">
          {exec ? 'Your manager will send you hotspots to scout. Found something on your own? Add it anyway.' : 'Open an area report and send an executive to a hotspot.'}
        </Empty>
      )}
      {open.length > 0 && (
        <div className="card h-56 overflow-hidden sm:h-72">
          <MapView className="h-full" basemap="streets">
            <FitBounds points={open.map((m: any) => [m.lng, m.lat])} maxZoom={13} />
            {open.map((m: any) => (
              <Marker key={m.id} lng={m.lng} lat={m.lat} popup={<Link to={`/missions/${m.id}`} className="font-semibold text-savo-700">{m.title}</Link>}>
                <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-savo-600 text-sun shadow"><MapPinned className="h-4 w-4" /></div>
              </Marker>
            ))}
          </MapView>
        </div>
      )}
      <div className="space-y-2">
        {data?.map((m: any) => (
          <Link key={m.id} to={`/missions/${m.id}`} className="card flex items-center gap-3 p-3 hover:border-savo-300">
            <div className={clsx('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl', m.status === 'done' ? 'bg-emerald-100 text-emerald-700' : 'bg-savo-100 text-savo-700')}><MapPinned className="h-5 w-5" /></div>
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold">{m.title}</div>
              <div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
                {!exec && <span>{m.assignee?.name}</span>}
                <span>{m.radius_m} m radius</span>
                {m.due_date && <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" />due {m.due_date}</span>}
                <span>{m.properties} propert{m.properties === 1 ? 'y' : 'ies'} found</span>
                <span>{ago(m.created_at)}</span>
              </div>
            </div>
            <span className={clsx('chip capitalize', STATUS[m.status])}>{m.status.replace('_', ' ')}</span>
            {exec && (
              <a href={`https://www.google.com/maps/dir/?api=1&destination=${m.lat},${m.lng}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="rounded-xl bg-sun p-2 text-savo-800" title="Navigate">
                <Navigation className="h-4 w-4" />
              </a>
            )}
          </Link>
        ))}
      </div>
    </div>
  )
}
