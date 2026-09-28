import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Flame, Grid3x3, Hexagon, Info, Layers, Play, Search, Sparkles, Store, X } from 'lucide-react'
import type { Map as MLMap } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FitBounds, GeoLayer, MapView, Marker, StoreMarker, geomPoints } from '../components/Map'
import { ErrorBox, Spinner } from '../components/ui'
import { errorText, get, post } from '../lib/api'
import { fmt1, fmtInt, RAMP, scoreColor } from '../lib/format'

type Mode = 'search' | 'cells'

export default function Explore() {
  const nav = useNavigate()
  const [mode, setMode] = useState<Mode>('search')
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [picked, setPicked] = useState<any | null>(null) // search result
  const [cells, setCells] = useState<string[]>([])
  const [grid, setGrid] = useState<any>(null)
  const [gridMsg, setGridMsg] = useState<string | null>('Zoom in to pick grid cells')
  const [showOpp, setShowOpp] = useState(true)
  const [showStores, setShowStores] = useState(true)
  const [name, setName] = useState('')
  const [panelOpen, setPanelOpen] = useState(true)
  const mapRef = useRef<MLMap | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 250)
    return () => clearTimeout(t)
  }, [q])

  const search = useQuery({ queryKey: ['search', debounced], queryFn: () => get(`/api/geo/search?q=${encodeURIComponent(debounced)}`), enabled: debounced.length >= 2 })
  const stores = useQuery({ queryKey: ['stores'], queryFn: () => get('/api/geo/stores') })
  const opp = useQuery({ queryKey: ['opportunity'], queryFn: () => get('/api/geo/opportunity'), staleTime: 300_000 })
  const top = useQuery({ queryKey: ['opportunity-top'], queryFn: () => get('/api/geo/opportunity/top?limit=8') })
  const preview = useQuery({
    queryKey: ['resolve', picked?.kind, picked?.id],
    queryFn: () => get(`/api/geo/resolve?selection_type=${picked.kind === 'pincode' ? 'pincode' : 'locality'}&value=${encodeURIComponent(picked.kind === 'pincode' ? picked.pincode : String(picked.id))}`),
    enabled: !!picked,
  })

  const run = useMutation({
    mutationFn: () =>
      post('/api/reports',
        mode === 'cells'
          ? { selection_type: 'cells', cells, name: name || undefined }
          : { selection_type: picked.kind === 'pincode' ? 'pincode' : 'locality', value: picked.kind === 'pincode' ? picked.pincode : String(picked.id), name: name || undefined }),
    onSuccess: (r) => nav(`/reports/${r.id}`),
  })

  async function loadGrid(m: MLMap) {
    if (mode !== 'cells') return
    const b = m.getBounds()
    if (m.getZoom() < 12.5) {
      setGridMsg('Zoom in to pick grid cells')
      setGrid(null)
      return
    }
    setGridMsg(null)
    try {
      setGrid(await get(`/api/geo/grid?south=${b.getSouth()}&west=${b.getWest()}&north=${b.getNorth()}&east=${b.getEast()}`))
    } catch (e) {
      setGridMsg(errorText(e))
    }
  }
  useEffect(() => {
    if (mapRef.current) loadGrid(mapRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const gridData = useMemo(() => {
    if (!grid) return null
    const sel = new Set(cells)
    return { ...grid, features: grid.features.map((f: any) => ({ ...f, properties: { ...f.properties, selected: sel.has(f.id) } })) }
  }, [grid, cells])

  const selectedFC = useMemo(() => {
    if (mode === 'cells') return gridData ? { ...gridData, features: gridData.features.filter((f: any) => f.properties.selected) } : null
    return preview.data?.geojson ?? null
  }, [mode, gridData, preview.data])

  const canRun = mode === 'cells' ? cells.length > 0 : !!preview.data
  const areaKm2 = mode === 'cells' ? cells.length * 0.737 : preview.data?.area_km2

  function toggleCell(id: string) {
    setCells((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 60 ? c : [...c, id]))
  }

  function flyTo(lng: number, lat: number, zoom = 14) {
    mapRef.current?.flyTo({ center: [lng, lat], zoom, duration: 900 })
  }

  return (
    <div className="relative h-[calc(100vh-57px-64px)] md:h-[calc(100vh-57px)]">
      <MapView className="h-full w-full" zoom={11} onReady={(m) => (mapRef.current = m)} onMoveEnd={loadGrid}>
        {showOpp && (
          <GeoLayer id="opp" data={opp.data}
            layers={[{ type: 'fill', paint: {
              'fill-color': ['step', ['get', 'score'], RAMP[0], 45, RAMP[1], 55, RAMP[2], 65, RAMP[3], 75, RAMP[4], 85, RAMP[5]],
              'fill-opacity': mode === 'cells' ? 0.25 : 0.55 } } as any]}
            onClick={mode === 'search' ? (f, e) => {
              const p = f.properties as any
              setMode('cells')
              setCells([p.h3])
              flyTo(e.lngLat.lng, e.lngLat.lat, 13.5)
            } : undefined}
          />
        )}
        {mode === 'cells' && (
          <GeoLayer id="grid" data={gridData}
            layers={[
              { type: 'fill', paint: { 'fill-color': ['case', ['get', 'selected'], '#FFF200', '#782B90'], 'fill-opacity': ['case', ['get', 'selected'], 0.55, 0.04] } } as any,
              { type: 'line', paint: { 'line-color': '#782B90', 'line-width': ['case', ['get', 'selected'], 2, 0.6], 'line-opacity': 0.7 } } as any,
            ]}
            onClick={(f) => toggleCell(String(f.id ?? (f.properties as any).h3))}
          />
        )}
        {mode === 'search' && selectedFC && (
          <>
            <GeoLayer id="selection" data={selectedFC}
              layers={[
                { type: 'fill', paint: { 'fill-color': '#FFF200', 'fill-opacity': 0.35 } } as any,
                { type: 'line', paint: { 'line-color': '#782B90', 'line-width': 2 } } as any,
              ]} />
            <FitBounds points={geomPoints(selectedFC)} padding={80} maxZoom={14} />
          </>
        )}
        {showStores && stores.data?.map((s: any) => (
          <Marker key={s.code} lng={s.lng} lat={s.lat} popup={<div><b>Savomart {s.name}</b><div className="text-xs text-slate-500">{s.address}</div></div>}>
            <StoreMarker name={s.name} />
          </Marker>
        ))}
      </MapView>

      {/* legend + layer toggles */}
      <div className="absolute bottom-3 right-3 z-10 hidden rounded-xl bg-white/95 p-3 text-xs shadow-lg sm:block">
        <div className="mb-1.5 flex items-center gap-1 font-semibold text-slate-700"><Layers className="h-3.5 w-3.5" /> Layers</div>
        <label className="flex items-center gap-2"><input type="checkbox" checked={showOpp} onChange={(e) => setShowOpp(e.target.checked)} /> Opportunity score</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={showStores} onChange={(e) => setShowStores(e.target.checked)} /> Savomart stores</label>
        {showOpp && (
          <div className="mt-2">
            <div className="flex">{RAMP.map((c) => <div key={c} className="h-2 w-6" style={{ background: c }} />)}</div>
            <div className="flex justify-between text-[10px] text-slate-500"><span>&lt;45</span><span>fit score</span><span>85+</span></div>
          </div>
        )}
      </div>

      {/* control panel */}
      <div className={clsx('absolute left-3 right-3 top-3 z-10 sm:right-auto sm:w-[380px]', !panelOpen && 'sm:w-auto')}>
        <div className="card overflow-hidden shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <div className="text-sm font-bold">Area intelligence</div>
              <div className="text-xs text-slate-500">Pick an area of Chennai to analyse</div>
            </div>
            <button className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" onClick={() => setPanelOpen(!panelOpen)} aria-label="Toggle panel">
              {panelOpen ? <X className="h-4 w-4" /> : <Search className="h-4 w-4" />}
            </button>
          </div>
          {panelOpen && (
            <div className="max-h-[42vh] space-y-3 overflow-y-auto p-4 sm:max-h-[calc(100vh-220px)]">
              <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1 text-sm font-semibold">
                <button className={clsx('flex items-center justify-center gap-1.5 rounded-lg py-1.5', mode === 'search' ? 'bg-white shadow text-savo-700' : 'text-slate-500')} onClick={() => setMode('search')}>
                  <Search className="h-4 w-4" /> Pincode / locality
                </button>
                <button className={clsx('flex items-center justify-center gap-1.5 rounded-lg py-1.5', mode === 'cells' ? 'bg-white shadow text-savo-700' : 'text-slate-500')} onClick={() => setMode('cells')}>
                  <Grid3x3 className="h-4 w-4" /> Grid cells
                </button>
              </div>

              {mode === 'search' ? (
                <div className="relative">
                  <input className="input pl-9" placeholder="e.g. 600042, Velachery, T Nagar…" value={q}
                    onChange={(e) => { setQ(e.target.value); setPicked(null) }} />
                  <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                  {!picked && debounced.length >= 2 && (
                    <div className="mt-1 max-h-60 overflow-y-auto rounded-xl border border-slate-200">
                      {search.isFetching && <div className="p-3"><Spinner /></div>}
                      {search.data?.length === 0 && <div className="p-3 text-sm text-slate-500">No match in Chennai.</div>}
                      {search.data?.map((r: any) => (
                        <button key={r.id} className="flex w-full items-center justify-between border-b border-slate-100 px-3 py-2 text-left text-sm hover:bg-savo-50"
                          onClick={() => { setPicked(r); setQ(r.name) }}>
                          <span className="font-medium">{r.name}</span>
                          <span className="chip bg-slate-100 text-slate-500">{r.kind === 'pincode' ? 'PIN' : r.place_type}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {preview.isFetching && <div className="mt-2 flex items-center gap-2 text-sm text-slate-500"><Spinner className="h-4 w-4" /> Mapping area…</div>}
                  {preview.error && <div className="mt-2"><ErrorBox error={preview.error} /></div>}
                  {preview.data && (
                    <div className="mt-2 rounded-xl bg-savo-50 p-3 text-sm">
                      <div className="font-semibold">{preview.data.name}</div>
                      <div className="text-xs text-slate-600">{preview.data.cells.length} grid cells · {fmt1(preview.data.area_km2)} km²</div>
                      <div className="mt-1 flex items-start gap-1 text-[11px] text-slate-500">
                        <Info className="mt-0.5 h-3 w-3 shrink-0" /> Boundaries approximated as the grid cells nearest to this {picked?.kind === 'pincode' ? 'pincode' : 'locality'}'s centre.
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-semibold"><Hexagon className="h-4 w-4 text-savo-600" /> {cells.length} cells selected</span>
                    {cells.length > 0 && <button className="text-xs font-semibold text-savo-700" onClick={() => setCells([])}>Clear</button>}
                  </div>
                  <div className="text-xs text-slate-500">Tap hexagons (~0.74 km² each) to build an area. Max 60.</div>
                  {gridMsg && <div className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{gridMsg}</div>}
                </div>
              )}

              {canRun && (
                <div className="space-y-2 border-t border-slate-100 pt-3">
                  <input className="input" placeholder="Report name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
                  <button className="btn-primary w-full" disabled={run.isPending} onClick={() => run.mutate()}>
                    {run.isPending ? <Spinner className="h-4 w-4 text-white" /> : <Play className="h-4 w-4" />}
                    Run virtual analysis · {fmt1(areaKm2)} km²
                  </button>
                  {run.error && <ErrorBox error={errorText(run.error)} />}
                </div>
              )}

              <div className="border-t border-slate-100 pt-3">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
                  <Flame className="h-3.5 w-3.5 text-savo-600" /> Top un-scouted pockets
                </div>
                {top.isLoading && <Spinner />}
                <div className="space-y-1">
                  {top.data?.map((t: any) => (
                    <button key={t.h3} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-savo-50"
                      onClick={() => { setMode('cells'); setCells([t.h3]); flyTo(t.lng, t.lat, 13.6) }}>
                      <span className="w-9 rounded-md py-0.5 text-center text-xs font-bold text-white" style={{ background: scoreColor(t.score) }}>{Math.round(t.score)}</span>
                      <span className="flex-1 truncate font-medium">{t.locality}</span>
                      <span className="text-xs text-slate-400">{fmtInt(t.population / 1000)}k ppl · {fmt1(t.nearest_store_km)} km</span>
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex items-start gap-1 text-[11px] text-slate-400">
                  <Sparkles className="mt-0.5 h-3 w-3 shrink-0" /> Every populated ~1.5 km neighbourhood in Chennai is pre-scored with the same model; "un-scouted" = no report or property there yet.
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Store className="h-3 w-3" /> {stores.data?.length ?? '…'} operational Savomart stores in Chennai (live API)</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
