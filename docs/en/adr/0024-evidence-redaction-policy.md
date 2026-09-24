# ADR-0024: Part- and shape-based evidence redaction with a recorded policy

Status: accepted.

## Context

Evidence redaction matched a fixed set of exact normalized key names. Common spellings
such as `authToken`, `sessionToken`, `X-Api-Key`, `csrfToken` or `pwd`, tokens in free
text, OAuth `code` and `session` query parameters, and secrets named in data (an oracle
diff `{"field": "authToken", "ui": ...}`) reached the ledger and the evidence pack in
clear text. The Allure exporter copies pack files into `allure-results`, and a team
uploads them to a shared TestOps instance. Screenshots had no masking at all. Evidence
already written by an older release could not be fixed after the fact.

## Options compared

- **More exact names.** Cheap, but every spelling is another miss; the set had already
  failed on the most common JSON conventions.
- **Entropy detection.** Catches unknown tokens, but Testence's own evidence is full of
  high-entropy digests and ids; false positives would erase proof.
- **Part- and shape-based rules plus a project policy.** Names are split into parts
  (camelCase, `_`, `-`, `.`); strong fragments (`token`, `password`, `secret`, `cookie`,
  `csrf`, `jwt`, ...) match anywhere, short words (`pwd`, `pin`, `sid`, `otp`, `pass`,
  `session`, `sig`) only as a whole part, and `<api|access|private|...> key` as a pair.
  Values are matched by shape (JWT, provider prefixes, Luhn-valid card numbers). The
  project adds or exempts names and opts into PII.

## Decision

Adopt part- and shape-based rules with a `RedactionPolicy` configured under
`evidence.redact` (`keys`, `allow_keys`, `url_params`, `env`, `pii`). A dict whose
`name`/`field`/`key`/`header`/`param` slot names a secret has its
`value`/`ui`/`api`/`expected`/`actual`/`old`/`new` slots redacted; other slots such as
an element fingerprint's role and selector are kept. Email and phone redaction is
opt-in because tests assert user emails.

The policy carries names only and is recorded in `run.start`. Export and report apply
it again to events and text attachments, so evidence from before a rule reaches an
integration redacted; the run directory of record is never rewritten. `testence export
--attachments full|minimal|none` limits which pack files leave the machine.

`evidence.mask` lists targets that every screenshot paints black through Playwright's
`mask`. A visual baseline records non-empty masks in its profile: changing masks makes
the baseline incompatible (inconclusive) instead of producing a pixel verdict, and
unmasked profiles keep their earlier shape.

## Consequences

Some fields are over-redacted (`session_status` hides its value); `allow_keys` exempts
them and Testence exempts its own counters (`sections_est_tokens`, `session_ms`).
Arbitrary personal or proprietary text is still only as protected as the configured
policy, and pixels are only protected where a mask is configured. Invalid settings
stop the pytest session before any test.

## Tripwire

Any canary from `tests/test_redaction_policy.py` found in a persisted or exported file,
an over-redacted negative control, or a baseline accepted after a mask change blocks
this decision. Revisit if real projects report redaction erasing the evidence needed to
classify a failure.
