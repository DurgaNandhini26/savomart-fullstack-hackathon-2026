// Thin fetch wrapper: bearer token, JSON, readable errors.

export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message || `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

const TOKEN_KEY = 'sitescout.token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode — token lives for the session only */
  }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) }
  const token = getToken()
  if (token) headers.authorization = `Bearer ${token}`
  let body = opts.body
  if (opts.json !== undefined) {
    headers['content-type'] = 'application/json'
    body = JSON.stringify(opts.json)
  }
  let res: Response
  try {
    res = await fetch(path, { ...opts, headers, body })
  } catch {
    throw new ApiError(0, 'You appear to be offline. Check your connection and retry.')
  }
  if (res.status === 401 && token) {
    setToken(null)
    window.location.href = '/login'
  }
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data ?? res.statusText)
  return data as T
}

function safeJson(t: string) {
  try {
    return JSON.parse(t)
  } catch {
    return t
  }
}

export const get = <T = any>(p: string) => api<T>(p)
export const post = <T = any>(p: string, json?: unknown) => api<T>(p, { method: 'POST', json: json ?? {} })
export const patch = <T = any>(p: string, json?: unknown) => api<T>(p, { method: 'PATCH', json })

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (Array.isArray(e.detail)) return e.detail.map((d: any) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join('; ')
    return e.message
  }
  return (e as Error)?.message || 'Something went wrong'
}
