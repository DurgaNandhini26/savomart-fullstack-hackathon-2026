import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, Ban, Check, ChevronLeft, ChevronRight, CloudOff, List, LocateFixed, Map as MapIcon, Minus, Plus } from 'lucide-react'
import type { Map as MLMap } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FitBounds, GeoLayer, MapView, Marker, geomPoints } from '../components/Map'
import { ErrorBox, PageLoader } from '../components/ui'
import { get } from '../lib/api'
import { fmt1, uuid } from '../lib/format'
import { enqueue, flush, hasDraft, useDraft, useOnline, useOutbox } from '../lib/offline'

const BRANDS = ['Reliance Smart', 'More', 'DMart', 'Nilgiris', "Spencer's", 'Star Bazaar', 'Kannan Departmental', 'Local supermarket']
const CACHE_KEY = (id: string) => `sitescout.unit.${id}`

interface LaneForm {
  households: number
  housing_type: string
  sec: string
  occupancy: string
  kiranas: number
  supermarkets: number
  competitor_brands: string[]
  footfall: string
  access: string
  notes: string
}
const EMPTY: LaneForm = { households: 0, housing_type: '', sec: '', occupancy: '', kiranas: 0, supermarkets: 0, competitor_brands: [], footfall: '', access: '', notes: '' }

export default function SurveyUnit() {
  const { id } = useParams()
  const qc = useQueryClient()
  const online = useOnline()
  const outbox = useOutbox()
  const [view, setView] = useState<'map' | 'list'>('map')
  const [laneId, setLaneId] = useState<number | null>(null)
  const [me, setMe] = useState<[number, number] | null>(null)
  const mapRef = useRef<MLMap | null>(null)

  // cache the assignment so it opens with no signal
  const { data, isLoading, error } = useQuery({
    queryKey: ['unit', id],
    queryFn: async () => {
      const d = await get(`/api/work-units/${id}`)
      try { localStorage.setItem(CACHE_KEY(id!), JSON.stringify(d)) } catch { /* quota */ }
      return d
    },
    initialData: () => { try { const c = localStorage.getItem(CACHE_KEY(id!)); return c ? JSON.parse(c) : undefined } catch { return undefined } },
    refetchInterval: 30000,
  })

  const queued = useMemo(() => new Map(outbox.filter((o) => o.kind === 'observation').map((o) => [o.payload.lane_id, o.payload.data.status])), [outbox])
  const lanes = useMemo(() => {
    if (!data) return null
    return {
      ...data.lanes,
      features: data.lanes.features.map((f: any) => {
        const q = queued.get(f.id)
        const st = q || f.properties.status
        return { ...f, properties: { ...f.properties, status: st, local: !!q, draft: st === 'pending' && hasDraft(`lane-${f.id}`), sel: f.id === laneId } }
      }),
    }
  }, [data, queued, laneId, outbox])

  if (isLoading && !data) return <PageLoader />
  if (error && !data) return <div className="p-6"><ErrorBox error={error} /></div>
  const feats = lanes.features
  const done = feats.filter((f: any) => f.properties.status !== 'pending').length
  const order = [...feats].sort((a: any, b: any) => (a.properties.status === 'pending' ? 0 : 1) - (b.properties.status === 'pending' ? 0 : 1))
  const lane = feats.find((f: any) => f.id === laneId)

  function locateMe() {
    navigator.geolocation?.getCurrentPosition((p) => {
      setMe([p.coords.longitude, p.coords.latitude])
      mapRef.current?.flyTo({ center: [p.coords.longitude, p.coords.latitude], zoom: 17 })
    })
  }
  function nextPending(after?: number) {
    const pend = feats.filter((f: any) => f.properties.status === 'pending' && f.id !== after)
    return pend[0]?.id ?? null
  }

  return (
    <div className="flex h-[calc(100vh-57px-64px)] flex-col md:h-[calc(100vh-57px)]">
      <div className="flex items-center gap-2 border-b bg-white px-3 py-2">
        <Link to="/" className="rounded-lg p-1.5 hover:bg-slate-100"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-bold">{data.study.code} · {data.name}</div>
          <div className="text-xs text-slate-500">{done}/{feats.length} lanes · {fmt1(data.lane_km)} km {!online && <span className="ml-1 text-slate-800"><CloudOff className="inline h-3 w-3" /> offline</span>}</div>
        </div>
        <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-emerald-500" style={{ width: `${(done / Math.max(feats.length, 1)) * 100}%` }} /></div>
        <button className="rounded-lg p-1.5 hover:bg-slate-100" onClick={() => setView(view === 'map' ? 'list' : 'map')}>{view === 'map' ? <List className="h-5 w-5" /> : <MapIcon className="h-5 w-5" />}</button>
      </div>

      <div className="relative min-h-0 flex-1">
        {view === 'map' ? (
          <MapView className="h-full" basemap="streets" onReady={(m) => (mapRef.current = m)}>
            <GeoLayer id="unit" data={{ type: 'Feature', geometry: data.outline, properties: {} } as any} layers={[{ type: 'line', paint: { 'line-color': data.color, 'line-width': 2, 'line-dasharray': [2, 1] } } as any]} />
            <GeoLayer id="lanes" data={lanes} onClick={(f) => setLaneId(Number(f.id))} layers={[
              { type: 'line', paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'sel'], 11, 7] } } as any,
              { type: 'line', paint: { 'line-color': ['case', ['get', 'sel'], '#FFF200', ['==', ['get', 'status'], 'done'], '#16a34a', ['==', ['get', 'status'], 'inaccessible'], '#dc2626', ['get', 'draft'], '#f59e0b', '#782B90'], 'line-width': ['case', ['get', 'sel'], 7, 4] } } as any,
            ]} />
            <FitBounds points={geomPoints(data.outline)} padding={20} maxZoom={17} />
            {me && <Marker lng={me[0]} lat={me[1]}><div className="h-4 w-4 rounded-full border-2 border-white bg-sky-500 shadow ring-4 ring-sky-300/40" /></Marker>}
          </MapView>
        ) : (
          <div className="h-full overflow-y-auto bg-slate-50 p-3">
            {order.map((f: any) => (
              <button key={f.id} onClick={() => setLaneId(f.id)} className="mb-1.5 flex w-full items-center gap-3 rounded-xl bg-white p-3 text-left shadow-sm">
                <span className={clsx('h-3 w-3 rounded-full', f.properties.status === 'done' ? 'bg-emerald-500' : f.properties.status === 'inaccessible' ? 'bg-rose-500' : f.properties.draft ? 'bg-amber-400' : 'bg-savo-500')} />
                <span className="flex-1 truncate font-medium">{f.properties.name || `Unnamed ${f.properties.highway} lane`}</span>
                <span className="text-xs text-slate-400">{Math.round(f.properties.length_m)} m</span>
                {f.properties.local && <CloudOff className="h-3.5 w-3.5 text-amber-600" />}
              </button>
            ))}
          </div>
        )}
        {view === 'map' && !lane && (
          <div className="absolute inset-x-3 bottom-3 flex gap-2">
            <button className="btn-ghost shadow-lg" onClick={locateMe}><LocateFixed className="h-4 w-4" /></button>
            <button className="btn-primary flex-1 shadow-lg" disabled={!nextPending()} onClick={() => setLaneId(nextPending())}>
              {nextPending() ? 'Next lane to survey' : 'All lanes surveyed 🎉'}
            </button>
          </div>
        )}
      </div>

      {lane && (
        <LaneSheet key={lane.id} lane={lane} unitId={Number(id)}
          onClose={() => setLaneId(null)}
          onSaved={() => {
            const nxt = nextPending(lane.id)
            setLaneId(nxt)
            flush().then(() => qc.invalidateQueries({ queryKey: ['unit', id] }))
          }} />
      )}
    </div>
  )
}

function Counter({ label, value, onChange, step = 1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="flex items-center gap-2">
        <button type="button" className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 active:bg-slate-200" onClick={() => onChange(Math.max(0, value - step))}><Minus className="h-5 w-5" /></button>
        <input className="input w-16 text-center text-lg font-bold" inputMode="numeric" value={value} onChange={(e) => onChange(Number(e.target.value.replace(/\D/g, '') || 0))} />
        <button type="button" className="flex h-11 w-11 items-center justify-center rounded-xl bg-savo-100 text-savo-700 active:bg-savo-200" onClick={() => onChange(value + step)}><Plus className="h-5 w-5" /></button>
      </div>
    </div>
  )
}

function Chips({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, l]) => (
          <button type="button" key={v} onClick={() => onChange(value === v ? '' : v)} className={clsx('rounded-xl border px-3 py-2 text-sm font-semibold', value === v ? 'border-savo-600 bg-savo-600 text-white' : 'border-slate-300 bg-white text-slate-600')}>{l}</button>
        ))}
      </div>
    </div>
  )
}

function LaneSheet({ lane, unitId, onClose, onSaved }: { lane: any; unitId: number; onClose: () => void; onSaved: () => void }) {
  const existing = lane.properties.observation
  const [f, setF, clear] = useDraft<LaneForm>(`lane-${lane.id}`, existing ? { ...EMPTY, ...existing } : EMPTY)
  const set = (p: Partial<LaneForm>) => setF((x) => ({ ...x, ...p }))
  const [page, setPage] = useState(0)
  useEffect(() => {
    setPage(0)
  }, [lane.id])

  function save(status: 'done' | 'inaccessible') {
    const cu = uuid()
    enqueue('observation', { client_uuid: cu, lane_id: lane.id, work_unit_id: unitId, captured_at: new Date().toISOString(), data: { ...f, status } }, cu)
    clear()
    onSaved()
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 max-h-[78vh] overflow-y-auto rounded-t-3xl bg-white p-4 shadow-[0_-10px_40px_rgba(0,0,0,.15)] md:left-60">
      <div className="mx-auto max-w-xl">
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <div className="text-lg font-bold">{lane.properties.name || `Unnamed ${lane.properties.highway} lane`}</div>
            <div className="text-xs text-slate-500">{Math.round(lane.properties.length_m)} m · {lane.properties.status !== 'pending' ? 'already recorded — saving updates it' : 'draft saves automatically'}</div>
          </div>
          <button className="text-sm font-semibold text-slate-500" onClick={onClose}>Close</button>
        </div>
        <div className="mb-3 grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
          {['Homes', 'Shops', 'Street'].map((t, i) => (
            <button key={t} className={clsx('rounded-lg py-1.5', page === i ? 'bg-white text-savo-700 shadow' : 'text-slate-500')} onClick={() => setPage(i)}>{t}</button>
          ))}
        </div>
        {page === 0 && (
          <div className="space-y-4">
            <Counter label="Households on this lane (approx.)" value={f.households} step={5} onChange={(v) => set({ households: v })} />
            <Chips label="Housing" value={f.housing_type} onChange={(v) => set({ housing_type: v })} options={[['independent', 'Independent houses'], ['apartments', 'Apartments'], ['gated', 'Gated community'], ['mixed', 'Mixed'], ['informal', 'Informal'], ['commercial', 'Mostly commercial']]} />
            <Chips label="Economic class (look & feel)" value={f.sec} onChange={(v) => set({ sec: v })} options={[['A', 'A · affluent'], ['B', 'B · upper-middle'], ['C', 'C · middle'], ['D', 'D · lower']]} />
            <Chips label="Occupancy" value={f.occupancy} onChange={(v) => set({ occupancy: v })} options={[['high', 'Fully lived-in'], ['medium', 'Some vacant'], ['low', 'Mostly vacant']]} />
          </div>
        )}
        {page === 1 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Counter label="Kirana / small grocery" value={f.kiranas} onChange={(v) => set({ kiranas: v })} />
              <Counter label="Supermarkets" value={f.supermarkets} onChange={(v) => set({ supermarkets: v })} />
            </div>
            <div>
              <div className="label">Competitor brands seen</div>
              <div className="flex flex-wrap gap-1.5">
                {BRANDS.map((b) => {
                  const on = f.competitor_brands.includes(b)
                  return <button type="button" key={b} onClick={() => set({ competitor_brands: on ? f.competitor_brands.filter((x) => x !== b) : [...f.competitor_brands, b] })}
                    className={clsx('rounded-xl border px-3 py-2 text-sm font-semibold', on ? 'border-rose-500 bg-rose-50 text-rose-700' : 'border-slate-300 text-slate-600')}>{b}</button>
                })}
              </div>
            </div>
          </div>
        )}
        {page === 2 && (
          <div className="space-y-4">
            <Chips label="People walking by" value={f.footfall} onChange={(v) => set({ footfall: v })} options={[['low', 'Few'], ['medium', 'Moderate'], ['high', 'Busy']]} />
            <Chips label="Vehicle access" value={f.access} onChange={(v) => set({ access: v })} options={[['car', 'Car can enter'], ['two_wheeler', 'Two-wheelers only'], ['walk_only', 'Walk only']]} />
            <textarea className="input min-h-20" placeholder="Notes (landmarks, new construction, anything notable)" value={f.notes} onChange={(e) => set({ notes: e.target.value })} />
          </div>
        )}
        <div className="mt-4 flex gap-2">
          {page > 0 ? <button className="btn-ghost" onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></button>
            : <button className="btn-ghost text-rose-600" onClick={() => save('inaccessible')} title="Gate closed, unsafe, not a real lane…"><Ban className="h-4 w-4" /> Can't access</button>}
          {page < 2 ? <button className="btn-primary flex-1" onClick={() => setPage(page + 1)}>Next <ChevronRight className="h-4 w-4" /></button>
            : <button className="btn-sun flex-1" onClick={() => save('done')}><Check className="h-4 w-4" /> Save lane & next</button>}
        </div>
      </div>
    </div>
  )
}
