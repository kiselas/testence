# MCP server

`testence mcp` gives an agent the calls the write-and-prove loop needs, over the Model
Context Protocol (stdio). It is narrow on purpose: the loop an agent runs, not the
framework. Nothing in it calls a model, and the tests the agent writes still run in CI
without one ([ADR-0006](adr/0006-no-llm-in-runner.md)).

## Connect a client

Run it from the project (the directory with `testence.json`):

Claude Code, `.mcp.json`:

```json
{"mcpServers": {"testence": {"command": "testence", "args": ["mcp", "--project", "."]}}}
```

Codex, `~/.codex/config.toml`:

```toml
[mcp_servers.testence]
command = "testence"
args = ["mcp", "--project", "."]
```

OpenCode, `opencode.json`:

```json
{"mcp": {"testence": {"type": "local", "command": ["testence", "mcp", "--project", "."], "enabled": true}}}
```

Each block is that client's own format; check your client's MCP
documentation if it differs from your version. `--headed` shows the exploration browser.

## The seven tools

| tool | what it does |
|---|---|
| `testence_doctor` | checks the runtime; `target: true` also reaches `base_url`, checks credentials and tries the login |
| `testence_snapshot` | opens a page (`url`, a path on `base_url` or absolute) and lists its interactive elements; each has the `Target` that addresses it, the Python that spells it and how many elements it matches: `unique: true` is usable as is |
| `testence_click` | clicks a `Target` in the exploration browser, to see what happens before writing the step |
| `testence_fill` | fills a field; the value is not echoed back |
| `testence_run` | runs pytest through `testence run` and returns the exit code, the run directory and its summary |
| `testence_inspect` | the outcome of a run: execution and assurance counts, integrity errors, evidence packs, flaky tests |
| `testence_oracle_suggest` | the API checks a finished run implies ([testing a feature](testing-a-feature.md)) |

A session that fits in a few calls: snapshot the page, click and fill to learn what the
flow does, write an ordinary pytest file with `ex`, run it, inspect it, then ask for the
oracle suggestions and add the API check.

## What it will not do

- There is no file-writing tool: source changes stay ordinary edits under the client's own
  permissions.
- Page text is redacted with the project's policy before the agent sees it
  ([configuration](configuration.md#evidence-capture-policy)); a filled value is never
  echoed; `run_dir` must be inside the project.
- The exploration browser is separate from the browsers a run starts, and it is signed in
  with the project's `auth`. `testence_run` runs the project's own tests, which is code
  execution by design: give it only to a client you would let run `pytest`.
- Not covered yet: repairing from a proposal, verdict submission and PlanSpec tools stay on
  the CLI ([agent workflow](agent-workflow.md)).
