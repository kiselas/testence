import registry from '../../defects.json'

/**
 * The injection layer, client half.
 *
 * The page is opened with `?defects=D-40,D-45`. That list is parsed once, checked
 * against the registry, and echoed back to the server on every request so one flag
 * can break both halves — see the module docstring in server.py.
 *
 * An unknown id is a hard failure, on purpose. If a corpus item misspells a flag
 * and the application quietly runs healthy, the suite passes and the benchmark has
 * manufactured its own false green — the exact failure it exists to measure. So a
 * bad id renders an error instead of an application, and no run can mistake it for
 * a working page.
 */

const KNOWN = new Set(Object.keys(registry.defects))

export class UnknownDefectError extends Error {}

function parse(): Set<string> {
  const raw = new URLSearchParams(window.location.search).get('defects')
  if (!raw) return new Set()
  const ids = raw.split(',').map((s) => s.trim()).filter(Boolean)
  const unknown = ids.filter((id) => !KNOWN.has(id))
  if (unknown.length) {
    throw new UnknownDefectError(`unknown defect id(s): ${unknown.join(', ')}`)
  }
  return new Set(ids)
}

let active: Set<string>
let parseError: Error | null = null
try {
  active = parse()
} catch (error) {
  active = new Set()
  parseError = error as Error
}

/** Whether a behaviour is injected in this run. */
export function on(id: string): boolean {
  return active.has(id)
}

/** The header value echoed to the server, so its halves apply too. */
export function header(): string {
  return [...active].join(',')
}

export function configurationError(): Error | null {
  return parseError
}

export function activeIds(): string[] {
  return [...active].sort()
}

/**
 * Which store this page talks to, from `?run=`.
 *
 * A corpus item that writes data must not move the baseline for the items after
 * it. One run id means one isolated store, and items can also
 * run concurrently against a single server.
 */
export function runId(): string {
  return new URLSearchParams(window.location.search).get('run') || 'default'
}
