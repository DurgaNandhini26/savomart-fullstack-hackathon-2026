import { useQuery } from '@tanstack/react-query'
import { Phone } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorBox, PageLoader } from '../components/ui'
import { get } from '../lib/api'

export default function Team() {
  const { data, isLoading, error } = useQuery({ queryKey: ['team'], queryFn: () => get('/api/team'), refetchInterval: 15000 })
  if (isLoading) return <PageLoader />
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const max = Math.max(1, ...data.map((t: any) => t.days_left))
  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="h-page">Survey team</h1>
        <p className="text-sm text-slate-500">Remaining workload per surveyor (at ~4 lane-km per day) — assign new units to whoever has the least.</p>
      </div>
      <div className="space-y-2">
        {data.map((t: any) => (
          <div key={t.user.id} className="card p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-savo-100 font-bold text-savo-700">{t.user.name[0]}</div>
              <div className="flex-1">
                <div className="font-semibold">{t.user.name}</div>
                <div className="text-xs text-slate-500">{t.active_units.length} active units · {t.done_units} completed · {t.lanes_left} lanes / {t.km_left} km left</div>
              </div>
              {t.user.phone && <a href={`tel:${t.user.phone.replace(/\s/g, '')}`} className="rounded-xl bg-slate-100 p-2"><Phone className="h-4 w-4" /></a>}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-savo-600" style={{ width: `${(t.days_left / max) * 100}%` }} /></div>
              <span className="w-20 text-right text-xs font-semibold">{t.days_left} days</span>
            </div>
            {t.active_units.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {t.active_units.map((u: any) => <Link key={u.id} to={`/survey/${u.id}`} className="chip bg-slate-100 text-slate-600">{u.study} · {u.name}</Link>)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
