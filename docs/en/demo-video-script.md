# 90-second demo recording script

Record one continuous terminal session against the candidate wheel digest. Keep the
clock visible and publish the resulting receipt with the same run IDs.

- **0–10 s:** show the empty directory and run
  `testence demo run --project testence-demo --json`.
- **10–35 s:** show the healthy run: pytest exit 0, execution `passed`, assurance
  `verified`, and its local report path.
- **35–60 s:** show the intentional false-green: pytest exit 1, execution `failed`,
  assurance `violated`, claim `onboarding.defect.detected` and the UI/API difference.
- **60–78 s:** open the standalone report and trace claim → assertion → evidence.
- **78–90 s:** show the machine receipt, both run IDs and the exact wheel SHA-256.

Do not splice a different run into the report view. Do not expose usernames, local
secrets or unrelated filesystem paths. The final video is an external launch asset and
is still required; this script alone does not satisfy G8.
