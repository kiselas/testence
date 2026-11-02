import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { CaseRow, RunSummary } from '../types'

const PANE = 'testence-runs'
const FOLDER_KEY = 'runsDir'
// A run that wrote nothing for this long without run.end was cut short (Ctrl+C, a killed worker).
const STALE_MS = 120_000

const summary = atom({ plugin: 'testence-runs', key: 'summary' } as const, null, { shape: 'summary-1' })

// run.jsonl grows past the 4 MiB a single $.fs.read takes (about 10 MB for 60 cases), so a small
// Python reads it and prints the summary the pane draws. Testence is a Python tool: Python is there.
const SUMMARIZE = String.raw`
import json, sys
cases, order, run = {}, [], {"profile": None, "status": "running", "startedAt": None, "durationMs": None}
def case(nodeid):
    if nodeid not in cases:
        name = nodeid.split("::")[-1]
        cases[nodeid] = {"nodeid": nodeid, "name": name, "file": nodeid.split("::")[0].split("/")[-1],
                         "status": "queued", "durationMs": None, "step": None, "steps": 0, "error": None}
        order.append(nodeid)
    return cases[nodeid]
with open(sys.argv[1], encoding="utf-8") as ledger:
    for line in ledger:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        kind = e.get("kind")
        if kind == "run.start":
            run["profile"] = (e.get("fingerprint") or {}).get("profile")
            run["startedAt"] = e.get("ts")
        elif kind == "collection.end":
            for nodeid in e.get("nodeids") or []:
                case(nodeid)
        elif kind == "test.start":
            case(e["nodeid"])["status"] = "running"
        elif kind == "step.start" and e.get("test"):
            row = case(e["test"])
            row["step"], row["steps"] = e.get("intent"), row["steps"] + 1
        elif kind == "test.end":
            row = case(e["nodeid"])
            row["status"], row["durationMs"], row["step"] = e.get("status") or "passed", e.get("duration_ms"), None
            error = (e.get("error") or "").strip()
            row["error"] = error.splitlines()[0][:300] if error else None
        elif kind == "run.end":
            run["status"], run["durationMs"] = e.get("run_status") or "complete", e.get("duration_ms")
print(json.dumps({**run, "total": len(order), "cases": [cases[n] for n in order]}, ensure_ascii=False))
`

const SYMBOL: Record<CaseRow['status'], string> = {
  queued: '○',
  running: '●',
  passed: '✓',
  failed: '✗',
  broken: '✗',
  skipped: '–',
}

const COLOR: Partial<Record<CaseRow['status'], 'success' | 'error' | 'warning' | 'suggestion'>> = {
  running: 'suggestion',
  passed: 'success',
  failed: 'error',
  broken: 'error',
  skipped: 'warning',
}

const seconds = (ms: number | null) => (ms === null ? '' : `${(ms / 1000).toFixed(1)} s`)

// test_12_drag_leaves_own_group → «12», «drag leaves own group»: the case number of the case file stands apart.
const caseTitle = (name: string) => {
  const words = name.replace(/^test_/, '').split('_')
  const number = /^\d+$/.test(words[0] ?? '') ? (words.shift() as string) : ''
  return { number, title: words.join(' ') }
}

const join = (dir: string, name: string) => `${dir.replace(/[\\/]+$/, '')}/${name}`

// Module variables start over on every reload; the summary itself lives in $.state.
let last = ''
let config = { runsDir: '', python: 'python' }

async function runsDir($: EngineInterface): Promise<string> {
  const chosen = (await $.store.get(FOLDER_KEY)) as string | undefined
  return chosen || config.runsDir || 'runs'
}

async function poll($: EngineInterface): Promise<void> {
  const dir = await runsDir($)
  if (!(await $.fs.exists(dir))) return
  const runs = (await $.fs.list(dir)).filter(entry => entry.kind === 'dir' && entry.name.startsWith('r-'))
  if (runs.length === 0) return
  const newest = runs.map(entry => entry.name).sort().at(-1) as string
  const ledger = (await $.fs.list(join(dir, newest))).find(entry => entry.name === 'run.jsonl')
  if (!ledger) return
  const now = await $.clock.now()
  const mark = `${newest}:${ledger.size}`
  const before = await read($, summary)
  if (mark === last) {
    // Nothing new: only a run gone quiet without run.end changes how it reads.
    if (before?.status === 'running' && now - ledger.mtimeMs > STALE_MS) {
      await update($, summary, value => (value ? { ...value, status: 'interrupted?' } : value))
    }
    return
  }
  const isFirstLook = last === ''
  last = mark
  const done = await $.process.run([config.python, '-c', SUMMARIZE, join(join(dir, newest), 'run.jsonl')], {
    timeoutMs: 20_000,
  })
  if (done.exitCode !== 0) {
    $.ui.status(`testence-runs: ${done.stderr.trim().split(/\r?\n/).at(-1) || 'summary failed'}`)
    return
  }
  const parsed = JSON.parse(done.stdout) as Omit<RunSummary, 'run' | 'updatedAtMs'>
  const next: RunSummary = { ...parsed, run: newest, updatedAtMs: now }
  await update($, summary, () => next)
  $.ui.status(undefined)

  if (before?.run !== newest && !isFirstLook) {
    void $.ui.open({ id: PANE, title: 'Testence run' })
  }
  const hasEnded = before?.run === newest && before.status === 'running' && next.status !== 'running'
  if (hasEnded) {
    const failed = next.cases.filter(row => row.status === 'failed' || row.status === 'broken').length
    const passed = next.cases.filter(row => row.status === 'passed').length
    $.ui.toast(`Testence ${newest}: ${passed} passed${failed ? `, ${failed} failed` : ''}`)
  }
}

export const register: Register = (on, options) => {
  config = {
    runsDir: (options?.runsDir as string | undefined) || '',
    python: (options?.python as string | undefined) || 'python',
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'testence-runs',
      description: 'Show the newest Testence run in a pane; with a folder, follow that runs/ folder',
    })
    $.clock.every(1000, () => poll($))
    return next(e)
  })

  on('command.run', { command: 'testence-runs' }, async ($, e) => {
    const asked = e.args.trim()
    if (asked) {
      if (!(await $.fs.exists(asked))) return { text: `No folder ${asked}.` }
      await $.store.set(FOLDER_KEY, asked)
      last = ''
    }
    await poll($)
    await $.ui.open({ id: PANE, title: 'Testence run' })
    return { text: `Following ${await runsDir($)}.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const value = await read($, summary)
    if (!value) {
      return (
        <Box flexDirection="column" gap="sm" paddingY="sm">
          <Text weight="semibold">No Testence run yet</Text>
          <Text size="footnote" dimColor>
            Looking in {await runsDir($)}
          </Text>
          <Text size="footnote" dimColor>
            /testence-runs &lt;runs folder&gt; follows another project
          </Text>
        </Box>
      )
    }

    const count = (...statuses: CaseRow['status'][]) => value.cases.filter(row => statuses.includes(row.status)).length
    const passed = count('passed')
    const failed = count('failed', 'broken')
    const running = count('running')
    const skipped = count('skipped')
    const done = passed + failed + skipped
    const total = Math.max(value.total, 1)
    const state = value.status === 'running' ? 'running' : failed > 0 ? 'failed' : value.status
    const stateColor = state === 'running' ? 'suggestion' : state === 'passed' ? 'success' : state === 'failed' ? 'error' : 'warning'
    const percent = (part: number) => `${Math.round((part / total) * 100)}%`

    const files = [...new Set(value.cases.map(row => row.file))]

    return (
      <Box flexDirection="column" gap="md" paddingY="sm">
        <Box flexDirection="column" gap="xs">
          <Box flexDirection="row" justifyContent="space-between" alignItems="center">
            <Text color={stateColor} weight="semibold" size="heading">
              {state === 'running' ? 'Running' : state === 'passed' ? 'Passed' : state === 'failed' ? 'Failed' : state}
            </Text>
            <Text tabular size="heading">
              {done}/{value.total}
            </Text>
          </Box>
          <Box flexDirection="row" height={1} width="100%" backgroundColor="inactive">
            <Box width={percent(passed)} backgroundColor="success" />
            <Box width={percent(failed)} backgroundColor="error" />
            <Box width={percent(running)} backgroundColor="suggestion" />
          </Box>
          <Box flexDirection="row" justifyContent="space-between">
            <Text size="footnote" tabular>
              <Text color="success">✓ {passed}</Text>
              {'   '}
              <Text color={failed ? 'error' : undefined} dimColor={!failed}>
                ✗ {failed}
              </Text>
              {'   '}
              <Text dimColor>○ {value.total - done - running}</Text>
            </Text>
            <Text size="footnote" dimColor tabular>
              {value.profile ?? '—'}
              {value.durationMs !== null ? ` · ${seconds(value.durationMs)}` : ''}
            </Text>
          </Box>
          <Text size="caption" dimColor mono wrap="truncate-middle">
            {value.run}
          </Text>
        </Box>

        {files.map(file => {
          const rows = value.cases.filter(row => row.file === file)
          const fileDone = rows.filter(row => row.status !== 'queued' && row.status !== 'running').length
          return (
            <Box flexDirection="column" gap="xs">
              <Box flexDirection="row" justifyContent="space-between">
                <Text size="caption" weight="semibold" dimColor mono>
                  {file}
                </Text>
                <Text size="caption" dimColor tabular>
                  {fileDone}/{rows.length}
                </Text>
              </Box>
              {rows.map(row => {
                const { number, title } = caseTitle(row.name)
                const isRunning = row.status === 'running'
                return (
                  <Box
                    flexDirection="column"
                    paddingX="xs"
                    backgroundColor={isRunning ? 'subtle' : undefined}
                  >
                    <Box flexDirection="row" gap="sm" alignItems="center">
                      <Box width={2}>
                        <Text color={COLOR[row.status]} dimColor={row.status === 'queued'}>
                          {SYMBOL[row.status]}
                        </Text>
                      </Box>
                      {number && (
                        <Text tabular dimColor>
                          {number}
                        </Text>
                      )}
                      <Box flexGrow={1} flexShrink={1} minWidth={0}>
                        <Text wrap="truncate-end" dimColor={row.status === 'queued'} weight={isRunning ? 'medium' : undefined}>
                          {title}
                        </Text>
                      </Box>
                      <Text size="footnote" tabular dimColor>
                        {seconds(row.durationMs)}
                      </Text>
                    </Box>
                    {isRunning && row.step && (
                      <Box paddingLeft={4}>
                        <Text size="footnote" color="suggestion" wrap="truncate-end">
                          step {row.steps} · {row.step}
                        </Text>
                      </Box>
                    )}
                    {row.error && (
                      <Box paddingLeft={4}>
                        <Text size="footnote" color="error" mono wrap="wrap">
                          {row.error}
                        </Text>
                      </Box>
                    )}
                  </Box>
                )
              })}
            </Box>
          )
        })}
      </Box>
    )
  })
}
