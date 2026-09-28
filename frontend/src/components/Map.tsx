// MapLibre wrapper with declarative GeoJSON layers and markers.
import maplibregl, { type LayerSpecification, type Map as MLMap, type MapLayerMouseEvent } from 'maplibre-gl'
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

// OpenFreeMap: free, keyless vector tiles built from OpenStreetMap. Falls back to OSM raster tiles.
const BASEMAPS = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  streets: 'https://tiles.openfreemap.org/styles/liberty',
}

const OSM_RASTER: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

const MapCtx = createContext<MLMap | null>(null)
export const useMap = () => useContext(MapCtx)

export const CHENNAI: [number, number] = [80.23, 13.05]

interface MapViewProps {
  center?: [number, number] // [lng, lat]
  zoom?: number
  className?: string
  basemap?: keyof typeof BASEMAPS
  children?: ReactNode
  onReady?: (m: MLMap) => void
  onClick?: (e: maplibregl.MapMouseEvent) => void
  onMoveEnd?: (m: MLMap) => void
  interactive?: boolean
}

export function MapView({ center = CHENNAI, zoom = 11, className = '', basemap = 'light', children, onReady, onClick, onMoveEnd, interactive = true }: MapViewProps) {
  const el = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MLMap | null>(null)
  const cb = useRef({ onClick, onMoveEnd })
  cb.current = { onClick, onMoveEnd }

  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      style: BASEMAPS[basemap],
      center,
      zoom,
      attributionControl: false,
      interactive,
      dragRotate: false,
      pitchWithRotate: false,
    })
    m.touchZoomRotate.disableRotation()
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'top-left')
    if (interactive) m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    let loaded = false
    m.on('error', (e) => {
      // basemap style unreachable (offline / blocked) -> plain OSM raster so the app keeps working
      if (!loaded && String((e as any)?.error?.message || '').match(/style|Failed to fetch|NetworkError/i)) m.setStyle(OSM_RASTER)
    })
    m.on('load', () => {
      loaded = true
      setMap(m)
      onReady?.(m)
    })
    m.on('click', (e) => cb.current.onClick?.(e))
    m.on('moveend', () => cb.current.onMoveEnd?.(m))
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current!)
    return () => {
      ro.disconnect()
      m.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className={`relative ${className}`}>
      {/* inline style: maplibre's unlayered CSS would override Tailwind's `absolute` */}
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      {map && <MapCtx.Provider value={map}>{children}</MapCtx.Provider>}
    </div>
  )
}

type LayerDef = Omit<LayerSpecification, 'id' | 'source'> & { id?: string; filter?: any }

interface GeoLayerProps {
  id: string
  data: GeoJSON.FeatureCollection | GeoJSON.Feature | null | undefined
  layers: LayerDef[]
  onClick?: (f: maplibregl.MapGeoJSONFeature, e: MapLayerMouseEvent) => void
  beforeId?: string
}

/** Adds/updates a GeoJSON source with one or more styled layers. */
export function GeoLayer({ id, data, layers, onClick }: GeoLayerProps) {
  const map = useMap()
  const clickRef = useRef(onClick)
  clickRef.current = onClick
  const layerIds = layers.map((l, i) => l.id || `${id}-${i}`)

  useEffect(() => {
    if (!map) return
    const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
    map.addSource(id, { type: 'geojson', data: (data as any) || empty, promoteId: 'id' } as any)
    layers.forEach((l, i) => map.addLayer({ ...(l as any), id: layerIds[i], source: id }))
    const handlers = layerIds.map((lid) => {
      const click = (e: MapLayerMouseEvent) => e.features?.[0] && clickRef.current?.(e.features[0], e)
      const enter = () => clickRef.current && (map.getCanvas().style.cursor = 'pointer')
      const leave = () => (map.getCanvas().style.cursor = '')
      map.on('click', lid, click)
      map.on('mouseenter', lid, enter)
      map.on('mouseleave', lid, leave)
      return { lid, click, enter, leave }
    })
    return () => {
      if (!map.getStyle()) return
      handlers.forEach(({ lid, click, enter, leave }) => {
        map.off('click', lid, click)
        map.off('mouseenter', lid, enter)
        map.off('mouseleave', lid, leave)
      })
      layerIds.forEach((lid) => map.getLayer(lid) && map.removeLayer(lid))
      map.getSource(id) && map.removeSource(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, id])

  useEffect(() => {
    const src = map?.getSource(id) as maplibregl.GeoJSONSource | undefined
    src?.setData((data as any) || { type: 'FeatureCollection', features: [] })
  }, [map, id, data])

  // allow paint updates (e.g. highlighting) without re-creating layers
  const paintKey = JSON.stringify(layers.map((l) => [(l as any).paint, (l as any).filter]))
  useEffect(() => {
    if (!map) return
    layers.forEach((l, i) => {
      const lid = layerIds[i]
      if (!map.getLayer(lid)) return
      Object.entries((l as any).paint || {}).forEach(([k, v]) => map.setPaintProperty(lid, k, v))
      if ((l as any).filter) map.setFilter(lid, (l as any).filter)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, paintKey])
  return null
}

interface MarkerProps {
  lng: number
  lat: number
  children?: ReactNode
  onClick?: () => void
  draggable?: boolean
  onDragEnd?: (lng: number, lat: number) => void
  popup?: ReactNode
  anchor?: maplibregl.PositionAnchor
}

/** A React-rendered HTML marker. */
export function Marker({ lng, lat, children, onClick, draggable, onDragEnd, popup, anchor = 'center' }: MarkerProps) {
  const map = useMap()
  const [el] = useState(() => document.createElement('div'))
  const [popEl] = useState(() => document.createElement('div'))
  const mk = useRef<maplibregl.Marker>()
  const handlers = useRef({ onClick, onDragEnd })
  handlers.current = { onClick, onDragEnd }

  useEffect(() => {
    if (!map) return
    const m = new maplibregl.Marker({ element: el, draggable, anchor }).setLngLat([lng, lat]).addTo(map)
    if (popup) m.setPopup(new maplibregl.Popup({ offset: 14, closeButton: false, maxWidth: '280px' }).setDOMContent(popEl))
    el.onclick = (ev) => {
      if (handlers.current.onClick) {
        ev.stopPropagation()
        handlers.current.onClick()
      }
    }
    m.on('dragend', () => {
      const p = m.getLngLat()
      handlers.current.onDragEnd?.(p.lng, p.lat)
    })
    mk.current = m
    return () => {
      m.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  useEffect(() => {
    mk.current?.setLngLat([lng, lat])
  }, [lng, lat])

  return (
    <>
      {createPortal(children ?? <div className="h-4 w-4 rounded-full border-2 border-white bg-savo-600 shadow" />, el)}
      {popup && createPortal(popup, popEl)}
    </>
  )
}

/** Fit the map to some coordinates once they are known. */
export function FitBounds({ points, padding = 50, maxZoom = 15 }: { points: [number, number][]; padding?: number; maxZoom?: number }) {
  const map = useMap()
  const key = points.length ? JSON.stringify([points[0], points[points.length - 1], points.length]) : ''
  useEffect(() => {
    if (!map || !points.length) return
    const b = new maplibregl.LngLatBounds(points[0], points[0])
    points.forEach((p) => b.extend(p))
    map.fitBounds(b, { padding, maxZoom, duration: 600 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key])
  return null
}

export function geomPoints(g: any): [number, number][] {
  if (!g) return []
  if (g.type === 'FeatureCollection') return g.features.flatMap((f: any) => geomPoints(f.geometry))
  if (g.type === 'Feature') return geomPoints(g.geometry)
  const flat = (c: any): [number, number][] => (typeof c[0] === 'number' ? [c as [number, number]] : c.flatMap(flat))
  return g.coordinates ? flat(g.coordinates) : []
}

export function StoreMarker({ name }: { name: string }) {
  return (
    <div title={`Savomart ${name}`} className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-sun shadow-md ring-2 ring-savo-600">
      <span className="text-[10px] font-black text-savo-700">S</span>
    </div>
  )
}
