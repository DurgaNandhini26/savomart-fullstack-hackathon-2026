import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Recycle, Route, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorText, get, post } from '../lib/api'
import { fmt1, pct } from '../lib/format'
import { FitBounds, GeoLayer, MapView, geomPoints } from './Map'
import { ErrorBox, Modal, Spinner } from './ui'

export function MissionModal({ open, onClose, preset }: {
  open: boolean
  onClose: () => void
  preset: { title: string; lat: number; lng: number; report_id?: number; hotspot_rank?: number; brief?: string }
}) {
  const qc = useQueryClient()
  const execs = useQuery({ queryKey: ['users', 'bd_exec'], queryFn: () => get('/api/users?role=bd_exec'), enabled: open })
  const [form, setForm] = useState({ title: preset.title, brief: preset.brief || '', assignee_id: '', radius_m: 600, due_date: '' })
  useEffect(() => setForm((f) => ({ ...f, title: preset.title, brief: preset.brief || '' })), [preset.title, preset.brief])
  const m = useMutation({
    mutationFn: () => post('/api/missions', { ...preset, ...form, assignee_id: Number(form.assignee_id), due_date: form.due_date || null }),
    onSuccess: () => {
      qc.invalidateQueries()
      onClose()
    },
  })
  return (
    <Modal open={open} onClose={onClose} title="Send an executive to scout">
      <div className="space-y-3">
        <div>
          <label className="label">Mission</label>
          <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div>
          <label className="label">Executive</label>
          <select className="input" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}>
            <option value="">Choose…</option>
            {execs.data?.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Search radius</label>
            <select className="input" value={form.radius_m} onChange={(e) => setForm({ ...form, radius_m: Number(e.target.value) })}>
              {[300, 600, 1000, 1500].map((r) => <option key={r} value={r}>{r} m</option>)}
            </select>
          </div>
          <div>
            <label className="label">Due</label>
            <input type="date" className="input" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="label">Brief for the executive</label>
          <textarea className="input min-h-24" value={form.brief} onChange={(e) => setForm({ ...form, brief: e.target.value })} />
        </div>
        {m.error && <ErrorBox error={errorText(m.error)} />}
        <button className="btn-primary w-full" disabled={!form.assignee_id || m.isPending} onClick={() => m.mutate()}>
          {m.isPending ? <Spinner className="h-4 w-4 text-white" /> : <Send className="h-4 w-4" />} Assign mission
        </button>
      </div>
    </Modal>
  )
}

export function StudyModal({ open, onClose, target }: {
  open: boolean
  onClose: () => void
  target: { target_type: 'property' | 'area'; property_id?: number; report_id?: number; label: string }
}) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [radius, setRadius] = useState(800)
  const [priority, setPriority] = useState('normal')
  const [due, setDue] = useState('')
  const [notes, setNotes] = useState('')
  const body = { target_type: target.target_type, property_id: target.property_id, report_id: target.report_id, radius_m: radius }
  const preview = useQuery({ queryKey: ['study-preview', body], queryFn: () => post('/api/studies/preview', body), enabled: open })
  const m = useMutation({
    mutationFn: () => post('/api/studies', { ...body, priority, due_date: due || null, notes }),
    onSuccess: (s) => {
      qc.invalidateQueries()
      onClose()
      nav(`/studies/${s.id}`)
    },
  })
  const p = preview.data
  return (
    <Modal open={open} onClose={onClose} title={`Catchment study · ${target.label}`}>
      <div className="space-y-3">
        {target.target_type === 'property' && (
          <div>
            <label className="label">Catchment radius</label>
            <div className="flex gap-2">
              {[500, 800, 1200].map((r) => (
                <button key={r} className={r === radius ? 'btn-primary flex-1' : 'btn-ghost flex-1'} onClick={() => setRadius(r)}>{r} m</button>
              ))}
            </div>
          </div>
        )}
        <div className="h-48 overflow-hidden rounded-xl">
          {p && (
            <MapView className="h-full" interactive={false}>
              <GeoLayer id="prev" data={p.geojson} layers={[
                { type: 'fill', paint: { 'fill-color': ['case', ['get', 'covered'], '#14b8a6', '#FFF200'], 'fill-opacity': 0.5 } } as any,
                { type: 'line', paint: { 'line-color': '#782B90', 'line-width': 0.7 } } as any,
              ]} />
              <FitBounds points={geomPoints(p.geojson)} padding={20} />
            </MapView>
          )}
          {preview.isLoading && <div className="flex h-full items-center justify-center"><Spinner /></div>}
        </div>
        {p && (
          <div className={`rounded-xl p-3 text-sm ${p.fully_reused ? 'bg-teal-50 text-teal-900' : 'bg-savo-50'}`}>
            {p.coverage > 0 ? (
              <div className="flex items-start gap-2">
                <Recycle className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
                <div>
                  <b>{pct(p.coverage)}</b> of this catchment is already covered by {p.sources.map((s: any) => s.code).join(', ')}
                  {' '}(policy: reuse if ≥ {pct(p.policy.min_coverage)} covered and ≤ {p.policy.max_age_days} days old).
                  {p.fully_reused ? <div className="mt-1 font-semibold">No new fieldwork needed — existing data will be reused.</div>
                    : <div className="mt-1">Only the <b>{p.remaining_cells.length}</b> uncovered cells (~{fmt1(p.lane_km_to_survey)} lane-km) will be surveyed.</div>}
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <Route className="mt-0.5 h-4 w-4 shrink-0 text-savo-600" />
                <div>No existing survey data here. {p.requested} cells · ~{fmt1(p.lane_km_to_survey)} km of lanes to survey.</div>
              </div>
            )}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Priority</label>
            <select className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
            </select>
          </div>
          <div>
            <label className="label">Needed by</label>
            <input type="date" className="input" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>
        <textarea className="input" placeholder="Notes for the survey team (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
        {m.error && <ErrorBox error={errorText(m.error)} />}
        <button className="btn-primary w-full" disabled={m.isPending || !p} onClick={() => m.mutate()}>
          {m.isPending && <Spinner className="h-4 w-4 text-white" />} {p?.fully_reused ? 'Link existing survey data' : 'Request catchment study'}
        </button>
      </div>
    </Modal>
  )
}
