import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { BandBadge, ErrorBox, PageLoader, ScoreRing, Section } from '../components/ui'
import { get } from '../lib/api'
import { dateTime, fmt1, fmtInt, scoreColor } from '../lib/format'

const COLORS = ['#782B90', '#E6007E', '#0091D5', '#F39200']

export default function Compare() {
  const [sp] = useSearchParams()
  const ids = sp.get('ids') || ''
  const { data, isLoading, error } = useQuery({ queryKey: ['compare', ids], queryFn: () => get(`/api/reports-compare?ids=${ids}`), enabled: !!ids })
  const all = useQuery({ queryKey: ['reports'], queryFn: () => get('/api/reports') })

  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const reports = (data || []).filter((r: any) => r.status === 'completed')
  const pillarKeys = reports[0] ? Object.keys(reports[0].pillars) : []
  const radar = pillarKeys.map((k) => ({ pillar: reports[0].pillars[k].label, ...Object.fromEntries(reports.map((r: any) => [r.name, Math.round(r.pillars[k].score)])) }))
  const idsArr = ids.split(',').filter(Boolean)

  const rows: [string, (r: any) => any][] = [
    ['Residents (est.)', (r) => fmtInt(r.profile.people.population)],
    ['Residents / km²', (r) => fmtInt(r.profile.people.density)],
    ['Area', (r) => `${fmt1(r.area_km2)} km²`],
    ['Grocery outlets (OSM)', (r) => r.profile.competition.supermarkets + r.profile.competition.grocery + r.profile.competition.fresh_food],
    ['Supermarkets (OSM)', (r) => r.profile.competition.supermarkets],
    ['Residents / outlet', (r) => fmtInt(r.profile.competition.people_per_outlet)],
    ['Schools · clinics · transit', (r) => `${r.profile.amenities.schools} · ${r.profile.amenities.healthcare} · ${r.profile.amenities.transit}`],
    ['Nearest Savomart', (r) => `${r.profile.savomart.nearest[0]?.name} (${fmt1(r.profile.savomart.nearest[0]?.distance_km)} km)`],
    ['Top hotspot', (r) => r.hotspots?.[0]?.label || '—'],
    ['Confidence', (r) => r.confidence],
    ['Generated', (r) => dateTime(r.completed_at)],
  ]

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 sm:p-6">
      <Link to="/reports" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-700"><ArrowLeft className="h-4 w-4" /> Reports</Link>
      <h1 className="h-page">Compare areas</h1>
      <div className="flex flex-wrap gap-2 text-sm">
        <span className="text-slate-500">Add:</span>
        {all.data?.filter((r: any) => r.status === 'completed' && !idsArr.includes(String(r.id))).slice(0, 8).map((r: any) => (
          <Link key={r.id} to={`/compare?ids=${[...idsArr, r.id].slice(-4).join(',')}`} className="chip bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-savo-400">+ {r.name}</Link>
        ))}
      </div>
      {reports.length < 1 ? <ErrorBox error="Pick at least one completed report." /> : (
        <>
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${reports.length}, minmax(0, 1fr))` }}>
            {reports.map((r: any, i: number) => (
              <Link key={r.id} to={`/reports/${r.id}`} className="card flex items-center gap-3 p-4" style={{ borderTop: `4px solid ${COLORS[i]}` }}>
                <ScoreRing score={r.score} size={64} />
                <div className="min-w-0">
                  <div className="truncate font-bold">{r.name}</div>
                  <BandBadge band={r.band} score={r.score} />
                </div>
              </Link>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Pillar profile">
              <div className="h-80">
                <ResponsiveContainer>
                  <RadarChart data={radar} outerRadius="72%">
                    <PolarGrid />
                    <PolarAngleAxis dataKey="pillar" tick={{ fontSize: 11 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    {reports.map((r: any, i: number) => <Radar key={r.id} name={r.name} dataKey={r.name} stroke={COLORS[i]} fill={COLORS[i]} fillOpacity={0.12} strokeWidth={2} />)}
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </Section>
            <Section title="Side by side">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {pillarKeys.map((k) => (
                      <tr key={k} className="border-t border-slate-100">
                        <td className="py-1.5 pr-2 text-slate-500">{reports[0].pillars[k].label}</td>
                        {reports.map((r: any) => <td key={r.id} className="py-1.5 text-right font-bold tabular-nums" style={{ color: scoreColor(r.pillars[k].score) }}>{Math.round(r.pillars[k].score)}</td>)}
                      </tr>
                    ))}
                    {rows.map(([label, fn]) => (
                      <tr key={label} className="border-t border-slate-100">
                        <td className="py-1.5 pr-2 text-slate-500">{label}</td>
                        {reports.map((r: any) => <td key={r.id} className="py-1.5 text-right tabular-nums">{fn(r)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>
        </>
      )}
    </div>
  )
}
