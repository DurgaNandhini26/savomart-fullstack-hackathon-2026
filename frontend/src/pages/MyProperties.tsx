import { useQuery } from '@tanstack/react-query'
import { CloudUpload, PlusCircle, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { Empty, ErrorBox, PageLoader, RecBadge, StageBadge } from '../components/ui'
import { get } from '../lib/api'
import { ago, fmtINR, scoreColor } from '../lib/format'
import { discard, flush, useOutbox } from '../lib/offline'

export default function MyProperties() {
  const [sp] = useSearchParams()
  const outbox = useOutbox().filter((i) => i.kind === 'property')
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['properties', 'mine'], queryFn: () => get('/api/properties?mine=true') })

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <h1 className="h-page">My properties</h1>
        <Link to="/properties/new" className="btn-primary"><PlusCircle className="h-4 w-4" /> Add</Link>
      </div>
      {sp.get('queued') && outbox.length > 0 && <div className="rounded-xl bg-slate-800 p-3 text-sm text-white">Saved on this phone. It'll upload automatically when you're online.</div>}
      {outbox.map((o) => (
        <div key={o.id} className="card flex items-center gap-3 border-dashed p-3">
          <CloudUpload className="h-5 w-5 text-amber-600" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-semibold">{o.payload.title}</div>
            <div className="text-xs text-slate-500">Waiting to upload · {o.photos?.length || 0} photos {o.error && <span className="text-rose-600">· {o.error}</span>}</div>
          </div>
          <button className="btn-ghost py-1.5" onClick={async () => { await flush(); refetch() }}>Sync</button>
          <button className="p-2 text-slate-400" title="Discard" onClick={() => confirm('Discard this unsent property?') && discard(o.id)}><Trash2 className="h-4 w-4" /></button>
        </div>
      ))}
      {isLoading && <PageLoader />}
      {error && <ErrorBox error={error} />}
      {data?.length === 0 && !outbox.length && <Empty title="Nothing onboarded yet">Tap “Add” when you find a vacant property.</Empty>}
      <div className="space-y-2">
        {data?.map((p: any) => (
          <Link key={p.id} to={`/properties/${p.id}`} className="card flex items-center gap-3 p-3">
            {p.photo ? <img src={p.photo} className="h-14 w-14 rounded-xl object-cover" /> : <div className="h-14 w-14 rounded-xl bg-slate-100" />}
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold">{p.title}</div>
              <div className="text-xs text-slate-500">{p.code} · {fmtINR(p.rent_monthly)}/mo · {ago(p.created_at)}</div>
              <div className="mt-1 flex gap-1"><StageBadge stage={p.stage} /><RecBadge rec={p.recommendation} /></div>
            </div>
            <div className="text-xl font-extrabold" style={{ color: scoreColor(p.score) }}>{p.score ? Math.round(p.score) : '…'}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
