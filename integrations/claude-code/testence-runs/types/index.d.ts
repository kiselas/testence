export type CaseStatus = 'queued' | 'running' | 'passed' | 'failed' | 'broken' | 'skipped'

export type CaseRow = {
  nodeid: string
  name: string
  file: string
  status: CaseStatus
  durationMs: number | null
  step: string | null
  steps: number
  error: string | null
}

export type RunSummary = {
  run: string
  profile: string | null
  status: string
  startedAt: string | null
  durationMs: number | null
  total: number
  cases: CaseRow[]
  updatedAtMs: number
}

declare module 'claude-code' {
  interface PluginState {
    'testence-runs': { summary: Shaped<RunSummary | null> }
  }
}
