"""Testence — agent-first browser test framework.

Public API surface (kept deliberately small; Playwright never leaks through it):
- testence.dsl.Actions / Target — step primitives for project ActionMaps
- testence.adapters — AuthAdapter / SeedAdapter protocols
- testence.evidence — run.jsonl schema and writer
- testence.oracle — API-oracle diff helpers
"""

__version__ = "0.1.0.dev0"

SCHEMA_VERSION = "testence/1"
