# T25–T26 distribution gates and portable demo

Status: **local implementation passed; hosted/video acceptance incomplete**.

CI now separates locked quality, Windows/Linux × Python 3.10/3.12 tests, Python 3.10
minimum dependencies, critical corpus/schema/docs checks, scale budgets and an
installed-wheel browser job. Actions are pinned. The final job builds wheel/sdist,
installs the wheel outside the checkout, launches real Chromium, runs both managed agent
layouts, executes the deterministic demo, emits checksums/SPDX SBOM/dependency inventory
and local provenance, and signs provenance outside pull requests. Release evidence is
uploaded with missing-file failure enabled.

The local installed-wheel run used Python 3.12.12 with Testence 0.1.0.dev0, Playwright
1.62.0 and pytest 9.1.1. It found 24 packaged schemas, installed and verified Codex and
Claude layouts, launched Chromium through the public engine, and created one healthy
`verified` result plus one expected failure with `violated` assurance. Both standalone
reports existed. Receipt: `outputs/audit-2026-09-06-followup/installed-wheel-smoke.json`.

The declared dependency floor was also exercised independently on Windows with Python
3.10.19, pytest 8.0.0, Playwright 1.49.0, pytest-xdist 3.6.1 and Playwright Chromium
build 1148: 339 tests passed and two link-creation cases skipped in 145.44 seconds.
`outputs/audit-2026-09-06-followup/minimum-dependencies.log` preserves the run.

`testence demo run --project testence-demo --json` is now the promised one-command demo.
It refuses existing run IDs, treats the intentional pytest exit 1 as accepted only when
execution and assurance show the intended defect, and returns a versioned
`testence/demo-run/1` receipt. EN/RU commands were updated. A timed recording script is
ready, but the actual 90-second video and a green hosted RC workflow on a clean commit
remain external T26/G8 evidence.
