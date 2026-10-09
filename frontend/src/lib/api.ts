import axios from 'axios'

function getApiUrl() {
  // If VITE_API_URL is set and not localhost, use it
  const envUrl = import.meta.env.VITE_API_URL
  // In e2b preview environment, use relative URL so vite proxy handles it
  // This avoids CORS and traffic token issues
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host.includes('e2b.app')) {
      // Use relative URL - vite proxy will forward to backend
      return ''
    }
    // If localhost and we're in browser, try to use relative proxy
    if (host === 'localhost' || host === '127.0.0.1') {
      // For local dev, use proxy (empty) or localhost:8000
      return ''
    }
    // Preview deployments may explicitly target an isolated staging API.
    if (envUrl) {
      return envUrl
    }
    // Production uses the stable API through its same-origin rewrite.
    if (host === 'freshstock-app.vercel.app' || host.endsWith('.vercel.app')) {
      return ''
    }
  }
  return envUrl || ''
}

const API_URL = getApiUrl()
console.log('API URL:', API_URL || '(relative)')

export const api = axios.create({
  baseURL: API_URL ? `${API_URL}/api` : `/api`,
  headers: {
    'Content-Type': 'application/json'
  }
})

// ---------------------------------------------------------------------------
// Idempotency + double-submit guard
//
// 1. Every mutating request carries a unique Idempotency-Key. The key is
//    stored on the request config, so the 401 token-refresh retry replays
//    the same key and the backend returns the stored response instead of
//    executing the mutation twice.
// 2. Identical mutating requests that are in flight at the same time
//    (double-click, double-tap, impatient user) share one promise, so the
//    mutation executes exactly once. The entry is removed as soon as the
//    request settles, which keeps intentional repeat submissions working.
//    /scanner/events is excluded: rapid identical scan events are legitimate.
//    FormData uploads are never deduplicated (no reliable fingerprint).
// ---------------------------------------------------------------------------

const MUTATING_METHODS = ['post', 'put', 'patch', 'delete']
const DEDUP_DENYLIST = ['/scanner/events']
const DEDUP_WINDOW_MS = 2000

const inFlight = new Map<string, { promise: Promise<unknown>; expires: number }>()

function uuidv4(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value !== 'object') return JSON.stringify(value)
  if (typeof FormData !== 'undefined' && value instanceof FormData) {
    // Uploads cannot be fingerprinted reliably - never deduplicate them.
    return `__formdata__${Date.now()}_${Math.random().toString(36).slice(2)}`
  }
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  const record = value as Record<string, unknown>
  const keys = Object.keys(record).sort()
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(record[k])}`).join(',')}}`
}

function setHeader(headers: unknown, name: string, value: string): void {
  if (!headers) return
  const h = headers as Record<string, unknown> & { set?: (k: string, v: string) => void; get?: (k: string) => string | null }
  if (typeof h.set === 'function' && typeof h.get === 'function') {
    if (!h.get(name)) h.set(name, value)
  } else if (!h[name]) {
    h[name] = value
  }
}

api.interceptors.request.use((config) => {
  // Let the browser/Axios generate multipart/form-data together with its boundary.
  // Keeping the instance-wide JSON content type makes FastAPI see an empty form.
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    if (typeof config.headers?.delete === 'function') {
      config.headers.delete('Content-Type')
    } else if (config.headers) {
      delete config.headers['Content-Type']
    }
  }
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const method = String(config.method || '').toLowerCase()
  if (MUTATING_METHODS.includes(method)) {
    setHeader(config.headers, 'Idempotency-Key', uuidv4())
  }
  return config
})

for (const method of MUTATING_METHODS) {
  const original = (api as unknown as Record<string, (...args: unknown[]) => Promise<unknown>>)[method].bind(api)
  ;(api as unknown as Record<string, (...args: unknown[]) => Promise<unknown>>)[method] = async (
    url: unknown,
    data?: unknown,
    config?: unknown
  ): Promise<unknown> => {
    const urlStr = String(url || '')
    if (DEDUP_DENYLIST.some((p) => urlStr.includes(p))) {
      return original(url, data, config)
    }
    const fingerprint = `${method}:${urlStr}:${stableStringify(data)}`
    const now = Date.now()
    const existing = inFlight.get(fingerprint)
    if (existing && existing.expires > now) {
      return existing.promise
    }
    const promise = original(url, data, config)
    inFlight.set(fingerprint, { promise, expires: now + DEDUP_WINDOW_MS })
    promise.finally(() => {
      const current = inFlight.get(fingerprint)
      if (current && current.promise === promise) {
        inFlight.delete(fingerprint)
      }
    })
    return promise
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const requestUrl = String(originalRequest?.url || '')
    const isAuthenticationRequest = ['/auth/login', '/auth/bootstrap', '/auth/register-store', '/auth/refresh']
      .some(path => requestUrl.includes(path))
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthenticationRequest) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_URL}/api/auth/refresh`, { refresh_token: refreshToken })
          localStorage.setItem('access_token', res.data.access_token)
          localStorage.setItem('refresh_token', res.data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${res.data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    if (error.response?.status === 403 && error.response?.data?.detail?.error === 'FEATURE_NOT_AVAILABLE') {
      window.dispatchEvent(new CustomEvent('freshstock:feature-blocked', { detail: error.response.data.detail }))
    }
    if (error.response?.status === 409 && error.response?.data?.error === 'DOUBLE_SUBMIT_DETECTED') {
      window.dispatchEvent(new CustomEvent('freshstock:double-submit', { detail: error.response.data }))
    }
    if (error.response?.status === 409 && error.response?.data?.error === 'IDEMPOTENCY_KEY_REUSED') {
      window.dispatchEvent(new CustomEvent('freshstock:idempotency-conflict', { detail: error.response.data }))
    }
    return Promise.reject(error)
  }
)
