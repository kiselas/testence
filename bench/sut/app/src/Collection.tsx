import { useCallback, useEffect, useRef, useState } from 'react'
import { createRow, fetchRows, type Page, type Query } from './api'
import { on } from './defects'

const PAGE_SIZE = 10
const DEBOUNCE_MS = 250

/**
 * The list's own parameter state.
 *
 * D-40 lives here, and it is written the way the real one was: a guard meant to
 * skip an initial effect that instead swallows the first real update. The first
 * search, sort or page change after a load does nothing; repeating the identical
 * action works. That is what makes it the flagship item — a framework that retries
 * a failed interaction reports green, and a human who clicks again concludes the
 * automation was at fault.
 */
function useListQueryParams(initial: Query): [Query, (patch: Partial<Query>) => void] {
  const [query, setQuery] = useState<Query>(initial)
  const [isInitial, setIsInitial] = useState(false)

  const update = useCallback(
    (patch: Partial<Query>) => {
      if (on('D-40') && !isInitial) {
        setIsInitial(true)
        return
      }
      setQuery((previous) => ({ ...previous, ...patch }))
    },
    [isInitial],
  )

  return [query, update]
}

function initialQuery(): Query {
  const params = new URLSearchParams(window.location.search)
  // D-34: the route carries a filter and a fresh load ignores it. Applying it from
  // within the component (rather than at mount) is the whole difference.
  if (on('D-34')) {
    return { search: '', status: '', sort: 'name', page: 1 }
  }
  return {
    search: params.get('search') || '',
    status: params.get('status') || '',
    sort: params.get('sort') || 'name',
    page: Number(params.get('page') || 1),
  }
}

function SkeletonRows() {
  // Deliberately the same shape and count as real rows: "the elements exist" and
  // "there are ten of them" must both pass against these. That is not an oversight
  // in the fixture, it is the property D-15 exploits.
  return (
    <>
      {Array.from({ length: PAGE_SIZE }, (_, index) => (
        <tr key={index} className="skeleton" aria-hidden="false">
          <td>
            <span className="bar" />
          </td>
          <td>
            <span className="bar" />
          </td>
          <td>
            <span className="bar" />
          </td>
          <td>
            <span className="bar" />
          </td>
        </tr>
      ))}
    </>
  )
}

export default function Collection() {
  const [query, update] = useListQueryParams(initialQuery())
  const [page, setPage] = useState<Page | null>(null)
  const [loading, setLoading] = useState(true)
  const [failure, setFailure] = useState<string | null>(null)
  const [text, setText] = useState(query.search)
  const [draft, setDraft] = useState('')
  const [reloadToken, setReloadToken] = useState(0)
  const firstRender = useRef(true)

  // C-12: a background error on every load that affects no scenario. It must reach
  // the evidence pack and it must not fail a run — a framework that reports console
  // noise as a defect is unusable against any real application.
  useEffect(() => {
    if (on('C-12')) {
      console.error('WebSocket connection to wss://sut/live failed: unexpected response code: 200')
    }
  }, [reloadToken])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailure(null)
    fetchRows(query)
      .then((result) => {
        if (cancelled) return
        setPage(result)
        // D-15: the data arrived and the placeholders never give way to it.
        if (!on('D-15')) setLoading(false)
      })
      .catch((error: Error) => {
        if (cancelled) return
        setFailure(error.message)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [query, reloadToken])

  // Debounced search. Under C-13 the box commits only on Enter — inert typing is a
  // deliberate design in plenty of applications, and a suite that types without
  // committing will declare the feature broken. That is the control.
  useEffect(() => {
    if (on('C-13')) return
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const timer = setTimeout(() => update({ search: text, page: 1 }), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [text])

  async function submitDraft(event: React.FormEvent) {
    event.preventDefault()
    if (!draft.trim()) return
    await createRow(draft.trim())
    setDraft('')
    // D-13: the write succeeded and the list is never asked again, so the new row
    // is missing until the page is reloaded. Any suite that reloads between acting
    // and asserting — most do — cannot see this at all.
    if (!on('D-13')) setReloadToken((token) => token + 1)
  }

  const total = page?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const createLabel = on('U-01-renamed-control') ? 'Add' : 'Create'
  const searchBox = (
    <label className={on('C-08-restyle') ? 'field field--lg accent' : 'field'}>
      Search
      <input
        type="search"
        value={text}
        placeholder="name"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') update({ search: text, page: 1 })
        }}
      />
    </label>
  )
  const statusBox = (
    <label className="field">
      Status
      <select value={query.status} onChange={(event) => update({ status: event.target.value, page: 1 })}>
        <option value="">any</option>
        <option value="draft">draft</option>
        <option value="published">published</option>
        <option value="archived">archived</option>
      </select>
    </label>
  )
  const createButton = <button type="submit">{createLabel}</button>

  return (
    <main>
      <h1>Rows</h1>
      <p className="counter">
        Rows <strong data-testid="total">{total}</strong>
      </p>

      <div className="toolbar">
        {/* C-08-reorder: pure reordering of controls that behave identically. */}
        {on('C-08-reorder') ? (
          <>
            {statusBox}
            {searchBox}
          </>
        ) : (
          <>
            {searchBox}
            {statusBox}
          </>
        )}
        <form onSubmit={submitDraft} className="create">
          <label className="field">
            New row
            <input value={draft} placeholder="new row name" onChange={(event) => setDraft(event.target.value)} />
          </label>
          {/* C-08-wrap: the control gains a container and keeps its semantics. */}
          {on('C-08-wrap') ? <div className="btn-holder">{createButton}</div> : createButton}
        </form>
      </div>

      {failure && <p role="alert">{failure}</p>}

      <table>
        <thead>
          <tr>
            {(['name', 'owner', 'status', 'updatedAt'] as const).map((column) => (
              <th key={column} scope="col">
                <button
                  type="button"
                  onClick={() =>
                    update({ sort: query.sort === column ? `-${column}` : column, page: 1 })
                  }
                >
                  {column}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? <SkeletonRows /> : null}
          {!loading &&
            page?.rows.map((row) => (
              <tr key={row.id} data-key={row.id}>
                <td>{row.name}</td>
                <td>{row.owner}</td>
                <td>{row.status}</td>
                <td>{row.updatedAt.slice(0, 10)}</td>
              </tr>
            ))}
          {!loading && page?.rows.length === 0 && (
            <tr>
              <td colSpan={4}>nothing matches</td>
            </tr>
          )}
        </tbody>
      </table>

      <nav className="pager" aria-label="pagination">
        <button type="button" disabled={query.page <= 1} onClick={() => update({ page: query.page - 1 })}>
          previous
        </button>
        <span>
          page {query.page} of {lastPage}
        </span>
        <button type="button" disabled={query.page >= lastPage} onClick={() => update({ page: query.page + 1 })}>
          next
        </button>
      </nav>
    </main>
  )
}
