export class ApiError extends Error {
  constructor(public status: number, public code: string | null, message: string) {
    super(message)
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let code: string | null = null
  let message = res.statusText
  try {
    const body = await res.json()
    const detail = body?.detail
    if (detail && typeof detail === 'object') {
      code = detail.code ?? null
      message = detail.message ?? JSON.stringify(detail)
    } else if (typeof detail === 'string') {
      message = detail
    }
  } catch {
    // non-JSON error body — keep statusText
  }
  return new ApiError(res.status, code, message)
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return res.json()
}

export const post = <T = any>(path: string) => api<T>(path, { method: 'POST' })
export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
