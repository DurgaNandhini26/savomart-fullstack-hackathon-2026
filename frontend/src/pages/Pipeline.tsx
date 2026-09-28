import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ImageOff, LayoutList, Map as MapIcon, Columns3 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FitBounds, MapView, Marker } from '../components/Map'
import { Empty, ErrorBox, PageLoader, RecBadge, StageBadge } from '../components/ui'
import { get } from '../lib/api'
import { ago, fmtINR, fmtInt, scoreColor, STAGE_LABEL } from '../lib/format'

const COLUMNS = ['submitted', 'info_requested', 'shortlisted', 'site_visit', 'catchment_study', 'negotiation', 'approved']
const CLOSED = ['rejected', 'on_hold', 'duplicate']

function Card({ p }: { p: any }) {
  return (
    <Link to={`/properties/${p.id}`} className="block rounded-2xl border border-slate-200 bg-white p-2.5 shadow-sm transition hover:border-savo-300 hover:shadow">
      <div className="flex gap-2.5">
        {p.photo ? <img src={p.photo} className="h-14 w-14 shrink-0 rounded-xl object-cover" /> :
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-slate-100"><ImageOff className="h-5 w-5 text-slate-300" /></div>}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1">
            <div className="line-clamp-2 text-sm font-semibold leading-tight">{p.title}</div>
            <div className="text-lg font-extrabold leading-none" style={{ color: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</div>
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">{p.code} · {p.locality}</div>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">{fmtInt(p.carpet_area_sqft)} sqft · {fmtINR(p.rent_monthly)}</span>
            <RecBadge rec={p.recommendation} />
          </div>
        </div>
      </div>
      {p.data_quality?.length > 0 && <div className="mt-1.5 truncate rounded-lg bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">⚠ {p.data_quality[0]}</div>}
    </Link>
  )
}

export default function Pipeline() {
  const nav = useNavigate()
  const [view, setView] = useState<'board' | 'list' | 'map'>('board')
  const [showClosed, setShowClosed] = useState(false)
  const { data, isLoading, error } = useQuery({ queryKey: ['properties'], queryFn: () => get('/api/properties'), refetchInterval: 10000 })
  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const props: any[] = data || []
  const by = (s: string) => props.filter((p) => p.stage === s)

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="h-page">Property pipeline</h1>
          <p className="text-sm text-slate-500">{props.length} properties · every move is logged with who and why</p>
        </div>
        <div className="flex rounded-xl bg-slate-100 p-1 text-sm font-semibold">
          {([['board', <Columns3 key="b" className="h-4 w-4" />], ['list', <LayoutList key="l" className="h-4 w-4" />], ['map', <MapIcon key="m" className="h-4 w-4" />]] as const).map(([v, icon]) => (
            <button key={v} onClick={() => setView(v)} className={clsx('flex items-center gap-1.5 rounded-lg px-3 py-1.5 capitalize', view === v ? 'bg-white text-savo-700 shadow' : 'text-slate-500')}>{icon}{v}</button>
          ))}
        </div>
      </div>
      {!props.length && <Empty title="No properties yet">Send executives on scouting missions from an area report; their submissions land here, auto-evaluated.</Empty>}

      {view === 'board' && props.length > 0 && (
        <>
          <div className="flex gap-3 overflow-x-auto pb-3">
            {COLUMNS.map((s) => (
              <div key={s} className="w-72 shrink-0 rounded-2xl bg-slate-100/80 p-2">
                <div className="mb-2 flex items-center justify-between px-1">
                  <span className="text-sm font-bold text-slate-700">{STAGE_LABEL[s]}</span>
                  <span className="chip bg-white text-slate-500">{by(s).length}</span>
                </div>
                <div className="space-y-2">{by(s).map((p) => <Card key={p.id} p={p} />)}</div>
              </div>
            ))}
          </div>
          <button className="text-sm font-semibold text-savo-700" onClick={() => setShowClosed(!showClosed)}>
            {showClosed ? 'Hide' : 'Show'} closed ({CLOSED.reduce((n, s) => n + by(s).length, 0)})
          </button>
          {showClosed && <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{CLOSED.flatMap(by).map((p) => <div key={p.id}><StageBadge stage={p.stage} /><div className="mt-1"><Card p={p} /></div></div>)}</div>}
        </>
      )}

      {view === 'list' && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr><th className="p-3">Property</th><th className="p-3">Stage</th><th className="p-3 text-right">Score</th><th className="p-3">Rec.</th><th className="p-3 text-right">Area</th><th className="p-3 text-right">Rent / mo</th><th className="p-3">By</th><th className="p-3">Updated</th></tr>
            </thead>
            <tbody>
              {props.map((p) => (
                <tr key={p.id} className="cursor-pointer border-t border-slate-100 hover:bg-savo-50" onClick={() => nav(`/properties/${p.id}`)}>
                  <td className="p-3"><div className="font-semibold">{p.title}</div><div className="text-xs text-slate-500">{p.code} · {p.locality}</div></td>
                  <td className="p-3"><StageBadge stage={p.stage} /></td>
                  <td className="p-3 text-right font-bold" style={{ color: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</td>
                  <td className="p-3"><RecBadge rec={p.recommendation} /></td>
                  <td className="p-3 text-right">{fmtInt(p.carpet_area_sqft)}</td>
                  <td className="p-3 text-right">{fmtINR(p.rent_monthly)}</td>
                  <td className="p-3">{p.submitted_by?.name}</td>
                  <td className="p-3 text-slate-500">{ago(p.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {view === 'map' && (
        <div className="card h-[70vh] overflow-hidden">
          <MapView className="h-full" basemap="streets">
            <FitBounds points={props.map((p) => [p.lng, p.lat])} />
            {props.map((p) => (
              <Marker key={p.id} lng={p.lng} lat={p.lat} anchor="bottom" popup={
                <div className="w-52"><div className="font-semibold">{p.title}</div><div className="my-1 flex gap-1"><StageBadge stage={p.stage} /><RecBadge rec={p.recommendation} /></div>
                  <Link className="text-xs font-semibold text-savo-700" to={`/properties/${p.id}`}>Open →</Link></div>}>
                <div className="rounded-full border-2 border-white px-2 py-0.5 text-xs font-extrabold text-white shadow-md" style={{ background: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</div>
              </Marker>
            ))}
          </MapView>
        </div>
      )}
    </div>
  )
}
