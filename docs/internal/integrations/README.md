# Platform recipes awaiting a live check (stage 4, L10)

Not linked from the public documentation. A recipe moves to `docs/{en,ru}/reporting.md`
only after the owner has run it against a real instance of the platform (plan rule Q1).
Each step up to the upload is reproduced by `tests/test_export_junit.py`.

## TestRail (`trcli`)

```bash
testence export "$RUN" --to junit --out junit-results
trcli -y -h "$TESTRAIL_URL" --project "$PROJECT" -u "$TESTRAIL_USER" -k "$TESTRAIL_KEY" \
  parse_junit -f junit-results/junit.xml --case-matcher property \
  --title "Testence $RUN"
```

Expected: results land on cases `C…` from `tms={"testrail": ...}`; step results from
`testrail_result_step`; evidence files from `testrail_attachment` (paths are relative to
`junit-results/`, so run `trcli` from that directory if it resolves them against the
working directory).

To verify: case matching by property; step results on a "Test Case (Steps)" template;
attachment upload; a multi-case `test_id` (`C1, C2`).

## Xray (Jira Cloud)

```bash
testence export "$RUN" --to junit --out junit-results
curl -H "Content-Type: text/xml" -H "Authorization: Bearer $XRAY_TOKEN" \
  --data @junit-results/junit.xml \
  "https://xray.cloud.getxray.app/api/v2/import/execution/junit?projectKey=$PROJECT"
```

Expected: each result updates the Test in `test_key`; `requirements` link the Test to
the PlanSpec requirements. Not written yet: `testrun_evidence` (base64 files); evidence is
referenced by `[[ATTACHMENT|…]]` lines only.

To verify: the `test_key` mapping; requirement linking; whether evidence should be
embedded as `testrun_evidence`.

## Zephyr Scale

Open. Its JUnit listener writes a custom JSON format (`zephyrscale_result.json`), and
the matching rule for plain JUnit XML could not be read (documentation behind a 403).
Needs the owner's instance to decide between `--to junit` with keys in test names and
a dedicated exporter.

## Test IT, Qase, ReportPortal

Test IT and Qase import Allure results (`testit-cli`, `qasectl testops result upload
--format allure`); ReportPortal imports JUnit. Commands to be written and checked the
same way.
