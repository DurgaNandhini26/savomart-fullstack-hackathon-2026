import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, CheckCircle2, Info, Recycle, Scissors, UserPlus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FitBounds, GeoLayer, MapView, Marker, geomPoints } from '../components/Map'
import { ErrorBox, PageLoader, Section, Spinner, StudyBadge } from '../components/ui'
import { errorText, get, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime, fmt1, pct } from '../lib/format'
import { GroundTruth } from './ReportDetail'

export default function StudyDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const sm = user?.role === 'survey_manager'
  const { data: s, isLoading, error, refetch } = useQuery({ queryKey: ['study', id], queryFn: () => get(`/api/studies/${id}`), refetchInterval: 8000 })
  const execs = useQuery({ queryKey: ['users', 'survey_exec'], queryFn: () => get('/api/users?role=survey_exec'), enabled: sm })
  const [k, setK] = useState<number>(3)
  const [hoverUnit, setHoverUnit] = useState<number | null>(null)
  useEffect(() => { if (s?.suggested_units) setK(s.suggested_units) }, [s?.suggested_units])
  const plan = useMutation({ mutationFn: () => post(`/api/studies/${id}/plan`, { units: k }), onSuccess: () => refetch() })
  const assign = useMutation({ mutationFn: ({ uid, assignee_id }: any) => post(`/api/work-units/${uid}/assign`, { assignee_id }), onSuccess: () => { refetch(); qc.invalidateQueries({ queryKey: ['team'] }) } })
  const complete = useMutation({ mutationFn: () => post(`/api/studies/${id}/complete`), onSuccess: () => refetch() })

  const unitsFC = useMemo(() => s && ({
    type: 'FeatureCollection',
    features: s.units.map((u: any) => ({ type: 'Feature', id: u.id, properties: { color: u.color, id: u.id }, geometry: u.outline })),
  }), [s])

  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const lanesDone = s.lanes.features.filter((f: any) => f.properties.status !== 'pending').length
  const days = s.lane_km_estimate && s.lane_km_per_day ? s.lane_km_estimate / s.lane_km_per_day : null

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 sm:p-6">
      <Link to={sm ? '/' : '/studies'} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-700"><ArrowLeft className="h-4 w-4" /> Studies</Link>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="h-page">{s.code} · {s.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <StudyBadge status={s.status} /> <span className="capitalize">{s.priority} priority</span>·<span>requested by {s.requested_by?.name} {dateTime(s.created_at)}</span>
            {s.property && <>· <Link to={`/properties/${s.property.id}`} className="text-savo-700">{s.property.code}</Link></>}
            {s.report && <>· <Link to={`/reports/${s.report.id}`} className="text-savo-700">{s.report.name}</Link></>}
          </div>
          {s.notes && <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">“{s.notes}”</div>}
        </div>
        {sm && ['in_progress', 'planned'].includes(s.status) && (
          <button className="btn-ghost" onClick={() => complete.mutate()} disabled={complete.isPending} title="Close early once ≥60% of lane-km are surveyed">
            <CheckCircle2 className="h-4 w-4" /> Close study & roll up
          </button>
        )}
      </div>
      {complete.error && <ErrorBox error={errorText(complete.error)} />}

      {s.reused.length > 0 && (
        <div className="flex items-start gap-2 rounded-2xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-900">
          <Recycle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            Reusing survey data from {s.reused.map((r: any) => <Link key={r.study_id} to={`/studies/${r.study_id}`} className="font-semibold underline">{r.code} ({r.n_cells} cells)</Link>)}.{' '}
            {s.status === 'reused' ? 'No new fieldwork was needed.' : `Only the remaining ${s.n_cells} of ${s.n_requested_cells} cells are surveyed.`}
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <section className="card relative h-[460px] overflow-hidden lg:col-span-3">
          <MapView className="h-full" basemap="light">
            <GeoLayer id="req" data={s.requested_geojson} layers={[
              { type: 'fill', paint: { 'fill-color': ['case', ['get', 'covered'], '#14b8a6', '#782B90'], 'fill-opacity': ['case', ['get', 'covered'], 0.25, 0.04] } } as any,
              { type: 'line', paint: { 'line-color': '#94a3b8', 'line-width': 0.5 } } as any,
            ]} />
            <GeoLayer id="units" data={unitsFC as any} layers={[
              { type: 'fill', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': hoverUnit ? ['case', ['==', ['get', 'id'], hoverUnit], 0.3, 0.06] : 0.12 } } as any,
              { type: 'line', paint: { 'line-color': ['get', 'color'], 'line-width': 2.5 } } as any,
            ]} />
            <GeoLayer id="lanes" data={s.lanes} layers={[
              { type: 'line', paint: { 'line-color': ['case', ['==', ['get', 'status'], 'done'], '#16a34a', ['==', ['get', 'status'], 'inaccessible'], '#dc2626', ['coalesce', ['get', 'color'], '#782B90']], 'line-width': ['case', ['==', ['get', 'status'], 'pending'], 1.6, 3.2], 'line-opacity': 0.85 } } as any,
            ]} />
            <FitBounds points={geomPoints(s.requested_geojson)} padding={30} />
            {s.property && (
              <Marker lng={s.property.lng} lat={s.property.lat}>
                <div className="rounded-lg bg-savo-600 px-2 py-0.5 text-xs font-bold text-sun shadow">{s.property.code}</div>
              </Marker>
            )}
          </MapView>
          <div className="absolute bottom-2 left-2 rounded-lg bg-white/95 px-2 py-1.5 text-[11px] shadow">
            <span className="mr-2"><span className="mr-1 inline-block h-1 w-4 bg-green-600 align-middle" />Surveyed</span>
            <span className="mr-2"><span className="mr-1 inline-block h-1 w-4 bg-red-600 align-middle" />Inaccessible</span>
            <span className="mr-2"><span className="mr-1 inline-block h-1 w-4 bg-savo-600 align-middle" />To do</span>
            {s.reused.length > 0 && <span><span className="mr-1 inline-block h-2.5 w-2.5 bg-teal-400/60 align-middle" />Already surveyed</span>}
          </div>
        </section>

        <div className="space-y-4 lg:col-span-2">
          {sm && ['requested', 'planned'].includes(s.status) && (
            <Section title={<span className="flex items-center gap-2"><Scissors className="h-4 w-4 text-savo-600" /> Split into work units</span>}>
              <p className="mb-3 text-sm text-slate-600">
                {s.lane_km_estimate != null
                  ? <>~<b>{fmt1(s.lane_km_estimate)} km</b> of lanes ≈ <b>{fmt1(days)}</b> surveyor-days at {s.lane_km_per_day} km/day. You have {s.surveyors} surveyors.</>
                  : <>Lanes are already materialised. Re-split to change the number of units.</>}
              </p>
              <div className="flex items-center gap-2">
                <label className="text-sm font-semibold">Units</label>
                <input type="range" min={1} max={8} value={k} onChange={(e) => setK(Number(e.target.value))} className="flex-1 accent-savo-600" />
                <span className="w-6 text-center font-bold">{k}</span>
              </div>
              <button className="btn-primary mt-3 w-full" onClick={() => plan.mutate()} disabled={plan.isPending}>
                {plan.isPending ? <Spinner className="h-4 w-4 text-white" /> : <Scissors className="h-4 w-4" />} {s.units.length ? 'Re-split' : 'Split'} into {k} sectors
              </button>
              {plan.error && <div className="mt-2"><ErrorBox error={errorText(plan.error)} /></div>}
              <div className="mt-2 flex items-start gap-1.5 text-[11px] text-slate-500">
                <Info className="mt-0.5 h-3 w-3 shrink-0" /> Grid cells are swept by compass bearing around the centre and cut into contiguous sectors with equal lane-km — non-overlapping, compact, and each starts near the centre.
              </div>
            </Section>
          )}

          <Section title="Work units" right={<span className="text-xs text-slate-500">{lanesDone}/{s.lanes.features.length} lanes · {pct(s.progress)}</span>}>
            {!s.units.length && <div className="text-sm text-slate-500">{s.status === 'reused' ? 'Satisfied by existing data.' : 'Not split yet.'}</div>}
            <div className="space-y-2">
              {s.units.map((u: any) => {
                const pu = s.progress_detail.units.find((x: any) => x.id === u.id)
                return (
                  <div key={u.id} className={clsx('rounded-xl border p-2.5 transition', hoverUnit === u.id ? 'border-savo-400' : 'border-slate-200')} onMouseEnter={() => setHoverUnit(u.id)} onMouseLeave={() => setHoverUnit(null)}>
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ background: u.color }} />
                      <span className="flex-1 font-semibold">{u.name}</span>
                      <span className="text-xs text-slate-500">{u.lane_count} lanes · {fmt1(u.lane_km)} km</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full" style={{ width: `${(pu?.pct || 0) * 100}%`, background: u.color }} /></div>
                    <div className="mt-1.5 flex items-center gap-2">
                      {sm && u.status !== 'done' ? (
                        <select className="input py-1.5 text-sm" value={u.assignee?.id || ''} onChange={(e) => e.target.value && assign.mutate({ uid: u.id, assignee_id: Number(e.target.value) })}>
                          <option value="">{u.assignee ? u.assignee.name : 'Assign to…'}</option>
                          {execs.data?.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}
                        </select>
                      ) : (
                        <span className="text-sm">{u.assignee ? <><UserPlus className="mr-1 inline h-3.5 w-3.5" />{u.assignee.name}</> : 'Unassigned'}</span>
                      )}
                      <span className="chip shrink-0 bg-slate-100 capitalize text-slate-600">{u.status.replace('_', ' ')}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>
        </div>
      </div>

      {s.insights ? (
        <Section title={<span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-teal-600" /> Catchment insights</span>} right={<span className="text-xs text-slate-500">Rolled up {dateTime(s.insights.computed_at)}</span>}>
          <GroundTruth g={s.insights} />
          <p className="mt-3 text-xs text-slate-500">Households on unsurveyed lanes are extrapolated by lane length. Linked properties were automatically re-evaluated with this ground truth.</p>
        </Section>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">
          Insights appear here automatically when every work unit is done (or the survey manager closes the study at ≥60% coverage).
        </div>
      )}
    </div>
  )
}
