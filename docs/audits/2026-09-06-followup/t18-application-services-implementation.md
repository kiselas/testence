# T18 application services implementation receipt

Date: 2026-09-06. Status: locally implemented and verified.

## Delivered behavior

The public CLI now exposes `doctor`, `init`, `run`, `inspect`, and validated
`verdict submit` application services. Initialization is additive and idempotent:
it creates a hidden synthetic example, requirement, project config and a digest-bound
scaffold manifest, while refusing to overwrite conflicting files. Ordinary pytest
collection does not discover the hidden example until the operator opts in.

`doctor` returns a machine-readable Python/settings/packaged-schema/Chromium/workspace
diagnostic without reading or printing credentials. `run` supplies an explicit project
root and stable run identity. `inspect` fails closed through the reconciled run reader.
`verdict submit` validates the candidate against the exact plan and immutable evidence
pack, then writes an atomic, idempotent submission receipt inside that pack.

The scaffold and submission schemas are packaged and included in the schema inventory.
ADR-0020 documents the application boundary and EN/RU indexes and quickstart content
link to the implemented commands.

## Consumer receipt

[`outputs/.../t18-wheel-consumer`](../../../outputs/audit-2026-09-06-followup/t18-wheel-consumer/README.md)
contains a wheel and sdist plus a fresh consumer project. The installed console script
created the project, passed `doctor`, ran the synthetic example and inspected a complete
run: one test passed, one assurance result verified, and zero integrity errors. An
isolated import resolved to the consumer virtual environment's `site-packages`.

## Verification

| Check | Observed |
|---|---|
| Full pytest | `309 passed, 2 skipped in 118.89s` |
| Ruff check | passed for source, tests, benchmark and corpus code |
| Ruff format | formatted the two outstanding corpus files |
| mypy | success, 49 source files |
| Installed wheel | doctor/run/inspect exits all `0`; one passed and verified test |

## Boundary

This closes the local application-service and installed-wheel synthetic workflow in
T18. Existing-suite compatibility is covered by the plugin's inert defaults and the
opt-in hidden scaffold regression tests. External agent-client acceptance remains T22.
This receipt becomes immutable only after review and commit.
