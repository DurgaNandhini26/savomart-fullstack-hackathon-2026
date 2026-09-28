import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Camera, Check, ChevronLeft, ChevronRight, CloudOff, Crosshair, ImagePlus, LocateFixed, MapPin, Trash2, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { FitBounds, MapView, Marker } from '../components/Map'
import { EMPTY_FORM, PropertyFields, formToPayload, type PropertyForm } from '../components/PropertyFields'
import { ErrorBox, Spinner } from '../components/ui'
import { ApiError, api, errorText, get, post } from '../lib/api'
import { compressImage, enqueue, useDraft, useOnline } from '../lib/offline'
import { uuid } from '../lib/format'

interface Draft {
  client_uuid: string
  mission_id: number | null
  lat: number | null
  lng: number | null
  accuracy: number | null
  device_lat: number | null
  device_lng: number | null
  address: string
  locality: string
  pincode: string
  form: PropertyForm
  photos: string[]
}

const blank = (): Draft => ({ client_uuid: uuid(), mission_id: null, lat: null, lng: null, accuracy: null, device_lat: null, device_lng: null, address: '', locality: '', pincode: '', form: EMPTY_FORM, photos: [] })
const STEPS = ['Location', 'Details', 'Photos', 'Review']

export default function NewProperty() {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const online = useOnline()
  const [d, setD, clearDraft] = useDraft<Draft>('new-property', blank())
  const [step, setStep] = useState(0)
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsErr, setGpsErr] = useState<string | null>(null)
  const [check, setCheck] = useState<any>(null)
  const [notDup, setNotDup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const set = (p: Partial<Draft>) => setD((x) => ({ ...x, ...p }))
  const missions = useQuery({ queryKey: ['missions'], queryFn: () => get('/api/missions') })

  useEffect(() => {
    const m = sp.get('mission')
    if (m && !d.mission_id) set({ mission_id: Number(m) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const mission = missions.data?.find((m: any) => m.id === d.mission_id)

  function locate() {
    if (!navigator.geolocation) return setGpsErr('This device has no GPS / location support.')
    setGpsBusy(true)
    setGpsErr(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords
        set({ lat: latitude, lng: longitude, device_lat: latitude, device_lng: longitude, accuracy })
        setGpsBusy(false)
        reverse(latitude, longitude)
      },
      (e) => { setGpsErr(e.code === 1 ? 'Location permission denied — drop the pin on the map instead.' : 'Could not get a GPS fix. Move outdoors or drop the pin manually.'); setGpsBusy(false) },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    )
  }

  async function reverse(lat: number, lng: number) {
    try {
      const r = await get(`/api/geo/reverse?lat=${lat}&lng=${lng}`)
      set({ address: r.address || '', locality: r.locality || '', pincode: r.pincode && /^\d{6}$/.test(r.pincode) ? r.pincode : '' })
      if (!r.in_region) setGpsErr('This location is outside the Chennai region.')
    } catch {
      /* offline: address can be filled later */
    }
  }

  async function addPhotos(files: FileList | null) {
    if (!files) return
    const out: string[] = []
    for (const f of Array.from(files).slice(0, 8)) out.push(await compressImage(f))
    set({ photos: [...d.photos, ...out].slice(0, 8) })
  }

  const payload = () => ({
    ...formToPayload(d.form), client_uuid: d.client_uuid, mission_id: d.mission_id, lat: d.lat, lng: d.lng,
    gps_accuracy_m: d.accuracy, device_lat: d.device_lat, device_lng: d.device_lng,
    address: d.address || null, locality: d.locality || null, pincode: d.pincode || null, confirm_not_duplicate: notDup,
  })

  async function review() {
    setStep(3)
    setCheck(null)
    if (!online) return
    try {
      setCheck(await post('/api/properties/check', payload()))
    } catch (e) {
      setErr(errorText(e))
    }
  }

  async function submit() {
    setBusy(true)
    setErr(null)
    const body = payload()
    if (!online) {
      enqueue('property', body, d.client_uuid, d.photos)
      clearDraft()
      setD(blank())
      setBusy(false)
      nav('/my-properties?queued=1')
      return
    }
    try {
      const r = await post('/api/properties', body)
      for (const dataUrl of d.photos) {
        const blob = await (await fetch(dataUrl)).blob()
        const fd = new FormData()
        fd.append('file', blob, 'photo.jpg')
        await api(`/api/properties/${r.property.id}/photos`, { method: 'POST', body: fd })
      }
      clearDraft()
      setD(blank())
      nav(`/properties/${r.property.id}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setCheck((c: any) => ({ ...(c || {}), duplicates: e.detail.duplicates }))
        setErr('Possible duplicate — check the list below.')
      } else if (e instanceof ApiError && e.status === 0) {
        enqueue('property', body, d.client_uuid, d.photos)
        clearDraft()
        setD(blank())
        nav('/my-properties?queued=1')
      } else setErr(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const locOk = d.lat != null && d.lng != null
  const detailsOk = d.form.title.trim().length >= 3
  const center: [number, number] = d.lng != null ? [d.lng, d.lat!] : mission ? [mission.lng, mission.lat] : [80.23, 13.05]

  return (
    <div className="mx-auto max-w-2xl p-4 pb-28 sm:p-6">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="h-page">Add property</h1>
        {!online && <span className="chip bg-slate-800 text-white"><CloudOff className="h-3.5 w-3.5" /> Offline — will sync later</span>}
      </div>
      {/* stepper */}
      <div className="mb-4 flex gap-1">
        {STEPS.map((s, i) => (
          <button key={s} onClick={() => i <= step && setStep(i)} className="flex-1">
            <div className={clsx('h-1.5 rounded-full', i <= step ? 'bg-savo-600' : 'bg-slate-200')} />
            <div className={clsx('mt-1 text-[11px] font-semibold', i === step ? 'text-savo-700' : 'text-slate-400')}>{s}</div>
          </button>
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-3">
          <div>
            <label className="label">Mission</label>
            <select className="input" value={d.mission_id ?? ''} onChange={(e) => set({ mission_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Found on my own (no mission)</option>
              {missions.data?.filter((m: any) => m.status !== 'done').map((m: any) => <option key={m.id} value={m.id}>{m.title}</option>)}
            </select>
          </div>
          <button className="btn-sun w-full py-3 text-base" onClick={locate} disabled={gpsBusy}>
            {gpsBusy ? <Spinner className="h-5 w-5" /> : <LocateFixed className="h-5 w-5" />} I'm standing at the property — use GPS
          </button>
          {gpsErr && <ErrorBox error={gpsErr} />}
          <div className="relative h-80 overflow-hidden rounded-2xl border border-slate-200">
            <MapView className="h-full" center={center} zoom={d.lat ? 17 : 13} basemap="streets"
              onClick={(e) => { set({ lat: e.lngLat.lat, lng: e.lngLat.lng }); reverse(e.lngLat.lat, e.lngLat.lng) }}>
              {locOk && (
                <Marker lng={d.lng!} lat={d.lat!} draggable anchor="bottom" onDragEnd={(lng, lat) => { set({ lat, lng }); reverse(lat, lng) }}>
                  <MapPin className="h-10 w-10 fill-savo-600 text-white drop-shadow-lg" />
                </Marker>
              )}
              {!locOk && mission && <FitBounds points={[[mission.lng, mission.lat]]} maxZoom={16} />}
              {d.device_lat != null && <Marker lng={d.device_lng!} lat={d.device_lat!}><div className="h-4 w-4 rounded-full border-2 border-white bg-sky-500 shadow" /></Marker>}
            </MapView>
            <div className="pointer-events-none absolute left-2 top-2 rounded-lg bg-white/95 px-2 py-1 text-xs text-slate-600 shadow">
              <Crosshair className="mr-1 inline h-3 w-3" /> Tap the map or drag the pin onto the entrance
            </div>
          </div>
          {locOk && (
            <div className="rounded-xl bg-slate-50 p-3 text-sm">
              <div className="font-semibold">{d.locality || 'Locating…'} {d.pincode}</div>
              <div className="text-xs text-slate-500">{d.address || `${d.lat!.toFixed(5)}, ${d.lng!.toFixed(5)}`}</div>
              {d.accuracy != null && <div className={clsx('mt-1 text-xs', d.accuracy > 100 ? 'text-amber-700' : 'text-emerald-700')}>GPS accuracy ±{Math.round(d.accuracy)} m</div>}
            </div>
          )}
        </div>
      )}

      {step === 1 && <PropertyFields f={d.form} set={(x) => set({ form: { ...d.form, ...x } })} />}

      {step === 2 && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">Front, inside, street view both ways, and the road. Photos are shrunk on your phone before upload.</p>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={(e) => { addPhotos(e.target.files); e.target.value = '' }} />
          <div className="grid grid-cols-3 gap-2">
            {d.photos.map((p, i) => (
              <div key={i} className="relative aspect-square overflow-hidden rounded-xl">
                <img src={p} className="h-full w-full object-cover" />
                <button className="absolute right-1 top-1 rounded-full bg-white/90 p-1" onClick={() => set({ photos: d.photos.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4 text-rose-600" /></button>
              </div>
            ))}
            {d.photos.length < 8 && (
              <button className="flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-savo-300 text-savo-600" onClick={() => fileRef.current?.click()}>
                <Camera className="h-7 w-7" /><span className="text-xs font-semibold">Take photo</span>
              </button>
            )}
          </div>
          {!d.photos.length && <div className="flex items-center gap-2 text-xs text-amber-700"><ImagePlus className="h-4 w-4" /> At least one photo helps the manager decide.</div>}
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3">
          <div className="card p-4 text-sm">
            <div className="font-bold">{d.form.title || 'Untitled'}</div>
            <div className="text-slate-500">{d.locality} · {d.form.carpet_area_sqft || '?'} sqft · ₹{d.form.rent_monthly || '?'} / month · {d.photos.length} photos</div>
          </div>
          {online && !check && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner className="h-4 w-4" /> Checking for duplicates & data issues…</div>}
          {check?.warnings?.length > 0 && (
            <div className="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <div className="font-semibold">Please double-check</div>
              {check.warnings.map((w: string) => <div key={w} className="flex gap-1.5"><TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />{w}</div>)}
              <div className="text-xs">You can still submit — these are flagged to your manager.</div>
            </div>
          )}
          {check?.duplicates?.length > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
              <div className="font-semibold text-rose-800">Already onboarded nearby?</div>
              {check.duplicates.map((x: any) => (
                <div key={x.id} className="mt-1 flex items-center gap-2">
                  {x.photo && <img src={x.photo} className="h-10 w-10 rounded object-cover" />}
                  <div><b>{x.code}</b> {x.title} · {x.distance_m} m away · by {x.submitted_by?.name}</div>
                </div>
              ))}
              <label className="mt-2 flex items-center gap-2 font-semibold"><input type="checkbox" className="h-4 w-4 accent-savo-600" checked={notDup} onChange={(e) => setNotDup(e.target.checked)} /> It's a different unit — submit anyway</label>
            </div>
          )}
          {check && !check.warnings?.length && !check.duplicates?.length && <div className="flex items-center gap-2 text-sm text-emerald-700"><Check className="h-4 w-4" /> No duplicates or data issues found.</div>}
          {!online && <div className="rounded-xl bg-slate-100 p-3 text-sm">You're offline. The property and photos will be saved on this phone and uploaded automatically when you're back online.</div>}
          {err && <ErrorBox error={err} />}
        </div>
      )}

      {/* sticky footer */}
      <div className="fixed inset-x-0 bottom-16 z-20 border-t border-slate-200 bg-white/95 p-3 backdrop-blur md:bottom-0 md:left-60">
        <div className="mx-auto flex max-w-2xl gap-2">
          {step > 0 && <button className="btn-ghost" onClick={() => setStep(step - 1)}><ChevronLeft className="h-4 w-4" /> Back</button>}
          {step === 0 && <button className="btn-primary flex-1" disabled={!locOk} onClick={() => setStep(1)}>Next: details <ChevronRight className="h-4 w-4" /></button>}
          {step === 1 && <button className="btn-primary flex-1" disabled={!detailsOk} onClick={() => setStep(2)}>{detailsOk ? 'Next: photos' : 'Add a name / landmark'} <ChevronRight className="h-4 w-4" /></button>}
          {step === 2 && <button className="btn-primary flex-1" onClick={review}>Review <ChevronRight className="h-4 w-4" /></button>}
          {step === 3 && (
            <button className="btn-sun flex-1" disabled={busy || (check?.duplicates?.length > 0 && !notDup)} onClick={submit}>
              {busy ? <Spinner className="h-4 w-4" /> : <Check className="h-4 w-4" />} {online ? 'Submit property' : 'Save offline'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
