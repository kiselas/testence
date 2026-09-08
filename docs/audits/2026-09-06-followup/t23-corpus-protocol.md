# T23 frozen correctness corpus protocol

Status: **structural protocol complete; external acceptance incomplete**.

The working tree adds `testence/correctness-corpus/1`, a public JSON Schema, a validator
and a frozen registry with exactly 40 unique cases: 20 product defects, 10 healthy
controls, 5 repairable drift cases and 5 ambiguous/infrastructure cases. Eight cases are
marked holdout. Every source path is contained in the repository and exists. The
adjacent freeze digest is
`sha256:6299a641564f940c11933248a266e04ee609dbef790ddbb5b90ead563f287ecc`.

`testence corpus validate corpus/r1-correctness-v1.json --structure-only --json` is the
CI gate and exits 0. The full command without `--structure-only` exits 3 with status
`incomplete`: zero of two required licensed OSS SUTs are registered and independent
truth review is false. That fail-closed result is preserved in
`outputs/audit-2026-09-06-followup/corpus-validation.json`.

Focused schema/protocol tests passed. T23 and G6 cannot be accepted until two targets on
different stacks record license, exact commit, reset/reproduction receipts, healthy/
bug/harmless revisions, two truth reviewers and an independent deterministic rerun.
