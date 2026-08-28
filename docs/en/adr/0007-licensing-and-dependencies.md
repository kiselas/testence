# ADR-0007: Apache-2.0 and a permissive runtime dependency policy

Status: accepted (2026-08-25)

## Context

Testence is intended for public use and extension. License and dependency rules must
be explicit before the first repository history is created.

## Decision

- Project license: Apache-2.0.
- Runtime dependencies must use permissive licenses (MIT, Apache, BSD or PSF).
- The runner must not require a hosted service, model-provider SDK or telemetry.
- Development tools should remain permissive where practical.
- Dependency licenses and forbidden imports will be checked in CI before release.

## Consequences

The core remains usable offline and model-provider neutral. Integrations that require
their own SDKs should ship as separate packages and register through a versioned seam.

## Tripwire

If an essential capability is available only under an incompatible license or as a
mandatory hosted service, record a new decision with the concrete capability and
distribution impact before adding it.
