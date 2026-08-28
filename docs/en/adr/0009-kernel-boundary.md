# ADR-0009: Compute-kernel boundary for future native (Rust) backends

Status: accepted (2026-08-25) — seam built, native backend **not** justified yet

## Context

Python is the primary language (ADR-0002): the ecosystem fits, and LLM agents — a
first-class user of this codebase — read and write it best. That makes "can we
rewrite hot spots natively later?" an architecture question to answer *now*, while
it is free, rather than a refactor to attempt under pressure later.

The prerequisite is knowing where CPU actually goes. Two planes:

- **Driving plane** (engine, DSL, pytest wiring) — I/O-bound. A step is one CDP
  round-trip: ~10 ms measured, of which the Python↔driver IPC is ~0.85 ms (E1,
  ADR-0002). Rewriting this in any language changes nothing; it waits on Chrome.
- **Analysis plane** (ledger parsing, snapshot diffing, candidate scoring, token
  counting) — CPU-bound, pure functions over plain data. This is the only place a
  native backend can pay.

## Decision

Introduce `testence.kernels`: a narrow, versioned ABI (`KERNEL_ABI`) of **pure**
functions with a normative pure-Python reference backend and pluggable
alternatives. Rules (full text in [`kernels.md`](../kernels.md)):

1. Plain data only across the boundary (bytes/str/numbers/lists/dicts) — the FFI
   contract. No framework or Playwright types.
2. Pure: no I/O, clocks, randomness, or global state. `EvidenceWriter` is
   deliberately *not* a kernel — it is fsync'd I/O and must stay in Python.
3. Reference implementation defines correctness; a native backend must pass the same
   conformance suite unchanged (`tests/test_kernels.py`, parametrized over backends).
4. Native is an optional wheel (`testence_kernels`), selected by `TESTENCE_KERNELS=
   auto|reference|native`. `auto` silently falls back; `native` fails loudly so a
   benchmark can never mis-attribute a Python number to Rust. ABI mismatch is
   refused, never silently tolerated.
5. Testence stays fully functional with zero native artifacts — a Rust toolchain is
   never required to install, develop, or contribute.

Current kernels: `parse_ledger`, `estimate_tokens`, `percentiles`, `diff_aria`,
`score_candidates`. The last two exist because experiments E3 (snapshot diffs
instead of full snapshots) and hypothesis H6 (heal proposals from fingerprints)
depend on them; they are the plausible native candidates.

## Measured cost (bench/kernels.py, Windows 11, Python 3.12.4, reference backend)

| kernel | workload (fleet-scale) | median | per unit |
|---|---|---|---|
| `parse_ledger` | 80 000 events / 22 MiB (~a month of CI) | 413 ms | 5.2 µs/event |
| `diff_aria` | 200 diffs of 500-node snapshots (one suite) | 303 ms | 1 517 µs/diff |
| `score_candidates` | 100 rankings × 300 candidates | 303 ms | 3 035 µs/ranking |
| `percentiles` | 80 000 samples, 2 percentiles | 2.1 ms | — |
| `estimate_tokens` | 4 MiB of evidence text | 0.9 ms | — |

Reading these honestly:

- **No kernel justifies Rust today.** The most expensive one, `diff_aria`, costs
  ~0.3 s per suite's worth of diffs — 0.1% of the 5-minute suite budget.
- `parse_ledger` is already backed by C (`json.loads`); a native rewrite buys maybe
  3–5×, on 0.4 s. Not worth an FFI dependency.
- `percentiles` and `estimate_tokens` are permanently off the table — they are
  `sorted()` and `len()` in disguise. Their kernel membership is for ABI uniformity,
  not for future speed.
- The real native candidates are the two pure-Python algorithms, `diff_aria` and
  `score_candidates` (both `difflib`-based, no C underneath), and only at
  *corpus-replay* volumes: ablation experiments E2–E4 re-diff whole corpora
  thousands of times, which is where 1.5 ms/diff turns into minutes.

## Consequences

- Refactoring cost when Rust becomes justified is near zero: implement the ABI in a
  separate crate, publish a wheel, flip an env var. Callers never change.
- Differential testing is available from day one: the same suite runs both backends,
  and `metrics.json` records which backend produced every number.
- Small ongoing cost: kernels must stay pure, so a tempting shortcut (caching inside
  a kernel, reading a file in `parse_ledger`) is a review-time rejection.
- Future kernels that arrive already needing speed — a real BPE tokenizer replacing
  the byte estimate is the obvious one — plug into a seam that already exists.

## Tripwire (pre-registered)

A kernel earns a native implementation when **either**:
1. it exceeds 5% of the suite wall-clock budget (> 15 s of a 5-minute run), or
2. it exceeds 10 s in a routine analysis workflow (corpus replay, `testence bench`
   aggregation, report generation).

At today's costs that means > 10 000 `diff_aria` calls per workflow (a 500-case suite
diffing every step, or a corpus ablation) — a scale we should reach before writing
any Rust, not before designing for it. `bench/kernels.py` is re-run per release; the
first kernel to cross a threshold gets the crate, alone, and must beat the reference
by ≥ 5× on the same bench to be kept.
