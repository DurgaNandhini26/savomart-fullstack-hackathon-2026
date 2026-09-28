import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Navigation, PlusCircle } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { GeoLayer, MapView, Marker, StoreMarker } from '../components/Map'
import { ErrorBox, PageLoader, RecBadge, Section, StageBadge } from '../components/ui'
import { get, patch } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtINR, scoreColor } from '../lib/format'

function circle(lng: number, lat: number, r: number) {
  const pts = Array.from({ length: 65 }, (_, i) => {
    const a = (i / 64) * 2 * Math.PI
    return [lng + ((r / 111320) * Math.cos(a)) / Math.cos((lat * Math.PI) / 180), lat + (r / 110540) * Math.sin(a)]
  })
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [pts] } } as any
}

export default function MissionDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: m, isLoading, error, refetch } = useQuery({ queryKey: ['mission', id], queryFn: () => get(`/api/missions/${id}`) })
  const stores = useQuery({ queryKey: ['stores'], queryFn: () => get('/api/geo/stores') })
  const upd = useMutation({ mutationFn: (status: string) => patch(`/api/missions/${id}`, { status }), onSuccess: () => refetch() })
  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const exec = user?.role === 'bd_exec'

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <Link to="/missions" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-700"><ArrowLeft className="h-4 w-4" /> Missions</Link>
      <div>
        <h1 className="h-page">{m.title}</h1>
        <div className="text-sm text-slate-500">Assigned to {m.assignee?.name} by {m.created_by?.name}{m.due_date && ` · due ${m.due_date}`} · <span className="capitalize">{m.status.replace('_', ' ')}</span></div>
      </div>
      <div className="card h-72 overflow-hidden">
        <MapView className="h-full" center={[m.lng, m.lat]} zoom={14.5} basemap="streets">
          <GeoLayer id="zone" data={circle(m.lng, m.lat, m.radius_m)} layers={[{ type: 'fill', paint: { 'fill-color': '#FFF200', 'fill-opacity': 0.25 } } as any, { type: 'line', paint: { 'line-color': '#782B90', 'line-width': 2, 'line-dasharray': [2, 1] } } as any]} />
          {stores.data?.map((s: any) => <Marker key={s.code} lng={s.lng} lat={s.lat}><StoreMarker name={s.name} /></Marker>)}
          {m.properties.map((p: any) => (
            <Marker key={p.id} lng={p.lng} lat={p.lat} popup={<Link to={`/properties/${p.id}`} className="font-semibold text-savo-700">{p.title}</Link>}>
              <div className="rounded-full border-2 border-white px-1.5 text-xs font-bold text-white shadow" style={{ background: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</div>
            </Marker>
          ))}
        </MapView>
      </div>
      {exec && m.status !== 'done' && (
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <a className="btn-sun" href={`https://www.google.com/maps/dir/?api=1&destination=${m.lat},${m.lng}`} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" /> Navigate</a>
          <Link className="btn-primary" to={`/properties/new?mission=${m.id}`}><PlusCircle className="h-4 w-4" /> Add property here</Link>
          <button className="btn-ghost col-span-2" onClick={() => upd.mutate('done')}><CheckCircle2 className="h-4 w-4" /> Mark mission complete</button>
        </div>
      )}
      {m.brief && <Section title="Brief"><p className="whitespace-pre-line text-sm text-slate-700">{m.brief}</p></Section>}
      {m.hotspot && (
        <Section title={`Why this hotspot (#${m.hotspot.rank} in ${m.report_name})`}>
          <ul className="space-y-1 text-sm">{m.hotspot.reasons.map((r: string) => <li key={r}>• {r}</li>)}</ul>
          {!exec && <Link to={`/reports/${m.report_id}`} className="mt-2 inline-block text-sm font-semibold text-savo-700">Open area report →</Link>}
        </Section>
      )}
      <Section title={`Properties found (${m.properties.length})`}>
        {!m.properties.length && <div className="text-sm text-slate-500">Nothing onboarded yet.</div>}
        <div className="divide-y divide-slate-100">
          {m.properties.map((p: any) => (
            <Link key={p.id} to={`/properties/${p.id}`} className="flex items-center gap-3 py-2">
              {p.photo ? <img src={p.photo} className="h-10 w-10 rounded-lg object-cover" /> : <div className="h-10 w-10 rounded-lg bg-slate-100" />}
              <div className="min-w-0 flex-1"><div className="truncate font-semibold">{p.title}</div><div className="text-xs text-slate-500">{p.code} · {fmtINR(p.rent_monthly)}/mo</div></div>
              <StageBadge stage={p.stage} /><RecBadge rec={p.recommendation} />
            </Link>
          ))}
        </div>
      </Section>
    </div>
  )
}
