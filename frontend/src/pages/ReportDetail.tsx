import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  ArrowLeft, Building2, CheckCircle2, Crosshair, GitCompare, GraduationCap, Info, MapPinned, RefreshCw, Route, ShoppingCart,
  Store, TriangleAlert, Users,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FitBounds, GeoLayer, MapView, Marker, StoreMarker, geomPoints } from '../components/Map'
import { MissionModal, StudyModal } from '../components/Modals'
import {
  AIBadge, BandBadge, DataVersions, ErrorBox, JobSteps, PageLoader, PillarBars, ScoreRing, Section, Spinner,
} from '../components/ui'
import { errorText, get, post } from '../lib/api'
import { dateTime, fmt1, fmtInt, pct, scoreColor } from '../lib/format'

export default function ReportDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [mission, setMission] = useState<any | null>(null)
  const [study, setStudy] = useState(false)
  const [focus, setFocus] = useState<number | null>(null)

  const { data: r, error, isLoading, refetch } = useQuery({
    queryKey: ['report', id],
    queryFn: () => get(`/api/reports/${id}`),
    refetchInterval: (q) => (['queued', 'running'].includes(q.state.data?.status) ? 1000 : false),
  })
  const stores = useQuery({ queryKey: ['stores'], queryFn: () => get('/api/geo/stores') })
  const retry = useMutation({ mutationFn: () => post(`/api/reports/${id}/retry`), onSuccess: () => refetch() })
  const rerun = useMutation({ mutationFn: () => post(`/api/reports/${id}/rerun`), onSuccess: (x) => { qc.invalidateQueries({ queryKey: ['reports'] }); nav(`/reports/${x.id}`) } })

  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} onRetry={refetch} /></div>
  const running = ['queued', 'running'].includes(r.status)
  const n = r.narrative || {}
  const comp = r.profile?.competition?.points || []

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/reports" className="mb-1 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-700"><ArrowLeft className="h-4 w-4" /> Reports</Link>
          <h1 className="h-page">{r.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Area Fitness Report #{r.id}</span>·<span>{fmt1(r.area_km2)} km² · {r.n_cells} cells</span>·
            <span>{r.completed_at ? `Generated ${dateTime(r.completed_at)}` : `Requested ${dateTime(r.created_at)}`}</span>
            {r.has_ground_truth && <span className="chip bg-teal-100 text-teal-800"><CheckCircle2 className="h-3 w-3" /> Ground-truthed</span>}
          </div>
        </div>
        {r.status === 'completed' && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={() => nav(`/compare?ids=${r.id}`)}><GitCompare className="h-4 w-4" /> Compare</button>
            <button className="btn-ghost" onClick={() => rerun.mutate()} disabled={rerun.isPending} title="Re-analyse with the latest data as a new, separately timestamped report">
              <RefreshCw className="h-4 w-4" /> Re-run
            </button>
            <button className="btn-primary" onClick={() => setStudy(true)}><Route className="h-4 w-4" /> Request catchment study</button>
          </div>
        )}
      </div>

      {(running || r.status === 'failed') && (
        <Section title={running ? 'Analysing area…' : 'Analysis failed'} right={running && <Spinner />}>
          <div className="grid gap-4 md:grid-cols-2">
            <JobSteps job={r.job} />
            <div className="text-sm text-slate-600">
              {running ? (
                <p>We're scoring this area against every populated neighbourhood in Chennai. This usually takes a few seconds; you can leave this page — the report is saved and will be here when you come back.</p>
              ) : (
                <div className="space-y-3">
                  <ErrorBox error={r.error || r.job?.error || 'Unknown error'} />
                  <p>Completed steps are kept; retrying re-runs the analysis from the start.</p>
                  <button className="btn-primary" onClick={() => retry.mutate()} disabled={retry.isPending}><RefreshCw className="h-4 w-4" /> Retry analysis</button>
                  {retry.error && <ErrorBox error={errorText(retry.error)} />}
                </div>
              )}
            </div>
          </div>
        </Section>
      )}

      {r.status === 'completed' && (
        <>
          <div className="grid gap-4 lg:grid-cols-5">
            <section className="card p-5 lg:col-span-2">
              <div className="flex items-center gap-4">
                <ScoreRing score={r.score} size={96} label="fit" />
                <div>
                  <BandBadge band={r.band} score={r.score} />
                  <div className="mt-1 text-sm text-slate-500">Confidence: <b className="text-slate-700">{r.confidence}</b></div>
                  <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
                    {r.profile?.confidence_reasons?.map((c: string) => <li key={c}>• {c}</li>)}
                  </ul>
                </div>
              </div>
              <h3 className="mt-4 text-lg font-bold leading-snug text-slate-900">{n.headline}</h3>
              <p className="mt-2 text-sm text-slate-600">{n.summary}</p>
              <div className="mt-3"><AIBadge meta={n.meta} /></div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <div className="mb-1 text-xs font-bold uppercase text-emerald-700">Strengths</div>
                  <ul className="space-y-1 text-sm">{n.strengths?.map((s: string) => <li key={s} className="flex gap-1.5"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />{s}</li>)}</ul>
                </div>
                <div>
                  <div className="mb-1 text-xs font-bold uppercase text-amber-700">Concerns</div>
                  <ul className="space-y-1 text-sm">{n.concerns?.map((s: string) => <li key={s} className="flex gap-1.5"><TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{s}</li>)}</ul>
                </div>
              </div>
              {n.scouting_advice && (
                <div className="mt-4 rounded-xl bg-sun/40 p-3 text-sm text-savo-900"><b>Where to scout first:</b> {n.scouting_advice}</div>
              )}
            </section>

            <section className="card relative h-[420px] overflow-hidden lg:col-span-3">
              <MapView className="h-full" basemap="streets">
                <GeoLayer id="area" data={r.outline ? { type: 'Feature', geometry: r.outline, properties: {} } as any : null}
                  layers={[{ type: 'fill', paint: { 'fill-color': '#782B90', 'fill-opacity': 0.08 } } as any,
                    { type: 'line', paint: { 'line-color': '#782B90', 'line-width': 2.5 } } as any]} />
                <GeoLayer id="comp" data={{ type: 'FeatureCollection', features: comp.map((c: any, i: number) => ({ type: 'Feature', id: i, properties: c, geometry: { type: 'Point', coordinates: [c.lng, c.lat] } })) } as any}
                  layers={[{ type: 'circle', paint: { 'circle-radius': ['case', ['==', ['get', 'category'], 'supermarket'], 5, 3.5], 'circle-color': ['case', ['==', ['get', 'category'], 'supermarket'], '#dc2626', '#f59e0b'], 'circle-stroke-width': 1, 'circle-stroke-color': '#fff' } } as any]} />
                {r.outline && <FitBounds points={geomPoints(r.outline)} padding={30} />}
                {stores.data?.map((s: any) => <Marker key={s.code} lng={s.lng} lat={s.lat} popup={<b>Savomart {s.name}</b>}><StoreMarker name={s.name} /></Marker>)}
                {r.hotspots?.map((h: any) => (
                  <Marker key={h.rank} lng={h.lng} lat={h.lat} onClick={() => setFocus(h.rank)}>
                    <div className={clsx('flex h-8 w-8 items-center justify-center rounded-full border-2 border-white text-sm font-black shadow-lg transition', focus === h.rank ? 'scale-125 bg-sun text-savo-800' : 'bg-savo-600 text-sun')}>{h.rank}</div>
                  </Marker>
                ))}
              </MapView>
              <div className="absolute bottom-2 left-2 rounded-lg bg-white/95 px-2 py-1.5 text-[11px] shadow">
                <span className="mr-2 inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-savo-600" /> Hotspot</span>
                <span className="mr-2 inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-red-600" /> Supermarket</span>
                <span className="mr-2 inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> Grocery / fresh</span>
                <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-sun ring-1 ring-savo-600" /> Savomart</span>
              </div>
            </section>
          </div>

          <Section title={<span className="flex items-center gap-2"><Crosshair className="h-4 w-4 text-savo-600" /> Scout here first</span>}
            right={<span className="text-xs text-slate-500">Ranked by demand, competition gap, footfall & road visibility within ~750 m</span>}>
            {!r.hotspots?.length && <div className="text-sm text-slate-500">No populated cells to rank in this area.</div>}
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {r.hotspots?.map((h: any) => {
                const m = r.missions?.find((x: any) => x.hotspot_rank === h.rank)
                return (
                  <div key={h.rank} onMouseEnter={() => setFocus(h.rank)}
                    className={clsx('rounded-2xl border p-3 transition', focus === h.rank ? 'border-savo-400 bg-savo-50' : 'border-slate-200')}>
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-savo-600 text-sm font-black text-sun">{h.rank}</div>
                      <div className="min-w-0 flex-1 truncate font-semibold">{h.label}</div>
                      <span className="text-sm font-bold" style={{ color: scoreColor(h.score) }}>{Math.round(h.score)}</span>
                    </div>
                    <ul className="mt-2 space-y-0.5 text-xs text-slate-600">{h.reasons.map((x: string) => <li key={x}>• {x}</li>)}</ul>
                    {m ? (
                      <Link to={`/missions/${m.id}`} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> Assigned to {m.assignee?.name} · {m.status.replace('_', ' ')}</Link>
                    ) : (
                      <button className="btn-sun mt-2 w-full py-1.5" onClick={() => setMission({
                        title: `${r.name} — hotspot #${h.rank} (${h.label})`, lat: h.lat, lng: h.lng, report_id: r.id, hotspot_rank: h.rank,
                        brief: `Look for ground-floor retail, 2,000–4,000 sq ft, main-road frontage.\nWhy here: ${h.reasons.join('; ')}.`,
                      })}>
                        <MapPinned className="h-4 w-4" /> Send an executive
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="How the score was reached" right={<span className="text-xs text-slate-500">Each pillar = percentile vs. Chennai neighbourhoods</span>}>
              <PillarBars pillars={r.pillars} />
              <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-500">
                Fit = Σ pillar × weight = {Object.values(r.pillars).map((p: any) => `${Math.round(p.score)}×${p.weight}`).join(' + ')} = <b className="text-slate-700">{r.score}</b>
              </div>
            </Section>
            <Section title="Indicators & sources">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase text-slate-400"><th className="pb-2">Indicator</th><th className="pb-2 text-right">Value</th><th className="pb-2 text-right">Score</th></tr></thead>
                  <tbody>
                    {r.indicators.map((i: any) => (
                      <tr key={i.key} className="border-t border-slate-100 align-top">
                        <td className="py-2 pr-2">
                          <div className="font-medium">{i.label}</div>
                          <div className="text-[11px] text-slate-400">{i.source}</div>
                        </td>
                        <td className="py-2 text-right tabular-nums">{fmt1(i.value)} <span className="text-xs text-slate-400">{i.unit}</span></td>
                        <td className="py-2 text-right font-bold tabular-nums" style={{ color: scoreColor(i.score) }}>{Math.round(i.score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>

          <Section title="What the area is like">
            <Profile p={r.profile} />
          </Section>

          {r.ground_truth && (
            <Section title={<span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-teal-600" /> Ground truth from catchment study {r.ground_truth.code}</span>}>
              <GroundTruth g={r.ground_truth} />
            </Section>
          )}

          <Section title="Data & method">
            <DataVersions versions={r.data_versions} created={r.completed_at} />
            <p className="mt-3 flex items-start gap-1.5 text-xs text-slate-500">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Resident numbers are estimates: a Census-2011 calibration total spread across grid cells by OSM residential buildings and streets.
              OSM under-counts small kirana stores, so competition counts are a relative signal — a catchment study gives the ground truth.
            </p>
          </Section>
        </>
      )}

      {mission && <MissionModal open onClose={() => { setMission(null); refetch() }} preset={mission} />}
      {study && <StudyModal open onClose={() => setStudy(false)} target={{ target_type: 'area', report_id: r.id, label: r.name }} />}
    </div>
  )
}

function Profile({ p }: { p: any }) {
  if (!p) return null
  const tile = (icon: JSX.Element, title: string, rows: [string, any][]) => (
    <div className="rounded-2xl bg-slate-50 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-savo-700">{icon}{title}</div>
      <dl className="space-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2"><dt className="text-slate-500">{k}</dt><dd className="font-semibold tabular-nums">{v}</dd></div>
        ))}
      </dl>
    </div>
  )
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {tile(<Users className="h-3.5 w-3.5" />, 'People', [
        ['Residents (est.)', fmtInt(p.people.population)], ['Households (est.)', fmtInt(p.people.households)], ['Per km²', fmtInt(p.people.density)]])}
      {tile(<Building2 className="h-3.5 w-3.5" />, 'Homes', [
        ['Buildings mapped', fmtInt(p.homes.buildings_mapped)], ['Apartment share', pct(p.homes.apartment_share)], ['Road network', `${fmt1(p.roads.road_km)} km`]])}
      {tile(<Store className="h-3.5 w-3.5" />, 'Businesses', [
        ['Retail shops', p.businesses.retail], ['Restaurants & cafés', p.businesses.food], ['Banks / ATMs', p.businesses.banks], ['Offices', p.businesses.offices]])}
      {tile(<GraduationCap className="h-3.5 w-3.5" />, 'Amenities & footfall', [
        ['Schools / colleges', `${p.amenities.schools} / ${p.amenities.colleges}`], ['Hospitals & clinics', p.amenities.healthcare], ['Transit stops', p.amenities.transit], ['Places of worship', p.amenities.worship]])}
      {tile(<ShoppingCart className="h-3.5 w-3.5" />, 'Competition (OSM)', [
        ['Supermarkets', p.competition.supermarkets], ['Kirana / convenience', p.competition.grocery], ['Fresh food shops', p.competition.fresh_food], ['Residents per outlet', fmtInt(p.competition.people_per_outlet)]])}
      <div className="rounded-2xl bg-savo-50 p-3">
        <div className="mb-2 text-xs font-bold uppercase tracking-wide text-savo-700">Nearest Savomart stores</div>
        <ul className="space-y-1 text-sm">
          {p.savomart.nearest.map((s: any) => (
            <li key={s.store_code} className="flex justify-between"><span>{s.name}</span><b className="tabular-nums">{fmt1(s.distance_km)} km</b></li>
          ))}
        </ul>
        {p.competition.top_brands?.length > 0 && (
          <>
            <div className="mb-1 mt-3 text-xs font-bold uppercase tracking-wide text-savo-700">Supermarkets named in OSM</div>
            <div className="flex flex-wrap gap-1">{p.competition.top_brands.map(([b, c]: [string, number]) => <span key={b} className="chip bg-white text-slate-600">{b}{c > 1 && ` ×${c}`}</span>)}</div>
          </>
        )}
      </div>
    </div>
  )
}

export function GroundTruth({ g }: { g: any }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-2xl bg-teal-50 p-3">
        <div className="text-xs font-bold uppercase text-teal-700">Households</div>
        <div className="text-2xl font-extrabold">{fmtInt(g.households_estimated)}</div>
        <div className="text-xs text-slate-500">{fmtInt(g.households_observed)} counted on {g.lanes_surveyed}/{g.lanes_total} lanes ({pct(g.coverage)} of lane-km)</div>
        {g.model_households_delta_pct != null && (
          <div className="mt-1 text-xs">Model estimated {fmtInt(g.model_households)} → survey is <b>{g.model_households_delta_pct > 0 ? '+' : ''}{g.model_households_delta_pct}%</b></div>
        )}
      </div>
      <div className="rounded-2xl bg-teal-50 p-3">
        <div className="text-xs font-bold uppercase text-teal-700">Competition on the ground</div>
        <div className="text-2xl font-extrabold">{g.kiranas_observed + g.supermarkets_observed}</div>
        <div className="text-xs text-slate-500">{g.kiranas_observed} kiranas · {g.supermarkets_observed} supermarkets · {fmtInt(g.households_per_outlet)} households per outlet</div>
      </div>
      <div className="rounded-2xl bg-teal-50 p-3">
        <div className="text-xs font-bold uppercase text-teal-700">Socio-economic mix</div>
        <div className="mt-1 flex h-3 overflow-hidden rounded-full">
          {Object.entries(g.sec_mix || {}).map(([k, v]: any, i) => <div key={k} style={{ width: `${v * 100}%`, background: ['#4d1c60', '#782B90', '#bf8dd0', '#ecdcf1'][i] }} title={`SEC ${k}: ${pct(v)}`} />)}
        </div>
        <div className="mt-1 text-xs text-slate-500">{Object.entries(g.sec_mix || {}).map(([k, v]: any) => `${k} ${pct(v)}`).join(' · ')}</div>
        <div className="mt-1 text-xs">Footfall index: <b>{g.footfall_index ?? '—'}</b> / 3</div>
      </div>
      <div className="rounded-2xl bg-teal-50 p-3">
        <div className="text-xs font-bold uppercase text-teal-700">Brands seen</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {Object.entries(g.competitor_brands || {}).map(([b, c]: any) => <span key={b} className="chip bg-white text-slate-700">{b} ×{c}</span>)}
          {!Object.keys(g.competitor_brands || {}).length && <span className="text-xs text-slate-500">None recorded</span>}
        </div>
      </div>
    </div>
  )
}
