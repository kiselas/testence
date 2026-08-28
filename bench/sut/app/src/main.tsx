import { createRoot } from 'react-dom/client'
import Collection from './Collection'
import { activeIds, configurationError } from './defects'
import './styles.css'

/**
 * No `<StrictMode>`, deliberately.
 *
 * StrictMode double-invokes effects in development and not in a production build.
 * Several corpus items are defined by *how many times* something happens — the
 * first parameter change after a load, a component settling once — so a double
 * invocation would make them behave differently while they are being written than
 * while they are being measured. A fixture that is not the same in both modes is
 * not a fixture.
 */

const root = createRoot(document.getElementById('root')!)
const error = configurationError()

if (error) {
  // A misspelled flag renders this instead of an application. It must be
  // impossible to mistake for a working page: a suite that passes here would be a
  // false green produced by the benchmark itself.
  root.render(
    <main className="config-error">
      <h1 role="alert">Benchmark configuration error</h1>
      <p>{error.message}</p>
      <p>No application is running. Fix the corpus item's defect list.</p>
    </main>,
  )
} else {
  const ids = activeIds()
  // Present in the DOM so an evidence pack records what the run was configured
  // with, without the reader having to reconstruct it from the URL.
  document.documentElement.dataset.defects = ids.join(',')
  root.render(<Collection />)
}
