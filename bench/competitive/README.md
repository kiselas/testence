# Competitive replay benchmark

This benchmark compares the deterministic replay path of Testence with four
code-first runners: Playwright Test (TypeScript), pytest-playwright (Python), Cypress
and SeleniumBase. It deliberately does **not** turn the result into a composite product
score.

Every arm executes the same six intent-bearing steps against `bench/target/index.html`:

1. open the page;
2. click the increment button;
3. assert that the counter is `1`;
4. fill a name;
5. click add;
6. assert that the row appeared.

Each arm is written the way its documentation recommends (`bench/competitive/*/`,
`bench/node/competitive/`, `bench/node/cypress/`). The target server is started before
timing. Every measured sample is a fresh runner process and includes test discovery,
browser launch, the test, reporting and shutdown. One warm-up run per arm is excluded.
Samples are taken in rounds: each round runs every arm once, in an order shuffled with a
fixed seed. Retries, tracing, video and screenshots are disabled. Testence still writes
its normal pass-run ledger; the other arms use their normal reporters.

## Setup

Each competitor runs in its own environment with its ordinary install, so no arm pays
for another's plugins (SeleniumBase alone brings pytest-html, xdist and rerunfailures).

```bash
uv sync --locked --extra dev
uv venv .tmp/bench-pytest-playwright --python 3.12
uv pip install --python .tmp/bench-pytest-playwright/<bin>/python -r bench/competitive/requirements-pytest-playwright.txt
uv venv .tmp/bench-seleniumbase --python 3.12
uv pip install --python .tmp/bench-seleniumbase/<bin>/python -r bench/competitive/requirements-seleniumbase.txt
npm ci --prefix bench/node
npx --prefix bench/node cypress install
```

`<bin>` is `Scripts` on Windows and `bin` elsewhere.

## Run

```bash
uv run python bench/competitive/run.py --repeats 30 --channel chrome
```

`--channel` picks one browser for every arm that can use it: `chrome` (system Chrome,
used by the hosted workflow `.github/workflows/benchmarks.yml`) and `msedge` put all
five arms on the same build; `chromium` is Playwright's bundled browser, which Cypress
and SeleniumBase cannot drive, so on it they fall back to Electron and system Chrome.
The browser of every arm is recorded in the result. `--arms` runs a subset.

The machine-readable result (`testence/competitive-replay/2`) is written to
`bench/results/competitive-replay.json`: git revision, environment, every tool's
version, the round order, raw samples, median with a bootstrap 95% interval, p95, and a
transparent source-size proxy. Source size is **not authoring time**; authoring and
maintenance are measured separately with agent sessions, as the benchmark protocol
describes.

Commercial agentic platforms are not silently approximated here. Momentic, mabl,
KaneAI, Reflect and similar hosted arms require an account, a disclosed plan/model and
vendor execution. Until those arms are run, their cells must remain `not measured`.
