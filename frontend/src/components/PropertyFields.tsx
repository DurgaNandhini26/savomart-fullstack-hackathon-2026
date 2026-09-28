// Field-capture inputs for a property. Big touch targets, numeric keyboards, segmented choices.
import clsx from 'clsx'
import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react'

export interface PropertyForm {
  title: string
  property_type: string
  carpet_area_sqft: string
  frontage_ft: string
  floor: string
  ceiling_height_ft: string
  rent_monthly: string
  rent_negotiable: boolean
  deposit_months: string
  lease_years: string
  parking_2w: string
  parking_4w: string
  road_facing: string
  road_width_ft: string
  visibility: number
  power_kw: string
  truck_access: string
  available_from: string
  owner_name: string
  owner_phone: string
  notes: string
}

export const EMPTY_FORM: PropertyForm = {
  title: '', property_type: 'shop', carpet_area_sqft: '', frontage_ft: '', floor: 'ground', ceiling_height_ft: '',
  rent_monthly: '', rent_negotiable: false, deposit_months: '', lease_years: '', parking_2w: '', parking_4w: '',
  road_facing: '', road_width_ft: '', visibility: 3, power_kw: '', truck_access: '', available_from: '',
  owner_name: '', owner_phone: '', notes: '',
}

const num = (s: string) => (s === '' || s == null ? null : Number(s))

export function formToPayload(f: PropertyForm) {
  return {
    title: f.title.trim(), property_type: f.property_type, carpet_area_sqft: num(f.carpet_area_sqft), frontage_ft: num(f.frontage_ft),
    floor: f.floor || null, ceiling_height_ft: num(f.ceiling_height_ft), rent_monthly: num(f.rent_monthly), rent_negotiable: f.rent_negotiable,
    deposit_months: num(f.deposit_months), lease_years: num(f.lease_years), parking_2w: num(f.parking_2w), parking_4w: num(f.parking_4w),
    road_facing: f.road_facing || null, road_width_ft: num(f.road_width_ft), visibility: f.visibility || null, power_kw: num(f.power_kw),
    truck_access: f.truck_access === '' ? null : f.truck_access === 'yes', available_from: f.available_from || null,
    owner_name: f.owner_name || null, owner_phone: f.owner_phone || null, notes: f.notes || null,
  }
}

export function propertyToForm(p: any): PropertyForm {
  const s = (v: any) => (v == null ? '' : String(v))
  return {
    title: p.title, property_type: p.property_type, carpet_area_sqft: s(p.carpet_area_sqft), frontage_ft: s(p.frontage_ft), floor: s(p.floor),
    ceiling_height_ft: s(p.ceiling_height_ft), rent_monthly: s(p.rent_monthly), rent_negotiable: !!p.rent_negotiable, deposit_months: s(p.deposit_months),
    lease_years: s(p.lease_years), parking_2w: s(p.parking_2w), parking_4w: s(p.parking_4w), road_facing: s(p.road_facing), road_width_ft: s(p.road_width_ft),
    visibility: p.visibility || 3, power_kw: s(p.power_kw), truck_access: p.truck_access == null ? '' : p.truck_access ? 'yes' : 'no',
    available_from: s(p.available_from), owner_name: s(p.owner_name), owner_phone: s(p.owner_phone), notes: s(p.notes),
  }
}

function Seg({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([v, l]) => (
        <button type="button" key={v} onClick={() => onChange(value === v ? '' : v)}
          className={clsx('rounded-xl border px-3 py-2 text-sm font-semibold transition', value === v ? 'border-savo-600 bg-savo-600 text-white' : 'border-slate-300 bg-white text-slate-600')}>
          {l}
        </button>
      ))}
    </div>
  )
}

function F({ label, children, hint, className }: { label: string; children: ReactNode; hint?: string; className?: string }) {
  const id = useId()
  // wire the visible label to native inputs; segmented button groups get a named group instead
  const native = isValidElement(children) && ['input', 'select', 'textarea'].includes((children as ReactElement).type as string)
  return (
    <div className={className} role={native ? undefined : 'group'} aria-label={native ? undefined : label}>
      <label className="label" htmlFor={native ? id : undefined}>{label}</label>
      {native ? cloneElement(children as ReactElement<any>, { id }) : children}
      {hint && <div className="mt-0.5 text-[11px] text-slate-400">{hint}</div>}
    </div>
  )
}

export function PropertyFields({ f, set }: { f: PropertyForm; set: (p: Partial<PropertyForm>) => void }) {
  const psf = f.rent_monthly && f.carpet_area_sqft ? Number(f.rent_monthly) / Number(f.carpet_area_sqft) : null
  return (
    <div className="space-y-5">
      <fieldset className="space-y-3">
        <legend className="mb-1 text-sm font-bold text-savo-700">The space</legend>
        <F label="Name / landmark"><input className="input" value={f.title} onChange={(e) => set({ title: e.target.value })} placeholder="e.g. Corner shop opp. Kolathur bus stand" /></F>
        <F label="Type">
          <Seg value={f.property_type} onChange={(v) => set({ property_type: v || 'shop' })} options={[['shop', 'Shop'], ['showroom', 'Showroom'], ['standalone_building', 'Standalone'], ['ground_floor_residential', 'Ground floor of house'], ['warehouse', 'Warehouse'], ['other', 'Other']]} />
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Carpet area (sq ft)"><input className="input" inputMode="numeric" value={f.carpet_area_sqft} onChange={(e) => set({ carpet_area_sqft: e.target.value.replace(/[^\d.]/g, '') })} /></F>
          <F label="Frontage (ft)"><input className="input" inputMode="numeric" value={f.frontage_ft} onChange={(e) => set({ frontage_ft: e.target.value.replace(/[^\d.]/g, '') })} /></F>
        </div>
        <F label="Floor"><Seg value={f.floor} onChange={(v) => set({ floor: v })} options={[['ground', 'Ground'], ['ground+first', 'Ground + 1st'], ['first', '1st floor'], ['basement', 'Basement']]} /></F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Ceiling height (ft)"><input className="input" inputMode="numeric" value={f.ceiling_height_ft} onChange={(e) => set({ ceiling_height_ft: e.target.value.replace(/[^\d.]/g, '') })} /></F>
          <F label="Power load (kW)"><input className="input" inputMode="numeric" value={f.power_kw} onChange={(e) => set({ power_kw: e.target.value.replace(/[^\d.]/g, '') })} /></F>
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-1 text-sm font-bold text-savo-700">Road & visibility</legend>
        <F label="Faces"><Seg value={f.road_facing} onChange={(v) => set({ road_facing: v })} options={[['main_road', 'Main road'], ['secondary', 'Secondary road'], ['interior', 'Interior street']]} /></F>
        <div className="grid grid-cols-2 gap-3">
          <F label="Road width (ft)"><input className="input" inputMode="numeric" value={f.road_width_ft} onChange={(e) => set({ road_width_ft: e.target.value.replace(/[^\d.]/g, '') })} /></F>
          <F label="Truck access"><Seg value={f.truck_access} onChange={(v) => set({ truck_access: v })} options={[['yes', 'Yes'], ['no', 'No']]} /></F>
        </div>
        <F label={`Visibility from the street: ${f.visibility}/5`}>
          <input type="range" min={1} max={5} value={f.visibility} onChange={(e) => set({ visibility: Number(e.target.value) })} className="w-full accent-savo-600" />
        </F>
        <div className="grid grid-cols-2 gap-3">
          <F label="2-wheeler parking"><input className="input" inputMode="numeric" value={f.parking_2w} onChange={(e) => set({ parking_2w: e.target.value.replace(/\D/g, '') })} /></F>
          <F label="Car parking"><input className="input" inputMode="numeric" value={f.parking_4w} onChange={(e) => set({ parking_4w: e.target.value.replace(/\D/g, '') })} /></F>
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-1 text-sm font-bold text-savo-700">Commercials</legend>
        <F label="Monthly rent (₹)" hint={psf ? `≈ ₹${psf.toFixed(0)} per sq ft per month` : 'Monthly, not annual'}>
          <input className="input" inputMode="numeric" value={f.rent_monthly} disabled={f.rent_negotiable} onChange={(e) => set({ rent_monthly: e.target.value.replace(/\D/g, '') })} />
        </F>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-savo-600" checked={f.rent_negotiable} onChange={(e) => set({ rent_negotiable: e.target.checked, rent_monthly: e.target.checked ? '' : f.rent_monthly })} /> Owner hasn't quoted rent yet</label>
        <div className="grid grid-cols-3 gap-3">
          <F label="Deposit (months)"><input className="input" inputMode="numeric" value={f.deposit_months} onChange={(e) => set({ deposit_months: e.target.value.replace(/[^\d.]/g, '') })} /></F>
          <F label="Lease (years)"><input className="input" inputMode="numeric" value={f.lease_years} onChange={(e) => set({ lease_years: e.target.value.replace(/[^\d.]/g, '') })} /></F>
          <F label="Available from"><input type="date" className="input px-2" value={f.available_from} onChange={(e) => set({ available_from: e.target.value })} /></F>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <F label="Owner / broker"><input className="input" value={f.owner_name} onChange={(e) => set({ owner_name: e.target.value })} /></F>
          <F label="Phone"><input className="input" inputMode="tel" value={f.owner_phone} onChange={(e) => set({ owner_phone: e.target.value })} placeholder="+91…" /></F>
        </div>
        <F label="Notes"><textarea className="input min-h-20" value={f.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="Condition, neighbours, anything the manager should know" /></F>
      </fieldset>
    </div>
  )
}
