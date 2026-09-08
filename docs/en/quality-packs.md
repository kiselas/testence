# Multi-project quality packs

A quality pack is a directory with `quality-pack.json` and digest-listed policy,
fixture-interface, oracle-recipe or selection files. Apply one exact revision:

```bash
testence quality apply ../team-quality-pack . --json
```

The command validates every byte, rejects paths outside the pack and credential-like
files, writes the fixed name/version/digest into `testence.json`, and records managed
files in `.testence/quality-pack.lock.json`. Updating replaces a file only when it still
matches the previous pack. A human edit produces a conflict. A deliberate local edit
needs `.testence/quality-overrides.json` with path, reason, owner and an unexpired
`YYYY-MM-DD` date; it is preserved and reported.

Each accepted revision retains the previous files under
`.testence/quality-pack-history/`. Restore an exact digest with:

```bash
testence quality rollback . --digest sha256:...
```

Rollback refuses a concurrently edited target and never deletes history. Aggregate
reconciled runs without copying raw evidence:

```bash
testence quality summary runs/r-catalog runs/r-billing runs/r-admin --json
```

The summary groups by project and emits only actionable violations, missing execution,
missing proof and integrity failures. `--project`, `--owner`, `--risk` and `--case`
filter the queue. Requirements/manual descriptions remain in TMS, executable policy in
Git, execution facts in immutable runs, and diagnosis/repair in bound proposals.
