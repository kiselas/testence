import { expect, mock, test } from 'claude-code/testing'

const PANE = {
  plugin: 'testence-runs',
  component: 'Pane',
  requestId: 'testence-runs',
  props: {
    title: 'Testence run',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const SUMMARY = {
  profile: 'dev3',
  status: 'running',
  startedAt: '2026-11-02T11:57:36Z',
  durationMs: null,
  total: 3,
  cases: [
    { nodeid: 'a.py::test_12_drag', name: 'test_12_drag', file: 'a.py', status: 'passed', durationMs: 20163.6, step: null, steps: 32, error: null },
    { nodeid: 'a.py::test_13_form', name: 'test_13_form', file: 'a.py', status: 'failed', durationMs: 15006.1, step: null, steps: 27, error: "AssertionError: assert {'green'} == {'red'}" },
    { nodeid: 'a.py::test_14_list', name: 'test_14_list', file: 'a.py', status: 'running', durationMs: null, step: 'open the Rule group list', steps: 7, error: null },
  ],
}

test('the pane shows the newest run with its cases, on every surface', async ($, on) => {
  // Nothing sits beneath the plugin: these hooks stand for the engine and the disk.
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'testence-runs' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('store.get', () => ({ value: 'C:/project/runs' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.list', (_, e) =>
    String(e.path).endsWith('runs')
      ? { value: [{ name: 'r-1', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }, { name: 'r-2', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }
      : { value: [{ name: 'run.jsonl', kind: 'file', size: 100, mtimeMs: 1, isLink: false }] },
  )
  on('process.run', (_, e) => {
    expect(e.argv.at(-1)).toBe('C:/project/runs/r-2/run.jsonl')
    return { value: { exitCode: 0, stdout: JSON.stringify(SUMMARY), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })

  on('command.run', () => ({ text: '' }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.command.run({ command: 'testence-runs', args: '', origin: 'typed', presentation: 'shown' } as never)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /^Running$/ }))?.text).toBe('Running')
    expect((await ui.find({ type: 'Text', text: /^2\/3$/ }))?.text).toBe('2/3')
    expect((await ui.find({ type: 'Text', text: /^r-2$/ }))?.text).toBe('r-2')
    expect((await ui.find({ type: 'Text', text: /^drag$/ }))?.text).toBe('drag')
    expect((await ui.find({ type: 'Text', text: /green/ }))?.text).toContain("{'red'}")
    expect((await ui.find({ type: 'Text', text: /step 7/ }))?.text).toBe('step 7 · open the Rule group list')
    await ui.unmount()
  }
})

test('with no run yet the pane says where it looks', async ($, on) => {
  on('store.get', () => ({ value: 'C:/project/runs' }))
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /No Testence run yet/ }))?.text).toBe('No Testence run yet')
  expect((await ui.find({ type: 'Text', text: /Looking in/ }))?.text).toBe('Looking in C:/project/runs')
  await ui.unmount()
})
