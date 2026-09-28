import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  Bell, Bot, ClipboardList, CloudOff, FileBarChart2, Home, KanbanSquare, LogOut, Map, MapPinned, PlusCircle, RefreshCw,
  Route, Users,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ErrorBoundary } from './ErrorBoundary'
import { get, post } from '../lib/api'
import { ROLE_LABEL, useAuth, type Role } from '../lib/auth'
import { ago } from '../lib/format'
import { flush, useOnline, useOutbox } from '../lib/offline'

type NavItem = { to: string; label: string; icon: ReactNode; end?: boolean }

const NAV: Record<Role, NavItem[]> = {
  bd_manager: [
    { to: '/', label: 'Home', icon: <Home className="h-5 w-5" />, end: true },
    { to: '/explore', label: 'Explore', icon: <Map className="h-5 w-5" /> },
    { to: '/reports', label: 'Reports', icon: <FileBarChart2 className="h-5 w-5" /> },
    { to: '/pipeline', label: 'Pipeline', icon: <KanbanSquare className="h-5 w-5" /> },
    { to: '/missions', label: 'Missions', icon: <MapPinned className="h-5 w-5" /> },
    { to: '/studies', label: 'Studies', icon: <Route className="h-5 w-5" /> },
    { to: '/assistant', label: 'Analyst', icon: <Bot className="h-5 w-5" /> },
  ],
  bd_exec: [
    { to: '/', label: 'Missions', icon: <MapPinned className="h-5 w-5" />, end: true },
    { to: '/properties/new', label: 'Add property', icon: <PlusCircle className="h-5 w-5" /> },
    { to: '/my-properties', label: 'My properties', icon: <ClipboardList className="h-5 w-5" /> },
  ],
  survey_manager: [
    { to: '/', label: 'Studies', icon: <Route className="h-5 w-5" />, end: true },
    { to: '/team', label: 'Team', icon: <Users className="h-5 w-5" /> },
  ],
  survey_exec: [{ to: '/', label: 'Assignments', icon: <ClipboardList className="h-5 w-5" />, end: true }],
}

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 64 64" className="h-8 w-8 shrink-0">
        <rect width="64" height="64" rx="14" fill="#782B90" />
        <path d="M32 12c-8.3 0-15 6.5-15 14.6C17 38 32 52 32 52s15-14 15-25.4C47 18.5 40.3 12 32 12z" fill="#FFF200" />
        <circle cx="32" cy="27" r="6" fill="#782B90" />
      </svg>
      {!compact && (
        <div className="leading-tight">
          <div className="text-[15px] font-extrabold tracking-tight text-slate-900">
            Savo <span className="text-savo-600">SiteScout</span>
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Chennai expansion</div>
        </div>
      )}
    </div>
  )
}

function NotificationBell() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data } = useQuery({ queryKey: ['notifications'], queryFn: () => get('/api/notifications'), refetchInterval: 15000 })
  const unread = data?.unread || 0
  return (
    <div className="relative">
      <button
        className="relative rounded-full p-2 hover:bg-slate-100"
        aria-label="Notifications"
        onClick={async () => {
          setOpen(!open)
          if (!open && unread) {
            await post('/api/notifications/read')
            qc.invalidateQueries({ queryKey: ['notifications'] })
          }
        }}
      >
        <Bell className="h-5 w-5 text-slate-600" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-savo-600 px-1 text-[10px] font-bold text-sun">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 max-h-[70vh] w-80 overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="border-b px-4 py-2.5 text-sm font-bold">Activity</div>
            {!data?.items?.length && <div className="p-4 text-sm text-slate-500">Nothing yet.</div>}
            {data?.items?.map((n: any) => (
              <button
                key={n.id}
                className={clsx('block w-full border-b border-slate-100 px-4 py-2.5 text-left hover:bg-savo-50', !n.read && 'bg-savo-50/60')}
                onClick={() => {
                  setOpen(false)
                  if (n.link) nav(n.link)
                }}
              >
                <div className="text-sm font-semibold text-slate-800">{n.title}</div>
                {n.body && <div className="line-clamp-2 text-xs text-slate-500">{n.body}</div>}
                <div className="mt-0.5 text-[11px] text-slate-400">{ago(n.created_at)}</div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function SyncPill() {
  const online = useOnline()
  const outbox = useOutbox()
  const [busy, setBusy] = useState(false)
  if (online && !outbox.length) return null
  return (
    <button
      onClick={async () => {
        setBusy(true)
        await flush()
        setBusy(false)
      }}
      className={clsx('chip gap-1.5 py-1', online ? 'bg-amber-100 text-amber-800' : 'bg-slate-800 text-white')}
      title="Items saved on this device, waiting to upload"
    >
      {online ? <RefreshCw className={clsx('h-3.5 w-3.5', busy && 'animate-spin')} /> : <CloudOff className="h-3.5 w-3.5" />}
      {online ? `${outbox.length} to sync` : `Offline${outbox.length ? ` · ${outbox.length} saved` : ''}`}
    </button>
  )
}

export function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  if (!user) return null
  const items = NAV[user.role]
  return (
    <div className="flex h-full">
      {/* desktop sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="px-5 py-5">
          <Link to="/"><Logo /></Link>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.end}
              className={({ isActive }) => clsx('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition',
                isActive ? 'bg-savo-600 text-white shadow-sm' : 'text-slate-600 hover:bg-savo-50 hover:text-savo-700')}>
              {i.icon}
              {i.label}
            </NavLink>
          ))}
        </nav>
        <div className="m-3 rounded-2xl bg-savo-50 p-3">
          <div className="text-sm font-bold text-slate-800">{user.name}</div>
          <div className="text-xs font-medium text-savo-700">{ROLE_LABEL[user.role]}</div>
          <button className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-savo-700"
            onClick={() => { logout(); nav('/login') }}>
            <LogOut className="h-3.5 w-3.5" /> Switch user
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b border-slate-200 bg-white/90 px-4 py-2.5 backdrop-blur">
          <div className="md:hidden"><Link to="/"><Logo compact /></Link></div>
          <div className="hidden text-sm text-slate-500 md:block">
            Signed in as <b className="text-slate-700">{user.name}</b> · {ROLE_LABEL[user.role]}
          </div>
          <div className="flex items-center gap-2">
            <SyncPill />
            <NotificationBell />
            <button className="rounded-full p-2 hover:bg-slate-100 md:hidden" aria-label="Switch user"
              onClick={() => { logout(); nav('/login') }}>
              <LogOut className="h-5 w-5 text-slate-600" />
            </button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto pb-20 md:pb-0">
          <ErrorBoundary resetKey={loc.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
        {/* mobile bottom nav */}
        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden">
          {items.slice(0, 5).map((i) => (
            <NavLink key={i.to} to={i.to} end={i.end}
              className={({ isActive }) => clsx('flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-semibold',
                isActive ? 'text-savo-700' : 'text-slate-500')}>
              {({ isActive }) => (
                <>
                  <span className={clsx('rounded-full px-3 py-0.5', isActive && 'bg-sun')}>{i.icon}</span>
                  {i.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
