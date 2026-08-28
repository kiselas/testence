# Compute kernels (normative)

The seam where a native implementation may replace Python without touching callers.
Decision record and measured costs: [ADR-0009](adr/0009-kernel-boundary.md).

## What may be a kernel

A function qualifies only if it is **pure** and **plain-data**:

| requirement | why | counter-example |
|---|---|---|
| no I/O | FFI boundaries and file handles do not mix; failures must be trivially retryable | `EvidenceWriter` (fsync per event) stays Python |
| no clocks / randomness | reproducibility: the same ledger must aggregate identically forever | timestamp stamping stays in the writer |
| no global state | backends must be swappable mid-process for differential tests | no memoization inside a kernel |
| plain data in/out | bytes, str, int, float, list, dict only — what crosses FFI cheaply | no `Target`, no Playwright objects, no callbacks |
| deterministic errors | `ValueError` with a message, or errors as data | no partial results |

If a candidate fails any row, it belongs in ordinary Python code. The point of the
boundary is that everything inside it is *mechanically* portable.

## Current kernels

| kernel | role | native candidate? |
|---|---|---|
| `parse_ledger(bytes) -> list[dict]` | read run.jsonl; hot when aggregating many runs | weak — `json.loads` is already C |
| `estimate_tokens(str) -> int` | evidence budget enforcement | no — it is `len()` on bytes |
| `percentiles(list, list) -> list` | metric aggregation | no — it is `sorted()` |
| `diff_aria(str, str) -> dict` | between-step page diffs (E3), "what changed" for triage | **yes** — pure-Python `difflib`, dominates corpus replay |
| `score_candidates(dict, list) -> list[float]` | heal-proposal ranking (H6) | **yes** — pure-Python similarity loops |

`diff_aria` semantics worth knowing as a consumer: a node present on both sides at a
different position is reported as `moved`, not as `removed` + `added`. Triage depends
on this distinction — an element *gone* from the page is a `real_bug`, while
reordering is not.

## Selecting a backend

```bash
TESTENCE_KERNELS=auto       # default: native if importable, else reference
TESTENCE_KERNELS=reference  # force pure Python (CI conformance, differential runs)
TESTENCE_KERNELS=native     # force native; hard error if missing or ABI-mismatched
```

`auto` falling back silently is intended for users; `native` failing loudly is
intended for benchmarks, so a "native" measurement can never turn out to have been
Python. Every `metrics.json` and every run's `run.start` fingerprint records the
active backend name and ABI.

## Adding a native backend

1. Implement the ABI in a crate exposing a Python module named `testence_kernels`
   (PyO3 + maturin), with module attributes `name: str` and `abi: int`.
2. Add it to `BACKENDS` in `tests/test_kernels.py`. The suite is parametrized over
   backends; it must pass **unchanged** — the reference implementation is normative,
   so any disagreement is a bug in the native backend, not a test to relax.
3. Prove the win on `bench/kernels.py`: ≥ 5× on the same workload, or the crate is
   not worth the FFI dependency and build complexity.
4. Ship it as a separate optional wheel, then wire it into the reserved
   `pip install testence[native]` extra. It must never become a hard dependency: an
   install with no compiler must remain fully functional.

## Changing a kernel's contract

Output shape changes are schema changes: bump `KERNEL_ABI`, update the conformance
suite, and note the change in ADR-0009. Backends declare the ABI they implement, and
a mismatch is refused at import — an old native wheel silently returning an old shape
is exactly the failure mode this guards against.
