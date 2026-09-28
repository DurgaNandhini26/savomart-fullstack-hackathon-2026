// Bonus: one-click decision pack — a print-optimised page ("Save as PDF" from the print dialog).
import { useQuery } from '@tanstack/react-query'
import { Printer } from 'lucide-react'
import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Logo } from '../components/Layout'
import { MapView, Marker, StoreMarker } from '../components/Map'
import { PageLoader, RecBadge, ScoreRing, StageBadge } from '../components/ui'
import { get } from '../lib/api'
import { dateTime, fmt1, fmtINR, fmtInt, REC_LABEL, STAGE_LABEL } from '../lib/format'
import { GroundTruth } from './ReportDetail'

export default function DecisionPack() {
  const { id } = useParams()
  const { data: p, isLoading } = useQuery({ queryKey: ['property', id], queryFn: () => get(`/api/properties/${id}`) })
  const stores = useQuery({ queryKey: ['stores'], queryFn: () => get('/api/geo/stores') })
  const study = useQuery({
    queryKey: ['study', p?.evaluation?.catchment_study_id],
    queryFn: () => get(`/api/studies/${p.evaluation.catchment_study_id}`),
    enabled: !!p?.evaluation?.catchment_study_id,
  })
  useEffect(() => { document.title = p ? `Decision pack ${p.code}` : 'Decision pack' }, [p])
  if (isLoading) return <PageLoader />
  const e = p.evaluation
  const f = e?.facts || {}

  return (
    <div className="mx-auto max-w-4xl bg-white p-6 text-sm print:p-0">
      <div className="no-print mb-4 flex justify-end"><button className="btn-primary" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print / Save as PDF</button></div>
      <header className="flex items-center justify-between border-b-4 border-savo-600 pb-3">
        <Logo />
        <div className="text-right text-xs text-slate-500">Decision pack · {p.code}<br />Generated {dateTime(new Date().toISOString())}</div>
      </header>
      <div className="mt-4 flex items-start gap-4">
        <ScoreRing score={e?.score} size={90} />
        <div className="flex-1">
          <h1 className="text-2xl font-extrabold">{p.title}</h1>
          <div className="text-slate-500">{p.address || p.locality} {p.pincode}</div>
          <div className="mt-1 flex gap-2"><StageBadge stage={p.stage} /><RecBadge rec={e?.recommendation} /></div>
          <p className="mt-2 font-semibold">{e?.narrative?.headline}</p>
          <p className="text-slate-600">{e?.narrative?.summary}</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-4 gap-2">
        {[['Rent / month', fmtINR(p.rent_monthly)], ['Rent / sq ft', f.rent_psf ? `₹${fmt1(f.rent_psf)} (bench. ₹${fmt1(f.rent_benchmark_psf_mock)} mock)` : '—'],
          ['Carpet area', `${fmtInt(p.carpet_area_sqft)} sq ft`], ['Frontage · floor', `${p.frontage_ft ?? '—'} ft · ${p.floor || '—'}`],
          ['Residents ≤ 800 m', fmtInt(f.residents_est)], ['Grocery outlets ≤ 800 m', f.grocery_outlets_mapped], ['Nearest Savomart', `${f.nearest_savomart?.name} · ${fmt1(f.nearest_savomart?.distance_km)} km`],
          ['Lease · deposit', `${p.lease_years ?? '—'} yrs · ${p.deposit_months ?? '—'} mo`]].map(([k, v]) => (
          <div key={k as string} className="rounded-lg bg-slate-50 p-2"><div className="text-[10px] font-semibold uppercase text-slate-500">{k}</div><div className="font-bold">{v}</div></div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <h2 className="mb-1 font-bold text-emerald-700">Strengths</h2>
          <ul className="list-disc space-y-0.5 pl-4">{e?.insights?.map((s: string) => <li key={s}>{s}</li>)}</ul>
        </div>
        <div>
          <h2 className="mb-1 font-bold text-rose-700">Risks</h2>
          <ul className="list-disc space-y-0.5 pl-4">{e?.risks?.length ? e.risks.map((s: string) => <li key={s}>{s}</li>) : <li>None flagged</li>}</ul>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div className="h-64 overflow-hidden rounded-xl border">
          <MapView className="h-full" center={[p.lng, p.lat]} zoom={14} basemap="streets" interactive={false}>
            {stores.data?.map((s: any) => <Marker key={s.code} lng={s.lng} lat={s.lat}><StoreMarker name={s.name} /></Marker>)}
            <Marker lng={p.lng} lat={p.lat}><div className="rounded bg-savo-600 px-1.5 text-xs font-bold text-sun">{p.code}</div></Marker>
          </MapView>
        </div>
        <div>
          <h2 className="mb-1 font-bold">Score breakdown</h2>
          <table className="w-full">
            <tbody>
              {e && Object.values(e.pillars).map((pl: any) => (
                <tr key={pl.label} className="border-t"><td className="py-1">{pl.label}</td><td className="text-right">{Math.round(pl.score)}</td><td className="text-right text-slate-400">× {pl.weight}</td></tr>
              ))}
              <tr className="border-t font-bold"><td className="py-1">Overall</td><td className="text-right">{e?.score}</td><td className="text-right">{REC_LABEL[e?.recommendation]}</td></tr>
            </tbody>
          </table>
          <h2 className="mb-1 mt-3 font-bold">Photos</h2>
          <div className="grid grid-cols-3 gap-1">{p.photos.slice(0, 6).map((ph: any) => <img key={ph.id} src={ph.url} className="aspect-square w-full rounded object-cover" />)}</div>
        </div>
      </div>

      {study.data?.insights && (
        <div className="print-break mt-4">
          <h2 className="mb-2 font-bold">Catchment study {study.data.code} (ground truth)</h2>
          <GroundTruth g={study.data.insights} />
        </div>
      )}

      <div className="mt-4">
        <h2 className="mb-1 font-bold">Decision trail</h2>
        <table className="w-full text-xs">
          <tbody>
            {[...p.events].reverse().map((ev: any) => (
              <tr key={ev.id} className="border-t align-top">
                <td className="whitespace-nowrap py-1 pr-2 text-slate-500">{dateTime(ev.created_at)}</td>
                <td className="py-1 pr-2 font-semibold">{ev.actor?.name || 'System'}</td>
                <td className="py-1 pr-2">{ev.action === 'stage_change' ? `${STAGE_LABEL[ev.from_stage]} → ${STAGE_LABEL[ev.to_stage]}` : ev.action.replace(/_/g, ' ')}</td>
                <td className="py-1">{ev.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="mt-6 border-t pt-2 text-[10px] text-slate-400">
        Evaluation v{e?.version} ({e?.trigger}). Residents are Census-2011-calibrated estimates from OpenStreetMap; rent benchmarks are mock data. Data: © OpenStreetMap contributors, Savomart Stores API.
      </footer>
    </div>
  )
}
