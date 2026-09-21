# Open-source readiness

The source tree uses Apache-2.0. The current publication inventory classifies code,
schemas, documentation, generated demo fixtures, SVG marks and benchmark SUTs as
repository-authored synthetic assets and identifies no vendored third-party dataset.
That classification still requires independent rights review on the clean candidate;
until then it does not authorize publication or prove that `NOTICE` is unnecessary.
The directory-by-directory record is the
[OSS publication inventory](../oss-publication-inventory.md).

Runtime dependencies are Playwright and pytest plus their transitive dependencies. The
installed-wheel inventory records Apache-2.0, MIT, BSD, PSF-2.0 or compatible compound
expressions for the current lock. CI generates an SPDX 2.3 SBOM, distribution
checksums, dependency inventory and build provenance beside every candidate artifact.
`pip-audit` and license review remain required on the final candidate lock.

The 2026-09-06 local history scan used Gitleaks 8.30.1 with redaction: five commits,
about 2.10 MB, no detected leaks. The locked runtime dependency audit reported no known
vulnerabilities. These scans cover known patterns/databases and do not prove that the
tree is free of every secret or vulnerability.

The repository became public and GitHub private vulnerability reporting was enabled and
verified through the API on 21 September 2026. Publication remains blocked until the
final clean RC commit is rescanned and a maintainer reviews all intended source assets.
See [support policy](../../SUPPORT.md), [security policy](../../SECURITY.md), and the
[current release decision](../../release/rc-manifest-v2.json). The manual
`publish.yml` workflow accepts only an existing tag, artifacts from the selected CI
run, and a protected acceptance bundle that makes this manifest validate as `go`.
Its `pypi` environment and trusted-publisher identity must be configured and reviewed
in GitHub/PyPI before the publish job is enabled.
