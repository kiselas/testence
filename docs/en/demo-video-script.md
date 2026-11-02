# 90-second demo recording script

Record one continuous terminal session against the candidate wheel digest. Keep the
clock visible and publish the resulting receipt with the same run IDs.

- **0–10 s:** show the empty directory and run
  `testence demo run --project testence-demo --json`.
- **10–30 s:** show the healthy run: pytest exit 0, execution `passed`, assurance
  `verified`, and its local report path.
- **30–50 s:** show the intentional false-green: pytest exit 1, execution `failed`,
  assurance `violated`, claim `onboarding.defect.detected` and the UI/API difference.
- **50–65 s:** show the negative run: the same healthy test with control `drop-save`
  (the save is acknowledged but never stored), pytest exit 1, and claim
  `onboarding.proof.recorded` `proven` in `testence inspect`. Say it: the test that
  just passed can fail for its claim.
- **65–80 s:** open the standalone report and trace claim → assertion → evidence.
- **80–90 s:** show the machine receipt, the four run IDs and the exact wheel SHA-256.

Do not splice a different run into the report view. Do not expose usernames, local
secrets or unrelated filesystem paths. The final video is an external launch asset and
is still required; this script alone does not satisfy G8.
