import { useQuery } from '@tanstack/react-query'
import { Briefcase, ClipboardCheck, LineChart, MapPin } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Layout'
import { ErrorBox, Spinner } from '../components/ui'
import { errorText, get } from '../lib/api'
import { ROLE_LABEL, useAuth, type Role, type User } from '../lib/auth'

const ROLE_INFO: Record<Role, { icon: JSX.Element; job: string }> = {
  bd_manager: { icon: <LineChart className="h-5 w-5" />, job: 'Explore areas, direct scouts, decide on properties' },
  bd_exec: { icon: <MapPin className="h-5 w-5" />, job: 'Scout hotspots and onboard properties from the field' },
  survey_manager: { icon: <Briefcase className="h-5 w-5" />, job: 'Plan catchment studies and assign survey teams' },
  survey_exec: { icon: <ClipboardCheck className="h-5 w-5" />, job: 'Survey lanes street by street, even offline' },
}

export default function Login() {
  const { user, login, switchTo } = useAuth()
  const nav = useNavigate()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | 'form' | null>(null)
  const { data: users } = useQuery<User[]>({ queryKey: ['demo-users'], queryFn: () => get('/api/auth/demo-users') })

  if (user) return <Navigate to="/" replace />

  async function pick(id: number) {
    setBusy(id)
    setErr(null)
    try {
      await switchTo(id)
      nav('/')
    } catch (e) {
      setErr(errorText(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="min-h-full bg-gradient-to-br from-savo-700 via-savo-600 to-savo-800">
      <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center gap-8 px-4 py-10 lg:flex-row lg:items-center">
        <div className="text-white lg:w-2/5">
          <div className="mb-6 inline-block rounded-2xl bg-white px-4 py-3"><Logo /></div>
          <h1 className="text-4xl font-extrabold leading-tight">
            Find the next <span className="text-sun">Savomart</span> before anyone leaves the office.
          </h1>
          <p className="mt-4 text-savo-100">
            Area intelligence, field scouting and catchment surveys for Chennai — one loop, four teams.
          </p>
        </div>
        <div className="rounded-3xl bg-white p-5 shadow-2xl sm:p-6 lg:w-3/5">
          <h2 className="text-lg font-bold">Demo: pick a persona</h2>
          <p className="mb-4 text-sm text-slate-500">One tap signs you in. Everyone's password is <code className="rounded bg-slate-100 px-1">savo@123</code>.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {users?.map((x) => (
              <button key={x.id} onClick={() => pick(x.id)} disabled={busy !== null}
                className="group flex items-start gap-3 rounded-2xl border border-slate-200 p-3 text-left transition hover:border-savo-400 hover:bg-savo-50">
                <div className="rounded-xl bg-savo-100 p-2 text-savo-700 group-hover:bg-sun">{ROLE_INFO[x.role].icon}</div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 font-semibold">
                    {x.name} {busy === x.id && <Spinner className="h-4 w-4" />}
                  </div>
                  <div className="text-xs font-semibold text-savo-700">{ROLE_LABEL[x.role]}</div>
                  <div className="text-xs text-slate-500">{ROLE_INFO[x.role].job}</div>
                </div>
              </button>
            ))}
            {!users && <div className="col-span-2 flex justify-center py-6"><Spinner /></div>}
          </div>
          <form className="mt-5 flex flex-col gap-2 border-t pt-4 sm:flex-row"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy('form')
              setErr(null)
              try {
                await login(u, p)
                nav('/')
              } catch (ex) {
                setErr(errorText(ex))
              } finally {
                setBusy(null)
              }
            }}>
            <input className="input" placeholder="username (e.g. priya)" value={u} onChange={(e) => setU(e.target.value)} autoCapitalize="none" />
            <input className="input" placeholder="password" type="password" value={p} onChange={(e) => setP(e.target.value)} />
            <button className="btn-primary shrink-0" disabled={busy !== null}>Sign in</button>
          </form>
          {err && <div className="mt-3"><ErrorBox error={err} /></div>}
        </div>
      </div>
    </div>
  )
}
