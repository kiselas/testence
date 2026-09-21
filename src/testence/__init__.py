"""Testence — agent-first browser test framework.

Public API surface (kept deliberately small; Playwright never leaks through it):
- testence.dsl.Actions / Target — step primitives for project ActionMaps
- testence.adapters — AuthAdapter / SeedAdapter protocols
- testence.evidence — run.jsonl schema and writer
- testence.oracle — API-oracle diff helpers
"""

from .identity import EVIDENCE_SCHEMA

__version__ = "0.1.0a1"

SCHEMA_VERSION = EVIDENCE_SCHEMA
