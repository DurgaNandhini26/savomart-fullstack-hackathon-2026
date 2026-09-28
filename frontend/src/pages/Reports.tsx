import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, FileBarChart2, GitCompare, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BandBadge, Empty, ErrorBox, PageLoader, Spinner } from '../components/ui'
import { get } from '../lib/api'
import { dateTime, fmt1, scoreColor } from '../lib/format'

export default function Reports() {
  const nav = useNavigate()
  const [sel, setSel] = useState<number[]>([])
  const { data, isLoading, error } = useQuery({
    queryKey: ['reports'], queryFn: () => get('/api/reports'),
    refetchInterval: (q) => (q.state.data?.some((r: any) => ['queued', 'running'].includes(r.status)) ? 2000 : false),
  })
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]))

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="h-page">Area reports</h1>
          <p className="text-sm text-slate-500">Every analysis is saved with the exact data snapshot it used. Tick up to 4 to compare.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={sel.length < 2} onClick={() => nav(`/compare?ids=${sel.join(',')}`)}>
            <GitCompare className="h-4 w-4" /> Compare {sel.length > 0 && `(${sel.length})`}
          </button>
          <Link to="/explore" className="btn-primary"><Plus className="h-4 w-4" /> New analysis</Link>
        </div>
      </div>
      {isLoading && <PageLoader />}
      {error && <ErrorBox error={error} />}
      {data?.length === 0 && (
        <Empty icon={<FileBarChart2 className="h-10 w-10" />} title="No reports yet">
          Open <Link to="/explore" className="font-semibold text-savo-700">Explore</Link>, pick a pincode, locality or grid cells and run a virtual analysis.
        </Empty>
      )}
      <div className="card divide-y divide-slate-100 overflow-hidden">
        {data?.map((r: any) => (
          <div key={r.id} className={clsx('flex items-center gap-3 px-4 py-3 hover:bg-slate-50', sel.includes(r.id) && 'bg-savo-50')}>
            <input type="checkbox" className="h-4 w-4 accent-savo-600" checked={sel.includes(r.id)} disabled={r.status !== 'completed'} onChange={() => toggle(r.id)} />
            <Link to={`/reports/${r.id}`} className="flex min-w-0 flex-1 items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white" style={{ background: scoreColor(r.score) }}>
                {r.status === 'completed' ? Math.round(r.score) : ['queued', 'running'].includes(r.status) ? <Spinner className="h-5 w-5 text-white" /> : '!'}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">{r.name}</div>
                <div className="text-xs text-slate-500">
                  {r.selection_type === 'cells' ? 'Grid selection' : r.selection_type === 'pincode' ? 'Pincode' : 'Locality'} · {fmt1(r.area_km2)} km² · {dateTime(r.completed_at || r.created_at)} · {r.created_by?.name}
                </div>
              </div>
              <div className="hidden items-center gap-2 sm:flex">
                {r.has_ground_truth && <span className="chip bg-teal-100 text-teal-800"><CheckCircle2 className="h-3 w-3" /> Surveyed</span>}
                {r.status === 'completed' ? <BandBadge band={r.band} score={r.score} /> : <span className="chip bg-slate-100 capitalize text-slate-600">{r.status}</span>}
              </div>
            </Link>
          </div>
        ))}
      </div>
    </div>
  )
}
