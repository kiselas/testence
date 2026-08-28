"""Compute-kernel ABI: the seam where a native (Rust) backend may replace Python.

Why kernels exist
-----------------
Driving a browser is I/O-bound: a step is one CDP round-trip (~10 ms, measured in
E1), so no language change helps there. The CPU work in this framework lives in the
*analysis* plane — parsing ledgers, diffing page snapshots, scoring element
candidates, counting tokens. Those are pure functions over plain data, which is
exactly what can be swapped for a native implementation without touching callers.

ABI rules (what makes a kernel portable)
----------------------------------------
1. **Pure.** No I/O, no globals, no clocks, no randomness. Same inputs → same output.
2. **Plain data only.** bytes / str / int / float / list / dict of those. No Python
   objects with behavior, no framework types, no Playwright types. This is the FFI
   boundary: anything here must survive serialization to a native backend.
3. **Total.** Errors are returned as data or raise ``ValueError`` with a message;
   no partial state, nothing to clean up. A crash in a kernel must never leave a run
   half-recorded (which is why ``EvidenceWriter`` — with its fsync — is deliberately
   NOT a kernel: it is I/O and must stay in Python).
4. **Versioned semantics.** Changing a kernel's output shape is a schema change:
   bump ``KERNEL_ABI`` and update the conformance suite. Backends declare the ABI
   they implement; a mismatch is refused loudly at import, never silently accepted.
5. **Reference-first.** The pure-Python implementation is normative. A native backend
   is an *optimization* that must agree with it bit-for-bit on the conformance corpus.
   Testence must stay installable and fully functional with zero native artifacts —
   a Rust toolchain is never a requirement for users or contributors.

Kernel selection is measured, not assumed: ``bench/kernels.py`` reports the cost of
each kernel at realistic volumes, and ADR-0009 records the pre-registered threshold
a kernel must cross before a native rewrite is justified.
"""

from __future__ import annotations

from typing import Any, Protocol

#: Bumped when any kernel's input/output contract changes.
KERNEL_ABI = 1


class KernelBackend(Protocol):
    """What a backend (reference, native, or future alternative) must provide."""

    name: str
    abi: int

    def parse_ledger(self, data: bytes) -> list[dict[str, Any]]:
        """Parse run.jsonl bytes into event dicts.

        Blank lines are skipped. Raises ValueError on malformed JSON or on an
        event whose ``v`` is not the expected schema version (the caller passes
        already-trusted files; a foreign version is a programming error, not input).
        """
        ...

    def estimate_tokens(self, text: str) -> int:
        """Estimate LLM tokens for budget enforcement. Monotonic in length."""
        ...

    def percentiles(self, values: list[float], pcts: list[float]) -> list[float | None]:
        """Linear-interpolated percentiles. Empty input → list of None."""
        ...

    def diff_aria(self, before: str, after: str) -> dict[str, Any]:
        """Structural diff of two ARIA snapshots.

        Returns ``{"added": [...], "removed": [...], "moved": int, "same": int}``
        where entries are ``{"depth": int, "role": str, "name": str}``. Used to ship
        between-step *diffs* instead of full snapshots (experiment E3) and to explain
        "what changed on the page" to a triage agent.
        """
        ...

    def score_candidates(
        self, target: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> list[float]:
        """Rank element fingerprints by similarity to a target fingerprint, 0..1.

        Feeds heal-diff proposals (hypothesis H6): when a locator drifts, the element
        that best matches the last green run's fingerprint is the candidate to
        propose. Scores are comparable within one call, not across calls.
        """
        ...
