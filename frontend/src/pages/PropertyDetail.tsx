import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  ArrowLeft, ArrowRight, CheckCircle2, Copy, FileDown, History, MessageSquare, Pencil, RefreshCw, Route, TriangleAlert, XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { GeoLayer, MapView, Marker, StoreMarker } from '../components/Map'
import { StudyModal } from '../components/Modals'
import { PropertyFields, formToPayload, propertyToForm } from '../components/PropertyFields'
import { AIBadge, DataVersions, ErrorBox, JobSteps, MockTag, Modal, PageLoader, RecBadge, ScoreRing, Section, Spinner, StageBadge, StudyBadge } from '../components/ui'
import { errorText, get, patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago, dateTime, fmt1, fmtINR, fmtInt, scoreColor, STAGE_LABEL } from '../lib/format'

const REASONS: Record<string, string> = {
  rent_too_high: 'Rent too high', size_unsuitable: 'Size unsuitable', poor_visibility: 'Poor visibility', weak_catchment: 'Weak catchment',
  too_close_to_store: 'Too close to a Savomart', legal_or_title_issue: 'Legal / title issue', owner_withdrew: 'Owner withdrew', other: 'Other',
}
const ACTION_LABEL: Record<string, string> = {
  shortlisted: 'Shortlist & ask exec to proceed', info_requested: 'Request more info', site_visit: 'Move to site visit',
  catchment_study: 'Mark catchment study', negotiation: 'Start negotiation', approved: 'Approve', rejected: 'Reject', on_hold: 'Put on hold',
  duplicate: 'Mark duplicate', submitted: 'Send back to review',
}

function circle(lng: number, lat: number, r: number) {
  const pts = Array.from({ length: 65 }, (_, i) => {
    const a = (i / 64) * 2 * Math.PI
    return [lng + ((r / 111320) * Math.cos(a)) / Math.cos((lat * Math.PI) / 180), lat + (r / 110540) * Math.sin(a)]
  })
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [pts] } } as any
}

export default function PropertyDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const [action, setAction] = useState<string | null>(null)
  const [study, setStudy] = useState(false)
  const [edit, setEdit] = useState(false)
  const [comment, setComment] = useState('')
  const [photo, setPhoto] = useState<string | null>(null)
  const { data: p, isLoading, error, refetch } = useQuery({
    queryKey: ['property', id],
    queryFn: () => get(`/api/properties/${id}`),
    refetchInterval: (q) => (['queued', 'running'].includes(q.state.data?.pending_evaluation?.status) ? 1200 : false),
  })
  const stores = useQuery({ queryKey: ['stores'], queryFn: () => get('/api/geo/stores') })
  const reeval = useMutation({ mutationFn: () => post(`/api/properties/${id}/evaluate`), onSuccess: () => refetch() })
  const addComment = useMutation({ mutationFn: () => post(`/api/properties/${id}/comments`, { note: comment }), onSuccess: () => { setComment(''); refetch() } })

  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} onRetry={refetch} /></div>
  const e = p.evaluation
  const pend = p.pending_evaluation
  const running = pend && ['queued', 'running'].includes(pend.status)
  const f = e?.facts || {}
  const isManager = user?.role === 'bd_manager'
  const canEdit = isManager || (user?.id === p.submitted_by?.id && !['approved', 'rejected'].includes(p.stage))

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={isManager ? '/pipeline' : '/my-properties'} className="mb-1 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-700"><ArrowLeft className="h-4 w-4" /> {isManager ? 'Pipeline' : 'My properties'}</Link>
          <h1 className="h-page">{p.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <StageBadge stage={p.stage} /> <span>{p.code}</span>·<span>{p.locality}{p.pincode && ` ${p.pincode}`}</span>·<span>by {p.submitted_by?.name} {ago(p.created_at)}</span>
            {p.mission && <>· <Link className="text-savo-700" to={`/missions/${p.mission.id}`}>Mission: {p.mission.title}</Link></>}
          </div>
        </div>
        <div className="no-print flex flex-wrap gap-2">
          {canEdit && <button className="btn-ghost" onClick={() => setEdit(true)}><Pencil className="h-4 w-4" /> Edit details</button>}
          {isManager && <Link className="btn-ghost" to={`/properties/${p.id}/pack`} target="_blank"><FileDown className="h-4 w-4" /> Decision pack</Link>}
          {isManager && !['approved', 'rejected', 'duplicate'].includes(p.stage) && <button className="btn-ghost" onClick={() => setStudy(true)}><Route className="h-4 w-4" /> Catchment study</button>}
        </div>
      </div>

      {p.stage === 'info_requested' && user?.id === p.submitted_by?.id && (
        <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm">
          <b>Your manager asked for more information:</b> {p.events.find((x: any) => x.to_stage === 'info_requested')?.note}
          <div className="mt-2"><button className="btn-primary" onClick={() => setEdit(true)}><Pencil className="h-4 w-4" /> Update & send back</button></div>
        </div>
      )}

      {p.duplicates?.length > 0 && (
        <div className="flex items-start gap-2 rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <Copy className="mt-0.5 h-4 w-4 shrink-0" />
          <div>Possible duplicate of {p.duplicates.map((d: any) => <Link key={d.id} to={`/properties/${d.id}`} className="font-semibold underline">{d.code} ({d.distance_m} m away)</Link>)}</div>
        </div>
      )}

      {/* ---------- 30-second decision card ---------- */}
      <div className="grid gap-4 lg:grid-cols-5">
        <section className="card p-5 lg:col-span-3">
          {running && <div className="mb-4"><div className="mb-2 text-sm font-semibold">Evaluating v{pend.version} ({pend.trigger.replace('_', ' ')})…</div><JobSteps job={pend.job} /></div>}
          {pend?.status === 'failed' && <div className="mb-4 space-y-2"><ErrorBox error={pend.error || 'Evaluation failed'} /><button className="btn-primary" onClick={() => reeval.mutate()}>Retry evaluation</button></div>}
          {e && (() => {
            const ev = e
            return (
              <>
                <div className="flex flex-wrap items-center gap-4">
                  <ScoreRing score={ev.score} size={96} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <RecBadge rec={ev.recommendation} />
                      <span className="text-xs text-slate-500">Evaluation v{ev.version} · {ev.trigger.replace('_', ' ')} · {ago(ev.created_at)}</span>
                      {f.previous && (
                        <span className="chip bg-slate-100 text-slate-600">
                          v{f.previous.version}: {Math.round(f.previous.score)} → {Math.round(ev.score)} {ev.score >= f.previous.score ? '▲' : '▼'}
                        </span>
                      )}
                    </div>
                    <h2 className="mt-1 text-lg font-bold leading-snug">{ev.narrative?.headline}</h2>
                    <p className="text-sm text-slate-600">{ev.narrative?.summary}</p>
                    <div className="mt-1.5"><AIBadge meta={ev.narrative?.meta} /></div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <KeyFact label="Rent / month" value={fmtINR(p.rent_monthly)} sub={f.rent_psf ? <>₹{fmt1(f.rent_psf)}/sqft vs ₹{fmt1(f.rent_benchmark_psf_mock)} <MockTag /></> : p.rent_negotiable ? 'not quoted' : null} tone={f.rent_vs_benchmark_pct > 20 ? 'bad' : f.rent_vs_benchmark_pct < -5 ? 'good' : undefined} />
                  <KeyFact label="Carpet area" value={`${fmtInt(p.carpet_area_sqft)} sqft`} sub={`${p.frontage_ft ?? '—'} ft frontage · ${p.floor || '—'}`} />
                  <KeyFact label="Nearest Savomart" value={`${fmt1(f.nearest_savomart?.distance_km)} km`} sub={f.nearest_savomart?.name} tone={f.nearest_savomart?.distance_km < 1.5 ? 'bad' : undefined} />
                  <KeyFact label="Residents ≤ 800 m" value={fmtInt(f.residents_est)} sub={`${f.grocery_outlets_mapped} grocery · ${f.supermarkets_mapped} supermarkets`} />
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs font-bold uppercase text-emerald-700">Why it could work</div>
                    <ul className="space-y-1 text-sm">{ev.insights?.slice(0, 5).map((s: string) => <li key={s} className="flex gap-1.5"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />{s}</li>)}</ul>
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-bold uppercase text-rose-700">Risks</div>
                    {!ev.risks?.length && <div className="text-sm text-slate-500">No material risks flagged.</div>}
                    <ul className="space-y-1 text-sm">{ev.risks?.slice(0, 6).map((s: string) => <li key={s} className="flex gap-1.5"><TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />{s}</li>)}</ul>
                  </div>
                </div>
                {ev.narrative?.next_step && <div className="mt-4 rounded-xl bg-sun/40 p-3 text-sm text-savo-900"><b>Suggested next step:</b> {ev.narrative.next_step}</div>}
              </>
            )
          })()}
        </section>

        <section className="card flex flex-col overflow-hidden lg:col-span-2">
          <div className="grid h-48 grid-cols-3 gap-0.5 bg-slate-100">
            {p.photos.slice(0, 3).map((ph: any, i: number) => (
              <button key={ph.id} className={clsx('overflow-hidden', i === 0 && p.photos.length > 1 && 'col-span-2 row-span-2', p.photos.length === 1 && 'col-span-3')} onClick={() => setPhoto(ph.url)}>
                <img src={ph.url} className="h-full w-full object-cover" />
              </button>
            ))}
            {!p.photos.length && <div className="col-span-3 flex items-center justify-center text-sm text-slate-400">No photos</div>}
          </div>
          {isManager && p.allowed_transitions.length > 0 && (
            <div className="space-y-2 p-4">
              <div className="text-xs font-bold uppercase text-slate-500">Decide</div>
              <div className="flex flex-wrap gap-2">
                {p.allowed_transitions.filter((t: string) => !['rejected', 'on_hold', 'duplicate', 'catchment_study'].includes(t)).map((t: string) => (
                  <button key={t} className={t === 'approved' || t === 'shortlisted' ? 'btn-primary' : 'btn-ghost'} onClick={() => setAction(t)}>
                    <ArrowRight className="h-4 w-4" /> {ACTION_LABEL[t] || STAGE_LABEL[t]}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {p.allowed_transitions.includes('rejected') && <button className="btn bg-rose-50 text-rose-700 hover:bg-rose-100" onClick={() => setAction('rejected')}><XCircle className="h-4 w-4" /> Reject</button>}
                {p.allowed_transitions.includes('on_hold') && <button className="btn-ghost" onClick={() => setAction('on_hold')}>Hold</button>}
                {p.allowed_transitions.includes('duplicate') && <button className="btn-ghost" onClick={() => setAction('duplicate')}>Duplicate</button>}
              </div>
            </div>
          )}
          <div className="border-t border-slate-100 p-4 text-sm">
            <div className="mb-1 text-xs font-bold uppercase text-slate-500">Catchment studies</div>
            {!p.studies.length && <div className="text-slate-500">None yet.</div>}
            {p.studies.map((s: any) => (
              <Link key={s.id} to={`/studies/${s.id}`} className="flex items-center justify-between py-1 hover:text-savo-700">
                <span>{s.code} · {s.title.slice(0, 28)}</span><StudyBadge status={s.status} />
              </Link>
            ))}
          </div>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card h-[380px] overflow-hidden">
          <MapView className="h-full" center={[p.lng, p.lat]} zoom={14.6} basemap="streets">
            <GeoLayer id="radius" data={circle(p.lng, p.lat, f.catchment_radius_m || 800)} layers={[{ type: 'fill', paint: { 'fill-color': '#782B90', 'fill-opacity': 0.06 } } as any, { type: 'line', paint: { 'line-color': '#782B90', 'line-dasharray': [2, 2] } } as any]} />
            <GeoLayer id="competitors" data={{ type: 'FeatureCollection', features: (f.competitors || []).map((c: any) => ({ type: 'Feature', id: c.id, properties: c, geometry: { type: 'Point', coordinates: [c.lng, c.lat] } })) } as any}
              layers={[{ type: 'circle', paint: { 'circle-radius': ['case', ['==', ['get', 'category'], 'supermarket'], 6, 4], 'circle-color': ['case', ['==', ['get', 'category'], 'supermarket'], '#dc2626', '#f59e0b'], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 } } as any]} />
            {stores.data?.map((s: any) => <Marker key={s.code} lng={s.lng} lat={s.lat} popup={<b>Savomart {s.name}</b>}><StoreMarker name={s.name} /></Marker>)}
            {p.duplicates?.map((d: any) => <Marker key={d.id} lng={d.lng} lat={d.lat}><div className="h-3 w-3 rounded-full border-2 border-white bg-amber-500" /></Marker>)}
            <Marker lng={p.lng} lat={p.lat} anchor="bottom">
              <div className="flex flex-col items-center"><div className="rounded-lg bg-savo-600 px-2 py-0.5 text-xs font-bold text-sun shadow">{p.code}</div><div className="h-2 w-0.5 bg-savo-600" /></div>
            </Marker>
          </MapView>
        </section>
        {e?.pillars && (
          <Section title="Score breakdown" right={isManager && <button className="text-xs font-semibold text-savo-700" onClick={() => reeval.mutate()} disabled={reeval.isPending}><RefreshCw className="mr-1 inline h-3.5 w-3.5" />Re-evaluate</button>}>
            <div className="space-y-3">
              {Object.entries(e.pillars).map(([k, pl]: any) => (
                <div key={k}>
                  <div className="mb-1 flex justify-between text-sm"><span className="font-medium">{pl.label} <span className="text-xs text-slate-400">× {Math.round(pl.weight * 100)}%</span></span><b style={{ color: scoreColor(pl.score) }}>{Math.round(pl.score)}</b></div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full" style={{ width: `${pl.score}%`, background: scoreColor(pl.score) }} /></div>
                  {pl.parts && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {pl.parts.map((x: any) => <span key={x.label} className="chip bg-slate-50 text-slate-600 ring-1 ring-slate-200" title={x.note}>{x.label}: <b style={{ color: scoreColor(x.score) }}>{x.score}</b></span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {f.nearest_road && <div className="mt-3 text-xs text-slate-500">Nearest mapped road: {f.nearest_road.name || 'unnamed'} ({f.nearest_road.highway}, {f.nearest_road.distance_m} m)</div>}
          </Section>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Section title="Captured details" className="lg:col-span-1">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
            {([
              ['Type', p.property_type?.replace(/_/g, ' ')], ['Carpet area', `${fmtInt(p.carpet_area_sqft)} sqft`], ['Frontage', p.frontage_ft && `${p.frontage_ft} ft`], ['Floor', p.floor],
              ['Ceiling', p.ceiling_height_ft && `${p.ceiling_height_ft} ft`], ['Road', p.road_facing?.replace('_', ' ')], ['Road width', p.road_width_ft && `${p.road_width_ft} ft`], ['Visibility', p.visibility && `${p.visibility}/5`],
              ['Parking', `${p.parking_2w ?? 0} 2W · ${p.parking_4w ?? 0} car`], ['Power', p.power_kw && `${p.power_kw} kW`], ['Truck access', p.truck_access == null ? null : p.truck_access ? 'Yes' : 'No'],
              ['Rent', fmtINR(p.rent_monthly)], ['Deposit', p.deposit_months && `${p.deposit_months} months`], ['Lease', p.lease_years && `${p.lease_years} years`], ['Available', p.available_from],
              ['Owner', p.owner_name], ['Phone', p.owner_phone], ['GPS accuracy', p.gps_accuracy_m && `±${Math.round(p.gps_accuracy_m)} m`],
            ] as [string, any][]).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="font-medium capitalize">{v || '—'}</dd></div>
            ))}
          </dl>
          {p.address && <div className="mt-2 text-xs text-slate-500">{p.address}</div>}
          {p.notes && <div className="mt-2 rounded-lg bg-slate-50 p-2 text-sm">{p.notes}</div>}
          {p.data_quality?.length > 0 && (
            <div className="mt-3 space-y-1">{p.data_quality.map((w: string) => <div key={w} className="rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-800">⚠ {w}</div>)}</div>
          )}
        </Section>

        <Section title={<span className="flex items-center gap-2"><History className="h-4 w-4 text-savo-600" /> History</span>} className="lg:col-span-2">
          <form className="no-print mb-3 flex gap-2" onSubmit={(ev) => { ev.preventDefault(); comment.trim() && addComment.mutate() }}>
            <input className="input" placeholder="Add a comment…" value={comment} onChange={(ev) => setComment(ev.target.value)} />
            <button className="btn-ghost" disabled={!comment.trim() || addComment.isPending}><MessageSquare className="h-4 w-4" /></button>
          </form>
          <ol className="relative space-y-3 border-l-2 border-savo-100 pl-4">
            {p.events.map((ev: any) => (
              <li key={ev.id} className="relative">
                <span className="absolute -left-[23px] top-1 h-3 w-3 rounded-full border-2 border-white bg-savo-500" />
                <div className="text-sm">
                  <b>{ev.actor?.name || 'System'}</b>{' '}
                  {ev.action === 'stage_change' ? <>moved it <StageBadge stage={ev.from_stage} /> → <StageBadge stage={ev.to_stage} /></> :
                    ev.action === 'created' ? 'onboarded the property' : ev.action === 'comment' ? 'commented' : ev.action === 'details_updated' ? 'updated details' : ev.action.replace(/_/g, ' ')}
                  <span className="ml-1 text-xs text-slate-400">{dateTime(ev.created_at)}</span>
                </div>
                {ev.meta?.reason && <div className="text-xs font-semibold text-rose-700">Reason: {REASONS[ev.meta.reason] || ev.meta.reason}</div>}
                {ev.note && <div className="mt-0.5 rounded-lg bg-slate-50 px-2 py-1 text-sm text-slate-700">{ev.note}</div>}
                {ev.meta?.changed && <div className="mt-0.5 text-xs text-slate-500">{Object.entries(ev.meta.changed).map(([k, v]: any) => `${k}: ${v.from} → ${v.to}`).join(' · ')}</div>}
              </li>
            ))}
          </ol>
          <div className="mt-4 border-t pt-3">
            <div className="mb-1 text-xs font-bold uppercase text-slate-500">Evaluation versions</div>
            <div className="flex flex-wrap gap-2">
              {p.evaluations.map((x: any) => (
                <span key={x.version} className="chip bg-slate-100 text-slate-700">v{x.version} · {x.trigger.replace('_', ' ')} · {x.score ? Math.round(x.score) : x.status} {x.recommendation && `(${x.recommendation.replace('_', '-')})`}</span>
              ))}
            </div>
          </div>
        </Section>
      </div>

      {e?.data_versions && <Section title="Data used"><DataVersions versions={e.data_versions} created={e.created_at} /></Section>}

      {action && <TransitionModal pid={p.id} to={action} onClose={() => setAction(null)} onDone={() => { setAction(null); qc.invalidateQueries() }} />}
      {study && <StudyModal open onClose={() => setStudy(false)} target={{ target_type: 'property', property_id: p.id, label: p.code }} />}
      {edit && <EditModal p={p} onClose={() => setEdit(false)} onDone={() => { setEdit(false); qc.invalidateQueries() }} />}
      <Modal open={!!photo} onClose={() => setPhoto(null)} title="Photo" wide>{photo && <img src={photo} className="w-full rounded-xl" />}</Modal>
    </div>
  )
}

function KeyFact({ label, value, sub, tone }: { label: string; value: any; sub?: any; tone?: 'good' | 'bad' }) {
  return (
    <div className={clsx('rounded-xl p-2.5', tone === 'bad' ? 'bg-rose-50' : tone === 'good' ? 'bg-emerald-50' : 'bg-slate-50')}>
      <div className="text-[11px] font-semibold uppercase text-slate-500">{label}</div>
      <div className="text-base font-extrabold tabular-nums">{value}</div>
      {sub && <div className="flex flex-wrap items-center gap-1 text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

function TransitionModal({ pid, to, onClose, onDone }: { pid: number; to: string; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const m = useMutation({ mutationFn: () => post(`/api/properties/${pid}/transition`, { to, note, reason: reason || null }), onSuccess: onDone })
  const prompts: Record<string, string> = {
    shortlisted: 'e.g. Strong catchment, rent fair. Get title documents and a revised quote.',
    info_requested: 'What does the executive need to find out or fix?',
    rejected: 'Why is this not going ahead?',
    approved: 'Final approval note for the record',
  }
  return (
    <Modal open onClose={onClose} title={ACTION_LABEL[to] || STAGE_LABEL[to]}>
      <div className="space-y-3">
        {to === 'rejected' && (
          <div>
            <label className="label">Reason</label>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(REASONS).map(([k, v]) => (
                <button key={k} className={clsx('rounded-xl border px-3 py-1.5 text-sm', reason === k ? 'border-rose-500 bg-rose-50 font-semibold text-rose-700' : 'border-slate-300')} onClick={() => setReason(k)}>{v}</button>
              ))}
            </div>
          </div>
        )}
        <div>
          <label className="label">Why? (visible to the team)</label>
          <textarea className="input min-h-24" value={note} onChange={(e) => setNote(e.target.value)} placeholder={prompts[to] || 'Add a note'} autoFocus />
        </div>
        {m.error && <ErrorBox error={errorText(m.error)} />}
        <button className={to === 'rejected' ? 'btn-danger w-full' : 'btn-primary w-full'} disabled={!note.trim() || (to === 'rejected' && !reason) || m.isPending} onClick={() => m.mutate()}>
          {m.isPending && <Spinner className="h-4 w-4 text-white" />} Confirm
        </button>
      </div>
    </Modal>
  )
}

function EditModal({ p, onClose, onDone }: { p: any; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState(propertyToForm(p))
  const [note, setNote] = useState('')
  const m = useMutation({ mutationFn: () => patch(`/api/properties/${p.id}`, { fields: formToPayload(f), note: note || null }), onSuccess: onDone })
  return (
    <Modal open onClose={onClose} title={`Edit ${p.code}`} wide>
      <PropertyFields f={f} set={(x) => setF({ ...f, ...x })} />
      <div className="mt-4 space-y-2 border-t pt-4">
        <input className="input" placeholder="What changed? (logged in history)" value={note} onChange={(e) => setNote(e.target.value)} />
        {m.error && <ErrorBox error={errorText(m.error)} />}
        <button className="btn-primary w-full" disabled={m.isPending} onClick={() => m.mutate()}>{m.isPending && <Spinner className="h-4 w-4 text-white" />} Save & re-evaluate</button>
      </div>
    </Modal>
  )
}
