# ADR-0028: A JUnit exporter beside `--junitxml`

Status: accepted (amends ADR-0013).

## Context

ADR-0013 left JUnit XML to `pytest --junitxml`, which writes it correctly under `-n`
and which every CI parses. That file carries pass/fail and a message, nothing else:
no Testence identity, no test-management case id, no intent steps, no evidence. The
tools most QA teams report into — TestRail through `trcli`, Xray, Jenkins and
GitLab — ingest JUnit and read exactly those extras from it: case ids from
`<properties>`, step results from TestRail's `testrail_result_step`, files from
`[[ATTACHMENT|path]]` lines. A Testence suite could reach none of them.

## Options compared

- **Keep `--junitxml` only.** Zero code; the ids and the evidence stay unreachable.
- **Hook pytest's JUnit writer** (`record_property` from the plugin). Couples the
  report to the live session again, which ADR-0013 exists to avoid, and cannot ship
  the redacted evidence files.
- **A ledger exporter like the others.** A pure function of the run, the same
  identity, redaction and attachment policy as Allure.

## Decision

`testence export --to junit` writes `junit.xml` plus `attachments/<test>/…`. One
`<testsuite>` per test file; `<failure>` for a product disagreement, `<error>` for a
broken or aborted test, `<skipped>` for skipped and not-run tests — the split Allure
makes. Each `<testcase>` carries `testence.*` identity properties and the Allure ID.
`@pytest.mark.testence(tms={...})` adds case ids: `testrail` as `test_id` (with
`testrail_result_step` per leaf step and `testrail_attachment` per file), `xray` as
`test_key` (with `requirements` from the PlanSpec), anything else as `tms.<system>`.
The same ids reach Allure as labels and CTRF as `labels`.

The XML is pytest's default dialect (`junit_family=xunit1`): Jenkins' `junit-4.xsd`
except `<properties>` and `file` on a test case, where the tools above read ids.
`--junitxml` stays the recommendation when a job only needs pass/fail.

## Consequences

JUnit becomes a first-class sink with goldens and a shape test. Two property names
mean different things in different tools (`test_id` is TestRail's `C123` and Xray's
numeric issue id), so a file is written for the systems a test declares, not for all.

## Tripwire

If a platform needs a property or layout this dialect cannot carry, that platform gets
its own exporter module rather than a flag on this one.
