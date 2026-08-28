# ADR-0005: Self-contained single-file HTML report

Status: accepted (2026-08-25)

## Context

Humans are the second first-class reader. Testers will not trust a verdict they
cannot verify. Reports must be transparent and work where runs happen: a developer's
machine, a GitLab CI artifact browser, a shared folder — all offline contexts.

## Options compared

| | single-file static HTML | served SPA (report server) | Allure report as the only human view |
|---|---|---|---|
| Opens from file:// / CI artifacts | yes | no (needs a process) | needs `allure serve` or TestOps |
| Zero-install for a reviewer | yes | no | no |
| Owns the verdict→evidence drill-down | yes, our design | yes | no (Allure model ≠ evidence packs) |
| Brandable for a future OSS product | yes | yes | no |
| Effort | low (template + vanilla JS) | high | none |

## Decision

One HTML file rendered from run.jsonl (`testence report <run-dir>`): no external
assets, no CDN, vanilla JS, light/dark via `prefers-color-scheme`. It is a *view*
over the same ledger agents read — never a second source of truth. Allure remains an
*export* for existing reporting pipelines, not the primary report.

Measured requirements (checked by tests / bench): opens offline; ≤ 5 MB for a
20-case run; renders ≤ 2 s; click depth from verdict to raw evidence ≤ 3
(`report_click_depth`).

## Consequences

- Report ships with every run automatically; a red CI job carries its own
  explanation as an artifact.
- Screenshots/packs stay as sibling files (linked, not embedded) to hold the size
  budget; the report degrades gracefully when moved without them.
- Theming/i18n hooks live in CSS variables from day one (future market-facing
  polish is a palette swap, not a rewrite).

## Tripwire

Any measured requirement broken on real runs (> 5 MB, > 2 s open, depth > 3) →
re-architect the report (sharding/lazy assets); do not "compress a bit more".
