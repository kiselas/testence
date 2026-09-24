# ADR-0025: Redacted parameter display values in the ledger

Status: accepted.

## Context

ADR-0019 kept only SHA-256 digests of test parameters, so no secret parameter value
could reach evidence. Every exported Allure parameter read `sha256:...`: a TestOps user
could not tell which role, browser or amount failed, and a migrated allure-pytest suite
lost the readable values it had.

## Options compared

- **Digests only.** Safe, unreadable.
- **Raw values.** Readable, and a password parameter lands in a shared TestOps.
- **Redacted display values.** The allure-pytest representation of each value, passed
  through the evidence redaction policy (ADR-0024) as a name/value record, so a
  secret-named parameter is masked and secret-shaped values are removed.

## Decision

`test.start.allure.parameters` records `{name, value}` display values computed while the
values exist; digests stay the identity (`parameters`, `variant_id`). The Allure
exporter shows the display values and marks a redacted one `mode: "masked"`.
`export.allure.parameters: digest` restores digest-only output. Parameter values that
pytest puts into test ids are outside this redaction; the plugin warns when a
secret-named parameter's value appears in an id.

## Consequences

Parameter values appear in evidence and exports unless the policy redacts them. Hashes
for allure-pytest `historyId` are computed from raw values at collection time, as
allure-pytest does, and only the hash is stored.

## Tripwire

A secret-named parameter value in any exported file, or a report of a secret parameter
value in a card that the policy should have caught, reopens this decision.
