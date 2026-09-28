// Offline-first field capture.
//
// * Drafts: every keystroke of a half-filled lane survey / property form is saved locally,
//   so closing the app, losing signal or a phone restart never loses work.
// * Outbox: completed submissions are queued locally with a client-generated UUID and
//   pushed when the network is back. The server treats the UUID as an idempotency key,
//   so a submit that timed out *after* reaching the server can be retried safely.
import { useEffect, useState, useSyncExternalStore } from 'react'
import { api } from './api'

type OutboxItem = { id: string; kind: 'observation' | 'property'; payload: any; created: number; error?: string; photos?: string[] }

const OUTBOX = 'sitescout.outbox'
const listeners = new Set<() => void>()
let cache: OutboxItem[] | null = null

function read(): OutboxItem[] {
  if (cache) return cache
  try {
    cache = JSON.parse(localStorage.getItem(OUTBOX) || '[]')
  } catch {
    cache = []
  }
  return cache!
}
function write(items: OutboxItem[]) {
  cache = items
  try {
    localStorage.setItem(OUTBOX, JSON.stringify(items))
  } catch {
    /* storage full / private mode: keep in memory */
  }
  listeners.forEach((l) => l())
}

export function enqueue(kind: OutboxItem['kind'], payload: any, id: string, photos?: string[]) {
  write([...read().filter((i) => i.id !== id), { id, kind, payload, created: Date.now(), photos }])
}

export function useOutbox() {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    read,
  )
}

let syncing = false
export async function flush(): Promise<{ sent: number; failed: number }> {
  if (syncing || !navigator.onLine) return { sent: 0, failed: 0 }
  syncing = true
  let sent = 0
  let failed = 0
  try {
    const items = read()
    const obs = items.filter((i) => i.kind === 'observation')
    if (obs.length) {
      try {
        const r = await api<{ results: { client_uuid: string; status: string; error?: string }[] }>(
          '/api/survey/observations',
          { method: 'POST', json: { observations: obs.map((o) => o.payload) } },
        )
        const done = new Set(r.results.filter((x) => x.status !== 'rejected').map((x) => x.client_uuid))
        const errs = Object.fromEntries(r.results.filter((x) => x.status === 'rejected').map((x) => [x.client_uuid, x.error]))
        sent += done.size
        failed += Object.keys(errs).length
        write(read().filter((i) => !done.has(i.id)).map((i) => (errs[i.id] ? { ...i, error: errs[i.id] } : i)))
      } catch {
        failed += obs.length
      }
    }
    for (const p of read().filter((i) => i.kind === 'property')) {
      try {
        const r = await api<{ property: { id: number } }>('/api/properties', { method: 'POST', json: p.payload })
        for (const dataUrl of p.photos || []) {
          const blob = await (await fetch(dataUrl)).blob()
          const fd = new FormData()
          fd.append('file', blob, 'photo.jpg')
          await api(`/api/properties/${r.property.id}/photos`, { method: 'POST', body: fd })
        }
        write(read().filter((i) => i.id !== p.id))
        sent++
      } catch (e: any) {
        failed++
        if (e?.status && e.status !== 0) write(read().map((i) => (i.id === p.id ? { ...i, error: e.message } : i)))
      }
    }
  } finally {
    syncing = false
  }
  return { sent, failed }
}

export function discard(id: string) {
  write(read().filter((i) => i.id !== id))
}

// auto-sync when connectivity returns and every 30 s while items are pending
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => flush())
  setInterval(() => {
    if (read().length) flush()
  }, 30000)
}

export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

// ---------------------------------------------------------------- drafts

export function useDraft<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void, () => void] {
  const k = `sitescout.draft.${key}`
  const [val, setVal] = useState<T>(() => {
    try {
      const s = localStorage.getItem(k)
      return s ? { ...initial, ...JSON.parse(s) } : initial
    } catch {
      return initial
    }
  })
  // only persist after the user actually changes something, so opening a form isn't a "draft"
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (!dirty) return
    try {
      localStorage.setItem(k, JSON.stringify(val))
    } catch {
      /* ignore */
    }
  }, [k, val, dirty])
  const update = (v: T | ((p: T) => T)) => {
    setDirty(true)
    setVal(v)
  }
  const clear = () => {
    setDirty(false)
    try {
      localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  }
  return [val, update, clear]
}

export function hasDraft(key: string) {
  try {
    return !!localStorage.getItem(`sitescout.draft.${key}`)
  } catch {
    return false
  }
}

// ---------------------------------------------------------------- photos

/** Downscale camera photos on the phone before upload: 12 MB -> ~300 KB on weak networks. */
export async function compressImage(file: File, maxDim = 1600, quality = 0.8): Promise<string> {
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => {
      const i = new Image()
      i.onload = () => res(i)
      i.onerror = rej
      i.src = url
    })
    const scale = Math.min(1, maxDim / Math.max(img.width, img.height))
    const c = document.createElement('canvas')
    c.width = Math.round(img.width * scale)
    c.height = Math.round(img.height * scale)
    c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
    return c.toDataURL('image/jpeg', quality)
  } finally {
    URL.revokeObjectURL(url)
  }
}
