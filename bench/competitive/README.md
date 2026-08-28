# Competitive replay benchmark

This benchmark compares the deterministic replay path of Testence with the closest
open, runnable baseline: Playwright Test. It deliberately does **not** turn the result
into a composite product score.

Both arms execute the same six intent-bearing steps against `bench/target/index.html`:

1. open the page;
2. click the increment button;
3. assert that the counter is `1`;
4. fill a name;
5. click add;
6. assert that the row appeared.

The target server is started before timing. Every measured sample is a fresh runner
process and includes test discovery, browser launch, the test, reporting and shutdown.
One warm-up run per arm is excluded. Arms run serially so they do not compete for CPU.
Retries, tracing and video are disabled. Testence still writes its normal pass-run
ledger; Playwright uses its normal line reporter.

Run from the repository root:

```powershell
.venv\Scripts\python bench\competitive\run.py --repeats 7
```

The machine-readable result is written to `bench/results/competitive-replay.json` and
contains environment metadata, raw samples, median, p95 and a transparent source-size
proxy. Source size is **not authoring time**. A valid authoring benchmark requires
fresh, isolated agent sessions, the same prompt and acceptance tests, and review-time
measurement; the product benchmark protocol documents that separate experiment.

Commercial agentic platforms are not silently approximated here. Momentic, mabl,
KaneAI, Reflect and similar hosted arms require an account, a disclosed plan/model and
vendor execution. Until those arms are run, their cells must remain `not measured`.
