import { header, runId } from './defects'

/**
 * Every call carries the run's defect list, which is what makes the server half
 * of a flag apply. Nothing else in the application talks to the network.
 */
async function call(path: string, init: RequestInit = {}): Promise<any> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Defects': header(),
      'X-Run': runId(),
      ...(init.headers || {}),
    },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    // Carried, not swallowed: the reporting-gap family of defects is about what the
    // interface does with this, so it has to reach the caller intact.
    const error = new Error(body?.error || `HTTP ${response.status}`) as Error & {
      status?: number
      body?: unknown
    }
    error.status = response.status
    error.body = body
    throw error
  }
  return body
}

export interface Row {
  id: string
  name: string
  owner: string
  status: string
  updatedAt: string
  deleted: boolean
}

export interface Page {
  total: number
  page: number
  pageSize: number
  rows: Row[]
}

export interface Query {
  search: string
  status: string
  sort: string
  page: number
}

export function fetchRows(query: Query): Promise<Page> {
  const params = new URLSearchParams({
    search: query.search,
    status: query.status,
    sort: query.sort,
    page: String(query.page),
  })
  return call(`/api/rows?${params}`)
}

export function createRow(name: string): Promise<Row> {
  return call('/api/rows', { method: 'POST', body: JSON.stringify({ name }) })
}
